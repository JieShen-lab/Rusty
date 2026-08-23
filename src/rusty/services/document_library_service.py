from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
from dataclasses import dataclass, replace
from pathlib import Path

from rusty.chapter_titles import format_chapter_heading, normalize_chapter_title
from rusty.db import session
from rusty.exporters import build_txt_export, export_epub
from rusty.importers import parse_docx, parse_epub, parse_txt, split_document_structure
from rusty.importers.txt import read_text_with_encoding
from rusty.models import ChapterRecord, ParsedBook, ParsedChapter, ParsedVolume, count_text_units


SUPPORTED_DOCUMENT_SUFFIXES = {".txt", ".epub", ".docx"}
DOCUMENT_COVER_PALETTES = ("indigo", "terracotta", "jade", "slate", "ochre", "plum", "bluegray")


@dataclass(frozen=True)
class LibraryDocument:
    id: int
    title: str
    author: str | None
    description: str | None
    source_filename: str
    source_format: str
    storage_path: str
    source_size_bytes: int
    stored_size_bytes: int
    chapter_count: int
    word_count: int
    cover_palette: str
    status: str
    favorite: bool
    is_project_document: bool
    category_ids: list[int]
    categories: list[str]
    project_ids: list[int]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DocumentImportResult:
    document: LibraryDocument
    created: bool


@dataclass(frozen=True)
class DocumentRevision:
    id: int
    document_id: int
    revision_number: int
    revision_type: str
    storage_path: str
    parent_revision_id: int | None
    created_at: str


@dataclass(frozen=True)
class CleanupResult:
    document: LibraryDocument
    revision: DocumentRevision
    created: bool
    created_chapter_id: int | None = None


class DraftConflictError(RuntimeError):
    """Raised when a draft no longer targets the active document revision."""


@dataclass(frozen=True)
class LibraryDocumentDraft:
    id: int
    document_id: int
    chapter_id: int | None
    base_revision_id: int
    title: str
    text: str
    updated_at: str


@dataclass(frozen=True)
class LibraryCategory:
    id: int
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int


@dataclass(frozen=True)
class LibraryChapter:
    id: int
    revision_id: int
    index: int
    title: str
    start_line: int | None
    end_line: int | None
    start_offset: int | None
    end_offset: int | None
    word_count: int
    volume_id: int | None = None


@dataclass(frozen=True)
class LibraryVolume:
    id: int
    revision_id: int
    index: int
    title: str
    start_offset: int
    end_offset: int
    word_count: int


@dataclass(frozen=True)
class LibraryDocumentDirectory:
    volumes: list[tuple[LibraryVolume, list[LibraryChapter]]]
    unassigned_chapters: list[LibraryChapter]


@dataclass(frozen=True)
class LibraryDocumentContent:
    document_id: int
    revision_id: int
    chapter_id: int | None
    title: str
    text: str
    body_text: str
    section_start_offset: int
    body_start_offset: int
    end_offset: int
    start_offset: int


def default_document_library_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Rusty" / "document-library"


def _validate_continuous_boundaries(
    text: str,
    boundaries: list[dict[str, object]],
) -> list[dict[str, object]]:
    if not boundaries:
        raise ValueError("At least one chapter boundary is required.")
    normalized = sorted(
        (
            {
                "title": str(item.get("title") or "").strip(),
                "start_offset": int(item.get("start_offset", -1)),
                "end_offset": int(item.get("end_offset", -1)),
                "reason": str(item.get("reason") or ""),
            }
            for item in boundaries
        ),
        key=lambda item: int(item["start_offset"]),
    )
    expected_start = 0
    for index, item in enumerate(normalized):
        if not item["title"]:
            raise ValueError(f"Chapter {index + 1} requires a title.")
        start, end = int(item["start_offset"]), int(item["end_offset"])
        if start != expected_start or end <= start or end > len(text):
            raise ValueError(
                "Chapter boundaries must be continuous, non-overlapping, and cover the source exactly."
            )
        expected_start = end
    if expected_start != len(text):
        raise ValueError("Chapter boundaries omit source text.")
    return normalized


class DocumentLibraryService:
    def __init__(
        self,
        database_path: str | Path,
        library_path: str | Path | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        configured_path = os.environ.get("RUSTY_DOCUMENT_LIBRARY_PATH")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT storage_path FROM document_library_settings WHERE id = 1"
            ).fetchone()
        stored_path = str(row["storage_path"]) if row is not None else None
        self.library_path = Path(library_path or configured_path or stored_path or default_document_library_path())

    def list_documents(self) -> list[LibraryDocument]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT d.*,
                       COALESCE((
                           SELECT GROUP_CONCAT(categories.id, char(31))
                           FROM document_category_links links
                           JOIN document_categories categories ON categories.id = links.category_id
                           WHERE links.document_id = d.id AND categories.deleted_at IS NULL
                       ), '') AS category_ids,
                       COALESCE((
                           SELECT GROUP_CONCAT(categories.name, char(31))
                           FROM document_category_links links
                           JOIN document_categories categories ON categories.id = links.category_id
                           WHERE links.document_id = d.id AND categories.deleted_at IS NULL
                       ), '') AS category_names,
                       EXISTS(
                           SELECT 1 FROM project_documents projects
                           WHERE projects.document_id = d.id
                       ) AS is_project_document,
                       COALESCE((
                           SELECT GROUP_CONCAT(projects.project_id, char(31))
                           FROM project_documents projects
                           WHERE projects.document_id = d.id
                       ), '') AS project_ids
                FROM library_documents d
                WHERE d.deleted_at IS NULL
                ORDER BY d.created_at DESC, d.id DESC
                """
            ).fetchall()
        return [self._row_to_document(row) for row in rows]

    def update_document_metadata(
        self,
        document_id: int,
        *,
        title: str,
        author: str | None,
    ) -> LibraryDocument:
        self._ensure_content_mutable(document_id)
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("文档名称不能为空。")
        normalized_author = author.strip() if author and author.strip() else None
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE library_documents
                SET title = ?, author = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (normalized_title, normalized_author, document_id),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"找不到文档：{document_id}")
        return self._get_document(document_id)

    def get_library_path(self) -> Path:
        return self.library_path

    def migrate_library_path(self, target_path: str | Path) -> Path:
        destination = Path(target_path).expanduser().resolve()
        if destination.exists() and not destination.is_dir():
            raise ValueError("文档目录必须是文件夹。")
        destination.mkdir(parents=True, exist_ok=True)
        if destination == self.library_path.expanduser().resolve():
            return destination

        with session(self.database_path) as connection:
            rows = connection.execute(
                "SELECT id, storage_path, content_hash FROM library_document_revisions ORDER BY id"
            ).fetchall()

        path_map: dict[str, str] = {}
        copied_paths: list[Path] = []
        for row in rows:
            source = Path(str(row["storage_path"])).expanduser().resolve()
            source_key = str(source)
            if source_key in path_map:
                continue
            if not source.is_file():
                raise FileNotFoundError(f"迁移失败，找不到版本文件：{source}")
            target = self._available_migration_path(destination / source.name, str(row["content_hash"]))
            if target != source:
                temporary = target.with_suffix(target.suffix + ".migrating")
                shutil.copy2(source, temporary)
                if hashlib.sha256(temporary.read_bytes()).hexdigest() != hashlib.sha256(source.read_bytes()).hexdigest():
                    temporary.unlink(missing_ok=True)
                    raise ValueError(f"迁移校验失败：{source.name}")
                temporary.replace(target)
                copied_paths.append(target)
            path_map[source_key] = str(target)

        try:
            with session(self.database_path) as connection:
                for old_path, new_path in path_map.items():
                    connection.execute(
                        "UPDATE library_document_revisions SET storage_path = ? WHERE storage_path = ?",
                        (new_path, old_path),
                    )
                    connection.execute(
                        "UPDATE library_documents SET storage_path = ? WHERE storage_path = ?",
                        (new_path, old_path),
                    )
                connection.execute(
                    """
                    INSERT INTO document_library_settings (id, storage_path, updated_at)
                    VALUES (1, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(id) DO UPDATE SET
                        storage_path = excluded.storage_path,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (str(destination),),
                )
        except Exception:
            for copied in copied_paths:
                copied.unlink(missing_ok=True)
            raise

        for old_path, new_path in path_map.items():
            source = Path(old_path)
            if str(source) != new_path:
                source.unlink(missing_ok=True)
        self.library_path = destination
        return destination

    def list_categories(self) -> list[LibraryCategory]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT category.id, category.name, category.normalized_name,
                       category.sort_order, COUNT(document.id) AS document_count
                FROM document_categories category
                LEFT JOIN document_category_links links ON links.category_id = category.id
                LEFT JOIN library_documents document
                  ON document.id = links.document_id AND document.deleted_at IS NULL
                WHERE category.deleted_at IS NULL
                GROUP BY category.id
                ORDER BY category.sort_order, category.name
                """
            ).fetchall()
        return [
            LibraryCategory(
                id=int(row["id"]),
                name=str(row["name"]),
                normalized_name=str(row["normalized_name"]),
                sort_order=int(row["sort_order"]),
                resource_count=int(row["document_count"]),
            )
            for row in rows
        ]

    def create_category(self, name: str) -> LibraryCategory:
        display_name, normalized_name = self._normalize_category_name(name)
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO document_categories (name, normalized_name)
                VALUES (?, ?)
                ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
                DO UPDATE SET updated_at = CURRENT_TIMESTAMP
                """,
                (display_name, normalized_name),
            )
        return next(
            category
            for category in self.list_categories()
            if category.normalized_name == normalized_name
        )

    def rename_category(self, category_id: int, name: str) -> LibraryCategory:
        display_name, normalized_name = self._normalize_category_name(name)
        try:
            with session(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    UPDATE document_categories
                    SET name = ?, normalized_name = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND deleted_at IS NULL
                    """,
                    (display_name, normalized_name, category_id),
                )
                if cursor.rowcount == 0:
                    raise FileNotFoundError(f"找不到文档分类：{category_id}")
        except sqlite3.IntegrityError as exc:
            raise ValueError(f"文档分类“{display_name}”已存在。") from exc
        return next(category for category in self.list_categories() if category.id == category_id)

    def delete_category(self, category_id: int) -> None:
        with session(self.database_path) as connection:
            connection.execute(
                "DELETE FROM document_category_links WHERE category_id = ?",
                (category_id,),
            )
            cursor = connection.execute(
                """
                UPDATE document_categories
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (category_id,),
            )
            if cursor.rowcount == 0:
                raise FileNotFoundError(f"找不到文档分类：{category_id}")

    def import_document(self, source_path: str | Path) -> DocumentImportResult:
        path = Path(source_path).expanduser().resolve()
        if path.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
            raise ValueError("仅支持 TXT、EPUB 和 DOCX 文档。")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"找不到源文件：{path}")

        source_size = path.stat().st_size
        source_format = path.suffix.lower().lstrip(".")
        book, text = self._read_source(path)
        normalized_text = self._normalize_text(text)
        encoded_text = normalized_text.encode("utf-8")
        content_hash = hashlib.sha256(encoded_text).hexdigest()

        existing = self._find_by_hash(content_hash)
        if existing is not None and Path(existing.storage_path).is_file():
            return DocumentImportResult(document=existing, created=False)

        self.library_path.mkdir(parents=True, exist_ok=True)
        safe_title = self._safe_filename(book.title or path.stem)
        storage_path = self._allocate_storage_path(safe_title, content_hash)
        temporary_path = storage_path.with_suffix(".tmp")
        temporary_path.write_bytes(encoded_text)
        temporary_path.replace(storage_path)

        metadata = {
            **(book.metadata or {}),
            "language": book.language,
            "publisher": book.publisher,
            "source_identifier": book.source_identifier,
            "source_encoding": book.source_encoding,
        }
        try:
            with session(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO library_documents (
                        title, author, description, source_filename, source_format,
                        storage_path, content_hash, source_size_bytes, stored_size_bytes,
                        chapter_count, word_count, source_metadata_json, cover_palette
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        book.title or path.stem,
                        book.author,
                        book.description,
                        path.name,
                        source_format,
                        str(storage_path),
                        content_hash,
                        source_size,
                        len(encoded_text),
                        len(book.chapters),
                        count_text_units(normalized_text),
                        json.dumps(metadata, ensure_ascii=False),
                        secrets.choice(DOCUMENT_COVER_PALETTES),
                    ),
                )
                document_id = int(cursor.lastrowid)
                revision_cursor = connection.execute(
                    """
                    INSERT INTO library_document_revisions (
                        document_id, revision_number, revision_type, storage_path,
                        content_hash, metadata_json
                    ) VALUES (?, 1, 'import', ?, ?, ?)
                    """,
                    (
                        document_id,
                        str(storage_path),
                        content_hash,
                        json.dumps({"source_format": source_format}, ensure_ascii=False),
                    ),
                )
                revision_id = int(revision_cursor.lastrowid)
                connection.execute(
                    "UPDATE library_documents SET current_revision_id = ? WHERE id = ?",
                    (revision_id, document_id),
                )
                self._insert_chapters(
                    connection,
                    document_id,
                    revision_id,
                    book.chapters,
                    book.volumes or [],
                )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        document = self._get_document(document_id)
        return DocumentImportResult(document=document, created=True)

    def ensure_project_document(self, project_id: int, source_path: str | Path) -> LibraryDocument:
        result = self.import_document(source_path)
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT id FROM projects WHERE id = ? AND deleted_at IS NULL",
                (project_id,),
            ).fetchone()
            if project is None:
                raise FileNotFoundError(f"找不到工程：{project_id}")
            connection.execute(
                """
                INSERT INTO project_documents (project_id, document_id)
                VALUES (?, ?)
                ON CONFLICT(project_id) DO UPDATE SET document_id = excluded.document_id
                """,
                (project_id, result.document.id),
            )
        return self._get_document(result.document.id)

    def list_revisions(self, document_id: int) -> list[DocumentRevision]:
        self._ensure_initial_revision(document_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM library_document_revisions
                WHERE document_id = ?
                ORDER BY revision_number DESC
                """,
                (document_id,),
            ).fetchall()
        return [self._row_to_revision(row) for row in rows]

    def list_chapters(self, document_id: int) -> list[LibraryChapter]:
        revision = self._ensure_initial_revision(document_id)
        text = Path(revision.storage_path).read_text(encoding="utf-8")
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM library_document_chapters
                WHERE revision_id = ?
                ORDER BY chapter_index
                """,
                (revision.id,),
            ).fetchall()
        chapters = [
            LibraryChapter(
                id=int(row["id"]),
                revision_id=int(row["revision_id"]),
                index=int(row["chapter_index"]),
                title=normalize_chapter_title(str(row["title"])),
                start_line=int(row["start_line"]) if row["start_line"] is not None else None,
                end_line=int(row["end_line"]) if row["end_line"] is not None else None,
                start_offset=int(row["start_offset"]) if row["start_offset"] is not None else None,
                end_offset=int(row["end_offset"]) if row["end_offset"] is not None else None,
                word_count=int(row["word_count"]),
                volume_id=int(row["volume_id"]) if row["volume_id"] is not None else None,
            )
            for row in rows
        ]
        result: list[LibraryChapter] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(text, chapter)
            body_start = self._chapter_body_start(text, chapter, start, end)
            result.append(replace(chapter, word_count=count_text_units(text[body_start:end])))
        return result

    def list_volumes(self, document_id: int) -> list[LibraryVolume]:
        revision = self._ensure_initial_revision(document_id)
        text = Path(revision.storage_path).read_text(encoding="utf-8")
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM library_document_volumes
                WHERE revision_id = ?
                ORDER BY volume_index
                """,
                (revision.id,),
            ).fetchall()
        return [
            LibraryVolume(
                id=int(row["id"]),
                revision_id=int(row["revision_id"]),
                index=int(row["volume_index"]),
                title=str(row["title"]),
                start_offset=int(row["start_offset"]),
                end_offset=int(row["end_offset"]),
                word_count=count_text_units(
                    text[int(row["start_offset"]):int(row["end_offset"])]
                ),
            )
            for row in rows
        ]

    def get_directory(self, document_id: int) -> LibraryDocumentDirectory:
        volumes = self.list_volumes(document_id)
        chapters = self.list_chapters(document_id)
        by_volume: dict[int, list[LibraryChapter]] = {
            volume.id: [] for volume in volumes
        }
        unassigned: list[LibraryChapter] = []
        for chapter in chapters:
            if chapter.volume_id is not None and chapter.volume_id in by_volume:
                by_volume[chapter.volume_id].append(chapter)
            else:
                unassigned.append(chapter)
        return LibraryDocumentDirectory(
            volumes=[(volume, by_volume[volume.id]) for volume in volumes],
            unassigned_chapters=unassigned,
        )

    def reorder_chapters(
        self,
        document_id: int,
        ordered_chapter_ids: list[int],
        volume_assignments: dict[int, int | None] | None = None,
    ) -> list[LibraryChapter]:
        self._ensure_content_mutable(document_id)
        revision = self._ensure_initial_revision(document_id)
        chapters = self.list_chapters(document_id)
        existing_ids = {chapter.id for chapter in chapters}
        if len(ordered_chapter_ids) != len(existing_ids) or set(ordered_chapter_ids) != existing_ids:
            raise ValueError("章节顺序必须包含当前版本的全部章节且不能重复。")
        valid_volume_ids = {volume.id for volume in self.list_volumes(document_id)}
        for chapter_id, volume_id in (volume_assignments or {}).items():
            if chapter_id not in existing_ids:
                raise ValueError(f"章节不属于当前版本：{chapter_id}")
            if volume_id is not None and volume_id not in valid_volume_ids:
                raise ValueError(f"卷不属于当前版本：{volume_id}")
        with session(self.database_path) as connection:
            for chapter_id in ordered_chapter_ids:
                connection.execute(
                    """
                    UPDATE library_document_chapters
                    SET chapter_index = ?
                    WHERE id = ? AND document_id = ? AND revision_id = ?
                    """,
                    (-chapter_id, chapter_id, document_id, revision.id),
                )
            for chapter_index, chapter_id in enumerate(ordered_chapter_ids, start=1):
                connection.execute(
                    """
                    UPDATE library_document_chapters
                    SET chapter_index = ?
                    WHERE id = ? AND document_id = ? AND revision_id = ?
                    """,
                    (chapter_index, chapter_id, document_id, revision.id),
                )
            for chapter_id, volume_id in (volume_assignments or {}).items():
                connection.execute(
                    """
                    UPDATE library_document_chapters
                    SET volume_id = ?
                    WHERE id = ? AND document_id = ? AND revision_id = ?
                    """,
                    (volume_id, chapter_id, document_id, revision.id),
                )
        return self.list_chapters(document_id)

    def delete_document(self, document_id: int) -> None:
        self._get_document(document_id)
        with session(self.database_path) as connection:
            connection.execute(
                """
                UPDATE library_documents
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (document_id,),
            )

    def get_content(self, document_id: int, chapter_id: int | None = None) -> LibraryDocumentContent:
        document = self._get_document(document_id)
        revision = self._ensure_initial_revision(document_id)
        source_text = Path(revision.storage_path).read_text(encoding="utf-8")
        if chapter_id is None:
            return LibraryDocumentContent(
                document_id=document.id,
                revision_id=revision.id,
                chapter_id=None,
                title=document.title,
                text=source_text,
                body_text=source_text,
                section_start_offset=0,
                body_start_offset=0,
                end_offset=len(source_text),
                start_offset=0,
            )

        chapter = next((item for item in self.list_chapters(document_id) if item.id == chapter_id), None)
        if chapter is None:
            raise FileNotFoundError(f"找不到当前版本的章节：{chapter_id}")
        section_start, end_offset = self._chapter_offsets(source_text, chapter)
        body_start = self._chapter_body_start(source_text, chapter, section_start, end_offset)
        body_text = source_text[body_start:end_offset]
        return LibraryDocumentContent(
            document_id=document.id,
            revision_id=revision.id,
            chapter_id=chapter.id,
            title=chapter.title,
            text=source_text[section_start:end_offset],
            body_text=body_text,
            section_start_offset=section_start,
            body_start_offset=body_start,
            end_offset=end_offset,
            start_offset=section_start,
        )

    def get_draft(self, document_id: int, chapter_id: int | None = None) -> LibraryDocumentDraft | None:
        self._get_document(document_id)
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT * FROM library_document_drafts
                WHERE document_id = ?
                  AND ((? IS NULL AND chapter_id IS NULL) OR chapter_id = ?)
                """,
                (document_id, chapter_id, chapter_id),
            ).fetchone()
        if row is None:
            return None
        return LibraryDocumentDraft(
            id=int(row["id"]),
            document_id=int(row["document_id"]),
            chapter_id=int(row["chapter_id"]) if row["chapter_id"] is not None else None,
            base_revision_id=int(row["base_revision_id"]),
            title=str(row["title"]),
            text=str(row["text"]),
            updated_at=str(row["updated_at"]),
        )

    def save_draft(
        self,
        document_id: int,
        *,
        base_revision_id: int,
        title: str,
        text: str,
        chapter_id: int | None = None,
    ) -> LibraryDocumentDraft:
        self._ensure_content_mutable(document_id)
        document = self._get_document(document_id)
        current = self._ensure_initial_revision(document_id)
        if current.id != base_revision_id:
            raise DraftConflictError(
                f"Draft base revision {base_revision_id} is stale; current revision is {current.id}."
            )
        normalized_title = title.strip()
        if chapter_id is None:
            if not normalized_title:
                normalized_title = document.title
        else:
            chapter = next((item for item in self.list_chapters(document_id) if item.id == chapter_id), None)
            if chapter is None:
                raise FileNotFoundError(f"找不到当前版本的章节：{chapter_id}")
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        with session(self.database_path) as connection:
            existing = connection.execute(
                """
                SELECT id FROM library_document_drafts
                WHERE document_id = ?
                  AND ((? IS NULL AND chapter_id IS NULL) OR chapter_id = ?)
                """,
                (document_id, chapter_id, chapter_id),
            ).fetchone()
            if existing is None:
                cursor = connection.execute(
                    """
                    INSERT INTO library_document_drafts (
                        document_id, chapter_id, base_revision_id, title, text
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (document_id, chapter_id, base_revision_id, normalized_title, normalized_text),
                )
                draft_id = int(cursor.lastrowid)
            else:
                draft_id = int(existing["id"])
                connection.execute(
                    """
                    UPDATE library_document_drafts
                    SET base_revision_id = ?, title = ?, text = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (base_revision_id, normalized_title, normalized_text, draft_id),
                )
        draft = self.get_draft(document_id, chapter_id)
        if draft is None:
            raise RuntimeError(f"Draft {draft_id} was not persisted.")
        return draft

    def commit_draft(self, document_id: int, chapter_id: int | None = None) -> CleanupResult:
        self._ensure_content_mutable(document_id)
        draft = self.get_draft(document_id, chapter_id)
        if draft is None:
            raise FileNotFoundError("No saved draft exists for this document scope.")
        current = self._ensure_initial_revision(document_id)
        if current.id != draft.base_revision_id:
            raise DraftConflictError(
                f"Draft base revision {draft.base_revision_id} is stale; current revision is {current.id}."
            )
        result = self._commit_content(
            document_id,
            text=draft.text,
            title=draft.title,
            chapter_id=chapter_id,
            draft_id=draft.id,
            draft_base_revision_id=draft.base_revision_id,
        )
        return result

    def rename_volume(self, document_id: int, volume_id: int, title: str) -> CleanupResult:
        self._ensure_content_mutable(document_id)
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("卷标题不能为空。")
        document = self._get_document(document_id)
        current = self._ensure_initial_revision(document_id)
        text = Path(current.storage_path).read_text(encoding="utf-8")
        volumes = self.list_volumes(document_id)
        target = next((volume for volume in volumes if volume.id == volume_id), None)
        if target is None:
            raise FileNotFoundError(f"找不到卷：{volume_id}")
        title_start = target.start_offset
        title_end = text.find("\n", title_start, target.end_offset)
        if title_end < 0:
            title_end = target.end_offset
        if text[title_start:title_end].strip() != target.title.strip():
            raise ValueError("卷标题不再对应当前版本文本，请重新加载后再试。")
        replacement = normalized_title
        new_text = text[:title_start] + replacement + text[title_end:]
        delta = len(replacement) - (title_end - title_start)
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        chapter_boundaries = []
        for chapter in self.list_chapters(document_id):
            start, end = self._chapter_offsets(text, chapter)
            if start >= title_end:
                start += delta
                end += delta
            chapter_boundaries.append(
                {
                    "title": chapter.title,
                    "start_offset": start,
                    "end_offset": end,
                    "volume_index": volume_index_by_id.get(chapter.volume_id),
                }
            )
        volume_boundaries = self._shift_volume_boundaries(
            volumes,
            title_start,
            title_end,
            delta,
        )
        for boundary in volume_boundaries:
            if int(boundary["volume_index"]) == target.index:
                boundary["title"] = normalized_title
                break
        revision = self._create_text_revision(
            document,
            current,
            new_text,
            "manual_edit",
            {"operation": "rename_volume", "source_volume_id": volume_id},
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=volume_boundaries,
        )
        return CleanupResult(
            document=self._get_document(document_id),
            revision=revision,
            created=True,
        )

    def create_volume(self, document_id: int, chapter_id: int, title: str) -> CleanupResult:
        """Start a new volume at an existing chapter and preserve the remaining hierarchy."""
        self._ensure_content_mutable(document_id)
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("卷标题不能为空。")
        document = self._get_document(document_id)
        current = self._ensure_initial_revision(document_id)
        source_text = Path(current.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
        if target is None:
            raise FileNotFoundError(f"找不到章节：{chapter_id}")
        volumes = self.list_volumes(document_id)
        target_start, _ = self._chapter_offsets(source_text, target)
        current_volume = next(
            (volume for volume in volumes if volume.id == target.volume_id),
            None,
        )
        if current_volume is not None:
            first_in_volume = next(
                (chapter for chapter in chapters if chapter.volume_id == current_volume.id),
                None,
            )
            if first_in_volume is not None and first_in_volume.id == target.id:
                raise ValueError("所选章节已经是当前卷的第一章。")

        leading_separator = "\n\n" if target_start > 0 and not source_text[:target_start].endswith("\n\n") else ""
        volume_heading = f"{normalized_title}\n\n"
        inserted_text = leading_separator + volume_heading
        heading_start = target_start + len(leading_separator)
        delta = len(inserted_text)
        new_text = source_text[:target_start] + inserted_text + source_text[target_start:]
        next_volume_start = min(
            (volume.start_offset for volume in volumes if volume.start_offset > target_start),
            default=len(source_text),
        )
        new_volume_key = max((volume.index for volume in volumes), default=0) + 1
        volume_index_by_id = {volume.id: volume.index for volume in volumes}

        chapter_boundaries: list[dict[str, object]] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(source_text, chapter)
            source_start = start
            if start >= target_start:
                start += delta
                end += delta
            chapter_boundaries.append(
                {
                    "title": chapter.title,
                    "start_offset": start,
                    "end_offset": end,
                    "volume_index": (
                        new_volume_key
                        if target_start <= source_start < next_volume_start
                        else volume_index_by_id.get(chapter.volume_id)
                    ),
                }
            )

        volume_boundaries: list[dict[str, object]] = []
        for volume in volumes:
            start, end = volume.start_offset, volume.end_offset
            if start > target_start:
                start += delta
                end += delta
            elif start < target_start < end:
                end = heading_start
            volume_boundaries.append(
                {
                    "volume_index": volume.index,
                    "title": volume.title,
                    "start_offset": start,
                    "end_offset": end,
                }
            )
        volume_boundaries.append(
            {
                "volume_index": new_volume_key,
                "title": normalized_title,
                "start_offset": heading_start,
                "end_offset": next_volume_start + delta,
            }
        )
        revision = self._create_text_revision(
            document,
            current,
            new_text,
            "manual_edit",
            {"operation": "create_volume", "source_chapter_id": chapter_id},
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=volume_boundaries,
        )
        return CleanupResult(
            document=self._get_document(document_id),
            revision=revision,
            created=True,
        )

    def _commit_content(
        self,
        document_id: int,
        *,
        text: str,
        title: str,
        chapter_id: int | None,
        draft_id: int,
        draft_base_revision_id: int,
        revision_type: str = "manual_edit",
        metadata: dict[str, object] | None = None,
    ) -> CleanupResult:
        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        if chapter_id is None:
            new_text = self._normalize_text(text)
            chapter_boundaries = None
            volume_boundaries = None
        else:
            normalized_title = normalize_chapter_title(title)
            source_text = Path(current_revision.storage_path).read_text(encoding="utf-8")
            chapters = self.list_chapters(document_id)
            volumes = self.list_volumes(document_id)
            volume_index_by_id = {volume.id: volume.index for volume in volumes}
            target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
            if target is None:
                raise FileNotFoundError(f"找不到章节：{chapter_id}")
            start, end = self._chapter_offsets(source_text, target)
            normalized_body = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
            body_start = self._chapter_body_start(source_text, target, start, end)
            if body_start > start:
                segment = source_text[start:end]
                leading_prefix = segment[: len(segment) - len(segment.lstrip("\n"))]
                trailing_separator = "\n" if end == len(source_text) else "\n\n"
                heading = format_chapter_heading(target.index, normalized_title)
                replacement = f"{leading_prefix}{heading}\n\n{normalized_body}{trailing_separator}"
            else:
                replacement = self._normalize_text(text)
            new_text = source_text[:start] + replacement + source_text[end:]
            delta = len(replacement) - (end - start)
            chapter_boundaries = []
            for chapter in chapters:
                chapter_start, chapter_end = self._chapter_offsets(source_text, chapter)
                if chapter.id == target.id:
                    chapter_end = chapter_start + len(replacement)
                elif chapter_start >= end:
                    chapter_start += delta
                    chapter_end += delta
                chapter_boundaries.append(
                    {
                        "title": normalized_title if chapter.id == target.id else chapter.title,
                        "start_offset": chapter_start,
                        "end_offset": chapter_end,
                        "volume_index": volume_index_by_id.get(chapter.volume_id),
                    }
                )
            volume_boundaries = self._shift_volume_boundaries(
                volumes,
                start,
                end,
                delta,
            )
        revision = self._create_text_revision(
            document,
            current_revision,
            new_text,
            revision_type,
            metadata or {},
            chapter_boundaries=chapter_boundaries if chapter_id is not None else None,
            volume_boundaries=volume_boundaries if chapter_id is not None else None,
            consume_draft_id=draft_id,
            consume_draft_base_revision_id=draft_base_revision_id,
            consume_draft_chapter_id=chapter_id,
            document_title=title.strip() if chapter_id is None else None,
        )
        return CleanupResult(document=self._get_document(document_id), revision=revision, created=True)

    def apply_prompt_cleanup(
        self,
        document_id: int,
        *,
        chapter_id: int | None,
        title: str,
        cleaned_text: str,
        prompt: str,
    ) -> CleanupResult:
        """Persist prompt-driven cleanup as a new revision while preserving chapter structure."""
        self._ensure_content_mutable(document_id)
        content = self.get_content(document_id, chapter_id)
        draft = self.save_draft(
            document_id,
            base_revision_id=content.revision_id,
            title=title,
            text=cleaned_text,
            chapter_id=chapter_id,
        )
        return self._commit_content(
            document_id,
            text=draft.text,
            title=draft.title,
            chapter_id=chapter_id,
            draft_id=draft.id,
            draft_base_revision_id=draft.base_revision_id,
            revision_type="cleanup_ai",
            metadata={"prompt": prompt},
        )

    def apply_prompt_cleanup_batch(
        self,
        document_id: int,
        *,
        cleaned_chapters: dict[int, tuple[str, str]],
        prompt: str,
    ) -> CleanupResult:
        """Replace selected chapter bodies together in one complete-document revision."""
        self._ensure_content_mutable(document_id)
        if not cleaned_chapters:
            raise ValueError("至少需要一章成功的整理结果。")
        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        source_text = Path(current_revision.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        volumes = self.list_volumes(document_id)
        chapter_by_id = {chapter.id: chapter for chapter in chapters}
        missing = set(cleaned_chapters) - set(chapter_by_id)
        if missing:
            raise FileNotFoundError(f"找不到当前版本章节：{sorted(missing)}")
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        pieces: list[str] = []
        cursor = 0
        chapter_boundaries: list[dict[str, object]] = []
        edits: list[tuple[int, int, int]] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(source_text, chapter)
            pieces.append(source_text[cursor:start])
            new_start = sum(len(piece) for piece in pieces)
            if chapter.id in cleaned_chapters:
                title, cleaned_text = cleaned_chapters[chapter.id]
                normalized_title = normalize_chapter_title(title)
                normalized_body = cleaned_text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "").strip()
                body_start = self._chapter_body_start(source_text, chapter, start, end)
                if body_start > start:
                    segment = source_text[start:end]
                    leading_prefix = segment[: len(segment) - len(segment.lstrip("\n"))]
                    trailing_separator = "\n" if end == len(source_text) else "\n\n"
                    replacement = f"{leading_prefix}{format_chapter_heading(chapter.index, normalized_title)}\n\n{normalized_body}{trailing_separator}"
                else:
                    replacement = self._normalize_text(cleaned_text)
                segment_title = normalized_title
                edits.append((start, end, len(replacement)))
            else:
                replacement = source_text[start:end]
                segment_title = chapter.title
            pieces.append(replacement)
            new_end = new_start + len(replacement)
            chapter_boundaries.append(
                {
                    "title": segment_title,
                    "start_offset": new_start,
                    "end_offset": new_end,
                    "volume_index": volume_index_by_id.get(chapter.volume_id),
                }
            )
            cursor = end
        pieces.append(source_text[cursor:])
        new_text = "".join(pieces)

        def translated(offset: int, *, end: bool = False) -> int:
            delta = 0
            for edit_start, edit_end, replacement_length in edits:
                if offset >= edit_end:
                    delta += replacement_length - (edit_end - edit_start)
                    continue
                if offset > edit_start:
                    return edit_start + delta + (replacement_length if end else 0)
                break
            return offset + delta

        volume_boundaries = [
            {
                "volume_index": volume.index,
                "title": volume.title,
                "start_offset": translated(volume.start_offset),
                "end_offset": translated(volume.end_offset, end=True),
            }
            for volume in volumes
        ]
        revision = self._create_text_revision(
            document,
            current_revision,
            new_text,
            "cleanup_ai",
            {"prompt": prompt, "chapter_ids": sorted(cleaned_chapters)},
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=volume_boundaries,
            delete_draft_chapter_ids=list(cleaned_chapters),
        )
        return CleanupResult(document=self._get_document(document_id), revision=revision, created=True)

    def merge_documents(self, document_ids: list[int], title: str, author: str | None = None) -> LibraryDocument:
        if len(document_ids) < 2:
            raise ValueError("合并文档至少需要选择两份文档。")
        normalized_title = title.strip()
        if not normalized_title:
            raise ValueError("合并后的文档标题不能为空。")
        merged_parts: list[str] = []
        merged_length = 0
        chapter_boundaries: list[dict[str, object]] = []
        volume_boundaries: list[dict[str, object]] = []
        sources: list[dict[str, object]] = []
        next_volume_index = 1
        for merge_order, document_id in enumerate(document_ids, start=1):
            document = self._get_document(document_id)
            revision = self._ensure_initial_revision(document_id)
            source_text = Path(revision.storage_path).read_text(encoding="utf-8")
            separator = ""
            if merged_parts:
                current = "".join(merged_parts)
                separator = "" if current.endswith("\n\n") else ("\n" if current.endswith("\n") else "\n\n")
                merged_parts.append(separator)
                merged_length += len(separator)
            source_start = merged_length
            merged_parts.append(source_text)
            merged_length += len(source_text)
            volumes = self.list_volumes(document_id)
            volume_index_map: dict[int, int] = {}
            for volume in volumes:
                merged_index = next_volume_index
                next_volume_index += 1
                volume_index_map[volume.id] = merged_index
                volume_boundaries.append(
                    {
                        "volume_index": merged_index,
                        "title": volume.title,
                        "start_offset": source_start + volume.start_offset,
                        "end_offset": source_start + volume.end_offset,
                    }
                )
            chapters = self.list_chapters(document_id)
            if not chapters:
                chapter_boundaries.append(
                    {
                        "title": "第一章",
                        "start_offset": source_start,
                        "end_offset": source_start + len(source_text),
                        "volume_index": None,
                    }
                )
            else:
                for chapter in chapters:
                    start, end = self._chapter_offsets(source_text, chapter)
                    chapter_boundaries.append(
                        {
                            "title": chapter.title,
                            "start_offset": source_start + start,
                            "end_offset": source_start + end,
                            "volume_index": volume_index_map.get(chapter.volume_id),
                        }
                    )
            sources.append(
                {
                    "document_id": document.id,
                    "revision_id": revision.id,
                    "title": document.title,
                    "merge_order": merge_order,
                }
            )
        merged_text = self._normalize_text("".join(merged_parts))
        if chapter_boundaries:
            final_delta = len(merged_text) - merged_length
            if final_delta:
                last = max(chapter_boundaries, key=lambda item: int(item["end_offset"]))
                last["end_offset"] = int(last["end_offset"]) + final_delta
                containing_volume = last.get("volume_index")
                if containing_volume is not None:
                    volume = next(
                        item
                        for item in volume_boundaries
                        if int(item["volume_index"]) == int(containing_volume)
                    )
                    volume["end_offset"] = int(volume["end_offset"]) + final_delta
        encoded = merged_text.encode("utf-8")
        content_hash = hashlib.sha256(encoded).hexdigest()
        self.library_path.mkdir(parents=True, exist_ok=True)
        storage_path = self._allocate_storage_path(self._safe_filename(normalized_title), content_hash)
        temporary_path = storage_path.with_suffix(".tmp")
        temporary_path.write_bytes(encoded)
        temporary_path.replace(storage_path)
        try:
            with session(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO library_documents (
                        title, author, description, source_filename, source_format,
                        storage_path, content_hash, source_size_bytes, stored_size_bytes,
                        chapter_count, word_count, source_metadata_json, cover_palette, status
                    ) VALUES (?, ?, '', ?, 'txt', ?, ?, ?, ?, ?, ?, ?, ?, 'imported')
                    """,
                    (
                        normalized_title,
                        author.strip() if author and author.strip() else None,
                        f"{self._safe_filename(normalized_title)}.txt",
                        str(storage_path),
                        content_hash,
                        len(encoded),
                        len(encoded),
                        len(chapter_boundaries),
                        count_text_units(merged_text),
                        json.dumps({"merge_sources": sources}, ensure_ascii=False),
                        secrets.choice(DOCUMENT_COVER_PALETTES),
                    ),
                )
                document_id = int(cursor.lastrowid)
                revision_cursor = connection.execute(
                    """
                    INSERT INTO library_document_revisions (
                        document_id, revision_number, revision_type, storage_path, content_hash, metadata_json
                    ) VALUES (?, 1, 'merge', ?, ?, ?)
                    """,
                    (document_id, str(storage_path), content_hash, json.dumps({"sources": sources}, ensure_ascii=False)),
                )
                revision_id = int(revision_cursor.lastrowid)
                connection.execute("UPDATE library_documents SET current_revision_id = ? WHERE id = ?", (revision_id, document_id))
                volume_ids: dict[int, int] = {}
                for volume_index, boundary in enumerate(
                    sorted(volume_boundaries, key=lambda item: int(item["start_offset"])),
                    start=1,
                ):
                    volume_cursor = connection.execute(
                        """
                        INSERT INTO library_document_volumes (
                            document_id, revision_id, volume_index, title,
                            start_offset, end_offset
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            revision_id,
                            volume_index,
                            str(boundary["title"]),
                            int(boundary["start_offset"]),
                            int(boundary["end_offset"]),
                        ),
                    )
                    volume_ids[int(boundary["volume_index"])] = int(volume_cursor.lastrowid)
                for chapter_index, boundary in enumerate(
                    sorted(chapter_boundaries, key=lambda item: int(item["start_offset"])),
                    start=1,
                ):
                    start = int(boundary["start_offset"])
                    end = int(boundary["end_offset"])
                    connection.execute(
                        """
                        INSERT INTO library_document_chapters (
                            document_id, revision_id, chapter_index, title,
                            start_line, end_line, start_offset, end_offset,
                            word_count, volume_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            document_id,
                            revision_id,
                            chapter_index,
                            normalize_chapter_title(str(boundary["title"])),
                            merged_text.count("\n", 0, start) + 1,
                            merged_text.count("\n", 0, end) + 1,
                            start,
                            end,
                            count_text_units(merged_text[start:end]),
                            volume_ids.get(
                                int(boundary["volume_index"])
                                if boundary.get("volume_index") is not None
                                else -1
                            ),
                        ),
                    )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise
        return self._get_document(document_id)

    def create_chapter(
        self,
        document_id: int,
        *,
        title: str,
        text: str,
        position: str = "after",
        anchor_chapter_id: int | None = None,
    ) -> CleanupResult:
        self._ensure_content_mutable(document_id)
        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        source_text = Path(current_revision.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        volumes = self.list_volumes(document_id)
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        normalized_title = normalize_chapter_title(title)
        if position not in {"before", "after"}:
            raise ValueError("插入位置必须是 before 或 after。")
        insert_at = len(source_text)
        target: LibraryChapter | None = None
        if chapters:
            target = next((chapter for chapter in chapters if chapter.id == anchor_chapter_id), None)
            if target is None:
                raise FileNotFoundError(f"找不到锚点章节：{anchor_chapter_id}")
            start, end = self._chapter_offsets(source_text, target)
            insert_at = start if position == "before" else end
        insertion_index = (
            (target.index if position == "before" else target.index + 1)
            if target is not None
            else len(chapters) + 1
        )
        chapter_text = self._normalize_text(
            f"{format_chapter_heading(insertion_index, normalized_title)}\n\n{text.strip()}"
        )
        leading_separator = "\n\n" if insert_at > 0 and not source_text[:insert_at].endswith("\n\n") else ""
        trailing_separator = "" if chapter_text.endswith("\n") else "\n"
        inserted_text = leading_separator + chapter_text + trailing_separator
        inserted_start = insert_at
        inserted_end = inserted_start + len(inserted_text)
        delta = len(inserted_text)
        new_text = source_text[:insert_at] + inserted_text + source_text[insert_at:]
        chapter_boundaries: list[dict[str, object]] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(source_text, chapter)
            if start >= insert_at:
                start += delta
                end += delta
            chapter_boundaries.append(
                {
                    "title": chapter.title,
                    "start_offset": start,
                    "end_offset": end,
                    "volume_index": volume_index_by_id.get(chapter.volume_id),
                }
            )
        chapter_boundaries.append(
            {
                "title": normalized_title,
                "start_offset": inserted_start,
                "end_offset": inserted_end,
                "volume_index": volume_index_by_id.get(target.volume_id) if target else None,
            }
        )
        chapter_boundaries.sort(key=lambda item: int(item["start_offset"]))
        revision = self._create_text_revision(
            document,
            current_revision,
            new_text,
            "manual_edit",
            {"operation": "create_chapter"},
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=self._shift_volume_boundaries(
                volumes,
                insert_at,
                insert_at,
                delta,
            ),
        )
        created_chapter = next(
            (
                chapter
                for chapter in self.list_chapters(document_id)
                if chapter.start_offset == inserted_start and chapter.title == normalized_title
            ),
            None,
        )
        return CleanupResult(
            document=self._get_document(document_id),
            revision=revision,
            created=True,
            created_chapter_id=created_chapter.id if created_chapter else None,
        )

    def delete_chapter(self, document_id: int, chapter_id: int) -> CleanupResult:
        """Delete one chapter by creating a full replacement revision."""
        self._ensure_content_mutable(document_id)
        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        source_text = Path(current_revision.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
        if target is None:
            raise FileNotFoundError(f"找不到章节：{chapter_id}")
        volumes = self.list_volumes(document_id)
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        start, end = self._chapter_offsets(source_text, target)
        removed_length = end - start
        new_text = source_text[:start] + source_text[end:]
        chapter_boundaries: list[dict[str, object]] = []
        for chapter in chapters:
            if chapter.id == target.id:
                continue
            chapter_start, chapter_end = self._chapter_offsets(source_text, chapter)
            if chapter_start >= end:
                chapter_start -= removed_length
                chapter_end -= removed_length
            chapter_boundaries.append(
                {
                    "title": chapter.title,
                    "start_offset": chapter_start,
                    "end_offset": chapter_end,
                    "volume_index": volume_index_by_id.get(chapter.volume_id),
                }
            )
        volume_boundaries = self._shift_volume_boundaries(volumes, start, end, -removed_length)
        revision = self._create_text_revision(
            document,
            current_revision,
            new_text,
            "manual_edit",
            {
                "operation": "delete_chapter",
                "source_chapter_id": target.id,
                "chapter_title": target.title,
            },
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=[
                boundary
                for boundary in volume_boundaries
                if int(boundary["end_offset"]) > int(boundary["start_offset"])
            ],
            delete_draft_chapter_id=target.id,
        )
        return CleanupResult(
            document=self._get_document(document_id),
            revision=revision,
            created=True,
        )

    def split_chapter_at_cursor(
        self,
        document_id: int,
        *,
        chapter_id: int,
        cursor_offset: int,
        next_title: str,
    ) -> CleanupResult:
        """Split one chapter at a body-relative cursor without reparsing the document."""
        self._ensure_content_mutable(document_id)
        content = self.get_content(document_id, chapter_id)
        if cursor_offset <= 0 or cursor_offset >= len(content.body_text):
            raise ValueError("分章位置必须位于正文中间。")
        normalized_title = normalize_chapter_title(next_title)
        if not normalized_title:
            raise ValueError("下一章标题不能为空。")

        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        source_text = Path(current_revision.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        volumes = self.list_volumes(document_id)
        target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
        if target is None:
            raise FileNotFoundError(f"找不到章节：{chapter_id}")

        split_at = content.body_start_offset + cursor_offset
        heading = format_chapter_heading(target.index + 1, normalized_title)
        separator = "\n\n" if not source_text[:split_at].endswith("\n\n") else ""
        inserted_text = f"{separator}{heading}\n\n"
        new_text = source_text[:split_at] + inserted_text + source_text[split_at:]
        delta = len(inserted_text)
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        chapter_boundaries: list[dict[str, object]] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(source_text, chapter)
            if chapter.id == chapter_id:
                chapter_boundaries.extend(
                    [
                        {
                            "title": chapter.title,
                            "start_offset": start,
                            "end_offset": split_at,
                            "volume_index": volume_index_by_id.get(chapter.volume_id),
                        },
                        {
                            "title": normalized_title,
                            "start_offset": split_at,
                            "end_offset": end + delta,
                            "volume_index": volume_index_by_id.get(chapter.volume_id),
                        },
                    ]
                )
            else:
                if start >= split_at:
                    start += delta
                    end += delta
                chapter_boundaries.append(
                    {
                        "title": chapter.title,
                        "start_offset": start,
                        "end_offset": end,
                        "volume_index": volume_index_by_id.get(chapter.volume_id),
                    }
                )
        revision = self._create_text_revision(
            document,
            current_revision,
            new_text,
            "split_cursor",
            {"chapter_id": chapter_id, "cursor_offset": cursor_offset},
            chapter_boundaries=chapter_boundaries,
            volume_boundaries=self._shift_volume_boundaries(volumes, split_at, split_at, delta),
        )
        created = next(
            (
                chapter
                for chapter in self.list_chapters(document_id)
                if chapter.start_offset == split_at and chapter.title == normalized_title
            ),
            None,
        )
        return CleanupResult(
            document=self._get_document(document_id),
            revision=revision,
            created=True,
            created_chapter_id=created.id if created else None,
        )

    def apply_chapter_split_boundaries(
        self,
        document_id: int,
        *,
        chapter_id: int,
        source_revision_id: int,
        boundaries: list[dict[str, object]],
        revision_type: str = "split_ai",
        metadata: dict[str, object] | None = None,
    ) -> tuple[DocumentRevision, list[LibraryChapter]]:
        """Replace one chapter in place with continuous body-relative boundaries."""
        self._ensure_content_mutable(document_id)
        current = self._ensure_initial_revision(document_id)
        if current.id != source_revision_id:
            raise ValueError("The document changed after the split preview; generate a new preview.")
        content = self.get_content(document_id, chapter_id)
        normalized = _validate_continuous_boundaries(content.body_text, boundaries)
        source_text = Path(current.storage_path).read_text(encoding="utf-8")
        chapters = self.list_chapters(document_id)
        volumes = self.list_volumes(document_id)
        target = next((chapter for chapter in chapters if chapter.id == chapter_id), None)
        if target is None:
            raise FileNotFoundError(f"找不到章节：{chapter_id}")
        target_start, target_end = self._chapter_offsets(source_text, target)

        replacement_parts: list[str] = []
        replacement_boundaries: list[dict[str, object]] = []
        relative_cursor = 0
        volume_index = next((volume.index for volume in volumes if volume.id == target.volume_id), None)
        for offset, boundary in enumerate(normalized):
            body = content.body_text[int(boundary["start_offset"]):int(boundary["end_offset"])]
            heading = format_chapter_heading(target.index + offset, str(boundary["title"]))
            section = f"{heading}\n\n{body}"
            if offset < len(normalized) - 1 and not section.endswith("\n\n"):
                section += "\n\n"
            replacement_parts.append(section)
            replacement_boundaries.append(
                {
                    "title": str(boundary["title"]),
                    "start_offset": target_start + relative_cursor,
                    "end_offset": target_start + relative_cursor + len(section),
                    "volume_index": volume_index,
                }
            )
            relative_cursor += len(section)
        replacement = "".join(replacement_parts)
        new_text = source_text[:target_start] + replacement + source_text[target_end:]
        delta = len(replacement) - (target_end - target_start)
        volume_index_by_id = {volume.id: volume.index for volume in volumes}
        final_boundaries: list[dict[str, object]] = []
        for chapter in chapters:
            if chapter.id == chapter_id:
                final_boundaries.extend(replacement_boundaries)
                continue
            start, end = self._chapter_offsets(source_text, chapter)
            if start >= target_end:
                start += delta
                end += delta
            final_boundaries.append(
                {
                    "title": chapter.title,
                    "start_offset": start,
                    "end_offset": end,
                    "volume_index": volume_index_by_id.get(chapter.volume_id),
                }
            )
        revision = self._create_text_revision(
            self._get_document(document_id),
            current,
            new_text,
            revision_type,
            metadata or {},
            chapter_boundaries=final_boundaries,
            volume_boundaries=self._shift_volume_boundaries(volumes, target_start, target_end, delta),
        )
        return revision, self.list_chapters(document_id)

    def export_document(self, document_id: int, export_format: str, output_path: str | Path) -> Path:
        document = self._get_document(document_id)
        output = Path(output_path).expanduser().resolve()
        normalized_format = export_format.strip().lower()
        if normalized_format not in {"txt", "epub"}:
            raise ValueError("仅支持导出 TXT 或 EPUB。")
        chapters = self._chapter_records_for_export(document)
        volume_titles = {
            volume.id: volume.title for volume in self.list_volumes(document_id)
        }
        if normalized_format == "txt":
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(
                build_txt_export(
                    chapters,
                    use_rewrites=False,
                    volume_titles=volume_titles,
                ),
                encoding="utf-8",
            )
            return output
        return export_epub(
            chapters,
            output,
            title=document.title,
            author=document.author,
            use_rewrites=False,
            volume_titles=volume_titles,
        )

    def activate_revision(self, document_id: int, revision_id: int) -> LibraryDocument:
        self._ensure_content_mutable(document_id)
        self._get_document(document_id)
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT r.*, COUNT(c.id) AS chapter_count
                FROM library_document_revisions r
                LEFT JOIN library_document_chapters c ON c.revision_id = r.id
                WHERE r.id = ? AND r.document_id = ?
                GROUP BY r.id
                """,
                (revision_id, document_id),
            ).fetchone()
            if row is None:
                raise FileNotFoundError(f"找不到文档版本：{revision_id}")
            storage_path = Path(str(row["storage_path"]))
            if not storage_path.is_file():
                raise FileNotFoundError(f"找不到版本文件：{storage_path}")
            revision_text = storage_path.read_text(encoding="utf-8")
            connection.execute(
                """
                UPDATE library_documents
                SET storage_path = ?, stored_size_bytes = ?, chapter_count = ?,
                    word_count = ?, status = ?, current_revision_id = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    str(storage_path),
                    storage_path.stat().st_size,
                    int(row["chapter_count"]),
                    count_text_units(revision_text),
                    "imported" if row["revision_type"] == "import" else "processed",
                    revision_id,
                    document_id,
                ),
            )
        return self._get_document(document_id)

    def _create_text_revision(
        self,
        document: LibraryDocument,
        parent_revision: DocumentRevision,
        text: str,
        revision_type: str,
        metadata: dict[str, object],
        chapter_boundaries: list[dict[str, object]] | None = None,
        volume_boundaries: list[dict[str, object]] | None = None,
        consume_draft_id: int | None = None,
        consume_draft_base_revision_id: int | None = None,
        consume_draft_chapter_id: int | None = None,
        delete_draft_chapter_id: int | None = None,
        delete_draft_chapter_ids: list[int] | None = None,
        document_title: str | None = None,
    ) -> DocumentRevision:
        encoded_text = self._normalize_text(text).encode("utf-8")
        content_hash = hashlib.sha256(encoded_text).hexdigest()
        revisions = self.list_revisions(document.id)
        revision_number = (revisions[0].revision_number if revisions else 0) + 1
        storage_path = self.library_path / f"{self._safe_filename(document.title)}-{content_hash[:12]}-v{revision_number}.txt"
        temporary_path = storage_path.with_suffix(".tmp")
        temporary_path.write_bytes(encoded_text)
        temporary_path.replace(storage_path)
        parsed_chapters = []
        parsed_volumes = []
        if chapter_boundaries is None:
            book = parse_txt(storage_path)
            parsed_chapters = book.chapters
            parsed_volumes = book.volumes or []
            known_volume_titles = {
                volume.title for volume in self.list_volumes(document.id)
            }
            if known_volume_titles:
                parsed_chapters, parsed_volumes = split_document_structure(
                    encoded_text.decode("utf-8"),
                    known_volume_titles=known_volume_titles,
                )
        try:
            with session(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO library_document_revisions (
                        document_id, revision_number, revision_type, storage_path,
                        content_hash, parent_revision_id, metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        document.id,
                        revision_number,
                        revision_type,
                        str(storage_path),
                        content_hash,
                        parent_revision.id,
                        json.dumps(metadata, ensure_ascii=False),
                    ),
                )
                revision_id = int(cursor.lastrowid)
                if chapter_boundaries is None:
                    self._insert_chapters(
                        connection,
                        document.id,
                        revision_id,
                        parsed_chapters,
                        parsed_volumes,
                    )
                    chapter_count = len(parsed_chapters)
                else:
                    normalized_text = encoded_text.decode("utf-8")
                    volume_ids: dict[int, int] = {}
                    for volume_index, boundary in enumerate(
                        sorted(
                            volume_boundaries or [],
                            key=lambda item: int(item["start_offset"]),
                        ),
                        start=1,
                    ):
                        start = int(boundary["start_offset"])
                        end = int(boundary["end_offset"])
                        if start < 0 or end <= start or end > len(normalized_text):
                            raise ValueError("Preserved volume offset is invalid in the new revision.")
                        cursor = connection.execute(
                            """
                            INSERT INTO library_document_volumes (
                                document_id, revision_id, volume_index, title,
                                start_offset, end_offset
                            ) VALUES (?, ?, ?, ?, ?, ?)
                            """,
                            (
                                document.id,
                                revision_id,
                                volume_index,
                                str(boundary["title"]),
                                start,
                                end,
                            ),
                        )
                        source_index = int(boundary.get("volume_index", volume_index))
                        volume_ids[source_index] = int(cursor.lastrowid)
                    ordered = sorted(chapter_boundaries, key=lambda item: int(item["start_offset"]))
                    for index, boundary in enumerate(ordered, start=1):
                        start = int(boundary["start_offset"])
                        end = int(boundary["end_offset"])
                        if start < 0 or end <= start or end > len(normalized_text):
                            raise ValueError("Preserved chapter offset is invalid in the new revision.")
                        connection.execute(
                            """
                            INSERT INTO library_document_chapters (
                                document_id, revision_id, chapter_index, title,
                                start_line, end_line, start_offset, end_offset, word_count,
                                volume_id
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """,
                            (
                                document.id,
                                revision_id,
                                index,
                                normalize_chapter_title(str(boundary["title"])),
                                normalized_text.count("\n", 0, start) + 1,
                                normalized_text.count("\n", 0, end) + 1,
                                start,
                                end,
                                count_text_units(normalized_text[start:end]),
                                volume_ids.get(
                                    int(boundary["volume_index"])
                                    if boundary.get("volume_index") is not None
                                    else -1
                                ),
                            ),
                        )
                    chapter_count = len(ordered)
                updated = connection.execute(
                    """
                    UPDATE library_documents
                    SET title = COALESCE(?, title),
                        storage_path = ?, content_hash = ?, stored_size_bytes = ?,
                        chapter_count = ?, word_count = ?, current_revision_id = ?,
                        status = 'processed', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ? AND current_revision_id = ?
                    """,
                    (
                        document_title,
                        str(storage_path),
                        content_hash,
                        len(encoded_text),
                        chapter_count,
                        count_text_units(encoded_text.decode("utf-8")),
                        revision_id,
                        document.id,
                        parent_revision.id,
                    ),
                )
                if updated.rowcount != 1:
                    if consume_draft_id is not None:
                        raise DraftConflictError(
                            "The draft base revision is no longer the document head."
                        )
                    raise ValueError("The document changed before the revision was finalized.")
                if consume_draft_id is not None:
                    deleted = connection.execute(
                        """
                        DELETE FROM library_document_drafts
                        WHERE id = ? AND document_id = ? AND base_revision_id = ?
                          AND ((? IS NULL AND chapter_id IS NULL) OR chapter_id = ?)
                        """,
                        (
                            consume_draft_id,
                            document.id,
                            consume_draft_base_revision_id,
                            consume_draft_chapter_id,
                            consume_draft_chapter_id,
                        ),
                    )
                    if deleted.rowcount != 1:
                        raise DraftConflictError(
                            "The committed draft changed before its revision was finalized."
                        )
                if delete_draft_chapter_id is not None:
                    connection.execute(
                        "DELETE FROM library_document_drafts WHERE document_id = ? AND chapter_id = ?",
                        (document.id, delete_draft_chapter_id),
                    )
                if delete_draft_chapter_ids:
                    placeholders = ",".join("?" for _ in delete_draft_chapter_ids)
                    connection.execute(
                        f"DELETE FROM library_document_drafts WHERE document_id = ? AND chapter_id IN ({placeholders})",
                        (document.id, *delete_draft_chapter_ids),
                    )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise
        return self.list_revisions(document.id)[0]

    @staticmethod
    def _chapter_offsets(text: str, chapter: LibraryChapter) -> tuple[int, int]:
        if (
            chapter.start_offset is not None
            and chapter.end_offset is not None
            and 0 <= chapter.start_offset < chapter.end_offset <= len(text)
        ):
            return chapter.start_offset, chapter.end_offset
        return DocumentLibraryService._chapter_offsets_from_lines(
            text,
            chapter.start_line,
            chapter.end_line,
        )

    @staticmethod
    def _shift_volume_boundaries(
        volumes: list[LibraryVolume],
        edit_start: int,
        edit_end: int,
        delta: int,
    ) -> list[dict[str, object]]:
        boundaries: list[dict[str, object]] = []
        for volume in volumes:
            start, end = volume.start_offset, volume.end_offset
            if start >= edit_end and not (
                edit_start == edit_end and start < edit_start <= end
            ):
                start += delta
                end += delta
            elif start <= edit_start <= end:
                end += delta
            boundaries.append(
                {
                    "volume_index": volume.index,
                    "title": volume.title,
                    "start_offset": start,
                    "end_offset": end,
                }
            )
        return boundaries

    @staticmethod
    def _chapter_body_start(
        text: str,
        chapter: LibraryChapter,
        section_start: int,
        section_end: int,
    ) -> int:
        segment = text[section_start:section_end]
        leading = len(segment) - len(segment.lstrip("\n"))
        title_segment = segment[leading:]
        first_newline = title_segment.find("\n")
        if (
            first_newline < 0
            or normalize_chapter_title(title_segment[:first_newline]) != chapter.title.strip()
        ):
            return section_start
        relative = leading + first_newline + 1
        if relative < len(segment) and segment[relative] == "\n":
            relative += 1
        return section_start + relative

    @staticmethod
    def _chapter_offsets_from_lines(text: str, start_line: int | None, end_line: int | None) -> tuple[int, int]:
        if start_line is None:
            return 0, len(text)
        line_starts = [0]
        for match in re.finditer("\n", text):
            line_starts.append(match.end())
        start_index = max(0, min(len(line_starts) - 1, start_line - 1))
        start = line_starts[start_index]
        if end_line is None or end_line >= len(line_starts):
            return start, len(text)
        return start, line_starts[max(start_index, end_line)]

    def _read_source(self, path: Path) -> tuple[ParsedBook, str]:
        suffix = path.suffix.lower()
        if suffix == ".txt":
            book = parse_txt(path)
            text, _ = read_text_with_encoding(path)
            return book, text
        if suffix == ".epub":
            book = parse_epub(path)
            return book, self._book_to_text(book)
        if suffix == ".docx":
            book = parse_docx(path)
            return book, self._book_to_text(book)
        raise ValueError("不支持的文档格式。")

    @staticmethod
    def _book_to_text(book: ParsedBook) -> str:
        sections: list[str] = []
        for chapter in book.chapters:
            title = chapter.title.strip()
            body = chapter.text.strip()
            if title and body:
                sections.append(f"{title}\n\n{body}")
            elif title or body:
                sections.append(title or body)
        return "\n\n".join(sections)

    @staticmethod
    def _normalize_text(text: str) -> str:
        normalized = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
        return normalized.strip() + "\n"

    def _find_by_hash(self, content_hash: str) -> LibraryDocument | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT d.id
                FROM library_documents d
                WHERE d.content_hash = ? AND d.deleted_at IS NULL
                ORDER BY d.id
                LIMIT 1
                """,
                (content_hash,),
            ).fetchone()
        return self._get_document(int(row["id"])) if row is not None else None

    def _ensure_content_mutable(self, document_id: int) -> None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT 1 FROM project_documents WHERE document_id = ? LIMIT 1",
                (document_id,),
            ).fetchone()
        if row is not None:
            raise ValueError("工程文档以工程内容为准，文档库工作区仅支持阅读、版本浏览和导出。")

    def _ensure_initial_revision(self, document_id: int) -> DocumentRevision:
        document = self._get_document(document_id)
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT r.*
                FROM library_documents d
                LEFT JOIN library_document_revisions r ON r.id = d.current_revision_id
                WHERE d.id = ?
                """,
                (document_id,),
            ).fetchone()
            if row is not None and row["id"] is not None:
                return self._row_to_revision(row)

            storage_path = Path(document.storage_path)
            if not storage_path.is_file():
                raise FileNotFoundError(f"找不到导入文档：{storage_path}")
            content_hash = hashlib.sha256(storage_path.read_bytes()).hexdigest()
            cursor = connection.execute(
                """
                INSERT INTO library_document_revisions (
                    document_id, revision_number, revision_type, storage_path, content_hash
                ) VALUES (?, 1, 'import', ?, ?)
                """,
                (document_id, str(storage_path), content_hash),
            )
            revision_id = int(cursor.lastrowid)
            book = parse_txt(storage_path)
            self._insert_chapters(
                connection,
                document_id,
                revision_id,
                book.chapters,
                book.volumes or [],
            )
            connection.execute(
                "UPDATE library_documents SET current_revision_id = ? WHERE id = ?",
                (revision_id, document_id),
            )
            row = connection.execute(
                "SELECT * FROM library_document_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        return self._row_to_revision(row)

    def _revision_hash(self, revision_id: int) -> str:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT content_hash FROM library_document_revisions WHERE id = ?",
                (revision_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"找不到文档版本：{revision_id}")
        return str(row["content_hash"])

    def _get_document(self, document_id: int) -> LibraryDocument:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT d.*,
                       COALESCE((
                           SELECT GROUP_CONCAT(categories.id, char(31))
                           FROM document_category_links links
                           JOIN document_categories categories ON categories.id = links.category_id
                           WHERE links.document_id = d.id AND categories.deleted_at IS NULL
                       ), '') AS category_ids,
                       COALESCE((
                           SELECT GROUP_CONCAT(categories.name, char(31))
                           FROM document_category_links links
                           JOIN document_categories categories ON categories.id = links.category_id
                           WHERE links.document_id = d.id AND categories.deleted_at IS NULL
                       ), '') AS category_names,
                       EXISTS(
                           SELECT 1 FROM project_documents projects
                           WHERE projects.document_id = d.id
                       ) AS is_project_document,
                       COALESCE((
                           SELECT GROUP_CONCAT(projects.project_id, char(31))
                           FROM project_documents projects
                           WHERE projects.document_id = d.id
                       ), '') AS project_ids
                FROM library_documents d
                WHERE d.id = ? AND d.deleted_at IS NULL
                """,
                (document_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"找不到文档：{document_id}")
        return self._row_to_document(row)

    def _allocate_storage_path(self, safe_title: str, content_hash: str) -> Path:
        base = self.library_path / f"{safe_title}-{content_hash[:12]}.txt"
        if not base.exists():
            return base
        return self.library_path / f"{safe_title}-{content_hash[:20]}.txt"

    @staticmethod
    def _available_migration_path(target: Path, content_hash: str) -> Path:
        if not target.exists():
            return target
        if hashlib.sha256(target.read_bytes()).hexdigest() == content_hash:
            return target
        return target.with_name(f"{target.stem}-{content_hash[:8]}{target.suffix}")

    def _chapter_records_for_export(self, document: LibraryDocument) -> list[ChapterRecord]:
        revision = self._ensure_initial_revision(document.id)
        chapters = self.list_chapters(document.id)
        text = Path(revision.storage_path).read_text(encoding="utf-8")
        records: list[ChapterRecord] = []
        for chapter in chapters:
            start, end = self._chapter_offsets(text, chapter)
            body_start = self._chapter_body_start(text, chapter, start, end)
            body = text[body_start:end].strip()
            records.append(
                ChapterRecord(
                    id=chapter.id,
                    project_id=document.id,
                    index=chapter.index,
                    title=chapter.title,
                    original_text=body,
                    rewritten_text=None,
                    word_count=chapter.word_count,
                    status="export",
                    start_line=chapter.start_line,
                    end_line=chapter.end_line,
                    volume_id=chapter.volume_id,
                )
            )
        if records:
            return records
        return [
            ChapterRecord(
                id=0,
                project_id=document.id,
                index=1,
                title=document.title,
                original_text=text,
                rewritten_text=None,
                word_count=document.word_count,
                status="export",
                start_line=None,
                end_line=None,
            )
        ]

    @staticmethod
    def _insert_chapters(
        connection,
        document_id: int,
        revision_id: int,
        chapters: list[ParsedChapter],
        volumes: list[ParsedVolume] | None = None,
    ) -> None:
        revision_row = connection.execute(
            "SELECT storage_path FROM library_document_revisions WHERE id = ?",
            (revision_id,),
        ).fetchone()
        full_text = Path(str(revision_row["storage_path"])).read_text(encoding="utf-8") if revision_row else ""
        volume_ids: dict[int, int] = {}
        for volume in volumes or []:
            start_offset, end_offset = DocumentLibraryService._chapter_offsets_from_lines(
                full_text,
                volume.start_line,
                volume.end_line,
            )
            cursor = connection.execute(
                """
                INSERT INTO library_document_volumes (
                    document_id, revision_id, volume_index, title, start_offset, end_offset
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    revision_id,
                    volume.index,
                    volume.title,
                    start_offset,
                    end_offset,
                ),
            )
            volume_ids[volume.index] = int(cursor.lastrowid)
        for chapter in chapters:
            start_offset, end_offset = DocumentLibraryService._chapter_offsets_from_lines(
                full_text,
                chapter.start_line,
                chapter.end_line,
            )
            connection.execute(
                """
                INSERT INTO library_document_chapters (
                    document_id, revision_id, chapter_index, title,
                    start_line, end_line, start_offset, end_offset, word_count, volume_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    revision_id,
                    chapter.index,
                    normalize_chapter_title(chapter.title),
                    chapter.start_line,
                    chapter.end_line,
                    start_offset,
                    end_offset,
                    count_text_units(full_text[start_offset:end_offset]),
                    volume_ids.get(chapter.volume_index) if chapter.volume_index is not None else None,
                ),
            )

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r"[^\w\-.一-龥]+", "-", value.strip(), flags=re.UNICODE).strip(".-")
        return cleaned[:80] or "document"

    @staticmethod
    def _row_to_document(row) -> LibraryDocument:
        category_ids = [
            int(value)
            for value in str(row["category_ids"] or "").split(chr(31))
            if value
        ]
        categories = [
            name
            for name in str(row["category_names"] or "").split(chr(31))
            if name
        ]
        project_ids = [
            int(value)
            for value in str(row["project_ids"] or "").split(chr(31))
            if value
        ]
        return LibraryDocument(
            id=int(row["id"]),
            title=str(row["title"]),
            author=row["author"],
            description=row["description"],
            source_filename=str(row["source_filename"]),
            source_format=str(row["source_format"]),
            storage_path=str(row["storage_path"]),
            source_size_bytes=int(row["source_size_bytes"]),
            stored_size_bytes=int(row["stored_size_bytes"]),
            chapter_count=int(row["chapter_count"]),
            word_count=int(row["word_count"]),
            cover_palette=str(row["cover_palette"]) if str(row["cover_palette"]) in DOCUMENT_COVER_PALETTES else "slate",
            status=str(row["status"]),
            favorite=bool(row["favorite"]),
            is_project_document=bool(row["is_project_document"]),
            category_ids=category_ids,
            categories=categories,
            project_ids=project_ids,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _normalize_category_name(name: str) -> tuple[str, str]:
        display_name = " ".join(name.strip().split())
        if not display_name:
            raise ValueError("分类名称不能为空。")
        if len(display_name) > 40:
            raise ValueError("分类名称不能超过 40 个字符。")
        return display_name, display_name.casefold()

    @staticmethod
    def _row_to_revision(row) -> DocumentRevision:
        return DocumentRevision(
            id=int(row["id"]),
            document_id=int(row["document_id"]),
            revision_number=int(row["revision_number"]),
            revision_type=str(row["revision_type"]),
            storage_path=str(row["storage_path"]),
            parent_revision_id=int(row["parent_revision_id"]) if row["parent_revision_id"] is not None else None,
            created_at=str(row["created_at"]),
        )
