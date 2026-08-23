from __future__ import annotations

import json
from pathlib import Path

from rusty.content_hash import hash_text
from rusty.db import default_database_path, session
from rusty.importers import parse_docx, parse_epub, parse_txt
from rusty.models import ChapterRecord, ParsedBook, ProjectSettings, ProjectSummary


class ProjectService:
    """Current project import and chapter catalog operations."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()

    def preview_book(self, source_path: str | Path) -> ParsedBook:
        path = Path(source_path)
        parser = {".txt": parse_txt, ".epub": parse_epub, ".docx": parse_docx}.get(path.suffix.lower())
        if parser is None:
            raise ValueError(f"Unsupported import format: {path.suffix or path.name}")
        return parser(path)

    def create_project(
        self,
        book: ParsedBook,
        workspace_path: str | Path,
        project_name: str | None = None,
        *,
        model_id: int | None = None,
    ) -> int:
        name = project_name.strip() if project_name and project_name.strip() else book.title
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """INSERT INTO projects(
                       name,status,current_stage,source_format,source_path,workspace_path,
                       total_chapters,total_words
                   ) VALUES(?,'imported','split',?,?,?,?,?)""",
                (name, book.source_format, str(book.source_path), str(workspace_path), len(book.chapters), book.total_words),
            )
            project_id = int(cursor.lastrowid)
            connection.execute(
                """INSERT INTO book_metadata(
                       project_id,title,author,language,publisher,description,source_encoding,
                       source_identifier,metadata_json
                   ) VALUES(?,?,?,?,?,?,?,?,?)""",
                (
                    project_id, book.title, book.author, book.language, book.publisher,
                    book.description, book.source_encoding, book.source_identifier,
                    json.dumps(book.metadata or {}, ensure_ascii=False),
                ),
            )
            connection.execute(
                "INSERT INTO project_settings(project_id,model_id) VALUES(?,?)",
                (project_id, model_id),
            )
            volume_id = int(connection.execute(
                "INSERT INTO story_volumes(project_id,volume_index,title) VALUES(?,1,'')", (project_id,)
            ).lastrowid)
            source_offset = 0
            for chapter in book.chapters:
                end_offset = source_offset + len(chapter.text)
                chapter_id = int(connection.execute(
                    """INSERT INTO chapters(
                           project_id,chapter_index,title,original_text,source_start_line,source_end_line,
                           source_start_offset,source_end_offset,word_count,status,volume_id
                       ) VALUES(?,?,?,?,?,?,?,?,?,'imported',?)""",
                    (
                        project_id, chapter.index, chapter.title, chapter.text, chapter.start_line,
                        chapter.end_line, source_offset, end_offset, chapter.word_count, volume_id,
                    ),
                ).lastrowid)
                connection.execute(
                    """INSERT INTO chapter_source_versions(
                           project_id,chapter_id,source_version,original_start_offset,original_end_offset,
                           original_text,content_hash
                       ) VALUES(?,?,1,?,?,?,?)""",
                    (project_id, chapter_id, source_offset, end_offset, chapter.text, hash_text(chapter.text)),
                )
                source_offset = end_offset
        return project_id

    def get_project(self, project_id: int) -> ProjectSummary | None:
        with session(self.database_path) as connection:
            row = connection.execute(self._project_select() + " WHERE p.id=? AND p.deleted_at IS NULL", (project_id,)).fetchone()
        return self._project(row) if row else None

    def list_projects(self) -> list[ProjectSummary]:
        with session(self.database_path) as connection:
            rows = connection.execute(self._project_select() + " WHERE p.deleted_at IS NULL ORDER BY p.updated_at DESC,p.id DESC").fetchall()
        return [self._project(row) for row in rows]

    def delete_project(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                "UPDATE projects SET deleted_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP WHERE id=? AND deleted_at IS NULL",
                (project_id,),
            )
        if cursor.rowcount == 0:
            raise FileNotFoundError(f"Project not found: {project_id}")

    def list_chapters(self, project_id: int) -> list[ChapterRecord]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """SELECT c.id,c.project_id,c.chapter_index,c.title,c.original_text,c.rewritten_text,c.word_count,
                          c.status,c.source_start_line,c.source_end_line,c.volume_id,
                          COALESCE(w.current_stage,'not_started') AS workflow_stage
                   FROM chapters c LEFT JOIN chapter_workflow_state w ON w.chapter_id=c.id
                   WHERE c.project_id=? ORDER BY c.chapter_index,c.id""",
                (project_id,),
            ).fetchall()
        return [self._chapter(row) for row in rows]

    def get_chapter(self, chapter_id: int) -> ChapterRecord | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """SELECT c.id,c.project_id,c.chapter_index,c.title,c.original_text,c.rewritten_text,c.word_count,
                          c.status,c.source_start_line,c.source_end_line,c.volume_id,
                          COALESCE(w.current_stage,'not_started') AS workflow_stage
                   FROM chapters c LEFT JOIN chapter_workflow_state w ON w.chapter_id=c.id
                   WHERE c.id=?""",
                (chapter_id,),
            ).fetchone()
        return self._chapter(row) if row else None

    def get_project_settings(self, project_id: int) -> ProjectSettings | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT project_id,model_id FROM project_settings WHERE project_id=?",
                (project_id,),
            ).fetchone()
        return ProjectSettings(int(row["project_id"]), row["model_id"]) if row else None

    @staticmethod
    def _project_select() -> str:
        return """SELECT p.id,p.name,p.status,p.current_stage,p.source_format,p.source_path,
                         p.workspace_path,p.total_chapters,p.total_words,p.completed_chapters,
                         p.created_at,p.updated_at,m.title AS book_title,m.author
                  FROM projects p LEFT JOIN book_metadata m ON m.project_id=p.id"""

    @staticmethod
    def _project(row) -> ProjectSummary:
        return ProjectSummary(
            id=int(row["id"]), name=str(row["name"]),
            status=str(row["status"]), current_stage=str(row["current_stage"]),
            source_format=row["source_format"], source_path=row["source_path"],
            workspace_path=row["workspace_path"], total_chapters=int(row["total_chapters"]),
            total_words=int(row["total_words"]), completed_chapters=int(row["completed_chapters"]),
            book_title=row["book_title"], author=row["author"], created_at=str(row["created_at"]),
            updated_at=str(row["updated_at"]),
        )

    @staticmethod
    def _chapter(row) -> ChapterRecord:
        return ChapterRecord(
            id=int(row["id"]), project_id=int(row["project_id"]), index=int(row["chapter_index"]),
            title=str(row["title"]), original_text=str(row["original_text"]),
            rewritten_text=row["rewritten_text"], word_count=int(row["word_count"]),
            status=str(row["status"]), start_line=row["source_start_line"],
            end_line=row["source_end_line"], volume_id=row["volume_id"],
            workflow_stage=str(row["workflow_stage"]),
        )
