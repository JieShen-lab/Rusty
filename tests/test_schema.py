from __future__ import annotations

import sqlite3
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import CURRENT_SCHEMA_VERSION, connect, initialize_database


class SchemaTests(unittest.TestCase):
    def test_initialize_database_creates_expected_tables(self) -> None:
        connection = sqlite3.connect(":memory:")
        initialize_database(connection)

        table_names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

        self.assertIn("projects", table_names)
        self.assertIn("chapters", table_names)
        self.assertIn("ai_models", table_names)
        self.assertIn("prompt_templates", table_names)
        self.assertIn("style_templates", table_names)
        self.assertIn("project_style_bindings", table_names)
        self.assertIn("chapter_stage_status", table_names)
        self.assertIn("exports", table_names)

    def test_initialize_database_records_schema_version_and_seed_rule(self) -> None:
        connection = sqlite3.connect(":memory:")
        initialize_database(connection)

        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        split_rule_count = connection.execute(
            "SELECT COUNT(*) FROM txt_split_rules WHERE is_default = 1"
        ).fetchone()[0]

        self.assertEqual(CURRENT_SCHEMA_VERSION, version)
        self.assertEqual(1, split_rule_count)

    def test_initialize_database_upgrades_v1_rewrite_table(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations(version) VALUES (1);

            CREATE TABLE chapter_rewrites (
                chapter_id INTEGER PRIMARY KEY,
                rewritten_text TEXT NOT NULL,
                target_word_count INTEGER,
                actual_word_count INTEGER NOT NULL DEFAULT 0,
                expansion_ratio REAL,
                model_id INTEGER,
                prompt_template_id INTEGER,
                token_usage_json TEXT NOT NULL DEFAULT '{}',
                elapsed_ms INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO chapter_rewrites (
                chapter_id,
                rewritten_text,
                actual_word_count
            ) VALUES (1, 'old rewrite', 11);
            """
        )

        initialize_database(connection)
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(chapter_rewrites)")
        }
        row = connection.execute(
            """
            SELECT rewrite_source, prompt_snapshot_json, anchor_snapshot_json
            FROM chapter_rewrites
            WHERE chapter_id = 1
            """
        ).fetchone()
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]

        self.assertIn("rewrite_source", columns)
        self.assertIn("prompt_snapshot_json", columns)
        self.assertIn("anchor_snapshot_json", columns)
        self.assertEqual(("unknown", "{}", "{}"), row)
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)

    def test_connect_enables_foreign_keys(self) -> None:
        connection = connect(":memory:")
        try:
            foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(1, foreign_keys_enabled)


if __name__ == "__main__":
    unittest.main()
