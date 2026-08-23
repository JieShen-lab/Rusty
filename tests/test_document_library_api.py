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
    def test_project_creation_does_not_create_a_library_document_copy(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "project.txt"
            source.write_text("第一章\n\n这是工程正文。\n", encoding="utf-8")
            library_path = root / "library"
            environment = {
                "RUSTY_API_TOKEN": "project-test-token",
                "RUSTY_DOCUMENT_LIBRARY_PATH": str(library_path),
            }
            headers = {"X-Rusty-Token": "project-test-token"}
            with patch.dict(os.environ, environment):
                client = TestClient(create_app(root / "rusty.db"))
                before = client.get("/api/documents")
                preview = client.post(
                    "/api/projects/preview",
                    headers=headers,
                    json={"source_path": str(source), "workspace_path": str(root)},
                )
                created = client.post(
                    "/api/projects",
                    headers=headers,
                    json={"preview_token": preview.json()["preview_token"], "project_name": "独立工程"},
                )
                after = client.get("/api/documents")

            self.assertEqual(200, before.status_code)
            self.assertEqual(200, preview.status_code)
            self.assertEqual(200, created.status_code)
            self.assertEqual(200, after.status_code)
            self.assertEqual([], before.json())
            self.assertEqual([], after.json())
            self.assertFalse(library_path.exists())

    def test_volume_directory_returns_nested_chapters_and_supports_rename(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "nested.txt"
            source.write_text("第七卷 雨夜\n\n第787章 雨夜\n正文。\n", encoding="utf-8")
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
                directory_before = client.get(f"/api/documents/{document_id}/directory")
                volume = directory_before.json()["volumes"][0]
                renamed = client.post(
                    f"/api/documents/{document_id}/volumes/{volume['id']}",
                    headers=headers,
                    json={"title": "第七卷 新雨"},
                )
                directory_after = client.get(f"/api/documents/{document_id}/directory")

            self.assertEqual(200, directory_before.status_code)
            self.assertEqual("第七卷 雨夜", volume["title"])
            self.assertEqual(["雨夜"], [item["title"] for item in volume["chapters"]])
            self.assertEqual([], directory_before.json()["unassigned_chapters"])
            self.assertEqual(200, renamed.status_code)
            self.assertEqual("第七卷 新雨", directory_after.json()["volumes"][0]["title"])

    def test_document_categories_can_be_assigned_and_removed(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "categorized.txt"
            source.write_text("第一章\n正文。\n", encoding="utf-8")
            environment = {
                "RUSTY_API_TOKEN": "category-test-token",
                "RUSTY_DOCUMENT_LIBRARY_PATH": str(root / "library"),
            }
            headers = {"X-Rusty-Token": "category-test-token"}
            with patch.dict(os.environ, environment):
                client = TestClient(create_app(root / "rusty.db"))
                imported = client.post(
                    "/api/documents/import",
                    headers=headers,
                    json={"source_path": str(source)},
                ).json()["document"]
                category = client.post(
                    "/api/document-categories",
                    headers=headers,
                    json={"name": "参考资料"},
                ).json()
                assigned = client.put(
                    f"/api/documents/{imported['id']}/categories",
                    headers=headers,
                    json={"category_ids": [category["id"]]},
                )
                removed = client.put(
                    f"/api/documents/{imported['id']}/categories",
                    headers=headers,
                    json={"category_ids": []},
                )

            self.assertEqual(200, assigned.status_code)
            self.assertEqual([category["id"]], assigned.json()["category_ids"])
            self.assertEqual(["参考资料"], assigned.json()["categories"])
            self.assertEqual(200, removed.status_code)
            self.assertEqual([], removed.json()["category_ids"])


if __name__ == "__main__":
    unittest.main()
