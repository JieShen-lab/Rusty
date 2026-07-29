from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient

from backend.api import create_app


class DocumentLibraryApiTests(unittest.TestCase):
    def test_import_and_list_document(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "sample.txt"
            source.write_text("第一章\n正文。", encoding="utf-8")
            environment = {
                "RUSTY_API_TOKEN": "document-test-token",
                "RUSTY_DOCUMENT_LIBRARY_PATH": str(root / "library"),
            }
            with patch.dict(os.environ, environment):
                client = TestClient(create_app(root / "rusty.db"))
                imported = client.post(
                    "/api/documents/import",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"source_path": str(source)},
                )
                templates = client.get("/api/document-processing-templates")
                cleaned = client.post(
                    f"/api/documents/{imported.json()['document']['id']}/cleanup",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"template_id": templates.json()[0]["id"]},
                )
                document_id = imported.json()["document"]["id"]
                updated = client.post(
                    f"/api/documents/{document_id}",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"title": "参考文本", "author": "测试作者"},
                )
                tag = client.post(
                    "/api/document-tags",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"name": "资料"},
                )
                assigned = client.post(
                    f"/api/documents/{document_id}/tags/{tag.json()['id']}",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"selected": True},
                )
                category = client.post(
                    "/api/document-categories",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"name": "研究"},
                )
                category_assigned = client.post(
                    f"/api/documents/{document_id}/categories/{category.json()['id']}",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"selected": True},
                )
                chapters = client.get(f"/api/documents/{document_id}/chapters")
                content = client.get(f"/api/documents/{document_id}/content")
                reordered = client.post(
                    f"/api/documents/{document_id}/chapters/reorder",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"ordered_chapter_ids": [item["id"] for item in reversed(chapters.json())]},
                )
                txt_output = root / "output.txt"
                epub_output = root / "output.epub"
                exported_txt = client.post(
                    f"/api/documents/{document_id}/export",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"format": "txt", "output_path": str(txt_output)},
                )
                exported_epub = client.post(
                    f"/api/documents/{document_id}/export",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"format": "epub", "output_path": str(epub_output)},
                )
                migrated = client.post(
                    "/api/document-library/migrate",
                    headers={"X-Rusty-Token": "document-test-token"},
                    json={"target_path": str(root / "migrated-library")},
                )
                listed = client.get("/api/documents")
                deleted = client.post(
                    f"/api/documents/{document_id}/delete",
                    headers={"X-Rusty-Token": "document-test-token"},
                )
                listed_after_delete = client.get("/api/documents")

            self.assertEqual(200, imported.status_code)
            self.assertTrue(imported.json()["created"])
            self.assertEqual("txt", imported.json()["storage_format"])
            self.assertEqual(200, templates.status_code)
            self.assertEqual(2, templates.json()[0]["settings"]["paragraph_indent"])
            self.assertEqual(200, cleaned.status_code)
            self.assertTrue(cleaned.json()["created"])
            self.assertEqual(200, updated.status_code)
            self.assertEqual("参考文本", updated.json()["title"])
            self.assertEqual("测试作者", updated.json()["author"])
            self.assertEqual(200, tag.status_code)
            self.assertEqual(["资料"], assigned.json()["tags"])
            self.assertEqual(200, category.status_code)
            self.assertEqual(["研究"], category_assigned.json()["categories"])
            self.assertEqual([category.json()["id"]], category_assigned.json()["category_ids"])
            self.assertFalse(category_assigned.json()["is_project_document"])
            self.assertGreaterEqual(len(chapters.json()), 1)
            self.assertEqual(200, content.status_code)
            self.assertIn("正文。", content.json()["text"])
            self.assertEqual(200, reordered.status_code)
            self.assertEqual(200, exported_txt.status_code)
            self.assertEqual(200, exported_epub.status_code)
            self.assertTrue(txt_output.is_file())
            self.assertTrue(epub_output.is_file())
            self.assertEqual(str((root / "migrated-library").resolve()), migrated.json()["storage_path"])
            self.assertEqual(200, listed.status_code)
            self.assertEqual(1, len(listed.json()))
            self.assertEqual(".txt", Path(listed.json()[0]["storage_path"]).suffix)
            self.assertEqual(200, deleted.status_code)
            self.assertEqual([], listed_after_delete.json())


if __name__ == "__main__":
    unittest.main()
