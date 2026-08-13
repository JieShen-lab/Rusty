from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.content_hash import hash_text
from rusty.db import default_database_path, session
from rusty.domain.plot_workflow import PLOT_ACTIVE_STATUSES
from rusty.domain.story_anchors import (
    BRANCH_GENERATION_MODES,
    ORIGINAL_ANCHOR_TYPES,
)


BRANCH_MODES = BRANCH_GENERATION_MODES
ACTIVE_PLOT_RUN_STATUSES = PLOT_ACTIVE_STATUSES


class BranchService:
    """Own independent branch routes and their versioned generated content."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

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
        if parent_branch_id is not None:
            raise ValueError("Child branches are not supported; append to the existing branch instead.")
        if return_anchor is not None:
            raise ValueError("Branches do not accept a return anchor.")
        if base_source_version_id is not None:
            raise ValueError("Root branches cannot specify base_source_version_id.")
        strategy = downstream_strategy or (
            "reference" if branch_mode == "open_continuation" else "replace"
        )
        if strategy not in {"replace", "reference"}:
            raise ValueError("Unsupported downstream strategy.")
        start_type = str(start_anchor.get("anchor_type") or "")
        if start_type not in ORIGINAL_ANCHOR_TYPES:
            raise ValueError("Branches must start from original content anchors.")
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT project_kind FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if project is None:
                raise FileNotFoundError(f"Project not found: {project_id}")
            if project["project_kind"] != "branch":
                raise ValueError("Branches can only be created in branch projects.")
            start_id = self._insert_anchor(
                connection,
                project_id,
                start_anchor,
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
                    None,
                    "original",
                    None,
                    name.strip() or "Untitled branch",
                    branch_mode,
                    strategy,
                    start_id,
                    None,
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
        return [self.get_branch(int(row["id"])) for row in rows]

    def delete_branch(self, branch_id: int) -> None:
        with session(self.database_path) as connection:
            child = connection.execute(
                "SELECT id FROM story_branches WHERE parent_branch_id = ? AND deleted_at IS NULL LIMIT 1",
                (branch_id,),
            ).fetchone()
            if child is not None:
                raise ValueError("Cannot delete a branch that still has child branches.")
            active_run = connection.execute(
                """
                SELECT id FROM plot_generation_runs
                WHERE branch_id = ? AND status IN (
                    'awaiting_skeleton', 'planning_blocked', 'awaiting_seams',
                    'ready', 'generating', 'repair_required'
                )
                LIMIT 1
                """,
                (branch_id,),
            ).fetchone()
            if active_run is not None:
                raise ValueError("Cannot delete a branch with an unfinished generation run.")
            connection.execute(
                "UPDATE branch_scenes SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE branch_id = ? AND deleted_at IS NULL",
                (branch_id,),
            )
            connection.execute(
                "UPDATE branch_chapters SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP WHERE branch_id = ? AND deleted_at IS NULL",
                (branch_id,),
            )
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

    def create_chapter(
        self,
        branch_id: int,
        *,
        title: str,
        summary: str = "",
        facts_before: dict[str, Any] | None = None,
        facts_after: dict[str, Any] | None = None,
        sequence_index: int | None = None,
        source_kind: str = "generation",
    ) -> dict[str, Any]:
        self.get_branch(branch_id)
        if source_kind not in {"generation", "manual", "repair", "migration", "restore"}:
            raise ValueError("Unsupported branch chapter source kind.")
        with session(self.database_path) as connection:
            index = sequence_index or int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence_index), 0) + 1 FROM branch_chapters WHERE branch_id = ?",
                    (branch_id,),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO branch_chapters(branch_id, sequence_index, title)
                VALUES (?, ?, ?)
                """,
                (branch_id, index, title),
            )
            chapter_id = int(cursor.lastrowid)
            version = connection.execute(
                """
                INSERT INTO branch_chapter_versions(
                    branch_chapter_id, version, title, summary,
                    facts_before_json, facts_after_json, source_kind
                ) VALUES (?, 1, ?, ?, ?, ?, ?)
                """,
                (
                    chapter_id,
                    title,
                    summary,
                    json.dumps(facts_before or {}, ensure_ascii=False),
                    json.dumps(facts_after or {}, ensure_ascii=False),
                    source_kind,
                ),
            )
        return self.get_chapter(chapter_id, version_id=int(version.lastrowid))

    def save_chapter_version(
        self,
        branch_chapter_id: int,
        *,
        title: str,
        summary: str,
        facts_before: dict[str, Any],
        facts_after: dict[str, Any],
        source_kind: str = "manual",
        parent_version_id: int | None = None,
    ) -> dict[str, Any]:
        if source_kind not in {"generation", "manual", "repair", "migration", "restore"}:
            raise ValueError("Unsupported branch chapter source kind.")
        with session(self.database_path) as connection:
            chapter = connection.execute(
                """
                SELECT c.*, v.id AS current_version_id
                FROM branch_chapters c
                JOIN branch_chapter_versions v
                  ON v.branch_chapter_id = c.id AND v.version = c.current_version
                WHERE c.id = ? AND c.deleted_at IS NULL
                """,
                (branch_chapter_id,),
            ).fetchone()
            if chapter is None:
                raise FileNotFoundError(f"Branch chapter not found: {branch_chapter_id}")
            next_version = int(chapter["current_version"]) + 1
            parent_id = parent_version_id or int(chapter["current_version_id"])
            parent = connection.execute(
                """
                SELECT id FROM branch_chapter_versions
                WHERE id = ? AND branch_chapter_id = ?
                """,
                (parent_id, branch_chapter_id),
            ).fetchone()
            if parent is None:
                raise ValueError("Parent chapter version does not belong to this chapter.")
            cursor = connection.execute(
                """
                INSERT INTO branch_chapter_versions(
                    branch_chapter_id, version, title, summary,
                    facts_before_json, facts_after_json, parent_version_id, source_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_chapter_id,
                    next_version,
                    title,
                    summary,
                    json.dumps(facts_before, ensure_ascii=False),
                    json.dumps(facts_after, ensure_ascii=False),
                    parent_id,
                    source_kind,
                ),
            )
            connection.execute(
                """
                UPDATE branch_chapters
                SET title = ?, current_version = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (title, next_version, branch_chapter_id),
            )
            connection.execute(
                """
                INSERT INTO branch_chapter_version_scenes(
                    branch_chapter_version_id, branch_scene_id,
                    branch_scene_version_id, scene_index
                )
                SELECT ?, branch_scene_id, branch_scene_version_id, scene_index
                FROM branch_chapter_version_scenes
                WHERE branch_chapter_version_id = ?
                ORDER BY scene_index
                """,
                (int(cursor.lastrowid), parent_id),
            )
        return self.get_chapter(branch_chapter_id, version_id=int(cursor.lastrowid))

    def restore_chapter_version(
        self, branch_chapter_id: int, version_id: int
    ) -> dict[str, Any]:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM branch_chapter_versions
                WHERE id = ? AND branch_chapter_id = ?
                """,
                (version_id, branch_chapter_id),
            ).fetchone()
        if row is None:
            raise FileNotFoundError("Branch chapter version not found.")
        return self.save_chapter_version(
            branch_chapter_id,
            title=str(row["title"]),
            summary=str(row["summary"]),
            facts_before=json.loads(row["facts_before_json"]),
            facts_after=json.loads(row["facts_after_json"]),
            source_kind="restore",
            parent_version_id=version_id,
        )

    def get_chapter(
        self, branch_chapter_id: int, *, version_id: int | None = None
    ) -> dict[str, Any]:
        with session(self.database_path) as connection:
            chapter = connection.execute(
                """
                SELECT * FROM branch_chapters
                WHERE id = ? AND deleted_at IS NULL
                """,
                (branch_chapter_id,),
            ).fetchone()
            if chapter is None:
                raise FileNotFoundError(f"Branch chapter not found: {branch_chapter_id}")
            if version_id is None:
                version = connection.execute(
                    """
                    SELECT * FROM branch_chapter_versions
                    WHERE branch_chapter_id = ? AND version = ?
                    """,
                    (branch_chapter_id, int(chapter["current_version"])),
                ).fetchone()
            else:
                version = connection.execute(
                    """
                    SELECT * FROM branch_chapter_versions
                    WHERE branch_chapter_id = ? AND id = ?
                    """,
                    (branch_chapter_id, version_id),
                ).fetchone()
            if version is None:
                raise FileNotFoundError("Branch chapter version not found.")
            scene_rows = connection.execute(
                """
                SELECT s.id, s.branch_id, s.branch_chapter_id, s.sequence_index,
                       snapshot.scene_index, s.title, v.id AS version_id,
                       v.version, v.generated_text, v.facts_after_json,
                       v.parent_version_id, v.source_kind
                FROM branch_chapter_version_scenes snapshot
                JOIN branch_scenes s ON s.id = snapshot.branch_scene_id
                JOIN branch_scene_versions v ON v.id = snapshot.branch_scene_version_id
                WHERE snapshot.branch_chapter_version_id = ?
                ORDER BY snapshot.scene_index
                """,
                (version["id"],),
            ).fetchall()
        return {
            **dict(chapter),
            "version_id": int(version["id"]),
            "version": int(version["version"]),
            "summary": str(version["summary"]),
            "facts_before": json.loads(version["facts_before_json"]),
            "facts_after": json.loads(version["facts_after_json"]),
            "parent_version_id": version["parent_version_id"],
            "source_kind": str(version["source_kind"]),
            "source_operation": str(version["source_operation"] or ""),
            "fact_chain_status": str(version["fact_chain_status"]),
            "scenes": [
                {**dict(row), "facts_after": json.loads(row["facts_after_json"])}
                for row in scene_rows
            ],
        }

    def list_chapters(self, branch_id: int) -> list[dict[str, Any]]:
        self.get_branch(branch_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT id
                FROM branch_chapters
                WHERE branch_id = ? AND deleted_at IS NULL
                ORDER BY sequence_index, id
                """,
                (branch_id,),
            ).fetchall()
        chapters = []
        for row in rows:
            chapter = self.get_chapter(int(row["id"]))
            chapters.append(chapter)
        return chapters

    def save_scene(
        self,
        branch_id: int,
        *,
        title: str,
        generated_text: str,
        facts_after: dict[str, Any] | None = None,
        sequence_index: int | None = None,
        branch_chapter_id: int | None = None,
        scene_index: int | None = None,
    ) -> dict[str, Any]:
        self.get_branch(branch_id)
        chapter_id = branch_chapter_id or self._ensure_default_chapter(branch_id)
        with session(self.database_path) as connection:
            chapter = connection.execute(
                """
                SELECT id FROM branch_chapters
                WHERE id = ? AND branch_id = ? AND deleted_at IS NULL
                """,
                (chapter_id, branch_id),
            ).fetchone()
            if chapter is None:
                raise ValueError("Branch scene chapter does not belong to the branch.")
            index = sequence_index or int(
                connection.execute(
                    "SELECT COALESCE(MAX(sequence_index), 0) + 1 FROM branch_scenes WHERE branch_id = ?",
                    (branch_id,),
                ).fetchone()[0]
            )
            chapter_scene_index = scene_index or int(
                connection.execute(
                    """
                    SELECT COALESCE(MAX(scene_index), 0) + 1
                    FROM branch_scenes
                    WHERE branch_chapter_id = ?
                    """,
                    (chapter_id,),
                ).fetchone()[0]
            )
            cursor = connection.execute(
                """
                INSERT INTO branch_scenes(
                    branch_id, branch_chapter_id, sequence_index, scene_index, title
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (branch_id, chapter_id, index, chapter_scene_index, title),
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
            self._snapshot_chapter_after_scene_change(
                connection,
                chapter_id,
                scene_id=scene_id,
                scene_version_id=int(version.lastrowid),
                scene_index=chapter_scene_index,
                facts_after=facts_after,
                source_kind="generation",
            )
        return {
            "id": scene_id,
            "branch_id": branch_id,
            "branch_chapter_id": chapter_id,
            "sequence_index": index,
            "scene_index": chapter_scene_index,
            "title": title,
            "version_id": int(version.lastrowid),
            "generated_text": generated_text,
            "facts_after": facts_after or {},
        }

    def save_scene_version(
        self,
        branch_scene_id: int,
        *,
        generated_text: str,
        facts_after: dict[str, Any],
        source_kind: str = "manual",
    ) -> dict[str, Any]:
        if source_kind not in {"generation", "manual", "repair", "restore"}:
            raise ValueError("Unsupported branch scene source kind.")
        with session(self.database_path) as connection:
            scene = connection.execute(
                """
                SELECT s.*, v.id AS current_version_id
                FROM branch_scenes s
                JOIN branch_scene_versions v
                  ON v.branch_scene_id = s.id AND v.version = s.current_version
                WHERE s.id = ? AND s.deleted_at IS NULL
                """,
                (branch_scene_id,),
            ).fetchone()
            if scene is None:
                raise FileNotFoundError(f"Branch scene not found: {branch_scene_id}")
            next_version = int(scene["current_version"]) + 1
            cursor = connection.execute(
                """
                INSERT INTO branch_scene_versions(
                    branch_scene_id, version, generated_text, facts_after_json,
                    source_kind, parent_version_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_scene_id,
                    next_version,
                    generated_text,
                    json.dumps(facts_after, ensure_ascii=False),
                    source_kind,
                    scene["current_version_id"],
                ),
            )
            connection.execute(
                "UPDATE branch_scenes SET current_version = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (next_version, branch_scene_id),
            )
            self._snapshot_chapter_after_scene_change(
                connection,
                int(scene["branch_chapter_id"]),
                scene_id=branch_scene_id,
                scene_version_id=int(cursor.lastrowid),
                scene_index=int(scene["scene_index"]),
                facts_after=facts_after,
                source_kind=source_kind,
            )
        return self.get_scene(branch_scene_id, version_id=int(cursor.lastrowid))

    def create_generated_chapter(
        self,
        branch_id: int,
        *,
        title: str,
        summary: str,
        facts_before: dict[str, Any],
        facts_after: dict[str, Any],
        scenes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self.get_branch(branch_id)
        if not scenes:
            raise ValueError("Generated chapters require at least one scene.")
        with session(self.database_path) as connection:
            created = self._create_generated_chapter_in_connection(
                connection,
                branch_id=branch_id,
                title=title,
                summary=summary,
                facts_before=facts_before,
                facts_after=facts_after,
                scenes=scenes,
            )
        return self.get_chapter(created["id"], version_id=created["version_id"])

    def commit_generated_run(
        self,
        connection,
        *,
        branch_id: int,
        chapters: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        branch = connection.execute(
            "SELECT id FROM story_branches WHERE id = ? AND deleted_at IS NULL",
            (branch_id,),
        ).fetchone()
        if branch is None:
            raise FileNotFoundError(f"Branch not found: {branch_id}")
        return [
            self._create_generated_chapter_in_connection(
                connection,
                branch_id=branch_id,
                title=str(chapter.get("title") or ""),
                summary=str(chapter.get("summary") or ""),
                facts_before=dict(chapter.get("facts_before") or {}),
                facts_after=dict(chapter.get("facts_after") or {}),
                scenes=list(chapter.get("scenes") or []),
            )
            for chapter in chapters
        ]

    @staticmethod
    def _create_generated_chapter_in_connection(
        connection,
        *,
        branch_id: int,
        title: str,
        summary: str,
        facts_before: dict[str, Any],
        facts_after: dict[str, Any],
        scenes: list[dict[str, Any]],
    ) -> dict[str, Any]:
        if not scenes:
            raise ValueError("Generated chapters require at least one scene.")
        sequence_index = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence_index), 0) + 1 FROM branch_chapters WHERE branch_id = ?",
                (branch_id,),
            ).fetchone()[0]
        )
        chapter_cursor = connection.execute(
            "INSERT INTO branch_chapters(branch_id, sequence_index, title) VALUES (?, ?, ?)",
            (branch_id, sequence_index, title),
        )
        chapter_id = int(chapter_cursor.lastrowid)
        chapter_version = connection.execute(
            """
            INSERT INTO branch_chapter_versions(
                branch_chapter_id, version, title, summary,
                facts_before_json, facts_after_json, source_kind, fact_chain_status
            ) VALUES (?, 1, ?, ?, ?, ?, 'generation', 'consistent')
            """,
            (
                chapter_id,
                title,
                summary,
                json.dumps(facts_before, ensure_ascii=False),
                json.dumps(facts_after, ensure_ascii=False),
            ),
        )
        chapter_version_id = int(chapter_version.lastrowid)
        base_sequence = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence_index), 0) FROM branch_scenes WHERE branch_id = ?",
                (branch_id,),
            ).fetchone()[0]
        )
        created_scenes: list[dict[str, Any]] = []
        for scene_index, scene in enumerate(scenes, start=1):
            scene_cursor = connection.execute(
                """
                INSERT INTO branch_scenes(
                    branch_id, branch_chapter_id, sequence_index, scene_index, title
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    branch_id,
                    chapter_id,
                    base_sequence + scene_index,
                    scene_index,
                    str(scene.get("title") or ""),
                ),
            )
            scene_id = int(scene_cursor.lastrowid)
            scene_version = connection.execute(
                """
                INSERT INTO branch_scene_versions(
                    branch_scene_id, version, generated_text,
                    facts_after_json, source_kind
                ) VALUES (?, 1, ?, ?, 'generation')
                """,
                (
                    scene_id,
                    str(scene["text"]),
                    json.dumps(scene.get("facts_after") or {}, ensure_ascii=False),
                ),
            )
            scene_version_id = int(scene_version.lastrowid)
            connection.execute(
                """
                INSERT INTO branch_chapter_version_scenes(
                    branch_chapter_version_id, branch_scene_id,
                    branch_scene_version_id, scene_index
                ) VALUES (?, ?, ?, ?)
                """,
                (chapter_version_id, scene_id, scene_version_id, scene_index),
            )
            created_scenes.append(
                {
                    "id": scene_id,
                    "version_id": scene_version_id,
                    "scene_index": scene_index,
                    "title": str(scene.get("title") or ""),
                    "generated_text": str(scene["text"]),
                    "facts_after": dict(scene.get("facts_after") or {}),
                }
            )
        return {
            "id": chapter_id,
            "branch_id": branch_id,
            "sequence_index": sequence_index,
            "title": title,
            "summary": summary,
            "version_id": chapter_version_id,
            "version": 1,
            "facts_before": facts_before,
            "facts_after": facts_after,
            "fact_chain_status": "consistent",
            "scenes": created_scenes,
        }

    @staticmethod
    def _snapshot_chapter_after_scene_change(
        connection,
        branch_chapter_id: int,
        *,
        scene_id: int,
        scene_version_id: int,
        scene_index: int,
        facts_after: dict[str, Any] | None,
        source_kind: str,
        fact_chain_status: str | None = None,
    ) -> int:
        current = connection.execute(
            """
            SELECT c.current_version, v.*
            FROM branch_chapters c
            JOIN branch_chapter_versions v
              ON v.branch_chapter_id = c.id AND v.version = c.current_version
            WHERE c.id = ? AND c.deleted_at IS NULL
            """,
            (branch_chapter_id,),
        ).fetchone()
        if current is None:
            raise FileNotFoundError(f"Branch chapter not found: {branch_chapter_id}")
        next_version = int(current["current_version"]) + 1
        max_scene_index = int(
            connection.execute(
                """
                SELECT COALESCE(MAX(scene_index), 0)
                FROM branch_chapter_version_scenes
                WHERE branch_chapter_version_id = ?
                """,
                (current["id"],),
            ).fetchone()[0]
        )
        chain_status = fact_chain_status or (
            "needs_recompute" if scene_index < max_scene_index else "consistent"
        )
        version_cursor = connection.execute(
            """
            INSERT INTO branch_chapter_versions(
                branch_chapter_id, version, title, summary,
                facts_before_json, facts_after_json, parent_version_id, source_kind,
                fact_chain_status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                branch_chapter_id,
                next_version,
                current["title"],
                current["summary"],
                current["facts_before_json"],
                current["facts_after_json"],
                current["id"],
                source_kind,
                chain_status,
            ),
        )
        new_version_id = int(version_cursor.lastrowid)
        connection.execute(
            """
            INSERT INTO branch_chapter_version_scenes(
                branch_chapter_version_id, branch_scene_id,
                branch_scene_version_id, scene_index
            )
            SELECT ?, branch_scene_id, branch_scene_version_id, scene_index
            FROM branch_chapter_version_scenes
            WHERE branch_chapter_version_id = ? AND branch_scene_id <> ?
            """,
            (new_version_id, current["id"], scene_id),
        )
        connection.execute(
            """
            INSERT INTO branch_chapter_version_scenes(
                branch_chapter_version_id, branch_scene_id,
                branch_scene_version_id, scene_index
            ) VALUES (?, ?, ?, ?)
            """,
            (new_version_id, scene_id, scene_version_id, scene_index),
        )
        last_scene = connection.execute(
            """
            SELECT sv.facts_after_json
            FROM branch_chapter_version_scenes map
            JOIN branch_scene_versions sv ON sv.id = map.branch_scene_version_id
            WHERE map.branch_chapter_version_id = ?
            ORDER BY map.scene_index DESC LIMIT 1
            """,
            (new_version_id,),
        ).fetchone()
        connection.execute(
            """
            UPDATE branch_chapter_versions
            SET facts_after_json = ?, fact_chain_status = ?
            WHERE id = ?
            """,
            (
                last_scene["facts_after_json"] if last_scene is not None else current["facts_after_json"],
                chain_status,
                new_version_id,
            ),
        )
        connection.execute(
            """
            UPDATE branch_chapters SET current_version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (next_version, branch_chapter_id),
        )
        return new_version_id

    def list_scenes(
        self, branch_id: int, *, branch_chapter_id: int | None = None
    ) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT s.id, s.branch_id, s.branch_chapter_id, s.sequence_index,
                       s.scene_index, s.title, s.current_version,
                       v.id AS version_id, v.generated_text, v.facts_after_json
                FROM branch_scenes s
                JOIN branch_scene_versions v
                  ON v.branch_scene_id = s.id AND v.version = s.current_version
                WHERE s.branch_id = ? AND s.deleted_at IS NULL
                  AND (? IS NULL OR s.branch_chapter_id = ?)
                ORDER BY s.sequence_index, s.scene_index, s.id
                """,
                (branch_id, branch_chapter_id, branch_chapter_id),
            ).fetchall()
        return [
            {
                **dict(row),
                "facts_after": json.loads(row["facts_after_json"]),
            }
            for row in rows
        ]

    def get_scene(
        self, branch_scene_id: int, *, version_id: int | None = None
    ) -> dict[str, Any]:
        with session(self.database_path) as connection:
            scene = connection.execute(
                """
                SELECT * FROM branch_scenes
                WHERE id = ? AND deleted_at IS NULL
                """,
                (branch_scene_id,),
            ).fetchone()
            if scene is None:
                raise FileNotFoundError(f"Branch scene not found: {branch_scene_id}")
            if version_id is None:
                version = connection.execute(
                    """
                    SELECT * FROM branch_scene_versions
                    WHERE branch_scene_id = ? AND version = ?
                    """,
                    (branch_scene_id, int(scene["current_version"])),
                ).fetchone()
            else:
                version = connection.execute(
                    """
                    SELECT * FROM branch_scene_versions
                    WHERE branch_scene_id = ? AND id = ?
                    """,
                    (branch_scene_id, version_id),
                ).fetchone()
            if version is None:
                raise FileNotFoundError("Branch scene version not found.")
        return {
            **dict(scene),
            "version_id": int(version["id"]),
            "version": int(version["version"]),
            "generated_text": str(version["generated_text"]),
            "facts_after": json.loads(version["facts_after_json"]),
        }

    def compose_export(self, branch_id: int) -> dict[str, Any]:
        branch = self.get_branch(branch_id)
        start_anchor = branch["start_anchor"]
        with session(self.database_path) as connection:
            baseline = connection.execute(
                """
                SELECT id, chapter_index, title, original_text
                FROM chapters
                WHERE project_id = ?
                ORDER BY chapter_index, id
                """,
                (branch["project_id"],),
            ).fetchall()
        chapter_id = start_anchor.get("chapter_id")
        if chapter_id is not None:
            accepted = []
            for row in baseline:
                accepted.append(row)
                if int(row["id"]) == int(chapter_id):
                    break
            baseline = accepted
        return {
            "branch": branch,
            "baseline_history": [dict(row) for row in baseline],
            "branch_chapters": self.list_chapters(branch_id),
        }

    def _ensure_default_chapter(self, branch_id: int) -> int:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT id FROM branch_chapters
                WHERE branch_id = ? AND deleted_at IS NULL
                ORDER BY sequence_index, id
                LIMIT 1
                """,
                (branch_id,),
            ).fetchone()
        if row is not None:
            return int(row["id"])
        return int(
            self.create_chapter(
                branch_id,
                title="Generated chapter",
                source_kind="generation",
            )["id"]
        )

    @staticmethod
    def source_hash(text: str) -> str:
        return hash_text(text)

    @classmethod
    def _insert_anchor(
        cls,
        connection,
        project_id: int,
        anchor: dict[str, Any],
    ) -> int:
        anchor_type = str(anchor.get("anchor_type") or "")
        if anchor_type not in ORIGINAL_ANCHOR_TYPES:
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
        cls._validate_anchor_target(
            connection,
            project_id=project_id,
            anchor=anchor,
        )
        source_text, source_range = cls._resolve_anchor_source(
            connection,
            project_id=project_id,
            anchor=anchor,
        )
        expected_hash = cls.source_hash(source_text)
        supplied_hash = str(anchor.get("source_hash") or "")
        if supplied_hash and supplied_hash != expected_hash:
            raise ValueError("Anchor source_hash does not match the current source.")
        source_hash = expected_hash
        offset = anchor.get("text_offset")
        if offset is not None:
            offset = int(offset)
            if offset < int(source_range["start"]) or offset > int(source_range["end"]):
                raise ValueError("Anchor text_offset is outside the source range.")
        cursor = connection.execute(
            """
            INSERT INTO story_anchors (
                project_id, anchor_type, chapter_id, scene_id,
                skeleton_version_id, node_id, text_offset, side,
                source_version_id, source_hash, branch_chapter_id, branch_scene_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                anchor.get("branch_chapter_id"),
                anchor.get("branch_scene_id"),
            ),
        )
        return int(cursor.lastrowid)

    def validate_anchor_order(
        self,
        project_id: int,
        start_anchor: dict[str, Any],
        return_anchor: dict[str, Any],
    ) -> None:
        with session(self.database_path) as connection:
            self._validate_anchor_order(connection, project_id, start_anchor, return_anchor)

    @classmethod
    def _validate_anchor_order(
        cls,
        connection,
        project_id: int,
        start_anchor: dict[str, Any],
        return_anchor: dict[str, Any],
    ) -> None:
        start = cls._original_anchor_position(connection, project_id, start_anchor)
        returned = cls._original_anchor_position(connection, project_id, return_anchor)
        if start is not None and returned is not None and returned < start:
            raise ValueError("Return anchor cannot be earlier than the start anchor.")

    @staticmethod
    def _original_anchor_position(connection, project_id: int, anchor: dict[str, Any]) -> tuple[int, int] | None:
        anchor_type = str(anchor.get("anchor_type") or "")
        if anchor_type in {"branch_chapter", "branch_scene"}:
            return None
        if anchor_type == "document_end":
            row = connection.execute(
                "SELECT chapter_index, LENGTH(original_text) AS offset FROM chapters WHERE project_id = ? ORDER BY chapter_index DESC LIMIT 1",
                (project_id,),
            ).fetchone()
            return (int(row["chapter_index"]), int(row["offset"])) if row else None
        if anchor_type.startswith("scene_"):
            row = connection.execute(
                """
                SELECT c.chapter_index, s.original_start_offset, s.original_end_offset
                FROM scenes s JOIN chapters c ON c.id = s.chapter_id
                WHERE s.id = ? AND c.project_id = ?
                """,
                (anchor.get("scene_id"), project_id),
            ).fetchone()
            if row is None:
                return None
            offset = row["original_start_offset"] if anchor_type == "scene_start" else row["original_end_offset"]
            return int(row["chapter_index"]), int(offset)
        if anchor_type == "skeleton_node":
            row = connection.execute(
                """
                SELECT c.chapter_index, c.original_text, v.skeleton_json
                FROM story_skeleton_versions v
                JOIN story_skeletons s ON s.id = v.skeleton_id
                JOIN chapters c ON c.id = s.chapter_id
                WHERE v.id = ? AND s.project_id = ?
                """,
                (anchor.get("skeleton_version_id"), project_id),
            ).fetchone()
            if row is None:
                return None
            nodes = json.loads(row["skeleton_json"] or "{}").get("event_nodes", [])
            node = next((item for item in nodes if str(item.get("id")) == str(anchor.get("node_id"))), {})
            span = node.get("source_span") if isinstance(node.get("source_span"), dict) else {}
            value = span.get("start", span.get("start_offset", 0)) if anchor.get("side") == "before" else span.get("end", span.get("end_offset", len(row["original_text"])))
            return int(row["chapter_index"]), int(value)
        chapter_id = anchor.get("chapter_id")
        if chapter_id is None:
            return None
        row = connection.execute(
            "SELECT chapter_index, LENGTH(original_text) AS length FROM chapters WHERE id = ? AND project_id = ?",
            (chapter_id, project_id),
        ).fetchone()
        if row is None:
            return None
        if anchor_type == "chapter_start":
            offset = 0
        elif anchor_type == "chapter_end":
            offset = int(row["length"])
        else:
            offset = int(anchor.get("text_offset") or 0)
        return int(row["chapter_index"]), offset

    @staticmethod
    def _resolve_anchor_source(
        connection,
        *,
        project_id: int,
        anchor: dict[str, Any],
    ) -> tuple[str, dict[str, int]]:
        anchor_type = str(anchor["anchor_type"])
        if anchor_type.startswith("scene_"):
            row = connection.execute(
                "SELECT original_text, original_start_offset, original_end_offset FROM scenes WHERE id = ?",
                (anchor["scene_id"],),
            ).fetchone()
            text = str(row["original_text"])
            return text, {"start": int(row["original_start_offset"]), "end": int(row["original_end_offset"])}
        chapter_id = anchor.get("chapter_id")
        if anchor_type == "skeleton_node":
            row = connection.execute(
                "SELECT s.chapter_id, s.scene_id FROM story_skeleton_versions v JOIN story_skeletons s ON s.id = v.skeleton_id WHERE v.id = ?",
                (anchor["skeleton_version_id"],),
            ).fetchone()
            if row["scene_id"] is not None:
                scene = connection.execute(
                    "SELECT original_text, original_start_offset, original_end_offset FROM scenes WHERE id = ?",
                    (row["scene_id"],),
                ).fetchone()
                text = str(scene["original_text"])
                return text, {"start": int(scene["original_start_offset"]), "end": int(scene["original_end_offset"])}
            chapter_id = row["chapter_id"]
        if chapter_id is None:
            row = connection.execute(
                "SELECT id, original_text FROM chapters WHERE project_id = ? ORDER BY chapter_index DESC LIMIT 1",
                (project_id,),
            ).fetchone()
        else:
            row = connection.execute("SELECT id, original_text FROM chapters WHERE id = ?", (chapter_id,)).fetchone()
        text = str(row["original_text"])
        return text, {"start": 0, "end": len(text)}

    @staticmethod
    def _validate_anchor_target(
        connection,
        *,
        project_id: int,
        anchor: dict[str, Any],
    ) -> None:
        anchor_type = str(anchor["anchor_type"])
        if anchor_type.startswith("chapter_"):
            row = connection.execute(
                "SELECT id FROM chapters WHERE id = ? AND project_id = ?",
                (anchor["chapter_id"], project_id),
            ).fetchone()
            if row is None:
                raise ValueError("Chapter anchor does not belong to the target project.")
        elif anchor_type.startswith("scene_"):
            row = connection.execute(
                """
                SELECT s.id
                FROM scenes s
                JOIN chapters c ON c.id = s.chapter_id
                WHERE s.id = ? AND c.project_id = ?
                """,
                (anchor["scene_id"], project_id),
            ).fetchone()
            if row is None:
                raise ValueError("Scene anchor does not belong to the target project.")
        elif anchor_type == "skeleton_node":
            row = connection.execute(
                """
                SELECT v.nodes_json, v.skeleton_json
                FROM story_skeleton_versions v
                JOIN story_skeletons s ON s.id = v.skeleton_id
                WHERE v.id = ? AND s.project_id = ?
                """,
                (anchor["skeleton_version_id"], project_id),
            ).fetchone()
            if row is None:
                raise ValueError("Skeleton version does not belong to the target project.")
            structured = json.loads(row["skeleton_json"] or "{}")
            nodes = structured.get("event_nodes") if isinstance(structured, dict) else None
            if not nodes:
                nodes = json.loads(row["nodes_json"] or "[]")
            node_ids = {
                str(node.get("id"))
                for node in nodes
                if isinstance(node, dict) and node.get("id") is not None
            }
            if str(anchor["node_id"]) not in node_ids:
                raise ValueError("Skeleton anchor node_id does not exist in the selected version.")

    @staticmethod
    def _anchor(connection, anchor_id: int) -> dict[str, Any]:
        row = connection.execute(
            "SELECT * FROM story_anchors WHERE id = ?", (anchor_id,)
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Anchor not found: {anchor_id}")
        return dict(row)
