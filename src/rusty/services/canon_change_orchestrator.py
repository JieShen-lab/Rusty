from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.content_hash import hash_text
from rusty.db import initialize_database, session
from rusty.services.branch_service import BranchService
from rusty.services.chapter_version_service import ChapterVersionService, SourceVersionConflict
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.workflow_ai import WorkflowAI
from rusty.services.rewrite_version_map_service import RewriteVersionMapService


IMPACT_TYPES = {
    "direct_fact",
    "action_consequence",
    "physical_symptom",
    "dialogue_reference",
    "other_character_reaction",
    "treatment",
    "possession_or_equipment",
    "movement_constraint",
    "knowledge_state",
    "relationship_effect",
    "recovery_progress",
    "foreshadowing",
}


class CanonChangeOrchestrator:
    """Two-stage semantic impact scan with atomic reviewed-patch application."""

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
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
        self.rewrite_maps = RewriteVersionMapService(self.database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def scan(
        self,
        *,
        project_id: int,
        old_fact: dict[str, Any],
        new_fact: dict[str, Any],
        effective_order: int,
        branch_id: int | None = None,
        source: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        if project.project_kind == "branch" and branch_id is None:
            raise ValueError("Canon changes in branch projects require a target branch.")
        with session(self.database_path) as connection:
            segments = self._segments(
                connection, project_id, branch_id, effective_order, source=source
            )
        candidates = _candidate_segments(segments, old_fact)
        analyzed: list[dict[str, Any]] = []
        for segment in candidates:
            response = self.ai.generate_json(
                project_id=project_id,
                stage="canon_semantic_impact",
                payload={
                    "old_fact": old_fact,
                    "new_fact": new_fact,
                    "candidate": segment,
                },
                output_contract=(
                    '{"impacts":[{"source_range":{"start":int,"end":int},'
                    '"original_text":str,"replacement_text":str,"impact_type":str,'
                    '"reason":str,"confidence":number,"evidence":array,'
                    '"requires_confirmation":bool}]}'
                ),
            )
            impacts = response.get("impacts")
            if not isinstance(impacts, list):
                raise ValueError("Canon semantic analysis must return impacts.")
            for impact in impacts:
                analyzed.append(_validate_impact(segment, impact))

        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO canon_change_runs (
                    project_id, branch_id, old_fact_json, new_fact_json,
                    effective_order, status, source_snapshots_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    branch_id,
                    json.dumps(old_fact, ensure_ascii=False),
                    json.dumps(new_fact, ensure_ascii=False),
                    effective_order,
                    "ready_to_apply" if not analyzed else "reviewing",
                    json.dumps(
                        {
                            f"{segment['route_kind']}:{segment['target_id']}": {
                                "source_base_version_id": segment.get("source_base_version_id"),
                                "expected_source_head_version_id": segment.get(
                                    "expected_source_head_version_id"
                                ),
                                "source_hash": hash_text(str(segment["text"])),
                                "text": segment["text"],
                                "facts": segment.get("facts", {}),
                                "require_head_match": bool(segment.get("require_head_match", True)),
                                "source_map_hash": (
                                    self.rewrite_maps.map_hash(
                                        int(segment["source_base_version_id"])
                                    )
                                    if segment["route_kind"] == "chapter"
                                    and segment.get("source_base_version_id") is not None
                                    else hash_text(str(segment["text"]))
                                ),
                            }
                            for segment in segments
                        },
                        ensure_ascii=False,
                    ),
                ),
            )
            run_id = int(cursor.lastrowid)
            for impact in analyzed:
                connection.execute(
                    """
                    INSERT INTO canon_change_patches (
                        run_id, route_kind, target_id, source_range_json,
                        source_hash, original_text, replacement_text,
                        impact_type, reason, confidence, evidence_json,
                        requires_confirmation, source_base_version_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        impact["route_kind"],
                        impact["target_id"],
                        json.dumps(impact["source_range"], ensure_ascii=False),
                        hash_text(impact["original_text"]),
                        impact["original_text"],
                        impact["replacement_text"],
                        impact["impact_type"],
                        impact["reason"],
                        impact["confidence"],
                        json.dumps(impact["evidence"], ensure_ascii=False),
                        1 if impact["requires_confirmation"] else 0,
                        impact.get("source_base_version_id"),
                    ),
                )
        return self.get_run(run_id)

    def review_patch(
        self,
        patch_id: int,
        *,
        decision: str,
        replacement_text: str | None = None,
    ) -> dict[str, Any]:
        if decision not in {"accepted", "rejected", "edited", "skipped"}:
            raise ValueError("Unsupported patch review decision.")
        if decision == "edited" and not replacement_text:
            raise ValueError("Edited patches require replacement text.")
        with session(self.database_path) as connection:
            current = connection.execute(
                """
                SELECT p.*, r.status AS run_status
                FROM canon_change_patches p
                JOIN canon_change_runs r ON r.id = p.run_id
                WHERE p.id = ?
                """,
                (patch_id,),
            ).fetchone()
            if current is None:
                raise FileNotFoundError(f"Canon patch not found: {patch_id}")
            if current["run_status"] not in {"reviewing", "ready_to_apply"}:
                raise ValueError("Canon patches cannot be reviewed after the run is terminal.")
            cursor = connection.execute(
                """
                UPDATE canon_change_patches
                SET status = ?, replacement_text = COALESCE(?, replacement_text),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (decision, replacement_text, patch_id),
            )
            row = connection.execute(
                "SELECT * FROM canon_change_patches WHERE id = ?", (patch_id,)
            ).fetchone()
            remaining = connection.execute(
                "SELECT COUNT(*) FROM canon_change_patches WHERE run_id = (SELECT run_id FROM canon_change_patches WHERE id = ?) AND status = 'draft'",
                (patch_id,),
            ).fetchone()[0]
            connection.execute(
                """
                UPDATE canon_change_runs
                SET status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('reviewing', 'ready_to_apply')
                """,
                (
                    "ready_to_apply" if int(remaining) == 0 else "reviewing",
                    row["run_id"],
                ),
            )
        return self._patch(row)

    def apply(self, run_id: int) -> dict[str, Any]:
        run = self.get_run(run_id)
        if run["status"] != "ready_to_apply":
            raise ValueError("Canon change run is not ready to apply.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE canon_change_runs SET status = 'applying', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'ready_to_apply'
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Canon change run is not ready to apply.")
        run = self.get_run(run_id)
        selected = [
            patch for patch in run["patches"] if patch["status"] in {"accepted", "edited"}
        ]
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for patch in selected:
            grouped.setdefault((patch["route_kind"], patch["target_id"]), []).append(patch)

        projected: dict[tuple[str, int], str] = {}
        conflicts: list[dict[str, Any]] = []
        with session(self.database_path) as connection:
            for key, snapshot in run["source_snapshots"].items():
                route_kind, raw_target_id = key.split(":", 1)
                target_id = int(raw_target_id)
                current = self._current_text(connection, route_kind, target_id)
                current_version_id = self._current_version_id(
                    connection, route_kind, target_id
                )
                if (
                    route_kind == "chapter"
                    and snapshot.get("source_base_version_id") is not None
                ):
                    try:
                        self.rewrite_maps.validate_map_hash(
                            int(snapshot["source_base_version_id"]),
                            str(snapshot["source_map_hash"]),
                        )
                    except ValueError:
                        conflicts.append(
                            {
                                "type": "source_map_conflict",
                                "route_kind": route_kind,
                                "target_id": target_id,
                            }
                        )
                        continue
                if (
                    hash_text(current) != snapshot["source_hash"]
                    or current_version_id
                    != snapshot.get("expected_source_head_version_id")
                ):
                    conflicts.append(
                        {
                            "type": "source_version_conflict",
                            "route_kind": route_kind,
                            "target_id": target_id,
                            "source_base_version_id": snapshot.get("source_base_version_id"),
                        }
                    )
            for target, patches in grouped.items():
                current = self._current_text(connection, *target)
                ordered = sorted(patches, key=lambda item: item["source_range"]["start"])
                for previous, following in zip(ordered, ordered[1:]):
                    if previous["source_range"]["end"] > following["source_range"]["start"]:
                        conflicts.append(
                            {
                                "type": "overlapping_patches",
                                "patch_ids": [previous["id"], following["id"]],
                                "target_id": target[1],
                            }
                        )
                for patch in ordered:
                    bounds = patch["source_range"]
                    current_slice = current[bounds["start"] : bounds["end"]]
                    if hash_text(current_slice) != patch["source_hash"]:
                        conflicts.append(
                            {
                                "type": "source_hash_mismatch",
                                "patch_id": patch["id"],
                                "target_id": target[1],
                            }
                        )
                rewritten = current
                for patch in reversed(ordered):
                    bounds = patch["source_range"]
                    rewritten = (
                        rewritten[: bounds["start"]]
                        + patch["replacement_text"]
                        + rewritten[bounds["end"] :]
                    )
                projected[target] = rewritten
        if conflicts:
            self._mark_blocked(run_id, conflicts)
            return self.get_run(run_id)

        try:
            consistency = self.ai.generate_json(
                project_id=int(run["project_id"]),
                stage="canon_consistency_check",
                payload={
                    "old_fact": run["old_fact"],
                    "new_fact": run["new_fact"],
                    "projected_targets": [
                        {"route_kind": key[0], "target_id": key[1], "text": text}
                        for key, text in projected.items()
                    ],
                },
                output_contract='{"issues":array}',
            )
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise
        issues = consistency.get("issues")
        if not isinstance(issues, list):
            exc = ValueError("Canon consistency check must return issues.")
            self._mark_failed(run_id, exc)
            raise exc
        if issues:
            self._mark_blocked(run_id, issues)
            return self.get_run(run_id)

        ledger = {
            **run["fact_ledger"],
            str(run["old_fact"].get("attribute") or "fact"): run["new_fact"],
        }
        try:
            with session(self.database_path) as connection:
                locked = connection.execute(
                    "UPDATE canon_change_runs SET updated_at = updated_at WHERE id = ? AND status = 'applying'",
                    (run_id,),
                )
                if locked.rowcount != 1:
                    raise ValueError("Canon change run is no longer applying.")
                attribute = str(run["old_fact"].get("attribute") or "fact")
                result_versions: dict[tuple[str, int], int] = {}
                if run["branch_id"] is None:
                    for key, snapshot in run["source_snapshots"].items():
                        route_kind, raw_target_id = key.split(":", 1)
                        if route_kind != "chapter":
                            continue
                        target_id = int(raw_target_id)
                        facts = dict(snapshot.get("facts") or {})
                        facts[attribute] = run["new_fact"]
                        version = self.chapter_versions.append_chapter_rewrite_version(
                            connection,
                            chapter_id=target_id,
                            rewritten_text=projected.get(
                                (route_kind, target_id), str(snapshot["text"])
                            ),
                            source_operation="canon_change",
                            source_run_id=run_id,
                            source_base_kind=(
                                "rewrite_version"
                                if snapshot.get("source_base_version_id") is not None
                                else "original"
                            ),
                            source_base_version_id=snapshot.get("source_base_version_id"),
                            source_hash=str(snapshot["source_hash"]),
                            facts_before=dict(snapshot.get("facts") or {}),
                            facts_after=facts,
                            require_head_match=bool(
                                snapshot.get("require_head_match", True)
                            ),
                            expected_head_version_id=snapshot.get(
                                "expected_source_head_version_id"
                            ),
                            fact_chain_status="consistent",
                            mapping_strategy="transformed",
                            map_changes=[
                                {
                                    "start": int(patch["source_range"]["start"]),
                                    "end": int(patch["source_range"]["end"]),
                                    "replacement_length": len(
                                        str(patch["replacement_text"])
                                    ),
                                    # Reviewed Canon patches change a fact's
                                    # wording while retaining the mapped scene
                                    # or event identity.
                                    "preserve_semantic_identity": True,
                                }
                                for patch in grouped.get((route_kind, target_id), [])
                            ],
                            source_skeleton=self.rewrite_maps.resolve_structure(
                                connection,
                                chapter_id=target_id,
                                rewrite_version_id=snapshot.get(
                                    "source_base_version_id"
                                ),
                            ),
                        )
                        result_versions[(route_kind, target_id)] = int(version["id"])
                else:
                    updates = []
                    for key, snapshot in run["source_snapshots"].items():
                        route_kind, raw_target_id = key.split(":", 1)
                        if route_kind != "branch_scene":
                            continue
                        target_id = int(raw_target_id)
                        facts = dict(snapshot.get("facts") or {})
                        facts[attribute] = run["new_fact"]
                        updates.append(
                            {
                                "scene_id": target_id,
                                "text": projected.get(
                                    (route_kind, target_id), str(snapshot["text"])
                                ),
                                "facts_after": facts,
                            }
                        )
                    chain = BranchService.apply_canon_fact_chain(
                        connection,
                        branch_id=int(run["branch_id"]),
                        scene_updates=updates,
                    )
                    result_versions.update(
                        {
                            ("branch_scene", int(scene_id)): int(version_id)
                            for scene_id, version_id in chain["scene_version_ids"].items()
                        }
                    )
                connection.executemany(
                    """
                    UPDATE canon_change_patches
                    SET status = 'applied', result_version_id = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    [
                        (
                            result_versions.get(
                                (patch["route_kind"], int(patch["target_id"]))
                            ),
                            patch["id"],
                        )
                        for patch in selected
                    ],
                )
                connection.execute(
                    """
                    UPDATE canon_change_runs
                    SET fact_ledger_json = ?, consistency_issues_json = '[]',
                        status = 'applied', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (json.dumps(ledger, ensure_ascii=False), run_id),
                )
        except SourceVersionConflict as conflict:
            self._mark_blocked(
                run_id,
                [{
                    "type": "source_version_conflict",
                    "expected_version_id": conflict.expected_version_id,
                    "current_version_id": conflict.current_version_id,
                }],
            )
            return self.get_run(run_id)
        except Exception as exc:
            self._mark_failed(run_id, exc)
            raise
        return self.get_run(run_id)

    def cancel(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE canon_change_runs SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('scanning', 'reviewing', 'blocked', 'ready_to_apply', 'failed')
                """,
                (run_id,),
            )
            if cursor.rowcount != 1:
                raise ValueError("Canon change run cannot be cancelled in its current state.")
        return self.get_run(run_id)

    def _mark_blocked(self, run_id: int, issues: list[dict[str, Any]]) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE canon_change_runs
                SET consistency_issues_json = ?, status = 'blocked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status IN ('reviewing', 'ready_to_apply', 'applying')
                """,
                (json.dumps(issues, ensure_ascii=False), run_id),
            )

    def _mark_failed(self, run_id: int, exc: Exception) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE canon_change_runs
                SET consistency_issues_json = ?, status = 'failed',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND status = 'applying'
                """,
                (
                    json.dumps(
                        [{"type": "technical_failure", "message": str(exc)}],
                        ensure_ascii=False,
                    ),
                    run_id,
                ),
            )

    def get_run(self, run_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM canon_change_runs WHERE id = ?", (run_id,)
            ).fetchone()
            patches = connection.execute(
                """
                SELECT * FROM canon_change_patches
                WHERE run_id = ? ORDER BY target_id, json_extract(source_range_json, '$.start')
                """,
                (run_id,),
            ).fetchall()
        if row is None:
            raise FileNotFoundError(f"Canon change run not found: {run_id}")
        result = dict(row)
        for key in ("old_fact", "new_fact", "fact_ledger", "consistency_issues"):
            result[key] = json.loads(row[f"{key}_json"])
        result["source_snapshots"] = json.loads(row["source_snapshots_json"] or "{}")
        result["patches"] = [self._patch(patch) for patch in patches]
        return result

    def list_runs(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id FROM canon_change_runs WHERE project_id = ? ORDER BY created_at DESC, id DESC",
                (project_id,),
            ).fetchall()
        return [self.get_run(int(row["id"])) for row in rows]

    def _segments(
        self,
        connection,
        project_id: int,
        branch_id: int | None,
        effective_order: int,
        *,
        source: dict[str, Any] | None,
    ):
        if branch_id is not None:
            rows = connection.execute(
                """
                SELECT s.id, s.sequence_index, v.id AS source_base_version_id,
                       v.generated_text, v.facts_after_json
                FROM branch_scenes s
                JOIN branch_scene_versions v
                  ON v.branch_scene_id = s.id AND v.version = s.current_version
                JOIN story_branches b ON b.id = s.branch_id
                WHERE s.branch_id = ? AND b.project_id = ?
                  AND s.sequence_index >= ? AND s.deleted_at IS NULL
                ORDER BY s.sequence_index
                """,
                (branch_id, project_id, effective_order),
            ).fetchall()
            return [
                {
                    "route_kind": "branch_scene",
                    "target_id": int(row["id"]),
                    "text": row["generated_text"],
                    "facts": json.loads(row["facts_after_json"]),
                    "source_base_version_id": int(row["source_base_version_id"]),
                    "expected_source_head_version_id": int(
                        row["source_base_version_id"]
                    ),
                    "require_head_match": True,
                }
                for row in rows
            ]
        rows = connection.execute(
            """
            SELECT id
            FROM chapters
            WHERE project_id = ? AND chapter_index >= ?
            ORDER BY chapter_index
            """,
            (project_id, effective_order),
        ).fetchall()
        segments = []
        for row in rows:
            selection = source
            if source and source.get("kind") == "rewrite_version":
                version = self.chapter_versions.get_version(int(source["version_id"]), connection=connection)
                selection = source if int(version["chapter_id"]) == int(row["id"]) else {"kind": "current"}
            snapshot = self.chapter_versions.resolve_chapter_source(
                int(row["id"]), selection, connection=connection
            )
            segments.append(
                {
                    "route_kind": "chapter",
                    "target_id": int(row["id"]),
                    "text": snapshot.text,
                    "facts": snapshot.facts_after,
                    "source_base_version_id": snapshot.source_version_id,
                    "expected_source_head_version_id": snapshot.expected_head_version_id,
                    "require_head_match": snapshot.require_head_match,
                }
            )
        return segments

    def _current_text(self, connection, route_kind: str, target_id: int) -> str:
        if route_kind == "chapter":
            return self.chapter_versions.resolve_chapter_source(
                target_id, {"kind": "current"}, connection=connection
            ).text
        else:
            row = connection.execute(
                """
                SELECT v.generated_text
                FROM branch_scenes s
                JOIN branch_scene_versions v
                  ON v.branch_scene_id = s.id AND v.version = s.current_version
                WHERE s.id = ?
                """,
                (target_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Patch target not found: {route_kind}:{target_id}")
        return str(row[0])

    def _current_version_id(
        self, connection, route_kind: str, target_id: int
    ) -> int | None:
        if route_kind == "chapter":
            return self.chapter_versions.get_current_head_id(
                target_id, connection=connection
            )
        row = connection.execute(
            """
            SELECT v.id
            FROM branch_scenes s
            JOIN branch_scene_versions v
              ON v.branch_scene_id = s.id AND v.version = s.current_version
            WHERE s.id = ? AND s.deleted_at IS NULL
            """,
            (target_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Patch target not found: {route_kind}:{target_id}")
        return int(row["id"])

    @staticmethod
    def _patch(row) -> dict[str, Any]:
        result = dict(row)
        result["source_range"] = json.loads(row["source_range_json"])
        result["evidence"] = json.loads(row["evidence_json"])
        result["requires_confirmation"] = bool(row["requires_confirmation"])
        return result


def _candidate_segments(
    segments: list[dict[str, Any]], old_fact: dict[str, Any]
) -> list[dict[str, Any]]:
    terms = {
        str(value).strip().casefold()
        for value in old_fact.values()
        if isinstance(value, (str, int, float)) and str(value).strip()
    }
    candidates = []
    for segment in segments:
        text = str(segment["text"])
        facts_text = json.dumps(segment.get("facts", {}), ensure_ascii=False)
        matched = [
            term for term in terms if term in text.casefold() or term in facts_text.casefold()
        ]
        candidates.append(
            {
                **segment,
                "recall_reason": "entity_or_fact_match" if matched else "downstream_semantic_scan",
                "matched_terms": matched,
            }
        )
    return candidates


def _validate_impact(segment: dict[str, Any], impact: Any) -> dict[str, Any]:
    if not isinstance(impact, dict):
        raise ValueError("Canon impact must be an object.")
    impact_type = impact.get("impact_type")
    if impact_type not in IMPACT_TYPES:
        raise ValueError("Canon impact has unsupported impact_type.")
    source_range = impact.get("source_range")
    if not isinstance(source_range, dict):
        raise ValueError("Canon impact requires source_range.")
    start = source_range.get("start")
    end = source_range.get("end")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start:
        raise ValueError("Canon impact source_range is invalid.")
    text = str(segment["text"])
    if end > len(text):
        raise ValueError("Canon impact source_range exceeds target text.")
    original = text[start:end]
    if original != impact.get("original_text"):
        raise ValueError("Canon impact original_text does not match source_range.")
    replacement = impact.get("replacement_text")
    if not isinstance(replacement, str):
        raise ValueError("Canon impact replacement_text must be text.")
    return {
        "route_kind": segment["route_kind"],
        "target_id": segment["target_id"],
        "source_base_version_id": segment.get("source_base_version_id"),
        "source_range": {"start": start, "end": end},
        "original_text": original,
        "replacement_text": replacement,
        "impact_type": impact_type,
        "reason": str(impact.get("reason") or ""),
        "confidence": float(impact.get("confidence", 0.0)),
        "evidence": impact.get("evidence") if isinstance(impact.get("evidence"), list) else [],
        "requires_confirmation": bool(impact.get("requires_confirmation", True)),
    }
