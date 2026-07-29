from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.structured_skeleton import validate_structured_skeleton


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
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.projects = ProjectService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def plan(
        self,
        *,
        project_id: int,
        chapter_id: int,
        source_skeleton: dict[str, Any],
        preservation_policy: dict[str, Any],
        target_skeleton: dict[str, Any],
        rewrite_plan: dict[str, Any],
    ) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        chapter = self.projects.get_chapter(chapter_id)
        if project is None or project.project_kind != "rewrite":
            raise ValueError("prose_rewrite requires a rewrite project.")
        if chapter is None or chapter.project_id != project_id:
            raise FileNotFoundError(f"Chapter not found in project: {chapter_id}")
        source = validate_structured_skeleton(source_skeleton)
        target = validate_structured_skeleton(target_skeleton)
        unknown = set(preservation_policy).difference(PRESERVATION_FIELDS | {"locked_node_ids"})
        if unknown:
            raise ValueError(f"Unknown preservation policy fields: {sorted(unknown)}")
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
                    json.dumps(rewrite_plan, ensure_ascii=False),
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    def execute(
        self,
        run_id: int,
        *,
        rewritten_text: str,
        observed_skeleton: dict[str, Any],
    ) -> dict[str, Any]:
        run = self.get_run(run_id)
        observed = validate_structured_skeleton(observed_skeleton)
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
                (rewritten_text, json.dumps(issues, ensure_ascii=False), status, run_id),
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
                issues.append(
                    {"type": f"{policy_key}_changed", "node_id": node_id}
                )
    if policy.get("causal_links", True) and expected["causal_links"] != actual["causal_links"]:
        issues.append({"type": "causal_links_changed"})
    if policy.get("foreshadowing", True) and expected["foreshadowing"] != actual["foreshadowing"]:
        issues.append({"type": "foreshadowing_changed"})
    for key in ("required_start_state", "required_end_state"):
        if policy.get(key, True) and expected[key] != actual[key]:
            issues.append({"type": f"{key}_changed", "expected": expected[key], "actual": actual[key]})
    return issues
