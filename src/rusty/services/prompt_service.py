from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path

REWRITE_PROMPT_SCHEMA = "rusty.rewrite_prompt"
LEGACY_PROMPT_PACKAGE_SCHEMA = "rusty.prompt_package"
PROMPT_PACKAGE_SCHEMA = REWRITE_PROMPT_SCHEMA
PROMPT_PACKAGE_SCHEMA_VERSION = 2


@dataclass(frozen=True)
class SceneRule:
    scene_key: str
    display_name: str
    description: str = ""
    detection_prompt: str = ""
    rewrite_prompt: str = ""
    sort_order: int = 0


@dataclass(frozen=True)
class PromptTemplate:
    id: int
    name: str
    global_rules: str
    summary_rules: str
    scene_detection_rules: str
    rewrite_rules: str
    description: str
    story_anchor: dict[str, Any]
    characters: list[dict[str, Any]]
    scene_rules: list[SceneRule]
    package_metadata: dict[str, Any]
    source_project_id: int | None
    version: int
    is_default: bool

    def to_package(self) -> dict[str, Any]:
        return {
            "schema": PROMPT_PACKAGE_SCHEMA,
            "schema_version": PROMPT_PACKAGE_SCHEMA_VERSION,
            "name": self.name,
            "description": self.description,
            "system_rules": self.global_rules,
            "scene_recognition": {
                "general_rules": self.scene_detection_rules,
                "categories": [
                    {
                        "key": rule.scene_key,
                        "name": rule.display_name,
                        "description": rule.description,
                        "detection_prompt": rule.detection_prompt,
                    }
                    for rule in self.scene_rules
                ],
            },
            "rewrite_rules": {
                "general": self.rewrite_rules,
                "specific": [
                    {"scene_key": rule.scene_key, "rewrite_prompt": rule.rewrite_prompt}
                    for rule in self.scene_rules
                    if rule.rewrite_prompt.strip()
                ],
            },
            "metadata": {
                **self.package_metadata,
                "template_kind": "rewrite",
            },
        }


class PromptService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_template(
        self,
        name: str,
        global_rules: str = "",
        summary_rules: str = "",
        scene_detection_rules: str = "",
        rewrite_rules: str = "",
        is_default: bool = False,
        description: str = "",
        story_anchor: dict[str, Any] | None = None,
        characters: list[dict[str, Any]] | None = None,
        scene_rules: list[SceneRule | dict[str, Any]] | None = None,
        package_metadata: dict[str, Any] | None = None,
        source_project_id: int | None = None,
    ) -> int:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            cursor = connection.execute(
                """
                INSERT INTO prompt_templates (
                    name, global_rules, summary_rules, scene_detection_rules, rewrite_rules,
                    description, story_anchor_json, characters_json, package_metadata_json,
                    source_project_id, is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    description,
                    _dump_object(story_anchor),
                    _dump_list(characters),
                    _dump_object(package_metadata),
                    source_project_id,
                    1 if is_default else 0,
                ),
            )
            template_id = int(cursor.lastrowid)
            self._replace_scene_rules(connection, template_id, scene_rules or [])
            return template_id

    def update_template(
        self,
        template_id: int,
        name: str,
        global_rules: str,
        summary_rules: str,
        scene_detection_rules: str,
        rewrite_rules: str,
        is_default: bool = False,
        description: str = "",
        story_anchor: dict[str, Any] | None = None,
        characters: list[dict[str, Any]] | None = None,
        scene_rules: list[SceneRule | dict[str, Any]] | None = None,
        package_metadata: dict[str, Any] | None = None,
        source_project_id: int | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            if is_default:
                connection.execute("UPDATE prompt_templates SET is_default = 0 WHERE deleted_at IS NULL")
            cursor = connection.execute(
                """
                UPDATE prompt_templates
                SET name = ?, global_rules = ?, summary_rules = ?, scene_detection_rules = ?,
                    rewrite_rules = ?, description = ?, story_anchor_json = ?, characters_json = ?,
                    package_metadata_json = ?, source_project_id = ?, version = version + 1,
                    is_default = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    name,
                    global_rules,
                    summary_rules,
                    scene_detection_rules,
                    rewrite_rules,
                    description,
                    _dump_object(story_anchor),
                    _dump_list(characters),
                    _dump_object(package_metadata),
                    source_project_id,
                    1 if is_default else 0,
                    template_id,
                ),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Prompt package not found: {template_id}")
            self._replace_scene_rules(connection, template_id, scene_rules or [])

    def delete_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE prompt_templates SET deleted_at = CURRENT_TIMESTAMP, is_default = 0 WHERE id = ?",
                (template_id,),
            )

    def list_templates(self) -> list[PromptTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(self._select_sql() + " ORDER BY is_default DESC, updated_at DESC, id DESC").fetchall()
            return [self._from_row(connection, row) for row in rows]

    def get_template(self, template_id: int) -> PromptTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(self._select_sql("id = ?"), (template_id,)).fetchone()
            return self._from_row(connection, row) if row is not None else None

    def get_default_template(self) -> PromptTemplate | None:
        templates = self.list_templates()
        return templates[0] if templates else None

    def export_template(self, template_id: int) -> str:
        template = self.get_template(template_id)
        if template is None:
            raise ValueError(f"Rewrite prompt not found: {template_id}")
        return json.dumps(template.to_package(), ensure_ascii=False, indent=2)

    def import_template_text(self, content: str) -> int:
        try:
            package = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Rewrite prompt is not valid JSON: {exc}") from exc
        if not isinstance(package, dict):
            raise ValueError("Rewrite prompt must be a JSON object.")
        if package.get("schema") not in (None, REWRITE_PROMPT_SCHEMA, LEGACY_PROMPT_PACKAGE_SCHEMA):
            raise ValueError("Unsupported rewrite prompt schema.")
        version = package.get("schema_version", 1)
        if not isinstance(version, int) or version not in (1, PROMPT_PACKAGE_SCHEMA_VERSION):
            raise ValueError(f"Unsupported rewrite prompt schema version: {version}")
        if package.get("schema") == REWRITE_PROMPT_SCHEMA and version == PROMPT_PACKAGE_SCHEMA_VERSION:
            missing = [
                key
                for key in ("name", "system_rules", "scene_recognition", "rewrite_rules")
                if key not in package
            ]
            if missing:
                raise ValueError(f"Rewrite prompt is missing required fields: {', '.join(missing)}")
            if not isinstance(package["name"], str) or not package["name"].strip():
                raise ValueError("Rewrite prompt field 'name' must be a non-empty string.")
            if not isinstance(package["scene_recognition"], dict):
                raise ValueError("Rewrite prompt field 'scene_recognition' must be an object.")
            if not isinstance(package["rewrite_rules"], dict):
                raise ValueError("Rewrite prompt field 'rewrite_rules' must be an object.")
        payload = _normalize_package(package)
        return self.create_template(**payload)

    def save_project_prompt(self, project_id: int, prompt_key: str, prompt_text: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_custom_prompts (project_id, prompt_key, prompt_text)
                VALUES (?, ?, ?)
                ON CONFLICT(project_id, prompt_key)
                DO UPDATE SET prompt_text = excluded.prompt_text, updated_at = CURRENT_TIMESTAMP
                """,
                (project_id, prompt_key, prompt_text),
            )

    def list_project_prompts(self, project_id: int) -> dict[str, str]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT prompt_key, prompt_text FROM project_custom_prompts WHERE project_id = ? ORDER BY prompt_key",
                (project_id,),
            ).fetchall()
        return {row["prompt_key"]: row["prompt_text"] for row in rows}

    @staticmethod
    def _select_sql(where: str | None = None) -> str:
        sql = """
            SELECT id, name, global_rules, summary_rules, scene_detection_rules, rewrite_rules,
                   description, story_anchor_json, characters_json, package_metadata_json,
                   source_project_id, version, is_default, updated_at
            FROM prompt_templates
            WHERE deleted_at IS NULL
        """
        return sql + (f" AND {where}" if where else "")

    @staticmethod
    def _replace_scene_rules(connection, template_id: int, rules: list[SceneRule | dict[str, Any]]) -> None:
        connection.execute("DELETE FROM prompt_rewrite_rules WHERE template_id = ?", (template_id,))
        connection.execute("DELETE FROM prompt_scene_rules WHERE template_id = ?", (template_id,))
        for index, raw in enumerate(rules):
            rule = raw if isinstance(raw, SceneRule) else SceneRule(
                scene_key=str(raw.get("scene_key") or raw.get("key") or f"scene_{index + 1}"),
                display_name=str(raw.get("display_name") or raw.get("name") or f"场景 {index + 1}"),
                description=str(raw.get("description") or ""),
                detection_prompt=str(raw.get("detection_prompt") or ""),
                rewrite_prompt=str(raw.get("rewrite_prompt") or ""),
                sort_order=int(raw.get("sort_order", index)),
            )
            connection.execute(
                """
                INSERT INTO prompt_scene_rules
                    (template_id, scene_key, display_name, description, detection_prompt, sort_order)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (template_id, rule.scene_key, rule.display_name, rule.description, rule.detection_prompt, rule.sort_order),
            )
            if rule.rewrite_prompt.strip():
                connection.execute(
                    "INSERT INTO prompt_rewrite_rules (template_id, scene_key, rewrite_prompt) VALUES (?, ?, ?)",
                    (template_id, rule.scene_key, rule.rewrite_prompt),
                )

    @staticmethod
    def _from_row(connection, row) -> PromptTemplate:
        rule_rows = connection.execute(
            """
            SELECT s.scene_key, s.display_name, s.description, s.detection_prompt, s.sort_order,
                   COALESCE(r.rewrite_prompt, '') AS rewrite_prompt
            FROM prompt_scene_rules AS s
            LEFT JOIN prompt_rewrite_rules AS r
                ON r.template_id = s.template_id AND r.scene_key = s.scene_key
            WHERE s.template_id = ?
            ORDER BY s.sort_order, s.id
            """,
            (row["id"],),
        ).fetchall()
        return PromptTemplate(
            id=row["id"],
            name=row["name"],
            global_rules=row["global_rules"],
            summary_rules=row["summary_rules"],
            scene_detection_rules=row["scene_detection_rules"],
            rewrite_rules=row["rewrite_rules"],
            description=row["description"],
            story_anchor=_parse_object(row["story_anchor_json"]),
            characters=_parse_list(row["characters_json"]),
            scene_rules=[SceneRule(**dict(rule)) for rule in rule_rows],
            package_metadata=_parse_object(row["package_metadata_json"]),
            source_project_id=row["source_project_id"],
            version=row["version"],
            is_default=bool(row["is_default"]),
        )


def _normalize_package(package: dict[str, Any]) -> dict[str, Any]:
    if any(key in package for key in ("rewriteTemplate", "identifyTemplate", "breakthroughTemplate")):
        return _normalize_legacy_template(package)

    recognition = package.get("scene_recognition") if isinstance(package.get("scene_recognition"), dict) else {}
    rewrite = package.get("rewrite_rules") if isinstance(package.get("rewrite_rules"), dict) else {}
    categories = recognition.get("categories") if isinstance(recognition.get("categories"), list) else []
    specifics = rewrite.get("specific") if isinstance(rewrite.get("specific"), list) else []
    rewrite_by_key = {
        str(item.get("scene_key")): str(item.get("rewrite_prompt") or "")
        for item in specifics
        if isinstance(item, dict) and item.get("scene_key")
    }
    scene_rules = []
    for index, item in enumerate(categories):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or item.get("scene_key") or f"scene_{index + 1}")
        scene_rules.append(
            {
                "scene_key": key,
                "display_name": str(item.get("name") or item.get("display_name") or key),
                "description": str(item.get("description") or ""),
                "detection_prompt": str(item.get("detection_prompt") or ""),
                "rewrite_prompt": rewrite_by_key.get(key, str(item.get("rewrite_prompt") or "")),
                "sort_order": index,
            }
        )
    metadata = package.get("metadata") if isinstance(package.get("metadata"), dict) else {}
    legacy_material: dict[str, Any] = {}
    if isinstance(package.get("story_anchor"), dict) and package.get("story_anchor"):
        legacy_material["story_anchor"] = package["story_anchor"]
    if isinstance(package.get("characters"), list) and package.get("characters"):
        legacy_material["characters"] = package["characters"]
    if legacy_material:
        metadata = {**metadata, "legacy_project_material": legacy_material}
    return {
        "name": str(package.get("name") or "导入的改写提示词"),
        "description": str(package.get("description") or ""),
        "global_rules": str(package.get("system_rules") or package.get("global_rules") or ""),
        "summary_rules": str(package.get("summary_rules") or ""),
        "scene_detection_rules": str(recognition.get("general_rules") or package.get("scene_detection_rules") or ""),
        "rewrite_rules": str(rewrite.get("general") or package.get("rewrite_rules_text") or ""),
        "story_anchor": {},
        "characters": [],
        "scene_rules": scene_rules,
        "package_metadata": metadata,
        "source_project_id": None,
        "is_default": False,
    }


def _normalize_legacy_template(package: dict[str, Any]) -> dict[str, Any]:
    raw_rewrite = package.get("rewriteTemplate")
    raw_identify = package.get("identifyTemplate")
    rewrite_template = _embedded_object(raw_rewrite)
    identify_template = _embedded_object(raw_identify)

    category_prompts = rewrite_template.get("categoryPrompts")
    rewrite_by_key: dict[str, str] = {}
    if isinstance(category_prompts, dict):
        rewrite_by_key = {
            str(key): _legacy_prompt_text(value)
            for key, value in category_prompts.items()
        }

    raw_categories = identify_template.get("categories")
    categories = raw_categories if isinstance(raw_categories, list) else []
    scene_rules: list[dict[str, Any]] = []
    imported_keys: set[str] = set()
    for index, item in enumerate(categories):
        if not isinstance(item, dict):
            continue
        key = str(item.get("id") or item.get("key") or item.get("scene_key") or f"scene_{index + 1}")
        imported_keys.add(key)
        scene_rules.append(
            {
                "scene_key": key,
                "display_name": str(item.get("name") or item.get("display_name") or key),
                "description": _legacy_prompt_text(item.get("description")),
                "detection_prompt": _legacy_prompt_text(
                    item.get("conditions") or item.get("detectionPrompt") or item.get("detection_prompt")
                ),
                "rewrite_prompt": rewrite_by_key.get(key, ""),
                "sort_order": index,
            }
        )

    for key, rewrite_prompt in rewrite_by_key.items():
        if key in imported_keys:
            continue
        scene_rules.append(
            {
                "scene_key": key,
                "display_name": key,
                "rewrite_prompt": rewrite_prompt,
                "sort_order": len(scene_rules),
            }
        )

    rewrite_rules = _legacy_prompt_text(
        rewrite_template.get("commonPrompt") or rewrite_template.get("prompt")
    )
    if not rewrite_template and raw_rewrite is not None:
        rewrite_rules = _legacy_prompt_text(raw_rewrite)

    scene_detection_rules = _legacy_prompt_text(
        identify_template.get("commonPrompt")
        or identify_template.get("generalPrompt")
        or identify_template.get("prompt")
    )
    if not identify_template and raw_identify is not None:
        scene_detection_rules = _legacy_prompt_text(raw_identify)

    metadata: dict[str, Any] = {
        "import_schema": "legacy.prompt_template",
        "legacy_fields": sorted(str(key) for key in package),
    }
    if "breakthroughTemplate" in package:
        metadata["legacy_breakthroughTemplate"] = package.get("breakthroughTemplate")

    return {
        "name": str(package.get("name") or "导入的改写提示词"),
        "description": str(package.get("description") or "从旧版提示词 JSON 导入。"),
        "global_rules": "",
        "summary_rules": "",
        "scene_detection_rules": scene_detection_rules,
        "rewrite_rules": rewrite_rules,
        "story_anchor": {},
        "characters": [],
        "scene_rules": scene_rules,
        "package_metadata": metadata,
        "source_project_id": None,
        "is_default": False,
    }


def _embedded_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _legacy_prompt_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(item) for item in value)
    if isinstance(value, dict):
        nested = value.get("prompt") or value.get("rewritePrompt") or value.get("rewrite_prompt")
        return _legacy_prompt_text(nested) if nested is not None else json.dumps(value, ensure_ascii=False)
    return str(value)


def _dump_object(value: dict[str, Any] | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False)


def _dump_list(value: list[dict[str, Any]] | None) -> str:
    return json.dumps(value or [], ensure_ascii=False)


def _parse_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _parse_list(value: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []
