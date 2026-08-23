from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

import support  # Adds src/ to sys.path for direct test execution.

from rusty.db.schema import (
    AUTHOR_STYLE_DIMENSIONS,
    CURRENT_SCHEMA_VERSION,
    PROMPT_SLOTS,
    V64_PROMPT_SLOTS,
    initialize_database,
)


REMOVED_COLUMNS = {
    "materials": {"description", "detail_level", "sort_order", "version"},
    "chapter_style_contexts": {"source_scope", "author_style_material_version"},
    "chapter_writings": {"writing_plan_json"},
    "library_document_revisions": {"template_id"},
}


def columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')}


def legacy_database(version: int) -> sqlite3.Connection:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(
        """
        CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE projects(id INTEGER PRIMARY KEY, name TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'imported', current_stage TEXT NOT NULL DEFAULT 'split', source_format TEXT, source_path TEXT, workspace_path TEXT, total_chapters INTEGER NOT NULL DEFAULT 0, total_words INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
        CREATE TABLE prompt_slots(slot_key TEXT PRIMARY KEY, content TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE library_documents(id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT, description TEXT, source_filename TEXT NOT NULL, source_format TEXT NOT NULL, storage_path TEXT NOT NULL, content_hash TEXT NOT NULL, source_size_bytes INTEGER NOT NULL, stored_size_bytes INTEGER NOT NULL, chapter_count INTEGER NOT NULL DEFAULT 0, word_count INTEGER NOT NULL DEFAULT 0, source_metadata_json TEXT NOT NULL DEFAULT '{}', status TEXT NOT NULL DEFAULT 'imported', favorite INTEGER NOT NULL DEFAULT 0, current_revision_id INTEGER, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
        """
    )
    if version == 64:
        connection.executescript(
            """
            CREATE TABLE materials(id INTEGER PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', detail_level TEXT NOT NULL DEFAULT 'standard', raw_text TEXT NOT NULL DEFAULT '', content_json TEXT NOT NULL DEFAULT '{}', source_metadata_json TEXT NOT NULL DEFAULT '{}', sort_order INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
            CREATE TABLE material_ai_settings(task_type TEXT PRIMARY KEY, model_id INTEGER, detail_level TEXT NOT NULL, extraction_rules TEXT NOT NULL, base_instruction TEXT NOT NULL, dimensions_json TEXT NOT NULL, extra_requirements TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            """
        )
        connection.executemany("INSERT INTO prompt_slots(slot_key,content) VALUES(?,?)", V64_PROMPT_SLOTS)
        connection.execute(
            """INSERT INTO material_ai_settings VALUES('author_style_extraction',NULL,'standard',?,?,?,'',CURRENT_TIMESTAMP)""",
            (
                "只提取文本中可观察的作者风格，不总结剧情，不评价优劣，不生成仿写正文。",
                "分析完整样本文本并返回整体风格与各配置维度。证据不足的维度保持简洁。",
                json.dumps([
                    {"id": "language", "name": "语言与句式", "requirement": "分析词汇、句长、节奏和修辞"},
                    {"id": "narration", "name": "叙事方式", "requirement": "分析视角、距离、节奏和信息组织"},
                    {"id": "dialogue", "name": "对白与人物呈现", "requirement": "分析对白、动作和人物塑造"},
                ], ensure_ascii=False),
            ),
        )
    else:
        connection.executescript(
            """
            CREATE TABLE materials(id INTEGER PRIMARY KEY, material_type TEXT NOT NULL, name TEXT NOT NULL, raw_text TEXT NOT NULL DEFAULT '', content_json TEXT NOT NULL DEFAULT '{}', source_metadata_json TEXT NOT NULL DEFAULT '{}', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
            CREATE TABLE material_ai_settings(task_type TEXT PRIMARY KEY, model_id INTEGER, detail_level TEXT NOT NULL, system_prompt TEXT NOT NULL, base_instruction TEXT NOT NULL, dimensions_json TEXT NOT NULL, extra_requirements TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY, kind TEXT NOT NULL, workflow_key TEXT, task_key TEXT, content TEXT NOT NULL, is_default INTEGER NOT NULL DEFAULT 1, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, deleted_at TEXT);
            """
        )
        for index, (slot, content) in enumerate(PROMPT_SLOTS, 1):
            kind = "master" if slot == "global_system" else "workflow_task"
            workflow = slot if slot in {"plot_adjust", "expansion", "plot_rewrite"} else None
            task = "special_analysis" if workflow else slot
            connection.execute(
                "INSERT INTO prompt_definitions(id,kind,workflow_key,task_key,content) VALUES(?,?,?,?,?)",
                (index, kind, workflow, task, content),
            )
        connection.execute(
            """INSERT INTO material_ai_settings VALUES('author_style_extraction',NULL,'standard','legacy rules','base',?,'',CURRENT_TIMESTAMP)""",
            (json.dumps(AUTHOR_STYLE_DIMENSIONS, ensure_ascii=False),),
        )
    connection.execute("INSERT INTO schema_migrations(version) VALUES(?)", (version,))
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'保留工程')")
    connection.execute("INSERT INTO materials(id," + ("material_type," if version == 63 else "") + "name,raw_text,content_json) VALUES(1," + ("'author_style'," if version == 63 else "") + "'保留作者','样本文本','{}')")
    connection.execute("""INSERT INTO library_documents(id,title,source_filename,source_format,storage_path,content_hash,source_size_bytes,stored_size_bytes) VALUES(1,'保留文档','book.txt','txt','book.txt','hash',1,1)""")
    connection.commit()
    return connection


class SchemaV66Tests(unittest.TestCase):
    def test_fresh_v66_is_canonical_and_has_complete_defaults(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        initialize_database(connection)
        self.assertEqual(66, CURRENT_SCHEMA_VERSION)
        self.assertEqual(66, connection.execute("SELECT version FROM schema_migrations").fetchone()[0])
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertFalse({"material_categories", "material_category_links"} & tables)
        for table, removed in REMOVED_COLUMNS.items():
            self.assertFalse(removed & columns(connection, table))
        self.assertIn("cover_palette", columns(connection, "library_documents"))
        self.assertIn("origin_kind", columns(connection, "chapters"))
        self.assertNotIn("project_documents", tables)
        self.assertEqual(dict(PROMPT_SLOTS), dict(connection.execute("SELECT slot_key,content FROM prompt_slots")))
        dimensions = json.loads(connection.execute("SELECT dimensions_json FROM material_ai_settings").fetchone()[0])
        self.assertEqual(12, len(dimensions))

    def test_v64_upgrade_restores_only_unmodified_defaults_and_keeps_data(self) -> None:
        connection = legacy_database(64)
        initialize_database(connection)
        self.assertEqual("保留工程", connection.execute("SELECT name FROM projects WHERE id=1").fetchone()[0])
        self.assertEqual("保留作者", connection.execute("SELECT name FROM materials WHERE id=1").fetchone()[0])
        document = connection.execute("SELECT title,cover_palette FROM library_documents WHERE id=1").fetchone()
        self.assertEqual(("保留文档", "indigo"), tuple(document))
        self.assertEqual(dict(PROMPT_SLOTS), dict(connection.execute("SELECT slot_key,content FROM prompt_slots")))
        dimensions = json.loads(connection.execute("SELECT dimensions_json FROM material_ai_settings").fetchone()[0])
        self.assertEqual(12, len(dimensions))

    def test_v63_can_upgrade_directly_without_losing_prompts_or_settings(self) -> None:
        connection = legacy_database(63)
        initialize_database(connection)
        self.assertEqual(66, connection.execute("SELECT version FROM schema_migrations").fetchone()[0])
        self.assertEqual("保留工程", connection.execute("SELECT name FROM projects").fetchone()[0])
        self.assertEqual("legacy rules", connection.execute("SELECT extraction_rules FROM material_ai_settings").fetchone()[0])
        self.assertEqual(dict(PROMPT_SLOTS), dict(connection.execute("SELECT slot_key,content FROM prompt_slots")))


if __name__ == "__main__":
    unittest.main()
