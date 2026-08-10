from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.context_service import ContextService
from rusty.services.chapter_version_service import ChapterVersionService, SourceVersionConflict
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.shared_analysis_service import SkeletonExtractionService
from rusty.services.structured_skeleton import validate_structured_skeleton
from rusty.services.workflow_ai import WorkflowAI
from rusty.services.rewrite_version_map_service import RewriteVersionMapService


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
        self.chapter_versions = ChapterVersionService(self.database_path)
        self.contexts = ContextService(self.database_path)
        self.skeletons = SkeletonExtractionService(self.database_path)
        self.rewrite_maps = RewriteVersionMapService(self.database_path)
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def plan(
        self,
        *,
        project_id: int,
        chapter_id: int,
        source_skeleton: dict[str, Any],
        source_skeleton_version_id: int | None = None,
        preservation_policy: dict[str, Any],
        style_profile_id: int | None = None,
        user_direction: str = "",
        source_selection: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        chapter = self.projects.get_chapter(chapter_id)
        if project is None or project.project_kind != "rewrite":
            raise ValueError("prose_rewrite requires a rewrite project.")
        if chapter is None or chapter.project_id != project_id:
            raise FileNotFoundError(f"Chapter not found in project: {chapter_id}")
        source = validate_structured_skeleton(source_skeleton)
        chapter_source = self.chapter_versions.resolve_chapter_source(
            chapter_id, source_selection
        )
        resolved_skeleton_version_id = source_skeleton_version_id
        if source_skeleton_version_id is not None:
            if chapter_source.source_version_id is not None:
                structure = self.rewrite_maps.get_rewrite_structure(
                    chapter_source.source_version_id
                )
            else:
                structure = self.rewrite_maps.get_original_structure(chapter_id)
            if structure is None:
                raise ValueError(
                    "Selected chapter source has no reliable structured skeleton."
                )
            if source_skeleton_version_id != int(structure["skeleton_version_id"]):
                raise ValueError("Source skeleton does not belong to the selected chapter version.")
            if structure["structured"] != source:
                raise ValueError("Source text and source skeleton are not the same version snapshot.")
        source_map_hash = (
            self.rewrite_maps.map_hash(chapter_source.source_version_id)
            if chapter_source.source_version_id is not None
            else chapter_source.content_hash
        )
        unknown = set(preservation_policy).difference(
            PRESERVATION_FIELDS | {"locked_node_ids"}
        )
        if unknown:
            raise ValueError(f"Unknown preservation policy fields: {sorted(unknown)}")
        proposed = self.ai.generate_json(
            project_id=project_id,
            stage="prose_rewrite_plan",
            payload={
                "source_text": chapter_source.text,
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
                    preservation_policy_json, target_skeleton_json, rewrite_plan_json,
                    source_base_kind, source_base_version_id, source_hash,
                    source_text_snapshot, require_source_head_match,
                    expected_source_head_version_id, source_map_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                            "source_skeleton_version_id": resolved_skeleton_version_id,
                        },
                        ensure_ascii=False,
                    ),
                    chapter_source.source_kind,
                    chapter_source.source_version_id,
                    chapter_source.content_hash,
                    chapter_source.text,
                    1 if chapter_source.require_head_match else 0,
                    chapter_source.expected_head_version_id,
                    source_map_hash,
                ),
            )
        return self.get_run(int(cursor.lastrowid))

    def execute(self, run_id: int, *, auto_repair: bool = True) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] != "planned":
            raise ValueError("Prose rewrite run is not ready to execute.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE prose_rewrite_runs SET status = 'generating', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'planned'
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Prose rewrite run is not ready to execute.")
        try:
            generated = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="prose_rewrite_generate",
                payload={
                    "source_text": run["source_text_snapshot"],
                    "target_skeleton": run["target_skeleton"],
                    "preservation_policy": run["preservation_policy"],
                    "rewrite_plan": run["rewrite_plan"],
                },
                output_contract='{"rewritten_text":str}',
            )
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise
        rewritten_text = generated.get("rewritten_text")
        if not isinstance(rewritten_text, str) or not rewritten_text.strip():
            exc = ValueError("AI prose rewrite returned empty text.")
            self._mark_failed(run_id, exc)
            raise exc
        try:
            observed = self.skeletons.extract_from_text(
                project_id=int(run["project_id"]),
                text=rewritten_text,
                workflow_ai=self.ai,
                expected_skeleton=run["target_skeleton"],
            )
            observed = self.rewrite_maps.normalize_observed_skeleton_ids(
                run["target_skeleton"], observed, 0
            )
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise
        issues = compare_skeletons(
            run["target_skeleton"], observed, run["preservation_policy"]
        )
        if issues and auto_repair:
            try:
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
                    observed = self.rewrite_maps.normalize_observed_skeleton_ids(
                        run["target_skeleton"], observed, 0
                    )
                    issues = compare_skeletons(
                        run["target_skeleton"], observed, run["preservation_policy"]
                    )
            except Exception as exc:
                self._mark_failed(run_id, exc)
                raise
        if issues:
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE prose_rewrite_runs
                    SET rewritten_text = ?, issues_json = ?, status = 'blocked',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'generating'
                    """,
                    (rewritten_text, json.dumps(issues, ensure_ascii=False), run_id),
                )
            return self.get_run(run_id)
        try:
            with session(self.database_path) as connection:
                locked = connection.execute(
                    "UPDATE prose_rewrite_runs SET updated_at = updated_at WHERE id = ? AND status = 'generating'",
                    (run_id,),
                )
                if locked.rowcount != 1:
                    raise ValueError("Prose rewrite run is no longer generating.")
                if run.get("source_base_version_id") is not None:
                    self.rewrite_maps.validate_map_hash(
                        int(run["source_base_version_id"]),
                        str(run["source_map_hash"]),
                    )
                source = self.chapter_versions.resolve_chapter_source(
                    int(run["chapter_id"]),
                    (
                        {"kind": "rewrite_version", "version_id": int(run["source_base_version_id"])}
                        if run.get("source_base_version_id") is not None
                        else {"kind": "original"}
                    ),
                    connection=connection,
                )
                version = self.chapter_versions.append_chapter_rewrite_version(
                    connection,
                    chapter_id=int(run["chapter_id"]),
                    rewritten_text=rewritten_text,
                    source_operation="prose_rewrite",
                    source_run_id=run_id,
                    source_base_kind=str(run["source_base_kind"]),
                    source_base_version_id=run.get("source_base_version_id"),
                    source_hash=str(run["source_hash"]),
                    facts_before=source.facts_before,
                    facts_after=source.facts_after,
                    require_head_match=bool(run["require_source_head_match"]),
                    expected_head_version_id=run.get(
                        "expected_source_head_version_id"
                    ),
                    fact_chain_status="consistent",
                    mapping_strategy="structural",
                    source_skeleton=run["source_skeleton"],
                    observed_skeleton=observed,
                )
                connection.execute(
                    """
                    UPDATE prose_rewrite_runs
                    SET rewritten_text = ?, issues_json = '[]', status = 'completed',
                        result_version_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'generating'
                    """,
                    (rewritten_text, version["id"], run_id),
                )
        except SourceVersionConflict as conflict:
            with session(self.database_path) as connection:
                connection.execute(
                    """
                    UPDATE prose_rewrite_runs
                    SET status = 'failed', issues_json = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND status = 'generating'
                    """,
                    (
                        json.dumps([{
                            "type": "source_version_conflict",
                            "expected_version_id": conflict.expected_version_id,
                            "current_version_id": conflict.current_version_id,
                        }], ensure_ascii=False),
                        run_id,
                    ),
                )
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise
        return self.get_run(run_id)

    def cancel(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE prose_rewrite_runs
                SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('planned', 'generating', 'blocked', 'failed')
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Prose rewrite run cannot be cancelled in its current state.")
        return self.get_run(run_id)

    def retry(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE prose_rewrite_runs
                SET status = 'planned', issues_json = '[]', rewritten_text = NULL,
                    generation_attempt = generation_attempt + 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('blocked', 'failed')
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Prose rewrite run cannot be retried in its current state.")
        return self.get_run(run_id)

    def _mark_failed(self, run_id: int, exc: Exception) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE prose_rewrite_runs
                SET status = 'failed', issues_json = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'generating'
                """,
                (json.dumps([{"type": "technical_failure", "message": str(exc)}]), run_id),
            )

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
        result["source_skeleton_version_id"] = result["rewrite_plan"].get(
            "source_skeleton_version_id"
        )
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
