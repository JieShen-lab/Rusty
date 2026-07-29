from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.services.project_service import default_database_path


ANCHOR_TYPES = {
    "document_end",
    "chapter_start",
    "chapter_end",
    "scene_start",
    "scene_end",
    "skeleton_node",
    "text_offset",
}
BRANCH_MODES = {"open_continuation", "fork", "fork_and_rejoin"}


class BranchService:
    """Own branch topology and versioned content without mutating baseline chapters."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def create_branch(
        self,
        *,
        project_id: int,
        name: str,
        branch_mode: str,
        start_anchor: dict[str, Any],
        return_anchor: dict[str, Any] | None = None,
        parent_branch_id: int | None = None,
        base_source_version_id: int | None = None,
        downstream_strategy: str | None = None,
    ) -> dict[str, Any]:
        if branch_mode not in BRANCH_MODES:
            raise ValueError(f"Unsupported branch mode: {branch_mode}")
        if branch_mode == "fork_and_rejoin" and return_anchor is None:
            raise ValueError("fork_and_rejoin requires a return anchor.")
        if branch_mode != "fork_and_rejoin" and return_anchor is not None:
            raise ValueError(f"{branch_mode} cannot have a return anchor.")
        strategy = downstream_strategy or (
            "rejoin" if branch_mode == "fork_and_rejoin"
            else "reference" if branch_mode == "open_continuation"
            else "replace"
        )
        if strategy not in {"replace", "reference", "rejoin"}:
            raise ValueError("Unsupported downstream strategy.")
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT project_kind FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if project["project_kind"] != "branch":
                raise ValueError("Branches can only be created in branch projects.")
            if parent_branch_id is not None:
                parent = connection.execute(
                    """
                    SELECT id FROM story_branches
                    WHERE id = ? AND project_id = ? AND deleted_at IS NULL
                    """,
                    (parent_branch_id, project_id),
                ).fetchone()
                if parent is None:
                    raise FileNotFoundError(f"Parent branch not found: {parent_branch_id}")
            start_id = self._insert_anchor(connection, project_id, start_anchor)
            return_id = (
                self._insert_anchor(connection, project_id, return_anchor)
                if return_anchor is not None
                else None
            )
            cursor = connection.execute(
                """
                INSERT INTO story_branches (
                    project_id, parent_branch_id, base_source_kind,
                    base_source_version_id, name, branch_mode,
                    downstream_strategy, start_anchor_id, return_anchor_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    parent_branch_id,
                    "branch" if parent_branch_id is not None else "original",
                    base_source_version_id,
                    name.strip() or "Untitled branch",
                    branch_mode,
                    strategy,
                    start_id,
                    return_id,
                ),
            )
            branch_id = int(cursor.lastrowid)
        return self.get_branch(branch_id)

    def get_branch(self, branch_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM story_branches WHERE id = ? AND deleted_at IS NULL",
                (branch_id,),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Branch not found: {branch_id}")
            result = dict(row)
            result["start_anchor"] = self._anchor(connection, int(row["start_anchor_id"]))
            result["return_anchor"] = (
                self._anchor(connection, int(row["return_anchor_id"]))
                if row["return_anchor_id"] is not None
                else None
            )
        return result

    def list_branches(self, project_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT * FROM story_branches
                WHERE project_id = ? AND deleted_at IS NULL
                ORDER BY created_at, id
                """,
                (project_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def delete_branch(self, branch_id: int) -> None:
        with session(self.database_path) as connection:
            child = connection.execute(
                "SELECT id FROM story_branches WHERE parent_branch_id = ? AND deleted_at IS NULL LIMIT 1",
                (branch_id,),
            ).fetchone()
            if child is not None:
                raise ValueError("Cannot delete a branch that still has child branches.")
            cursor = connection.execute(
                """
                UPDATE story_branches
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (branch_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"Branch not found: {branch_id}")

    def save_scene(
        self,
        branch_id: int,
        *,
        title: str,
        generated_text: str,
        facts_after: dict[str, Any] | None = None,
        sequence_index: int | None = None,
    ) -> dict[str, Any]:
        self.get_branch(branch_id)
        with session(self.database_path) as connection:
            index = sequence_index or int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence_index), 0) + 1 FROM branch_scenes WHERE branch_id = ?",
                    (branch_id,),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO branch_scenes(branch_id, sequence_index, title)
                VALUES (?, ?, ?)
                """,
                (branch_id, index, title),
            )
            scene_id = int(cursor.lastrowid)
            version = connection.execute(
                """
                INSERT INTO branch_scene_versions(
                    branch_scene_id, version, generated_text, facts_after_json
                ) VALUES (?, 1, ?, ?)
                """,
                (scene_id, generated_text, json.dumps(facts_after or {}, ensure_ascii=False)),
            )
        return {
            "id": scene_id,
            "branch_id": branch_id,
            "sequence_index": index,
            "title": title,
            "version_id": int(version.lastrowid),
            "generated_text": generated_text,
            "facts_after": facts_after or {},
        }

    def list_scenes(self, branch_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.branch_id, s.sequence_index, s.title, s.current_version,
                       v.id AS version_id, v.generated_text, v.facts_after_json
                FROM branch_scenes s
                JOIN branch_scene_versions v
                  ON v.branch_scene_id = s.id AND v.version = s.current_version
                WHERE s.branch_id = ? AND s.deleted_at IS NULL
                ORDER BY s.sequence_index
                """,
                (branch_id,),
            ).fetchall()
        return [
            {
                **dict(row),
                "facts_after": json.loads(row["facts_after_json"]),
            }
            for row in rows
        ]

    def create_seam(
        self,
        branch_id: int,
        *,
        seam_kind: str,
        operation: str,
        original_text: str,
        proposed_text: str,
        source_range: dict[str, Any],
        source_hash: str,
        reason: str,
    ) -> dict[str, Any]:
        self.get_branch(branch_id)
        if seam_kind not in {"entry", "return"}:
            raise ValueError("Unsupported seam kind.")
        if operation not in {"keep", "insert_before", "insert_after", "replace_range"}:
            raise ValueError("Unsupported seam operation.")
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO branch_seams (
                    branch_id, seam_kind, operation, original_text, proposed_text,
                    source_range_json, source_hash, reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    seam_kind,
                    operation,
                    original_text,
                    proposed_text,
                    json.dumps(source_range, ensure_ascii=False),
                    source_hash,
                    reason,
                ),
            )
        return self.get_seam(int(cursor.lastrowid))

    def review_seam(
        self, seam_id: int, *, decision: str, current_source_text: str
    ) -> dict[str, Any]:
        if decision not in {"confirmed", "rejected"}:
            raise ValueError("Seam decision must be confirmed or rejected.")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM branch_seams WHERE id = ?", (seam_id,)
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"Seam not found: {seam_id}")
            actual = hashlib.sha256(current_source_text.encode("utf-8")).hexdigest()
            if decision == "confirmed" and actual != row["source_hash"]:
                raise ValueError("Seam source hash mismatch; refusing silent application.")
            connection.execute(
                "UPDATE branch_seams SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (decision, seam_id),
            )
        return self.get_seam(seam_id)

    def get_seam(self, seam_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM branch_seams WHERE id = ?", (seam_id,)
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Seam not found: {seam_id}")
        result = dict(row)
        result["source_range"] = json.loads(row["source_range_json"])
        return result

    @staticmethod
    def source_hash(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    @staticmethod
    def _insert_anchor(connection, project_id: int, anchor: dict[str, Any]) -> int:
        anchor_type = str(anchor.get("anchor_type") or "")
        if anchor_type not in ANCHOR_TYPES:
            raise ValueError(f"Unsupported anchor type: {anchor_type}")
        if anchor_type.startswith("chapter_") and anchor.get("chapter_id") is None:
            raise ValueError("Chapter anchors require chapter_id.")
        if anchor_type.startswith("scene_") and anchor.get("scene_id") is None:
            raise ValueError("Scene anchors require scene_id.")
        if anchor_type == "skeleton_node" and (
            anchor.get("skeleton_version_id") is None or not anchor.get("node_id")
        ):
            raise ValueError("Skeleton anchors require version and node id.")
        if anchor_type == "text_offset" and anchor.get("text_offset") is None:
            raise ValueError("Text anchors require text_offset.")
        source_hash = str(anchor.get("source_hash") or "")
        if not source_hash:
            raise ValueError("Anchors require a source hash.")
        cursor = connection.execute(
            """
            INSERT INTO story_anchors (
                project_id, anchor_type, chapter_id, scene_id,
                skeleton_version_id, node_id, text_offset, side,
                source_version_id, source_hash
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                project_id,
                anchor_type,
                anchor.get("chapter_id"),
                anchor.get("scene_id"),
                anchor.get("skeleton_version_id"),
                anchor.get("node_id"),
                anchor.get("text_offset"),
                anchor.get("side") or "after",
                anchor.get("source_version_id"),
                source_hash,
            ),
        )
        return int(cursor.lastrowid)

    @staticmethod
    def _anchor(connection, anchor_id: int) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM story_anchors WHERE id = ?", (anchor_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Anchor not found: {anchor_id}")
        return dict(row)
