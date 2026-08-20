from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, session
from rusty.services.style_service import DETAIL_LEVELS


@dataclass(frozen=True)
class OutlineTemplate:
    id: int
    name: str
    description: str
    detail_level: str
    outline_json: str
    anchor_prompt: str
    source_metadata_json: str
    import_metadata_json: str
    version: int


class AnchorService:
    """Legacy outline-template storage retained for projects that still use it."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

    def create_outline_template(
        self, name: str, description: str = "", detail_level: str = "standard",
        outline: dict[str, Any] | None = None, anchor_prompt: str = "",
        source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> int:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO outline_templates (
                    name, description, detail_level, outline_json, anchor_prompt,
                    source_metadata_json, import_metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (_required_name(name), description, _validate_detail_level(detail_level),
                 json.dumps(outline or {}, ensure_ascii=False), anchor_prompt,
                 json.dumps(source_metadata or {}, ensure_ascii=False),
                 json.dumps(import_metadata or {}, ensure_ascii=False)),
            )
            return int(cursor.lastrowid)

    def update_outline_template(
        self, template_id: int, name: str, description: str = "",
        detail_level: str = "standard", outline: dict[str, Any] | None = None,
        anchor_prompt: str = "", source_metadata: dict[str, Any] | None = None,
        import_metadata: dict[str, Any] | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE outline_templates
                SET name=?, description=?, detail_level=?, outline_json=?, anchor_prompt=?,
                    source_metadata_json=?, import_metadata_json=?, version=version+1,
                    updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND deleted_at IS NULL
                """,
                (_required_name(name), description, _validate_detail_level(detail_level),
                 json.dumps(outline or {}, ensure_ascii=False), anchor_prompt,
                 json.dumps(source_metadata or {}, ensure_ascii=False),
                 json.dumps(import_metadata or {}, ensure_ascii=False), template_id),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Outline template not found: {template_id}")

    def delete_outline_template(self, template_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE outline_templates SET deleted_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE id=? AND deleted_at IS NULL
                """, (template_id,),
            )
            connection.execute(
                """
                UPDATE project_outline_bindings SET is_active=0, updated_at=CURRENT_TIMESTAMP
                WHERE outline_template_id=?
                """, (template_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Outline template not found: {template_id}")

    def list_outline_templates(self) -> list[OutlineTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id, name, description, detail_level, outline_json, anchor_prompt,
                       source_metadata_json, import_metadata_json, version
                FROM outline_templates WHERE deleted_at IS NULL
                ORDER BY updated_at DESC, id DESC
                """
            ).fetchall()
        return [self._outline_from_row(row) for row in rows]

    def get_outline_template(self, template_id: int) -> OutlineTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id, name, description, detail_level, outline_json, anchor_prompt,
                       source_metadata_json, import_metadata_json, version
                FROM outline_templates WHERE id=? AND deleted_at IS NULL
                """, (template_id,),
            ).fetchone()
        return self._outline_from_row(row) if row is not None else None

    def bind_project_outline(self, project_id: int, template_id: int) -> None:
        if self.get_outline_template(template_id) is None:
            raise ValueError(f"Outline template not found: {template_id}")
        self._ensure_project_exists(project_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_outline_bindings(project_id, outline_template_id, is_active)
                VALUES (?, ?, 1)
                ON CONFLICT(project_id) DO UPDATE SET outline_template_id=excluded.outline_template_id,
                    is_active=1, updated_at=CURRENT_TIMESTAMP
                """, (project_id, template_id),
            )

    def unbind_project_outline(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE project_outline_bindings SET is_active=0, updated_at=CURRENT_TIMESTAMP
                WHERE project_id=?
                """, (project_id,),
            )

    def get_project_outline_template(self, project_id: int) -> OutlineTemplate | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT o.id, o.name, o.description, o.detail_level, o.outline_json, o.anchor_prompt,
                       o.source_metadata_json, o.import_metadata_json, o.version
                FROM project_outline_bindings b JOIN outline_templates o ON o.id=b.outline_template_id
                WHERE b.project_id=? AND b.is_active=1 AND o.deleted_at IS NULL
                """, (project_id,),
            ).fetchone()
        return self._outline_from_row(row) if row is not None else None

    def _ensure_project_exists(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM projects WHERE id=? AND deleted_at IS NULL", (project_id,)
            ).fetchone()
        if row is None:
            raise ValueError(f"Project not found: {project_id}")

    @staticmethod
    def _outline_from_row(row: Any) -> OutlineTemplate:
        return OutlineTemplate(
            id=int(row["id"]), name=str(row["name"]), description=str(row["description"]),
            detail_level=str(row["detail_level"]), outline_json=str(row["outline_json"]),
            anchor_prompt=str(row["anchor_prompt"]),
            source_metadata_json=str(row["source_metadata_json"]),
            import_metadata_json=str(row["import_metadata_json"]), version=int(row["version"]),
        )


def _required_name(value: str) -> str:
    name = value.strip()
    if not name:
        raise ValueError("Outline template name is required.")
    return name


def _validate_detail_level(value: str) -> str:
    level = value.strip().lower()
    if level not in DETAIL_LEVELS:
        raise ValueError(f"Unsupported detail level: {value}")
    return level
