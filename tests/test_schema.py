from __future__ import annotations

import sqlite3
import sys
import unittest
from unittest import mock
import json
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import CURRENT_SCHEMA_VERSION, connect, initialize_database
from rusty.db.schema import (
    _migrate_to_v14,
    _migrate_to_v15,
    _migrate_to_v17,
    _migrate_to_v18,
    _migrate_to_v19,
    _migrate_to_v20,
    _migrate_to_v21,
    _migrate_to_v37,
)
from rusty.services.project_service import ProjectService


class SchemaTests(unittest.TestCase):
    def test_v14_database_migrates_to_v15_with_immutable_source_snapshot(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE library_documents (id INTEGER PRIMARY KEY);
            CREATE TABLE project_documents (
                project_id INTEGER PRIMARY KEY,
                document_id INTEGER
            );
            CREATE TABLE chapters (
                id INTEGER PRIMARY KEY,
                project_id INTEGER NOT NULL,
                chapter_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                original_text TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO projects (id, name) VALUES (1, 'legacy');
            INSERT INTO chapters (id, project_id, chapter_index, title, original_text)
            VALUES (10, 1, 1, 'chapter', 'immutable legacy source');
            """
        )

        _migrate_to_v15(connection)
        _migrate_to_v15(connection)

        source = connection.execute(
            "SELECT original_text, source_version FROM chapter_source_versions WHERE chapter_id = 10"
        ).fetchone()
        scene_tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        self.assertEqual("immutable legacy source", source["original_text"])
        self.assertEqual(1, source["source_version"])
        self.assertIn("scenes", scene_tables)
        self.assertIn("scene_fact_ledgers", scene_tables)
        self.assertIn("prompt_compilations", scene_tables)
        self.assertIn("rewrite_plans", scene_tables)
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute("UPDATE chapters SET original_text = 'changed' WHERE id = 10")

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
        self.assertIn("analysis_prompt_templates", table_names)
        self.assertIn("chapter_style_analyses", table_names)
        self.assertIn("project_style_syntheses", table_names)
        self.assertIn("style_templates", table_names)
        self.assertIn("project_style_bindings", table_names)
        self.assertIn("outline_templates", table_names)
        self.assertIn("character_cards", table_names)
        self.assertIn("material_tags", table_names)
        self.assertIn("material_tag_links", table_names)
        self.assertIn("character_tags", table_names)
        self.assertIn("character_tag_links", table_names)
        self.assertIn("character_categories", table_names)
        self.assertIn("character_category_links", table_names)
        self.assertIn("character_extraction_settings", table_names)
        self.assertIn("document_tags", table_names)
        self.assertIn("document_tag_links", table_names)
        self.assertIn("material_categories", table_names)
        self.assertIn("material_category_links", table_names)
        self.assertIn("project_material_filters", table_names)
        self.assertIn("project_material_filter_tags", table_names)
        self.assertIn("material_ai_settings", table_names)
        self.assertIn("document_categories", table_names)
        self.assertIn("document_category_links", table_names)
        self.assertIn("library_document_drafts", table_names)
        self.assertIn("library_document_volumes", table_names)
        self.assertIn("project_outline_bindings", table_names)
        self.assertIn("project_character_bindings", table_names)
        self.assertIn("chapter_stage_status", table_names)
        self.assertIn("generation_attempts", table_names)
        self.assertIn("exports", table_names)
        self.assertIn("export_chapter_plan", table_names)

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

    def test_v35_plot_runs_migrate_to_v37_state_and_progress_without_loss(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE projects(id INTEGER PRIMARY KEY);
            CREATE TABLE story_branches(id INTEGER PRIMARY KEY);
            CREATE TABLE plot_generation_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                branch_id INTEGER,
                operation_type TEXT NOT NULL DEFAULT 'plot_generation',
                generation_mode TEXT NOT NULL,
                output_topology TEXT NOT NULL,
                start_anchor_json TEXT NOT NULL,
                return_anchor_json TEXT,
                start_state_json TEXT NOT NULL DEFAULT '{}',
                required_return_state_json TEXT NOT NULL DEFAULT '{}',
                target_skeleton_json TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                seams_json TEXT NOT NULL DEFAULT '[]',
                issues_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL,
                stage TEXT NOT NULL DEFAULT 'start',
                user_direction TEXT NOT NULL DEFAULT '',
                selected_character_ids_json TEXT NOT NULL DEFAULT '[]',
                selected_material_ids_json TEXT NOT NULL DEFAULT '[]',
                style_profile_id INTEGER,
                scene_plan_json TEXT NOT NULL DEFAULT '{}',
                fact_ledger_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                range_operation TEXT NOT NULL DEFAULT 'insert_between',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO projects(id) VALUES (1);
            INSERT INTO plot_generation_runs(
                id, project_id, generation_mode, output_topology,
                start_anchor_json, target_skeleton_json, status, stage,
                user_direction, fact_ledger_json
            ) VALUES (
                7, 1, 'fork', 'branch', '{"anchor_type":"chapter_end"}',
                '{"event_nodes":[{"id":"legacy"}]}', 'blocked',
                'consistency_check', 'legacy direction', '{"legacy_fact":true}'
            );
            """
        )
        _migrate_to_v37(connection)
        row = connection.execute(
            "SELECT * FROM plot_generation_runs WHERE id = 7"
        ).fetchone()
        self.assertEqual("repair_required", row["status"])
        self.assertEqual("legacy direction", row["user_direction"])
        self.assertEqual('{"legacy_fact":true}', row["fact_ledger_json"])
        self.assertEqual(0, row["next_scene_cursor"])
        self.assertEqual(0, row["generation_attempt"])

    def test_v37_rewrite_projection_backfills_v38_version_and_v39_head_without_loss(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "legacy-rewrite.txt"
            database = root / "legacy.db"
            source.write_text("1. One\nimmutable original", encoding="utf-8")
            with mock.patch("rusty.db.schema.CURRENT_SCHEMA_VERSION", 37):
                projects = ProjectService(database)
                project_id = projects.create_project(
                    projects.preview_book(source), root, project_kind="rewrite"
                )
            chapter = projects.list_chapters(project_id)[0]
            connection = connect(database)
            try:
                connection.execute(
                    "UPDATE chapters SET rewritten_text = 'legacy current text', status = 'rewritten' WHERE id = ?",
                    (chapter.id,),
                )
                scene_id = connection.execute(
                    """
                    INSERT INTO scenes(
                        project_id, chapter_id, scene_index, title,
                        original_start_offset, original_end_offset, original_text
                    ) VALUES (?, ?, 1, 'Legacy scene', 0, 18, 'immutable original')
                    """,
                    (project_id, chapter.id),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO scene_fact_ledgers(scene_id, ledger_version, facts_json)
                    VALUES (?, 1, '{"required_start_state":{"location":"before"},"location":"after"}')
                    """,
                    (scene_id,),
                )
                connection.execute(
                    """
                    INSERT INTO chapter_rewrites(
                        chapter_id, rewritten_text, rewrite_source,
                        prompt_snapshot_json, anchor_snapshot_json,
                        rewrite_mode, anchor_text, expanded_text
                    ) VALUES (?, 'legacy current text', 'ai', '{}', '{}',
                              'full_rewrite', '', 'legacy current text')
                    """,
                    (chapter.id,),
                )
                connection.execute(
                    """
                    INSERT INTO prose_rewrite_runs(
                        project_id, chapter_id, source_skeleton_json,
                        preservation_policy_json, target_skeleton_json,
                        rewrite_plan_json, rewritten_text, status
                    ) VALUES (?, ?, '{"event_nodes":[]}', '{}',
                              '{"event_nodes":[]}', '{"legacy":true}',
                              'legacy prose draft', 'completed')
                    """,
                    (project_id, chapter.id),
                )
                connection.execute(
                    """
                    INSERT INTO canon_change_runs(
                        project_id, old_fact_json, new_fact_json,
                        effective_order, fact_ledger_json, status
                    ) VALUES (?, '{"old":true}', '{"new":true}', 1,
                              '{"legacy_fact":true}', 'scanned')
                    """,
                    (project_id,),
                )
                initialize_database(connection)
                version = connection.execute(
                    "SELECT * FROM chapter_rewrite_versions WHERE chapter_id = ?",
                    (chapter.id,),
                ).fetchone()
                head = connection.execute(
                    "SELECT current_version_id, current_version FROM chapter_rewrites WHERE chapter_id = ?",
                    (chapter.id,),
                ).fetchone()
                original = connection.execute(
                    "SELECT original_text, rewritten_text FROM chapters WHERE id = ?",
                    (chapter.id,),
                ).fetchone()
                prose_run = connection.execute(
                    "SELECT status, rewritten_text, rewrite_plan_json FROM prose_rewrite_runs"
                ).fetchone()
                canon_run = connection.execute(
                    "SELECT status, old_fact_json, fact_ledger_json FROM canon_change_runs"
                ).fetchone()
            finally:
                connection.close()
            self.assertEqual("migration", version["source_operation"])
            self.assertEqual("original", version["source_base_kind"])
            self.assertEqual("legacy current text", version["rewritten_text"])
            self.assertEqual(
                {"location": "before"}, json.loads(version["facts_before_json"])
            )
            self.assertEqual("after", json.loads(version["facts_after_json"])["location"])
            self.assertEqual("consistent", version["fact_chain_status"])
            self.assertEqual(version["id"], head["current_version_id"])
            self.assertEqual(1, head["current_version"])
            self.assertEqual("immutable original", original["original_text"])
            self.assertEqual("legacy current text", original["rewritten_text"])
            self.assertEqual("completed", prose_run["status"])
            self.assertEqual("legacy prose draft", prose_run["rewritten_text"])
            self.assertIn("legacy", prose_run["rewrite_plan_json"])
            self.assertEqual("reviewing", canon_run["status"])
            self.assertIn("old", canon_run["old_fact_json"])
            self.assertIn("legacy_fact", canon_run["fact_ledger_json"])

    def test_v39_database_upgrades_to_v40_without_changing_rewrite_head_or_text(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "v39.txt"
            database = root / "v39.db"
            source.write_text("1. One\nimmutable original", encoding="utf-8")
            with mock.patch("rusty.db.schema.CURRENT_SCHEMA_VERSION", 39):
                projects = ProjectService(database)
                project_id = projects.create_project(
                    projects.preview_book(source), root, project_kind="rewrite"
                )
            chapter = projects.list_chapters(project_id)[0]
            connection = connect(database)
            try:
                version_id = connection.execute(
                    """
                    INSERT INTO chapter_rewrite_versions(
                        project_id, chapter_id, version, source_kind,
                        source_operation, source_base_kind, source_hash,
                        rewritten_text, content_hash, facts_before_json,
                        facts_after_json
                    ) VALUES (?, ?, 1, 'ai', 'manual', 'original',
                              'source-hash', 'v39 rewrite', 'content-hash',
                              '{"location":"before"}', '{"location":"after"}')
                    """,
                    (project_id, chapter.id),
                ).lastrowid
                connection.execute(
                    """
                    INSERT INTO chapter_rewrites(
                        chapter_id, rewritten_text, rewrite_source,
                        prompt_snapshot_json, anchor_snapshot_json,
                        rewrite_mode, anchor_text, expanded_text,
                        current_version_id, current_version
                    ) VALUES (?, 'v39 rewrite', 'manual', '{}', '{}',
                              'full_rewrite', '', 'v39 rewrite', ?, 1)
                    """,
                    (chapter.id, version_id),
                )
                connection.execute(
                    "UPDATE chapters SET rewritten_text = 'v39 rewrite' WHERE id = ?",
                    (chapter.id,),
                )
                initialize_database(connection)
                migrated = connection.execute(
                    "SELECT * FROM chapter_rewrite_versions WHERE id = ?",
                    (version_id,),
                ).fetchone()
                head = connection.execute(
                    "SELECT current_version_id FROM chapter_rewrites WHERE chapter_id = ?",
                    (chapter.id,),
                ).fetchone()
                original = connection.execute(
                    "SELECT original_text, rewritten_text FROM chapters WHERE id = ?",
                    (chapter.id,),
                ).fetchone()
                schema_version = connection.execute(
                    "SELECT MAX(version) FROM schema_migrations"
                ).fetchone()[0]
            finally:
                connection.close()
            self.assertEqual(CURRENT_SCHEMA_VERSION, schema_version)
            self.assertEqual(version_id, head["current_version_id"])
            self.assertEqual("v39 rewrite", migrated["rewritten_text"])
            self.assertEqual({"location": "before"}, json.loads(migrated["facts_before_json"]))
            self.assertEqual({"location": "after"}, json.loads(migrated["facts_after_json"]))
            self.assertEqual("immutable original", original["original_text"])
            self.assertEqual("v39 rewrite", original["rewritten_text"])

    def test_v20_to_v21_character_extraction_settings_migration_is_idempotent(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        initialize_database(connection)
        connection.execute("DROP TABLE character_extraction_settings")

        _migrate_to_v21(connection)
        _migrate_to_v21(connection)
        connection.execute(
            """
            INSERT INTO character_extraction_settings (
                id, detail_level, max_candidates, generate_tags
            ) VALUES (1, 'detailed', 4, 0)
            """
        )
        row = connection.execute(
            "SELECT detail_level, max_candidates, generate_tags FROM character_extraction_settings"
        ).fetchone()

        self.assertEqual("detailed", row["detail_level"])
        self.assertEqual(4, row["max_candidates"])
        self.assertEqual(0, row["generate_tags"])

    def test_v19_to_v20_character_category_migration_repairs_project_bindings_idempotently(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        initialize_database(connection)
        connection.execute("DELETE FROM schema_migrations WHERE version = 20")
        connection.execute("DROP TABLE character_category_links")
        connection.execute("DROP TABLE character_categories")
        connection.execute("INSERT INTO projects (id, name) VALUES (900, 'Legacy project')")
        connection.execute(
            """
            INSERT INTO character_cards (id, name, scope, project_id)
            VALUES (901, 'Legacy character', 'project', 900)
            """
        )

        _migrate_to_v20(connection)
        _migrate_to_v20(connection)

        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
        binding = connection.execute(
            """
            SELECT project_id, character_card_id, is_active
            FROM project_character_bindings
            WHERE project_id = 900 AND character_card_id = 901
            """
        ).fetchone()
        self.assertIn("character_categories", tables)
        self.assertIn("character_category_links", tables)
        self.assertEqual((900, 901, 1), tuple(binding))

    def test_initialize_database_upgrades_v18_chapters_before_creating_volume_index(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations(version) VALUES (18);

            CREATE TABLE library_document_chapters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                document_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL,
                chapter_index INTEGER NOT NULL,
                title TEXT NOT NULL,
                start_line INTEGER,
                end_line INTEGER,
                start_offset INTEGER,
                end_offset INTEGER,
                word_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE (revision_id, chapter_index)
            );
            """
        )

        initialize_database(connection)

        columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(library_document_chapters)")
        }
        indexes = {
            row["name"]
            for row in connection.execute("PRAGMA index_list(library_document_chapters)")
        }
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        self.assertIn("volume_id", columns)
        self.assertIn("idx_library_chapters_volume_order", indexes)
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)

    def test_v17_to_v18_draft_migration_is_idempotent_and_scopes_null_chapter(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE library_documents (id INTEGER PRIMARY KEY);
            CREATE TABLE library_document_revisions (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL
            );
            CREATE TABLE library_document_chapters (
                id INTEGER PRIMARY KEY,
                document_id INTEGER NOT NULL,
                revision_id INTEGER NOT NULL
            );
            INSERT INTO library_documents (id) VALUES (1);
            INSERT INTO library_document_revisions (id, document_id) VALUES (10, 1);
            INSERT INTO library_document_chapters (id, document_id, revision_id) VALUES (20, 1, 10);
            """
        )

        _migrate_to_v18(connection)
        _migrate_to_v18(connection)
        connection.execute(
            """
            INSERT INTO library_document_drafts
                (document_id, chapter_id, base_revision_id, title, text)
            VALUES (1, NULL, 10, '全文', '草稿')
            """
        )
        with self.assertRaises(sqlite3.IntegrityError):
            connection.execute(
                """
                INSERT INTO library_document_drafts
                    (document_id, chapter_id, base_revision_id, title, text)
                VALUES (1, NULL, 10, '重复', '草稿')
                """
            )
        connection.execute(
            """
            INSERT INTO library_document_drafts
                (document_id, chapter_id, base_revision_id, title, text)
            VALUES (1, 20, 10, '章节', '草稿')
            """
        )
        self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM library_document_drafts").fetchone()[0])

    def test_v18_to_v19_promotes_only_unmistakable_volume_chapters_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            text = "卷首语\n第七卷 雨夜\n第787章 雨夜\n正文。"
            source = Path(directory) / "legacy.txt"
            source.write_text(text, encoding="utf-8")
            volume_start = text.index("第七卷")
            chapter_start = text.index("第787章")
            connection = sqlite3.connect(":memory:")
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.executescript(
                """
                CREATE TABLE library_documents (
                    id INTEGER PRIMARY KEY,
                    current_revision_id INTEGER,
                    chapter_count INTEGER NOT NULL,
                    deleted_at TEXT
                );
                CREATE TABLE library_document_revisions (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    storage_path TEXT NOT NULL
                );
                CREATE TABLE library_document_chapters (
                    id INTEGER PRIMARY KEY,
                    document_id INTEGER NOT NULL,
                    revision_id INTEGER NOT NULL,
                    chapter_index INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    start_offset INTEGER,
                    end_offset INTEGER,
                    UNIQUE(revision_id, chapter_index)
                );
                """
            )
            connection.execute(
                "INSERT INTO library_documents VALUES (1, 10, 3, NULL)"
            )
            connection.execute(
                "INSERT INTO library_document_revisions VALUES (10, 1, ?)",
                (str(source),),
            )
            connection.executemany(
                """
                INSERT INTO library_document_chapters
                    (id, document_id, revision_id, chapter_index, title, start_offset, end_offset)
                VALUES (?, 1, 10, ?, ?, ?, ?)
                """,
                [
                    (20, 1, "卷首语", 0, volume_start),
                    (21, 2, "第七卷 雨夜", volume_start, chapter_start),
                    (22, 3, "第787章 雨夜", chapter_start, len(text)),
                ],
            )

            _migrate_to_v19(connection)
            _migrate_to_v19(connection)

            volumes = connection.execute(
                "SELECT * FROM library_document_volumes"
            ).fetchall()
            chapters = connection.execute(
                "SELECT title, volume_id FROM library_document_chapters ORDER BY chapter_index"
            ).fetchall()
            self.assertEqual(["第七卷 雨夜"], [row["title"] for row in volumes])
            self.assertEqual(["卷首语", "第787章 雨夜"], [row["title"] for row in chapters])
            self.assertIsNone(chapters[0]["volume_id"])
            self.assertEqual(volumes[0]["id"], chapters[1]["volume_id"])
            self.assertEqual(2, connection.execute("SELECT chapter_count FROM library_documents").fetchone()[0])

    def test_v16_document_tags_migrate_to_v17_categories_idempotently(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE library_documents (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                deleted_at TEXT
            );
            CREATE TABLE document_tags (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            CREATE TABLE document_tag_links (
                document_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, tag_id)
            );
            INSERT INTO library_documents(id, title) VALUES (1, 'legacy');
            INSERT INTO document_tags(id, name, normalized_name, sort_order)
            VALUES (10, '参考', '参考', 3), (11, '工程', '工程', 0);
            INSERT INTO document_tag_links(document_id, tag_id) VALUES (1, 10), (1, 11);
            """
        )

        _migrate_to_v17(connection)
        _migrate_to_v17(connection)

        category = connection.execute(
            "SELECT id, name, sort_order FROM document_categories WHERE deleted_at IS NULL"
        ).fetchone()
        self.assertEqual(("参考", 3), (category["name"], category["sort_order"]))
        self.assertEqual(
            1,
            connection.execute(
                "SELECT COUNT(*) FROM document_category_links WHERE document_id = 1 AND category_id = ?",
                (category["id"],),
            ).fetchone()[0],
        )
        self.assertEqual(
            1,
            connection.execute(
                "SELECT COUNT(*) FROM document_tags WHERE id = 10 AND deleted_at IS NULL"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            connection.execute(
                "SELECT COUNT(*) FROM document_tags WHERE id = 11 AND deleted_at IS NULL"
            ).fetchone()[0],
        )
        self.assertEqual(
            0,
            connection.execute(
                "SELECT COUNT(*) FROM document_tag_links WHERE tag_id = 11"
            ).fetchone()[0],
        )
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM document_categories").fetchone()[0])

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
        self.assertIn("confirmed_at", columns)
        self.assertIn("rewrite_mode", columns)
        self.assertIn("anchor_text", columns)
        self.assertIn("expanded_text", columns)
        self.assertEqual(("unknown", "{}", "{}"), row)
        self.assertEqual(CURRENT_SCHEMA_VERSION, version)

    def test_connect_enables_foreign_keys(self) -> None:
        connection = connect(":memory:")
        try:
            foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone()[0]
        finally:
            connection.close()

        self.assertEqual(1, foreign_keys_enabled)

    def test_v13_material_character_and_document_data_migrate_to_v14_idempotently(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE projects (id INTEGER PRIMARY KEY);
            CREATE TABLE materials (
                id INTEGER PRIMARY KEY,
                material_type TEXT NOT NULL CHECK (material_type IN ('outline', 'plot_skeleton', 'snippet')),
                scope TEXT NOT NULL DEFAULT 'public',
                project_id INTEGER,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                detail_level TEXT NOT NULL DEFAULT 'standard',
                content_json TEXT NOT NULL DEFAULT '{}',
                source_metadata_json TEXT NOT NULL DEFAULT '{}',
                import_metadata_json TEXT NOT NULL DEFAULT '{}',
                source_material_id INTEGER,
                source_version INTEGER,
                legacy_outline_id INTEGER UNIQUE,
                timeline_start_chapter INTEGER,
                timeline_end_chapter INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            INSERT INTO materials (id, material_type, name) VALUES
                (1, 'outline', '旧大纲'),
                (2, 'snippet', '旧片段');
            CREATE TABLE material_categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                material_type TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            CREATE TABLE material_category_links (
                material_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (material_id, category_id),
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
            );
            INSERT INTO material_categories (id, name, material_type) VALUES
                (1, '冒险', 'outline'),
                (2, '冒险', 'snippet');
            INSERT INTO material_category_links (material_id, category_id) VALUES (1, 1), (2, 2);

            CREATE TABLE character_cards (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                aliases_json TEXT NOT NULL DEFAULT '[]',
                description TEXT NOT NULL DEFAULT '',
                priority INTEGER NOT NULL DEFAULT 50,
                is_main INTEGER NOT NULL DEFAULT 0,
                relationship_notes TEXT NOT NULL DEFAULT '',
                personality TEXT NOT NULL DEFAULT '',
                speech_style TEXT NOT NULL DEFAULT '',
                action_constraints TEXT NOT NULL DEFAULT '',
                anti_ooc_rules TEXT NOT NULL DEFAULT '',
                profile_json TEXT NOT NULL DEFAULT '{}',
                source_metadata_json TEXT NOT NULL DEFAULT '{}',
                import_metadata_json TEXT NOT NULL DEFAULT '{}',
                scope TEXT NOT NULL DEFAULT 'public',
                project_id INTEGER,
                source_character_card_id INTEGER,
                source_version INTEGER,
                version INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            INSERT INTO character_cards (
                id, name, description, relationship_notes, personality, profile_json
            ) VALUES (
                1, '林玄', '旧设定', '师徒', '沉稳', '{"身份":"外门弟子","年龄":"十八岁","境界":"筑基"}'
            );

            CREATE TABLE library_documents (id INTEGER PRIMARY KEY, deleted_at TEXT);
            INSERT INTO library_documents (id) VALUES (1);
            CREATE TABLE document_categories (
                id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                parent_id INTEGER,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            CREATE TABLE document_category_links (
                document_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (document_id, category_id)
            );
            INSERT INTO document_categories (id, name) VALUES (1, '参考');
            INSERT INTO document_category_links (document_id, category_id) VALUES (1, 1);
            CREATE TABLE library_document_chapters (id INTEGER PRIMARY KEY);
            """
        )

        _migrate_to_v14(connection)
        _migrate_to_v14(connection)

        materials = connection.execute(
            "SELECT material_type, import_metadata_json FROM materials ORDER BY id"
        ).fetchall()
        character = connection.execute(
            "SELECT identity, age, setting_text, custom_fields_json FROM character_cards WHERE id = 1"
        ).fetchone()
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }

        self.assertEqual(["plot_skeleton", "scene_reference"], [row["material_type"] for row in materials])
        self.assertIn('"legacy_material_type":"outline"', materials[0]["import_metadata_json"])
        self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM material_tags").fetchone()[0])
        self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM material_tag_links").fetchone()[0])
        self.assertEqual("外门弟子", character["identity"])
        self.assertEqual("十八岁", character["age"])
        self.assertEqual("旧设定", character["setting_text"])
        self.assertEqual(3, len(json.loads(character["custom_fields_json"])))
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM document_tags").fetchone()[0])
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM document_tag_links").fetchone()[0])
        self.assertNotIn("material_categories", tables)
        self.assertNotIn("document_categories", tables)

    def test_initialize_database_removes_general_scene_detection_column(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.executescript(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            INSERT INTO schema_migrations(version) VALUES (7);
            CREATE TABLE prompt_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                scene_detection_rules TEXT NOT NULL DEFAULT ''
            );
            CREATE TABLE projects (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'draft',
                current_stage TEXT NOT NULL DEFAULT 'import'
            );
            CREATE TABLE project_custom_prompts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                prompt_key TEXT NOT NULL,
                prompt_text TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (project_id, prompt_key)
            );
            INSERT INTO prompt_templates(name, scene_detection_rules) VALUES ('Legacy', 'Legacy rule');
            INSERT INTO projects(id, name) VALUES (1, 'Legacy project');
            INSERT INTO project_custom_prompts(project_id, prompt_key, prompt_text)
            VALUES (1, 'scene_detection_rules', 'Legacy override');
            """
        )

        initialize_database(connection)

        columns = {row[1] for row in connection.execute("PRAGMA table_info(prompt_templates)")}
        self.assertNotIn("scene_detection_rules", columns)
        self.assertEqual("Legacy", connection.execute("SELECT name FROM prompt_templates").fetchone()[0])
        self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM project_custom_prompts").fetchone()[0])


if __name__ == "__main__":
    unittest.main()
