from __future__ import annotations

import sqlite3
import unittest

import support  # Adds src/ to sys.path for direct test execution.

from rusty.db.schema import CURRENT_SCHEMA_VERSION, initialize_database


def legacy_v65_database() -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'imported', current_stage TEXT NOT NULL DEFAULT 'split', source_format TEXT, source_path TEXT, workspace_path TEXT, total_chapters INTEGER NOT NULL DEFAULT 0, total_words INTEGER NOT NULL DEFAULT 0, completed_chapters INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
        CREATE TABLE chapters(id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, chapter_index INTEGER NOT NULL, title TEXT NOT NULL, original_text TEXT NOT NULL, rewritten_text TEXT, source_start_line INTEGER, source_end_line INTEGER, source_start_offset INTEGER, source_end_offset INTEGER, volume_id INTEGER, word_count INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'imported', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE chapter_writings(id INTEGER PRIMARY KEY, chapter_id INTEGER NOT NULL, strategy TEXT NOT NULL, result_text TEXT NOT NULL DEFAULT '', created_chapter_id INTEGER, source_hash TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'draft', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE library_documents(id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, description TEXT, source_filename TEXT NOT NULL, source_format TEXT NOT NULL, storage_path TEXT NOT NULL, content_hash TEXT NOT NULL, source_size_bytes INTEGER NOT NULL DEFAULT 0, stored_size_bytes INTEGER NOT NULL DEFAULT 0, chapter_count INTEGER NOT NULL DEFAULT 0, word_count INTEGER NOT NULL DEFAULT 0, source_metadata_json TEXT NOT NULL DEFAULT '{}', cover_palette TEXT NOT NULL DEFAULT 'slate', status TEXT NOT NULL DEFAULT 'imported', favorite INTEGER NOT NULL DEFAULT 0, current_revision_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
        CREATE TABLE document_categories(id INTEGER PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
        CREATE TABLE document_category_links(document_id INTEGER NOT NULL, category_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(document_id, category_id));
        CREATE TABLE library_document_revisions(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, revision_number INTEGER NOT NULL, revision_type TEXT NOT NULL, storage_path TEXT NOT NULL, content_hash TEXT NOT NULL, parent_revision_id INTEGER, metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE library_document_drafts(id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, chapter_id INTEGER, base_revision_id INTEGER NOT NULL, title TEXT NOT NULL, text TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE project_documents(project_id INTEGER PRIMARY KEY, document_id INTEGER NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        """
    )
    connection.execute("INSERT INTO schema_migrations(version) VALUES(65)")
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'旧工程')")
    connection.executemany(
        "INSERT INTO chapters(id,project_id,chapter_index,title,original_text,word_count,source_start_offset,source_end_offset) VALUES(?,?,?,?,?,?,?,?)",
        [
            (1, 1, 1, "原文章节", "原文", 2, 0, 2),
            (2, 1, 2, "新增章节", "新增", 2, None, None),
        ],
    )
    connection.execute(
        "INSERT INTO chapter_writings(id,chapter_id,strategy,result_text,created_chapter_id,source_hash) VALUES(1,1,'expansion','新增',2,'hash')"
    )
    connection.executemany(
        "INSERT INTO library_documents(id,title,source_filename,source_format,storage_path,content_hash) VALUES(?,?,?,?,?,?)",
        [
            (1, "纯镜像", "mirror.txt", "txt", "mirror.txt", "mirror"),
            (2, "用户文档", "user.txt", "txt", "user.txt", "user"),
        ],
    )
    connection.executemany(
        "INSERT INTO library_document_revisions(id,document_id,revision_number,revision_type,storage_path,content_hash) VALUES(?,?,?,?,?,?)",
        [
            (1, 1, 1, "import", "mirror.txt", "mirror"),
            (2, 2, 1, "import", "user.txt", "user"),
            (3, 2, 2, "manual_edit", "user-2.txt", "user-2"),
        ],
    )
    connection.executemany("INSERT INTO project_documents(project_id,document_id) VALUES(?,?)", [(1, 1), (2, 2)])
    connection.commit()
    return connection


class SchemaV66Tests(unittest.TestCase):
    def test_v65_migration_soft_deletes_only_pure_project_mirrors(self) -> None:
        connection = legacy_v65_database()
        initialize_database(connection)

        self.assertEqual(66, CURRENT_SCHEMA_VERSION)
        self.assertEqual(66, connection.execute("SELECT version FROM schema_migrations").fetchone()[0])
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("project_documents", tables)
        self.assertIsNotNone(connection.execute("SELECT deleted_at FROM library_documents WHERE id=1").fetchone()[0])
        self.assertIsNone(connection.execute("SELECT deleted_at FROM library_documents WHERE id=2").fetchone()[0])
        self.assertEqual("manual_edit", connection.execute("SELECT revision_type FROM library_document_revisions WHERE id=3").fetchone()[0])
        self.assertEqual("expansion", connection.execute("SELECT origin_kind FROM chapters WHERE id=2").fetchone()[0])
        self.assertEqual("source", connection.execute("SELECT origin_kind FROM chapters WHERE id=1").fetchone()[0])

        initialize_database(connection)
        self.assertNotIn("project_documents", {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")})


if __name__ == "__main__":
    unittest.main()
