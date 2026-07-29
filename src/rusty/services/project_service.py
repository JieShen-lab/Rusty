from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from rusty.db import initialize_database, session
from rusty.exporters import build_txt_export, export_epub
from rusty.importers import parse_docx, parse_epub, parse_txt
from rusty.models import (
    ChapterRecord,
    EffectiveExportChapter,
    ExportPlanItem,
    ExportRecord,
    ParsedBook,
    ProjectSettings,
    ProjectSummary,
    count_text_units,
)


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

    def preview_book(self, source_path: str | Path) -> ParsedBook:
        return self._parse_book(source_path)

    def import_book(self, source_path: str | Path, workspace_path: str | Path | None = None) -> int:
        path = Path(source_path)
        parsed_book = self._parse_book(path)
        workspace = Path(workspace_path) if workspace_path is not None else path.parent
        return self.create_project(parsed_book, workspace)

    def create_project(
        self,
        book: ParsedBook,
        workspace_path: str | Path,
        project_name: str | None = None,
        project_kind: str = "rewrite",
        processing_mode: str = "manual",
        prompt_template_id: int | None = None,
        analysis_prompt_template_id: int | None = None,
        txt_split_rule_id: int | None = 1,
        model_id: int | None = None,
    ) -> int:
        if project_kind not in {"rewrite", "branch"}:
            raise ValueError(f"Unsupported project kind for creation: {project_kind}")
        source_bytes = book.source_path.read_bytes()
        content_hash = hashlib.sha256(source_bytes).hexdigest()
        metadata_json = json.dumps(book.metadata or {}, ensure_ascii=False)
        name = project_name.strip() if project_name and project_name.strip() else book.title

        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO projects (
                    name,
                    project_kind,
                    status,
                    current_stage,
                    source_format,
                    source_path,
                    workspace_path,
                    total_chapters,
                    total_words
                ) VALUES (?, ?, 'imported', 'split', ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    project_kind,
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
                """
                INSERT INTO project_settings (
                    project_id, model_id, prompt_template_id, analysis_prompt_template_id,
                    txt_split_rule_id, processing_mode
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    project_id,
                    model_id,
                    prompt_template_id,
                    analysis_prompt_template_id,
                    txt_split_rule_id,
                    processing_mode,
                ),
            )
            chapter_rows = [
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
            ]
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
                chapter_rows,
            )
            volume_cursor = connection.execute(
                """
                INSERT INTO story_volumes (project_id, volume_index, title)
                VALUES (?, 1, '')
                """,
                (project_id,),
            )
            volume_id = int(volume_cursor.lastrowid)
            source_offset = 0
            inserted_chapters = connection.execute(
                """
                SELECT id, original_text
                FROM chapters
                WHERE project_id = ?
                ORDER BY chapter_index
                """,
                (project_id,),
            ).fetchall()
            for row in inserted_chapters:
                original_text = str(row["original_text"])
                end_offset = source_offset + len(original_text)
                connection.execute(
                    """
                    UPDATE chapters
                    SET volume_id = ?, source_start_offset = ?, source_end_offset = ?
                    WHERE id = ?
                    """,
                    (volume_id, source_offset, end_offset, int(row["id"])),
                )
                connection.execute(
                    """
                    INSERT INTO chapter_source_versions (
                        project_id, chapter_id, source_version,
                        original_start_offset, original_end_offset,
                        original_text, content_hash
                    ) VALUES (?, ?, 1, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        int(row["id"]),
                        source_offset,
                        end_offset,
                        original_text,
                        hashlib.sha256(original_text.encode("utf-8")).hexdigest(),
                    ),
                )
                source_offset = end_offset
            chapter_plan_rows = connection.execute(
                """
                SELECT id, chapter_index, title
                FROM chapters
                WHERE project_id = ?
                ORDER BY chapter_index
                """,
                (project_id,),
            ).fetchall()
            connection.executemany(
                """
                INSERT INTO export_chapter_plan (
                    project_id,
                    chapter_id,
                    export_order,
                    export_title,
                    include_in_export
                ) VALUES (?, ?, ?, ?, 1)
                """,
                [
                    (project_id, row["id"], row["chapter_index"], row["title"])
                    for row in chapter_plan_rows
                ],
            )

        return project_id

    def create_txt_split_rule(
        self,
        *,
        name: str,
        mode: str,
        line_prefix: str | None = None,
        number_pattern: str | None = None,
        title_suffix: str | None = None,
        custom_regex: str | None = None,
        extra_rules: dict | None = None,
    ) -> int:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO txt_split_rules (
                    name,
                    mode,
                    line_prefix,
                    number_pattern,
                    title_suffix,
                    custom_regex,
                    extra_rules_json,
                    is_default
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
                """,
                (
                    name.strip() or "Project chapter split rule",
                    mode,
                    line_prefix,
                    number_pattern,
                    title_suffix,
                    custom_regex,
                    json.dumps(extra_rules or {}, ensure_ascii=False),
                ),
            )
        return int(cursor.lastrowid)

    @staticmethod
    def _parse_book(source_path: str | Path) -> ParsedBook:
        path = Path(source_path)
        suffix = path.suffix.lower()
        if suffix == ".txt":
            return parse_txt(path)
        if suffix == ".epub":
            return parse_epub(path)
        if suffix == ".docx":
            return parse_docx(path)
        raise ValueError(f"Unsupported import format: {suffix or path.name}")

    def get_project(self, project_id: int) -> ProjectSummary | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    p.id,
                    p.name,
                    p.project_kind,
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
                    p.project_kind,
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

    def delete_project(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            cursor = connection.execute(
                """
                UPDATE projects
                SET deleted_at = CURRENT_TIMESTAMP, updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (project_id,),
            )
        if cursor.rowcount == 0:
            raise ValueError(f"Project not found: {project_id}")

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

    def save_chapter_rewrite(self, chapter_id: int, rewritten_text: str) -> None:
        chapter = self.get_chapter(chapter_id)
        if chapter is None:
            raise ValueError(f"Chapter not found: {chapter_id}")

        text = rewritten_text.strip()
        with session(self.database_path) as connection:
            if not text:
                connection.execute("DELETE FROM chapter_rewrites WHERE chapter_id = ?", (chapter_id,))
                connection.execute(
                    """
                    UPDATE chapters
                    SET rewritten_text = NULL, status = 'imported', updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (chapter_id,),
                )
            else:
                word_count = count_text_units(text)
                ratio = word_count / chapter.word_count if chapter.word_count else None
                connection.execute(
                    """
                    INSERT INTO chapter_rewrites (
                        chapter_id,
                        rewritten_text,
                        rewrite_source,
                        actual_word_count,
                        expansion_ratio,
                        prompt_snapshot_json,
                        anchor_snapshot_json,
                        rewrite_mode,
                        anchor_text,
                        expanded_text,
                        updated_at
                    ) VALUES (?, ?, 'manual', ?, ?, ?, '{}', 'full_rewrite', '', ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(chapter_id)
                    DO UPDATE SET
                        rewritten_text = excluded.rewritten_text,
                        rewrite_source = excluded.rewrite_source,
                        actual_word_count = excluded.actual_word_count,
                        expansion_ratio = excluded.expansion_ratio,
                        prompt_snapshot_json = excluded.prompt_snapshot_json,
                        anchor_snapshot_json = excluded.anchor_snapshot_json,
                        rewrite_mode = excluded.rewrite_mode,
                        anchor_text = excluded.anchor_text,
                        expanded_text = excluded.expanded_text,
                        confirmed_at = NULL,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        chapter_id,
                        text,
                        word_count,
                        ratio,
                        json.dumps({"source": "manual_edit"}, ensure_ascii=False),
                        text,
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
        self.refresh_project_progress(chapter.project_id)

    def refresh_project_progress(self, project_id: int) -> None:
        with session(self.database_path) as connection:
            project = connection.execute(
                "SELECT project_kind FROM projects WHERE id = ?",
                (project_id,),
            ).fetchone()
            summary_project = project is not None and project["project_kind"] == "legacy_extract"
            completed_expression = (
                """
                SUM(
                    CASE WHEN EXISTS (
                        SELECT 1
                        FROM chapter_stage_status stage_status
                        WHERE stage_status.chapter_id = chapters.id
                          AND stage_status.stage = 'summary'
                          AND stage_status.status = 'completed'
                    ) THEN 1 ELSE 0 END
                )
                """
                if summary_project
                else "SUM(CASE WHEN status IN ('rewritten', 'kept_original') THEN 1 ELSE 0 END)"
            )
            row = connection.execute(
                f"""
                SELECT
                    COUNT(*) AS total_chapters,
                    COALESCE(SUM(word_count), 0) AS total_words,
                    COALESCE({completed_expression}, 0) AS completed_chapters
                FROM chapters
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
            if row is None:
                raise ValueError(f"Project not found: {project_id}")
            connection.execute(
                """
                UPDATE projects
                SET
                    total_chapters = ?,
                    total_words = ?,
                    completed_chapters = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = ? AND deleted_at IS NULL
                """,
                (
                    row["total_chapters"],
                    row["total_words"],
                    row["completed_chapters"],
                    project_id,
                ),
            )

    def export_txt(self, project_id: int, output_path: str | Path) -> Path:
        chapters = self.get_effective_export_chapters(project_id)
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
                    self._export_word_count(chapters),
                ),
            )

        return output

    def export_legacy_analysis(self, project_id: int) -> dict:
        """Return the retained analysis corpus, not a disguised novel export."""
        project = self.get_project(project_id)
        if project is None:
            raise FileNotFoundError(f"Project not found: {project_id}")
        if project.project_kind != "legacy_extract":
            raise ValueError("Legacy analysis export is only available for legacy_extract projects.")
        with session(self.database_path) as connection:
            metadata = connection.execute(
                "SELECT * FROM book_metadata WHERE project_id = ?", (project_id,)
            ).fetchone()
            chapters = connection.execute(
                """
                SELECT c.id, c.chapter_index, c.title,
                       s.plot_summary, s.characters_json, s.key_events_json,
                       a.analysis_json AS style_analysis_json,
                       a.reviewed_json AS reviewed_style_json,
                       p.expanded_plot
                FROM chapters c
                LEFT JOIN chapter_summaries s ON s.chapter_id = c.id
                LEFT JOIN chapter_style_analyses a ON a.chapter_id = c.id
                LEFT JOIN chapter_plot_expansions p ON p.chapter_id = c.id
                WHERE c.project_id = ?
                ORDER BY c.chapter_index
                """,
                (project_id,),
            ).fetchall()
            characters = connection.execute(
                """
                SELECT id, name, aliases_json, description, profile_json,
                       relationship_notes, personality, speech_style,
                       action_constraints, anti_ooc_rules
                FROM character_cards
                WHERE project_id = ? AND deleted_at IS NULL
                ORDER BY id
                """,
                (project_id,),
            ).fetchall()
            style = connection.execute(
                "SELECT * FROM project_style_syntheses WHERE project_id = ?",
                (project_id,),
            ).fetchone()
            prompts = connection.execute(
                """
                SELECT prompt_key, prompt_text
                FROM project_custom_prompts WHERE project_id = ? ORDER BY prompt_key
                """,
                (project_id,),
            ).fetchall()
            skeletons = connection.execute(
                """
                SELECT s.id, s.scope, s.source_kind, s.status, s.chapter_id,
                       v.version, v.skeleton_json, v.nodes_json,
                       v.source_references_json, v.confirmed_at
                FROM story_skeletons s
                JOIN story_skeleton_versions v ON v.skeleton_id = s.id
                WHERE s.project_id = ?
                ORDER BY s.id, v.version
                """,
                (project_id,),
            ).fetchall()
        return {
            "schema": "rusty.legacy_analysis_export.v1",
            "project": {
                "id": project.id,
                "name": project.name,
                "project_kind": project.project_kind,
                "status": project.status,
                "created_at": project.created_at,
                "updated_at": project.updated_at,
            },
            "metadata": dict(metadata) if metadata else {},
            "chapter_analyses": [_decode_analysis_row(row) for row in chapters],
            "character_analyses": [_decode_analysis_row(row) for row in characters],
            "style_analysis": _decode_analysis_row(style) if style else {},
            "generated_prompts": [dict(row) for row in prompts],
            "structured_skeletons": [_decode_analysis_row(row) for row in skeletons],
        }

    def create_from_legacy(
        self,
        source_project_id: int,
        *,
        target_project_kind: str,
        copy_source_text: bool = True,
        copy_analysis_results: bool = True,
        project_name: str | None = None,
    ) -> int:
        if target_project_kind not in {"rewrite", "branch"}:
            raise ValueError("Target project kind must be rewrite or branch.")
        if not copy_source_text:
            raise ValueError("A derived writing project requires copy_source_text.")
        source = self.get_project(source_project_id)
        if source is None:
            raise FileNotFoundError(f"Project not found: {source_project_id}")
        if source.project_kind != "legacy_extract":
            raise ValueError("Only legacy_extract projects can use this migration endpoint.")
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM projects WHERE id = ?", (source_project_id,)
            ).fetchone()
            cursor = connection.execute(
                """
                INSERT INTO projects(
                    name, project_kind, status, current_stage, source_format,
                    source_path, workspace_path, total_chapters, total_words
                ) VALUES (?, ?, 'imported', 'split', ?, ?, ?, ?, ?)
                """,
                (
                    project_name.strip() if project_name and project_name.strip()
                    else f"{row['name']} - {'改写' if target_project_kind == 'rewrite' else '扩写'}",
                    target_project_kind,
                    row["source_format"],
                    row["source_path"],
                    row["workspace_path"],
                    row["total_chapters"],
                    row["total_words"],
                ),
            )
            target_project_id = int(cursor.lastrowid)
            _copy_rows(connection, "book_metadata", "project_id = ?", (source_project_id,), {"project_id": target_project_id})
            _copy_rows(connection, "import_sources", "project_id = ?", (source_project_id,), {"project_id": target_project_id})
            _copy_rows(connection, "project_settings", "project_id = ?", (source_project_id,), {"project_id": target_project_id, "processing_mode": "manual"})

            volume_map: dict[int, int] = {}
            for volume in connection.execute(
                "SELECT * FROM story_volumes WHERE project_id = ? ORDER BY volume_index",
                (source_project_id,),
            ).fetchall():
                volume_map[int(volume["id"])] = _copy_single_row(
                    connection, "story_volumes", volume, {"project_id": target_project_id}
                )
            chapter_map: dict[int, int] = {}
            for chapter in connection.execute(
                "SELECT * FROM chapters WHERE project_id = ? ORDER BY chapter_index",
                (source_project_id,),
            ).fetchall():
                overrides = {
                    "project_id": target_project_id,
                    "rewritten_text": None,
                    "status": "imported",
                }
                if chapter["volume_id"] is not None:
                    overrides["volume_id"] = volume_map[int(chapter["volume_id"])]
                chapter_map[int(chapter["id"])] = _copy_single_row(
                    connection, "chapters", chapter, overrides
                )
            for old_id, new_id in chapter_map.items():
                _copy_rows(connection, "chapter_source_versions", "chapter_id = ?", (old_id,), {"project_id": target_project_id, "chapter_id": new_id})
                _copy_rows(connection, "export_chapter_plan", "chapter_id = ?", (old_id,), {"project_id": target_project_id, "chapter_id": new_id})
                if copy_analysis_results:
                    for table in (
                        "chapter_summaries",
                        "chapter_style_analyses",
                        "chapter_scene_analysis",
                        "chapter_plot_expansions",
                    ):
                        _copy_rows(connection, table, "chapter_id = ?", (old_id,), {"chapter_id": new_id})
            if copy_analysis_results:
                for table in (
                    "project_style_syntheses",
                    "project_custom_prompts",
                    "character_cards",
                    "materials",
                ):
                    _copy_rows(connection, table, "project_id = ?", (source_project_id,), {"project_id": target_project_id})
                for skeleton in connection.execute(
                    "SELECT * FROM story_skeletons WHERE project_id = ? ORDER BY id",
                    (source_project_id,),
                ).fetchall():
                    overrides = {"project_id": target_project_id}
                    if skeleton["chapter_id"] is not None:
                        overrides["chapter_id"] = chapter_map[int(skeleton["chapter_id"])]
                    overrides["scene_id"] = None
                    new_skeleton_id = _copy_single_row(
                        connection, "story_skeletons", skeleton, overrides
                    )
                    _copy_rows(
                        connection,
                        "story_skeleton_versions",
                        "skeleton_id = ?",
                        (int(skeleton["id"]),),
                        {"skeleton_id": new_skeleton_id},
                    )
        return target_project_id

    def export_epub(self, project_id: int, output_path: str | Path) -> Path:
        chapters = self.get_effective_export_chapters(project_id)
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
                    self._export_word_count(chapters),
                ),
            )

        return output

    def list_export_plan(self, project_id: int) -> list[ExportPlanItem]:
        self._ensure_export_plan(project_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    p.chapter_id,
                    p.export_order,
                    COALESCE(NULLIF(p.export_title, ''), c.title) AS export_title,
                    p.include_in_export,
                    c.status,
                    r.rewrite_source,
                    r.confirmed_at
                FROM export_chapter_plan p
                JOIN chapters c ON c.id = p.chapter_id
                LEFT JOIN chapter_rewrites r ON r.chapter_id = c.id
                WHERE p.project_id = ?
                ORDER BY p.export_order, c.chapter_index, c.id
                """,
                (project_id,),
            ).fetchall()
        return [
            ExportPlanItem(
                chapter_id=row["chapter_id"],
                export_order=row["export_order"],
                export_title=row["export_title"],
                include_in_export=bool(row["include_in_export"]),
                source_status=_export_source_status(row["status"], row["rewrite_source"], row["confirmed_at"]),
            )
            for row in rows
        ]

    def save_export_plan(self, project_id: int, items: list[ExportPlanItem]) -> None:
        project = self.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        if not items:
            raise ValueError("Export plan cannot be empty.")
        chapter_ids = {chapter.id for chapter in self.list_chapters(project_id)}
        seen: set[int] = set()
        rows = []
        for position, item in enumerate(items, start=1):
            if item.chapter_id not in chapter_ids:
                raise ValueError(f"Chapter not found in project export plan: {item.chapter_id}")
            if item.chapter_id in seen:
                raise ValueError(f"Duplicate chapter in export plan: {item.chapter_id}")
            seen.add(item.chapter_id)
            rows.append(
                (
                    project_id,
                    item.chapter_id,
                    item.export_order if item.export_order > 0 else position,
                    item.export_title.strip(),
                    1 if item.include_in_export else 0,
                )
            )
        missing = chapter_ids - seen
        if missing:
            raise ValueError(f"Export plan is missing project chapters: {sorted(missing)}")

        with session(self.database_path) as connection:
            connection.execute("DELETE FROM export_chapter_plan WHERE project_id = ?", (project_id,))
            connection.executemany(
                """
                INSERT INTO export_chapter_plan (
                    project_id,
                    chapter_id,
                    export_order,
                    export_title,
                    include_in_export
                ) VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )

    def get_effective_export_chapters(self, project_id: int) -> list[EffectiveExportChapter]:
        self._ensure_export_plan(project_id)
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    c.id,
                    c.project_id,
                    p.export_order,
                    COALESCE(NULLIF(p.export_title, ''), c.title) AS export_title,
                    c.title AS original_title,
                    c.original_text,
                    CASE
                        WHEN r.confirmed_at IS NOT NULL OR c.status = 'confirmed' THEN c.rewritten_text
                        ELSE NULL
                    END AS rewritten_text,
                    c.word_count,
                    c.status,
                    c.source_start_line,
                    c.source_end_line,
                    p.include_in_export,
                    r.rewrite_source,
                    r.confirmed_at
                FROM export_chapter_plan p
                JOIN chapters c ON c.id = p.chapter_id
                LEFT JOIN chapter_rewrites r ON r.chapter_id = c.id
                WHERE p.project_id = ?
                  AND p.include_in_export = 1
                ORDER BY p.export_order, c.chapter_index, c.id
                """,
                (project_id,),
            ).fetchall()
        return [self._effective_export_chapter_from_row(row) for row in rows]

    def list_exports(self, project_id: int) -> list[ExportRecord]:
        with session(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    project_id,
                    export_format,
                    output_path,
                    chapter_count,
                    word_count,
                    created_at
                FROM exports
                WHERE project_id = ?
                ORDER BY created_at DESC, id DESC
                """,
                (project_id,),
            ).fetchall()
        return [
            ExportRecord(
                id=row["id"],
                project_id=row["project_id"],
                export_format=row["export_format"],
                output_path=row["output_path"],
                chapter_count=row["chapter_count"],
                word_count=row["word_count"],
                created_at=row["created_at"],
            )
            for row in rows
        ]

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

    def get_project_settings(self, project_id: int) -> ProjectSettings | None:
        with session(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                    project_id,
                    model_id,
                    prompt_template_id,
                    analysis_prompt_template_id,
                    txt_split_rule_id,
                    processing_mode,
                    concurrency,
                    target_word_count,
                    min_expansion_ratio,
                    rewrite_mode,
                    max_attempts
                FROM project_settings
                WHERE project_id = ?
                """,
                (project_id,),
            ).fetchone()
        return self._settings_from_row(row) if row is not None else None

    def update_project_settings(
        self,
        project_id: int,
        model_id: int | None = None,
        prompt_template_id: int | None = None,
        analysis_prompt_template_id: int | None = None,
        processing_mode: str = "manual",
        concurrency: int = 1,
        target_word_count: int | None = None,
        min_expansion_ratio: float | None = None,
        rewrite_mode: str = "anchor_expand",
        max_attempts: int = 2,
    ) -> None:
        if rewrite_mode not in {"anchor_expand", "full_rewrite"}:
            raise ValueError(f"Unsupported rewrite mode: {rewrite_mode}")
        if max_attempts < 1 or max_attempts > 10:
            raise ValueError("max_attempts must be between 1 and 10")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO project_settings (
                    project_id,
                    model_id,
                    prompt_template_id,
                    analysis_prompt_template_id,
                    processing_mode,
                    concurrency,
                    target_word_count,
                    min_expansion_ratio,
                    rewrite_mode,
                    max_attempts
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(project_id)
                DO UPDATE SET
                    model_id = excluded.model_id,
                    prompt_template_id = excluded.prompt_template_id,
                    analysis_prompt_template_id = excluded.analysis_prompt_template_id,
                    processing_mode = excluded.processing_mode,
                    concurrency = excluded.concurrency,
                    target_word_count = excluded.target_word_count,
                    min_expansion_ratio = excluded.min_expansion_ratio,
                    rewrite_mode = excluded.rewrite_mode,
                    max_attempts = excluded.max_attempts,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    project_id,
                    model_id,
                    prompt_template_id,
                    analysis_prompt_template_id,
                    processing_mode,
                    concurrency,
                    target_word_count,
                    min_expansion_ratio,
                    rewrite_mode,
                    max_attempts,
                ),
            )

    @staticmethod
    def _project_from_row(row) -> ProjectSummary:
        return ProjectSummary(
            id=row["id"],
            name=row["name"],
            project_kind=row["project_kind"],
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

    @staticmethod
    def _export_word_count(chapters: list[ChapterRecord]) -> int:
        return sum(count_text_units(chapter.rewritten_text or chapter.original_text) for chapter in chapters)

    def _ensure_export_plan(self, project_id: int) -> None:
        project = self.get_project(project_id)
        if project is None:
            raise ValueError(f"Project not found: {project_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO export_chapter_plan (
                    project_id,
                    chapter_id,
                    export_order,
                    export_title,
                    include_in_export
                )
                SELECT
                    c.project_id,
                    c.id,
                    c.chapter_index,
                    c.title,
                    1
                FROM chapters c
                WHERE c.project_id = ?
                """,
                (project_id,),
            )
            connection.execute(
                """
                DELETE FROM export_chapter_plan
                WHERE project_id = ?
                  AND chapter_id NOT IN (
                    SELECT id FROM chapters WHERE project_id = ?
                  )
                """,
                (project_id, project_id),
            )

    @staticmethod
    def _settings_from_row(row) -> ProjectSettings:
        return ProjectSettings(
            project_id=row["project_id"],
            model_id=row["model_id"],
            prompt_template_id=row["prompt_template_id"],
            analysis_prompt_template_id=row["analysis_prompt_template_id"],
            txt_split_rule_id=row["txt_split_rule_id"],
            processing_mode=row["processing_mode"],
            concurrency=row["concurrency"],
            target_word_count=row["target_word_count"],
            min_expansion_ratio=row["min_expansion_ratio"],
            rewrite_mode=row["rewrite_mode"],
            max_attempts=row["max_attempts"],
        )

    @staticmethod
    def _effective_export_chapter_from_row(row) -> EffectiveExportChapter:
        source_status = _export_source_status(row["status"], row["rewrite_source"], row["confirmed_at"])
        return EffectiveExportChapter(
            id=row["id"],
            project_id=row["project_id"],
            index=row["export_order"],
            title=row["export_title"],
            original_title=row["original_title"],
            original_text=row["original_text"],
            rewritten_text=row["rewritten_text"],
            word_count=row["word_count"],
            status=row["status"],
            source_status=source_status,
            include_in_export=bool(row["include_in_export"]),
            start_line=row["source_start_line"],
            end_line=row["source_end_line"],
        )


def _export_source_status(chapter_status: str, rewrite_source: str | None, confirmed_at: str | None = None) -> str:
    if chapter_status == "kept_original":
        return "kept_original"
    if chapter_status != "confirmed" and confirmed_at is None:
        return "original"
    if rewrite_source == "manual":
        return "manual_rewrite"
    if rewrite_source == "ai":
        return "ai_rewrite"
    return "original"


def _copy_single_row(connection, table: str, row, overrides: dict) -> int:
    values = dict(row)
    values.pop("id", None)
    values.update(overrides)
    columns = [
        item["name"]
        for item in connection.execute(f"PRAGMA table_info({table})").fetchall()
        if item["name"] in values
    ]
    placeholders = ", ".join("?" for _ in columns)
    cursor = connection.execute(
        f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({placeholders})",
        tuple(values[column] for column in columns),
    )
    return int(cursor.lastrowid)


def _copy_rows(
    connection,
    table: str,
    where: str,
    params: tuple,
    overrides: dict,
) -> list[int]:
    return [
        _copy_single_row(connection, table, row, overrides)
        for row in connection.execute(
            f"SELECT * FROM {table} WHERE {where}", params
        ).fetchall()
    ]


def _decode_analysis_row(row) -> dict:
    result = dict(row)
    for key, value in list(result.items()):
        if key.endswith("_json") and isinstance(value, str):
            try:
                result[key.removesuffix("_json")] = json.loads(value)
                del result[key]
            except json.JSONDecodeError:
                pass
    return result
