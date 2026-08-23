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


if __name__ == "__main__":
    unittest.main()
