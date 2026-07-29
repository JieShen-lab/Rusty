from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.branch_service import BranchService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.structured_skeleton import validate_structured_skeleton


GENERATION_MODES = {
    "bounded_insert": ("rewrite", "in_place", True),
    "open_continuation": ("branch", "branch", False),
    "fork": ("branch", "branch", False),
    "fork_and_rejoin": ("branch", "branch", True),
}
BRANCH_CONTEXT_KEYS = (
    "start_anchor_context",
    "previous_text_tail",
    "start_state",
    "character_states",
    "fact_ledger",
    "open_threads",
    "foreshadowing",
    "global_skeleton",
    "user_direction",
    "material_context",
    "style_profile",
    "previous_generated_scene",
    "return_state_constraints",
)


class PlotGenerationOrchestrator:
    """One persisted orchestration path for in-place inserts and branch plots."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.projects = ProjectService(self.database_path)
        self.branches = BranchService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def start(
        self,
        *,
        project_id: int,
        generation_mode: str,
        start_anchor: dict[str, Any],
        target_skeleton: dict[str, Any],
        context: dict[str, Any],
        return_anchor: dict[str, Any] | None = None,
        required_return_state: dict[str, Any] | None = None,
        parent_branch_id: int | None = None,
        branch_name: str = "Generated branch",
    ) -> dict[str, Any]:
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
        skeleton = validate_structured_skeleton(target_skeleton)
        normalized_context = self.compile_generation_context(topology, context)
        branch_id = None
        if topology == "branch":
            branch = self.branches.create_branch(
                project_id=project_id,
                parent_branch_id=parent_branch_id,
                name=branch_name,
                branch_mode=generation_mode,
                start_anchor=start_anchor,
                return_anchor=return_anchor,
            )
            branch_id = int(branch["id"])
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO plot_generation_runs (
                    project_id, branch_id, generation_mode, output_topology,
                    start_anchor_json, return_anchor_json, start_state_json,
                    required_return_state_json, target_skeleton_json, context_json,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'awaiting_seams')
                """,
                (
                    project_id,
                    branch_id,
                    generation_mode,
                    topology,
                    json.dumps(start_anchor, ensure_ascii=False),
                    json.dumps(return_anchor, ensure_ascii=False) if return_anchor else None,
                    json.dumps(normalized_context.get("start_state", {}), ensure_ascii=False),
                    json.dumps(required_return_state or {}, ensure_ascii=False),
                    json.dumps(skeleton, ensure_ascii=False),
                    json.dumps(normalized_context, ensure_ascii=False),
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    @staticmethod
    def compile_generation_context(topology: str, context: dict[str, Any]) -> dict[str, Any]:
        if topology == "in_place":
            if not context.get("rewrite_source_context"):
                raise ValueError("bounded_insert requires rewrite_source_context.")
            return dict(context)
        missing = [key for key in BRANCH_CONTEXT_KEYS if key not in context]
        if missing:
            raise ValueError(f"Branch generation context is missing: {', '.join(missing)}")
        # Required blocks are copied whole. Budgeting may drop optional retrieval
        # elsewhere, but this boundary never truncates semantic state.
        return {key: context[key] for key in BRANCH_CONTEXT_KEYS}

    def confirm_seams(
        self, run_id: int, seams: list[dict[str, Any]], *, current_source_text: str
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        actual_hash = hashlib.sha256(current_source_text.encode("utf-8")).hexdigest()
        normalized = []
        for seam in seams:
            if seam.get("status") != "confirmed":
                raise ValueError("All generation seams must be explicitly confirmed.")
            if seam.get("source_hash") != actual_hash:
                raise ValueError("Generation seam source hash mismatch.")
            normalized.append(dict(seam))
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE plot_generation_runs
                SET seams_json = ?, status = 'ready', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(normalized, ensure_ascii=False), run_id),
            )
        return self.get_run(run_id)

    def execute(
        self,
        run_id: int,
        *,
        generated_scenes: list[dict[str, Any]],
        final_state: dict[str, Any],
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] not in {"ready", "blocked"}:
            raise ValueError("Target skeleton and seams must be confirmed before generation.")
        issues = _state_issues(run["required_return_state"], final_state)
        if issues:
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE plot_generation_runs
                    SET status = 'blocked', issues_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(issues, ensure_ascii=False), run_id),
                )
            return self.get_run(run_id)
        if not generated_scenes:
            raise ValueError("Plot generation must produce at least one scene.")

        if run["output_topology"] == "branch":
            saved = [
                self.branches.save_scene(
                    int(run["branch_id"]),
                    title=str(scene.get("title") or ""),
                    generated_text=str(scene.get("text") or ""),
                    facts_after=scene.get("facts_after") or final_state,
                )
                for scene in generated_scenes
            ]
            result = {"branch_id": run["branch_id"], "scenes": saved}
        else:
            start = run["start_anchor"]
            end = run["return_anchor"]
            if start.get("chapter_id") != end.get("chapter_id"):
                raise ValueError("bounded_insert anchors must belong to the same chapter.")
            chapter_id = int(start["chapter_id"])
            chapter = self.projects.get_chapter(chapter_id)
            if chapter is None:
                raise FileNotFoundError(f"Chapter not found: {chapter_id}")
            start_offset = int(start["text_offset"])
            end_offset = int(end["text_offset"])
            inserted = "\n\n".join(str(scene.get("text") or "") for scene in generated_scenes)
            rewritten = chapter.original_text[:start_offset] + inserted + chapter.original_text[end_offset:]
            self.projects.save_chapter_rewrite(chapter_id, rewritten)
            result = {
                "chapter_id": chapter_id,
                "rewrite_version": "chapter_rewrite",
                "rewritten_text": rewritten,
            }
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE plot_generation_runs
                SET status = 'completed', result_json = ?, issues_json = '[]',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(result, ensure_ascii=False), run_id),
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
        for key in (
            "start_anchor",
            "return_anchor",
            "start_state",
            "required_return_state",
            "target_skeleton",
            "context",
            "seams",
            "issues",
            "result",
        ):
            column = f"{key}_json"
            raw = row[column] if column in row.keys() else None
            result[key] = json.loads(raw) if raw else (None if key == "return_anchor" else {})
        return result


def _state_issues(required: dict[str, Any], actual: dict[str, Any]) -> list[dict[str, Any]]:
    issues = []
    for key, expected in required.items():
        if actual.get(key) != expected:
            issues.append(
                {
                    "type": "return_state_mismatch",
                    "field": key,
                    "expected": expected,
                    "actual": actual.get(key),
                }
            )
    return issues
