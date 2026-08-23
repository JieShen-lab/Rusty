from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rusty.content_hash import hash_text
from rusty.db import session
from rusty.models import count_text_units


@dataclass(frozen=True)
class ChapterSourceSnapshot:
    chapter_id: int
    project_id: int
    source_kind: str
    source_version_id: int | None
    text: str
    content_hash: str
    expected_head_version_id: int | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ChapterVersionService:
    """Immutable chapter edits with one explicit current-version projection."""

    def __init__(self, database_path: str | Path) -> None:
        self.database_path = Path(database_path)

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
            "SELECT id,project_id,original_text FROM chapters WHERE id=?", (chapter_id,)
        ).fetchone()
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        head = connection.execute(
            "SELECT current_version_id FROM chapter_rewrites WHERE chapter_id=?", (chapter_id,)
        ).fetchone()
        head_id = int(head["current_version_id"]) if head and head["current_version_id"] else None
        selected = None
        if kind == "current" and head_id is not None:
            selected = connection.execute(
                "SELECT id,rewritten_text,content_hash FROM chapter_rewrite_versions WHERE id=? AND chapter_id=?",
                (head_id, chapter_id),
            ).fetchone()
        elif kind == "rewrite_version":
            version_id = selection.get("version_id")
            if not isinstance(version_id, int):
                raise ValueError("rewrite_version source requires version_id.")
            selected = connection.execute(
                "SELECT id,rewritten_text,content_hash FROM chapter_rewrite_versions WHERE id=? AND chapter_id=?",
                (version_id, chapter_id),
            ).fetchone()
            if selected is None:
                raise ValueError("Rewrite source version does not belong to the chapter.")
        if selected is not None:
            return ChapterSourceSnapshot(
                int(chapter["id"]), int(chapter["project_id"]), "rewrite_version",
                int(selected["id"]), str(selected["rewritten_text"]), str(selected["content_hash"]), head_id,
            )
        original = str(chapter["original_text"])
        return ChapterSourceSnapshot(
            int(chapter["id"]), int(chapter["project_id"]), "original", None,
            original, hash_text(original), head_id,
        )

    def append_chapter_rewrite_version(
        self,
        connection: sqlite3.Connection,
        *,
        chapter_id: int,
        rewritten_text: str,
        source_base_kind: str,
        source_base_version_id: int | None,
        source_hash: str,
        expected_head_version_id: int | None,
        source_kind: str,
    ) -> dict[str, Any]:
        text = rewritten_text.strip()
        if not text:
            raise ValueError("A chapter rewrite version cannot be empty.")
        chapter = connection.execute(
            "SELECT project_id,original_text,word_count FROM chapters WHERE id=?", (chapter_id,)
        ).fetchone()
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        current = connection.execute(
            "SELECT current_version_id FROM chapter_rewrites WHERE chapter_id=?", (chapter_id,)
        ).fetchone()
        current_id = int(current["current_version_id"]) if current and current["current_version_id"] else None
        if current_id != expected_head_version_id:
            raise SourceVersionConflict(chapter_id, expected_head_version_id, current_id)
        if source_base_kind == "original":
            if source_base_version_id is not None or hash_text(str(chapter["original_text"])) != source_hash:
                raise ValueError("Original chapter source mismatch.")
        elif source_base_kind == "rewrite_version":
            parent = connection.execute(
                "SELECT content_hash FROM chapter_rewrite_versions WHERE id=? AND chapter_id=?",
                (source_base_version_id, chapter_id),
            ).fetchone()
            if parent is None or str(parent["content_hash"]) != source_hash:
                raise ValueError("Rewrite chapter source mismatch.")
        else:
            raise ValueError("Unsupported chapter source kind.")
        version = int(connection.execute(
            "SELECT COALESCE(MAX(version),0)+1 FROM chapter_rewrite_versions WHERE chapter_id=?",
            (chapter_id,),
        ).fetchone()[0])
        content_hash = hash_text(text)
        version_id = int(connection.execute(
            """INSERT INTO chapter_rewrite_versions(
                   project_id,chapter_id,version,parent_version_id,source_kind,source_base_kind,
                   source_base_version_id,source_hash,rewritten_text,content_hash
               ) VALUES(?,?,?,?,?,?,?,?,?,?)""",
            (
                int(chapter["project_id"]), chapter_id, version, source_base_version_id,
                source_kind, source_base_kind, source_base_version_id, source_hash, text, content_hash,
            ),
        ).lastrowid)
        word_count = count_text_units(text)
        ratio = word_count / int(chapter["word_count"]) if chapter["word_count"] else None
        connection.execute(
            """INSERT INTO chapter_rewrites(
                   chapter_id,current_version_id,rewritten_text,actual_word_count,expansion_ratio
               ) VALUES(?,?,?,?,?)
               ON CONFLICT(chapter_id) DO UPDATE SET
                   current_version_id=excluded.current_version_id,
                   rewritten_text=excluded.rewritten_text,
                   actual_word_count=excluded.actual_word_count,
                   expansion_ratio=excluded.expansion_ratio,
                   updated_at=CURRENT_TIMESTAMP""",
            (chapter_id, version_id, text, word_count, ratio),
        )
        connection.execute(
            "UPDATE chapters SET rewritten_text=?,status='rewritten',updated_at=CURRENT_TIMESTAMP WHERE id=?",
            (text, chapter_id),
        )
        return {
            "id": version_id,
            "chapter_id": chapter_id,
            "version": version,
            "source_kind": source_kind,
            "rewritten_text": text,
            "content_hash": content_hash,
            "is_current": True,
        }


class SourceVersionConflict(ValueError):
    def __init__(self, chapter_id: int, expected_version_id: int | None, current_version_id: int | None) -> None:
        super().__init__(
            f"Chapter {chapter_id} source changed: expected {expected_version_id}, current {current_version_id}."
        )
        self.chapter_id = chapter_id
        self.expected_version_id = expected_version_id
        self.current_version_id = current_version_id
