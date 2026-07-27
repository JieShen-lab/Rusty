from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path
from rusty.services.style_service import DETAIL_LEVELS


MATERIAL_TYPES = {"scene_reference", "plot_skeleton"}
MATERIAL_SCOPES = {"public", "project"}
ANALYSIS_STATUSES = {"unanalyzed", "analyzed"}


@dataclass(frozen=True)
class ResourceTag:
    id: int
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int


@dataclass(frozen=True)
class Material:
    id: int
    material_type: str
    scope: str
    project_id: int | None
    project_name: str | None
    name: str
    description: str
    detail_level: str
    raw_text: str
    content_json: str
    analysis_status: str
    source_metadata_json: str
    import_metadata_json: str
    source_material_id: int | None
    source_version: int | None
    timeline_start_chapter: int | None
    timeline_end_chapter: int | None
    sort_order: int
    version: int
    created_at: str
    updated_at: str
    tags: tuple[str, ...] = ()

MaterialTag = ResourceTag


class MaterialService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def list_materials(
        self,
        *,
        scope: str | None = None,
        project_id: int | None = None,
        material_type: str | None = None,
        tag_id: int | None = None,
        analysis_status: str | None = None,
        untagged: bool = False,
        query: str | None = None,
    ) -> list[Material]:
        if scope is not None:
            _validate_scope(scope, project_id)
        if material_type is not None:
            material_type = _validate_type(material_type)
        if analysis_status is not None:
            analysis_status = _validate_analysis_status(analysis_status)
        clauses = ["m.deleted_at IS NULL"]
        parameters: list[object] = []
        if scope is not None:
            clauses.append("m.scope = ?")
            parameters.append(scope)
        if project_id is not None:
            clauses.append("m.project_id = ?")
            parameters.append(project_id)
        if material_type is not None:
            clauses.append("m.material_type = ?")
            parameters.append(material_type)
        if analysis_status is not None:
            clauses.append("m.analysis_status = ?")
            parameters.append(analysis_status)
        if tag_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM material_tag_links filter_link "
                "WHERE filter_link.material_id = m.id AND filter_link.tag_id = ?)"
            )
            parameters.append(tag_id)
        if untagged:
            clauses.append("NOT EXISTS (SELECT 1 FROM material_tag_links tl WHERE tl.material_id = m.id)")
        if query and query.strip():
            like = f"%{query.strip()}%"
            clauses.append(
                "(m.name LIKE ? OR m.description LIKE ? OR m.raw_text LIKE ? OR "
                "EXISTS (SELECT 1 FROM material_tag_links ql JOIN material_tags qt ON qt.id = ql.tag_id "
                "WHERE ql.material_id = m.id AND qt.deleted_at IS NULL AND qt.name LIKE ?))"
            )
            parameters.extend([like, like, like, like])
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, p.name AS project_name,
                       COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names
                FROM materials m
                LEFT JOIN projects p ON p.id = m.project_id
                LEFT JOIN material_tag_links link ON link.material_id = m.id
                LEFT JOIN material_tags t ON t.id = link.tag_id AND t.deleted_at IS NULL
                WHERE {' AND '.join(clauses)}
                GROUP BY m.id
                ORDER BY m.updated_at DESC, m.id DESC
                """,
                parameters,
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def get_material(self, material_id: int) -> Material | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT m.*, p.name AS project_name,
                       COALESCE(GROUP_CONCAT(t.name, char(31)), '') AS tag_names
                FROM materials m
                LEFT JOIN projects p ON p.id = m.project_id
                LEFT JOIN material_tag_links link ON link.material_id = m.id
                LEFT JOIN material_tags t ON t.id = link.tag_id AND t.deleted_at IS NULL
                WHERE m.id = ? AND m.deleted_at IS NULL
                GROUP BY m.id
                """,
                (material_id,),
            ).fetchone()
        return self._row_to_material(row) if row is not None else None

    def create_material(
        self,
        *,
        material_type: str,
        scope: str,
        name: str,
        project_id: int | None = None,
        description: str = "",
        detail_level: str = "standard",
        raw_text: str = "",
        content: dict[str, Any] | None = None,
        analysis_status: str = "analyzed",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        source_material_id: int | None = None,
        source_version: int | None = None,
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        tag_ids: list[int] | None = None,
    ) -> int:
        material_type = _validate_type(material_type)
        scope = _validate_scope(scope, project_id)
        normalized_name = _required_name(name)
        detail_level = _validate_detail_level(detail_level)
        analysis_status = _validate_analysis_status(analysis_status)
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        with session(self.database_path) as connection:
            if project_id is not None:
                self._require_project(connection, project_id)
            cursor = connection.execute(
                """
                INSERT INTO materials (
                    material_type, scope, project_id, name, description, detail_level,
                    raw_text, content_json, analysis_status, source_metadata_json,
                    import_metadata_json, source_material_id, source_version,
                    timeline_start_chapter, timeline_end_chapter, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_type,
                    scope,
                    project_id,
                    normalized_name,
                    description,
                    detail_level,
                    raw_text,
                    json.dumps(content or {}, ensure_ascii=False),
                    analysis_status,
                    json.dumps(source_metadata or {}, ensure_ascii=False),
                    json.dumps(import_metadata or {}, ensure_ascii=False),
                    source_material_id,
                    source_version,
                    timeline_start_chapter,
                    timeline_end_chapter,
                    sort_order,
                ),
            )
            material_id = int(cursor.lastrowid)
            self._replace_tags(connection, material_id, tag_ids or [])
        return material_id

    def update_material(
        self,
        material_id: int,
        *,
        name: str,
        description: str,
        detail_level: str,
        content: dict[str, Any],
        raw_text: str | None = None,
        analysis_status: str | None = None,
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        tag_ids: list[int] | None = None,
    ) -> None:
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        status = _validate_analysis_status(analysis_status) if analysis_status is not None else None
        with session(self.database_path) as connection:
            current = connection.execute(
                "SELECT id FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Material not found: {material_id}")
            connection.execute(
                """
                UPDATE materials
                SET name = ?, description = ?, detail_level = ?, content_json = ?,
                    raw_text = COALESCE(?, raw_text),
                    analysis_status = COALESCE(?, analysis_status),
                    timeline_start_chapter = ?, timeline_end_chapter = ?, sort_order = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    _required_name(name),
                    description,
                    _validate_detail_level(detail_level),
                    json.dumps(content, ensure_ascii=False),
                    raw_text,
                    status,
                    timeline_start_chapter,
                    timeline_end_chapter,
                    sort_order,
                    material_id,
                ),
            )
            if tag_ids is not None:
                self._replace_tags(connection, material_id, tag_ids)

    def analyze_material(self, material_id: int, *, content: dict[str, Any], model_id: int | None = None) -> None:
        if not isinstance(content, dict) or not content:
            raise ValueError("Material analysis result must be a non-empty object.")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT import_metadata_json FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Material not found: {material_id}")
            metadata = _json_object(str(row["import_metadata_json"]))
            metadata["last_analyzed_model_id"] = model_id
            connection.execute(
                """
                UPDATE materials
                SET content_json = ?, analysis_status = 'analyzed',
                    import_metadata_json = ?, version = version + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(content, ensure_ascii=False), json.dumps(metadata, ensure_ascii=False), material_id),
            )

    def delete_material(self, material_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE materials SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material not found: {material_id}")

    def copy_material(
        self,
        material_id: int,
        *,
        target_scope: str,
        target_project_id: int | None = None,
        tag_ids: list[int] | None = None,
    ) -> int:
        source = self.get_material(material_id)
        if source is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        copied_id = self.create_material(
            material_type=source.material_type,
            scope=target_scope,
            project_id=target_project_id,
            name=source.name,
            description=source.description,
            detail_level=source.detail_level,
            raw_text=source.raw_text,
            content=_json_object(source.content_json),
            analysis_status=source.analysis_status,
            source_metadata={
                **_json_object(source.source_metadata_json),
                "copied_from_scope": source.scope,
                "copied_from_project_id": source.project_id,
            },
            import_metadata={
                **_json_object(source.import_metadata_json),
                "created_by": "material_copy",
                "source_material_id": source.id,
                "source_version": source.version,
            },
            source_material_id=source.id,
            source_version=source.version,
            timeline_start_chapter=source.timeline_start_chapter,
            timeline_end_chapter=source.timeline_end_chapter,
            sort_order=source.sort_order,
            tag_ids=tag_ids,
        )
        if tag_ids is None:
            with session(self.database_path) as connection:
                source_tags = [
                    int(row["tag_id"])
                    for row in connection.execute(
                        "SELECT tag_id FROM material_tag_links WHERE material_id = ?",
                        (source.id,),
                    ).fetchall()
                ]
                self._replace_tags(connection, copied_id, source_tags)
        return copied_id

    def list_tags(self) -> list[MaterialTag]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT t.*, COUNT(m.id) AS resource_count
                FROM material_tags t
                LEFT JOIN material_tag_links link ON link.tag_id = t.id
                LEFT JOIN materials m ON m.id = link.material_id AND m.deleted_at IS NULL
                WHERE t.deleted_at IS NULL
                GROUP BY t.id
                ORDER BY t.sort_order, t.name
                """
            ).fetchall()
        return [self._row_to_tag(row) for row in rows]

    def create_tag(self, name: str) -> MaterialTag:
        normalized_name = _required_tag_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO material_tags (name, normalized_name)
                VALUES (?, ?)
                ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (normalized_name, _normalize_tag_name(normalized_name)),
            )
            tag_id = int(cursor.lastrowid) if cursor.lastrowid else int(
                connection.execute(
                    "SELECT id FROM material_tags WHERE normalized_name = ? AND deleted_at IS NULL",
                    (_normalize_tag_name(normalized_name),),
                ).fetchone()["id"]
            )
        return next(item for item in self.list_tags() if item.id == tag_id)

    def rename_tag(self, tag_id: int, name: str) -> MaterialTag:
        normalized_name = _required_tag_name(name)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE material_tags
                SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (normalized_name, _normalize_tag_name(normalized_name), tag_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material tag not found: {tag_id}")
        return next(item for item in self.list_tags() if item.id == tag_id)

    def delete_tag(self, tag_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM material_tag_links WHERE tag_id = ?", (tag_id,))
            cursor = connection.execute(
                "UPDATE material_tags SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (tag_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Material tag not found: {tag_id}")

    def set_material_tag(self, material_id: int, tag_id: int, selected: bool) -> Material:
        with session(self.database_path) as connection:
            self._require_material(connection, material_id)
            self._require_tag(connection, tag_id)
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO material_tag_links (material_id, tag_id) VALUES (?, ?)",
                    (material_id, tag_id),
                )
            else:
                connection.execute(
                    "DELETE FROM material_tag_links WHERE material_id = ? AND tag_id = ?",
                    (material_id, tag_id),
                )
        material = self.get_material(material_id)
        if material is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        return material

    @staticmethod
    def _require_project(connection, project_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Project not found: {project_id}")

    @staticmethod
    def _require_material(connection, material_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM materials WHERE id = ? AND deleted_at IS NULL",
            (material_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Material not found: {material_id}")

    @staticmethod
    def _require_tag(connection, tag_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM material_tags WHERE id = ? AND deleted_at IS NULL",
            (tag_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Material tag not found: {tag_id}")

    @staticmethod
    def _replace_tags(connection, material_id: int, tag_ids: list[int]) -> None:
        connection.execute("DELETE FROM material_tag_links WHERE material_id = ?", (material_id,))
        for tag_id in dict.fromkeys(tag_ids):
            MaterialService._require_tag(connection, int(tag_id))
            connection.execute(
                "INSERT INTO material_tag_links (material_id, tag_id) VALUES (?, ?)",
                (material_id, int(tag_id)),
            )

    @staticmethod
    def _row_to_material(row) -> Material:
        tag_names = str(row["tag_names"] or "")
        return Material(
            id=int(row["id"]),
            material_type=str(row["material_type"]),
            scope=str(row["scope"]),
            project_id=int(row["project_id"]) if row["project_id"] is not None else None,
            project_name=str(row["project_name"]) if row["project_name"] is not None else None,
            name=str(row["name"]),
            description=str(row["description"]),
            detail_level=str(row["detail_level"]),
            raw_text=str(row["raw_text"]),
            content_json=str(row["content_json"]),
            analysis_status=str(row["analysis_status"]),
            source_metadata_json=str(row["source_metadata_json"]),
            import_metadata_json=str(row["import_metadata_json"]),
            source_material_id=int(row["source_material_id"]) if row["source_material_id"] is not None else None,
            source_version=int(row["source_version"]) if row["source_version"] is not None else None,
            timeline_start_chapter=(
                int(row["timeline_start_chapter"]) if row["timeline_start_chapter"] is not None else None
            ),
            timeline_end_chapter=(
                int(row["timeline_end_chapter"]) if row["timeline_end_chapter"] is not None else None
            ),
            sort_order=int(row["sort_order"]),
            version=int(row["version"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
            tags=tuple(item for item in tag_names.split(chr(31)) if item),
        )

    @staticmethod
    def _row_to_tag(row) -> MaterialTag:
        return MaterialTag(
            id=int(row["id"]),
            name=str(row["name"]),
            normalized_name=str(row["normalized_name"]),
            sort_order=int(row["sort_order"]),
            resource_count=int(row["resource_count"]),
        )


def _validate_type(value: str) -> str:
    if value not in MATERIAL_TYPES:
        raise ValueError(f"Unsupported material type: {value}")
    return value


def _validate_scope(value: str, project_id: int | None) -> str:
    if value not in MATERIAL_SCOPES:
        raise ValueError(f"Unsupported material scope: {value}")
    if value == "project" and project_id is None:
        raise ValueError("Project materials require a project_id.")
    if value == "public" and project_id is not None:
        raise ValueError("Public materials cannot belong to a project.")
    return value


def _validate_analysis_status(value: str) -> str:
    if value not in ANALYSIS_STATUSES:
        raise ValueError(f"Unsupported analysis status: {value}")
    return value


def _validate_detail_level(value: str) -> str:
    if value not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {value}")
    return value


def _required_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("Material name is required.")
    return normalized


def _required_tag_name(value: str) -> str:
    normalized = " ".join(value.strip().split())
    if not normalized:
        raise ValueError("Tag name is required.")
    if len(normalized) > 40:
        raise ValueError("Tag name must be 40 characters or fewer.")
    return normalized


def _normalize_tag_name(value: str) -> str:
    return " ".join(value.strip().split()).casefold()


def _validate_timeline(start: int | None, end: int | None) -> None:
    if start is not None and start < 1:
        raise ValueError("timeline_start_chapter must be greater than 0.")
    if end is not None and end < 1:
        raise ValueError("timeline_end_chapter must be greater than 0.")
    if start is not None and end is not None and end < start:
        raise ValueError("timeline_end_chapter cannot be before timeline_start_chapter.")


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
