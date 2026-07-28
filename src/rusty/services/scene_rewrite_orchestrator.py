from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.context_service import ContextService
from rusty.services.material_service import MaterialService
from rusty.services.project_service import default_database_path
from rusty.services.prompt_compiler import PromptCompiler
from rusty.services.rewrite_workflow_service import (
    CONSISTENCY_KEYS,
    SCENE_ANALYSIS_KEYS,
    RewriteWorkflowService,
)
from rusty.services.scene_service import SceneService
from rusty.services.structured_model_service import StructuredModelResult, StructuredModelService


class SceneRewriteOrchestrator:
    """Run the real scene-level model workflow around explicit user confirmation gates."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.scene_service = SceneService(self.database_path)
        self.context_service = ContextService(self.database_path)
        self.workflow = RewriteWorkflowService(self.database_path)
        self.material_service = MaterialService(self.database_path)
        self.prompt_compiler = PromptCompiler()
        self.model_service = structured_model_service or StructuredModelService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def start(
        self,
        scene_id: int,
        *,
        mode: str,
        user_instruction: str = "",
        model_id: int | None = None,
        character_ids: list[int] | None = None,
        material_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        if mode not in {"skeleton_rewrite", "expansion"}:
            raise ValueError(f"Unsupported rewrite mode: {mode}")
        scene = self._require_scene(scene_id)
        if not scene.user_confirmed:
            raise ValueError("Scene boundaries must be confirmed before analysis.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO scene_workflow_runs (
                    project_id, chapter_id, scene_id, mode, status, current_stage
                ) VALUES (?, ?, ?, ?, 'analyzing', 'analysis')
                """,
                (scene.project_id, scene.chapter_id, scene.id, mode),
            )
            run_id = int(cursor.lastrowid)
        try:
            analysis = self._call_stage(
                scene_id,
                stage="analysis",
                system_rules=(
                    "Analyze the complete current scene. Preserve source facts and distinguish "
                    "stable character cards from dynamic story state."
                ),
                user_instruction=user_instruction,
                task={"mode": mode},
                output_protocol=_schema_text("scene_analysis", sorted(SCENE_ANALYSIS_KEYS)),
                validator=_validate_analysis,
                model_id=model_id,
                character_ids=character_ids or [],
                material_ids=material_ids or [],
            )
            self.workflow.save_stage_output(
                scene_id,
                "analysis",
                analysis.value,
                prompt_compilation_id=_prompt_compilation_id(analysis),
            )
            skeleton_result = self._call_stage(
                scene_id,
                stage="skeleton",
                system_rules=(
                    "Extract an editable causal plot skeleton from the complete current scene. "
                    "Every node must be supported by the original text."
                ),
                user_instruction=user_instruction,
                task={"analysis": analysis.value, "mode": mode},
                output_protocol=_schema_text("story_skeleton", ["event_nodes"]),
                validator=_validate_skeleton,
                model_id=model_id,
                character_ids=character_ids or [],
                material_ids=material_ids or [],
            )
            skeleton = self.workflow.create_skeleton(
                project_id=scene.project_id,
                chapter_id=scene.chapter_id,
                scene_id=scene.id,
                nodes=skeleton_result.value["event_nodes"],
            )
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE scene_workflow_runs
                    SET status = 'awaiting_skeleton', current_stage = 'skeleton_confirmation',
                        skeleton_id = ?, skeleton_version_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (skeleton.skeleton_id, skeleton.version_id, run_id),
                )
            return self.get_run(run_id)
        except Exception as exc:
            self._fail_run(run_id, exc)
            raise

    def generate_plan(
        self,
        run_id: int,
        *,
        skeleton_version_id: int,
        user_instruction: str = "",
        model_id: int | None = None,
        character_ids: list[int] | None = None,
        material_mappings: list[dict[str, Any]] | None = None,
        scene_reference_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        self._require_confirmed_skeleton(skeleton_version_id)
        mappings = material_mappings or []
        if run["mode"] == "expansion" and not mappings:
            raise ValueError("Expansion mode requires at least one plot skeleton insertion.")
        for mapping in mappings:
            material = self.material_service.get_material(int(mapping["material_id"]))
            if material is None:
                raise FileNotFoundError(f"Material not found: {mapping['material_id']}")
            if material.material_type != "plot_skeleton":
                raise ValueError("Only plot_skeleton materials can create expansion events.")
            if not mapping.get("event_nodes"):
                content = _object(material.content_json)
                mapping["event_nodes"] = content.get("event_nodes", [])
        reference_ids = list(scene_reference_ids or [])
        for material_id in reference_ids:
            material = self.material_service.get_material(material_id)
            if material is None or material.material_type != "scene_reference":
                raise ValueError("Scene writing references must use scene_reference materials.")
        skeleton_nodes = self._skeleton_nodes(skeleton_version_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE scene_workflow_runs
                SET status = 'planning', current_stage = 'planning',
                    skeleton_version_id = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (skeleton_version_id, run_id),
            )
        try:
            plan_result = self._call_stage(
                int(run["scene_id"]),
                stage="planning",
                system_rules=(
                    "Create a scene rewrite plan. Scene references guide local writing only. "
                    "Only plot skeleton mappings may add events. Preserve required outcomes."
                ),
                user_instruction=user_instruction,
                task={
                    "mode": run["mode"],
                    "confirmed_skeleton": skeleton_nodes,
                    "material_mappings": mappings,
                },
                output_protocol=_schema_text(
                    "rewrite_plan",
                    [
                        "sequence",
                        "preserve",
                        "modify",
                        "add",
                        "material_insertions",
                        "character_changes",
                        "expected_end_state",
                    ],
                ),
                validator=_validate_plan,
                model_id=model_id,
                character_ids=character_ids or [],
                material_ids=[*[int(item["material_id"]) for item in mappings], *reference_ids],
            )
            scene = self._require_scene(int(run["scene_id"]))
            if run["mode"] == "skeleton_rewrite":
                plan_id = self.workflow.create_skeleton_rewrite_plan(
                    project_id=scene.project_id,
                    chapter_id=scene.chapter_id,
                    scene_id=scene.id,
                    skeleton_version_id=skeleton_version_id,
                    plan=plan_result.value,
                )
            else:
                plan_id = self.workflow.create_expansion_plan(
                    project_id=scene.project_id,
                    chapter_id=scene.chapter_id,
                    scene_id=scene.id,
                    skeleton_version_id=skeleton_version_id,
                    plan=plan_result.value,
                    material_mappings=mappings,
                )
            self.workflow.save_stage_output(
                scene.id,
                "planning",
                plan_result.value,
                plan_id=plan_id,
                prompt_compilation_id=_prompt_compilation_id(plan_result),
                status="needs_confirmation",
            )
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE scene_workflow_runs
                    SET status = 'awaiting_plan', current_stage = 'plan_confirmation',
                        plan_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (plan_id, run_id),
                )
            return self.get_run(run_id)
        except Exception as exc:
            self._fail_run(run_id, exc)
            raise

    def execute(
        self,
        run_id: int,
        *,
        user_instruction: str = "",
        model_id: int | None = None,
        character_ids: list[int] | None = None,
        material_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        plan_id = int(run["plan_id"] or 0)
        if not plan_id:
            raise ValueError("A rewrite plan is required.")
        plan = self.workflow.get_plan(plan_id)
        if plan["status"] != "confirmed":
            raise ValueError("The rewrite plan must be confirmed before generation.")
        scene_id = int(run["scene_id"])
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE scene_workflow_runs
                SET status = 'generating', current_stage = 'rewrite', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (run_id,),
            )
        try:
            rewrite = self._call_stage(
                scene_id,
                stage="rewrite",
                system_rules=(
                    "Write the scene from the confirmed plan. The complete current original scene "
                    "is authoritative. Return rewritten text and the resulting dynamic facts."
                ),
                user_instruction=user_instruction,
                task={
                    **plan["plan"],
                    "must_preserve_events": plan["plan"].get("preserve", []),
                    "required_end_state": plan["plan"].get("expected_end_state", {}),
                },
                output_protocol=_schema_text("scene_rewrite", ["text", "facts_after"]),
                validator=_validate_rewrite,
                model_id=model_id,
                character_ids=character_ids or [],
                material_ids=material_ids or [int(item["material_id"]) for item in plan["materials"]],
            )
            self.workflow.save_stage_output(
                scene_id,
                "rewrite",
                rewrite.value,
                plan_id=plan_id,
                prompt_compilation_id=_prompt_compilation_id(rewrite),
            )
            version_id = self.workflow.save_rewrite_version(
                scene_id,
                rewrite.value["text"],
                plan_id=plan_id,
                skeleton_version_id=int(plan["skeleton_version_id"]),
                prompt_compilation_id=_prompt_compilation_id(rewrite),
                facts_after=rewrite.value["facts_after"],
            )
            if rewrite.value["facts_after"]:
                self.scene_service.save_fact_ledger(
                    scene_id,
                    rewrite.value["facts_after"],
                    source_kind="rewrite",
                    model_id=rewrite.model_id,
                    prompt_compilation_id=_prompt_compilation_id(rewrite),
                )
            final_version_id, check = self._check_and_repair(
                run_id,
                scene_id,
                version_id,
                plan,
                user_instruction=user_instruction,
                model_id=model_id,
                character_ids=character_ids or [],
                material_ids=material_ids or [],
            )
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE scene_workflow_runs
                    SET status = 'completed', current_stage = 'completed',
                        completed_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (run_id,),
                )
            return {**self.get_run(run_id), "rewrite_version_id": final_version_id, "consistency": check}
        except Exception as exc:
            self._fail_run(run_id, exc)
            raise

    def get_run(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute("SELECT * FROM scene_workflow_runs WHERE id = ?", (run_id,)).fetchone()
            skeleton = None
            plan = None
            if row is not None and row["skeleton_version_id"] is not None:
                skeleton = connection.execute(
                    "SELECT nodes_json FROM story_skeleton_versions WHERE id = ?",
                    (row["skeleton_version_id"],),
                ).fetchone()
            if row is not None and row["plan_id"] is not None:
                plan = connection.execute(
                    "SELECT plan_json FROM rewrite_plans WHERE id = ?",
                    (row["plan_id"],),
                ).fetchone()
                material_rows = connection.execute(
                    "SELECT * FROM rewrite_plan_materials WHERE plan_id = ? ORDER BY material_id",
                    (row["plan_id"],),
                ).fetchall()
            else:
                material_rows = []
        if row is None:
            raise FileNotFoundError(f"Scene workflow run not found: {run_id}")
        result = dict(row)
        result["skeleton_nodes"] = json.loads(str(skeleton["nodes_json"])) if skeleton else []
        result["plan"] = json.loads(str(plan["plan_json"])) if plan else None
        result["material_mappings"] = [
            {
                **dict(item),
                "event_nodes": json.loads(str(item["event_nodes_json"])),
                "impact": json.loads(str(item["impact_json"])),
            }
            for item in material_rows
        ]
        return result

    def list_scene_history(self, scene_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT r.*, p.mode
                FROM scene_rewrite_versions r
                LEFT JOIN rewrite_plans p ON p.id = r.plan_id
                WHERE r.scene_id = ?
                ORDER BY r.version DESC
                """,
                (scene_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def restore_version(self, scene_id: int, version_id: int) -> int:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM scene_rewrite_versions WHERE id = ? AND scene_id = ?",
                (version_id, scene_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Scene rewrite version not found: {version_id}")
        return self.workflow.save_rewrite_version(
            scene_id,
            str(row["rewritten_text"]),
            plan_id=int(row["plan_id"]),
            skeleton_version_id=int(row["skeleton_version_id"]),
            facts_after=_object(row["facts_after_json"]),
            revision_kind="manual",
            parent_version_id=version_id,
        )

    def _call_stage(
        self,
        scene_id: int,
        *,
        stage: str,
        system_rules: str,
        user_instruction: str,
        task: dict[str, Any],
        output_protocol: str,
        validator,
        model_id: int | None,
        character_ids: list[int],
        material_ids: list[int],
    ) -> StructuredModelResult:
        scene = self._require_scene(scene_id)
        retrieval = self.context_service.retrieve(
            scene_id,
            manual_material_ids=material_ids,
            manual_character_ids=character_ids,
        )
        style = self.context_service.build_style_context(scene_id)
        model = self.model_service.resolve_model(model_id=model_id, project_id=scene.project_id)
        compilation = self.context_service.compile_scene_context(
            scene_id,
            stage=stage,
            system_rules=system_rules,
            user_instruction=user_instruction,
            task=task,
            model_context_tokens=max(16000, (model.max_tokens or 0) + 8000),
            reserved_output_tokens=max(2000, model.max_tokens or 0),
            retrieval_results=retrieval,
            style_context=style,
            model_id=model.id,
        )
        compiled = self.prompt_compiler.compile_scene_stage(
            stage=stage,
            compilation=compilation,
            output_protocol=output_protocol,
            provenance={"scene_id": scene_id},
        )
        result = self.model_service.run(
            invocation_kind="scene_rewrite",
            stage=stage,
            messages=compiled.message_list(),
            output_schema={"protocol": output_protocol},
            validator=validator,
            model_id=model.id,
            project_id=scene.project_id,
            chapter_id=scene.chapter_id,
            scene_id=scene.id,
        )
        object.__setattr__(result, "_prompt_compilation_id", int(compilation["id"]))
        return result

    def _check_and_repair(
        self,
        run_id: int,
        scene_id: int,
        source_version_id: int,
        plan: dict[str, Any],
        *,
        user_instruction: str,
        model_id: int | None,
        character_ids: list[int],
        material_ids: list[int],
    ) -> tuple[int, dict[str, Any]]:
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE scene_workflow_runs SET status = 'checking', current_stage = 'consistency' WHERE id = ?",
                (run_id,),
            )
        check_result = self._call_stage(
            scene_id,
            stage="consistency_check",
            system_rules=(
                "Compare the latest rewritten scene against the original, confirmed plan, facts, "
                "knowledge states, timeline, transitions, and recent style techniques."
            ),
            user_instruction=user_instruction,
            task={"plan": plan["plan"], "rewrite_version_id": source_version_id},
            output_protocol=_schema_text("consistency", sorted(CONSISTENCY_KEYS)),
            validator=_validate_consistency,
            model_id=model_id,
            character_ids=character_ids,
            material_ids=material_ids,
        )
        check = check_result.value
        scene = self._require_scene(scene_id)
        self.workflow.save_stage_output(
            scene_id,
            "consistency_check",
            check,
            plan_id=int(plan["id"]),
            prompt_compilation_id=_prompt_compilation_id(check_result),
        )
        self.workflow.save_consistency_check(
            project_id=scene.project_id,
            chapter_id=scene.chapter_id,
            scene_id=scene_id,
            check_scope="scene",
            result=check,
        )
        if not check["revision_required"]:
            return source_version_id, check
        with session(self.database_path) as connection:
            connection.execute(
                "UPDATE scene_workflow_runs SET status = 'repairing', current_stage = 'targeted_repair' WHERE id = ?",
                (run_id,),
            )
        repair_result = self._call_stage(
            scene_id,
            stage="targeted_repair",
            system_rules=(
                "Repair only the identified paragraph ranges. Do not rewrite unaffected paragraphs."
            ),
            user_instruction=user_instruction,
            task={"consistency": check, "rewrite_version_id": source_version_id},
            output_protocol=_schema_text("targeted_repairs", ["repairs"]),
            validator=_validate_repairs,
            model_id=model_id,
            character_ids=character_ids,
            material_ids=material_ids,
        )
        current_version = source_version_id
        for repair in repair_result.value["repairs"]:
            self.workflow.save_stage_output(
                scene_id,
                "targeted_repair",
                {"text": repair["replacement_text"], **repair},
                plan_id=int(plan["id"]),
                prompt_compilation_id=_prompt_compilation_id(repair_result),
            )
            repair_id = self.workflow.targeted_repair(
                scene_id=scene_id,
                source_version_id=current_version,
                paragraph_start=repair["paragraph_start"],
                paragraph_end=repair["paragraph_end"],
                issues=repair["issues"],
                replacement_text=repair["replacement_text"],
                affected_facts=repair["affected_facts"],
            )
            with session(self.database_path) as connection:
                current_version = int(
                    connection.execute(
                        "SELECT result_version_id FROM targeted_repairs WHERE id = ?",
                        (repair_id,),
                    ).fetchone()[0]
                )
        recheck = self._call_stage(
            scene_id,
            stage="consistency_check",
            system_rules="Recheck the repaired scene and report only remaining consistency risks.",
            user_instruction=user_instruction,
            task={"plan": plan["plan"], "rewrite_version_id": current_version},
            output_protocol=_schema_text("consistency", sorted(CONSISTENCY_KEYS)),
            validator=_validate_consistency,
            model_id=model_id,
            character_ids=character_ids,
            material_ids=material_ids,
        )
        self.workflow.save_consistency_check(
            project_id=scene.project_id,
            chapter_id=scene.chapter_id,
            scene_id=scene_id,
            check_scope="scene",
            result=recheck.value,
        )
        return current_version, recheck.value

    def _require_scene(self, scene_id: int):
        scene = self.scene_service.get_scene(scene_id)
        if scene is None:
            raise FileNotFoundError(f"Scene not found: {scene_id}")
        return scene

    def _require_confirmed_skeleton(self, version_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT v.confirmed_at, s.status
                FROM story_skeleton_versions v
                JOIN story_skeletons s ON s.id = v.skeleton_id
                WHERE v.id = ?
                """,
                (version_id,),
            ).fetchone()
        if row is None or row["confirmed_at"] is None or row["status"] != "confirmed":
            raise ValueError("Skeleton version must be confirmed before planning.")

    def _skeleton_nodes(self, version_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT nodes_json FROM story_skeleton_versions WHERE id = ?",
                (version_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Skeleton version not found: {version_id}")
        value = json.loads(str(row["nodes_json"]))
        return value if isinstance(value, list) else []

    def _fail_run(self, run_id: int, exc: Exception) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE scene_workflow_runs
                SET status = 'failed', error_message = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (str(exc), run_id),
            )


def _prompt_compilation_id(result: StructuredModelResult) -> int | None:
    return getattr(result, "_prompt_compilation_id", None)


def _schema_text(name: str, fields: list[str]) -> str:
    return f"Return strict JSON for {name}. Required fields: {', '.join(fields)}."


def _validate_analysis(value: dict[str, Any]) -> dict[str, Any]:
    missing = SCENE_ANALYSIS_KEYS - set(value)
    if missing:
        raise ValueError(f"Scene analysis missing fields: {', '.join(sorted(missing))}")
    return value


def _validate_skeleton(value: dict[str, Any]) -> dict[str, Any]:
    nodes = value.get("event_nodes")
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("event_nodes must be a non-empty array.")
    for index, node in enumerate(nodes):
        if not isinstance(node, dict) or not str(node.get("event") or "").strip():
            raise ValueError(f"event_nodes[{index}] requires event text.")
    return {"event_nodes": nodes}


def _validate_plan(value: dict[str, Any]) -> dict[str, Any]:
    required = {
        "sequence",
        "preserve",
        "modify",
        "add",
        "material_insertions",
        "character_changes",
        "expected_end_state",
    }
    missing = required - set(value)
    if missing or not isinstance(value.get("sequence"), list) or not value["sequence"]:
        raise ValueError(f"Rewrite plan is invalid; missing: {', '.join(sorted(missing))}")
    return value


def _validate_rewrite(value: dict[str, Any]) -> dict[str, Any]:
    text = str(value.get("text") or "").strip()
    facts = value.get("facts_after")
    if not text or not isinstance(facts, dict):
        raise ValueError("Rewrite output requires non-empty text and facts_after object.")
    return {"text": text, "facts_after": facts}


def _validate_consistency(value: dict[str, Any]) -> dict[str, Any]:
    missing = CONSISTENCY_KEYS - set(value)
    if missing:
        raise ValueError(f"Consistency output missing fields: {', '.join(sorted(missing))}")
    value["revision_required"] = bool(value["revision_required"])
    return value


def _validate_repairs(value: dict[str, Any]) -> dict[str, Any]:
    repairs = value.get("repairs")
    if not isinstance(repairs, list) or not repairs:
        raise ValueError("Targeted repair output requires a non-empty repairs array.")
    normalized = []
    for index, repair in enumerate(repairs):
        if not isinstance(repair, dict):
            raise ValueError(f"repairs[{index}] must be an object.")
        start = int(repair.get("paragraph_start", -1))
        end = int(repair.get("paragraph_end", -1))
        replacement = str(repair.get("replacement_text") or "").strip()
        if start < 0 or end < start or not replacement:
            raise ValueError(f"repairs[{index}] has an invalid paragraph range or replacement.")
        normalized.append(
            {
                "paragraph_start": start,
                "paragraph_end": end,
                "issues": repair.get("issues", []),
                "replacement_text": replacement,
                "affected_facts": repair.get("affected_facts", {}),
            }
        )
    return {"repairs": normalized}


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
