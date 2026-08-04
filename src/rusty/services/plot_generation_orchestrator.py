from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.branch_service import BranchService
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
    ) -> dict[str, Any]:
        required_kind, topology, needs_return = self._validate_mode(
            project_id, generation_mode, return_anchor
        )
        del required_kind
        if range_operation not in {"insert_between", "replace_range"}:
            raise ValueError(f"Unsupported range operation: {range_operation}")
        if generation_mode != "bounded_insert" and range_operation != "insert_between":
            raise ValueError("range_operation only applies to bounded_insert runs.")
        context = self.contexts.compile_plot_generation_context(
            project_id=project_id,
            start_anchor=start_anchor,
            return_anchor=return_anchor,
            parent_branch_id=parent_branch_id,
            user_direction=user_direction,
            selected_character_ids=selected_character_ids or [],
            selected_material_ids=selected_material_ids or [],
            style_profile_id=style_profile_id,
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
                    style_profile_id
                    , range_operation
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    "blocked" if planning_issues else "awaiting_skeleton",
                    "confirm_target_skeleton",
                    user_direction,
                    json.dumps(selected_character_ids or []),
                    json.dumps(selected_material_ids or []),
                    style_profile_id,
                    range_operation,
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    def confirm_target_skeleton(
        self, run_id: int, target_skeleton: dict[str, Any]
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] == "blocked":
            raise ValueError("Blocked plot planning must be revised before confirmation.")
        skeleton = validate_structured_skeleton(target_skeleton)
        if run["generation_mode"] == "fork_and_rejoin":
            issues = _state_issues(
                run["required_return_state"], skeleton["required_end_state"]
            )
            if issues:
                self._update_run(
                    run_id,
                    status="blocked",
                    stage="confirm_target_skeleton",
                    issues_json=issues,
                    target_skeleton_json=skeleton,
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
        self._update_run(
            run_id,
            status="awaiting_seams",
            stage="confirm_seams",
            target_skeleton_json=skeleton,
            seams_json=seams,
            issues_json=[],
        )
        return self.get_run(run_id)

    def confirm_seams(
        self,
        run_id: int,
        reviews: list[dict[str, Any]],
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        reviewed = []
        stored_by_id = {int(item["id"]): item for item in self._stored_seams(run)}
        validated: list[tuple[dict[str, Any], dict[str, Any], dict[str, Any]]] = []
        for review in reviews:
            decision = str(review.get("decision") or "")
            if decision not in {"confirmed", "rejected"}:
                raise ValueError("All generation seams must be explicitly reviewed.")
            seam_id = int(review.get("seam_id") or 0)
            if seam_id not in stored_by_id:
                raise ValueError("Generation seam does not belong to this run.")
            current_source = self._resolve_seam_source(run, stored_by_id[seam_id])
            if (
                decision == "confirmed"
                and current_source["source_hash"] != stored_by_id[seam_id]["source_hash"]
            ):
                raise ValueError("Generation seam source hash mismatch.")
            validated.append((review, stored_by_id[seam_id], current_source))
        for review, stored, current_source in validated:
            decision = str(review["decision"])
            reviewed.append(
                self._review_stored_seam(
                    run,
                    int(stored["id"]),
                    decision=decision,
                    current_source_text=current_source["text"],
                    proposed_text=(
                        str(review["proposed_text"])
                        if review.get("proposed_text") is not None
                        else str(stored.get("proposed_text") or "")
                    ),
                )
            )
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
        self._update_run(
            run_id,
            status="ready",
            stage="generate_next_scene",
            seams_json=reviewed,
            scene_plan_json=scene_plan,
        )
        return self.get_run(run_id)

    def execute(self, run_id: int, *, max_scenes: int | None = None) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {"ready", "blocked"}:
            raise ValueError("Target skeleton and seams must be confirmed before generation.")
        generated: list[dict[str, Any]] = []
        generated_chapters: list[dict[str, Any]] = []
        ledger = dict(run["start_state"])
        count = 0
        for chapter in run["scene_plan"]["chapters"]:
            chapter_result = {
                "title": chapter["title"],
                "summary": chapter.get("summary", ""),
                "facts_before": dict(ledger),
                "scenes": [],
            }
            for scene in chapter["scenes"]:
                if max_scenes is not None and count >= max_scenes:
                    break
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
                            generated[-1]["text"] if generated else ""
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
                ledger = facts_after
                scene_result = {
                    "title": str(scene.get("title") or ""),
                    "text": text,
                    "facts_after": facts_after,
                }
                generated.append(scene_result)
                chapter_result["scenes"].append(scene_result)
                count += 1
            chapter_result["facts_after"] = dict(ledger)
            if chapter_result["scenes"]:
                generated_chapters.append(chapter_result)
        chapters = generated_chapters
        if not generated:
            raise ValueError("Plot generation must produce at least one scene.")
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
        issues.extend(_state_issues(run["required_return_state"], final_state))
        if issues:
            self._update_run(
                run_id,
                status="blocked",
                stage="consistency_check",
                issues_json=issues,
                fact_ledger_json=ledger,
            )
            return self.get_run(run_id)

        generated = _apply_branch_seam_text(generated, run["seams"])
        if run["output_topology"] == "branch":
            saved_chapters = []
            for chapter in chapters:
                saved_chapter = self.branches.create_chapter(
                    int(run["branch_id"]),
                    title=chapter["title"],
                    summary=chapter["summary"],
                    facts_before=chapter["facts_before"],
                    facts_after=chapter["facts_after"],
                )
                saved_scenes = [
                    self.branches.save_scene(
                        int(run["branch_id"]),
                        branch_chapter_id=int(saved_chapter["id"]),
                        title=scene["title"],
                        generated_text=scene["text"],
                        facts_after=scene["facts_after"],
                    )
                    for scene in chapter["scenes"]
                ]
                saved_chapters.append({**saved_chapter, "scenes": saved_scenes})
            result = {"branch_id": run["branch_id"], "chapters": saved_chapters}
        else:
            start = run["start_anchor"]
            end = run["return_anchor"]
            if start.get("chapter_id") != end.get("chapter_id"):
                raise ValueError("bounded_insert anchors must belong to the same chapter.")
            chapter = self.projects.get_chapter(int(start["chapter_id"]))
            if chapter is None:
                raise FileNotFoundError("Bounded insert chapter not found.")
            inserted = "\n\n".join(scene["text"] for scene in generated)
            if run["range_operation"] == "replace_range":
                rewritten = _compose_replace_range(
                    chapter.original_text,
                    int(start["text_offset"]),
                    int(end["text_offset"]),
                    inserted,
                    run["seams"],
                )
            else:
                rewritten = _compose_insert_between(
                    chapter.original_text,
                    int(start["text_offset"]),
                    inserted,
                    run["seams"],
                )
            self.projects.save_chapter_rewrite(chapter.id, rewritten)
            result = {"chapter_id": chapter.id, "rewritten_text": rewritten}
        self._update_run(
            run_id,
            status="completed",
            stage="complete",
            result_json=result,
            issues_json=[],
            fact_ledger_json=ledger,
        )
        return self.get_run(run_id)

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

    def _update_run(self, run_id: int, **values: Any) -> None:
        assignments = []
        parameters = []
        for key, value in values.items():
            assignments.append(f"{key} = ?")
            parameters.append(
                json.dumps(value, ensure_ascii=False)
                if key.endswith("_json")
                else value
            )
        parameters.append(run_id)
        with session(self.database_path) as connection:
            connection.execute(
                f"UPDATE plot_generation_runs SET {', '.join(assignments)}, "
                "updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                parameters,
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
