from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .connection import session


CURRENT_SCHEMA_VERSION = 64

PROMPT_SLOTS = (
    ("global_system", "只使用请求中提供的事实和当前有效正文；遵守用户明确要求与输出契约，不虚构未提供事实，不跨任务擅自扩展。"),
    ("chapter_summary", "阅读当前章节原文，生成剧情总结、关键事件、主要人物及人物设定；不要提出修改方案或创作正文。"),
    ("plot_adjust", "根据用户要求生成用于对照的旧大纲，以及包含必要细节的新大纲。未要求改变的内容必须保留。"),
    ("expansion", "阅读整本小说原文并根据用户要求，设计应插入当前章之后的新章节大纲；不要修改当前章节。"),
    ("plot_rewrite", "阅读当前章节原文并根据用户要求生成全新的重写大纲；只返回大纲，不要生成正文。"),
    ("writing", "根据程序提供的原文、新大纲、用户要求和作者风格生成完整小说正文；不要输出分析、说明或 JSON。"),
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
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

CREATE TABLE IF NOT EXISTS book_metadata (
    project_id INTEGER PRIMARY KEY,
    title TEXT,
    author TEXT,
    language TEXT,
    publisher TEXT,
    description TEXT,
    source_encoding TEXT,
    source_identifier TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ai_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    display_name TEXT NOT NULL,
    provider TEXT NOT NULL DEFAULT 'openai_compatible',
    base_url TEXT NOT NULL,
    model_name TEXT NOT NULL,
    api_key_secret_ref TEXT,
    temperature REAL NOT NULL DEFAULT 0.7,
    max_tokens INTEGER,
    timeout_seconds INTEGER NOT NULL DEFAULT 60,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER PRIMARY KEY,
    model_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS story_volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    volume_index INTEGER NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, volume_index),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    original_text TEXT NOT NULL,
    rewritten_text TEXT,
    source_start_line INTEGER,
    source_end_line INTEGER,
    source_start_offset INTEGER,
    source_end_offset INTEGER,
    volume_id INTEGER,
    word_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'imported',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_id, chapter_index),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (volume_id) REFERENCES story_volumes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_source_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    source_version INTEGER NOT NULL DEFAULT 1,
    original_start_offset INTEGER NOT NULL DEFAULT 0,
    original_end_offset INTEGER NOT NULL DEFAULT 0,
    original_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chapter_id, source_version),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_rewrite_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    parent_version_id INTEGER,
    source_kind TEXT NOT NULL CHECK(source_kind IN ('ai','manual')),
    source_base_kind TEXT NOT NULL CHECK(source_base_kind IN ('original','rewrite_version')),
    source_base_version_id INTEGER,
    source_hash TEXT NOT NULL,
    rewritten_text TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chapter_id, version),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL,
    FOREIGN KEY (source_base_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_rewrites (
    chapter_id INTEGER PRIMARY KEY,
    current_version_id INTEGER NOT NULL,
    rewritten_text TEXT NOT NULL,
    actual_word_count INTEGER NOT NULL DEFAULT 0,
    expansion_ratio REAL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (current_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detail_level TEXT NOT NULL DEFAULT 'standard' CHECK(detail_level IN ('brief','standard','detailed')),
    raw_text TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    sort_order INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS material_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS material_category_links (
    material_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(material_id, category_id),
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS material_ai_settings (
    task_type TEXT PRIMARY KEY CHECK(task_type='author_style_extraction'),
    model_id INTEGER,
    detail_level TEXT NOT NULL DEFAULT 'standard' CHECK(detail_level IN ('brief','standard','detailed')),
    extraction_rules TEXT NOT NULL DEFAULT '',
    base_instruction TEXT NOT NULL DEFAULT '',
    dimensions_json TEXT NOT NULL DEFAULT '[]',
    extra_requirements TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS prompt_slots (
    slot_key TEXT PRIMARY KEY CHECK(slot_key IN (
        'global_system','chapter_summary','plot_adjust','expansion','plot_rewrite','writing'
    )),
    content TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS chapter_workflow_state (
    chapter_id INTEGER PRIMARY KEY,
    current_stage TEXT NOT NULL DEFAULT 'not_started' CHECK(current_stage IN (
        'not_started','summary','direction','special_analysis','style','writing','review','confirmed'
    )),
    source_base_kind TEXT CHECK(source_base_kind IN ('original','rewrite_version')),
    source_base_version_id INTEGER,
    source_hash TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (source_base_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_workflow_summaries (
    chapter_id INTEGER PRIMARY KEY,
    plot_summary TEXT NOT NULL DEFAULT '',
    main_characters TEXT NOT NULL DEFAULT '',
    key_events TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_creative_intents (
    chapter_id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL CHECK(strategy IN ('plot_adjust','expansion','plot_rewrite')),
    user_instruction TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_special_analyses (
    chapter_id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL CHECK(strategy IN ('plot_adjust','expansion','plot_rewrite')),
    source_outline TEXT NOT NULL DEFAULT '',
    target_outline TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_style_contexts (
    chapter_id INTEGER PRIMARY KEY,
    strategy TEXT NOT NULL CHECK(strategy IN ('plot_adjust','expansion','plot_rewrite')),
    style_mode TEXT NOT NULL CHECK(style_mode IN ('source_auto','selected_author_style')),
    source_scope TEXT NOT NULL CHECK(source_scope IN ('document','chapter')),
    author_style_material_id INTEGER,
    author_style_material_version INTEGER,
    style_snapshot_json TEXT NOT NULL DEFAULT '{}',
    extraction_settings_snapshot_json TEXT NOT NULL DEFAULT '{}',
    generated_guidance TEXT NOT NULL DEFAULT '',
    source_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (author_style_material_id) REFERENCES materials(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_writings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL UNIQUE,
    strategy TEXT NOT NULL CHECK(strategy IN ('plot_adjust','expansion','plot_rewrite')),
    writing_plan_json TEXT NOT NULL DEFAULT '[]',
    result_text TEXT NOT NULL DEFAULT '',
    created_chapter_id INTEGER,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','reviewed','confirmed')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (created_chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS library_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    author TEXT,
    description TEXT,
    source_filename TEXT NOT NULL,
    source_format TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    source_size_bytes INTEGER NOT NULL DEFAULT 0,
    stored_size_bytes INTEGER NOT NULL DEFAULT 0,
    chapter_count INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0,
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'imported',
    favorite INTEGER NOT NULL DEFAULT 0,
    current_revision_id INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS document_categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS document_category_links (
    document_id INTEGER NOT NULL,
    category_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY(document_id, category_id),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES document_categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS library_document_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    revision_number INTEGER NOT NULL,
    revision_type TEXT NOT NULL,
    storage_path TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    template_id INTEGER,
    parent_revision_id INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(document_id, revision_number),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (parent_revision_id) REFERENCES library_document_revisions(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS library_document_volumes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    revision_id INTEGER NOT NULL,
    volume_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_offset INTEGER NOT NULL,
    end_offset INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(revision_id, volume_index),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS library_document_chapters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    revision_id INTEGER NOT NULL,
    chapter_index INTEGER NOT NULL,
    title TEXT NOT NULL,
    start_line INTEGER,
    end_line INTEGER,
    start_offset INTEGER,
    end_offset INTEGER,
    volume_id INTEGER,
    word_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE(revision_id, chapter_index),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE,
    FOREIGN KEY (volume_id) REFERENCES library_document_volumes(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS library_document_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    chapter_id INTEGER,
    base_revision_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    text TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES library_document_chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (base_revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_library_settings (
    id INTEGER PRIMARY KEY CHECK(id=1),
    storage_path TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS project_documents (
    project_id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_split_proposals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    source_revision_id INTEGER NOT NULL,
    proposal_kind TEXT NOT NULL DEFAULT 'ai' CHECK(proposal_kind='ai'),
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','applied','cancelled')),
    boundaries_json TEXT NOT NULL DEFAULT '[]',
    unmatched_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    applied_revision_id INTEGER,
    applied_at TEXT,
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (source_revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE,
    FOREIGN KEY (applied_revision_id) REFERENCES library_document_revisions(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_projects_updated ON projects(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_chapters_project_order ON chapters(project_id, chapter_index);
CREATE INDEX IF NOT EXISTS idx_chapter_versions_order ON chapter_rewrite_versions(chapter_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_chapter_workflow_stage ON chapter_workflow_state(current_stage, updated_at);
CREATE INDEX IF NOT EXISTS idx_materials_updated ON materials(updated_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_material_categories_name_active
    ON material_categories(normalized_name) WHERE deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_document_categories_name_active
    ON document_categories(normalized_name) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_library_documents_created ON library_documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_documents_hash ON library_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_library_revisions_order ON library_document_revisions(document_id, revision_number DESC);
CREATE INDEX IF NOT EXISTS idx_library_chapters_order ON library_document_chapters(revision_id, chapter_index);
CREATE INDEX IF NOT EXISTS idx_library_volumes_order ON library_document_volumes(revision_id, volume_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_library_draft_full
    ON library_document_drafts(document_id) WHERE chapter_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_library_draft_chapter
    ON library_document_drafts(document_id, chapter_id) WHERE chapter_id IS NOT NULL;
"""

CANONICAL_TABLES = (
    "projects", "book_metadata", "ai_models",
    "project_settings", "story_volumes", "chapters", "chapter_source_versions",
    "chapter_rewrite_versions", "chapter_rewrites", "materials", "material_categories",
    "material_category_links", "material_ai_settings", "prompt_slots", "chapter_workflow_state",
    "chapter_workflow_summaries", "chapter_creative_intents", "chapter_special_analyses",
    "chapter_style_contexts", "chapter_writings", "library_documents", "document_categories",
    "document_category_links", "library_document_revisions", "library_document_volumes",
    "library_document_chapters", "library_document_drafts", "document_library_settings",
    "project_documents", "document_split_proposals",
)


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the canonical schema or migrate the sole supported v63 baseline."""
    connection.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    row = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()
    version = int(row[0]) if row and row[0] is not None else 0
    if version == 0:
        connection.executescript(SCHEMA_SQL)
        _seed_defaults(connection)
    elif version == 63:
        _migrate_v63_to_v64(connection)
    elif version == CURRENT_SCHEMA_VERSION:
        connection.executescript(SCHEMA_SQL)
        _seed_defaults(connection)
    else:
        raise RuntimeError(
            f"Unsupported Rusty schema version {version}; only a fresh database or v63 can be opened."
        )
    connection.execute("DELETE FROM schema_migrations")
    connection.execute("INSERT INTO schema_migrations(version) VALUES(?)", (CURRENT_SCHEMA_VERSION,))


def _migrate_v63_to_v64(connection: sqlite3.Connection) -> None:
    connection.commit()
    connection.execute("PRAGMA foreign_keys=OFF")
    try:
        old_tables = {
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            ).fetchall()
        }
        for table in CANONICAL_TABLES:
            if table in old_tables:
                connection.execute(f'ALTER TABLE "{table}" RENAME TO "__v63_{table}"')
        connection.executescript(SCHEMA_SQL)

        for table in CANONICAL_TABLES:
            backup = f"__v63_{table}"
            if not _table_exists(connection, backup):
                continue
            if table == "chapter_rewrite_versions":
                connection.execute(
                    """INSERT OR IGNORE INTO chapter_rewrite_versions(
                           id,project_id,chapter_id,version,parent_version_id,source_kind,
                           source_base_kind,source_base_version_id,source_hash,rewritten_text,
                           content_hash,created_at
                       ) SELECT id,project_id,chapter_id,version,parent_version_id,
                                CASE WHEN source_kind='manual' THEN 'manual' ELSE 'ai' END,
                                source_base_kind,source_base_version_id,source_hash,rewritten_text,
                                content_hash,created_at
                         FROM __v63_chapter_rewrite_versions
                         ORDER BY chapter_id,version"""
                )
                continue
            new_columns = _columns(connection, table)
            old_columns = _columns(connection, backup)
            shared = [column for column in new_columns if column in old_columns]
            if not shared:
                continue
            quoted = ",".join(f'"{column}"' for column in shared)
            where = " WHERE material_type='author_style'" if table == "materials" else ""
            connection.execute(
                f'INSERT OR IGNORE INTO "{table}"({quoted}) SELECT {quoted} FROM "{backup}"{where}'
            )

        old_settings = "__v63_material_ai_settings"
        if _table_exists(connection, old_settings) and "system_prompt" in _columns(connection, old_settings):
            row = connection.execute(
                f'SELECT system_prompt FROM "{old_settings}" WHERE task_type=?',
                ("author_style_extraction",),
            ).fetchone()
            if row is not None:
                connection.execute(
                    "UPDATE material_ai_settings SET extraction_rules=? WHERE task_type='author_style_extraction'",
                    (str(row[0] or ""),),
                )

        _canonicalize_author_materials(connection)
        _seed_defaults(connection)
        if "prompt_definitions" in old_tables:
            _copy_prompt_slots(connection)

        keep = {"schema_migrations", *CANONICAL_TABLES}
        for row in connection.execute(
            "SELECT type,name FROM sqlite_master WHERE type IN ('view','trigger') AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            connection.execute(f'DROP {str(row[0]).upper()} IF EXISTS "{str(row[1])}"')
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall():
            name = str(row[0])
            if name not in keep:
                connection.execute(f'DROP TABLE IF EXISTS "{name}"')
        connection.executescript(SCHEMA_SQL)
        connection.commit()
    finally:
        connection.execute("PRAGMA foreign_keys=ON")


def _seed_defaults(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO prompt_slots(slot_key,content) VALUES(?,?)", PROMPT_SLOTS
    )
    connection.execute(
        """INSERT OR IGNORE INTO material_ai_settings(
               task_type,detail_level,extraction_rules,base_instruction,dimensions_json,extra_requirements
           ) VALUES(
               'author_style_extraction','standard',
               '只提取文本中可观察的作者风格，不总结剧情，不评价优劣，不生成仿写正文。',
               '分析完整样本文本并返回整体风格与各配置维度。证据不足的维度保持简洁。',
               '[{"id":"language","name":"语言与句式","requirement":"分析词汇、句长、节奏和修辞"},{"id":"narration","name":"叙事方式","requirement":"分析视角、距离、节奏和信息组织"},{"id":"dialogue","name":"对白与人物呈现","requirement":"分析对白、动作和人物塑造"}]',
               ''
           )"""
    )
    connection.execute(
        "INSERT OR IGNORE INTO chapter_workflow_state(chapter_id) SELECT id FROM chapters"
    )


def _copy_prompt_slots(connection: sqlite3.Connection) -> None:
    selectors = {
        "global_system": "kind='master'",
        "chapter_summary": "task_key='chapter_summary'",
        "plot_adjust": "workflow_key='plot_adjust' AND task_key='special_analysis'",
        "expansion": "workflow_key='expansion' AND task_key='special_analysis'",
        "plot_rewrite": "workflow_key='plot_rewrite' AND task_key='special_analysis'",
        "writing": "task_key='writing'",
    }
    for slot_key, selector in selectors.items():
        row = connection.execute(
            f"""SELECT content FROM prompt_definitions
                WHERE deleted_at IS NULL AND {selector}
                ORDER BY is_default DESC,updated_at DESC,id DESC LIMIT 1"""
        ).fetchone()
        if row is not None and str(row[0] or "").strip():
            connection.execute(
                "UPDATE prompt_slots SET content=?,updated_at=CURRENT_TIMESTAMP WHERE slot_key=?",
                (str(row[0]), slot_key),
            )


def _canonicalize_author_materials(connection: sqlite3.Connection) -> None:
    rows = connection.execute(
        "SELECT id,content_json,source_metadata_json FROM materials"
    ).fetchall()
    for row in rows:
        content = _json_object(row["content_json"])
        metadata = _json_object(row["source_metadata_json"])
        source_file_name = str(
            metadata.get("source_file_name")
            or metadata.get("file_name")
            or metadata.get("source_filename")
            or ""
        ).strip()
        canonical_metadata = {
            key: value
            for key, value in {
                "source_type": metadata.get("source_type") or ("file" if source_file_name else None),
                "source_file_name": source_file_name or None,
                "source_path": metadata.get("source_path"),
                "source_format": metadata.get("source_format"),
                "book_title": metadata.get("book_title"),
            }.items()
            if value not in {None, ""}
        }
        raw_dimensions = content.get("dimensions") if isinstance(content.get("dimensions"), list) else []
        dimensions: list[dict[str, object]] = []
        for index, item in enumerate(raw_dimensions, 1):
            if not isinstance(item, dict):
                continue
            dimension_id = str(item.get("id") or f"dimension-{index}").strip()
            if not dimension_id:
                continue
            dimensions.append({
                "id": dimension_id,
                "name": str(item.get("name") or "未命名维度").strip(),
                "analysis": str(item.get("analysis") or "").strip(),
                "features": _json_strings(item.get("features")),
                "examples": _json_strings(item.get("examples")),
            })
        work = str(content.get("work") or "").strip()
        if not work and source_file_name:
            work = Path(source_file_name).stem
        canonical_content = {
            "schema_version": 1,
            "work": work,
            "overall_style": str(content.get("overall_style") or content.get("summary") or "").strip(),
            "dimensions": dimensions,
        }
        connection.execute(
            "UPDATE materials SET content_json=?,source_metadata_json=? WHERE id=?",
            (
                json.dumps(canonical_content, ensure_ascii=False),
                json.dumps(canonical_metadata, ensure_ascii=False),
                int(row["id"]),
            ),
        )


def _json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _json_strings(value: object) -> list[str]:
    return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []


def _table_exists(connection: sqlite3.Connection, name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _columns(connection: sqlite3.Connection, table: str) -> list[str]:
    return [str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")').fetchall()]


def initialize_database_file(database_path: str | Path) -> None:
    with session(database_path) as connection:
        initialize_database(connection)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a Rusty SQLite database.")
    parser.add_argument("database", type=Path)
    args = parser.parse_args(argv)
    initialize_database_file(args.database)
    print(f"Initialized database: {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
