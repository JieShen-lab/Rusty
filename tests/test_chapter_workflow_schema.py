from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import connect, initialize_database
from rusty.db.schema import (
    CURRENT_SCHEMA_VERSION,
    DEFAULT_SEED_SQL,
    MIGRATIONS,
    SCHEMA_SQL,
)
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


PREVIOUS_SCHEMA_VERSION = 51


def initialize_as_v51(connection: sqlite3.Connection) -> None:
    """Build the real pre-v52 schema without invoking the current initializer."""
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, PREVIOUS_SCHEMA_VERSION + 1):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
        connection.execute(
            "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
            (version,),
        )
    connection.commit()


def seed_existing_v51_data(connection: sqlite3.Connection) -> None:
    connection.execute(
        "INSERT INTO projects(id, name, project_kind) VALUES (1, 'existing project', 'rewrite')"
    )
    connection.execute(
        """
        INSERT INTO chapters(id, project_id, chapter_index, title, original_text, word_count)
        VALUES (10, 1, 1, 'existing chapter', 'existing text', 13)
        """
    )
    connection.execute(
        """
        INSERT INTO scenes(
            id, project_id, chapter_id, scene_index, title,
            original_start_offset, original_end_offset, original_text
        ) VALUES (100, 1, 10, 1, 'existing scene', 0, 13, 'existing text')
        """
    )
    connection.execute(
        "INSERT INTO character_cards(id, name) VALUES (20, 'existing character')"
    )
    connection.execute(
        """
        INSERT INTO materials(id, material_type, name, raw_text)
        VALUES (30, 'plot_skeleton', 'existing material', 'existing material text')
        """
    )
    connection.commit()


class ChapterWorkflowSchemaRepairTests(unittest.TestCase):
    def test_fresh_database_supports_real_workflow_round_trip(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            database = root / "rusty.db"
            source = root / "book.txt"
            source.write_text("第一章 起点\n已有章节正文。", encoding="utf-8")

            with connect(database) as connection:
                initialize_database(connection)
                self.assertEqual(
                    CURRENT_SCHEMA_VERSION,
                    connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
                )
                self.assertIsNotNone(
                    connection.execute(
                        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'chapter_workflow_state'"
                    ).fetchone()
                )

            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]
            scene = SceneService(database).split_chapter(chapter.id)[0]
            workflow = CreativeWorkflowService(database)

            initial = workflow.get_chapter_state(chapter.id)
            saved = workflow.update_chapter_state(
                chapter.id,
                active_scene_id=scene.id,
                current_stage="preanalysis",
            )
            restored = CreativeWorkflowService(database).get_chapter_state(chapter.id)

        self.assertEqual("not_started", initial["current_stage"])
        self.assertEqual("preanalysis", saved["current_stage"])
        self.assertEqual(scene.id, restored["active_scene_id"])
        self.assertEqual("preanalysis", restored["current_stage"])

    def test_real_v51_database_upgrades_without_losing_existing_data(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            database = Path(directory) / "rusty.db"
            with connect(database) as connection:
                initialize_as_v51(connection)
                seed_existing_v51_data(connection)

            with connect(database) as connection:
                initialize_database(connection)
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                counts = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in ("projects", "chapters", "scenes", "character_cards", "materials")
                }

            workflow = CreativeWorkflowService(database)
            initial = workflow.get_chapter_state(10)
            workflow.update_chapter_state(10, active_scene_id=100, current_stage="direction")
            restored = CreativeWorkflowService(database).get_chapter_state(10)

        self.assertEqual(CURRENT_SCHEMA_VERSION, version)
        self.assertEqual({table: 1 for table in counts}, counts)
        self.assertEqual("not_started", initial["current_stage"])
        self.assertEqual("direction", restored["current_stage"])
        self.assertEqual(100, restored["active_scene_id"])

    def test_v51_database_marked_current_but_missing_table_is_repaired(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            database = Path(directory) / "rusty.db"
            with connect(database) as connection:
                initialize_as_v51(connection)
                seed_existing_v51_data(connection)
                connection.execute("DROP TABLE chapter_workflow_state")

            with connect(database) as connection:
                initialize_database(connection)
                version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
                state = connection.execute(
                    "SELECT chapter_id, active_scene_id, current_stage FROM chapter_workflow_state"
                ).fetchone()
                preserved = connection.execute(
                    "SELECT p.name, c.title, cc.name, m.name FROM projects p, chapters c, character_cards cc, materials m"
                ).fetchone()

        self.assertEqual(CURRENT_SCHEMA_VERSION, version)
        self.assertEqual((10, None, "not_started"), tuple(state))
        self.assertEqual(
            ("existing project", "existing chapter", "existing character", "existing material"),
            tuple(preserved),
        )

    def test_initialize_is_idempotent_and_preserves_workflow_data(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        initialize_database(connection)
        connection.execute("INSERT INTO projects(id, name) VALUES (1, 'kept')")
        connection.execute(
            "INSERT INTO chapters(id, project_id, chapter_index, title, original_text) VALUES (10, 1, 1, 'kept', 'kept')"
        )
        connection.execute(
            "INSERT INTO chapter_workflow_state(chapter_id) VALUES (10)"
        )
        connection.execute(
            "UPDATE chapter_workflow_state SET current_stage = 'writing' WHERE chapter_id = 10"
        )

        initialize_database(connection)
        initialize_database(connection)

        self.assertEqual(
            CURRENT_SCHEMA_VERSION,
            connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
        )
        self.assertEqual(
            1,
            connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version = 52").fetchone()[0],
        )
        self.assertEqual(
            "writing",
            connection.execute(
                "SELECT current_stage FROM chapter_workflow_state WHERE chapter_id = 10"
            ).fetchone()[0],
        )
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM projects WHERE id = 1").fetchone()[0])

    def test_invalid_repair_does_not_advance_schema_version(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        initialize_as_v51(connection)
        connection.execute("DROP TABLE chapter_workflow_state")
        connection.execute("CREATE TABLE chapter_workflow_state(id INTEGER PRIMARY KEY)")

        with self.assertRaisesRegex(RuntimeError, "incompatible column layout"):
            initialize_database(connection)

        self.assertIsNone(
            connection.execute("SELECT 1 FROM schema_migrations WHERE version = 52").fetchone()
        )
        self.assertEqual(
            PREVIOUS_SCHEMA_VERSION,
            connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0],
        )


if __name__ == "__main__":
    unittest.main()
