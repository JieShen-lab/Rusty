from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path
from rusty.services.style_service import DETAIL_LEVELS


MATERIAL_TYPES = {"outline", "plot_skeleton", "snippet"}
MATERIAL_SCOPES = {"public", "project"}


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
    content_json: str
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
    categories: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaterialCategory:
    id: int
    name: str
    material_type: str
    sort_order: int
    material_count: int


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
        category_id: int | None = None,
    ) -> list[Material]:
        if scope is not None:
            _validate_scope(scope, project_id)
        if material_type is not None:
            _validate_type(material_type)
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
        if category_id is not None:
            clauses.append(
                "EXISTS (SELECT 1 FROM material_category_links filter_link "
                "WHERE filter_link.material_id = m.id AND filter_link.category_id = ?)"
            )
            parameters.append(category_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT m.*, p.name AS project_name,
                       COALESCE(GROUP_CONCAT(c.name, char(31)), '') AS category_names
                FROM materials m
                LEFT JOIN projects p ON p.id = m.project_id
                LEFT JOIN material_category_links link ON link.material_id = m.id
                LEFT JOIN material_categories c
                    ON c.id = link.category_id AND c.deleted_at IS NULL
                WHERE {' AND '.join(clauses)}
                GROUP BY m.id
                ORDER BY
                    CASE WHEN m.timeline_start_chapter IS NULL THEN 1 ELSE 0 END,
                    m.timeline_start_chapter,
                    m.sort_order,
                    m.updated_at DESC,
                    m.id DESC
                """,
                parameters,
            ).fetchall()
        return [self._row_to_material(row) for row in rows]

    def get_material(self, material_id: int) -> Material | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT m.*, p.name AS project_name,
                       COALESCE(GROUP_CONCAT(c.name, char(31)), '') AS category_names
                FROM materials m
                LEFT JOIN projects p ON p.id = m.project_id
                LEFT JOIN material_category_links link ON link.material_id = m.id
                LEFT JOIN material_categories c
                    ON c.id = link.category_id AND c.deleted_at IS NULL
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
        content: dict[str, Any] | None = None,
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
        source_material_id: int | None = None,
        source_version: int | None = None,
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        category_ids: list[int] | None = None,
    ) -> int:
        material_type = _validate_type(material_type)
        scope = _validate_scope(scope, project_id)
        normalized_name = _required_name(name)
        detail_level = _validate_detail_level(detail_level)
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        with session(self.database_path) as connection:
            if project_id is not None:
                self._require_project(connection, project_id)
            cursor = connection.execute(
                """
                INSERT INTO materials (
                    material_type, scope, project_id, name, description, detail_level,
                    content_json, source_metadata_json, import_metadata_json,
                    source_material_id, source_version, timeline_start_chapter,
                    timeline_end_chapter, sort_order
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    material_type,
                    scope,
                    project_id,
                    normalized_name,
                    description,
                    detail_level,
                    json.dumps(content or {}, ensure_ascii=False),
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
            if scope == "public":
                self._replace_categories(connection, material_id, material_type, category_ids or [])
        return material_id

    def update_material(
        self,
        material_id: int,
        *,
        name: str,
        description: str,
        detail_level: str,
        content: dict[str, Any],
        timeline_start_chapter: int | None = None,
        timeline_end_chapter: int | None = None,
        sort_order: int = 0,
        category_ids: list[int] | None = None,
    ) -> None:
        _validate_timeline(timeline_start_chapter, timeline_end_chapter)
        with session(self.database_path) as connection:
            current = connection.execute(
                "SELECT material_type, scope FROM materials WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"找不到素材：{material_id}")
            connection.execute(
                """
                UPDATE materials
                SET name = ?, description = ?, detail_level = ?, content_json = ?,
                    timeline_start_chapter = ?, timeline_end_chapter = ?, sort_order = ?,
                    version = version + 1, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    _required_name(name),
                    description,
                    _validate_detail_level(detail_level),
                    json.dumps(content, ensure_ascii=False),
                    timeline_start_chapter,
                    timeline_end_chapter,
                    sort_order,
                    material_id,
                ),
            )
            if str(current["scope"]) == "public" and category_ids is not None:
                self._replace_categories(
                    connection,
                    material_id,
                    str(current["material_type"]),
                    category_ids,
                )

    def delete_material(self, material_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE materials SET deleted_at = CURRENT_TIMESTAMP WHERE id = ? AND deleted_at IS NULL",
                (material_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"找不到素材：{material_id}")

    def copy_material(
        self,
        material_id: int,
        *,
        target_scope: str,
        target_project_id: int | None = None,
        category_ids: list[int] | None = None,
    ) -> int:
        source = self.get_material(material_id)
        if source is None:
            raise FileNotFoundError(f"找不到素材：{material_id}")
        return self.create_material(
            material_type=source.material_type,
            scope=target_scope,
            project_id=target_project_id,
            name=source.name,
            description=source.description,
            detail_level=source.detail_level,
            content=_json_object(source.content_json),
            source_metadata={
                **_json_object(source.source_metadata_json),
                "copied_from_scope": source.scope,
                "copied_from_project_id": source.project_id,
            },
            import_metadata={
                "created_by": "material_copy",
                "source_material_id": source.id,
                "source_version": source.version,
            },
            source_material_id=source.id,
            source_version=source.version,
            timeline_start_chapter=source.timeline_start_chapter,
            timeline_end_chapter=source.timeline_end_chapter,
            sort_order=source.sort_order,
            category_ids=category_ids,
        )

    def list_categories(self, material_type: str | None = None) -> list[MaterialCategory]:
        if material_type is not None:
            _validate_type(material_type)
        parameters: list[object] = []
        type_clause = ""
        if material_type is not None:
            type_clause = "AND c.material_type = ?"
            parameters.append(material_type)
        with session(self.database_path) as connection:
            rows = connection.execute(
                f"""
                SELECT c.*, COUNT(link.material_id) AS material_count
                FROM material_categories c
                LEFT JOIN material_category_links link ON link.category_id = c.id
                LEFT JOIN materials m ON m.id = link.material_id AND m.deleted_at IS NULL
                WHERE c.deleted_at IS NULL {type_clause}
                GROUP BY c.id
                ORDER BY c.sort_order, c.name
                """,
                parameters,
            ).fetchall()
        return [
            MaterialCategory(
                id=int(row["id"]),
                name=str(row["name"]),
                material_type=str(row["material_type"]),
                sort_order=int(row["sort_order"]),
                material_count=int(row["material_count"]),
            )
            for row in rows
        ]

    def create_category(self, name: str, material_type: str) -> MaterialCategory:
        normalized_name = _required_name(name)
        material_type = _validate_type(material_type)
        with session(self.database_path) as connection:
            duplicate = connection.execute(
                """
                SELECT id FROM material_categories
                WHERE lower(name) = lower(?) AND material_type = ? AND deleted_at IS NULL
                """,
                (normalized_name, material_type),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("当前素材类型下已经存在同名分类。")
            cursor = connection.execute(
                "INSERT INTO material_categories (name, material_type) VALUES (?, ?)",
                (normalized_name, material_type),
            )
            category_id = int(cursor.lastrowid)
        return next(item for item in self.list_categories(material_type) if item.id == category_id)

    @staticmethod
    def _require_project(connection, project_id: int) -> None:
        row = connection.execute(
            "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
            (project_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"找不到工程：{project_id}")

    @staticmethod
    def _replace_categories(
        connection,
        material_id: int,
        material_type: str,
        category_ids: list[int],
    ) -> None:
        connection.execute("DELETE FROM material_category_links WHERE material_id = ?", (material_id,))
        for category_id in dict.fromkeys(category_ids):
            category = connection.execute(
                """
                SELECT id FROM material_categories
                WHERE id = ? AND material_type = ? AND deleted_at IS NULL
                """,
                (category_id, material_type),
            ).fetchone()
            if category is None:
                raise ValueError("素材分类不存在或与素材类型不匹配。")
            connection.execute(
                "INSERT INTO material_category_links (material_id, category_id) VALUES (?, ?)",
                (material_id, category_id),
            )

    @staticmethod
    def _row_to_material(row) -> Material:
        category_names = str(row["category_names"] or "")
        return Material(
            id=int(row["id"]),
            material_type=str(row["material_type"]),
            scope=str(row["scope"]),
            project_id=int(row["project_id"]) if row["project_id"] is not None else None,
            project_name=str(row["project_name"]) if row["project_name"] is not None else None,
            name=str(row["name"]),
            description=str(row["description"]),
            detail_level=str(row["detail_level"]),
            content_json=str(row["content_json"]),
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
            categories=tuple(item for item in category_names.split(chr(31)) if item),
        )


def _validate_type(value: str) -> str:
    if value not in MATERIAL_TYPES:
        raise ValueError(f"不支持的素材类型：{value}")
    return value


def _validate_scope(value: str, project_id: int | None) -> str:
    if value not in MATERIAL_SCOPES:
        raise ValueError(f"不支持的素材作用域：{value}")
    if value == "project" and project_id is None:
        raise ValueError("工程素材必须指定工程。")
    if value == "public" and project_id is not None:
        raise ValueError("公共素材不能关联工程。")
    return value


def _validate_detail_level(value: str) -> str:
    if value not in DETAIL_LEVELS:
        raise ValueError(f"不支持的细节等级：{value}")
    return value


def _required_name(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("素材名称不能为空。")
    return normalized


def _validate_timeline(start: int | None, end: int | None) -> None:
    if start is not None and start < 1:
        raise ValueError("起始章节必须大于 0。")
    if end is not None and end < 1:
        raise ValueError("结束章节必须大于 0。")
    if start is not None and end is not None and end < start:
        raise ValueError("结束章节不能早于起始章节。")


def _json_object(value: str) -> dict[str, Any]:
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
