from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, initialize_database, session
from rusty.services.scene_service import SceneService
from rusty.services.workflow_ai import WorkflowAI
from rusty.services.anchor_service import AnchorService


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

CHARACTER_ANALYSIS_CATEGORIES = (
    "explicit_mentions", "implicit_references", "actions", "dialogue", "states",
    "objects", "spatial_relations", "related_events", "target_character_conflicts",
)


class CreativeWorkflowService:
    """Persistence boundary for the chapter-centric creative workflow."""

    def __init__(self, database_path: str | Path | None = None, *, ai_client: Any | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)
        self.scenes = SceneService(self.database_path)
        self.characters = AnchorService(self.database_path)
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
            if self._table_exists(connection, "character_modification_analyses"):
                connection.execute(
                    """
                    UPDATE character_modification_analyses
                    SET status = 'stale', confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE scene_id = ?
                    """,
                    (scene_id,),
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
            if self._table_exists(connection, "character_modification_analyses"):
                connection.execute(
                    """
                    UPDATE character_modification_analyses
                    SET status = 'stale', confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE scene_id = ?
                    """,
                    (scene_id,),
                )
        self.update_chapter_state(scene.chapter_id, active_scene_id=scene_id, current_stage="direction")
        return self.get_intent(scene_id) or {}

    def get_character_modification_analysis(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM character_modification_analyses WHERE scene_id = ?", (scene_id,)
            ).fetchone()
        if row is None:
            return None
        result: dict[str, Any] = {
            "scene_id": int(row["scene_id"]),
            "source_character": str(row["source_character"]),
            "target_character_card_id": int(row["target_character_card_id"]),
            "target_character_name": str(row["target_character_name"]),
            "status": str(row["status"]),
            "user_edited": bool(row["user_edited"]),
            "confirmed_at": row["confirmed_at"],
            "updated_at": str(row["updated_at"]),
        }
        for category in CHARACTER_ANALYSIS_CATEGORIES:
            result[category] = self._json_items(row[f"{category}_json"])
        return result

    def run_character_modification_analysis(
        self,
        scene_id: int,
        *,
        source_character: str,
        target_character_card_id: int,
        replace_existing: bool = False,
    ) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        preanalysis = self.get_preanalysis(scene_id)
        if not preanalysis or preanalysis["status"] != "confirmed":
            raise ValueError("Confirm scene preanalysis before specialized analysis.")
        intent = self.get_intent(scene_id)
        if not intent or intent["strategy"] != "faithful":
            raise ValueError("Character modification analysis requires the faithful strategy.")
        target = self.characters.get_character_card(target_character_card_id)
        if target is None:
            raise FileNotFoundError(f"Character card not found: {target_character_card_id}")
        current = self.get_character_modification_analysis(scene_id)
        if current and current["user_edited"] and not replace_existing:
            raise ValueError("Reanalysis would replace the user-edited character analysis.")
        value = self.ai.generate_json(
            project_id=scene.project_id,
            stage="character_modification_analysis",
            workflow_key="faithful",
            task_key="character_modification_analysis",
            user_instruction=intent["user_instruction"],
            payload={
                "source_text": scene.original_text,
                "scene_source_range": {
                    "start_offset": scene.original_start_offset,
                    "end_offset": scene.original_end_offset,
                },
                "preanalysis": preanalysis,
                "creative_intent": intent,
                "source_character": source_character.strip(),
                "target_character": {
                    "id": target.id,
                    "name": target.name,
                    "description": target.description,
                    "setting_text": target.setting_text,
                    "personality": target.personality,
                    "action_constraints": target.action_constraints,
                    "profile": target.profile,
                    "custom_fields": target.custom_fields,
                },
            },
            output_contract=(
                "Return arrays explicit_mentions, implicit_references, actions, dialogue, states, "
                "objects, spatial_relations, related_events, target_character_conflicts. Each item "
                "must contain id, summary, source_text, start_offset, end_offset, inferred. Offsets "
                "are relative to the supplied scene. Conflict items may also contain source_state, "
                "target_state, and difference. Do not propose the replacement action."
            ),
        )
        normalized = self._normalize_character_analysis(scene, value)
        normalized.update({
            "source_character": source_character.strip(),
            "target_character_card_id": target.id,
            "target_character_name": target.name,
        })
        return self.save_character_modification_analysis(scene_id, normalized, user_edited=False)

    def save_character_modification_analysis(
        self,
        scene_id: int,
        value: dict[str, Any],
        *,
        user_edited: bool = True,
    ) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        target_id = int(value.get("target_character_card_id") or 0)
        target = self.characters.get_character_card(target_id)
        if target is None:
            raise FileNotFoundError(f"Character card not found: {target_id}")
        normalized = self._normalize_character_analysis(scene, value)
        columns = ", ".join(f"{category}_json" for category in CHARACTER_ANALYSIS_CATEGORIES)
        placeholders = ", ".join("?" for _ in CHARACTER_ANALYSIS_CATEGORIES)
        updates = ", ".join(f"{category}_json = excluded.{category}_json" for category in CHARACTER_ANALYSIS_CATEGORIES)
        category_values = [json.dumps(normalized[category], ensure_ascii=False) for category in CHARACTER_ANALYSIS_CATEGORIES]
        with session(self.database_path) as connection:
            connection.execute(
                f"""
                INSERT INTO character_modification_analyses (
                    scene_id, source_character, target_character_card_id, target_character_name,
                    {columns}, status, user_edited, confirmed_at, updated_at
                ) VALUES (?, ?, ?, ?, {placeholders}, 'draft', ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET
                    source_character = excluded.source_character,
                    target_character_card_id = excluded.target_character_card_id,
                    target_character_name = excluded.target_character_name,
                    {updates}, status = 'draft', user_edited = excluded.user_edited,
                    confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scene_id, str(value.get("source_character") or "").strip(), target.id,
                    target.name, *category_values, 1 if user_edited else 0,
                ),
            )
        self.update_chapter_state(
            scene.chapter_id, active_scene_id=scene_id, current_stage="special_analysis"
        )
        return self.get_character_modification_analysis(scene_id) or {}

    def confirm_character_modification_analysis(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        if self.get_character_modification_analysis(scene_id) is None:
            raise ValueError("Run character modification analysis before confirming it.")
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE character_modification_analyses
                SET status = 'confirmed', confirmed_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE scene_id = ?
                """,
                (scene_id,),
            )
        self.update_chapter_state(
            scene.chapter_id, active_scene_id=scene_id, current_stage="target_design"
        )
        return self.get_character_modification_analysis(scene_id) or {}

    @staticmethod
    def _normalize_character_analysis(scene: Any, value: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for category in CHARACTER_ANALYSIS_CATEGORIES:
            raw_items = value.get(category)
            normalized: list[dict[str, Any]] = []
            if not isinstance(raw_items, list):
                result[category] = normalized
                continue
            for index, raw in enumerate(raw_items):
                if not isinstance(raw, dict):
                    continue
                source_text = str(raw.get("source_text") or "")
                start = int(raw.get("start_offset") or 0)
                end = int(raw.get("end_offset") or start)
                local_start, local_end = start, end
                if not (0 <= local_start <= local_end <= len(scene.original_text)) or (
                    source_text and scene.original_text[local_start:local_end] != source_text
                ):
                    local_start = start - scene.original_start_offset
                    local_end = end - scene.original_start_offset
                if not (0 <= local_start <= local_end <= len(scene.original_text)) or (
                    source_text and scene.original_text[local_start:local_end] != source_text
                ):
                    local_start = scene.original_text.find(source_text) if source_text else 0
                    if local_start < 0:
                        raise ValueError(f"Analysis evidence is not present in Source: {source_text[:40]}")
                    local_end = local_start + len(source_text)
                item = {
                    "id": str(raw.get("id") or f"{category}-{index + 1}"),
                    "summary": str(raw.get("summary") or ""),
                    "source_text": source_text,
                    "start_offset": scene.original_start_offset + local_start,
                    "end_offset": scene.original_start_offset + local_end,
                    "inferred": bool(raw.get("inferred", False)),
                }
                for key in ("source_state", "target_state", "difference"):
                    if key in raw:
                        item[key] = str(raw.get(key) or "")
                normalized.append(item)
            result[category] = normalized
        return result

    @staticmethod
    def _json_items(value: Any) -> list[dict[str, Any]]:
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError):
            return []
        return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []

    @staticmethod
    def _table_exists(connection: Any, name: str) -> bool:
        return connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone() is not None

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
