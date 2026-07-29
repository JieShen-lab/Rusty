from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.models import count_text_units
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.workflow_ai import WorkflowAI


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
        self.ai = WorkflowAI(self.database_path, ai_client=ai_client)
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
    ) -> dict[str, Any]:
        project = self.projects.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        if project.project_kind == "branch" and branch_id is None:
            raise ValueError("Canon changes in branch projects require a target branch.")
        with session(self.database_path) as connection:
            segments = self._segments(connection, project_id, branch_id, effective_order)
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
                    project_id, branch_id, old_fact_json, new_fact_json, effective_order
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    branch_id,
                    json.dumps(old_fact, ensure_ascii=False),
                    json.dumps(new_fact, ensure_ascii=False),
                    effective_order,
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
                        requires_confirmation
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        impact["route_kind"],
                        impact["target_id"],
                        json.dumps(impact["source_range"], ensure_ascii=False),
                        _hash(impact["original_text"]),
                        impact["original_text"],
                        impact["replacement_text"],
                        impact["impact_type"],
                        impact["reason"],
                        impact["confidence"],
                        json.dumps(impact["evidence"], ensure_ascii=False),
                        1 if impact["requires_confirmation"] else 0,
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
            cursor = connection.execute(
                """
                UPDATE canon_change_patches
                SET status = ?, replacement_text = COALESCE(?, replacement_text),
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (decision, replacement_text, patch_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Canon patch not found: {patch_id}")
            row = connection.execute(
                "SELECT * FROM canon_change_patches WHERE id = ?", (patch_id,)
            ).fetchone()
        return self._patch(row)

    def apply(self, run_id: int) -> dict[str, Any]:
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
                    if _hash(current_slice) != patch["source_hash"]:
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
        issues = consistency.get("issues")
        if not isinstance(issues, list):
            raise ValueError("Canon consistency check must return issues.")
        if issues:
            self._mark_blocked(run_id, issues)
            return self.get_run(run_id)

        ledger = {
            **run["fact_ledger"],
            str(run["old_fact"].get("attribute") or "fact"): run["new_fact"],
        }
        with session(self.database_path) as connection:
            for (route_kind, target_id), text in projected.items():
                self._save_route_text(
                    connection,
                    route_kind,
                    target_id,
                    text,
                    old_fact=run["old_fact"],
                    new_fact=run["new_fact"],
                )
            connection.executemany(
                """
                UPDATE canon_change_patches
                SET status = 'applied', updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                [(patch["id"],) for patch in selected],
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
        return self.get_run(run_id)

    def _mark_blocked(self, run_id: int, issues: list[dict[str, Any]]) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE canon_change_runs
                SET consistency_issues_json = ?, status = 'blocked',
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (json.dumps(issues, ensure_ascii=False), run_id),
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
        result["patches"] = [self._patch(patch) for patch in patches]
        return result

    @staticmethod
    def _segments(connection, project_id: int, branch_id: int | None, effective_order: int):
        if branch_id is not None:
            rows = connection.execute(
                """
                SELECT s.id, s.sequence_index, v.generated_text, v.facts_after_json
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
                }
                for row in rows
            ]
        rows = connection.execute(
            """
            SELECT id, COALESCE(rewritten_text, original_text) AS text
            FROM chapters
            WHERE project_id = ? AND chapter_index >= ?
            ORDER BY chapter_index
            """,
            (project_id, effective_order),
        ).fetchall()
        return [
            {
                "route_kind": "chapter",
                "target_id": int(row["id"]),
                "text": row["text"],
                "facts": {},
            }
            for row in rows
        ]

    @staticmethod
    def _current_text(connection, route_kind: str, target_id: int) -> str:
        if route_kind == "chapter":
            row = connection.execute(
                "SELECT COALESCE(rewritten_text, original_text) FROM chapters WHERE id = ?",
                (target_id,),
            ).fetchone()
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

    @staticmethod
    def _save_route_text(
        connection,
        route_kind: str,
        target_id: int,
        text: str,
        *,
        old_fact: dict[str, Any],
        new_fact: dict[str, Any],
    ) -> None:
        attribute = str(old_fact.get("attribute") or "fact")
        if route_kind == "chapter":
            chapter = connection.execute(
                "SELECT word_count FROM chapters WHERE id = ?", (target_id,)
            ).fetchone()
            word_count = count_text_units(text)
            ratio = word_count / int(chapter["word_count"]) if chapter["word_count"] else None
            connection.execute(
                """
                INSERT INTO chapter_rewrites(
                    chapter_id, rewritten_text, rewrite_source, actual_word_count,
                    expansion_ratio, prompt_snapshot_json, anchor_snapshot_json,
                    rewrite_mode, anchor_text, expanded_text
                ) VALUES (?, ?, 'ai', ?, ?, '{}', '{}', 'full_rewrite', '', ?)
                ON CONFLICT(chapter_id) DO UPDATE SET
                    rewritten_text=excluded.rewritten_text,
                    rewrite_source='ai',
                    actual_word_count=excluded.actual_word_count,
                    expansion_ratio=excluded.expansion_ratio,
                    expanded_text=excluded.expanded_text,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (target_id, text, word_count, ratio, text),
            )
            connection.execute(
                "UPDATE chapters SET rewritten_text = ?, status = 'rewritten', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (text, target_id),
            )
            scenes = connection.execute(
                "SELECT id FROM scenes WHERE chapter_id = ? AND deleted_at IS NULL",
                (target_id,),
            ).fetchall()
            for scene in scenes:
                latest = connection.execute(
                    """
                    SELECT ledger_version, facts_json
                    FROM scene_fact_ledgers
                    WHERE scene_id = ? ORDER BY ledger_version DESC LIMIT 1
                    """,
                    (scene["id"],),
                ).fetchone()
                if latest is None:
                    continue
                facts = json.loads(latest["facts_json"])
                facts[attribute] = new_fact
                connection.execute(
                    """
                    INSERT INTO scene_fact_ledgers(
                        scene_id, ledger_version, facts_json, source_kind
                    ) VALUES (?, ?, ?, 'manual')
                    """,
                    (
                        scene["id"],
                        int(latest["ledger_version"]) + 1,
                        json.dumps(facts, ensure_ascii=False),
                    ),
                )
            return
        row = connection.execute(
            """
            SELECT s.current_version, v.id AS parent_id, v.facts_after_json
            FROM branch_scenes s
            JOIN branch_scene_versions v
              ON v.branch_scene_id = s.id AND v.version = s.current_version
            WHERE s.id = ?
            """,
            (target_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Branch scene not found: {target_id}")
        facts = json.loads(row["facts_after_json"])
        facts[attribute] = new_fact
        version = int(row["current_version"]) + 1
        connection.execute(
            """
            INSERT INTO branch_scene_versions(
                branch_scene_id, version, generated_text, facts_after_json,
                source_kind, parent_version_id
            ) VALUES (?, ?, ?, ?, 'manual', ?)
            """,
            (
                target_id,
                version,
                text,
                json.dumps(facts, ensure_ascii=False),
                int(row["parent_id"]),
            ),
        )
        connection.execute(
            "UPDATE branch_scenes SET current_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (version, target_id),
        )

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
        "source_range": {"start": start, "end": end},
        "original_text": original,
        "replacement_text": replacement,
        "impact_type": impact_type,
        "reason": str(impact.get("reason") or ""),
        "confidence": float(impact.get("confidence", 0.0)),
        "evidence": impact.get("evidence") if isinstance(impact.get("evidence"), list) else [],
        "requires_confirmation": bool(impact.get("requires_confirmation", True)),
    }


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
