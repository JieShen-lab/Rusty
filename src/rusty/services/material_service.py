from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, session


DETAIL_LEVELS = {"brief", "standard", "detailed"}


@dataclass(frozen=True)
class MaterialAISettings:
    task_type: str
    model_id: int | None
    detail_level: str
    extraction_rules: str
    base_instruction: str
    dimensions: tuple[dict[str, str], ...]
    extra_requirements: str
    updated_at: str


@dataclass(frozen=True)
class Material:
    id: int
    name: str
    raw_text: str
    content_json: str
    source_metadata_json: str
    created_at: str
    updated_at: str


class MaterialService:
    """Persist the current global author-style library and its extraction settings."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

    def list_materials(
        self,
        *,
        query: str | None = None,
    ) -> list[Material]:
        clauses = ["m.deleted_at IS NULL"]
        parameters: list[Any] = []
        if query and query.strip():
            clauses.append("(m.name LIKE ? OR json_extract(m.content_json, '$.work') LIKE ?)")
            like = f"%{query.strip()}%"
            parameters.extend([like, like])
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT m.*
                FROM materials m WHERE {' AND '.join(clauses)}
                ORDER BY m.updated_at DESC, m.id DESC
                """,
                parameters,
            ).fetchall()
        return [self._material(row) for row in rows]

    def get_material(self, material_id: int) -> Material | None:
        return next((item for item in self.list_materials() if item.id == material_id), None)

    def create_material(
        self,
        *,
        name: str,
        raw_text: str = "",
        content: dict[str, Any],
        source_metadata: dict[str, Any] | None = None,
    ) -> int:
        clean_name = _required_name(name)
        metadata = canonical_source_metadata(source_metadata)
        normalized = normalize_author_style_content(content)
        if not normalized["work"]:
            normalized["work"] = material_work_from_source_metadata(metadata)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO materials(
                    name, raw_text, content_json, source_metadata_json
                ) VALUES(?,?,?,?)
                """,
                (
                    clean_name,
                    raw_text,
                    json.dumps(normalized, ensure_ascii=False),
                    json.dumps(metadata, ensure_ascii=False),
                ),
            )
            return int(cursor.lastrowid)

    def update_material(
        self,
        material_id: int,
        *,
        name: str,
        content: dict[str, Any],
    ) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE materials SET name=?, content_json=?, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND deleted_at IS NULL
                """,
                (
                    _required_name(name),
                    json.dumps(normalize_author_style_content(content), ensure_ascii=False),
                    material_id,
                ),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Author style not found: {material_id}")

    def delete_material(self, material_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE materials SET deleted_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL",
                (material_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Author style not found: {material_id}")

    def get_ai_settings(self, task_type: str) -> MaterialAISettings:
        if task_type != "author_style_extraction":
            raise ValueError(f"Unsupported material AI task type: {task_type}")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM material_ai_settings WHERE task_type='author_style_extraction'"
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Author style extraction settings are missing.")
        return MaterialAISettings(
            task_type="author_style_extraction",
            model_id=int(row["model_id"]) if row["model_id"] is not None else None,
            detail_level=str(row["detail_level"]),
            extraction_rules=str(row["extraction_rules"]),
            base_instruction=str(row["base_instruction"]),
            dimensions=tuple(_dimension_definitions(row["dimensions_json"])),
            extra_requirements=str(row["extra_requirements"]),
            updated_at=str(row["updated_at"]),
        )

    def update_ai_settings(
        self,
        task_type: str,
        *,
        model_id: int | None,
        detail_level: str,
        extraction_rules: str,
        base_instruction: str,
        dimensions: list[dict[str, str]],
        extra_requirements: str,
    ) -> MaterialAISettings:
        if task_type != "author_style_extraction":
            raise ValueError(f"Unsupported material AI task type: {task_type}")
        _detail_level(detail_level)
        normalized_dimensions = _normalized_dimension_definitions(dimensions)
        with session(self.database_path) as connection:
            if model_id is not None and connection.execute(
                "SELECT 1 FROM ai_models WHERE id=? AND deleted_at IS NULL", (model_id,)
            ).fetchone() is None:
                raise FileNotFoundError(f"AI model not found: {model_id}")
            connection.execute(
                """
                UPDATE material_ai_settings SET model_id=?, detail_level=?, extraction_rules=?,
                    base_instruction=?, dimensions_json=?, extra_requirements=?, updated_at=CURRENT_TIMESTAMP
                WHERE task_type='author_style_extraction'
                """,
                (
                    model_id,
                    detail_level,
                    _limited(extraction_rules, "extraction_rules"),
                    _limited(base_instruction, "base_instruction"),
                    json.dumps(normalized_dimensions, ensure_ascii=False),
                    _limited(extra_requirements, "extra_requirements"),
                ),
            )
        return self.get_ai_settings(task_type)

    def export_author_style_settings(self) -> dict[str, Any]:
        settings = self.get_ai_settings("author_style_extraction")
        return {
            "schema_version": 2,
            "config_type": "author_style_extraction",
            "detail_level": settings.detail_level,
            "extraction_rules": settings.extraction_rules,
            "base_instruction": settings.base_instruction,
            "dimensions": [dict(item) for item in settings.dimensions],
            "extra_requirements": settings.extra_requirements,
        }

    def import_author_style_settings(self, value: object) -> MaterialAISettings:
        if not isinstance(value, dict):
            raise ValueError("Author style settings JSON must be an object.")
        if value.get("schema_version") != 2 or value.get("config_type") != "author_style_extraction":
            raise ValueError("Invalid author style extraction settings file.")
        dimensions = value.get("dimensions")
        if not isinstance(dimensions, list) or any(not isinstance(item, dict) for item in dimensions):
            raise ValueError("dimensions must be an array of objects.")
        current = self.get_ai_settings("author_style_extraction")
        return self.update_ai_settings(
            "author_style_extraction",
            model_id=current.model_id,
            detail_level=str(value.get("detail_level") or ""),
            extraction_rules=_limited(value.get("extraction_rules"), "extraction_rules"),
            base_instruction=_limited(value.get("base_instruction"), "base_instruction"),
            dimensions=[dict(item) for item in dimensions],
            extra_requirements=_limited(value.get("extra_requirements"), "extra_requirements"),
        )

    @staticmethod
    def _material(row) -> Material:
        metadata = _json_object(row["source_metadata_json"])
        return Material(
            id=int(row["id"]),
            name=str(row["name"]),
            raw_text=str(row["raw_text"]),
            content_json=str(row["content_json"]),
            source_metadata_json=json.dumps(metadata, ensure_ascii=False),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )


def merge_author_style_content(value: object, configured_dimensions: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    returned = {
        str(item.get("id") or "").strip(): item
        for item in source.get("dimensions", [])
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    } if isinstance(source.get("dimensions"), list) else {}
    dimensions: list[dict[str, Any]] = []
    for configured in configured_dimensions if isinstance(configured_dimensions, (list, tuple)) else []:
        if not isinstance(configured, dict):
            continue
        dimension_id = str(configured.get("id") or "").strip()
        if not dimension_id:
            continue
        item = returned.get(dimension_id, {})
        dimensions.append({
            "id": dimension_id,
            "name": str(configured.get("name") or "未命名维度").strip(),
            "analysis": str(item.get("analysis") or "").strip(),
            "features": _strings(item.get("features")),
            "examples": _strings(item.get("examples")),
        })
    return {
        "schema_version": 1,
        "work": str(source.get("work") or "").strip(),
        "overall_style": str(source.get("overall_style") or "").strip(),
        "dimensions": dimensions,
    }


def normalize_author_style_content(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    dimensions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in source.get("dimensions", []) if isinstance(source.get("dimensions"), list) else []:
        if not isinstance(item, dict):
            continue
        dimension_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        if not dimension_id or dimension_id in seen or not name:
            raise ValueError("Every author-style dimension requires a unique stable id and a name.")
        seen.add(dimension_id)
        dimensions.append({
            "id": dimension_id,
            "name": name,
            "analysis": str(item.get("analysis") or "").strip(),
            "features": _strings(item.get("features")),
            "examples": _strings(item.get("examples")),
        })
    return {
        "schema_version": 1,
        "work": str(source.get("work") or "").strip(),
        "overall_style": str(source.get("overall_style") or "").strip(),
        "dimensions": dimensions,
    }


def canonical_source_metadata(value: object) -> dict[str, Any]:
    source = dict(value) if isinstance(value, dict) else {}
    return {
        key: source[key]
        for key in ("source_type", "source_file_name", "source_path", "source_format", "book_title")
        if source.get(key) not in {None, ""}
    }


def material_work_from_source_metadata(value: object) -> str:
    source = value if isinstance(value, dict) else {}
    file_name = str(source.get("source_file_name") or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if file_name:
        suffix = Path(file_name).suffix
        return file_name[:-len(suffix)] if suffix else file_name
    return str(source.get("book_title") or "").strip()


def _required_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Author name is required.")
    return normalized


def _detail_level(value: str) -> str:
    if value not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {value}")
    return value


def _limited(value: object, field: str) -> str:
    text = str(value or "")
    if len(text) > 12000:
        raise ValueError(f"{field} must be 12000 characters or fewer.")
    return text


def _normalized_dimension_definitions(values: list[dict[str, str]]) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in values:
        dimension_id = str(item.get("id") or "").strip()
        name = str(item.get("name") or "").strip()
        requirement = str(item.get("requirement") or "").strip()
        if not dimension_id or dimension_id in seen or not name:
            raise ValueError("Each dimension requires a unique stable id and a name.")
        seen.add(dimension_id)
        result.append({"id": dimension_id, "name": name, "requirement": requirement})
    return result


def _dimension_definitions(value: object) -> list[dict[str, str]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return _normalized_dimension_definitions([dict(item) for item in parsed if isinstance(item, dict)]) if isinstance(parsed, list) else []


def _json_object(value: object) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _strings(value: object) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []
