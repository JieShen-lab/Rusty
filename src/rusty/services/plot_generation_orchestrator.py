from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.branch_service import BranchService
from rusty.services.chapter_version_service import (
    ChapterVersionService,
    SourceVersionConflict,
)
from rusty.services.context_service import ContextService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.structured_skeleton import validate_structured_skeleton
from rusty.services.workflow_ai import WorkflowAI


GENERATION_MODES = {
    "bounded_insert": ("rewrite", "in_place", True),
    "open_continuation": ("branch", "branch", False),
    "fork": ("branch", "branch", False),
    "fork_and_rejoin": ("branch", "branch", True),
}

PLOT_STATUS_AWAITING_SKELETON = "awaiting_skeleton"
PLOT_STATUS_PLANNING_BLOCKED = "planning_blocked"
PLOT_STATUS_AWAITING_SEAMS = "awaiting_seams"
PLOT_STATUS_READY = "ready"
PLOT_STATUS_GENERATING = "generating"
PLOT_STATUS_REPAIR_REQUIRED = "repair_required"
PLOT_STATUS_COMPLETED = "completed"
PLOT_STATUS_FAILED = "failed"
PLOT_STATUS_CANCELLED = "cancelled"

PLOT_ACTIVE_STATUSES = {
    PLOT_STATUS_AWAITING_SKELETON,
    PLOT_STATUS_PLANNING_BLOCKED,
    PLOT_STATUS_AWAITING_SEAMS,
    PLOT_STATUS_READY,
    PLOT_STATUS_GENERATING,
    PLOT_STATUS_REPAIR_REQUIRED,
}
PLOT_TERMINAL_STATUSES = {
    PLOT_STATUS_COMPLETED,
    PLOT_STATUS_FAILED,
    PLOT_STATUS_CANCELLED,
}


class PlotGenerationOrchestrator:
    """Persisted, AI-driven orchestration shared by all plot topologies."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        ai_client=None,
    ) -> None:
        self.database_path = (
            Path(database_path) if database_path is not None else default_database_path()
        )
        self.projects = ProjectService(self.database_path)
        self.branches = BranchService(self.database_path)
        self.chapter_versions = ChapterVersionService(self.database_path)
        self.contexts = ContextService(self.database_path)
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def start(
        self,
        *,
        project_id: int,
        generation_mode: str,
        start_anchor: dict[str, Any],
        user_direction: str,
        return_anchor: dict[str, Any] | None = None,
        parent_branch_id: int | None = None,
        selected_character_ids: list[int] | None = None,
        selected_material_ids: list[int] | None = None,
        style_profile_id: int | None = None,
        branch_name: str = "Generated branch",
        range_operation: str = "insert_between",
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        required_kind, topology, needs_return = self._validate_mode(
            project_id, generation_mode, return_anchor
        )
        del required_kind
        if range_operation not in {"insert_between", "replace_range"}:
            raise ValueError(f"Unsupported range operation: {range_operation}")
        if generation_mode != "bounded_insert" and range_operation != "insert_between":
            raise ValueError("range_operation only applies to bounded_insert runs.")
        rewrite_source = None
        if generation_mode == "bounded_insert":
            chapter_id = self.chapter_versions.resolve_anchor_chapter_id(
                project_id, start_anchor
            )
            rewrite_source = self.chapter_versions.resolve_chapter_source(
                int(chapter_id), source
            ).to_dict()
        context = self.contexts.compile_plot_generation_context(
            project_id=project_id,
            start_anchor=start_anchor,
            return_anchor=return_anchor,
            parent_branch_id=parent_branch_id,
            user_direction=user_direction,
            selected_character_ids=selected_character_ids or [],
            selected_material_ids=selected_material_ids or [],
            style_profile_id=style_profile_id,
            rewrite_source_snapshot=rewrite_source,
        )
        source_text = str(context["start_anchor_context"].get("text") or "")
        start_anchor = {**start_anchor}
        if start_anchor.get("chapter_id") is None and context["start_anchor_context"].get("chapter_id") is not None:
            start_anchor["chapter_id"] = int(context["start_anchor_context"]["chapter_id"])
        if (
            start_anchor.get("text_offset") is None
            and context["start_anchor_context"].get("offset") is not None
        ):
            start_anchor["text_offset"] = int(
                context["start_anchor_context"]["offset"]
            )
        if context["start_anchor_context"].get("source_version_id") is not None:
            start_anchor.setdefault(
                "source_version_id",
                int(context["start_anchor_context"]["source_version_id"]),
            )
        authoritative_start_hash = str(context["start_anchor_context"].get("source_hash") or self.branches.source_hash(source_text))
        if start_anchor.get("source_hash") and start_anchor["source_hash"] != authoritative_start_hash:
            raise ValueError("Start anchor source_hash does not match the current source.")
        if not start_anchor.get("source_hash"):
            start_anchor["source_hash"] = str(
                authoritative_start_hash
            )
        if return_anchor is not None:
            return_text = str(
                (context.get("return_anchor_context") or {}).get("text") or source_text
            )
            return_anchor = {**return_anchor}
            if return_anchor.get("chapter_id") is None and (context.get("return_anchor_context") or {}).get("chapter_id") is not None:
                return_anchor["chapter_id"] = int(context["return_anchor_context"]["chapter_id"])
            if (
                return_anchor.get("text_offset") is None
                and (context.get("return_anchor_context") or {}).get("offset")
                is not None
            ):
                return_anchor["text_offset"] = int(
                    context["return_anchor_context"]["offset"]
                )
            authoritative_return_hash = str((context.get("return_anchor_context") or {}).get("source_hash") or self.branches.source_hash(return_text))
            if return_anchor.get("source_hash") and return_anchor["source_hash"] != authoritative_return_hash:
                raise ValueError("Return anchor source_hash does not match the current source.")
            if not return_anchor.get("source_hash"):
                return_anchor["source_hash"] = str(
                    authoritative_return_hash
                )
            if (context.get("return_anchor_context") or {}).get("source_version_id") is not None:
                return_anchor.setdefault(
                    "source_version_id",
                    int(context["return_anchor_context"]["source_version_id"]),
                )
            if generation_mode == "bounded_insert":
                if start_anchor.get("chapter_id") != return_anchor.get("chapter_id"):
                    raise ValueError("bounded_insert anchors must belong to the same chapter.")
                if int(return_anchor["text_offset"]) < int(start_anchor["text_offset"]):
                    raise ValueError("Return anchor cannot be earlier than start anchor.")
            else:
                self.branches.validate_anchor_order(project_id, start_anchor, return_anchor)

        proposed = self.ai.generate_json(
            project_id=project_id,
            stage="propose_target_skeleton",
            payload={
                "generation_mode": generation_mode,
                "context": context,
                "user_direction": user_direction,
            },
            output_contract="A complete StructuredSkeleton JSON object.",
        )
        skeleton = validate_structured_skeleton(
            proposed.get("target_skeleton", proposed)
        )
        required_return_state = (
            context["return_state_constraints"] if needs_return else {}
        )
        planning_issues = (
            _state_issues(required_return_state, skeleton["required_end_state"])
            if generation_mode == "fork_and_rejoin"
            else []
        )
        branch_id = None
        if topology == "branch":
            branch = self.branches.create_branch(
                project_id=project_id,
                parent_branch_id=parent_branch_id,
                name=branch_name,
                branch_mode=generation_mode,
                start_anchor=start_anchor,
                return_anchor=return_anchor,
                base_source_version_id=(
                    int(start_anchor["source_version_id"])
                    if parent_branch_id is not None
                    and start_anchor.get("source_version_id") is not None
                    else None
                ),
            )
            branch_id = int(branch["id"])
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO plot_generation_runs (
                    project_id, branch_id, generation_mode, output_topology,
                    start_anchor_json, return_anchor_json, start_state_json,
                    required_return_state_json, target_skeleton_json, context_json,
                    issues_json, status, stage, user_direction,
                    selected_character_ids_json, selected_material_ids_json,
                    style_profile_id, range_operation, source_chapter_id,
                    source_base_kind, source_base_version_id, source_hash,
                    source_text_snapshot, require_source_head_match,
                    expected_source_head_version_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    branch_id,
                    generation_mode,
                    topology,
                    json.dumps(start_anchor, ensure_ascii=False),
                    json.dumps(return_anchor, ensure_ascii=False)
                    if return_anchor
                    else None,
                    json.dumps(context["start_state"], ensure_ascii=False),
                    json.dumps(required_return_state, ensure_ascii=False),
                    json.dumps(skeleton, ensure_ascii=False),
                    json.dumps(context, ensure_ascii=False),
                    json.dumps(planning_issues, ensure_ascii=False),
                    PLOT_STATUS_PLANNING_BLOCKED
                    if planning_issues
                    else PLOT_STATUS_AWAITING_SKELETON,
                    "confirm_target_skeleton",
                    user_direction,
                    json.dumps(selected_character_ids or []),
                    json.dumps(selected_material_ids or []),
                    style_profile_id,
                    range_operation,
                    rewrite_source["chapter_id"] if rewrite_source else None,
                    rewrite_source["source_kind"] if rewrite_source else None,
                    rewrite_source["source_version_id"] if rewrite_source else None,
                    rewrite_source["content_hash"] if rewrite_source else None,
                    rewrite_source["text"] if rewrite_source else None,
                    1 if rewrite_source and rewrite_source["require_head_match"] else 0,
                    rewrite_source["expected_head_version_id"] if rewrite_source else None,
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    def confirm_target_skeleton(
        self, run_id: int, target_skeleton: dict[str, Any]
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {
            PLOT_STATUS_AWAITING_SKELETON,
            PLOT_STATUS_PLANNING_BLOCKED,
        }:
            raise ValueError("Target skeleton cannot be changed in the current run state.")
        skeleton = validate_structured_skeleton(target_skeleton)
        if run["generation_mode"] == "fork_and_rejoin":
            issues = _state_issues(
                run["required_return_state"], skeleton["required_end_state"]
            )
            if issues:
                self._transition(
                    run_id,
                    allowed_from={
                        PLOT_STATUS_AWAITING_SKELETON,
                        PLOT_STATUS_PLANNING_BLOCKED,
                    },
                    to_status=PLOT_STATUS_PLANNING_BLOCKED,
                    stage="confirm_target_skeleton",
                    updates={
                        "issues_json": issues,
                        "target_skeleton_json": skeleton,
                    },
                )
                return self.get_run(run_id)
        proposed = self.ai.generate_json(
            project_id=int(run["project_id"]),
            stage="propose_seams",
            payload={
                "generation_mode": run["generation_mode"],
                "start_anchor": run["start_anchor"],
                "return_anchor": run["return_anchor"],
                "target_skeleton": skeleton,
                "context": run["context"],
            },
            output_contract='{"seams":[SeamProposal,...]}',
        )
        seams = proposed.get("seams")
        if not isinstance(seams, list):
            raise ValueError("AI seam proposal must contain a seams array.")
        for seam in seams:
            if not isinstance(seam, dict) or seam.get("operation") not in {
                "keep",
                "insert_before",
                "insert_after",
                "replace_range",
            }:
                raise ValueError("AI returned an invalid seam proposal.")
        seams = self._replace_seam_records(run, seams)
        self._transition(
            run_id,
            allowed_from={
                PLOT_STATUS_AWAITING_SKELETON,
                PLOT_STATUS_PLANNING_BLOCKED,
            },
            to_status=PLOT_STATUS_AWAITING_SEAMS,
            stage="confirm_seams",
            updates={
                "target_skeleton_json": skeleton,
                "seams_json": seams,
                "issues_json": [],
            },
        )
        return self.get_run(run_id)

    def confirm_seams(
        self,
        run_id: int,
        reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] != PLOT_STATUS_AWAITING_SEAMS:
            raise ValueError("Generation seams cannot be reviewed in the current run state.")
        stored_by_id = {int(item["id"]): item for item in self._stored_seams(run)}
        review_ids = [int(review.get("seam_id") or 0) for review in reviews]
        if len(review_ids) != len(set(review_ids)):
            raise ValueError("Duplicate seam reviews are not allowed.")
        if set(review_ids) != set(stored_by_id):
            raise ValueError("Every generation seam must be explicitly reviewed.")
        validated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for review in reviews:
            decision = str(review.get("decision") or "")
            if decision not in {"confirmed", "rejected"}:
                raise ValueError("All generation seams must be explicitly reviewed.")
            seam_id = int(review.get("seam_id") or 0)
            if seam_id not in stored_by_id:
                raise ValueError("Generation seam does not belong to this run.")
            current_source = self._resolve_seam_source(run, stored_by_id[seam_id])
            if current_source["source_hash"] != stored_by_id[seam_id]["source_hash"]:
                raise ValueError("Generation seam source hash mismatch.")
            validated.append((review, stored_by_id[seam_id], current_source))
        reviewed = [
            {
                **stored,
                "status": str(review["decision"]),
                "proposed_text": (
                    str(review["proposed_text"])
                    if review.get("proposed_text") is not None
                    else str(stored.get("proposed_text") or "")
                ),
            }
            for review, stored, _current_source in validated
        ]
        scene_plan = self.ai.generate_json(
            project_id=int(run["project_id"]),
            stage="generate_scene_plan",
            payload={
                "target_skeleton": run["target_skeleton"],
                "context": run["context"],
                "confirmed_seams": reviewed,
            },
            output_contract='{"chapters":[{"title":str,"summary":str,"scenes":[{"title":str,"direction":str}]}]}',
        )
        _validate_scene_plan(scene_plan)
        self._commit_seam_reviews_and_ready(run, reviewed, scene_plan)
        return self.get_run(run_id)

    def execute(self, run_id: int, *, max_scenes: int | None = None) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {PLOT_STATUS_READY, PLOT_STATUS_GENERATING}:
            raise ValueError("Target skeleton and seams must be confirmed before generation.")
        remaining = self._planned_scene_count(run) - int(run["next_scene_cursor"])
        limit = remaining if max_scenes is None else min(max_scenes, remaining)
        if limit <= 0:
            raise ValueError("Plot generation has no remaining scenes.")
        current = run
        for _ in range(limit):
            current = self._generate_next_scene(run_id)
            if current["status"] in {
                PLOT_STATUS_COMPLETED,
                PLOT_STATUS_REPAIR_REQUIRED,
                PLOT_STATUS_FAILED,
            }:
                break
        return current

    def generate_next(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {PLOT_STATUS_READY, PLOT_STATUS_GENERATING}:
            raise ValueError("Run is not ready to generate the next scene.")
        return self._generate_next_scene(run_id)

    def retry(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        self._transition(
            run_id,
            allowed_from={PLOT_STATUS_REPAIR_REQUIRED, PLOT_STATUS_FAILED},
            to_status=PLOT_STATUS_READY,
            stage="generate_next_scene",
            updates={
                "generated_progress_json": {"chapters": [], "scenes": []},
                "next_scene_cursor": 0,
                "generation_attempt": int(run.get("generation_attempt") or 0) + 1,
                "fact_ledger_json": run["start_state"],
                "issues_json": [],
                "result_json": {},
            },
        )
        return self.get_run(run_id)

    def _generate_next_scene(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {PLOT_STATUS_READY, PLOT_STATUS_GENERATING}:
            raise ValueError("Run is not ready to generate the next scene.")
        targets = self._flatten_scene_plan(run)
        cursor = int(run["next_scene_cursor"])
        if cursor >= len(targets):
            raise ValueError("Plot generation has no remaining scenes.")
        chapter_index, chapter, scene = targets[cursor]
        progress = json.loads(json.dumps(run["generated_progress"], ensure_ascii=False))
        progress.setdefault("chapters", [])
        progress.setdefault("scenes", [])
        ledger = (
            dict(run["fact_ledger"])
            if cursor > 0 and run["fact_ledger"]
            else dict(run["start_state"])
        )
        try:
            prose = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="generate_next_scene",
                payload={
                    "scene": scene,
                    "chapter": chapter,
                    "target_skeleton": run["target_skeleton"],
                    "context": run["context"],
                    "fact_ledger": ledger,
                    "previous_generated_scene": (
                        progress["scenes"][-1]["text"] if progress["scenes"] else ""
                    ),
                },
                output_contract='{"text":str}',
            )
            text = prose.get("text")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("AI scene generation returned empty text.")
            facts = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="update_fact_ledger",
                payload={"text": text, "facts_before": ledger},
                output_contract='{"facts_after":object}',
            )
            facts_after = facts.get("facts_after")
            if not isinstance(facts_after, dict):
                raise ValueError("AI fact extraction must return facts_after.")
        except Exception as exc:
            self._transition(
                run_id,
                allowed_from={PLOT_STATUS_READY, PLOT_STATUS_GENERATING},
                to_status=PLOT_STATUS_FAILED,
                stage="generate_next_scene",
                updates={"issues_json": [{"type": "technical_failure", "message": str(exc)}]},
            )
            raise
        scene_result = {
            "title": str(scene.get("title") or ""),
            "text": text,
            "facts_after": facts_after,
        }
        while len(progress["chapters"]) <= chapter_index:
            planned = run["scene_plan"]["chapters"][len(progress["chapters"])]
            progress["chapters"].append(
                {
                    "title": planned["title"],
                    "summary": planned.get("summary", ""),
                    "facts_before": dict(ledger),
                    "facts_after": dict(ledger),
                    "scenes": [],
                }
            )
        progress["chapters"][chapter_index]["scenes"].append(scene_result)
        progress["chapters"][chapter_index]["facts_after"] = dict(facts_after)
        progress["scenes"].append(scene_result)
        next_cursor = cursor + 1
        self._transition(
            run_id,
            allowed_from={PLOT_STATUS_READY, PLOT_STATUS_GENERATING},
            to_status=PLOT_STATUS_GENERATING,
            stage="generate_next_scene",
            updates={
                "generated_progress_json": progress,
                "next_scene_cursor": next_cursor,
                "fact_ledger_json": facts_after,
            },
        )
        if next_cursor < len(targets):
            return self.get_run(run_id)
        return self._consistency_check_and_commit(run_id)

    def _consistency_check_and_commit(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        generated = list(run["generated_progress"]["scenes"])
        ledger = dict(run["fact_ledger"])
        try:
            consistency = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="consistency_check",
                payload={
                    "target_skeleton": run["target_skeleton"],
                    "generated_scenes": generated,
                    "final_state": ledger,
                    "required_return_state": run["required_return_state"],
                },
                output_contract='{"issues":array,"final_state":object}',
            )
            issues = consistency.get("issues")
            final_state = consistency.get("final_state", ledger)
            if not isinstance(issues, list) or not isinstance(final_state, dict):
                raise ValueError("AI consistency check returned an invalid result.")
        except Exception as exc:
            self._transition(
                run_id,
                allowed_from={PLOT_STATUS_GENERATING},
                to_status=PLOT_STATUS_FAILED,
                stage="consistency_check",
                updates={"issues_json": [{"type": "technical_failure", "message": str(exc)}]},
            )
            raise
        issues.extend(_state_issues(run["required_return_state"], final_state))
        if issues:
            self._transition(
                run_id,
                allowed_from={PLOT_STATUS_GENERATING},
                to_status=PLOT_STATUS_REPAIR_REQUIRED,
                stage="consistency_check",
                updates={"issues_json": issues, "fact_ledger_json": ledger},
            )
            return self.get_run(run_id)

        generated = _apply_branch_seam_text(
            json.loads(json.dumps(generated, ensure_ascii=False)), run["seams"]
        )
        chapters = json.loads(
            json.dumps(run["generated_progress"]["chapters"], ensure_ascii=False)
        )
        scene_cursor = 0
        for chapter in chapters:
            for scene_index in range(len(chapter["scenes"])):
                chapter["scenes"][scene_index] = generated[scene_cursor]
                scene_cursor += 1
        try:
            with session(self.database_path) as connection:
                locked = connection.execute(
                    """
                    UPDATE plot_generation_runs SET updated_at = updated_at
                    WHERE id = ? AND status = ?
                    """,
                    (run_id, PLOT_STATUS_GENERATING),
                )
                if locked.rowcount != 1:
                    raise ValueError("Plot run is no longer generating.")
                if run["output_topology"] == "branch":
                    saved_chapters = self.branches.commit_generated_run(
                        connection,
                        branch_id=int(run["branch_id"]),
                        chapters=chapters,
                    )
                    result = {"branch_id": run["branch_id"], "chapters": saved_chapters}
                    result_version_id = None
                else:
                    start = run["start_anchor"]
                    end = run["return_anchor"]
                    if start.get("chapter_id") != end.get("chapter_id"):
                        raise ValueError("bounded_insert anchors must belong to the same chapter.")
                    source_text = str(run.get("source_text_snapshot") or "")
                    if not source_text:
                        raise ValueError("Bounded insert run has no frozen source text.")
                    inserted = "\n\n".join(scene["text"] for scene in generated)
                    if run["range_operation"] == "replace_range":
                        rewritten = _compose_replace_range(
                            source_text,
                            int(start["text_offset"]),
                            int(end["text_offset"]),
                            inserted,
                            run["seams"],
                        )
                    else:
                        rewritten = _compose_insert_between(
                            source_text,
                            int(start["text_offset"]),
                            inserted,
                            run["seams"],
                        )
                    version = self.chapter_versions.append_chapter_rewrite_version(
                        connection,
                        chapter_id=int(run["source_chapter_id"]),
                        rewritten_text=rewritten,
                        source_operation="plot_generation",
                        source_run_id=run_id,
                        source_base_kind=str(run["source_base_kind"]),
                        source_base_version_id=run.get("source_base_version_id"),
                        source_hash=str(run["source_hash"]),
                        facts_before=run["start_state"],
                        facts_after=ledger,
                        require_head_match=bool(run["require_source_head_match"]),
                        expected_head_version_id=run.get(
                            "expected_source_head_version_id"
                        ),
                    )
                    result_version_id = int(version["id"])
                    result = {
                        "chapter_id": int(run["source_chapter_id"]),
                        "rewrite_version_id": result_version_id,
                        "rewritten_text": rewritten,
                    }
                self._transition_in_connection(
                    connection,
                    run_id,
                    allowed_from={PLOT_STATUS_GENERATING},
                    to_status=PLOT_STATUS_COMPLETED,
                    stage="complete",
                    updates={
                        "result_json": result,
                        "issues_json": [],
                        "fact_ledger_json": ledger,
                        "result_version_id": result_version_id,
                    },
                )
        except SourceVersionConflict as conflict:
            self._transition(
                run_id,
                allowed_from={PLOT_STATUS_GENERATING},
                to_status=PLOT_STATUS_FAILED,
                stage="source_conflict",
                updates={
                    "issues_json": [
                        {
                            "type": "source_version_conflict",
                            "expected_version_id": conflict.expected_version_id,
                            "current_version_id": conflict.current_version_id,
                        }
                    ]
                },
            )
            return self.get_run(run_id)
        except Exception as exc:
            try:
                self._transition(
                    run_id,
                    allowed_from={PLOT_STATUS_GENERATING},
                    to_status=PLOT_STATUS_FAILED,
                    stage="finalize",
                    updates={
                        "issues_json": [
                            {"type": "finalization_failure", "message": str(exc)}
                        ]
                    },
                )
            except ValueError:
                pass
            raise
        return self.get_run(run_id)

    @staticmethod
    def _flatten_scene_plan(run: dict[str, Any]) -> list[tuple[int, dict[str, Any], dict[str, Any]]]:
        return [
            (chapter_index, chapter, scene)
            for chapter_index, chapter in enumerate(run["scene_plan"]["chapters"])
            for scene in chapter["scenes"]
        ]

    def _planned_scene_count(self, run: dict[str, Any]) -> int:
        return len(self._flatten_scene_plan(run))

    def cancel(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        self._transition(
            run_id,
            allowed_from=PLOT_ACTIVE_STATUSES | {PLOT_STATUS_FAILED},
            to_status=PLOT_STATUS_CANCELLED,
            stage="cancelled",
        )
        return self.get_run(run_id)

    def list_runs(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id FROM plot_generation_runs
                WHERE project_id = ? ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [self.get_run(int(row["id"])) for row in rows]

    def get_run(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM plot_generation_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Plot generation run not found: {run_id}")
        result = dict(row)
        defaults = {
            "start_anchor": {},
            "return_anchor": None,
            "start_state": {},
            "required_return_state": {},
            "target_skeleton": {},
            "context": {},
            "seams": [],
            "issues": [],
            "result": {},
            "scene_plan": {},
            "fact_ledger": {},
            "generated_progress": {"chapters": [], "scenes": []},
            "selected_character_ids": [],
            "selected_material_ids": [],
        }
        for key, default in defaults.items():
            raw = row[f"{key}_json"] if f"{key}_json" in row.keys() else None
            result[key] = json.loads(raw) if raw else default
        return result

    def _replace_seam_records(
        self, run: dict[str, Any], seams: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            if run["branch_id"] is not None:
                connection.execute(
                    "DELETE FROM branch_seams WHERE plot_run_id = ?", (run["id"],)
                )
            else:
                connection.execute(
                    "DELETE FROM rewrite_seams WHERE run_id = ?", (run["id"],)
                )
        stored = []
        for seam in seams:
            binding = self._seam_binding(run, str(seam["seam_kind"]))
            if run["branch_id"] is not None:
                item = self.branches.create_seam(
                    int(run["branch_id"]),
                    seam_kind=str(seam["seam_kind"]),
                    operation=str(seam["operation"]),
                    original_text=binding["text"],
                    proposed_text=str(seam.get("proposed_text") or ""),
                    source_anchor=binding["anchor"],
                    source_version_id=binding.get("source_version_id"),
                    source_range=binding["source_range"],
                    source_hash=binding["source_hash"],
                    reason=str(seam.get("reason") or ""),
                    plot_run_id=int(run["id"]),
                )
            else:
                with session(self.database_path) as connection:
                    cursor = connection.execute(
                        """
                        INSERT INTO rewrite_seams(
                            run_id, project_id, seam_kind, operation,
                            original_text, proposed_text, source_range_json,
                            source_hash, reason, source_anchor_json, source_version_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run["id"],
                            run["project_id"],
                            seam["seam_kind"],
                            seam["operation"],
                            binding["text"],
                            seam.get("proposed_text") or "",
                            json.dumps(binding["source_range"], ensure_ascii=False),
                            binding["source_hash"],
                            seam.get("reason") or "",
                            json.dumps(binding["anchor"], ensure_ascii=False),
                            binding.get("source_version_id"),
                        ),
                    )
                    rewrite_seam_id = int(cursor.lastrowid)
                item = self._get_rewrite_seam(rewrite_seam_id)
            stored.append(item)
        return stored

    def _stored_seams(self, run: dict[str, Any]) -> list[dict[str, Any]]:
        if run["branch_id"] is not None:
            with session(self.database_path) as connection:
                rows = connection.execute(
                    "SELECT id FROM branch_seams WHERE plot_run_id = ? ORDER BY id",
                    (run["id"],),
                ).fetchall()
            return [self.branches.get_seam(int(row["id"])) for row in rows]
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id FROM rewrite_seams WHERE run_id = ? ORDER BY id",
                (run["id"],),
            ).fetchall()
        return [self._get_rewrite_seam(int(row["id"])) for row in rows]

    def _review_stored_seam(
        self,
        run: dict[str, Any],
        seam_id: int,
        *,
        decision: str,
        current_source_text: str,
        proposed_text: str,
    ) -> dict[str, Any]:
        if run["branch_id"] is not None:
            return self.branches.review_seam(
                seam_id,
                decision=decision,
                current_source_text=current_source_text,
                proposed_text=proposed_text,
            )
        seam = self._get_rewrite_seam(seam_id)
        if decision == "confirmed" and self.branches.source_hash(current_source_text) != seam["source_hash"]:
            raise ValueError("Generation seam source hash mismatch.")
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE rewrite_seams
                SET status = ?, proposed_text = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND run_id = ?
                """,
                (decision, proposed_text, seam_id, run["id"]),
            )
        return self._get_rewrite_seam(seam_id)

    def _get_rewrite_seam(self, seam_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM rewrite_seams WHERE id = ?", (seam_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Rewrite seam not found.")
        result = dict(row)
        result["source_range"] = json.loads(row["source_range_json"])
        result["source_anchor"] = json.loads(row["source_anchor_json"] or "{}")
        return result

    def _seam_binding(self, run: dict[str, Any], seam_kind: str) -> dict[str, Any]:
        anchor = run["start_anchor"] if seam_kind == "entry" else run["return_anchor"]
        if not isinstance(anchor, dict):
            raise ValueError(f"{seam_kind} seam has no source anchor.")
        source = self._resolve_anchor_source(run, anchor)
        return {**source, "anchor": anchor}

    def _resolve_seam_source(
        self, run: dict[str, Any], seam: dict[str, Any]
    ) -> dict[str, Any]:
        anchor = seam.get("source_anchor")
        if not isinstance(anchor, dict) or not anchor:
            anchor = (
                run["start_anchor"]
                if seam["seam_kind"] == "entry"
                else run["return_anchor"]
            )
        if not isinstance(anchor, dict):
            raise ValueError("Generation seam source anchor is missing.")
        current_anchor = dict(anchor)
        if current_anchor.get("anchor_type") in {"branch_chapter", "branch_scene"}:
            current_anchor.pop("source_version_id", None)
        source = self._resolve_anchor_source(run, current_anchor)
        if seam.get("source_version_id") is not None and source.get("source_version_id") != seam.get("source_version_id"):
            raise ValueError("Generation seam source version changed.")
        return source

    def _resolve_anchor_source(
        self, run: dict[str, Any], anchor: dict[str, Any]
    ) -> dict[str, Any]:
        if run.get("output_topology") == "in_place":
            source_text = str(run.get("source_text_snapshot") or "")
            if not source_text:
                raise ValueError("Rewrite generation run has no frozen source snapshot.")
            offset = int(anchor.get("text_offset") or 0)
            if offset < 0 or offset > len(source_text):
                raise ValueError("Generation seam offset exceeds the frozen source snapshot.")
            return {
                "text": source_text,
                "source_hash": str(run["source_hash"]),
                "source_version_id": run.get("source_base_version_id"),
                "source_range": {"start": 0, "end": len(source_text)},
                "offset": offset,
            }
        parent_branch_id = None
        if anchor.get("anchor_type") in {"branch_chapter", "branch_scene"}:
            if run.get("branch_id") is None:
                raise ValueError("Branch seam anchor has no generated branch.")
            branch = self.branches.get_branch(int(run["branch_id"]))
            parent_branch_id = branch.get("parent_branch_id")
        return self.contexts.resolve_generation_anchor_source(
            int(run["project_id"]),
            anchor,
            parent_branch_id=(int(parent_branch_id) if parent_branch_id else None),
        )

    def _validate_mode(
        self,
        project_id: int,
        generation_mode: str,
        return_anchor: dict[str, Any] | None,
    ) -> tuple[str, str, bool]:
        if generation_mode not in GENERATION_MODES:
            raise ValueError(f"Unsupported generation mode: {generation_mode}")
        required_kind, topology, needs_return = GENERATION_MODES[generation_mode]
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        if project.project_kind != required_kind:
            raise ValueError(f"{generation_mode} requires a {required_kind} project.")
        if needs_return != (return_anchor is not None):
            raise ValueError(
                f"{generation_mode} {'requires' if needs_return else 'does not accept'} a return anchor."
            )
        return required_kind, topology, needs_return

    def _transition(
        self,
        run_id: int,
        *,
        allowed_from: set[str],
        to_status: str,
        stage: str,
        updates: dict[str, Any] | None = None,
    ) -> None:
        with session(self.database_path) as connection:
            self._transition_in_connection(
                connection,
                run_id,
                allowed_from=allowed_from,
                to_status=to_status,
                stage=stage,
                updates=updates,
            )

    def _transition_in_connection(
        self,
        connection: Any,
        run_id: int,
        *,
        allowed_from: set[str],
        to_status: str,
        stage: str,
        updates: dict[str, Any] | None = None,
    ) -> None:
        if to_status not in PLOT_ACTIVE_STATUSES | PLOT_TERMINAL_STATUSES:
            raise ValueError(f"Unsupported plot generation status: {to_status}")
        values = {"status": to_status, "stage": stage, **(updates or {})}
        assignments = []
        parameters: list[Any] = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(
                json.dumps(value, ensure_ascii=False)
                if key.endswith("_json")
                else value
            )
        allowed = sorted(allowed_from)
        parameters.extend([run_id, *allowed])
        placeholders = ", ".join("?" for _ in allowed)
        cursor = connection.execute(
            f"UPDATE plot_generation_runs SET {', '.join(assignments)}, "
            "updated_at = CURRENT_TIMESTAMP WHERE id = ? "
            f"AND status IN ({placeholders})",
            parameters,
        )
        if cursor.rowcount == 0:
            row = connection.execute(
                "SELECT status FROM plot_generation_runs WHERE id = ?", (run_id,)
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Plot generation run not found: {run_id}")
            raise ValueError(
                f"Illegal plot generation transition: {row['status']} -> {to_status}."
            )

    def _commit_seam_reviews_and_ready(
        self,
        run: dict[str, Any],
        reviewed: list[dict[str, Any]],
        scene_plan: dict[str, Any],
    ) -> None:
        table = "branch_seams" if run["branch_id"] is not None else "rewrite_seams"
        with session(self.database_path) as connection:
            current = connection.execute(
                "SELECT status FROM plot_generation_runs WHERE id = ?", (run["id"],)
            ).fetchone()
            if current is None or current["status"] != PLOT_STATUS_AWAITING_SEAMS:
                raise ValueError("Generation seams cannot be reviewed in the current run state.")
            for seam in reviewed:
                cursor = connection.execute(
                    f"""
                    UPDATE {table}
                    SET status = ?, proposed_text = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (seam["status"], seam["proposed_text"], seam["id"]),
                )
                if cursor.rowcount != 1:
                    raise ValueError("Generation seam disappeared during review.")
            self._transition_in_connection(
                connection,
                int(run["id"]),
                allowed_from={PLOT_STATUS_AWAITING_SEAMS},
                to_status=PLOT_STATUS_READY,
                stage="generate_next_scene",
                updates={"seams_json": reviewed, "scene_plan_json": scene_plan},
            )


def _validate_scene_plan(plan: dict[str, Any]) -> None:
    chapters = plan.get("chapters")
    if not isinstance(chapters, list) or not chapters:
        raise ValueError("AI scene plan must contain chapters.")
    for chapter in chapters:
        if not isinstance(chapter, dict) or not isinstance(chapter.get("scenes"), list):
            raise ValueError("Each planned chapter must contain scenes.")
        if not chapter["scenes"]:
            raise ValueError("Each planned chapter must contain at least one scene.")


def _state_issues(required: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": "return_state_mismatch",
            "field": key,
            "expected": expected,
            "actual": actual.get(key),
        }
        for key, expected in required.items()
        if actual.get(key) != expected
    ]


def _seam_contribution(seam: dict[str, Any]) -> str:
    if seam.get("status") != "confirmed":
        return ""
    proposed = str(seam.get("proposed_text") or "")
    operation = seam.get("operation")
    if operation == "keep":
        return ""
    if operation in {"insert_before", "insert_after", "replace_range"}:
        return proposed
    raise ValueError("Unsupported seam operation.")


def _apply_branch_seam_text(
    scenes: list[dict[str, Any]], seams: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    confirmed = [seam for seam in seams if seam.get("status") == "confirmed"]
    entry = next((item for item in confirmed if item.get("seam_kind") == "entry"), None)
    returned = next((item for item in confirmed if item.get("seam_kind") == "return"), None)
    if entry is not None:
        scenes[0]["text"] = _seam_contribution(entry) + scenes[0]["text"]
    if returned is not None:
        scenes[-1]["text"] = scenes[-1]["text"] + _seam_contribution(returned)
    return scenes


def _compose_insert_between(
    original: str,
    insert_offset: int,
    generated: str,
    seams: list[dict[str, Any]],
) -> str:
    if not 0 <= insert_offset <= len(original):
        raise ValueError("Insert offset is outside the source text.")
    entry_text, return_text = _bounded_seam_text(seams)
    return (
        original[:insert_offset]
        + entry_text
        + generated
        + return_text
        + original[insert_offset:]
    )


def _compose_replace_range(
    original: str,
    start_offset: int,
    end_offset: int,
    generated: str,
    seams: list[dict[str, Any]],
) -> str:
    if not 0 <= start_offset <= end_offset <= len(original):
        raise ValueError("Replacement range is outside the source text.")
    entry_text, return_text = _bounded_seam_text(seams)
    return (
        original[:start_offset]
        + entry_text
        + generated
        + return_text
        + original[end_offset:]
    )


def _bounded_seam_text(seams: list[dict[str, Any]]) -> tuple[str, str]:
    confirmed = [seam for seam in seams if seam.get("status") == "confirmed"]
    entry = next((item for item in confirmed if item.get("seam_kind") == "entry"), None)
    returned = next((item for item in confirmed if item.get("seam_kind") == "return"), None)
    return (
        _seam_contribution(entry) if entry is not None else "",
        _seam_contribution(returned) if returned is not None else "",
    )
