from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rusty.db import initialize_database, session
from rusty.models import count_text_units


SOURCE_OPERATIONS = {
    "plot_generation",
    "prose_rewrite",
    "canon_change",
    "manual",
    "migration",
    "restore",
}


@dataclass(frozen=True)
class ChapterSourceSnapshot:
    chapter_id: int
    project_id: int
    source_kind: str
    source_version_id: int | None
    text: str
    content_hash: str
    facts_before: dict[str, Any]
    facts_after: dict[str, Any]
    require_head_match: bool
    expected_head_version_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChapterVersionService:
    """Authority for immutable chapter rewrite versions and their current projection."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)
        with session(self.database_path) as connection:
            initialize_database(connection)

    def resolve_chapter_source(
        self,
        chapter_id: int,
        source: dict[str, Any] | None = None,
        *,
        connection: sqlite3.Connection | None = None,
    ) -> ChapterSourceSnapshot:
        if connection is None:
            with session(self.database_path) as owned:
                return self.resolve_chapter_source(chapter_id, source, connection=owned)
        selection = source or {"kind": "current"}
        kind = str(selection.get("kind") or "current")
        if kind not in {"current", "original", "rewrite_version"}:
            raise ValueError("Unsupported chapter source selection.")
        chapter = connection.execute(
            "SELECT id, project_id, original_text FROM chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        selected = None
        current_head_id = self.get_current_head_id(chapter_id, connection=connection)
        require_head_match = True
        if kind == "current":
            selected = connection.execute(
                """
                SELECT v.* FROM chapter_rewrites h
                JOIN chapter_rewrite_versions v ON v.id = h.current_version_id
                WHERE h.chapter_id = ?
                """,
                (chapter_id,),
            ).fetchone()
        elif kind == "rewrite_version":
            version_id = selection.get("version_id")
            if not isinstance(version_id, int):
                raise ValueError("rewrite_version source requires version_id.")
            selected = connection.execute(
                "SELECT * FROM chapter_rewrite_versions WHERE id = ? AND chapter_id = ?",
                (version_id, chapter_id),
            ).fetchone()
            if selected is None:
                raise ValueError("Rewrite source version does not belong to the chapter.")
        if selected is not None:
            return ChapterSourceSnapshot(
                chapter_id=int(chapter["id"]),
                project_id=int(chapter["project_id"]),
                source_kind="rewrite_version",
                source_version_id=int(selected["id"]),
                text=str(selected["rewritten_text"]),
                content_hash=str(selected["content_hash"]),
                facts_before=_json_object(selected["facts_before_json"]),
                facts_after=_json_object(selected["facts_after_json"]),
                require_head_match=require_head_match,
                expected_head_version_id=current_head_id,
            )
        original = str(chapter["original_text"])
        facts_before, facts_after = self._original_facts(connection, chapter_id)
        return ChapterSourceSnapshot(
            chapter_id=int(chapter["id"]),
            project_id=int(chapter["project_id"]),
            source_kind="original",
            source_version_id=None,
            text=original,
            content_hash=_hash(original),
            facts_before=facts_before,
            facts_after=facts_after,
            require_head_match=require_head_match,
            expected_head_version_id=current_head_id,
        )

    def resolve_anchor_chapter_id(
        self, project_id: int, anchor: dict[str, Any]
    ) -> int:
        with session(self.database_path) as connection:
            if anchor.get("chapter_id") is not None:
                row = connection.execute(
                    "SELECT id FROM chapters WHERE id = ? AND project_id = ?",
                    (anchor["chapter_id"], project_id),
                ).fetchone()
            elif anchor.get("scene_id") is not None:
                row = connection.execute(
                    """
                    SELECT c.id FROM scenes s
                    JOIN chapters c ON c.id = s.chapter_id
                    WHERE s.id = ? AND c.project_id = ? AND s.deleted_at IS NULL
                    """,
                    (anchor["scene_id"], project_id),
                ).fetchone()
            elif anchor.get("skeleton_version_id") is not None:
                row = connection.execute(
                    """
                    SELECT s.chapter_id AS id
                    FROM story_skeleton_versions v
                    JOIN story_skeletons s ON s.id = v.skeleton_id
                    WHERE v.id = ? AND s.project_id = ?
                    """,
                    (anchor["skeleton_version_id"], project_id),
                ).fetchone()
            else:
                row = None
        if row is None:
            raise ValueError("Anchor does not resolve to a chapter in this project.")
        return int(row["id"])

    def get_current_head_id(
        self, chapter_id: int, *, connection: sqlite3.Connection
    ) -> int | None:
        row = connection.execute(
            "SELECT current_version_id FROM chapter_rewrites WHERE chapter_id = ?",
            (chapter_id,),
        ).fetchone()
        return int(row["current_version_id"]) if row and row["current_version_id"] else None

    def append_chapter_rewrite_version(
        self,
        connection: sqlite3.Connection,
        *,
        chapter_id: int,
        rewritten_text: str,
        source_operation: str,
        source_run_id: int | None,
        source_base_kind: str,
        source_base_version_id: int | None,
        source_hash: str,
        facts_before: dict[str, Any] | None = None,
        facts_after: dict[str, Any] | None = None,
        require_head_match: bool = True,
        expected_head_version_id: int | None = None,
        source_kind: str = "ai",
        prompt_snapshot: dict[str, Any] | None = None,
        anchor_snapshot: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if source_operation not in SOURCE_OPERATIONS:
            raise ValueError("Unsupported chapter rewrite source operation.")
        if source_base_kind not in {"original", "rewrite_version"}:
            raise ValueError("Unsupported chapter rewrite base kind.")
        if source_base_kind == "original" and source_base_version_id is not None:
            raise ValueError("Original chapter source cannot have a rewrite version id.")
        if source_base_kind == "rewrite_version" and source_base_version_id is None:
            raise ValueError("Rewrite chapter source requires a version id.")
        chapter = connection.execute(
            "SELECT project_id, word_count FROM chapters WHERE id = ?",
            (chapter_id,),
        ).fetchone()
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        current_head = self.get_current_head_id(chapter_id, connection=connection)
        expected_head = expected_head_version_id
        if require_head_match and current_head != expected_head:
            raise SourceVersionConflict(
                chapter_id=chapter_id,
                expected_version_id=expected_head,
                current_version_id=current_head,
            )
        if source_base_version_id is not None:
            parent = connection.execute(
                "SELECT id, content_hash FROM chapter_rewrite_versions WHERE id = ? AND chapter_id = ?",
                (source_base_version_id, chapter_id),
            ).fetchone()
            if parent is None:
                raise ValueError("Rewrite base version does not belong to the chapter.")
            if str(parent["content_hash"]) != source_hash:
                raise ValueError("Rewrite base source hash does not match its immutable version.")
        else:
            original = connection.execute(
                "SELECT original_text FROM chapters WHERE id = ?", (chapter_id,)
            ).fetchone()
            if original is None or _hash(str(original["original_text"])) != source_hash:
                raise ValueError("Original chapter source hash mismatch.")
        next_version = int(
            connection.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM chapter_rewrite_versions WHERE chapter_id = ?",
                (chapter_id,),
            ).fetchone()[0]
        )
        text = rewritten_text.strip()
        if not text:
            raise ValueError("A chapter rewrite version cannot be empty.")
        cursor = connection.execute(
            """
            INSERT INTO chapter_rewrite_versions(
                project_id, chapter_id, version, parent_version_id,
                source_kind, source_operation, source_run_id,
                source_base_kind, source_base_version_id, source_hash,
                rewritten_text, content_hash, facts_before_json, facts_after_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(chapter["project_id"]),
                chapter_id,
                next_version,
                source_base_version_id,
                source_kind,
                source_operation,
                source_run_id,
                source_base_kind,
                source_base_version_id,
                source_hash,
                text,
                _hash(text),
                json.dumps(facts_before or {}, ensure_ascii=False),
                json.dumps(facts_after or {}, ensure_ascii=False),
            ),
        )
        version_id = int(cursor.lastrowid)
        word_count = count_text_units(text)
        ratio = word_count / int(chapter["word_count"]) if chapter["word_count"] else None
        connection.execute(
            """
            INSERT INTO chapter_rewrites(
                chapter_id, rewritten_text, rewrite_source, actual_word_count,
                expansion_ratio, prompt_snapshot_json, anchor_snapshot_json,
                rewrite_mode, anchor_text, expanded_text,
                current_version_id, current_version, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'full_rewrite', '', ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chapter_id) DO UPDATE SET
                rewritten_text = excluded.rewritten_text,
                rewrite_source = excluded.rewrite_source,
                actual_word_count = excluded.actual_word_count,
                expansion_ratio = excluded.expansion_ratio,
                prompt_snapshot_json = excluded.prompt_snapshot_json,
                anchor_snapshot_json = excluded.anchor_snapshot_json,
                rewrite_mode = 'full_rewrite',
                expanded_text = excluded.expanded_text,
                current_version_id = excluded.current_version_id,
                current_version = excluded.current_version,
                confirmed_at = NULL,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                chapter_id,
                text,
                "manual" if source_kind == "manual" else "ai",
                word_count,
                ratio,
                json.dumps(prompt_snapshot or {}, ensure_ascii=False),
                json.dumps(anchor_snapshot or {}, ensure_ascii=False),
                text,
                version_id,
                next_version,
            ),
        )
        connection.execute(
            """
            UPDATE chapters
            SET rewritten_text = ?, status = 'rewritten', updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (text, chapter_id),
        )
        return self.get_version(version_id, connection=connection)

    def list_versions(self, chapter_id: int) -> list[dict[str, Any]]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT v.*, CASE WHEN h.current_version_id = v.id THEN 1 ELSE 0 END AS is_current
                FROM chapter_rewrite_versions v
                LEFT JOIN chapter_rewrites h ON h.chapter_id = v.chapter_id
                WHERE v.chapter_id = ? ORDER BY v.version DESC
                """,
                (chapter_id,),
            ).fetchall()
        return [self._version(row) for row in rows]

    def get_version(
        self, version_id: int, *, connection: sqlite3.Connection | None = None
    ) -> dict[str, Any]:
        if connection is None:
            with session(self.database_path) as owned:
                return self.get_version(version_id, connection=owned)
        row = connection.execute(
            """
            SELECT v.*, CASE WHEN h.current_version_id = v.id THEN 1 ELSE 0 END AS is_current
            FROM chapter_rewrite_versions v
            LEFT JOIN chapter_rewrites h ON h.chapter_id = v.chapter_id
            WHERE v.id = ?
            """,
            (version_id,),
        ).fetchone()
        if row is None:
            raise FileNotFoundError(f"Chapter rewrite version not found: {version_id}")
        return self._version(row)

    def restore_version(self, version_id: int) -> dict[str, Any]:
        with session(self.database_path) as connection:
            source = self.get_version(version_id, connection=connection)
            expected_head = self.get_current_head_id(
                int(source["chapter_id"]), connection=connection
            )
            return self.append_chapter_rewrite_version(
                connection,
                chapter_id=int(source["chapter_id"]),
                rewritten_text=str(source["rewritten_text"]),
                source_operation="restore",
                source_run_id=None,
                source_base_kind="rewrite_version",
                source_base_version_id=version_id,
                source_hash=str(source["content_hash"]),
                facts_before=source["facts_before"],
                facts_after=source["facts_after"],
                require_head_match=True,
                expected_head_version_id=expected_head,
                source_kind="manual",
            )

    @staticmethod
    def _original_facts(
        connection: sqlite3.Connection, chapter_id: int
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        rows = connection.execute(
            """
            SELECT s.id FROM scenes s
            WHERE s.chapter_id = ? AND s.deleted_at IS NULL
            ORDER BY s.scene_index, s.id
            """,
            (chapter_id,),
        ).fetchall()
        facts: list[dict[str, Any]] = []
        for row in rows:
            ledger = connection.execute(
                """
                SELECT facts_json FROM scene_fact_ledgers
                WHERE scene_id = ? ORDER BY ledger_version DESC LIMIT 1
                """,
                (row["id"],),
            ).fetchone()
            if ledger is not None:
                facts.append(_json_object(ledger["facts_json"]))
        return ({}, facts[-1] if facts else {})

    @staticmethod
    def _version(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        result["facts_before"] = _json_object(row["facts_before_json"])
        result["facts_after"] = _json_object(row["facts_after_json"])
        result["is_current"] = bool(result.get("is_current"))
        return result


class SourceVersionConflict(ValueError):
    def __init__(
        self,
        *,
        chapter_id: int,
        expected_version_id: int | None,
        current_version_id: int | None,
    ) -> None:
        self.chapter_id = chapter_id
        self.expected_version_id = expected_version_id
        self.current_version_id = current_version_id
        super().__init__("Chapter source head changed after the workflow run started.")


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _json_object(value: Any) -> dict[str, Any]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
