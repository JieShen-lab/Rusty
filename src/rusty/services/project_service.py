from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from rusty.db import initialize_database, session
from rusty.exporters import build_txt_export, export_epub
from rusty.importers import parse_docx, parse_epub, parse_txt
from rusty.models import ChapterRecord, ParsedBook, ProjectSummary


def default_database_path() -> Path:
    base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    return base / "Rusty" / "rusty.db"


class ProjectService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        with session(self.database_path) as connection:
            initialize_database(connection)

    def import_txt(self, source_path: str | Path, workspace_path: str | Path | None = None) -> int:
        parsed_book = parse_txt(source_path)
        workspace = Path(workspace_path) if workspace_path is not None else Path(source_path).parent
        return self.create_project(parsed_book, workspace)

    def import_book(self, source_path: str | Path, workspace_path: str | Path | None = None) -> int:
        path = Path(source_path)
        suffix = path.suffix.lower()
        if suffix == ".txt":
            parsed_book = parse_txt(path)
        elif suffix == ".epub":
            parsed_book = parse_epub(path)
        elif suffix == ".docx":
            parsed_book = parse_docx(path)
        else:
            raise ValueError(f"Unsupported import format: {suffix or path.name}")

        workspace = Path(workspace_path) if workspace_path is not None else path.parent
        return self.create_project(parsed_book, workspace)

    def create_project(self, book: ParsedBook, workspace_path: str | Path) -> int:
        source_bytes = book.source_path.read_bytes()
        content_hash = hashlib.sha256(source_bytes).hexdigest()
        metadata_json = json.dumps(book.metadata or {}, ensure_ascii=False)

        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (
                    name,
                    status,
                    current_stage,
                    source_format,
                    source_path,
                    workspace_path,
                    total_chapters,
                    total_words
                ) VALUES (?, 'imported', 'split', ?, ?, ?, ?, ?)
                """,
                (
                    book.title,
                    book.source_format,
                    str(book.source_path),
                    str(workspace_path),
                    len(book.chapters),
                    book.total_words,
                ),
            )
            project_id = int(cursor.lastrowid)

            connection.execute(
                """
                INSERT INTO book_metadata (
                    project_id,
                    title,
                    author,
                    language,
                    publisher,
                    description,
                    source_encoding,
                    source_identifier,
                    metadata_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    book.title,
                    book.author,
                    book.language,
                    book.publisher,
                    book.description,
                    book.source_encoding,
                    book.source_identifier,
                    metadata_json,
                ),
            )
            connection.execute(
                """
                INSERT INTO import_sources (
                    project_id,
                    source_path,
                    source_format,
                    source_size_bytes,
                    content_hash,
                    parser_name,
                    parser_version
                ) VALUES (?, ?, ?, ?, ?, ?, '1')
                """,
                (
                    project_id,
                    str(book.source_path),
                    book.source_format,
                    len(source_bytes),
                    content_hash,
                    f"rusty_{book.source_format}",
                ),
            )
            connection.execute(
                "INSERT INTO project_settings (project_id, txt_split_rule_id) VALUES (?, 1)",
                (project_id,),
            )
            connection.executemany(
                """
                INSERT INTO chapters (
                    project_id,
                    chapter_index,
                    title,
                    original_text,
                    source_start_line,
                    source_end_line,
                    word_count,
                    status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'imported')
                """,
                [
                    (
                        project_id,
                        chapter.index,
                        chapter.title,
                        chapter.text,
                        chapter.start_line,
                        chapter.end_line,
                        chapter.word_count,
                    )
                    for chapter in book.chapters
                ],
            )

        return project_id

    def get_project(self, project_id: int) -> ProjectSummary | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.status,
                    p.current_stage,
                    p.source_format,
                    p.source_path,
                    p.workspace_path,
                    p.total_chapters,
                    p.total_words,
                    p.completed_chapters,
                    p.created_at,
                    p.updated_at,
                    m.title AS book_title,
                    m.author
                FROM projects p
                LEFT JOIN book_metadata m ON m.project_id = p.id
                WHERE p.id = ? AND p.deleted_at IS NULL
                """,
                (project_id,),
            ).fetchone()

        return self._project_from_row(row) if row is not None else None

    def list_projects(self) -> list[ProjectSummary]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.status,
                    p.current_stage,
                    p.source_format,
                    p.source_path,
                    p.workspace_path,
                    p.total_chapters,
                    p.total_words,
                    p.completed_chapters,
                    p.created_at,
                    p.updated_at,
                    m.title AS book_title,
                    m.author
                FROM projects p
                LEFT JOIN book_metadata m ON m.project_id = p.id
                WHERE p.deleted_at IS NULL
                ORDER BY p.updated_at DESC, p.id DESC
                """
            ).fetchall()

        return [self._project_from_row(row) for row in rows]

    def list_chapters(self, project_id: int) -> list[ChapterRecord]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    chapter_index,
                    title,
                    original_text,
                    rewritten_text,
                    word_count,
                    status,
                    source_start_line,
                    source_end_line
                FROM chapters
                WHERE project_id = ?
                ORDER BY chapter_index
                """,
                (project_id,),
            ).fetchall()

        return [self._chapter_from_row(row) for row in rows]

    def get_chapter(self, chapter_id: int) -> ChapterRecord | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    chapter_index,
                    title,
                    original_text,
                    rewritten_text,
                    word_count,
                    status,
                    source_start_line,
                    source_end_line
                FROM chapters
                WHERE id = ?
                """,
                (chapter_id,),
            ).fetchone()

        return self._chapter_from_row(row) if row is not None else None

    def export_txt(self, project_id: int, output_path: str | Path) -> Path:
        chapters = self.list_chapters(project_id)
        if not chapters:
            raise ValueError("Project has no chapters to export.")

        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        exported_text = build_txt_export(chapters)
        output.write_text(exported_text, encoding="utf-8")

        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO exports (
                    project_id,
                    export_format,
                    output_path,
                    chapter_count,
                    word_count
                ) VALUES (?, 'txt', ?, ?, ?)
                """,
                (
                    project_id,
                    str(output),
                    len(chapters),
                    sum(chapter.word_count for chapter in chapters),
                ),
            )

        return output

    def export_epub(self, project_id: int, output_path: str | Path) -> Path:
        chapters = self.list_chapters(project_id)
        if not chapters:
            raise ValueError("Project has no chapters to export.")

        project = self.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")

        metadata = self.get_book_metadata(project_id)
        title = metadata.get("title") or project.book_title or project.name
        output = export_epub(
            chapters=chapters,
            output_path=output_path,
            title=title,
            author=metadata.get("author") or project.author,
            language=metadata.get("language"),
            identifier=metadata.get("source_identifier"),
        )

        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO exports (
                    project_id,
                    export_format,
                    output_path,
                    chapter_count,
                    word_count
                ) VALUES (?, 'epub', ?, ?, ?)
                """,
                (
                    project_id,
                    str(output),
                    len(chapters),
                    sum(chapter.word_count for chapter in chapters),
                ),
            )

        return output

    def get_book_metadata(self, project_id: int) -> dict[str, str | None]:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    title,
                    author,
                    language,
                    publisher,
                    description,
                    source_encoding,
                    source_identifier,
                    metadata_json
                FROM book_metadata
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()

        if row is None:
            return {}
        return {
            "title": row["title"],
            "author": row["author"],
            "language": row["language"],
            "publisher": row["publisher"],
            "description": row["description"],
            "source_encoding": row["source_encoding"],
            "source_identifier": row["source_identifier"],
            "metadata_json": row["metadata_json"],
        }

    @staticmethod
    def _project_from_row(row) -> ProjectSummary:
        return ProjectSummary(
            id=row["id"],
            name=row["name"],
            status=row["status"],
            current_stage=row["current_stage"],
            source_format=row["source_format"],
            source_path=row["source_path"],
            workspace_path=row["workspace_path"],
            total_chapters=row["total_chapters"],
            total_words=row["total_words"],
            completed_chapters=row["completed_chapters"],
            book_title=row["book_title"],
            author=row["author"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @staticmethod
    def _chapter_from_row(row) -> ChapterRecord:
        return ChapterRecord(
            id=row["id"],
            project_id=row["project_id"],
            index=row["chapter_index"],
            title=row["title"],
            original_text=row["original_text"],
            rewritten_text=row["rewritten_text"],
            word_count=row["word_count"],
            status=row["status"],
            start_line=row["source_start_line"],
            end_line=row["source_end_line"],
        )
