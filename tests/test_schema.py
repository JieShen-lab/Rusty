from __future__ import annotations

import json
import sqlite3
import unittest

import support  # Adds src/ to sys.path for direct test execution.

from rusty.db.schema import AUTHOR_STYLE_DIMENSIONS, PROMPT_SLOTS, initialize_database


EXPECTED_TABLES = {
    "projects",
    "book_metadata",
    "ai_models",
    "project_settings",
    "story_volumes",
    "chapters",
    "chapter_source_versions",
    "chapter_rewrite_versions",
    "chapter_rewrites",
    "materials",
    "material_ai_settings",
    "prompt_slots",
    "chapter_workflow_state",
    "chapter_workflow_summaries",
    "chapter_creative_intents",
    "chapter_special_analyses",
    "chapter_style_contexts",
    "chapter_writings",
    "library_documents",
    "document_categories",
    "document_category_links",
    "library_document_revisions",
    "library_document_volumes",
    "library_document_chapters",
    "library_document_drafts",
    "document_library_settings",
    "document_split_proposals",
}


class SchemaTests(unittest.TestCase):
    def test_fresh_database_has_current_schema_and_defaults(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row

        initialize_database(connection)
        initialize_database(connection)

        tables = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        self.assertEqual(EXPECTED_TABLES, tables)
        self.assertNotIn("schema_migrations", tables)
        self.assertNotIn("project_documents", tables)
        self.assertEqual(
            dict(PROMPT_SLOTS),
            dict(connection.execute("SELECT slot_key,content FROM prompt_slots")),
        )
        dimensions = json.loads(
            connection.execute(
                "SELECT dimensions_json FROM material_ai_settings WHERE task_type='author_style_extraction'"
            ).fetchone()[0]
        )
        self.assertEqual(list(AUTHOR_STYLE_DIMENSIONS), dimensions)


if __name__ == "__main__":
    unittest.main()
