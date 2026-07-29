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
    def test_volume_directory_api_returns_nested_chapters_and_supports_rename(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "nested.txt"
            source.write_text(
                "第七卷 雨夜\n\n第787章 雨夜\n正文。\n",
                encoding="utf-8",
            )
            environment = {
                "RUSTY_API_TOKEN": "document-test-token",
                "RUSTY_DOCUMENT_LIBRARY_PATH": str(root / "library"),
            }
            headers = {"X-Rusty-Token": "document-test-token"}
            with patch.dict(os.environ, environment):
                client = TestClient(create_app(root / "rusty.db"))
                imported = client.post(
                    "/api/documents/import",
                    headers=headers,
                    json={"source_path": str(source)},
                )
                document_id = imported.json()["document"]["id"]
                directory_before = client.get(
                    f"/api/documents/{document_id}/directory"
                )
                volume = directory_before.json()["volumes"][0]
                renamed = client.post(
                    f"/api/documents/{document_id}/volumes/{volume['id']}",
                    headers=headers,
                    json={"title": "第七卷 新雨"},
                )
                directory_after = client.get(
                    f"/api/documents/{document_id}/directory"
                )

            self.assertEqual(200, directory_before.status_code)
            self.assertEqual("第七卷 雨夜", volume["title"])
            self.assertEqual(["第787章 雨夜"], [item["title"] for item in volume["chapters"]])
            self.assertEqual([], directory_before.json()["unassigned_chapters"])
            self.assertEqual(200, renamed.status_code)
            self.assertEqual("第七卷 新雨", directory_after.json()["volumes"][0]["title"])

    def test_document_draft_api_autosaves_commits_once_and_reports_conflict(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "draft-api.txt"
            source.write_text("第一章\n\n正文。\n\n第二章\n\n尾声。\n", encoding="utf-8")
            environment = {
                "RUSTY_API_TOKEN": "document-test-token",
                "RUSTY_DOCUMENT_LIBRARY_PATH": str(root / "library"),
            }
            headers = {"X-Rusty-Token": "document-test-token"}
            with patch.dict(os.environ, environment):
                client = TestClient(create_app(root / "rusty.db"))
                imported = client.post("/api/documents/import", headers=headers, json={"source_path": str(source)})
                document_id = imported.json()["document"]["id"]
                chapter = client.get(f"/api/documents/{document_id}/chapters").json()[0]
                content = client.get(
                    f"/api/documents/{document_id}/content",
                    params={"chapter_id": chapter["id"]},
                ).json()
                before = client.get(f"/api/documents/{document_id}/revisions").json()
                saved = client.put(
                    f"/api/documents/{document_id}/draft",
                    headers=headers,
                    json={
                        "chapter_id": chapter["id"],
                        "base_revision_id": content["revision_id"],
                        "title": "新标题",
                        "text": "草稿正文",
                    },
                )
                after_autosave = client.get(f"/api/documents/{document_id}/revisions").json()
                committed = client.post(
                    f"/api/documents/{document_id}/draft/commit",
                    headers=headers,
                    json={"chapter_id": chapter["id"]},
                )

                self.assertEqual(200, saved.status_code)
                self.assertEqual(len(before), len(after_autosave))
                self.assertEqual(200, committed.status_code)
                self.assertEqual(len(before) + 1, len(client.get(f"/api/documents/{document_id}/revisions").json()))
                self.assertIsNone(
                    client.get(
                        f"/api/documents/{document_id}/draft",
                        params={"chapter_id": chapter["id"]},
                    ).json()
                )

                current_chapter = client.get(f"/api/documents/{document_id}/chapters").json()[0]
                current_content = client.get(
                    f"/api/documents/{document_id}/content",
                    params={"chapter_id": current_chapter["id"]},
                ).json()
                client.put(
                    f"/api/documents/{document_id}/draft",
                    headers=headers,
                    json={
                        "chapter_id": current_chapter["id"],
                        "base_revision_id": current_content["revision_id"],
                        "title": current_content["title"],
                        "text": "会冲突的草稿",
                    },
                )
                full = client.get(f"/api/documents/{document_id}/content").json()
                client.post(
                    f"/api/documents/{document_id}/content",
                    headers=headers,
                    json={"chapter_id": None, "title": full["title"], "text": full["body_text"] + "新版本"},
                )
                conflict = client.post(
                    f"/api/documents/{document_id}/draft/commit",
                    headers=headers,
                    json={"chapter_id": current_chapter["id"]},
                )

            self.assertEqual(409, conflict.status_code)
            self.assertEqual("document_draft_conflict", conflict.json()["error"])

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
            self.assertEqual(200, migrated.status_code, migrated.text)
            self.assertEqual(str((root / "migrated-library").resolve()), migrated.json()["storage_path"])
            self.assertEqual(200, listed.status_code)
            self.assertEqual(1, len(listed.json()))
            self.assertEqual(".txt", Path(listed.json()[0]["storage_path"]).suffix)
            self.assertEqual(200, deleted.status_code)
            self.assertEqual([], listed_after_delete.json())


if __name__ == "__main__":
    unittest.main()
