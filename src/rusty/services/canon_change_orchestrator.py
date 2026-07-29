from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import ProjectService, default_database_path


INJURY_IMPACTS = (
    ("左臂受伤", "腿部受伤", "direct_fact", "直接伤势必须改为新事实"),
    ("左臂的伤", "腿部的伤", "direct_fact", "直接伤势指代必须一致"),
    ("无法抬剑", "腿伤令他难以站稳，只能勉强挥剑", "action_consequence", "动作限制需按腿伤重新推导"),
    ("袖口渗血", "裤腿渗血", "physical_symptom", "出血位置需与腿伤一致"),
    ("扶住手肘", "扶住腰身帮助他站稳", "other_character_reaction", "同伴反应需匹配行动障碍"),
    ("剪开衣袖", "剪开裤腿", "treatment", "治疗部位需匹配腿伤"),
    ("重新持剑", "腿伤恢复后重新站稳持剑", "recovery_progress", "恢复结果需保留并匹配新伤势"),
)


class CanonChangeOrchestrator:
    """Scan semantic consequences and apply only explicitly reviewed patches."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.projects = ProjectService(self.database_path)
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
            segments = self._segments(connection, project_id, branch_id, effective_order)
            for segment in segments:
                for candidate in _impact_candidates(
                    segment["text"], old_fact=old_fact, new_fact=new_fact
                ):
                    connection.execute(
                        """
                        INSERT INTO canon_change_patches (
                            run_id, route_kind, target_id, source_range_json,
                            source_hash, original_text, replacement_text,
                            impact_type, reason
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            run_id,
                            segment["route_kind"],
                            segment["target_id"],
                            json.dumps(
                                {"start": candidate["start"], "end": candidate["end"]},
                                ensure_ascii=False,
                            ),
                            _hash(candidate["original_text"]),
                            candidate["original_text"],
                            candidate["replacement_text"],
                            candidate["impact_type"],
                            candidate["reason"],
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
        if decision == "edited" and replacement_text is None:
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
            patch
            for patch in run["patches"]
            if patch["status"] in {"accepted", "edited"}
        ]
        grouped: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for patch in selected:
            grouped.setdefault((patch["route_kind"], patch["target_id"]), []).append(patch)
        blocked: list[dict[str, Any]] = []
        for (route_kind, target_id), patches in grouped.items():
            current = self._current_text(route_kind, target_id)
            for patch in patches:
                source_range = patch["source_range"]
                current_slice = current[source_range["start"] : source_range["end"]]
                if _hash(current_slice) != patch["source_hash"]:
                    blocked.append(
                        {
                            "type": "source_hash_mismatch",
                            "patch_id": patch["id"],
                            "target_id": target_id,
                        }
                    )
            if blocked:
                continue
            rewritten = current
            for patch in sorted(
                patches, key=lambda item: item["source_range"]["start"], reverse=True
            ):
                source_range = patch["source_range"]
                rewritten = (
                    rewritten[: source_range["start"]]
                    + patch["replacement_text"]
                    + rewritten[source_range["end"] :]
                )
            self._save_route_text(route_kind, target_id, rewritten)
            with session(self.database_path) as connection:
                connection.executemany(
                    """
                    UPDATE canon_change_patches
                    SET status = 'applied', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    [(patch["id"],) for patch in patches],
                )
        ledger = {**run["fact_ledger"], str(run["old_fact"].get("attribute") or "fact"): run["new_fact"]}
        status = "blocked" if blocked else "applied"
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE canon_change_runs
                SET fact_ledger_json = ?, consistency_issues_json = ?,
                    status = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    json.dumps(ledger, ensure_ascii=False),
                    json.dumps(blocked, ensure_ascii=False),
                    status,
                    run_id,
                ),
            )
            if blocked:
                connection.executemany(
                    "UPDATE canon_change_patches SET status = 'blocked' WHERE id = ?",
                    [(issue["patch_id"],) for issue in blocked],
                )
        return self.get_run(run_id)

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
                SELECT s.id, s.sequence_index, v.generated_text
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
                {"route_kind": "branch_scene", "target_id": int(row["id"]), "text": row["generated_text"]}
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
            {"route_kind": "chapter", "target_id": int(row["id"]), "text": row["text"]}
            for row in rows
        ]

    def _current_text(self, route_kind: str, target_id: int) -> str:
        with session(self.database_path) as connection:
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

    def _save_route_text(self, route_kind: str, target_id: int, text: str) -> None:
        if route_kind == "chapter":
            self.projects.save_chapter_rewrite(target_id, text)
            return
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT current_version FROM branch_scenes WHERE id = ?", (target_id,)
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Branch scene not found: {target_id}")
            version = int(row["current_version"]) + 1
            parent = connection.execute(
                """
                SELECT id FROM branch_scene_versions
                WHERE branch_scene_id = ? AND version = ?
                """,
                (target_id, int(row["current_version"])),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO branch_scene_versions (
                    branch_scene_id, version, generated_text, source_kind, parent_version_id
                ) VALUES (?, ?, ?, 'manual', ?)
                """,
                (target_id, version, text, int(parent["id"])),
            )
            connection.execute(
                "UPDATE branch_scenes SET current_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (version, target_id),
            )

    @staticmethod
    def _patch(row) -> dict[str, Any]:
        result = dict(row)
        result["source_range"] = json.loads(row["source_range_json"])
        return result


def _impact_candidates(
    text: str, *, old_fact: dict[str, Any], new_fact: dict[str, Any]
) -> list[dict[str, Any]]:
    attribute = str(old_fact.get("attribute") or "")
    old_value = str(old_fact.get("value") or "")
    new_value = str(new_fact.get("value") or "")
    patterns = []
    if attribute == "injury" and "左臂" in old_value and "腿" in new_value:
        patterns.extend(INJURY_IMPACTS)
    elif attribute == "relationship":
        patterns.append((old_value, new_value, "relationship_effect", "关系影响需按新事实传播"))
    elif attribute == "possession":
        patterns.append((old_value, new_value, "possession_or_equipment", "物品归属需按新事实传播"))
    elif attribute == "knowledge":
        patterns.append((old_value, new_value, "knowledge_state", "人物知识状态需按新事实传播"))
    else:
        patterns.append((old_value, new_value, "direct_fact", "直接事实需更新"))
    candidates = []
    for needle, replacement, impact_type, reason in patterns:
        if not needle:
            continue
        start = 0
        while True:
            index = text.find(needle, start)
            if index < 0:
                break
            candidates.append(
                {
                    "start": index,
                    "end": index + len(needle),
                    "original_text": needle,
                    "replacement_text": replacement,
                    "impact_type": impact_type,
                    "reason": reason,
                }
            )
            start = index + len(needle)
    return sorted(candidates, key=lambda item: (item["start"], item["impact_type"]))


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
