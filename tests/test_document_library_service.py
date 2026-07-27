from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from docx import Document
from ebooklib import epub

from rusty.services.document_library_service import DocumentLibraryService


class DocumentLibraryServiceTests(unittest.TestCase):
    def test_default_cleanup_template_versions_text_and_can_restore_import(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "排版.txt"
            source.write_text("  第一章 风起\n第一段。\n\n　第二段。\n", encoding="utf-8")
            service = DocumentLibraryService(root / "rusty.db", root / "library")
            imported = service.import_document(source)
            template = service.list_processing_templates()[0]

            cleaned = service.apply_cleanup(imported.document.id, template.id)
            repeated = service.apply_cleanup(imported.document.id, template.id)
            revisions = service.list_revisions(imported.document.id)
            cleaned_text = Path(cleaned.document.storage_path).read_text(encoding="utf-8")

            self.assertTrue(template.is_default)
            self.assertEqual(0, template.settings["chapter_indent"])
            self.assertEqual(2, template.settings["paragraph_indent"])
            self.assertEqual("第一章 风起\n\n　　第一段。\n\n　　第二段。\n", cleaned_text)
            self.assertTrue(cleaned.created)
            self.assertFalse(repeated.created)
            self.assertEqual(2, len(revisions))
            self.assertEqual("processed", cleaned.document.status)

            restored = service.activate_revision(imported.document.id, revisions[-1].id)
            self.assertEqual("imported", restored.status)
            self.assertEqual(imported.document.storage_path, restored.storage_path)

    def test_txt_is_normalized_to_utf8_and_duplicate_content_is_reused(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "原稿.txt"
            source.write_bytes("第一章\r\n正文。".encode("gb18030"))
            service = DocumentLibraryService(root / "rusty.db", root / "library")

            first = service.import_document(source)
            second = service.import_document(source)
            renamed = service.update_document_metadata(
                first.document.id,
                title="新的书名",
                author="作者甲",
            )

            stored_path = Path(first.document.storage_path)
            self.assertTrue(first.created)
            self.assertFalse(second.created)
            self.assertEqual(first.document.id, second.document.id)
            self.assertEqual(".txt", stored_path.suffix)
            self.assertEqual("第一章\n正文。\n", stored_path.read_text(encoding="utf-8"))
            self.assertEqual("txt", first.document.source_format)
            self.assertEqual("新的书名", renamed.title)
            self.assertEqual("作者甲", renamed.author)
            self.assertEqual(1, len(service.list_documents()))

    def test_categories_chapters_migration_and_exports_are_functional(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "长篇.txt"
            source.write_text(
                "第一章 风起\n第一段。\n\n第二章 归途\n第二段。\n",
                encoding="utf-8",
            )
            database_path = root / "rusty.db"
            original_library = root / "library"
            migrated_library = root / "migrated-library"
            service = DocumentLibraryService(database_path, original_library)

            imported = service.import_document(source)
            category = service.create_category("参考资料")
            assigned = service.set_document_category(imported.document.id, category.id, True)
            chapters = service.list_chapters(imported.document.id)
            full_content = service.get_content(imported.document.id)
            chapter_content = service.get_content(imported.document.id, chapters[1].id)
            reordered = service.reorder_chapters(
                imported.document.id,
                [chapters[1].id, chapters[0].id],
            )
            original_paths = [Path(item.storage_path) for item in service.list_revisions(imported.document.id)]

            migrated = service.migrate_library_path(migrated_library)
            txt_output = service.export_document(imported.document.id, "txt", root / "export.txt")
            epub_output = service.export_document(imported.document.id, "epub", root / "export.epub")
            restarted = DocumentLibraryService(database_path)

            self.assertEqual(["参考资料"], assigned.categories)
            self.assertEqual(1, service.list_categories()[0].document_count)
            self.assertEqual(["第一章 风起", "第二章 归途"], [item.title for item in chapters])
            self.assertIn("第一章 风起", full_content.text)
            self.assertEqual("第二章 归途", chapter_content.title)
            self.assertIn("第二段。", chapter_content.text)
            self.assertEqual(["第二章 归途", "第一章 风起"], [item.title for item in reordered])
            self.assertEqual(migrated_library.resolve(), migrated)
            self.assertEqual(migrated_library.resolve(), restarted.get_library_path().resolve())
            self.assertTrue(all(not path.exists() for path in original_paths))
            self.assertTrue(all(Path(item.storage_path).parent == migrated_library.resolve() for item in service.list_revisions(imported.document.id)))
            self.assertIn("第一章 风起", txt_output.read_text(encoding="utf-8"))
            self.assertLess(
                txt_output.read_text(encoding="utf-8").index("第二章 归途"),
                txt_output.read_text(encoding="utf-8").index("第一章 风起"),
            )
            self.assertTrue(epub_output.is_file())
            self.assertGreater(epub_output.stat().st_size, 0)
            service.delete_document(imported.document.id)
            self.assertEqual([], service.list_documents())

    def test_docx_is_flattened_to_txt_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "word.docx"
            document = Document()
            document.core_properties.title = "Word 示例"
            document.core_properties.author = "作者甲"
            document.add_heading("第一章", level=1)
            document.add_paragraph("第一段正文。")
            document.add_heading("第二章", level=1)
            document.add_paragraph("第二段正文。")
            document.save(source)
            service = DocumentLibraryService(root / "rusty.db", root / "library")

            result = service.import_document(source)
            stored_text = Path(result.document.storage_path).read_text(encoding="utf-8")

            self.assertEqual("Word 示例", result.document.title)
            self.assertEqual("作者甲", result.document.author)
            self.assertEqual("docx", result.document.source_format)
            self.assertEqual(2, result.document.chapter_count)
            self.assertIn("第一章\n\n第一段正文。", stored_text)
            self.assertIn("第二章\n\n第二段正文。", stored_text)
            self.assertEqual(".txt", Path(result.document.storage_path).suffix)

    def test_epub_is_flattened_to_txt_with_metadata(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.epub"
            _write_sample_epub(source)
            service = DocumentLibraryService(root / "rusty.db", root / "library")

            result = service.import_document(source)
            stored_text = Path(result.document.storage_path).read_text(encoding="utf-8")

            self.assertEqual("EPUB 示例", result.document.title)
            self.assertEqual("作者乙", result.document.author)
            self.assertEqual("epub", result.document.source_format)
            self.assertIn("开篇\n\n第一段。", stored_text)
            self.assertEqual(".txt", Path(result.document.storage_path).suffix)


def _write_sample_epub(path: Path) -> None:
    book = epub.EpubBook()
    book.set_identifier("library-test")
    book.set_title("EPUB 示例")
    book.set_language("zh-CN")
    book.add_author("作者乙")
    chapter = epub.EpubHtml(title="开篇", file_name="chapter.xhtml", lang="zh-CN")
    chapter.content = "<h1>开篇</h1><p>第一段。</p>"
    book.add_item(chapter)
    book.toc = (chapter,)
    book.spine = ["nav", chapter]
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    epub.write_epub(str(path), book)


if __name__ == "__main__":
    unittest.main()
