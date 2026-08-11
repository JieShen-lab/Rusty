from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v41
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


class CreativeWorkspaceTests(unittest.TestCase):
    def test_v41_migration_backfills_chapter_state_and_is_idempotent(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY);
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                deleted_at TEXT
            );
            INSERT INTO chapters(id) VALUES (10), (20);
            """
        )

        _migrate_to_v41(connection)
        _migrate_to_v41(connection)

        rows = connection.execute(
            "SELECT chapter_id, current_stage FROM chapter_workflow_state ORDER BY chapter_id"
        ).fetchall()
        self.assertEqual([(10, "not_started"), (20, "not_started")], [tuple(row) for row in rows])
        self.assertEqual(41, CURRENT_SCHEMA_VERSION)

    def test_rewrite_and_branch_projects_share_persisted_chapter_workflow(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章 起宴\n张三退到了墙边。\n\n第二章 夜宴\n王五举刀。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            parsed = projects.preview_book(source)
            rewrite_id = projects.create_project(parsed, root, project_kind="rewrite")
            branch_id = projects.create_project(parsed, root, project_name="历史分支", project_kind="branch")
            service = CreativeWorkflowService(database)
            scene_service = SceneService(database)

            for project_id in (rewrite_id, branch_id):
                chapter = projects.list_chapters(project_id)[0]
                scene = scene_service.split_chapter(chapter.id)[0]
                saved = service.update_chapter_state(
                    chapter.id, active_scene_id=scene.id, current_stage="preanalysis"
                )
                restored = CreativeWorkflowService(database).get_chapter_state(chapter.id)
                self.assertEqual("preanalysis", saved["current_stage"])
                self.assertEqual(scene.id, restored["active_scene_id"])

    def test_api_keeps_legacy_extract_on_dedicated_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n原文。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE projects SET project_kind = 'legacy_extract' WHERE id = ?", (project_id,)
                )
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            os.environ["RUSTY_DATABASE_PATH"] = str(database)
            from backend.api import create_app

            with TestClient(create_app(database)) as client:
                response = client.get(f"/api/projects/{project_id}/creative-workflow")

        self.assertEqual(409, response.status_code)
        self.assertEqual("legacy_extract_workflow", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
