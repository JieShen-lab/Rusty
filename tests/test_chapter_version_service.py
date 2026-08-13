from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from backend.api import create_app
from rusty.db import session
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.project_service import ProjectService


class ChapterVersionServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = initialized_database(self.root / "rusty.db")
        source = self.root / "book.txt"
        source.write_text("1. One\nimmutable original", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind="rewrite"
        )
        self.chapter_id = self.projects.list_chapters(self.project_id)[0].id
        self.versions = ChapterVersionService(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_restore_appends_new_version_from_historical_parent(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "version one")
        v1 = self.versions.list_versions(self.chapter_id)[0]
        self.projects.save_chapter_rewrite(self.chapter_id, "version two")
        v2 = self.versions.list_versions(self.chapter_id)[0]

        restored = self.versions.restore_version(v1["id"])
        all_versions = self.versions.list_versions(self.chapter_id)

        self.assertEqual(3, restored["version"])
        self.assertEqual(v1["id"], restored["parent_version_id"])
        self.assertEqual("restore", restored["source_operation"])
        self.assertEqual("version one", restored["rewritten_text"])
        self.assertTrue(restored["is_current"])
        self.assertEqual("version two", self.versions.get_version(v2["id"])["rewritten_text"])
        self.assertEqual([3, 2, 1], [item["version"] for item in all_versions])

    def test_current_head_and_compatibility_projections_stay_identical(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "projection invariant")

        with session(self.database) as connection:
            row = connection.execute(
                """
                SELECT v.rewritten_text AS head_text, v.version AS head_version,
                       h.rewritten_text AS rewrite_text,
                       h.current_version AS rewrite_version,
                       c.rewritten_text AS chapter_text
                FROM chapter_rewrites h
                JOIN chapter_rewrite_versions v ON v.id = h.current_version_id
                JOIN chapters c ON c.id = h.chapter_id
                WHERE h.chapter_id = ?
                """,
                (self.chapter_id,),
            ).fetchone()

        self.assertEqual(row["head_text"], row["rewrite_text"])
        self.assertEqual(row["head_text"], row["chapter_text"])
        self.assertEqual(row["head_version"], row["rewrite_version"])

    def test_source_selection_resolves_current_original_and_history(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "version one")
        v1 = self.versions.list_versions(self.chapter_id)[0]
        self.projects.save_chapter_rewrite(self.chapter_id, "version two")

        current = self.versions.resolve_chapter_source(self.chapter_id)
        original = self.versions.resolve_chapter_source(
            self.chapter_id, {"kind": "original"}
        )
        history = self.versions.resolve_chapter_source(
            self.chapter_id, {"kind": "rewrite_version", "version_id": v1["id"]}
        )

        self.assertEqual("version two", current.text)
        self.assertTrue(current.require_head_match)
        self.assertEqual("immutable original", original.text)
        self.assertTrue(original.require_head_match)
        self.assertEqual("version one", history.text)
        self.assertTrue(history.require_head_match)
        self.assertEqual(current.source_version_id, original.expected_head_version_id)
        self.assertEqual(current.source_version_id, history.expected_head_version_id)

    def test_version_http_api_lists_reads_and_restores_without_deleting_history(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "version one")
        version = self.versions.list_versions(self.chapter_id)[0]
        os.environ["RUSTY_API_TOKEN"] = "version-test-token"
        client = TestClient(create_app(self.database))

        listed = client.get(f"/api/chapters/{self.chapter_id}/rewrite-versions")
        read = client.get(f"/api/chapter-rewrite-versions/{version['id']}")
        restored = client.post(
            f"/api/chapter-rewrite-versions/{version['id']}/restore",
            headers={"X-Rusty-Token": "version-test-token"},
        )

        self.assertEqual(200, listed.status_code)
        self.assertEqual(200, read.status_code)
        self.assertEqual(200, restored.status_code)
        self.assertEqual(version["id"], restored.json()["parent_version_id"])
        self.assertEqual(2, len(self.versions.list_versions(self.chapter_id)))


if __name__ == "__main__":
    unittest.main()
