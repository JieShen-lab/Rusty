from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from rusty.db import initialize_database, session
from rusty.exporters import build_txt_export, export_epub
from rusty.importers import parse_docx, parse_epub, parse_txt
from rusty.importers.txt import read_text_with_encoding, split_chapters
from rusty.models import ChapterRecord, ParsedBook, ParsedChapter


SUPPORTED_DOCUMENT_SUFFIXES = {".txt", ".epub", ".docx"}


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
    status: str
    favorite: bool
    categories: list[str]
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DocumentImportResult:
    document: LibraryDocument
    created: bool


@dataclass(frozen=True)
class ProcessingTemplate:
    id: int
    name: str
    settings: dict[str, object]
    is_default: bool
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class DocumentRevision:
    id: int
    document_id: int
    revision_number: int
    revision_type: str
    storage_path: str
    template_id: int | None
    parent_revision_id: int | None
    created_at: str


@dataclass(frozen=True)
class CleanupResult:
    document: LibraryDocument
    revision: DocumentRevision
    created: bool


@dataclass(frozen=True)
class LibraryCategory:
    id: int
    name: str
    parent_id: int | None
    sort_order: int
    document_count: int


@dataclass(frozen=True)
class LibraryChapter:
    id: int
    revision_id: int
    index: int
    title: str
    start_line: int | None
    end_line: int | None
    word_count: int


@dataclass(frozen=True)
class LibraryDocumentContent:
    document_id: int
    revision_id: int
    chapter_id: int | None
    title: str
    text: str


def default_document_library_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Rusty" / "document-library"


class DocumentLibraryService:
    def __init__(
        self,
        database_path: str | Path,
        library_path: str | Path | None = None,
    ) -> None:
        self.database_path = Path(database_path)
        configured_path = os.environ.get("RUSTY_DOCUMENT_LIBRARY_PATH")
        with session(self.database_path) as connection:
            initialize_database(connection)
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
                       COALESCE(GROUP_CONCAT(c.name, char(31)), '') AS category_names
                FROM library_documents d
                LEFT JOIN document_category_links link ON link.document_id = d.id
                LEFT JOIN document_categories c
                    ON c.id = link.category_id AND c.deleted_at IS NULL
                WHERE d.deleted_at IS NULL
                GROUP BY d.id
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
                SELECT c.*, COUNT(link.document_id) AS document_count
                FROM document_categories c
                LEFT JOIN document_category_links link ON link.category_id = c.id
                WHERE c.deleted_at IS NULL
                GROUP BY c.id
                ORDER BY c.sort_order, c.name
                """
            ).fetchall()
        return [
            LibraryCategory(
                id=int(row["id"]),
                name=str(row["name"]),
                parent_id=int(row["parent_id"]) if row["parent_id"] is not None else None,
                sort_order=int(row["sort_order"]),
                document_count=int(row["document_count"]),
            )
            for row in rows
        ]

    def create_category(self, name: str, parent_id: int | None = None) -> LibraryCategory:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("分类名称不能为空。")
        with session(self.database_path) as connection:
            duplicate = connection.execute(
                "SELECT id FROM document_categories WHERE lower(name) = lower(?) AND deleted_at IS NULL",
                (normalized_name,),
            ).fetchone()
            if duplicate is not None:
                raise ValueError("已经存在同名分类。")
            if parent_id is not None:
                parent = connection.execute(
                    "SELECT id FROM document_categories WHERE id = ? AND deleted_at IS NULL",
                    (parent_id,),
                ).fetchone()
                if parent is None:
                    raise FileNotFoundError(f"找不到父分类：{parent_id}")
            cursor = connection.execute(
                "INSERT INTO document_categories (name, parent_id) VALUES (?, ?)",
                (normalized_name, parent_id),
            )
            category_id = int(cursor.lastrowid)
        return next(category for category in self.list_categories() if category.id == category_id)

    def set_document_category(self, document_id: int, category_id: int, selected: bool) -> LibraryDocument:
        self._get_document(document_id)
        with session(self.database_path) as connection:
            category = connection.execute(
                "SELECT id FROM document_categories WHERE id = ? AND deleted_at IS NULL",
                (category_id,),
            ).fetchone()
            if category is None:
                raise FileNotFoundError(f"找不到分类：{category_id}")
            if selected:
                connection.execute(
                    "INSERT OR IGNORE INTO document_category_links (document_id, category_id) VALUES (?, ?)",
                    (document_id, category_id),
                )
            else:
                connection.execute(
                    "DELETE FROM document_category_links WHERE document_id = ? AND category_id = ?",
                    (document_id, category_id),
                )
        return self._get_document(document_id)

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
                        chapter_count, word_count, source_metadata_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        book.total_words,
                        json.dumps(metadata, ensure_ascii=False),
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
                self._insert_chapters(connection, document_id, revision_id, book.chapters)
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        document = self._get_document(document_id)
        return DocumentImportResult(document=document, created=True)

    def ensure_project_document(self, project_id: int, source_path: str | Path) -> LibraryDocument:
        result = self.import_document(source_path)
        categories = self.list_categories()
        project_category = next((item for item in categories if item.name == "工程"), None)
        if project_category is None:
            project_category = self.create_category("工程")
        self.set_document_category(result.document.id, project_category.id, True)
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

    def list_processing_templates(self) -> list[ProcessingTemplate]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT *
                FROM document_processing_templates
                WHERE deleted_at IS NULL
                ORDER BY is_default DESC, id
                """
            ).fetchall()
        return [self._row_to_template(row) for row in rows]

    def create_processing_template(self, name: str, settings: dict[str, object]) -> ProcessingTemplate:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("模板名称不能为空。")
        normalized_settings = self._validate_template_settings(settings)
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO document_processing_templates (name, settings_json)
                VALUES (?, ?)
                """,
                (normalized_name, json.dumps(normalized_settings, ensure_ascii=False)),
            )
            template_id = int(cursor.lastrowid)
        return self._get_template(template_id)

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
        return [
            LibraryChapter(
                id=int(row["id"]),
                revision_id=int(row["revision_id"]),
                index=int(row["chapter_index"]),
                title=str(row["title"]),
                start_line=int(row["start_line"]) if row["start_line"] is not None else None,
                end_line=int(row["end_line"]) if row["end_line"] is not None else None,
                word_count=int(row["word_count"]),
            )
            for row in rows
        ]

    def reorder_chapters(self, document_id: int, ordered_chapter_ids: list[int]) -> list[LibraryChapter]:
        revision = self._ensure_initial_revision(document_id)
        chapters = self.list_chapters(document_id)
        existing_ids = {chapter.id for chapter in chapters}
        if len(ordered_chapter_ids) != len(existing_ids) or set(ordered_chapter_ids) != existing_ids:
            raise ValueError("章节顺序必须包含当前版本的全部章节且不能重复。")
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
        if chapter_id is None:
            text = Path(revision.storage_path).read_text(encoding="utf-8")
            return LibraryDocumentContent(
                document_id=document.id,
                revision_id=revision.id,
                chapter_id=None,
                title=document.title,
                text=text,
            )

        chapter = next(
            (item for item in self._chapter_records_for_export(document) if item.id == chapter_id),
            None,
        )
        if chapter is None:
            raise FileNotFoundError(f"找不到当前版本的章节：{chapter_id}")
        text = f"{chapter.title}\n\n{chapter.original_text}".strip() + "\n"
        return LibraryDocumentContent(
            document_id=document.id,
            revision_id=revision.id,
            chapter_id=chapter.id,
            title=chapter.title,
            text=text,
        )

    def export_document(self, document_id: int, export_format: str, output_path: str | Path) -> Path:
        document = self._get_document(document_id)
        output = Path(output_path).expanduser().resolve()
        normalized_format = export_format.strip().lower()
        if normalized_format not in {"txt", "epub"}:
            raise ValueError("仅支持导出 TXT 或 EPUB。")
        chapters = self._chapter_records_for_export(document)
        if normalized_format == "txt":
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(build_txt_export(chapters, use_rewrites=False), encoding="utf-8")
            return output
        return export_epub(
            chapters,
            output,
            title=document.title,
            author=document.author,
            use_rewrites=False,
        )

    def apply_cleanup(self, document_id: int, template_id: int) -> CleanupResult:
        document = self._get_document(document_id)
        current_revision = self._ensure_initial_revision(document_id)
        template = self._get_template(template_id)
        source_path = Path(current_revision.storage_path)
        if not source_path.is_file():
            raise FileNotFoundError(f"找不到当前文档版本：{source_path}")

        settings = self._validate_template_settings(template.settings)
        pattern = re.compile(str(settings["chapter_pattern"]))
        source_text = source_path.read_text(encoding="utf-8")
        cleaned_text = self._apply_rule_cleanup(source_text, pattern, settings)
        encoded_text = cleaned_text.encode("utf-8")
        content_hash = hashlib.sha256(encoded_text).hexdigest()
        if content_hash == self._revision_hash(current_revision.id):
            return CleanupResult(document=document, revision=current_revision, created=False)

        revisions = self.list_revisions(document_id)
        revision_number = (revisions[0].revision_number if revisions else 0) + 1
        safe_title = self._safe_filename(document.title)
        storage_path = self.library_path / f"{safe_title}-{content_hash[:12]}-v{revision_number}.txt"
        temporary_path = storage_path.with_suffix(".tmp")
        temporary_path.write_bytes(encoded_text)
        temporary_path.replace(storage_path)
        chapters = split_chapters(cleaned_text, pattern)

        try:
            with session(self.database_path) as connection:
                cursor = connection.execute(
                    """
                    INSERT INTO library_document_revisions (
                        document_id, revision_number, revision_type, storage_path,
                        content_hash, template_id, parent_revision_id, metadata_json
                    ) VALUES (?, ?, 'cleanup', ?, ?, ?, ?, ?)
                    """,
                    (
                        document_id,
                        revision_number,
                        str(storage_path),
                        content_hash,
                        template.id,
                        current_revision.id,
                        json.dumps({"settings": settings}, ensure_ascii=False),
                    ),
                )
                revision_id = int(cursor.lastrowid)
                self._insert_chapters(connection, document_id, revision_id, chapters)
                connection.execute(
                    """
                    UPDATE library_documents
                    SET storage_path = ?, stored_size_bytes = ?, chapter_count = ?,
                        word_count = ?, status = 'processed', current_revision_id = ?,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        str(storage_path),
                        len(encoded_text),
                        len(chapters),
                        sum(chapter.word_count for chapter in chapters),
                        revision_id,
                        document_id,
                    ),
                )
        except Exception:
            storage_path.unlink(missing_ok=True)
            raise

        return CleanupResult(
            document=self._get_document(document_id),
            revision=self.list_revisions(document_id)[0],
            created=True,
        )

    def activate_revision(self, document_id: int, revision_id: int) -> LibraryDocument:
        self._get_document(document_id)
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT r.*, COUNT(c.id) AS chapter_count,
                       COALESCE(SUM(c.word_count), 0) AS word_count
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
                    int(row["word_count"]),
                    "imported" if row["revision_type"] == "import" else "processed",
                    revision_id,
                    document_id,
                ),
            )
        return self._get_document(document_id)

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
                SELECT d.*,
                       COALESCE(GROUP_CONCAT(c.name, char(31)), '') AS category_names
                FROM library_documents d
                LEFT JOIN document_category_links link ON link.document_id = d.id
                LEFT JOIN document_categories c
                    ON c.id = link.category_id AND c.deleted_at IS NULL
                WHERE d.content_hash = ? AND d.deleted_at IS NULL
                GROUP BY d.id
                ORDER BY d.id
                LIMIT 1
                """,
                (content_hash,),
            ).fetchone()
        return self._row_to_document(row) if row is not None else None

    def _get_template(self, template_id: int) -> ProcessingTemplate:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT *
                FROM document_processing_templates
                WHERE id = ? AND deleted_at IS NULL
                """,
                (template_id,),
            ).fetchone()
        if row is None:
            raise FileNotFoundError(f"找不到处理模板：{template_id}")
        return self._row_to_template(row)

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
            self._insert_chapters(connection, document_id, revision_id, book.chapters)
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
                       COALESCE(GROUP_CONCAT(c.name, char(31)), '') AS category_names
                FROM library_documents d
                LEFT JOIN document_category_links link ON link.document_id = d.id
                LEFT JOIN document_categories c
                    ON c.id = link.category_id AND c.deleted_at IS NULL
                WHERE d.id = ? AND d.deleted_at IS NULL
                GROUP BY d.id
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
        lines = text.splitlines()
        title_positions: list[int | None] = []
        used_positions: set[int] = set()
        for chapter in chapters:
            position = next(
                (
                    index
                    for index, line in enumerate(lines)
                    if index not in used_positions and line.strip() == chapter.title.strip()
                ),
                None,
            )
            title_positions.append(position)
            if position is not None:
                used_positions.add(position)

        records: list[ChapterRecord] = []
        for index, chapter in enumerate(chapters):
            position = title_positions[index]
            next_positions = [
                item
                for item in title_positions
                if position is not None and item is not None and item > position
            ]
            end = min(next_positions) if next_positions else len(lines)
            if position is None:
                body = text if len(chapters) == 1 else ""
            else:
                body = "\n".join(lines[position + 1:end]).strip()
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
    def _apply_rule_cleanup(
        text: str,
        chapter_pattern: re.Pattern[str],
        settings: dict[str, object],
    ) -> str:
        chapter_indent = int(settings["chapter_indent"])
        paragraph_indent = int(settings["paragraph_indent"])
        blank_lines = int(settings["blank_lines"])
        trim_whitespace = bool(settings["trim_whitespace"])
        formatted_lines: list[str] = []

        for raw_line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
            line = raw_line.rstrip() if trim_whitespace else raw_line
            content = line.lstrip(" \t　") if trim_whitespace else line
            if not content:
                continue
            indent = chapter_indent if chapter_pattern.fullmatch(content) else paragraph_indent
            formatted_lines.append(f"{'　' * indent}{content}")

        separator = "\n" * (blank_lines + 1)
        return separator.join(formatted_lines).strip() + "\n"

    @staticmethod
    def _validate_template_settings(settings: dict[str, object]) -> dict[str, object]:
        chapter_pattern = str(settings.get("chapter_pattern") or "").strip()
        if not chapter_pattern:
            raise ValueError("章节标题正则不能为空。")
        try:
            re.compile(chapter_pattern)
        except re.error as exc:
            raise ValueError(f"章节标题正则无效：{exc}") from exc

        normalized: dict[str, object] = {
            "chapter_pattern": chapter_pattern,
            "chapter_indent": int(settings.get("chapter_indent", 0)),
            "paragraph_indent": int(settings.get("paragraph_indent", 2)),
            "blank_lines": int(settings.get("blank_lines", 1)),
            "trim_whitespace": bool(settings.get("trim_whitespace", True)),
        }
        for key in ("chapter_indent", "paragraph_indent"):
            if not 0 <= int(normalized[key]) <= 8:
                raise ValueError("缩进必须在 0 到 8 个全角空格之间。")
        if not 0 <= int(normalized["blank_lines"]) <= 3:
            raise ValueError("段落间空行必须在 0 到 3 行之间。")
        return normalized

    @staticmethod
    def _insert_chapters(connection, document_id: int, revision_id: int, chapters: list[ParsedChapter]) -> None:
        for chapter in chapters:
            connection.execute(
                """
                INSERT INTO library_document_chapters (
                    document_id, revision_id, chapter_index, title,
                    start_line, end_line, word_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    document_id,
                    revision_id,
                    chapter.index,
                    chapter.title,
                    chapter.start_line,
                    chapter.end_line,
                    chapter.word_count,
                ),
            )

    @staticmethod
    def _safe_filename(value: str) -> str:
        cleaned = re.sub(r"[^\w\-.一-龥]+", "-", value.strip(), flags=re.UNICODE).strip(".-")
        return cleaned[:80] or "document"

    @staticmethod
    def _row_to_document(row) -> LibraryDocument:
        raw_categories = str(row["category_names"] or "")
        categories = [name for name in raw_categories.split(chr(31)) if name]
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
            status=str(row["status"]),
            favorite=bool(row["favorite"]),
            categories=categories,
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_template(row) -> ProcessingTemplate:
        try:
            settings = json.loads(str(row["settings_json"]))
        except json.JSONDecodeError:
            settings = {}
        return ProcessingTemplate(
            id=int(row["id"]),
            name=str(row["name"]),
            settings=settings if isinstance(settings, dict) else {},
            is_default=bool(row["is_default"]),
            created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _row_to_revision(row) -> DocumentRevision:
        return DocumentRevision(
            id=int(row["id"]),
            document_id=int(row["document_id"]),
            revision_number=int(row["revision_number"]),
            revision_type=str(row["revision_type"]),
            storage_path=str(row["storage_path"]),
            template_id=int(row["template_id"]) if row["template_id"] is not None else None,
            parent_revision_id=int(row["parent_revision_id"]) if row["parent_revision_id"] is not None else None,
            created_at=str(row["created_at"]),
        )
