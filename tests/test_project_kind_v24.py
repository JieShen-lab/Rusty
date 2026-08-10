from __future__ import annotations

import sqlite3
import os
import sys
import tempfile
import unittest
from pathlib import Path

from pydantic import ValidationError
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.schemas import CreateProjectRequest
from rusty.db.schema import CURRENT_SCHEMA_VERSION, initialize_database
from rusty.services.project_service import ProjectService


class ProjectKindV24Tests(unittest.TestCase):
    def test_new_database_and_project_service_support_only_new_kinds(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. Opening\nOriginal.", encoding="utf-8")
            service = ProjectService(root / "rusty.db")

            rewrite_id = service.create_project(
                service.preview_book(source),
                root,
                project_kind="rewrite",
            )
            branch_id = service.create_project(
                service.preview_book(source),
                root,
                project_name="Branch",
                project_kind="branch",
            )

            with self.assertRaisesRegex(ValueError, "Unsupported project kind"):
                service.create_project(
                    service.preview_book(source),
                    root,
                    project_kind="legacy_extract",
                )

            projects = {project.id: project for project in service.list_projects()}
            connection = sqlite3.connect(root / "rusty.db")
            try:
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
                project_columns = {
                    row[1] for row in connection.execute("PRAGMA table_info(projects)")
                }
            finally:
                connection.close()

        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 24)
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)
        self.assertIn("project_kind", project_columns)
        self.assertEqual("rewrite", projects[rewrite_id].project_kind)
        self.assertEqual("branch", projects[branch_id].project_kind)

    def test_create_request_rejects_legacy_kinds(self) -> None:
        CreateProjectRequest(preview_token="token", project_kind="rewrite")
        CreateProjectRequest(preview_token="token", project_kind="branch")
        for invalid in ("extract", "summary", "legacy_extract"):
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                CreateProjectRequest(preview_token="token", project_kind=invalid)

    def test_legacy_extract_cannot_run_retired_project_pipelines(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. One\nOriginal.", encoding="utf-8")
            database = root / "rusty.db"
            service = ProjectService(database)
            project_id = service.create_project(
                service.preview_book(source), root, project_kind="rewrite"
            )
            connection = sqlite3.connect(database)
            connection.execute(
                "UPDATE projects SET project_kind = 'legacy_extract' WHERE id = ?",
                (project_id,),
            )
            connection.commit()
            connection.close()

            from backend.api import create_app

            os.environ["RUSTY_API_TOKEN"] = "test-token"
            client = TestClient(create_app(database))
            headers = {"X-Rusty-Token": "test-token"}
            run = client.post(
                f"/api/projects/{project_id}/pipeline/run", headers=headers
            )
            analyze = client.post(
                f"/api/projects/{project_id}/pipeline/summarize", headers=headers
            )

        self.assertEqual(409, run.status_code)
        self.assertEqual("legacy_extract_read_only", run.json()["error"])
        self.assertEqual(409, analyze.status_code)
        self.assertEqual("legacy_extract_read_only", analyze.json()["error"])

    def test_v23_migration_maps_projects_without_losing_content_or_analysis(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = Path(directory) / "legacy.db"
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO schema_migrations(version) VALUES (23);

                CREATE TABLE projects (
                    id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'draft',
                    current_stage TEXT NOT NULL DEFAULT 'import',
                    source_format TEXT,
                    source_path TEXT,
                    workspace_path TEXT,
                    total_chapters INTEGER NOT NULL DEFAULT 0,
                    total_words INTEGER NOT NULL DEFAULT 0,
                    completed_chapters INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                );
                INSERT INTO projects(id, name) VALUES (1, 'rewrite-old');
                INSERT INTO projects(id, name) VALUES (2, 'extract-old');

                CREATE TABLE project_settings (
                    project_id INTEGER PRIMARY KEY,
                    processing_mode TEXT NOT NULL DEFAULT 'manual'
                );
                INSERT INTO project_settings(project_id, processing_mode)
                VALUES (1, 'rewrite'), (2, 'extract');

                CREATE TABLE chapters (
                    id INTEGER PRIMARY KEY,
                    project_id INTEGER NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    original_text TEXT NOT NULL,
                    rewritten_text TEXT,
                    source_start_line INTEGER,
                    source_end_line INTEGER,
                    word_count INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'imported',
                    needs_rewrite INTEGER,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (project_id, chapter_index)
                );
                INSERT INTO chapters(id, project_id, chapter_index, title, original_text)
                VALUES
                    (10, 1, 1, 'rewrite chapter', 'rewrite source'),
                    (20, 2, 1, 'extract chapter', 'extract source');

                CREATE TABLE chapter_summaries (
                    chapter_id INTEGER PRIMARY KEY,
                    plot_summary TEXT NOT NULL DEFAULT ''
                );
                INSERT INTO chapter_summaries(chapter_id, plot_summary)
                VALUES (20, 'legacy analysis');
                """
            )

            try:
                initialize_database(connection)

                kinds = {
                    row["id"]: row["project_kind"]
                    for row in connection.execute(
                        "SELECT id, project_kind FROM projects ORDER BY id"
                    )
                }
                modes = {
                    row["project_id"]: row["processing_mode"]
                    for row in connection.execute(
                        "SELECT project_id, processing_mode FROM project_settings ORDER BY project_id"
                    )
                }
                source_rows = [
                    tuple(row)
                    for row in connection.execute(
                        "SELECT id, project_id, original_text FROM chapters ORDER BY id"
                    )
                ]
                analysis = connection.execute(
                    "SELECT plot_summary FROM chapter_summaries WHERE chapter_id = 20"
                ).fetchone()[0]
                version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
            finally:
                connection.close()

        self.assertEqual({1: "rewrite", 2: "legacy_extract"}, kinds)
        self.assertEqual({1: "rewrite", 2: "extract"}, modes)
        self.assertEqual(
            [(10, 1, "rewrite source"), (20, 2, "extract source")],
            source_rows,
        )
        self.assertEqual("legacy analysis", analysis)
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)


if __name__ == "__main__":
    unittest.main()
