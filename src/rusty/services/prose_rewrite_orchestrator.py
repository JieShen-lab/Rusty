from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.context_service import ContextService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.shared_analysis_service import SkeletonExtractionService
from rusty.services.structured_skeleton import validate_structured_skeleton
from rusty.services.workflow_ai import WorkflowAI


PRESERVATION_FIELDS = {
    "events",
    "event_order",
    "character_motivations",
    "behavior_results",
    "knowledge_reveal_order",
    "causal_links",
    "foreshadowing",
    "required_start_state",
    "required_end_state",
}


class ProseRewriteOrchestrator:
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
        self.contexts = ContextService(self.database_path)
        self.skeletons = SkeletonExtractionService(self.database_path)
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def plan(
        self,
        *,
        project_id: int,
        chapter_id: int,
        source_skeleton: dict[str, Any],
        preservation_policy: dict[str, Any],
        style_profile_id: int | None = None,
        user_direction: str = "",
    ) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        chapter = self.projects.get_chapter(chapter_id)
        if project is None or project.project_kind != "rewrite":
            raise ValueError("prose_rewrite requires a rewrite project.")
        if chapter is None or chapter.project_id != project_id:
            raise FileNotFoundError(f"Chapter not found in project: {chapter_id}")
        source = validate_structured_skeleton(source_skeleton)
        unknown = set(preservation_policy).difference(
            PRESERVATION_FIELDS | {"locked_node_ids"}
        )
        if unknown:
            raise ValueError(f"Unknown preservation policy fields: {sorted(unknown)}")
        proposed = self.ai.generate_json(
            project_id=project_id,
            stage="prose_rewrite_plan",
            payload={
                "source_text": chapter.original_text,
                "source_skeleton": source,
                "preservation_policy": preservation_policy,
                "style_profile_id": style_profile_id,
                "user_direction": user_direction,
            },
            output_contract='{"target_skeleton":StructuredSkeleton,"rewrite_plan":object}',
        )
        target = validate_structured_skeleton(proposed.get("target_skeleton"))
        rewrite_plan = proposed.get("rewrite_plan")
        if not isinstance(rewrite_plan, dict):
            raise ValueError("AI rewrite plan must be an object.")
        issues = compare_skeletons(source, target, preservation_policy)
        if issues:
            raise ValueError(f"Target skeleton violates preservation policy: {issues}")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO prose_rewrite_runs (
                    project_id, chapter_id, source_skeleton_json,
                    preservation_policy_json, target_skeleton_json, rewrite_plan_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    chapter_id,
                    json.dumps(source, ensure_ascii=False),
                    json.dumps(preservation_policy, ensure_ascii=False),
                    json.dumps(target, ensure_ascii=False),
                    json.dumps(
                        {
                            **rewrite_plan,
                            "style_profile_id": style_profile_id,
                            "user_direction": user_direction,
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    def execute(self, run_id: int, *, auto_repair: bool = True) -> dict[str, Any]:
        run = self.get_run(run_id)
        chapter = self.projects.get_chapter(int(run["chapter_id"]))
        if chapter is None:
            raise FileNotFoundError("Rewrite source chapter not found.")
        generated = self.ai.generate_json(
            project_id=int(run["project_id"]),
            stage="prose_rewrite_generate",
            payload={
                "source_text": chapter.original_text,
                "target_skeleton": run["target_skeleton"],
                "preservation_policy": run["preservation_policy"],
                "rewrite_plan": run["rewrite_plan"],
            },
            output_contract='{"rewritten_text":str}',
        )
        rewritten_text = generated.get("rewritten_text")
        if not isinstance(rewritten_text, str) or not rewritten_text.strip():
            raise ValueError("AI prose rewrite returned empty text.")
        observed = self.skeletons.extract_from_text(
            project_id=int(run["project_id"]),
            text=rewritten_text,
            workflow_ai=self.ai,
            expected_skeleton=run["target_skeleton"],
        )
        issues = compare_skeletons(
            run["target_skeleton"], observed, run["preservation_policy"]
        )
        if issues and auto_repair:
            repaired = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="prose_rewrite_repair",
                payload={
                    "rewritten_text": rewritten_text,
                    "target_skeleton": run["target_skeleton"],
                    "issues": issues,
                },
                output_contract='{"rewritten_text":str}',
            )
            candidate = repaired.get("rewritten_text")
            if isinstance(candidate, str) and candidate.strip():
                rewritten_text = candidate
                observed = self.skeletons.extract_from_text(
                    project_id=int(run["project_id"]),
                    text=rewritten_text,
                    workflow_ai=self.ai,
                    expected_skeleton=run["target_skeleton"],
                )
                issues = compare_skeletons(
                    run["target_skeleton"], observed, run["preservation_policy"]
                )
        status = "blocked" if issues else "completed"
        if not issues:
            self.projects.save_chapter_rewrite(int(run["chapter_id"]), rewritten_text)
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE prose_rewrite_runs
                SET rewritten_text = ?, issues_json = ?, status = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    rewritten_text,
                    json.dumps(issues, ensure_ascii=False),
                    status,
                    run_id,
                ),
            )
        return self.get_run(run_id)

    def get_run(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM prose_rewrite_runs WHERE id = ?", (run_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Prose rewrite run not found: {run_id}")
        result = dict(row)
        for key in (
            "source_skeleton",
            "preservation_policy",
            "target_skeleton",
            "rewrite_plan",
            "issues",
        ):
            result[key] = json.loads(row[f"{key}_json"])
        return result

    def list_runs(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id FROM prose_rewrite_runs WHERE project_id = ? ORDER BY created_at DESC, id DESC",
                (project_id,),
            ).fetchall()
        return [self.get_run(int(row["id"])) for row in rows]


def compare_skeletons(
    expected: dict[str, Any],
    actual: dict[str, Any],
    policy: dict[str, Any],
) -> list[dict[str, Any]]:
    expected_nodes = expected["event_nodes"]
    actual_nodes = actual["event_nodes"]
    expected_by_id = {node["id"]: node for node in expected_nodes}
    actual_by_id = {node["id"]: node for node in actual_nodes}
    issues: list[dict[str, Any]] = []
    preserve_events = policy.get("events", True)
    locked = set(policy.get("locked_node_ids", [])) | {
        node["id"] for node in expected_nodes if node["locked"]
    }
    for node_id in expected_by_id:
        if node_id not in actual_by_id and (preserve_events or node_id in locked):
            issues.append({"type": "missing_event", "node_id": node_id})
    if preserve_events:
        for node_id in actual_by_id.keys() - expected_by_id.keys():
            issues.append({"type": "added_key_event", "node_id": node_id})
    if policy.get("event_order", True):
        expected_order = [node["id"] for node in expected_nodes if node["id"] in actual_by_id]
        actual_order = [node["id"] for node in actual_nodes if node["id"] in expected_by_id]
        if expected_order != actual_order:
            issues.append(
                {
                    "type": "event_order_changed",
                    "expected": expected_order,
                    "actual": actual_order,
                }
            )
    comparisons = {
        "character_motivations": "motivation",
        "behavior_results": "effects",
        "knowledge_reveal_order": "knowledge_changes",
    }
    for policy_key, node_key in comparisons.items():
        if not policy.get(policy_key, True):
            continue
        for node_id in expected_by_id.keys() & actual_by_id.keys():
            if expected_by_id[node_id].get(node_key) != actual_by_id[node_id].get(node_key):
                issues.append({"type": f"{policy_key}_changed", "node_id": node_id})
    if policy.get("causal_links", True) and expected["causal_links"] != actual["causal_links"]:
        issues.append({"type": "causal_links_changed"})
    if policy.get("foreshadowing", True) and expected["foreshadowing"] != actual["foreshadowing"]:
        issues.append({"type": "foreshadowing_changed"})
    for key in ("required_start_state", "required_end_state"):
        if policy.get(key, True) and expected[key] != actual[key]:
            issues.append(
                {"type": f"{key}_changed", "expected": expected[key], "actual": actual[key]}
            )
    return issues
