from __future__ import annotations

import json
import difflib
from pathlib import Path
from typing import Any

from rusty.db import default_database_path, initialize_database, session
from rusty.services.scene_service import SceneService
from rusty.services.workflow_ai import WorkflowAI
from rusty.services.anchor_service import AnchorService
from rusty.services.material_service import MaterialService


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
        self.materials = MaterialService(self.database_path)
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)

    def list_chapter_states(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            chapter_ids = [
                int(row["id"])
                for row in connection.execute(
                    "SELECT id FROM chapters WHERE project_id = ? ORDER BY chapter_index",
                    (project_id,),
                ).fetchall()
            ]
        for chapter_id in chapter_ids:
            self.reconcile_chapter_scenes(chapter_id)
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
                       state.active_scene_id,
                       COALESCE(scene_state.current_stage, state.current_stage) AS current_stage,
                       state.updated_at
                FROM chapters c
                JOIN chapter_workflow_state state ON state.chapter_id = c.id
                LEFT JOIN scene_workflow_state scene_state
                    ON scene_state.scene_id = state.active_scene_id
                WHERE c.project_id = ?
                ORDER BY c.chapter_index
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_chapter_state(self, chapter_id: int) -> dict[str, Any]:
        self.reconcile_chapter_scenes(chapter_id)
        with session(self.database_path) as connection:
            connection.execute(
                "INSERT OR IGNORE INTO chapter_workflow_state (chapter_id) VALUES (?)",
                (chapter_id,),
            )
            row = connection.execute(
                """
                SELECT c.id AS chapter_id, c.chapter_index, c.title,
                       state.active_scene_id,
                       COALESCE(scene_state.current_stage, state.current_stage) AS current_stage,
                       state.updated_at
                FROM chapters c
                JOIN chapter_workflow_state state ON state.chapter_id = c.id
                LEFT JOIN scene_workflow_state scene_state
                    ON scene_state.scene_id = state.active_scene_id
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
        if active_scene_id is not None:
            scene = self.scenes.get_scene(active_scene_id)
            if scene is None or scene.chapter_id != chapter_id:
                raise ValueError("Active scene must belong to the selected chapter.")
            return self.set_scene_stage(active_scene_id, current_stage, activate=True)
        with session(self.database_path) as connection:
            chapter = connection.execute(
                "SELECT project_id FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            if chapter is None:
                raise FileNotFoundError(f"Chapter not found: {chapter_id}")
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

    def list_scene_states(self, chapter_id: int) -> list[dict[str, Any]]:
        self.reconcile_chapter_scenes(chapter_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT scene.id AS scene_id, scene.scene_index, scene.title,
                       state.current_stage, state.updated_at
                FROM scenes scene
                JOIN scene_workflow_state state ON state.scene_id = scene.id
                WHERE scene.chapter_id = ? AND scene.deleted_at IS NULL
                ORDER BY scene.scene_index
                """,
                (chapter_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_scene_state(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        self.reconcile_chapter_scenes(scene.chapter_id)
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT scene_id, current_stage, updated_at FROM scene_workflow_state WHERE scene_id = ?",
                (scene_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Scene workflow state not found: {scene_id}")
        return dict(row)

    def activate_scene(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        state = self.get_scene_state(scene_id)
        self._sync_chapter_to_scene(scene.chapter_id, scene_id, str(state["current_stage"]))
        return self.get_chapter_state(scene.chapter_id)

    def set_scene_stage(self, scene_id: int, current_stage: str, *, activate: bool = True) -> dict[str, Any]:
        if current_stage not in WORKFLOW_STAGES:
            raise ValueError(f"Unsupported creative workflow stage: {current_stage}")
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO scene_workflow_state (scene_id, current_stage, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET
                    current_stage = excluded.current_stage,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (scene_id, current_stage),
            )
        if activate:
            self._sync_chapter_to_scene(scene.chapter_id, scene_id, current_stage)
        return self.get_scene_state(scene_id)

    def reconcile_chapter_scenes(self, chapter_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            chapter = connection.execute(
                "SELECT id FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            if chapter is None:
                raise FileNotFoundError(f"Chapter not found: {chapter_id}")
            connection.execute(
                """
                INSERT OR IGNORE INTO scene_workflow_state (scene_id)
                SELECT id FROM scenes WHERE chapter_id = ? AND deleted_at IS NULL
                """,
                (chapter_id,),
            )
            live = connection.execute(
                "SELECT id FROM scenes WHERE chapter_id = ? AND deleted_at IS NULL ORDER BY scene_index",
                (chapter_id,),
            ).fetchall()
            live_ids = [int(row["id"]) for row in live]
            current = connection.execute(
                "SELECT active_scene_id FROM chapter_workflow_state WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()
            active_scene_id = (
                int(current["active_scene_id"])
                if current is not None and current["active_scene_id"] is not None
                else None
            )
            if active_scene_id not in live_ids:
                active_scene_id = live_ids[0] if live_ids else None
            stage = "not_started"
            if active_scene_id is not None:
                stage_row = connection.execute(
                    "SELECT current_stage FROM scene_workflow_state WHERE scene_id = ?",
                    (active_scene_id,),
                ).fetchone()
                stage = str(stage_row["current_stage"]) if stage_row is not None else "not_started"
            connection.execute(
                """
                INSERT INTO chapter_workflow_state (chapter_id, active_scene_id, current_stage, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    active_scene_id = excluded.active_scene_id,
                    current_stage = excluded.current_stage,
                    updated_at = CASE
                        WHEN chapter_workflow_state.active_scene_id IS excluded.active_scene_id
                         AND chapter_workflow_state.current_stage = excluded.current_stage
                        THEN chapter_workflow_state.updated_at
                        ELSE CURRENT_TIMESTAMP
                    END
                """,
                (chapter_id, active_scene_id, stage),
            )
        return {"chapter_id": chapter_id, "active_scene_id": active_scene_id, "current_stage": stage}

    def _sync_chapter_to_scene(self, chapter_id: int, scene_id: int, current_stage: str) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO chapter_workflow_state (chapter_id, active_scene_id, current_stage, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    active_scene_id = excluded.active_scene_id,
                    current_stage = excluded.current_stage,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chapter_id, scene_id, current_stage),
            )

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
        if not scene.user_confirmed:
            raise ValueError("Confirm scene boundaries before running scene preanalysis.")
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
            self._mark_strategy_analysis_stale(connection, scene_id)
        self.set_scene_stage(scene_id, "preanalysis")
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
        self.set_scene_stage(scene_id, "direction")
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
        normalized = {
            "strategy": strategy,
            "user_instruction": str(value.get("user_instruction") or ""),
            "selected_character_ids": selected_character_ids,
            "selected_plot_material_ids": selected_plot_material_ids,
            "selected_scene_material_ids": selected_scene_material_ids,
        }
        existing = self.get_intent(scene_id)
        if existing is not None and all(existing[key] == normalized[key] for key in normalized):
            return existing
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
                    normalized["user_instruction"],
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
            self._mark_strategy_analysis_stale(connection, scene_id)
        self.set_scene_stage(scene_id, "direction")
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

    def get_strategy_analysis(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM strategy_scene_analyses WHERE scene_id=?", (scene_id,)).fetchone()
        if row is None:
            return None
        return {"id": int(row["id"]), "scene_id": int(row["scene_id"]), "strategy": str(row["strategy"]),
                "analysis": self._json_object(row["analysis_json"]), "status": str(row["status"]),
                "user_edited": bool(row["user_edited"]), "confirmed_at": row["confirmed_at"],
                "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])}

    def run_strategy_analysis(self, scene_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        scene, intent, preanalysis = self.scenes.get_scene(scene_id), self.get_intent(scene_id), self.get_preanalysis(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        if not preanalysis or preanalysis["status"] != "confirmed":
            raise ValueError("Confirm scene preanalysis before specialized analysis.")
        if not intent or intent["strategy"] not in {"plot_adjust", "expansion", "reimagine"}:
            raise ValueError("Current strategy does not use generic specialized analysis.")
        current = self.get_strategy_analysis(scene_id)
        if current and current["user_edited"] and not replace_existing:
            raise ValueError("Reanalysis would replace the user-edited specialized analysis.")
        contracts = {
            "plot_adjust": "Return source_events, causal_links, participants, preconditions, downstream_dependencies, affected_events as arrays. Analyze Source only; do not propose changes.",
            "expansion": "Return entry_state, exit_constraints, character_relations, active_events, unresolved_goals, available_hooks. Analyze the bridge only.",
            "reimagine": "Return initial_state, required_characters, location, time, inherited_facts, required_end_state, downstream_constraints. Analyze boundary conditions only.",
        }
        value = self.ai.generate_json(project_id=scene.project_id, stage="special_analysis", workflow_key=intent["strategy"], task_key="special_analysis",
                                      user_instruction=intent["user_instruction"], payload={"source_text": scene.original_text, "preanalysis": preanalysis,
                                      "creative_intent": intent}, output_contract=contracts[intent["strategy"]])
        return self.save_strategy_analysis(scene_id, {"strategy": intent["strategy"], "analysis": value}, user_edited=False)

    def save_strategy_analysis(self, scene_id: int, value: dict[str, Any], *, user_edited: bool = True) -> dict[str, Any]:
        intent = self.get_intent(scene_id)
        strategy = str(value.get("strategy") or (intent or {}).get("strategy") or "")
        if strategy not in {"plot_adjust", "expansion", "reimagine"}:
            raise ValueError("Unsupported strategy analysis.")
        analysis = value.get("analysis") if isinstance(value.get("analysis"), dict) else {}
        current = self.get_strategy_analysis(scene_id)
        status = "stale" if user_edited and current and current["status"] == "stale" else "draft"
        with session(self.database_path) as connection:
            connection.execute("""INSERT INTO strategy_scene_analyses(scene_id,strategy,analysis_json,status,user_edited,confirmed_at,updated_at)
                VALUES(?,?,?,?,?,NULL,CURRENT_TIMESTAMP) ON CONFLICT(scene_id) DO UPDATE SET strategy=excluded.strategy,
                analysis_json=excluded.analysis_json,status=excluded.status,user_edited=excluded.user_edited,confirmed_at=NULL,updated_at=CURRENT_TIMESTAMP""",
                (scene_id, strategy, json.dumps(analysis, ensure_ascii=False), status, 1 if user_edited else 0))
            self._mark_target_stale(connection, scene_id)
        self.set_scene_stage(scene_id, "special_analysis")
        return self.get_strategy_analysis(scene_id) or {}

    def confirm_strategy_analysis(self, scene_id: int) -> dict[str, Any]:
        analysis, intent = self.get_strategy_analysis(scene_id), self.get_intent(scene_id)
        if analysis is None:
            raise ValueError("Run specialized analysis before confirming it.")
        if analysis["status"] == "stale":
            raise ValueError("Re-run stale specialized analysis before confirming it.")
        if not intent or intent["strategy"] != analysis["strategy"]:
            raise ValueError("Analysis no longer matches current strategy.")
        with session(self.database_path) as connection:
            connection.execute("UPDATE strategy_scene_analyses SET status='confirmed',confirmed_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))
        self.set_scene_stage(scene_id, "target_design")
        return self.get_strategy_analysis(scene_id) or {}

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
        current = self.get_character_modification_analysis(scene_id)
        saved_status = "stale" if user_edited and current and current["status"] == "stale" else "draft"
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
                ) VALUES (?, ?, ?, ?, {placeholders}, ?, ?, NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET
                    source_character = excluded.source_character,
                    target_character_card_id = excluded.target_character_card_id,
                    target_character_name = excluded.target_character_name,
                    {updates}, status = excluded.status, user_edited = excluded.user_edited,
                    confirmed_at = NULL, updated_at = CURRENT_TIMESTAMP
                """,
                (
                    scene_id, str(value.get("source_character") or "").strip(), target.id,
                    target.name, *category_values, saved_status, 1 if user_edited else 0,
                ),
            )
            self._mark_target_stale(connection, scene_id)
        self.set_scene_stage(scene_id, "special_analysis")
        return self.get_character_modification_analysis(scene_id) or {}

    def get_target(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM scene_targets WHERE scene_id = ?", (scene_id,)).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]), "scene_id": int(row["scene_id"]),
            "strategy": str(row["strategy"]), "user_instruction": str(row["user_instruction"]),
            "design": self._json_object(row["design_json"]), "status": str(row["status"]),
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
            "confirmed_at": row["confirmed_at"],
        }

    def run_target_design(self, scene_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        intent = self.get_intent(scene_id)
        if intent is None:
            raise ValueError("Choose a creative direction before target design.")
        existing = self.get_target(scene_id)
        if existing and existing["status"] == "draft" and not replace_existing:
            raise ValueError("Regenerating would replace the current target draft.")
        analysis = self.get_character_modification_analysis(scene_id) if intent["strategy"] == "faithful" else self.get_strategy_analysis(scene_id)
        if not analysis or analysis["status"] != "confirmed":
            raise ValueError("Confirm the current specialized analysis before target design.")
        target_character = None
        if intent["strategy"] == "faithful":
            card = self.characters.get_character_card(int(analysis["target_character_card_id"]))
            if card:
                target_character = {
                    "id": card.id, "name": card.name, "description": card.description,
                    "setting_text": card.setting_text, "personality": card.personality,
                    "action_constraints": card.action_constraints, "profile": card.profile,
                    "custom_fields": card.custom_fields,
                }
        resources = []
        for material_id in [*intent["selected_plot_material_ids"], *intent["selected_scene_material_ids"]]:
            material = self.materials.get_material(material_id)
            if material:
                resources.append({"id": material.id, "type": material.material_type, "name": material.name,
                                  "content": self._json_object(material.content_json)})
        value = self.ai.generate_json(
            project_id=scene.project_id, stage="target_design", workflow_key=intent["strategy"],
            task_key="target_design", user_instruction=intent["user_instruction"],
            payload={"source_text": scene.original_text, "confirmed_special_analysis": analysis,
                     "creative_intent": intent, "target_character": target_character,
                     "selected_resources": resources},
            output_contract=self._target_output_contract(intent["strategy"]),
        )
        return self.save_target(scene_id, {"strategy": intent["strategy"], "user_instruction": intent["user_instruction"], "design": value})

    def save_target(self, scene_id: int, value: dict[str, Any]) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        intent = self.get_intent(scene_id)
        strategy = str(value.get("strategy") or (intent or {}).get("strategy") or "")
        if strategy not in {"faithful", "plot_adjust", "expansion", "reimagine"}:
            raise ValueError(f"Unsupported target strategy: {strategy}")
        design = self._normalize_target_design(strategy, value.get("design"))
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO scene_targets (scene_id, strategy, user_instruction, design_json, status, confirmed_at, updated_at)
                VALUES (?, ?, ?, ?, 'draft', NULL, CURRENT_TIMESTAMP)
                ON CONFLICT(scene_id) DO UPDATE SET strategy=excluded.strategy,
                    user_instruction=excluded.user_instruction, design_json=excluded.design_json,
                    status='draft', confirmed_at=NULL, updated_at=CURRENT_TIMESTAMP
                """,
                (scene_id, strategy, str(value.get("user_instruction") or (intent or {}).get("user_instruction") or ""),
                 json.dumps(design, ensure_ascii=False)),
            )
            if self._table_exists(connection, "writing_plans"):
                connection.execute("UPDATE writing_plans SET status='stale', updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))
        self.set_scene_stage(scene_id, "target_design")
        return self.get_target(scene_id) or {}

    def confirm_target(self, scene_id: int) -> dict[str, Any]:
        target = self.get_target(scene_id)
        if target is None:
            raise ValueError("Generate or create a target before confirming it.")
        if target["status"] == "stale":
            raise ValueError("Regenerate the stale target before confirming it.")
        with session(self.database_path) as connection:
            connection.execute("UPDATE scene_targets SET status='confirmed', confirmed_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))
        self.set_scene_stage(scene_id, "writing")
        return self.get_target(scene_id) or {}

    def get_writing_plan(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM writing_plans WHERE scene_id=?", (scene_id,)).fetchone()
            if row is None:
                return None
            blocks = connection.execute("SELECT * FROM writing_plan_blocks WHERE plan_id=? ORDER BY block_order", (row["id"],)).fetchall()
        return {
            "id": int(row["id"]), "scene_id": int(row["scene_id"]), "target_id": int(row["target_id"]),
            "strategy": str(row["strategy"]), "status": str(row["status"]),
            "coverage": self._json_object(row["coverage_json"]),
            "blocks": [self._block_from_row(block) for block in blocks],
            "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"]),
        }

    def run_writing_plan(self, scene_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        target = self.get_target(scene_id)
        if not target or target["status"] != "confirmed":
            raise ValueError("Confirm the current target before writing planning.")
        current = self.get_writing_plan(scene_id)
        if current and current["status"] != "stale" and not replace_existing:
            raise ValueError("Replanning would replace the current writing plan.")
        value = self.ai.generate_json(
            project_id=scene.project_id, stage="writing_plan", workflow_key=target["strategy"], task_key="writing_plan",
            user_instruction=target["user_instruction"],
            payload={"source_text": scene.original_text, "scene_source_range": {"start_offset": scene.original_start_offset, "end_offset": scene.original_end_offset},
                     "target": target, "special_analysis": self.get_character_modification_analysis(scene_id) if target["strategy"] == "faithful" else self.get_strategy_analysis(scene_id)},
            output_contract=("Return {blocks:[{title,source_start_offset,source_end_offset,source_text_snapshot,operation,instruction,preserve_constraints,target_requirements,resource_refs}]}. "
                             "Use semantic blocks and cover Source in order. Operations: preserve, transform, rewrite, insert, delete."),
        )
        return self.save_writing_plan(scene_id, {"target_id": target["id"], "strategy": target["strategy"], "blocks": value.get("blocks", [])})

    def save_writing_plan(self, scene_id: int, value: dict[str, Any]) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        target = self.get_target(scene_id)
        if target is None:
            raise ValueError("Writing plan requires a scene target.")
        target_id = int(value.get("target_id") or target["id"])
        blocks = self._normalize_writing_blocks(scene, value.get("blocks"))
        coverage = self._coverage(blocks)
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO writing_plans(scene_id,target_id,strategy,status,coverage_json,updated_at)
                   VALUES(?,?,?,'ready',?,CURRENT_TIMESTAMP)
                   ON CONFLICT(scene_id) DO UPDATE SET target_id=excluded.target_id,strategy=excluded.strategy,
                     status='ready',coverage_json=excluded.coverage_json,updated_at=CURRENT_TIMESTAMP""",
                (scene_id, target_id, str(value.get("strategy") or target["strategy"]), json.dumps(coverage)),
            )
            plan_id = int(connection.execute("SELECT id FROM writing_plans WHERE scene_id=?", (scene_id,)).fetchone()["id"])
            connection.execute("DELETE FROM writing_plan_blocks WHERE plan_id=?", (plan_id,))
            for order, block in enumerate(blocks, 1):
                connection.execute(
                    """INSERT INTO writing_plan_blocks(plan_id,scene_id,block_order,title,source_start_offset,source_end_offset,
                       source_text_snapshot,operation,instruction,preserve_constraints_json,target_requirements_json,resource_refs_json)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (plan_id, scene_id, order, block["title"], block["source_start_offset"], block["source_end_offset"],
                     block["source_text_snapshot"], block["operation"], block["instruction"],
                     json.dumps(block["preserve_constraints"], ensure_ascii=False), json.dumps(block["target_requirements"], ensure_ascii=False),
                     json.dumps(block["resource_refs"], ensure_ascii=False)),
                )
        self.set_scene_stage(scene_id, "writing")
        return self.get_writing_plan(scene_id) or {}

    def get_current_draft(self, scene_id: int) -> dict[str, Any] | None:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM scene_current_drafts WHERE scene_id=?", (scene_id,)).fetchone()
        if row is None:
            return None
        return {"scene_id": int(row["scene_id"]), "text": str(row["text"]),
                "based_on_target_id": int(row["based_on_target_id"]), "based_on_plan_id": int(row["based_on_plan_id"]),
                "block_spans": self._json_items(row["block_spans_json"]), "status": str(row["status"]),
                "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])}

    def generate_current_draft(self, scene_id: int, *, replace_existing: bool = False) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        plan = self.get_writing_plan(scene_id)
        target = self.get_target(scene_id)
        if scene is None or plan is None or target is None:
            raise ValueError("Current draft generation requires Source, Target, and Writing Plan.")
        if plan["status"] != "ready" or plan["target_id"] != target["id"] or target["status"] != "confirmed":
            raise ValueError("Replan against the confirmed current target before generating.")
        if self.get_current_draft(scene_id) is not None and not replace_existing:
            raise ValueError("Generating again would replace the current draft.")
        if target["strategy"] == "reimagine" and float(plan["coverage"].get("preserve", 0)) < 10:
            intent = self.get_intent(scene_id) or {}
            character_cards = []
            for card_id in intent.get("selected_character_ids", []):
                card = self.characters.get_character_card(card_id)
                if card:
                    character_cards.append({"id": card.id, "name": card.name, "setting_text": card.setting_text,
                                            "personality": card.personality, "action_constraints": card.action_constraints})
            value = self.ai.generate_json(
                project_id=scene.project_id, stage="full_scene_generation", workflow_key="reimagine", task_key="full_scene_generation",
                user_instruction=target["user_instruction"],
                payload={"source_reference": scene.original_text, "boundary_conditions": target["design"].get("boundary_conditions", {}),
                         "target_skeleton": target["design"].get("nodes", []), "writing_plan": plan,
                         "character_cards": character_cards, "preanalysis": self.get_preanalysis(scene_id)},
                output_contract="Return {text:string}. text is the complete new scene only.",
            )
            text = str(value.get("text") or "")
            return self.save_current_draft(scene_id, {"text": text, "based_on_target_id": target["id"],
                                                      "based_on_plan_id": plan["id"],
                                                      "block_spans": [{"block_id": plan["blocks"][0]["id"] if plan["blocks"] else 0,
                                                                       "start_offset": 0, "end_offset": len(text)}]})
        assembled = ""
        spans: list[dict[str, Any]] = []
        blocks = plan["blocks"]
        for index, block in enumerate(blocks):
            operation = block["operation"]
            source_block = block["source_text_snapshot"]
            if operation == "preserve":
                generated = source_block
            elif operation == "delete":
                generated = ""
            else:
                next_source = blocks[index + 1]["source_text_snapshot"][:500] if index + 1 < len(blocks) else ""
                generated = self._generate_block_text(scene, target, plan, block, assembled[-800:], next_source)
            start = len(assembled)
            assembled += generated
            spans.append({"block_id": block["id"], "start_offset": start, "end_offset": len(assembled)})
        return self.save_current_draft(scene_id, {"text": assembled, "based_on_target_id": target["id"], "based_on_plan_id": plan["id"], "block_spans": spans})

    def save_current_draft(self, scene_id: int, value: dict[str, Any]) -> dict[str, Any]:
        current = self.get_current_draft(scene_id)
        target = self.get_target(scene_id)
        plan = self.get_writing_plan(scene_id)
        if target is None or plan is None:
            raise ValueError("Current draft requires Target and Writing Plan.")
        with session(self.database_path) as connection:
            connection.execute(
                """INSERT INTO scene_current_drafts(scene_id,text,based_on_target_id,based_on_plan_id,block_spans_json,status,updated_at)
                   VALUES(?,?,?,?,?,'draft',CURRENT_TIMESTAMP)
                   ON CONFLICT(scene_id) DO UPDATE SET text=excluded.text,based_on_target_id=excluded.based_on_target_id,
                     based_on_plan_id=excluded.based_on_plan_id,block_spans_json=excluded.block_spans_json,
                     status='draft',updated_at=CURRENT_TIMESTAMP""",
                (scene_id, str(value.get("text") or ""), int(value.get("based_on_target_id") or (current or {}).get("based_on_target_id") or target["id"]),
                 int(value.get("based_on_plan_id") or (current or {}).get("based_on_plan_id") or plan["id"]),
                 json.dumps(value.get("block_spans") if isinstance(value.get("block_spans"), list) else (current or {}).get("block_spans", []))),
            )
        self.set_scene_stage(scene_id, "writing")
        return self.get_current_draft(scene_id) or {}

    def edit_selected_draft_text(self, scene_id: int, *, start_offset: int, end_offset: int, user_instruction: str) -> dict[str, Any]:
        draft = self.get_current_draft(scene_id)
        target = self.get_target(scene_id)
        scene = self.scenes.get_scene(scene_id)
        if draft is None or target is None or scene is None:
            raise ValueError("Selected text editing requires a current draft and target.")
        if not (0 <= start_offset <= end_offset <= len(draft["text"])):
            raise ValueError("Selected draft range is invalid.")
        value = self.ai.generate_json(
            project_id=scene.project_id, stage="selected_text_edit", task_key="selected_text_edit",
            user_instruction=user_instruction,
            payload={"selected_text": draft["text"][start_offset:end_offset], "previous_context": draft["text"][max(0,start_offset-800):start_offset],
                     "next_context": draft["text"][end_offset:end_offset+800], "target": target},
            output_contract="Return {text:string}. text must contain only the replacement for the selected range.",
        )
        replacement = str(value.get("text") or "")
        updated = draft["text"][:start_offset] + replacement + draft["text"][end_offset:]
        return self.save_current_draft(scene_id, {**draft, "text": updated})

    def regenerate_writing_block(self, scene_id: int, block_id: int, *, current_start_offset: int, current_end_offset: int) -> dict[str, Any]:
        draft = self.get_current_draft(scene_id)
        plan = self.get_writing_plan(scene_id)
        target = self.get_target(scene_id)
        scene = self.scenes.get_scene(scene_id)
        if draft is None or plan is None or target is None or scene is None:
            raise ValueError("Block regeneration requires a current draft, plan, and target.")
        block = next((item for item in plan["blocks"] if item["id"] == block_id), None)
        if block is None or block["operation"] in {"preserve", "delete"}:
            raise ValueError("Only AI-backed writing blocks can be regenerated.")
        if not (0 <= current_start_offset <= current_end_offset <= len(draft["text"])):
            raise ValueError("Current block range is invalid.")
        index = plan["blocks"].index(block)
        next_source = plan["blocks"][index + 1]["source_text_snapshot"][:500] if index + 1 < len(plan["blocks"]) else ""
        replacement = self._generate_block_text(scene, target, plan, block, draft["text"][max(0,current_start_offset-800):current_start_offset], next_source)
        updated = draft["text"][:current_start_offset] + replacement + draft["text"][current_end_offset:]
        return self.save_current_draft(scene_id, {**draft, "text": updated})

    def get_review_diff(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        draft = self.get_current_draft(scene_id)
        if scene is None or draft is None:
            raise ValueError("Review requires Source and Current Draft.")
        source_lines = scene.original_text.splitlines(keepends=True)
        target_lines = draft["text"].splitlines(keepends=True)
        source_offsets = self._line_offsets(source_lines)
        target_offsets = self._line_offsets(target_lines)
        chunks = []
        for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, source_lines, target_lines, autojunk=False).get_opcodes():
            chunks.append({"tag": tag, "source_start_offset": source_offsets[i1], "source_end_offset": source_offsets[i2],
                           "target_start_offset": target_offsets[j1], "target_end_offset": target_offsets[j2],
                           "source_text": "".join(source_lines[i1:i2]), "target_text": "".join(target_lines[j1:j2])})
        return {"scene_id": scene_id, "source_text": scene.original_text, "target_text": draft["text"], "chunks": chunks}

    def start_review(self, scene_id: int) -> dict[str, Any]:
        result = self.get_review_diff(scene_id)
        self.set_scene_stage(scene_id, "review")
        return result

    def list_review_marks(self, scene_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute("SELECT * FROM review_marks WHERE scene_id=? ORDER BY resolved, created_at, id", (scene_id,)).fetchall()
        return [self._review_mark_from_row(row) for row in rows]

    def save_review_mark(self, scene_id: int, value: dict[str, Any]) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        draft = self.get_current_draft(scene_id)
        if scene is None or draft is None:
            raise ValueError("Review mark requires Source and Current Draft.")
        source_start, source_end = int(value.get("source_start_offset") or 0), int(value.get("source_end_offset") or 0)
        if source_start < scene.original_start_offset:
            source_start += scene.original_start_offset; source_end += scene.original_start_offset
        local_start, local_end = source_start - scene.original_start_offset, source_end - scene.original_start_offset
        if not (0 <= local_start <= local_end <= len(scene.original_text)):
            raise ValueError("Review Source range is invalid.")
        target_start, target_end = int(value.get("target_start_offset") or 0), int(value.get("target_end_offset") or 0)
        if not (0 <= target_start <= target_end <= len(draft["text"])):
            raise ValueError("Review target range is invalid.")
        mark_id = int(value.get("id") or 0)
        with session(self.database_path) as connection:
            if mark_id:
                connection.execute("""UPDATE review_marks SET source_start_offset=?,source_end_offset=?,source_text=?,target_start_offset=?,target_end_offset=?,user_note=?,resolved=?,updated_at=CURRENT_TIMESTAMP WHERE id=? AND scene_id=?""",
                                   (source_start, source_end, scene.original_text[local_start:local_end], target_start, target_end, str(value.get("user_note") or ""), 1 if value.get("resolved") else 0, mark_id, scene_id))
            else:
                cursor = connection.execute("""INSERT INTO review_marks(scene_id,source_start_offset,source_end_offset,source_text,target_start_offset,target_end_offset,user_note,resolved) VALUES(?,?,?,?,?,?,?,?)""",
                                            (scene_id, source_start, source_end, scene.original_text[local_start:local_end], target_start, target_end, str(value.get("user_note") or ""), 1 if value.get("resolved") else 0))
                mark_id = int(cursor.lastrowid)
            row = connection.execute("SELECT * FROM review_marks WHERE id=?", (mark_id,)).fetchone()
        return self._review_mark_from_row(row)

    def delete_review_mark(self, scene_id: int, mark_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM review_marks WHERE id=? AND scene_id=?", (mark_id, scene_id))

    def restore_review_source(self, scene_id: int, mark_id: int) -> dict[str, Any]:
        draft = self.get_current_draft(scene_id)
        mark = next((item for item in self.list_review_marks(scene_id) if item["id"] == mark_id), None)
        if draft is None or mark is None:
            raise ValueError("Review mark or Current Draft not found.")
        start, end = mark["target_start_offset"], mark["target_end_offset"]
        updated = draft["text"][:start] + mark["source_text"] + draft["text"][end:]
        saved = self.save_current_draft(scene_id, {**draft, "text": updated})
        self._resolve_mark(mark_id)
        return saved

    def rework_review_range(self, scene_id: int, *, target_start_offset: int, target_end_offset: int,
                            source_start_offset: int | None = None, source_end_offset: int | None = None,
                            user_instruction: str = "", mark_id: int | None = None) -> dict[str, Any]:
        scene, draft, target, plan = self.scenes.get_scene(scene_id), self.get_current_draft(scene_id), self.get_target(scene_id), self.get_writing_plan(scene_id)
        if scene is None or draft is None or target is None or plan is None:
            raise ValueError("Review rework requires Source, Current Draft, Target, and Writing Plan.")
        if not (0 <= target_start_offset <= target_end_offset <= len(draft["text"])):
            raise ValueError("Review target range is invalid.")
        mark = next((item for item in self.list_review_marks(scene_id) if item["id"] == mark_id), None) if mark_id else None
        if mark:
            source_text, note = mark["source_text"], mark["user_note"]
        else:
            raw_start, raw_end = int(source_start_offset or 0), int(source_end_offset or 0)
            local_start = raw_start if raw_start < scene.original_start_offset else raw_start - scene.original_start_offset
            local_end = raw_end if raw_end < scene.original_start_offset else raw_end - scene.original_start_offset
            local_start, local_end = max(0, local_start), max(local_start, local_end)
            source_text, note = scene.original_text[local_start:local_end], ""
        value = self.ai.generate_json(
            project_id=scene.project_id, stage="review_rework", task_key="review_rework", user_instruction=user_instruction or note,
            payload={"source_range_text": source_text, "current_draft_range": draft["text"][target_start_offset:target_end_offset],
                     "previous_context": draft["text"][max(0,target_start_offset-800):target_start_offset],
                     "next_context": draft["text"][target_end_offset:target_end_offset+800], "target": target, "writing_plan": plan,
                     "review_note": note}, output_contract="Return {text:string}. text contains only the selected range replacement.")
        replacement = str(value.get("text") or "")
        before = draft["text"]
        saved = self.save_current_draft(scene_id, {**draft, "text": before[:target_start_offset] + replacement + before[target_end_offset:]})
        if mark_id: self._resolve_mark(mark_id)
        return {"draft": saved, "before_text": before, "after_text": saved["text"],
                "start_offset": target_start_offset, "end_offset": target_start_offset + len(replacement)}

    def rework_all_review_marks(self, scene_id: int) -> dict[str, Any]:
        marks = sorted((item for item in self.list_review_marks(scene_id) if not item["resolved"]), key=lambda item: item["target_start_offset"], reverse=True)
        before = self.get_current_draft(scene_id)
        for mark in marks:
            self.rework_review_range(scene_id, target_start_offset=mark["target_start_offset"], target_end_offset=mark["target_end_offset"], mark_id=mark["id"])
        return {"draft": self.get_current_draft(scene_id), "before_text": before["text"] if before else "", "processed": len(marks)}

    def confirm_scene(self, scene_id: int) -> dict[str, Any]:
        draft = self.get_current_draft(scene_id)
        if draft is None:
            raise ValueError("Confirming a scene requires a Current Draft.")
        with session(self.database_path) as connection:
            connection.execute("UPDATE scene_current_drafts SET status='confirmed',updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))
        self.set_scene_stage(scene_id, "confirmed")
        return {"draft": self.get_current_draft(scene_id), "unresolved_marks": sum(not item["resolved"] for item in self.list_review_marks(scene_id))}

    @staticmethod
    def _line_offsets(lines: list[str]) -> list[int]:
        result, total = [0], 0
        for line in lines: total += len(line); result.append(total)
        return result

    @staticmethod
    def _review_mark_from_row(row: Any) -> dict[str, Any]:
        return {"id": int(row["id"]), "scene_id": int(row["scene_id"]), "source_start_offset": int(row["source_start_offset"]),
                "source_end_offset": int(row["source_end_offset"]), "source_text": str(row["source_text"]),
                "target_start_offset": int(row["target_start_offset"]), "target_end_offset": int(row["target_end_offset"]),
                "user_note": str(row["user_note"]), "resolved": bool(row["resolved"]),
                "created_at": str(row["created_at"]), "updated_at": str(row["updated_at"])}

    def _resolve_mark(self, mark_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute("UPDATE review_marks SET resolved=1,updated_at=CURRENT_TIMESTAMP WHERE id=?", (mark_id,))

    def _generate_block_text(self, scene: Any, target: dict[str, Any], plan: dict[str, Any], block: dict[str, Any], previous_tail: str, next_source: str) -> str:
        operation = str(block["operation"])
        task_key = "insert_block" if operation == "insert" else f"{operation}_block"
        value = self.ai.generate_json(
            project_id=scene.project_id, stage=task_key,
            workflow_key=None if operation == "insert" and target["strategy"] == "faithful" else target["strategy"], task_key=task_key,
            user_instruction=target["user_instruction"],
            payload={"previous_current_draft_tail": previous_tail, "current_source_block": block["source_text_snapshot"],
                     "next_source_block_beginning": next_source, "target": target, "writing_block": block,
                     "preserve_constraints": block["preserve_constraints"], "target_requirements": block["target_requirements"]},
            output_contract="Return {text:string}. text must contain only the current block, never adjacent blocks.",
        )
        return str(value.get("text") or "")

    @staticmethod
    def _block_from_row(row: Any) -> dict[str, Any]:
        return {"id": int(row["id"]), "plan_id": int(row["plan_id"]), "scene_id": int(row["scene_id"]),
                "order": int(row["block_order"]), "title": str(row["title"]),
                "source_start_offset": int(row["source_start_offset"]), "source_end_offset": int(row["source_end_offset"]),
                "source_text_snapshot": str(row["source_text_snapshot"]), "operation": str(row["operation"]),
                "instruction": str(row["instruction"]),
                "preserve_constraints": CreativeWorkflowService._json_string_list(row["preserve_constraints_json"]),
                "target_requirements": CreativeWorkflowService._json_string_list(row["target_requirements_json"]),
                "resource_refs": CreativeWorkflowService._json_int_list(row["resource_refs_json"])}

    @staticmethod
    def _normalize_writing_blocks(scene: Any, value: Any) -> list[dict[str, Any]]:
        raw_blocks = value if isinstance(value, list) else []
        result = []
        for index, raw in enumerate(raw_blocks):
            if not isinstance(raw, dict): continue
            operation = str(raw.get("operation") or "preserve").lower()
            if operation not in {"preserve","transform","rewrite","insert","delete"}:
                raise ValueError(f"Unsupported writing operation: {operation}")
            start, end = int(raw.get("source_start_offset") or 0), int(raw.get("source_end_offset") or 0)
            snapshot = str(raw.get("source_text_snapshot") or "")
            if operation != "insert":
                local_start, local_end = start, end
                if not (0 <= local_start <= local_end <= len(scene.original_text)) or (snapshot and scene.original_text[local_start:local_end] != snapshot):
                    local_start, local_end = start - scene.original_start_offset, end - scene.original_start_offset
                if not (0 <= local_start <= local_end <= len(scene.original_text)) or (snapshot and scene.original_text[local_start:local_end] != snapshot):
                    local_start = scene.original_text.find(snapshot) if snapshot else -1
                    if local_start < 0: raise ValueError("Writing block snapshot is not present in Source.")
                    local_end = local_start + len(snapshot)
                start, end, snapshot = scene.original_start_offset + local_start, scene.original_start_offset + local_end, scene.original_text[local_start:local_end]
            result.append({"title": str(raw.get("title") or f"区块 {index+1}"), "source_start_offset": start,
                           "source_end_offset": end, "source_text_snapshot": snapshot, "operation": operation,
                           "instruction": str(raw.get("instruction") or ""),
                           "preserve_constraints": [str(x) for x in raw.get("preserve_constraints", [])] if isinstance(raw.get("preserve_constraints"), list) else [],
                           "target_requirements": [str(x) for x in raw.get("target_requirements", [])] if isinstance(raw.get("target_requirements"), list) else [],
                           "resource_refs": CreativeWorkflowService._normalize_ids(raw.get("resource_refs"))})
        return result

    @staticmethod
    def _coverage(blocks: list[dict[str, Any]]) -> dict[str, float]:
        sizes = {key: 0 for key in ("preserve","transform","rewrite","insert","delete")}
        for block in blocks: sizes[block["operation"]] += max(0, block["source_end_offset"] - block["source_start_offset"])
        total = sum(sizes.values()) or 1
        return {key: round(value * 100 / total, 1) for key, value in sizes.items()}

    @staticmethod
    def _json_string_list(value: Any) -> list[str]:
        try: parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError): return []
        return [str(item) for item in parsed] if isinstance(parsed, list) else []

    @staticmethod
    def _normalize_target_design(strategy: str, value: Any) -> dict[str, Any]:
        design = value if isinstance(value, dict) else {}
        if strategy != "faithful":
            return design
        items = []
        for index, raw in enumerate(design.get("items") if isinstance(design.get("items"), list) else []):
            if not isinstance(raw, dict):
                continue
            operation = str(raw.get("operation") or "preserve").lower()
            if operation not in {"preserve", "adapt", "modify"}:
                raise ValueError(f"Unsupported faithful target operation: {operation}")
            items.append({
                "id": str(raw.get("id") or f"change-{index + 1}"), "label": str(raw.get("label") or ""),
                "operation": operation, "source_value": str(raw.get("source_value") or ""),
                "target_value": str(raw.get("target_value") or ""),
                "source_start_offset": int(raw.get("source_start_offset") or 0),
                "source_end_offset": int(raw.get("source_end_offset") or 0),
            })
        summary = [str(item) for item in design.get("summary", [])] if isinstance(design.get("summary"), list) else []
        return {"items": items, "summary": summary}

    @staticmethod
    def _target_output_contract(strategy: str) -> str:
        if strategy == "faithful":
            return ("Return {items:[{id,label,operation,source_value,target_value,source_start_offset,source_end_offset}], summary:string[]}. "
                    "operation must be preserve, adapt, or modify. Do not write prose.")
        if strategy == "plot_adjust":
            return ("Return {nodes:[{id,order,summary,participants,outcome,source_relation}],source_mapping:[{source_event_id,target_node_id|null}],summary:string[]}. "
                    "source_relation must be inherited, modified, or inserted. Do not write prose.")
        if strategy == "expansion":
            return "Return {insert_after,insert_before,entry_state,new_events:[{id,order,summary}],exit_constraints:string[],summary:string[]}. Do not copy the full Source skeleton."
        return "Return {boundary_conditions:{initial_state,required_characters,location,time,inherited_facts,required_end_state,downstream_constraints},nodes:[{id,order,summary,participants,outcome,source_relation}],summary:string[]}."

    @staticmethod
    def _json_object(value: Any) -> dict[str, Any]:
        try:
            parsed = json.loads(str(value or "{}"))
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _mark_target_stale(connection: Any, scene_id: int) -> None:
        if CreativeWorkflowService._table_exists(connection, "scene_targets"):
            connection.execute("UPDATE scene_targets SET status='stale', confirmed_at=NULL, updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))

    @staticmethod
    def _mark_strategy_analysis_stale(connection: Any, scene_id: int) -> None:
        if CreativeWorkflowService._table_exists(connection, "strategy_scene_analyses"):
            connection.execute("UPDATE strategy_scene_analyses SET status='stale',confirmed_at=NULL,updated_at=CURRENT_TIMESTAMP WHERE scene_id=?", (scene_id,))

    def confirm_character_modification_analysis(self, scene_id: int) -> dict[str, Any]:
        scene = self.scenes.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        analysis = self.get_character_modification_analysis(scene_id)
        if analysis is None:
            raise ValueError("Run character modification analysis before confirming it.")
        if analysis["status"] == "stale":
            raise ValueError("Re-run stale character modification analysis before confirming it.")
        preanalysis = self.get_preanalysis(scene_id)
        if not preanalysis or preanalysis["status"] != "confirmed":
            raise ValueError("Character analysis cannot be confirmed after preanalysis changed.")
        intent = self.get_intent(scene_id)
        if not intent or intent["strategy"] != "faithful":
            raise ValueError("Character analysis confirmation requires the current faithful intent.")
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
        self.set_scene_stage(scene_id, "target_design")
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
