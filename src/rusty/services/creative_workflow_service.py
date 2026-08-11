from __future__ import annotations

from pathlib import Path
from typing import Any

from rusty.db import default_database_path, initialize_database, session


WORKFLOW_STAGES = (
    "not_started",
    "preanalysis",
    "direction",
    "special_analysis",
    "target_design",
    "writing",
    "review",
    "confirmed",
)


class CreativeWorkflowService:
    """Persistence boundary for the chapter-centric creative workflow."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def list_chapter_states(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO chapter_workflow_state (chapter_id)
                SELECT id FROM chapters WHERE project_id = ?
                """,
                (project_id,),
            )
            rows = connection.execute(
                """
                SELECT c.id AS chapter_id, c.chapter_index, c.title,
                       state.active_scene_id, state.current_stage, state.updated_at
                FROM chapters c
                JOIN chapter_workflow_state state ON state.chapter_id = c.id
                WHERE c.project_id = ?
                ORDER BY c.chapter_index
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chapter_state(self, chapter_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO chapter_workflow_state (chapter_id) VALUES (?)",
                (chapter_id,),
            )
            row = connection.execute(
                """
                SELECT c.id AS chapter_id, c.chapter_index, c.title,
                       state.active_scene_id, state.current_stage, state.updated_at
                FROM chapters c
                JOIN chapter_workflow_state state ON state.chapter_id = c.id
                WHERE c.id = ?
                """,
                (chapter_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        return dict(row)

    def update_chapter_state(
        self,
        chapter_id: int,
        *,
        active_scene_id: int | None,
        current_stage: str,
    ) -> dict[str, Any]:
        if current_stage not in WORKFLOW_STAGES:
            raise ValueError(f"Unsupported creative workflow stage: {current_stage}")
        with session(self.database_path) as connection:
            chapter = connection.execute(
                "SELECT project_id FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            if chapter is None:
                raise FileNotFoundError(f"Chapter not found: {chapter_id}")
            if active_scene_id is not None:
                scene = connection.execute(
                    "SELECT chapter_id FROM scenes WHERE id = ? AND deleted_at IS NULL",
                    (active_scene_id,),
                ).fetchone()
                if scene is None or int(scene["chapter_id"]) != chapter_id:
                    raise ValueError("Active scene must belong to the selected chapter.")
            connection.execute(
                """
                INSERT INTO chapter_workflow_state (
                    chapter_id, active_scene_id, current_stage, updated_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    active_scene_id = excluded.active_scene_id,
                    current_stage = excluded.current_stage,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chapter_id, active_scene_id, current_stage),
            )
        return self.get_chapter_state(chapter_id)
