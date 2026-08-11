from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, initialize_database, session
from rusty.services.scene_service import SceneService
from rusty.services.workflow_ai import WorkflowAI


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

    def __init__(self, database_path: str | Path | None = None, *, ai_client: Any | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)
        self.scenes = SceneService(self.database_path)
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)

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

    def get_preanalysis(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scene_preanalyses WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        return self._preanalysis_from_row(row) if row is not None else None

    def run_preanalysis(self, scene_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        current = self.get_preanalysis(scene_id)
        if current and current["user_edited"] and not replace_existing:
            raise ValueError("Reanalysis would replace the user-edited preanalysis result.")
        value = self.ai.generate_json(
            project_id=scene.project_id,
            stage="scene_preanalysis",
            payload={
                "scene_id": scene.id,
                "source_text": scene.original_text,
                "source_start_offset": scene.original_start_offset,
                "source_end_offset": scene.original_end_offset,
            },
            output_contract=(
                "Return summary:string, characters:string[], location:string, time:string, "
                "scene_type:string, basic_events:string[]. Do not perform detailed character "
                "state, causality, or rewrite planning analysis."
            ),
            task_key="scene_preanalysis",
        )
        normalized = self._normalize_preanalysis(value)
        return self.save_preanalysis(scene_id, normalized, user_edited=False)

    def save_preanalysis(
        self,
        scene_id: int,
        value: dict[str, Any],
        *,
        user_edited: bool = True,
    ) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        normalized = self._normalize_preanalysis(value)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO scene_preanalyses (
                    scene_id, summary, characters_json, location, time_text,
                    scene_type, basic_events_json, status, user_edited, confirmed_at,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET
                    summary = excluded.summary,
                    characters_json = excluded.characters_json,
                    location = excluded.location,
                    time_text = excluded.time_text,
                    scene_type = excluded.scene_type,
                    basic_events_json = excluded.basic_events_json,
                    status = 'draft',
                    user_edited = excluded.user_edited,
                    confirmed_at = NULL,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scene_id,
                    normalized["summary"],
                    json.dumps(normalized["characters"], ensure_ascii=False),
                    normalized["location"],
                    normalized["time"],
                    normalized["scene_type"],
                    json.dumps(normalized["basic_events"], ensure_ascii=False),
                    1 if user_edited else 0,
                ),
            )
        self.update_chapter_state(
            scene.chapter_id, active_scene_id=scene_id, current_stage="preanalysis"
        )
        return self.get_preanalysis(scene_id) or {}

    def confirm_preanalysis(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        if self.get_preanalysis(scene_id) is None:
            raise ValueError("Run scene preanalysis before confirming it.")
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE scene_preanalyses
                SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE scene_id = ?
                """,
                (scene_id,),
            )
        self.update_chapter_state(
            scene.chapter_id, active_scene_id=scene_id, current_stage="direction"
        )
        return self.get_preanalysis(scene_id) or {}

    def get_intent(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM creative_intents WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        if row is None:
            return None
        return {
            "scene_id": int(row["scene_id"]),
            "strategy": str(row["strategy"]),
            "user_instruction": str(row["user_instruction"]),
            "selected_character_ids": self._json_int_list(row["selected_character_ids_json"]),
            "selected_plot_material_ids": self._json_int_list(row["selected_plot_material_ids_json"]),
            "selected_scene_material_ids": self._json_int_list(row["selected_scene_material_ids_json"]),
            "status": str(row["status"]),
            "updated_at": str(row["updated_at"]),
        }

    def save_intent(self, scene_id: int, value: dict[str, Any]) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        strategy = str(value.get("strategy") or "")
        if strategy not in {"faithful", "plot_adjust", "expansion", "reimagine"}:
            raise ValueError(f"Unsupported creative strategy: {strategy}")
        selected_character_ids = self._normalize_ids(value.get("selected_character_ids"))
        selected_plot_material_ids = self._normalize_ids(value.get("selected_plot_material_ids"))
        selected_scene_material_ids = self._normalize_ids(value.get("selected_scene_material_ids"))
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO creative_intents (
                    scene_id, strategy, user_instruction,
                    selected_character_ids_json, selected_plot_material_ids_json,
                    selected_scene_material_ids_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET
                    strategy = excluded.strategy,
                    user_instruction = excluded.user_instruction,
                    selected_character_ids_json = excluded.selected_character_ids_json,
                    selected_plot_material_ids_json = excluded.selected_plot_material_ids_json,
                    selected_scene_material_ids_json = excluded.selected_scene_material_ids_json,
                    status = 'draft', updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scene_id,
                    strategy,
                    str(value.get("user_instruction") or ""),
                    json.dumps(selected_character_ids),
                    json.dumps(selected_plot_material_ids),
                    json.dumps(selected_scene_material_ids),
                ),
            )
        self.update_chapter_state(scene.chapter_id, active_scene_id=scene_id, current_stage="direction")
        return self.get_intent(scene_id) or {}

    @staticmethod
    def _normalize_preanalysis(value: dict[str, Any]) -> dict[str, Any]:
        def strings(key: str) -> list[str]:
            raw = value.get(key)
            if not isinstance(raw, list):
                return []
            return [str(item).strip() for item in raw if str(item).strip()]

        return {
            "summary": str(value.get("summary") or "").strip(),
            "characters": strings("characters"),
            "location": str(value.get("location") or "").strip(),
            "time": str(value.get("time") or value.get("time_text") or "").strip(),
            "scene_type": str(value.get("scene_type") or "").strip(),
            "basic_events": strings("basic_events"),
        }

    @staticmethod
    def _normalize_ids(value: Any) -> list[int]:
        return sorted({int(item) for item in value}) if isinstance(value, list) else []

    @staticmethod
    def _json_int_list(value: Any) -> list[int]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        return CreativeWorkflowService._normalize_ids(parsed)

    @staticmethod
    def _preanalysis_from_row(row: Any) -> dict[str, Any]:
        def string_list(column: str) -> list[str]:
            try:
                value = json.loads(str(row[column] or "[]"))
            except (TypeError, ValueError):
                return []
            return [str(item) for item in value] if isinstance(value, list) else []

        return {
            "scene_id": int(row["scene_id"]),
            "summary": str(row["summary"]),
            "characters": string_list("characters_json"),
            "location": str(row["location"]),
            "time": str(row["time_text"]),
            "scene_type": str(row["scene_type"]),
            "basic_events": string_list("basic_events_json"),
            "status": str(row["status"]),
            "user_edited": bool(row["user_edited"]),
            "confirmed_at": row["confirmed_at"],
            "updated_at": str(row["updated_at"]),
        }
