from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docx import Document

from rusty.importers.epub import parse_epub
from rusty.services import ProjectService


class ProjectServiceTests(unittest.TestCase):
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

