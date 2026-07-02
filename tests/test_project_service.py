from __future__ import annotations

import sys
import sqlite3
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docx import Document

from rusty.importers.epub import parse_epub
from rusty.services import ProjectService


class ProjectServiceTests(unittest.TestCase):
    def test_delete_project_soft_deletes_from_project_list(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            txt_path = root / "delete-me.txt"
            database_path = root / "rusty.db"
            txt_path.write_text("1. Opening\nOriginal text.\n", encoding="utf-8")

            service = ProjectService(database_path)
            project_id = service.import_book(txt_path, root)
            chapters_before_delete = service.list_chapters(project_id)

            service.delete_project(project_id)
            projects_after_delete = service.list_projects()
            project_after_delete = service.get_project(project_id)
            chapters_after_delete = service.list_chapters(project_id)

        self.assertEqual(1, len(chapters_before_delete))
        self.assertEqual([], projects_after_delete)
        self.assertIsNone(project_after_delete)
        self.assertEqual(chapters_before_delete, chapters_after_delete)

    def test_save_chapter_rewrite_updates_export_text_and_can_clear(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            txt_path = root / "manual.txt"
            database_path = root / "rusty.db"
            export_path = root / "manual-export.txt"
            txt_path.write_text("1. Opening\nOriginal text.\n", encoding="utf-8")

            service = ProjectService(database_path)
            project_id = service.import_book(txt_path, root)
            chapter = service.list_chapters(project_id)[0]

            service.save_chapter_rewrite(chapter.id, "Manual rewrite.")
            updated = service.get_chapter(chapter.id)
            project_after_rewrite = service.get_project(project_id)
            service.export_txt(project_id, export_path)
            export_records = service.list_exports(project_id)
            exported_text = export_path.read_text(encoding="utf-8")
            connection = sqlite3.connect(database_path)
            try:
                rewrite_source, prompt_snapshot_json, anchor_snapshot_json = connection.execute(
                    """
                    SELECT rewrite_source, prompt_snapshot_json, anchor_snapshot_json
                    FROM chapter_rewrites
                    WHERE chapter_id = ?
                    """,
                    (chapter.id,),
                ).fetchone()
            finally:
                connection.close()

            service.save_chapter_rewrite(chapter.id, "")
            cleared = service.get_chapter(chapter.id)
            project_after_clear = service.get_project(project_id)

        self.assertIsNotNone(updated)
        self.assertEqual("Manual rewrite.", updated.rewritten_text)
        self.assertEqual("rewritten", updated.status)
        self.assertIsNotNone(project_after_rewrite)
        self.assertEqual(1, project_after_rewrite.completed_chapters)
        self.assertEqual(1, len(export_records))
        self.assertEqual("txt", export_records[0].export_format)
        self.assertEqual(str(export_path), export_records[0].output_path)
        self.assertEqual(14, export_records[0].word_count)
        self.assertEqual("manual", rewrite_source)
        self.assertIn("manual_edit", prompt_snapshot_json)
        self.assertEqual("{}", anchor_snapshot_json)
        self.assertIn("Manual rewrite.", exported_text)
        self.assertNotIn("Original text.", exported_text)
        self.assertIsNotNone(cleared)
        self.assertIsNone(cleared.rewritten_text)
        self.assertEqual("imported", cleared.status)
        self.assertIsNotNone(project_after_clear)
        self.assertEqual(0, project_after_clear.completed_chapters)

    def test_import_docx_persists_metadata_and_exports_epub(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            docx_path = root / "service.docx"
            database_path = root / "rusty.db"
            epub_path = root / "service.epub"

            document = Document()
            document.core_properties.title = "Service Book"
            document.core_properties.author = "Service Author"
            document.add_heading("Opening", level=1)
            document.add_paragraph("A saved chapter.")
            document.save(docx_path)

            service = ProjectService(database_path)
            project_id = service.import_book(docx_path, root)
            project = service.get_project(project_id)
            metadata = service.get_book_metadata(project_id)
            chapters = service.list_chapters(project_id)
            exported = service.export_epub(project_id, epub_path)
            parsed_export = parse_epub(exported)

        self.assertIsNotNone(project)
        self.assertEqual("Service Book", project.name)
        self.assertEqual("docx", project.source_format)
        self.assertEqual("Service Author", metadata["author"])
        self.assertEqual(1, len(chapters))
        self.assertEqual("Opening", chapters[0].title)
        self.assertEqual("Service Book", parsed_export.title)
        self.assertEqual("Service Author", parsed_export.author)


if __name__ == "__main__":
    unittest.main()
