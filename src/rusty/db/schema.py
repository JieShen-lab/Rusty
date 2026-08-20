from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import sqlite3
from pathlib import Path

from .connection import session

CURRENT_SCHEMA_VERSION = 57

logger = logging.getLogger(__name__)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    project_kind TEXT NOT NULL DEFAULT 'rewrite'
        CHECK (project_kind IN ('rewrite', 'branch', 'legacy_extract')),
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

CREATE TABLE IF NOT EXISTS import_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    source_path TEXT NOT NULL,
    source_format TEXT NOT NULL,
    source_size_bytes INTEGER,
    content_hash TEXT,
    parser_name TEXT,
    parser_version TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS txt_split_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'simple',
    line_prefix TEXT,
    number_pattern TEXT,
    title_suffix TEXT,
    custom_regex TEXT,
    extra_rules_json TEXT NOT NULL DEFAULT '{}',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
    word_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'imported',
    needs_rewrite INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, chapter_index),
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

CREATE TABLE IF NOT EXISTS prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    global_rules TEXT NOT NULL DEFAULT '',
    summary_rules TEXT NOT NULL DEFAULT '',
    rewrite_rules TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    story_anchor_json TEXT NOT NULL DEFAULT '{}',
    characters_json TEXT NOT NULL DEFAULT '[]',
    package_metadata_json TEXT NOT NULL DEFAULT '{}',
    source_project_id INTEGER,
    version INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS prompt_scene_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    scene_key TEXT NOT NULL,
    display_name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detection_prompt TEXT NOT NULL DEFAULT '',
    sort_order INTEGER NOT NULL DEFAULT 0,
    UNIQUE (template_id, scene_key),
    FOREIGN KEY (template_id) REFERENCES prompt_templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS prompt_rewrite_rules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    template_id INTEGER NOT NULL,
    scene_key TEXT NOT NULL,
    rewrite_prompt TEXT NOT NULL DEFAULT '',
    UNIQUE (template_id, scene_key),
    FOREIGN KEY (template_id) REFERENCES prompt_templates(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS analysis_prompt_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    analysis_dimensions TEXT NOT NULL DEFAULT '',
    evidence_rules TEXT NOT NULL DEFAULT '',
    synthesis_rules TEXT NOT NULL DEFAULT '',
    output_requirements TEXT NOT NULL DEFAULT '',
    version INTEGER NOT NULL DEFAULT 1,
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS project_settings (
    project_id INTEGER PRIMARY KEY,
    model_id INTEGER,
    prompt_template_id INTEGER,
    analysis_prompt_template_id INTEGER,
    txt_split_rule_id INTEGER,
    processing_mode TEXT NOT NULL DEFAULT 'manual',
    concurrency INTEGER NOT NULL DEFAULT 1,
    target_word_count INTEGER,
    min_expansion_ratio REAL,
    rewrite_mode TEXT NOT NULL DEFAULT 'anchor_expand' CHECK (rewrite_mode IN ('anchor_expand', 'full_rewrite')),
    max_attempts INTEGER NOT NULL DEFAULT 2,
    settings_json TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL,
    FOREIGN KEY (analysis_prompt_template_id) REFERENCES analysis_prompt_templates(id) ON DELETE SET NULL,
    FOREIGN KEY (txt_split_rule_id) REFERENCES txt_split_rules(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_custom_prompts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    prompt_key TEXT NOT NULL,
    prompt_text TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, prompt_key),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS style_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
    global_prompt TEXT NOT NULL DEFAULT '',
    rewrite_prompt TEXT NOT NULL DEFAULT '',
    style_profile_json TEXT NOT NULL DEFAULT '{}',
    generated_prompt TEXT NOT NULL DEFAULT '',
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    import_metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS project_style_bindings (
    project_id INTEGER PRIMARY KEY,
    style_template_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (style_template_id) REFERENCES style_templates(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS outline_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
    outline_json TEXT NOT NULL DEFAULT '{}',
    anchor_prompt TEXT NOT NULL DEFAULT '',
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    import_metadata_json TEXT NOT NULL DEFAULT '{}',
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_type TEXT NOT NULL CHECK (material_type = 'author_style'),
    scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
    project_id INTEGER,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
    raw_text TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    analysis_status TEXT NOT NULL DEFAULT 'analyzed'
        CHECK (analysis_status IN ('unanalyzed', 'analyzed')),
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
    deleted_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (source_material_id) REFERENCES materials(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS material_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    tag_group TEXT NOT NULL DEFAULT 'general'
        CHECK (tag_group IN ('general', 'applicable_scene')),
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_material_tags_normalized_active
    ON material_tags(normalized_name)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS material_tag_links (
    material_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (material_id, tag_id),
    FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_documents (
    project_id INTEGER PRIMARY KEY,
    document_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_materials_scope_project_timeline
    ON materials(scope, project_id, timeline_start_chapter, sort_order);
CREATE INDEX IF NOT EXISTS idx_materials_public_type
    ON materials(scope, material_type, updated_at);
CREATE TABLE IF NOT EXISTS project_outline_bindings (
    project_id INTEGER PRIMARY KEY,
    outline_template_id INTEGER NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (outline_template_id) REFERENCES outline_templates(id) ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS chapter_stage_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    started_at TEXT,
    finished_at TEXT,
    retry_count INTEGER NOT NULL DEFAULT 0,
    elapsed_ms INTEGER,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (chapter_id, stage),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS chapter_summaries (
    chapter_id INTEGER PRIMARY KEY,
    plot_summary TEXT NOT NULL DEFAULT '',
    characters_json TEXT NOT NULL DEFAULT '[]',
    key_events_json TEXT NOT NULL DEFAULT '[]',
    model_id INTEGER,
    prompt_template_id INTEGER,
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_style_analyses (
    chapter_id INTEGER PRIMARY KEY,
    analysis_json TEXT NOT NULL DEFAULT '{}',
    reviewed_json TEXT NOT NULL DEFAULT '{}',
    status TEXT NOT NULL DEFAULT 'pending_review',
    model_id INTEGER,
    analysis_prompt_template_id INTEGER,
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    elapsed_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (analysis_prompt_template_id) REFERENCES analysis_prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS project_style_syntheses (
    project_id INTEGER PRIMARY KEY,
    synthesis_json TEXT NOT NULL DEFAULT '{}',
    reviewed_json TEXT NOT NULL DEFAULT '{}',
    prompt_template_id INTEGER,
    model_id INTEGER,
    analysis_prompt_template_id INTEGER,
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    elapsed_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reviewed_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (analysis_prompt_template_id) REFERENCES analysis_prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_scene_analysis (
    chapter_id INTEGER PRIMARY KEY,
    needs_rewrite INTEGER NOT NULL DEFAULT 0,
    scene_labels_json TEXT NOT NULL DEFAULT '[]',
    reasoning TEXT NOT NULL DEFAULT '',
    context_markers_json TEXT NOT NULL DEFAULT '[]',
    model_id INTEGER,
    prompt_template_id INTEGER,
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_plot_expansions (
    chapter_id INTEGER PRIMARY KEY,
    enabled INTEGER NOT NULL DEFAULT 1,
    expanded_plot TEXT NOT NULL DEFAULT '',
    model_id INTEGER,
    prompt_template_id INTEGER,
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    elapsed_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_rewrites (
    chapter_id INTEGER PRIMARY KEY,
    rewritten_text TEXT NOT NULL,
    rewrite_source TEXT NOT NULL DEFAULT 'ai' CHECK (rewrite_source IN ('ai', 'manual', 'unknown')),
    target_word_count INTEGER,
    actual_word_count INTEGER NOT NULL DEFAULT 0,
    expansion_ratio REAL,
    model_id INTEGER,
    prompt_template_id INTEGER,
    prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
    anchor_snapshot_json TEXT NOT NULL DEFAULT '{}',
    rewrite_mode TEXT NOT NULL DEFAULT 'anchor_expand' CHECK (rewrite_mode IN ('anchor_expand', 'full_rewrite')),
    anchor_text TEXT NOT NULL DEFAULT '',
    expanded_text TEXT NOT NULL DEFAULT '',
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    elapsed_ms INTEGER,
    confirmed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS generation_attempts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    attempt_number INTEGER NOT NULL,
    request_json TEXT NOT NULL DEFAULT '{}',
    response_text TEXT NOT NULL DEFAULT '',
    parsed_json TEXT NOT NULL DEFAULT '{}',
    error_type TEXT,
    error_message TEXT,
    model_id INTEGER,
    prompt_template_id INTEGER,
    token_usage_json TEXT NOT NULL DEFAULT '{}',
    elapsed_ms INTEGER,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chapter_id, stage, attempt_number),
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
    FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
);

CREATE TABLE IF NOT EXISTS chapter_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chapter_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    error_type TEXT,
    message TEXT NOT NULL,
    traceback TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    stage TEXT NOT NULL,
    error_type TEXT,
    message TEXT NOT NULL,
    traceback TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    export_format TEXT NOT NULL,
    output_path TEXT NOT NULL,
    chapter_count INTEGER NOT NULL DEFAULT 0,
    word_count INTEGER NOT NULL DEFAULT 0,
    options_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS export_chapter_plan (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    project_id INTEGER NOT NULL,
    chapter_id INTEGER NOT NULL,
    export_order INTEGER NOT NULL,
    export_title TEXT,
    include_in_export INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (project_id, chapter_id),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
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
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT,
    current_revision_id INTEGER
);

CREATE TABLE IF NOT EXISTS document_tags (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    normalized_name TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_document_tags_normalized_active
    ON document_tags(normalized_name)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS document_tag_links (
    document_id INTEGER NOT NULL,
    tag_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (document_id, tag_id),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (tag_id) REFERENCES document_tags(id) ON DELETE CASCADE
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
    PRIMARY KEY (document_id, category_id),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES document_categories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS document_processing_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    settings_json TEXT NOT NULL DEFAULT '{}',
    is_default INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
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
    UNIQUE (document_id, revision_number),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (template_id) REFERENCES document_processing_templates(id) ON DELETE SET NULL,
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
    UNIQUE (revision_id, volume_index),
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
    UNIQUE (revision_id, chapter_index),
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
    id INTEGER PRIMARY KEY CHECK (id = 1),
    storage_path TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_projects_status ON projects(status);
CREATE INDEX IF NOT EXISTS idx_chapters_project_order ON chapters(project_id, chapter_index);
CREATE INDEX IF NOT EXISTS idx_export_plan_project_order ON export_chapter_plan(project_id, export_order);
CREATE INDEX IF NOT EXISTS idx_stage_status_stage_status ON chapter_stage_status(stage, status);
CREATE INDEX IF NOT EXISTS idx_chapter_errors_stage ON chapter_errors(stage, created_at);
CREATE INDEX IF NOT EXISTS idx_project_errors_stage ON project_errors(stage, created_at);
CREATE INDEX IF NOT EXISTS idx_generation_attempts_chapter_stage
    ON generation_attempts(chapter_id, stage, attempt_number);
CREATE INDEX IF NOT EXISTS idx_library_documents_created_at
    ON library_documents(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_library_documents_content_hash
    ON library_documents(content_hash);
CREATE INDEX IF NOT EXISTS idx_document_tags_order
    ON document_tags(sort_order, name);
CREATE INDEX IF NOT EXISTS idx_library_revisions_document_number
    ON library_document_revisions(document_id, revision_number DESC);
CREATE INDEX IF NOT EXISTS idx_library_chapters_revision_order
    ON library_document_chapters(revision_id, chapter_index);
CREATE INDEX IF NOT EXISTS idx_library_volumes_revision_order
    ON library_document_volumes(revision_id, volume_index);
CREATE UNIQUE INDEX IF NOT EXISTS idx_library_drafts_document_full
    ON library_document_drafts(document_id)
    WHERE chapter_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_library_drafts_document_chapter
    ON library_document_drafts(document_id, chapter_id)
    WHERE chapter_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_library_drafts_base_revision
    ON library_document_drafts(base_revision_id, updated_at DESC);
"""

DEFAULT_SEED_SQL = """
INSERT OR IGNORE INTO txt_split_rules (
    id,
    name,
    mode,
    custom_regex,
    is_default
) VALUES (
    1,
    'Chinese chapter headings',
    'custom_regex',
    '^(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.． ].*)$',
    1
);

INSERT OR IGNORE INTO document_processing_templates (
    id,
    name,
    settings_json,
    is_default
) VALUES (
    1,
    '标准中文小说排版',
    '{"chapter_pattern":"^\\\\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.． ].*)\\\\s*$","chapter_indent":0,"paragraph_indent":2,"blank_lines":1,"trim_whitespace":true}',
    1
);
"""


def _column_exists(connection: sqlite3.Connection, table_name: str, column_name: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    return any(row[1] == column_name for row in rows)


def _add_column_if_missing(connection: sqlite3.Connection, table_name: str, column_name: str, definition: str) -> None:
    if not _column_exists(connection, table_name, column_name):
        connection.execute(f"ALTER TABLE {table_name} ADD COLUMN {definition}")


def _migrate_to_v2(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "rewrite_source",
        "rewrite_source TEXT NOT NULL DEFAULT 'unknown' CHECK (rewrite_source IN ('ai', 'manual', 'unknown'))",
    )
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "prompt_snapshot_json",
        "prompt_snapshot_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "anchor_snapshot_json",
        "anchor_snapshot_json TEXT NOT NULL DEFAULT '{}'",
    )


def _migrate_to_v3(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS style_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            global_prompt TEXT NOT NULL DEFAULT '',
            rewrite_prompt TEXT NOT NULL DEFAULT '',
            style_profile_json TEXT NOT NULL DEFAULT '{}',
            generated_prompt TEXT NOT NULL DEFAULT '',
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            import_metadata_json TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS project_style_bindings (
            project_id INTEGER PRIMARY KEY,
            style_template_id INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (style_template_id) REFERENCES style_templates(id) ON DELETE RESTRICT
        );
        """
    )


def _migrate_to_v4(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS outline_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            outline_json TEXT NOT NULL DEFAULT '{}',
            anchor_prompt TEXT NOT NULL DEFAULT '',
            source_metadata_json TEXT NOT NULL DEFAULT '{}',
            import_metadata_json TEXT NOT NULL DEFAULT '{}',
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS character_cards (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS project_outline_bindings (
            project_id INTEGER PRIMARY KEY,
            outline_template_id INTEGER NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (outline_template_id) REFERENCES outline_templates(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS project_character_bindings (
            project_id INTEGER NOT NULL,
            character_card_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (project_id, character_card_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (character_card_id) REFERENCES character_cards(id) ON DELETE RESTRICT
        );
        """
    )


def _migrate_to_v5(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS export_chapter_plan (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            export_order INTEGER NOT NULL,
            export_title TEXT,
            include_in_export INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (project_id, chapter_id),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_export_plan_project_order
            ON export_chapter_plan(project_id, export_order);
        """
    )


def _migrate_to_v6(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(connection, "prompt_templates", "description", "description TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(
        connection,
        "prompt_templates",
        "story_anchor_json",
        "story_anchor_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        connection,
        "prompt_templates",
        "characters_json",
        "characters_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        connection,
        "prompt_templates",
        "package_metadata_json",
        "package_metadata_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(connection, "prompt_templates", "source_project_id", "source_project_id INTEGER")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS chapter_plot_expansions (
            chapter_id INTEGER PRIMARY KEY,
            enabled INTEGER NOT NULL DEFAULT 1,
            expanded_plot TEXT NOT NULL DEFAULT '',
            model_id INTEGER,
            prompt_template_id INTEGER,
            prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
            FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
        );
        """
    )


def _migrate_to_v7(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "project_settings",
        "analysis_prompt_template_id",
        "analysis_prompt_template_id INTEGER",
    )
    _add_column_if_missing(connection, "chapter_rewrites", "confirmed_at", "confirmed_at TEXT")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS analysis_prompt_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            analysis_dimensions TEXT NOT NULL DEFAULT '',
            evidence_rules TEXT NOT NULL DEFAULT '',
            synthesis_rules TEXT NOT NULL DEFAULT '',
            output_requirements TEXT NOT NULL DEFAULT '',
            version INTEGER NOT NULL DEFAULT 1,
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS chapter_style_analyses (
            chapter_id INTEGER PRIMARY KEY,
            analysis_json TEXT NOT NULL DEFAULT '{}',
            reviewed_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'pending_review',
            model_id INTEGER,
            analysis_prompt_template_id INTEGER,
            prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
            FOREIGN KEY (analysis_prompt_template_id) REFERENCES analysis_prompt_templates(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS project_style_syntheses (
            project_id INTEGER PRIMARY KEY,
            synthesis_json TEXT NOT NULL DEFAULT '{}',
            reviewed_json TEXT NOT NULL DEFAULT '{}',
            prompt_template_id INTEGER,
            model_id INTEGER,
            analysis_prompt_template_id INTEGER,
            prompt_snapshot_json TEXT NOT NULL DEFAULT '{}',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            reviewed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
            FOREIGN KEY (analysis_prompt_template_id) REFERENCES analysis_prompt_templates(id) ON DELETE SET NULL
        );
        """
    )
    connection.execute(
        """
        INSERT INTO analysis_prompt_templates (
            name, description, analysis_dimensions, evidence_rules,
            synthesis_rules, output_requirements, is_default
        )
        SELECT ?, ?, ?, ?, ?, ?, 1
        WHERE NOT EXISTS (SELECT 1 FROM analysis_prompt_templates WHERE deleted_at IS NULL)
        """,
        (
            "通用小说风格分析",
            "逐章提取可迁移的表达规律，并汇总为改写提示词。",
            "动作描写；对话与人物关系；心理活动；节奏与句式；叙事视角；环境与感官；转场与信息揭示。",
            "每条观察必须附短文本证据；区分稳定规律与本章偶然写法；不把人物名、剧情事实或专有设定当作风格。",
            "跨章节去重并处理冲突，只保留反复出现且可执行的规律；将观察转写为基础规则、识别规则和改写规则。",
            "输出严格 JSON；保留 observations、evidence 和 confidence；最终改写提示词必须符合 rusty.rewrite_prompt schema v2。",
        ),
    )
    connection.execute("UPDATE project_settings SET processing_mode = 'extract' WHERE processing_mode = 'summary'")


def _migrate_to_v8(connection: sqlite3.Connection) -> None:
    if _column_exists(connection, "prompt_templates", "scene_detection_rules"):
        connection.execute("ALTER TABLE prompt_templates DROP COLUMN scene_detection_rules")
    connection.execute(
        "DELETE FROM project_custom_prompts WHERE prompt_key IN (?, ?, ?)",
        ("scene_detection_rules", "scene_detection", "scene_override"),
    )


def _migrate_to_v9(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "project_settings",
        "rewrite_mode",
        "rewrite_mode TEXT NOT NULL DEFAULT 'anchor_expand' CHECK (rewrite_mode IN ('anchor_expand', 'full_rewrite'))",
    )
    _add_column_if_missing(
        connection,
        "project_settings",
        "max_attempts",
        "max_attempts INTEGER NOT NULL DEFAULT 2",
    )
    _add_column_if_missing(
        connection,
        "chapter_scene_analysis",
        "context_markers_json",
        "context_markers_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "rewrite_mode",
        "rewrite_mode TEXT NOT NULL DEFAULT 'anchor_expand' CHECK (rewrite_mode IN ('anchor_expand', 'full_rewrite'))",
    )
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "anchor_text",
        "anchor_text TEXT NOT NULL DEFAULT ''",
    )
    _add_column_if_missing(
        connection,
        "chapter_rewrites",
        "expanded_text",
        "expanded_text TEXT NOT NULL DEFAULT ''",
    )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS generation_attempts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL,
            stage TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            request_json TEXT NOT NULL DEFAULT '{}',
            response_text TEXT NOT NULL DEFAULT '',
            parsed_json TEXT NOT NULL DEFAULT '{}',
            error_type TEXT,
            error_message TEXT,
            model_id INTEGER,
            prompt_template_id INTEGER,
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chapter_id, stage, attempt_number),
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL,
            FOREIGN KEY (prompt_template_id) REFERENCES prompt_templates(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_generation_attempts_chapter_stage
            ON generation_attempts(chapter_id, stage, attempt_number);
        """
    )


def _migrate_to_v10(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
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
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS document_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            parent_id INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (parent_id) REFERENCES document_categories(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS document_category_links (
            document_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (document_id, category_id),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES document_categories(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_library_documents_created_at
            ON library_documents(created_at DESC);
            CREATE INDEX IF NOT EXISTS idx_library_documents_content_hash
                ON library_documents(content_hash);
            """
        )
    category_columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(document_categories)").fetchall()
    }
    if "parent_id" in category_columns:
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_document_categories_parent_order
            ON document_categories(parent_id, sort_order, name)
            """
        )


def _migrate_to_v11(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(connection, "library_documents", "current_revision_id", "current_revision_id INTEGER")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS document_processing_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            settings_json TEXT NOT NULL DEFAULT '{}',
            is_default INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
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
            UNIQUE (document_id, revision_number),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (template_id) REFERENCES document_processing_templates(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_revision_id) REFERENCES library_document_revisions(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS library_document_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            chapter_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_line INTEGER,
            end_line INTEGER,
            word_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (revision_id, chapter_index),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_library_revisions_document_number
            ON library_document_revisions(document_id, revision_number DESC);
        CREATE INDEX IF NOT EXISTS idx_library_chapters_revision_order
            ON library_document_chapters(revision_id, chapter_index);

        INSERT OR IGNORE INTO document_processing_templates (
            id, name, settings_json, is_default
        ) VALUES (
            1,
            '标准中文小说排版',
            '{"chapter_pattern":"^\\\\s*(第[一二三四五六七八九十百千万零〇两0-9]+[章节卷集部篇回].*|[0-9]+[、.． ].*)\\\\s*$","chapter_indent":0,"paragraph_indent":2,"blank_lines":1,"trim_whitespace":true}',
            1
        );
        """
    )


def _migrate_to_v12(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS document_library_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            storage_path TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _migrate_to_v13(connection: sqlite3.Connection) -> None:
    if _table_exists(connection, "character_cards"):
        _add_column_if_missing(
            connection,
            "character_cards",
            "scope",
            "scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project'))",
        )
        _add_column_if_missing(connection, "character_cards", "project_id", "project_id INTEGER")
        _add_column_if_missing(
            connection,
            "character_cards",
            "source_character_card_id",
            "source_character_card_id INTEGER",
        )
        _add_column_if_missing(connection, "character_cards", "source_version", "source_version INTEGER")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS material_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            material_type TEXT NOT NULL CHECK (material_type IN ('outline', 'plot_skeleton', 'snippet')),
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );

        CREATE TABLE IF NOT EXISTS materials (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT NOT NULL CHECK (material_type IN ('outline', 'plot_skeleton', 'snippet')),
            scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
            project_id INTEGER,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
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
            deleted_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_material_id) REFERENCES materials(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS material_category_links (
            material_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_id, category_id),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS project_documents (
            project_id INTEGER PRIMARY KEY,
            document_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_materials_scope_project_timeline
            ON materials(scope, project_id, timeline_start_chapter, sort_order);
        CREATE INDEX IF NOT EXISTS idx_materials_public_type
            ON materials(scope, material_type, updated_at);
        CREATE INDEX IF NOT EXISTS idx_material_categories_type
            ON material_categories(material_type, sort_order);
        """
    )
    connection.execute(
        """
        INSERT INTO materials (
            material_type, scope, name, description, detail_level, content_json,
            source_metadata_json, import_metadata_json, legacy_outline_id, version,
            created_at, updated_at
        )
        SELECT
            'plot_skeleton', 'public', name, description, detail_level, outline_json,
            source_metadata_json,
            json_set(
                json_set(COALESCE(import_metadata_json, '{}'), '$.migrated_from', 'outline_templates'),
                '$.legacy_material_type',
                'outline'
            ),
            id, version, created_at, updated_at
        FROM outline_templates
        WHERE deleted_at IS NULL
          AND NOT EXISTS (
              SELECT 1 FROM materials m WHERE m.legacy_outline_id = outline_templates.id
          )
        """
    )


def _migrate_to_v14(connection: sqlite3.Connection) -> None:
    _ensure_v14_tag_tables(connection)
    _migrate_materials_to_v14(connection)
    _migrate_character_cards_to_v14(connection)
    _migrate_document_tags_to_v14(connection)
    _add_column_if_missing(connection, "library_document_chapters", "start_offset", "start_offset INTEGER")
    _add_column_if_missing(connection, "library_document_chapters", "end_offset", "end_offset INTEGER")
    connection.executescript(
        """
        DROP TABLE IF EXISTS material_category_links;
        DROP TABLE IF EXISTS material_categories;
        DROP TABLE IF EXISTS document_category_links;
        DROP TABLE IF EXISTS document_categories;
        """
    )


def _migrate_to_v15(connection: sqlite3.Connection) -> None:
    """Add the scene-first long-form rewrite model without replacing legacy data."""
    _add_column_if_missing(connection, "chapters", "volume_id", "volume_id INTEGER")
    _add_column_if_missing(connection, "chapters", "source_start_offset", "source_start_offset INTEGER")
    _add_column_if_missing(connection, "chapters", "source_end_offset", "source_end_offset INTEGER")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS story_volumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            volume_index INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            original_start_offset INTEGER,
            original_end_offset INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (project_id, volume_index),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS chapter_source_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            document_id INTEGER,
            chapter_id INTEGER NOT NULL,
            source_version INTEGER NOT NULL DEFAULT 1,
            original_start_offset INTEGER NOT NULL DEFAULT 0,
            original_end_offset INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chapter_id, source_version),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE SET NULL,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            parent_scene_id INTEGER,
            scene_index INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            original_start_offset INTEGER NOT NULL,
            original_end_offset INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            source_version INTEGER NOT NULL DEFAULT 1,
            boundary_reason_json TEXT NOT NULL DEFAULT '[]',
            boundary_status TEXT NOT NULL DEFAULT 'proposed'
                CHECK (boundary_status IN ('proposed', 'confirmed', 'adjusted')),
            scene_type TEXT NOT NULL DEFAULT 'general',
            user_confirmed INTEGER NOT NULL DEFAULT 0,
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            UNIQUE (chapter_id, scene_index),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scene_paragraphs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            paragraph_index INTEGER NOT NULL,
            original_start_offset INTEGER NOT NULL,
            original_end_offset INTEGER NOT NULL,
            original_text TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (scene_id, paragraph_index),
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scene_fact_ledgers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            ledger_version INTEGER NOT NULL DEFAULT 1,
            facts_json TEXT NOT NULL DEFAULT '{}',
            schema_version TEXT NOT NULL DEFAULT 'rusty.scene_facts.v1',
            source_kind TEXT NOT NULL DEFAULT 'analysis',
            model_id INTEGER,
            prompt_compilation_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (scene_id, ledger_version),
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS character_story_states (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            character_card_id INTEGER,
            character_name TEXT NOT NULL,
            state_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (scene_id, character_name),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (character_card_id) REFERENCES character_cards(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS story_skeletons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER,
            scene_id INTEGER,
            scope TEXT NOT NULL DEFAULT 'scene' CHECK (scope IN ('scene', 'chapter', 'volume', 'book')),
            source_kind TEXT NOT NULL DEFAULT 'original_analysis',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'superseded')),
            current_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS story_skeleton_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            skeleton_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            nodes_json TEXT NOT NULL DEFAULT '[]',
            skeleton_json TEXT NOT NULL DEFAULT '{}',
            source_references_json TEXT NOT NULL DEFAULT '[]',
            change_note TEXT NOT NULL DEFAULT '',
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (skeleton_id, version),
            FOREIGN KEY (skeleton_id) REFERENCES story_skeletons(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS rewrite_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            scene_id INTEGER,
            mode TEXT NOT NULL CHECK (mode IN ('skeleton_rewrite', 'expansion')),
            skeleton_version_id INTEGER NOT NULL,
            plan_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'executed', 'cancelled')),
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS rewrite_plan_materials (
            plan_id INTEGER NOT NULL,
            material_id INTEGER NOT NULL,
            insertion_after_node TEXT,
            insertion_before_node TEXT,
            insertion_scene_offset INTEGER,
            usage_mode TEXT NOT NULL DEFAULT 'reference'
                CHECK (usage_mode IN ('required', 'reference')),
            event_nodes_json TEXT NOT NULL DEFAULT '[]',
            impact_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (plan_id, material_id),
            FOREIGN KEY (plan_id) REFERENCES rewrite_plans(id) ON DELETE CASCADE,
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS prompt_compilations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER,
            scene_id INTEGER,
            stage TEXT NOT NULL,
            model_id INTEGER,
            max_input_tokens INTEGER NOT NULL,
            reserved_output_tokens INTEGER NOT NULL,
            used_input_tokens INTEGER NOT NULL,
            snapshot_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS prompt_compilation_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            compilation_id INTEGER NOT NULL,
            block_key TEXT NOT NULL,
            content TEXT NOT NULL,
            priority INTEGER NOT NULL,
            required INTEGER NOT NULL DEFAULT 0,
            token_count INTEGER NOT NULL DEFAULT 0,
            source_type TEXT NOT NULL DEFAULT '',
            source_id TEXT NOT NULL DEFAULT '',
            included INTEGER NOT NULL DEFAULT 1,
            decision TEXT NOT NULL DEFAULT 'included',
            sort_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (compilation_id) REFERENCES prompt_compilations(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS retrieval_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            query_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS retrieval_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            retrieval_run_id INTEGER NOT NULL,
            retrieval_type TEXT NOT NULL
                CHECK (retrieval_type IN ('manual', 'structure', 'keyword', 'relationship', 'vector')),
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            source_location TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            relevance_reason TEXT NOT NULL DEFAULT '',
            confidence REAL NOT NULL DEFAULT 0,
            included_in_prompt INTEGER NOT NULL DEFAULT 0,
            token_count INTEGER NOT NULL DEFAULT 0,
            rank_order INTEGER NOT NULL DEFAULT 0,
            FOREIGN KEY (retrieval_run_id) REFERENCES retrieval_runs(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scene_style_contexts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            scene_type TEXT NOT NULL DEFAULT 'general',
            global_rules_json TEXT NOT NULL DEFAULT '[]',
            scene_rules_json TEXT NOT NULL DEFAULT '[]',
            examples_json TEXT NOT NULL DEFAULT '[]',
            recent_techniques_json TEXT NOT NULL DEFAULT '[]',
            forbidden_repetitions_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS scene_generation_stages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            plan_id INTEGER,
            stage TEXT NOT NULL
                CHECK (stage IN ('analysis', 'planning', 'rewrite', 'consistency_check', 'targeted_repair')),
            status TEXT NOT NULL DEFAULT 'pending'
                CHECK (status IN ('pending', 'running', 'completed', 'failed', 'needs_confirmation')),
            output_json TEXT NOT NULL DEFAULT '{}',
            prompt_compilation_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES rewrite_plans(id) ON DELETE SET NULL,
            FOREIGN KEY (prompt_compilation_id) REFERENCES prompt_compilations(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS scene_rewrite_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            plan_id INTEGER,
            skeleton_version_id INTEGER,
            version INTEGER NOT NULL,
            rewritten_text TEXT NOT NULL,
            revision_kind TEXT NOT NULL DEFAULT 'generation'
                CHECK (revision_kind IN ('generation', 'manual', 'targeted_repair')),
            parent_version_id INTEGER,
            prompt_compilation_id INTEGER,
            facts_after_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (scene_id, version),
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (plan_id) REFERENCES rewrite_plans(id) ON DELETE SET NULL,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE SET NULL,
            FOREIGN KEY (parent_version_id) REFERENCES scene_rewrite_versions(id) ON DELETE SET NULL,
            FOREIGN KEY (prompt_compilation_id) REFERENCES prompt_compilations(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS targeted_repairs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            source_version_id INTEGER NOT NULL,
            result_version_id INTEGER,
            paragraph_start INTEGER NOT NULL,
            paragraph_end INTEGER NOT NULL,
            issues_json TEXT NOT NULL DEFAULT '[]',
            before_text TEXT NOT NULL,
            after_text TEXT NOT NULL DEFAULT '',
            affected_facts_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (source_version_id) REFERENCES scene_rewrite_versions(id) ON DELETE RESTRICT,
            FOREIGN KEY (result_version_id) REFERENCES scene_rewrite_versions(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS consistency_checks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER,
            scene_id INTEGER,
            check_scope TEXT NOT NULL CHECK (check_scope IN ('scene', 'chapter', 'volume', 'book')),
            result_json TEXT NOT NULL DEFAULT '{}',
            revision_required INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chapter_source_versions_chapter
            ON chapter_source_versions(chapter_id, source_version);
        CREATE INDEX IF NOT EXISTS idx_scenes_chapter_order
            ON scenes(chapter_id, scene_index);
        CREATE INDEX IF NOT EXISTS idx_scene_facts_scene_version
            ON scene_fact_ledgers(scene_id, ledger_version);
        CREATE INDEX IF NOT EXISTS idx_character_story_states_project_name
            ON character_story_states(project_id, character_name, scene_id);
        CREATE INDEX IF NOT EXISTS idx_prompt_blocks_compilation_order
            ON prompt_compilation_blocks(compilation_id, sort_order);
        CREATE INDEX IF NOT EXISTS idx_retrieval_results_run_rank
            ON retrieval_results(retrieval_run_id, rank_order);
        CREATE INDEX IF NOT EXISTS idx_scene_rewrites_scene_version
            ON scene_rewrite_versions(scene_id, version DESC);

        CREATE TRIGGER IF NOT EXISTS prevent_original_chapter_text_update
        BEFORE UPDATE OF original_text ON chapters
        WHEN NEW.original_text <> OLD.original_text
        BEGIN
            SELECT RAISE(ABORT, 'chapter original_text is immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_source_version_update
        BEFORE UPDATE ON chapter_source_versions
        BEGIN
            SELECT RAISE(ABORT, 'chapter source versions are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_source_version_delete
        BEFORE DELETE ON chapter_source_versions
        BEGIN
            SELECT RAISE(ABORT, 'chapter source versions are immutable');
        END;

        CREATE TRIGGER IF NOT EXISTS prevent_scene_original_update
        BEFORE UPDATE OF original_text, original_start_offset, original_end_offset ON scenes
        WHEN NEW.original_text <> OLD.original_text
          OR NEW.original_start_offset <> OLD.original_start_offset
          OR NEW.original_end_offset <> OLD.original_end_offset
        BEGIN
            SELECT RAISE(ABORT, 'scene original source range is immutable');
        END;
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO story_volumes (project_id, volume_index, title)
        SELECT id, 1, ''
        FROM projects
        """
    )
    connection.execute(
        """
        UPDATE chapters
        SET
            volume_id = COALESCE(
                volume_id,
                (SELECT id FROM story_volumes v WHERE v.project_id = chapters.project_id AND v.volume_index = 1)
            ),
            source_start_offset = COALESCE(
                source_start_offset,
                (
                    SELECT COALESCE(SUM(length(previous.original_text)), 0)
                    FROM chapters previous
                    WHERE previous.project_id = chapters.project_id
                      AND previous.chapter_index < chapters.chapter_index
                )
            ),
            source_end_offset = COALESCE(
                source_end_offset,
                (
                    SELECT COALESCE(SUM(length(previous.original_text)), 0)
                    FROM chapters previous
                    WHERE previous.project_id = chapters.project_id
                      AND previous.chapter_index <= chapters.chapter_index
                )
            )
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO chapter_source_versions (
            project_id, document_id, chapter_id, source_version,
            original_start_offset, original_end_offset, original_text, content_hash
        )
        SELECT
            c.project_id,
            pd.document_id,
            c.id,
            1,
            COALESCE(c.source_start_offset, 0),
            COALESCE(c.source_end_offset, length(c.original_text)),
            c.original_text,
            lower(hex(cast(c.original_text AS blob)))
        FROM chapters c
        LEFT JOIN project_documents pd ON pd.project_id = c.project_id
        """
    )


def _migrate_to_v16(connection: sqlite3.Connection) -> None:
    """Add auditable model calls and migrate legacy character fields without data loss."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS model_invocations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invocation_kind TEXT NOT NULL,
            project_id INTEGER,
            document_id INTEGER,
            chapter_id INTEGER,
            scene_id INTEGER,
            resource_type TEXT,
            resource_id INTEGER,
            model_id INTEGER,
            stage TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'running'
                CHECK (status IN ('running', 'completed', 'failed', 'invalid')),
            request_json TEXT NOT NULL DEFAULT '{}',
            output_schema_json TEXT NOT NULL DEFAULT '{}',
            response_text TEXT NOT NULL DEFAULT '',
            parsed_json TEXT NOT NULL DEFAULT '{}',
            validation_json TEXT NOT NULL DEFAULT '{}',
            token_usage_json TEXT NOT NULL DEFAULT '{}',
            elapsed_ms INTEGER,
            error_type TEXT,
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE SET NULL,
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE SET NULL,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE SET NULL,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_model_invocations_resource
            ON model_invocations(resource_type, resource_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_model_invocations_scene
            ON model_invocations(scene_id, stage, created_at DESC);

        CREATE TABLE IF NOT EXISTS document_split_proposals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            source_revision_id INTEGER NOT NULL,
            proposal_kind TEXT NOT NULL CHECK (proposal_kind IN ('ai', 'regex', 'manual')),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'applied', 'cancelled')),
            boundaries_json TEXT NOT NULL DEFAULT '[]',
            unmatched_json TEXT NOT NULL DEFAULT '{}',
            model_invocation_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            applied_revision_id INTEGER,
            applied_at TEXT,
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (source_revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE,
            FOREIGN KEY (model_invocation_id) REFERENCES model_invocations(id) ON DELETE SET NULL,
            FOREIGN KEY (applied_revision_id) REFERENCES library_document_revisions(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS scene_workflow_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            mode TEXT NOT NULL CHECK (mode IN ('skeleton_rewrite', 'expansion')),
            status TEXT NOT NULL DEFAULT 'analyzing'
                CHECK (status IN (
                    'analyzing', 'awaiting_skeleton', 'planning', 'awaiting_plan',
                    'generating', 'checking', 'repairing', 'completed', 'failed'
                )),
            skeleton_id INTEGER,
            skeleton_version_id INTEGER,
            plan_id INTEGER,
            current_stage TEXT NOT NULL DEFAULT 'analysis',
            error_message TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            completed_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (skeleton_id) REFERENCES story_skeletons(id) ON DELETE SET NULL,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE SET NULL,
            FOREIGN KEY (plan_id) REFERENCES rewrite_plans(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_scene_workflow_runs_scene
            ON scene_workflow_runs(scene_id, created_at DESC);
        """
    )

    rows = connection.execute(
        """
        SELECT id, description, personality, speech_style, action_constraints,
               anti_ooc_rules, relationship_notes, profile_json, custom_fields_json
        FROM character_cards
        WHERE deleted_at IS NULL
        """
    ).fetchall()
    labels = (
        ("description", "人物简介"),
        ("personality", "长期性格"),
        ("speech_style", "说话方式"),
        ("action_constraints", "能力与限制"),
        ("anti_ooc_rules", "不可改变的设定"),
        ("relationship_notes", "关系说明"),
    )
    for row in rows:
        existing = _safe_json_list(row["custom_fields_json"])
        normalized = {
            " ".join(str(item.get("label") or "").strip().split()).casefold()
            for item in existing
            if isinstance(item, dict)
        }
        additions: list[dict[str, object]] = []
        for column, label in labels:
            value = str(row[column] or "").strip()
            if value and label.casefold() not in normalized:
                additions.append(
                    {
                        "id": f"legacy-{column}",
                        "label": label,
                        "value": value,
                        "sort_order": len(existing) + len(additions),
                    }
                )
        profile = _safe_json_object(row["profile_json"])
        for key, value in profile.items():
            if value in (None, "", [], {}):
                continue
            label = str(key).strip() or "旧版属性"
            if " ".join(label.split()).casefold() in normalized:
                continue
            rendered = (
                json.dumps(value, ensure_ascii=False)
                if isinstance(value, (dict, list))
                else str(value)
            )
            additions.append(
                {
                    "id": f"legacy-profile-{len(additions)}",
                    "label": label,
                    "value": rendered,
                    "sort_order": len(existing) + len(additions),
                }
            )
        if additions:
            connection.execute(
                "UPDATE character_cards SET custom_fields_json = ? WHERE id = ?",
                (json.dumps([*existing, *additions], ensure_ascii=False), row["id"]),
            )


def _migrate_to_v17(connection: sqlite3.Connection) -> None:
    """Restore independent document categories and remove the legacy project tag."""
    if _table_exists(connection, "document_categories"):
        _add_column_if_missing(
            connection,
            "document_categories",
            "normalized_name",
            "normalized_name TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            connection,
            "document_categories",
            "sort_order",
            "sort_order INTEGER NOT NULL DEFAULT 0",
        )
        _add_column_if_missing(
            connection,
            "document_categories",
            "updated_at",
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP",
        )
        _add_column_if_missing(connection, "document_categories", "deleted_at", "deleted_at TEXT")
        for row in connection.execute(
            "SELECT id, name FROM document_categories WHERE deleted_at IS NULL ORDER BY id"
        ).fetchall():
            category_id = int(row[0])
            normalized_name = _normalized_tag_name(str(row[1]))
            existing = connection.execute(
                """
                SELECT id FROM document_categories
                WHERE id <> ? AND normalized_name = ? AND deleted_at IS NULL
                ORDER BY id LIMIT 1
                """,
                (category_id, normalized_name),
            ).fetchone()
            if existing is None:
                connection.execute(
                    "UPDATE document_categories SET normalized_name = ? WHERE id = ?",
                    (normalized_name, category_id),
                )
                continue
            existing_id = int(existing[0])
            if _table_exists(connection, "document_category_links"):
                connection.execute(
                    """
                    INSERT OR IGNORE INTO document_category_links (document_id, category_id, created_at)
                    SELECT document_id, ?, created_at
                    FROM document_category_links
                    WHERE category_id = ?
                    """,
                    (existing_id, category_id),
                )
                connection.execute(
                    "DELETE FROM document_category_links WHERE category_id = ?",
                    (category_id,),
                )
            connection.execute(
                """
                UPDATE document_categories
                SET deleted_at = CURRENT_TIMESTAMP, normalized_name = ?
                WHERE id = ?
                """,
                (normalized_name, category_id),
            )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS document_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_document_categories_normalized_active
            ON document_categories(normalized_name)
            WHERE deleted_at IS NULL;
        CREATE TABLE IF NOT EXISTS document_category_links (
            document_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (document_id, category_id),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES document_categories(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_document_categories_order
            ON document_categories(sort_order, name);
        CREATE INDEX IF NOT EXISTS idx_document_category_links_category
            ON document_category_links(category_id, document_id);
        """
    )
    legacy_project_name = _normalized_tag_name("工程")
    if not _table_exists(connection, "document_tags"):
        return
    connection.execute(
        """
        INSERT INTO document_categories (name, normalized_name, sort_order)
        SELECT name, normalized_name, sort_order
        FROM document_tags
        WHERE deleted_at IS NULL AND normalized_name <> ?
        ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
        DO UPDATE SET name = excluded.name, sort_order = excluded.sort_order,
                      updated_at = CURRENT_TIMESTAMP
        """,
        (legacy_project_name,),
    )
    if _table_exists(connection, "document_tag_links"):
        connection.execute(
            """
            INSERT OR IGNORE INTO document_category_links (document_id, category_id, created_at)
            SELECT links.document_id, categories.id, links.created_at
            FROM document_tag_links links
            JOIN document_tags tags ON tags.id = links.tag_id
            JOIN document_categories categories
              ON categories.normalized_name = tags.normalized_name
             AND categories.deleted_at IS NULL
            WHERE tags.deleted_at IS NULL AND tags.normalized_name <> ?
            """,
            (legacy_project_name,),
        )
        connection.execute(
            """
            DELETE FROM document_tag_links
            WHERE tag_id IN (
                SELECT id FROM document_tags
                WHERE deleted_at IS NULL AND normalized_name = ?
            )
            """,
            (legacy_project_name,),
        )
    connection.execute(
        """
        UPDATE document_tags
        SET deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP),
            updated_at = CURRENT_TIMESTAMP
        WHERE deleted_at IS NULL AND normalized_name = ?
        """,
        (legacy_project_name,),
    )


def _migrate_to_v18(connection: sqlite3.Connection) -> None:
    """Add revision-bound autosave drafts without mutating revision files."""
    connection.executescript(
        """
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
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_drafts_document_full
            ON library_document_drafts(document_id)
            WHERE chapter_id IS NULL;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_library_drafts_document_chapter
            ON library_document_drafts(document_id, chapter_id)
            WHERE chapter_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_library_drafts_base_revision
            ON library_document_drafts(base_revision_id, updated_at DESC);
        """
    )


def _migrate_to_v19(connection: sqlite3.Connection) -> None:
    """Promote unmistakable legacy volume pseudo-chapters into a hierarchy."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS library_document_volumes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            document_id INTEGER NOT NULL,
            revision_id INTEGER NOT NULL,
            volume_index INTEGER NOT NULL,
            title TEXT NOT NULL,
            start_offset INTEGER NOT NULL,
            end_offset INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (revision_id, volume_index),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_library_volumes_revision_order
            ON library_document_volumes(revision_id, volume_index);
        """
    )
    _add_column_if_missing(
        connection,
        "library_document_chapters",
        "volume_id",
        "volume_id INTEGER REFERENCES library_document_volumes(id) ON DELETE SET NULL",
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_library_chapters_volume_order "
        "ON library_document_chapters(volume_id, chapter_index)"
    )
    volume_pattern = re.compile(
        r"^\s*(?:第[一二三四五六七八九十百千万零〇两0-9]+卷|卷[一二三四五六七八九十百千万零〇两0-9]+)(?:\s.*|[：:].*)?\s*$"
    )
    revisions = connection.execute(
        """
        SELECT r.id, r.document_id, r.storage_path
        FROM library_document_revisions r
        JOIN library_documents d ON d.current_revision_id = r.id
        WHERE d.deleted_at IS NULL
        """
    ).fetchall()
    for revision in revisions:
        revision_id = int(revision["id"])
        if connection.execute(
            "SELECT 1 FROM library_document_volumes WHERE revision_id = ? LIMIT 1",
            (revision_id,),
        ).fetchone():
            continue
        path = Path(str(revision["storage_path"]))
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        chapters = connection.execute(
            """
            SELECT *
            FROM library_document_chapters
            WHERE revision_id = ?
            ORDER BY chapter_index
            """,
            (revision_id,),
        ).fetchall()
        volume_rows = [row for row in chapters if volume_pattern.fullmatch(str(row["title"]))]
        if not volume_rows:
            continue
        volume_ids: list[tuple[int, int, int]] = []
        for index, row in enumerate(volume_rows, start=1):
            start = int(row["start_offset"]) if row["start_offset"] is not None else 0
            next_start = (
                int(volume_rows[index]["start_offset"])
                if index < len(volume_rows) and volume_rows[index]["start_offset"] is not None
                else len(text)
            )
            cursor = connection.execute(
                """
                INSERT OR IGNORE INTO library_document_volumes (
                    document_id, revision_id, volume_index, title, start_offset, end_offset
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(revision["document_id"]),
                    revision_id,
                    index,
                    str(row["title"]).strip(),
                    start,
                    next_start,
                ),
            )
            volume_id = int(cursor.lastrowid) if cursor.lastrowid else int(
                connection.execute(
                    "SELECT id FROM library_document_volumes WHERE revision_id = ? AND volume_index = ?",
                    (revision_id, index),
                ).fetchone()["id"]
            )
            volume_ids.append((volume_id, start, next_start))
        volume_chapter_ids = {int(row["id"]) for row in volume_rows}
        for row in chapters:
            chapter_id = int(row["id"])
            if chapter_id in volume_chapter_ids:
                continue
            start = int(row["start_offset"]) if row["start_offset"] is not None else -1
            volume_id = next(
                (item[0] for item in volume_ids if item[1] < start < item[2]),
                None,
            )
            connection.execute(
                "UPDATE library_document_chapters SET volume_id = ? WHERE id = ?",
                (volume_id, chapter_id),
            )
        connection.executemany(
            "DELETE FROM library_document_chapters WHERE id = ?",
            [(chapter_id,) for chapter_id in volume_chapter_ids],
        )
        remaining = connection.execute(
            "SELECT id FROM library_document_chapters WHERE revision_id = ? ORDER BY chapter_index",
            (revision_id,),
        ).fetchall()
        for index, row in enumerate(remaining, start=1):
            connection.execute(
                "UPDATE library_document_chapters SET chapter_index = ? WHERE id = ?",
                (-(1000000 + index), int(row["id"])),
            )
        for index, row in enumerate(remaining, start=1):
            connection.execute(
                "UPDATE library_document_chapters SET chapter_index = ? WHERE id = ?",
                (index, int(row["id"])),
            )
        connection.execute(
            "UPDATE library_documents SET chapter_count = ? WHERE id = ?",
            (len(remaining), int(revision["document_id"])),
        )


def _migrate_to_v20(connection: sqlite3.Connection) -> None:
    """Add public character categories and repair legacy project bindings."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_character_categories_normalized_active
            ON character_categories(normalized_name)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_character_categories_sort_order
            ON character_categories(sort_order);

        CREATE TABLE IF NOT EXISTS character_category_links (
            character_card_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (character_card_id, category_id),
            FOREIGN KEY (character_card_id)
                REFERENCES character_cards(id)
                ON DELETE CASCADE,
            FOREIGN KEY (category_id)
                REFERENCES character_categories(id)
                ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_character_category_links_category
            ON character_category_links(category_id);
        CREATE INDEX IF NOT EXISTS idx_character_category_links_character
            ON character_category_links(character_card_id);

        INSERT OR IGNORE INTO project_character_bindings (
            project_id,
            character_card_id,
            sort_order,
            is_active
        )
        SELECT
            project_id,
            id,
            0,
            1
        FROM character_cards
        WHERE scope = 'project'
          AND project_id IS NOT NULL
          AND deleted_at IS NULL;
        """
    )


def _migrate_to_v21(connection: sqlite3.Connection) -> None:
    """Persist configurable character extraction behavior."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_extraction_settings (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            model_id INTEGER,
            detail_level TEXT NOT NULL DEFAULT 'standard'
                CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            max_candidates INTEGER NOT NULL DEFAULT 8,
            extract_all_characters INTEGER NOT NULL DEFAULT 1,
            generate_tags INTEGER NOT NULL DEFAULT 1,
            generate_appearance INTEGER NOT NULL DEFAULT 1,
            generate_relationships INTEGER NOT NULL DEFAULT 1,
            generate_personality INTEGER NOT NULL DEFAULT 1,
            generate_speech_style INTEGER NOT NULL DEFAULT 1,
            generate_action_constraints INTEGER NOT NULL DEFAULT 1,
            generate_anti_ooc_rules INTEGER NOT NULL DEFAULT 1,
            generate_abilities_background INTEGER NOT NULL DEFAULT 1,
            custom_requirements TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        );
        """
    )


def _migrate_to_v22(connection: sqlite3.Connection) -> None:
    """Unify material assets and add categories, tag filters, and AI settings."""
    _add_column_if_missing(
        connection,
        "material_tags",
        "tag_group",
        "tag_group TEXT NOT NULL DEFAULT 'general' CHECK (tag_group IN ('general', 'applicable_scene'))",
    )
    if _table_exists(connection, "material_categories"):
        category_columns = {
            str(row[1])
            for row in connection.execute("PRAGMA table_info(material_categories)").fetchall()
        }
        if "normalized_name" not in category_columns:
            _migrate_material_categories_to_tags(connection)
            connection.execute("DROP TABLE IF EXISTS material_category_links")
            connection.execute("DROP TABLE IF EXISTS material_categories")
    connection.executescript(
        """
        DROP INDEX IF EXISTS idx_material_tags_normalized_active;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_material_tags_normalized_active
            ON material_tags(normalized_name, tag_group)
            WHERE deleted_at IS NULL;

        CREATE TABLE IF NOT EXISTS material_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT NOT NULL CHECK (material_type IN ('scene_reference', 'plot_skeleton')),
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_material_categories_type_name_active
            ON material_categories(material_type, normalized_name)
            WHERE deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_material_categories_type_sort
            ON material_categories(material_type, sort_order);

        CREATE TABLE IF NOT EXISTS material_category_links (
            material_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_id, category_id),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_material_category_links_category
            ON material_category_links(category_id);
        CREATE INDEX IF NOT EXISTS idx_material_category_links_material
            ON material_category_links(material_id);

        CREATE TABLE IF NOT EXISTS project_material_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            material_type TEXT NOT NULL CHECK (material_type IN ('scene_reference', 'plot_skeleton')),
            match_mode TEXT NOT NULL DEFAULT 'any' CHECK (match_mode IN ('any', 'all')),
            manual_material_ids_json TEXT NOT NULL DEFAULT '[]',
            include_scene_keywords INTEGER NOT NULL DEFAULT 1,
            include_applicable_scene_tags INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (project_id, material_type),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE IF NOT EXISTS project_material_filter_tags (
            filter_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (filter_id, tag_id),
            FOREIGN KEY (filter_id) REFERENCES project_material_filters(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_project_material_filter_tags_tag
            ON project_material_filter_tags(tag_id);

        CREATE TABLE IF NOT EXISTS material_ai_settings (
            task_type TEXT PRIMARY KEY CHECK (task_type IN (
                'narrative_to_plot_skeleton',
                'plot_text_to_normalized_skeleton',
                'source_text_to_scene_material'
            )),
            model_id INTEGER,
            detail_level TEXT NOT NULL DEFAULT 'standard'
                CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            max_candidates INTEGER NOT NULL DEFAULT 6,
            generate_tags INTEGER NOT NULL DEFAULT 1,
            custom_requirements TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        );
        """
    )

    defaults = {
        "narrative_to_plot_skeleton": (
            "从叙事文本提炼可复用剧情骨架。只使用来源中有证据的因果、冲突和转折；缺失项留空。"
        ),
        "plot_text_to_normalized_skeleton": (
            "把已有剧情文本规范化为结构化剧情骨架。保持原有事件次序和事实，不添加新情节。"
        ),
        "source_text_to_scene_material": (
            "从来源文本提炼场景写作素材，只总结场面、动作、环境、感官和写作提示，不生成剧情骨架。"
        ),
    }
    for task_type, system_prompt in defaults.items():
        connection.execute(
            """
            INSERT OR IGNORE INTO material_ai_settings (task_type, system_prompt)
            VALUES (?, ?)
            """,
            (task_type, system_prompt),
        )

    legacy_rows = connection.execute(
        """
        SELECT id, project_id, material_type, source_metadata_json
        FROM materials
        WHERE scope = 'project' AND project_id IS NOT NULL
        """
    ).fetchall()
    for row in legacy_rows:
        material_id = int(row["id"])
        project_id = int(row["project_id"])
        material_type = str(row["material_type"])
        metadata = _safe_json_object(row["source_metadata_json"])
        metadata.update(
            {
                "legacy_scope": "project",
                "legacy_project_id": project_id,
                "migrated_to_unified_library": True,
            }
        )
        connection.execute(
            """
            UPDATE materials
            SET scope = 'public', project_id = NULL, source_metadata_json = ?,
                updated_at = updated_at
            WHERE id = ?
            """,
            (json.dumps(metadata, ensure_ascii=False), material_id),
        )
        tag_rows = connection.execute(
            "SELECT tag_id FROM material_tag_links WHERE material_id = ?",
            (material_id,),
        ).fetchall()
        if not tag_rows:
            continue
        connection.execute(
            """
            INSERT OR IGNORE INTO project_material_filters (project_id, material_type)
            VALUES (?, ?)
            """,
            (project_id, material_type),
        )
        filter_id = int(
            connection.execute(
                """
                SELECT id FROM project_material_filters
                WHERE project_id = ? AND material_type = ?
                """,
                (project_id, material_type),
            ).fetchone()["id"]
        )
        for tag_row in tag_rows:
            connection.execute(
                """
                INSERT OR IGNORE INTO project_material_filter_tags (filter_id, tag_id)
                VALUES (?, ?)
                """,
                (filter_id, int(tag_row["tag_id"])),
            )


def _migrate_to_v23(connection: sqlite3.Connection) -> None:
    """Expand the three material AI task settings without losing v22 preferences."""
    columns = {
        str(row[1])
        for row in connection.execute("PRAGMA table_info(material_ai_settings)").fetchall()
    }
    additions = {
        "user_prompt_template": "TEXT NOT NULL DEFAULT ''",
        "analysis_dimensions_json": "TEXT NOT NULL DEFAULT '[]'",
        "generate_general_tags": "INTEGER NOT NULL DEFAULT 1",
        "generate_applicable_scene_tags": "INTEGER NOT NULL DEFAULT 1",
    }
    for column_name, declaration in additions.items():
        if column_name not in columns:
            connection.execute(
                f"ALTER TABLE material_ai_settings ADD COLUMN {column_name} {declaration}"
            )

    defaults = {
        "narrative_to_plot_skeleton": {
            "user_prompt_template": "Identify the premise, stages, conflicts, turns, climax, resolution, and hooks.",
            "analysis_dimensions": [
                "premise", "stages", "conflicts", "turning_points", "climax", "resolution", "hooks",
            ],
        },
        "plot_text_to_normalized_skeleton": {
            "user_prompt_template": "Normalize the supplied plot while preserving every supported causal link.",
            "analysis_dimensions": [
                "premise", "stages", "conflicts", "turning_points", "climax", "resolution", "hooks",
            ],
        },
        "source_text_to_scene_material": {
            "user_prompt_template": "Extract scene beats, actions, environment, sensory cues, and writing guidance.",
            "analysis_dimensions": [
                "summary", "key_beats", "actions", "environment", "sensory",
                "writing_guidance", "source_cues", "avoidances", "applicable_conditions",
            ],
        },
    }
    for task_type, values in defaults.items():
        connection.execute(
            """
            UPDATE material_ai_settings
            SET user_prompt_template = CASE
                    WHEN user_prompt_template = '' THEN ?
                    ELSE user_prompt_template
                END,
                analysis_dimensions_json = CASE
                    WHEN analysis_dimensions_json = '[]' THEN ?
                    ELSE analysis_dimensions_json
                END,
                generate_general_tags = generate_tags,
                generate_applicable_scene_tags = generate_tags
            WHERE task_type = ?
            """,
            (
                values["user_prompt_template"],
                json.dumps(values["analysis_dimensions"], ensure_ascii=False),
                task_type,
            ),
        )


def _migrate_to_v24(connection: sqlite3.Connection) -> None:
    """Separate durable project purpose from execution settings."""
    _add_column_if_missing(
        connection,
        "projects",
        "project_kind",
        "project_kind TEXT NOT NULL DEFAULT 'rewrite' "
        "CHECK (project_kind IN ('rewrite', 'branch', 'legacy_extract'))",
    )
    connection.execute(
        """
        UPDATE projects
        SET project_kind = CASE
            WHEN EXISTS (
                SELECT 1
                FROM project_settings settings
                WHERE settings.project_id = projects.id
                  AND settings.processing_mode IN ('extract', 'summary')
            ) THEN 'legacy_extract'
            ELSE 'rewrite'
        END
        """
    )


def _migrate_to_v25(connection: sqlite3.Connection) -> None:
    """Add the structured skeleton payload without replacing legacy nodes."""
    # Some historical/diagnostic databases legitimately contain only a subset
    # of feature tables. v15 owns creation of this table; do not fabricate a
    # disconnected replacement when that feature was never present.
    if not _table_exists(connection, "story_skeleton_versions"):
        return
    _add_column_if_missing(
        connection,
        "story_skeleton_versions",
        "skeleton_json",
        "skeleton_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        connection,
        "story_skeleton_versions",
        "source_references_json",
        "source_references_json TEXT NOT NULL DEFAULT '[]'",
    )


def _migrate_to_v26(connection: sqlite3.Connection) -> None:
    """Create branch, semantic-anchor, seam, and branch-content storage."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS story_anchors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            anchor_type TEXT NOT NULL CHECK (anchor_type IN (
                'document_end', 'chapter_start', 'chapter_end',
                'scene_start', 'scene_end', 'skeleton_node', 'text_offset'
            )),
            chapter_id INTEGER,
            scene_id INTEGER,
            skeleton_version_id INTEGER,
            node_id TEXT,
            text_offset INTEGER,
            side TEXT NOT NULL DEFAULT 'after' CHECK (side IN ('before', 'after', 'at')),
            source_version_id INTEGER,
            source_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE RESTRICT,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE RESTRICT,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS story_branches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            parent_branch_id INTEGER,
            base_source_kind TEXT NOT NULL CHECK (base_source_kind IN ('original', 'branch')),
            base_source_version_id INTEGER,
            name TEXT NOT NULL,
            branch_mode TEXT NOT NULL CHECK (branch_mode IN (
                'open_continuation', 'fork', 'fork_and_rejoin'
            )),
            downstream_strategy TEXT NOT NULL DEFAULT 'replace'
                CHECK (downstream_strategy IN ('replace', 'reference', 'rejoin')),
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'active', 'completed', 'archived')),
            start_anchor_id INTEGER NOT NULL,
            return_anchor_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_branch_id) REFERENCES story_branches(id) ON DELETE RESTRICT,
            FOREIGN KEY (start_anchor_id) REFERENCES story_anchors(id) ON DELETE RESTRICT,
            FOREIGN KEY (return_anchor_id) REFERENCES story_anchors(id) ON DELETE RESTRICT
        );

        CREATE TABLE IF NOT EXISTS branch_seams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            seam_kind TEXT NOT NULL CHECK (seam_kind IN ('entry', 'return')),
            operation TEXT NOT NULL CHECK (operation IN (
                'keep', 'insert_before', 'insert_after', 'replace_range'
            )),
            original_text TEXT NOT NULL DEFAULT '',
            proposed_text TEXT NOT NULL DEFAULT '',
            source_range_json TEXT NOT NULL DEFAULT '{}',
            source_hash TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'confirmed', 'rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS branch_scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            sequence_index INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            current_version INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            UNIQUE (branch_id, sequence_index),
            FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS branch_scene_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_scene_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            generated_text TEXT NOT NULL,
            facts_after_json TEXT NOT NULL DEFAULT '{}',
            source_kind TEXT NOT NULL DEFAULT 'generation'
                CHECK (source_kind IN ('generation', 'manual', 'repair')),
            parent_version_id INTEGER,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (branch_scene_id, version),
            FOREIGN KEY (branch_scene_id) REFERENCES branch_scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_version_id) REFERENCES branch_scene_versions(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_story_branches_project_parent
            ON story_branches(project_id, parent_branch_id);
        CREATE INDEX IF NOT EXISTS idx_branch_scenes_branch_order
            ON branch_scenes(branch_id, sequence_index);
        """
    )


def _migrate_to_v27(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS plot_generation_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            branch_id INTEGER,
            operation_type TEXT NOT NULL DEFAULT 'plot_generation'
                CHECK (operation_type = 'plot_generation'),
            generation_mode TEXT NOT NULL CHECK (generation_mode IN (
                'bounded_insert', 'open_continuation', 'fork', 'fork_and_rejoin'
            )),
            output_topology TEXT NOT NULL CHECK (output_topology IN ('in_place', 'branch')),
            start_anchor_json TEXT NOT NULL,
            return_anchor_json TEXT,
            start_state_json TEXT NOT NULL DEFAULT '{}',
            required_return_state_json TEXT NOT NULL DEFAULT '{}',
            target_skeleton_json TEXT NOT NULL,
            context_json TEXT NOT NULL DEFAULT '{}',
            seams_json TEXT NOT NULL DEFAULT '[]',
            issues_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'awaiting_skeleton'
                CHECK (status IN (
                    'awaiting_skeleton', 'awaiting_seams', 'ready',
                    'blocked', 'completed', 'failed'
                )),
            result_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_plot_generation_project_status
            ON plot_generation_runs(project_id, status);
        """
    )


def _migrate_to_v28(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS prose_rewrite_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            operation_type TEXT NOT NULL DEFAULT 'prose_rewrite'
                CHECK (operation_type = 'prose_rewrite'),
            source_skeleton_json TEXT NOT NULL,
            preservation_policy_json TEXT NOT NULL,
            target_skeleton_json TEXT NOT NULL,
            rewrite_plan_json TEXT NOT NULL DEFAULT '{}',
            rewritten_text TEXT,
            issues_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'planned'
                CHECK (status IN ('planned', 'blocked', 'completed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_to_v29(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS canon_change_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            branch_id INTEGER,
            operation_type TEXT NOT NULL DEFAULT 'canon_change'
                CHECK (operation_type = 'canon_change'),
            old_fact_json TEXT NOT NULL,
            new_fact_json TEXT NOT NULL,
            effective_order INTEGER NOT NULL DEFAULT 0,
            fact_ledger_json TEXT NOT NULL DEFAULT '{}',
            consistency_issues_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'scanned'
                CHECK (status IN ('scanned', 'reviewing', 'applied', 'blocked')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS canon_change_patches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            route_kind TEXT NOT NULL CHECK (route_kind IN ('chapter', 'branch_scene')),
            target_id INTEGER NOT NULL,
            source_range_json TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            original_text TEXT NOT NULL,
            replacement_text TEXT NOT NULL,
            impact_type TEXT NOT NULL CHECK (impact_type IN (
                'direct_fact', 'action_consequence', 'physical_symptom',
                'dialogue_reference', 'other_character_reaction', 'treatment',
                'possession_or_equipment', 'movement_constraint', 'knowledge_state',
                'relationship_effect', 'recovery_progress', 'foreshadowing'
            )),
            reason TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'accepted', 'rejected', 'edited', 'skipped', 'applied', 'blocked')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES canon_change_runs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_canon_patches_run_type
            ON canon_change_patches(run_id, impact_type, target_id);
        """
    )


def _migrate_to_v30(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS branch_chapters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_id INTEGER NOT NULL,
            sequence_index INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            current_version INTEGER NOT NULL DEFAULT 1,
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'generated', 'confirmed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT,
            UNIQUE (branch_id, sequence_index),
            FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS branch_chapter_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_chapter_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            summary TEXT NOT NULL DEFAULT '',
            facts_before_json TEXT NOT NULL DEFAULT '{}',
            facts_after_json TEXT NOT NULL DEFAULT '{}',
            parent_version_id INTEGER,
            source_kind TEXT NOT NULL DEFAULT 'generation'
                CHECK (source_kind IN ('generation', 'manual', 'repair', 'migration', 'restore')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (branch_chapter_id, version),
            FOREIGN KEY (branch_chapter_id) REFERENCES branch_chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_version_id) REFERENCES branch_chapter_versions(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_branch_chapters_branch_order
            ON branch_chapters(branch_id, sequence_index);
        """
    )
    _add_column_if_missing(
        connection,
        "branch_scenes",
        "branch_chapter_id",
        "branch_chapter_id INTEGER REFERENCES branch_chapters(id) ON DELETE CASCADE",
    )
    _add_column_if_missing(
        connection,
        "branch_scenes",
        "scene_index",
        "scene_index INTEGER",
    )
    _add_column_if_missing(
        connection,
        "story_anchors",
        "branch_chapter_id",
        "branch_chapter_id INTEGER REFERENCES branch_chapters(id) ON DELETE SET NULL",
    )
    _add_column_if_missing(
        connection,
        "story_anchors",
        "branch_scene_id",
        "branch_scene_id INTEGER REFERENCES branch_scenes(id) ON DELETE SET NULL",
    )
    _rebuild_story_anchors_v30(connection)
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_branch_scenes_chapter_order
        ON branch_scenes(branch_chapter_id, scene_index)
        WHERE branch_chapter_id IS NOT NULL AND scene_index IS NOT NULL
        """
    )

    branch_rows = connection.execute(
        """
        SELECT DISTINCT branch_id
        FROM branch_scenes
        WHERE branch_chapter_id IS NULL
        ORDER BY branch_id
        """
    ).fetchall()
    for branch_row in branch_rows:
        branch_id = int(branch_row[0])
        sequence_index = int(
            connection.execute(
                "SELECT COALESCE(MAX(sequence_index), 0) + 1 FROM branch_chapters WHERE branch_id = ?",
                (branch_id,),
            ).fetchone()[0]
        )
        cursor = connection.execute(
            """
            INSERT INTO branch_chapters(
                branch_id, sequence_index, title, status
            ) VALUES (?, ?, 'Imported branch scenes', 'generated')
            """,
            (branch_id, sequence_index),
        )
        chapter_id = int(cursor.lastrowid)
        last_scene = connection.execute(
            """
            SELECT v.facts_after_json
            FROM branch_scenes s
            JOIN branch_scene_versions v
              ON v.branch_scene_id = s.id AND v.version = s.current_version
            WHERE s.branch_id = ? AND s.branch_chapter_id IS NULL
            ORDER BY s.sequence_index DESC, s.id DESC
            LIMIT 1
            """,
            (branch_id,),
        ).fetchone()
        facts_after = str(last_scene[0]) if last_scene is not None else "{}"
        connection.execute(
            """
            INSERT INTO branch_chapter_versions(
                branch_chapter_id, version, title, summary,
                facts_before_json, facts_after_json, source_kind
            ) VALUES (?, 1, 'Imported branch scenes', '', '{}', ?, 'migration')
            """,
            (chapter_id, facts_after),
        )
        scenes = connection.execute(
            """
            SELECT id
            FROM branch_scenes
            WHERE branch_id = ? AND branch_chapter_id IS NULL
            ORDER BY sequence_index, id
            """,
            (branch_id,),
        ).fetchall()
        for scene_index, scene in enumerate(scenes, start=1):
            connection.execute(
                """
                UPDATE branch_scenes
                SET branch_chapter_id = ?, scene_index = ?
                WHERE id = ?
                """,
                (chapter_id, scene_index, int(scene[0])),
            )


def _rebuild_story_anchors_v30(connection: sqlite3.Connection) -> None:
    table_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'story_anchors'"
    ).fetchone()
    table_sql = str(table_row[0] or "") if table_row is not None else ""
    if "'branch_chapter'" in table_sql and "'branch_scene'" in table_sql:
        return
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            DROP TABLE IF EXISTS story_anchors_v30;
            CREATE TABLE story_anchors_v30 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                anchor_type TEXT NOT NULL CHECK (anchor_type IN (
                    'document_end', 'chapter_start', 'chapter_end',
                    'scene_start', 'scene_end', 'skeleton_node', 'text_offset',
                    'branch_chapter', 'branch_scene'
                )),
                chapter_id INTEGER,
                scene_id INTEGER,
                skeleton_version_id INTEGER,
                node_id TEXT,
                text_offset INTEGER,
                side TEXT NOT NULL DEFAULT 'after' CHECK (side IN ('before', 'after', 'at')),
                source_version_id INTEGER,
                source_hash TEXT NOT NULL,
                branch_chapter_id INTEGER,
                branch_scene_id INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE RESTRICT,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE RESTRICT,
                FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE RESTRICT,
                FOREIGN KEY (branch_chapter_id) REFERENCES branch_chapters(id) ON DELETE SET NULL,
                FOREIGN KEY (branch_scene_id) REFERENCES branch_scenes(id) ON DELETE SET NULL
            );

            INSERT INTO story_anchors_v30 (
                id, project_id, anchor_type, chapter_id, scene_id,
                skeleton_version_id, node_id, text_offset, side,
                source_version_id, source_hash, branch_chapter_id,
                branch_scene_id, created_at
            )
            SELECT
                id, project_id, anchor_type, chapter_id, scene_id,
                skeleton_version_id, node_id, text_offset, side,
                source_version_id, source_hash, branch_chapter_id,
                branch_scene_id, created_at
            FROM story_anchors;

            DROP TABLE story_anchors;
            ALTER TABLE story_anchors_v30 RENAME TO story_anchors;
            """
        )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_to_v31(connection: sqlite3.Connection) -> None:
    columns = [
        ("stage", "stage TEXT NOT NULL DEFAULT 'start'"),
        ("user_direction", "user_direction TEXT NOT NULL DEFAULT ''"),
        (
            "selected_character_ids_json",
            "selected_character_ids_json TEXT NOT NULL DEFAULT '[]'",
        ),
        (
            "selected_material_ids_json",
            "selected_material_ids_json TEXT NOT NULL DEFAULT '[]'",
        ),
        ("style_profile_id", "style_profile_id INTEGER"),
        ("scene_plan_json", "scene_plan_json TEXT NOT NULL DEFAULT '{}'"),
        ("fact_ledger_json", "fact_ledger_json TEXT NOT NULL DEFAULT '{}'"),
    ]
    for column, definition in columns:
        _add_column_if_missing(connection, "plot_generation_runs", column, definition)


def _migrate_to_v32(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS rewrite_seams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id INTEGER NOT NULL,
            project_id INTEGER NOT NULL,
            seam_kind TEXT NOT NULL CHECK (seam_kind IN ('entry', 'return')),
            operation TEXT NOT NULL CHECK (operation IN (
                'keep', 'insert_before', 'insert_after', 'replace_range'
            )),
            original_text TEXT NOT NULL DEFAULT '',
            proposed_text TEXT NOT NULL DEFAULT '',
            source_range_json TEXT NOT NULL,
            source_hash TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft'
                CHECK (status IN ('draft', 'confirmed', 'rejected')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (run_id) REFERENCES plot_generation_runs(id) ON DELETE CASCADE,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_rewrite_seams_run_kind
            ON rewrite_seams(run_id, seam_kind);
        """
    )
    _add_column_if_missing(
        connection,
        "branch_seams",
        "plot_run_id",
        "plot_run_id INTEGER REFERENCES plot_generation_runs(id) ON DELETE CASCADE",
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_branch_seams_plot_run ON branch_seams(plot_run_id)"
    )


def _migrate_to_v33(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "canon_change_patches",
        "confidence",
        "confidence REAL NOT NULL DEFAULT 1.0",
    )
    _add_column_if_missing(
        connection,
        "canon_change_patches",
        "evidence_json",
        "evidence_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        connection,
        "canon_change_patches",
        "requires_confirmation",
        "requires_confirmation INTEGER NOT NULL DEFAULT 1",
    )


def _migrate_to_v34(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection,
        "plot_generation_runs",
        "range_operation",
        "range_operation TEXT NOT NULL DEFAULT 'insert_between' "
        "CHECK (range_operation IN ('insert_between', 'replace_range'))",
    )


def _migrate_to_v35(connection: sqlite3.Connection) -> None:
    for table in ("branch_seams", "rewrite_seams"):
        _add_column_if_missing(
            connection,
            table,
            "source_anchor_json",
            "source_anchor_json TEXT NOT NULL DEFAULT '{}'",
        )
        _add_column_if_missing(
            connection,
            table,
            "source_version_id",
            "source_version_id INTEGER",
        )


def _migrate_to_v36(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS branch_chapter_version_scenes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_chapter_version_id INTEGER NOT NULL,
            branch_scene_id INTEGER NOT NULL,
            branch_scene_version_id INTEGER NOT NULL,
            scene_index INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (branch_chapter_version_id, branch_scene_id),
            UNIQUE (branch_chapter_version_id, scene_index),
            FOREIGN KEY (branch_chapter_version_id)
                REFERENCES branch_chapter_versions(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_scene_id)
                REFERENCES branch_scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (branch_scene_version_id)
                REFERENCES branch_scene_versions(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_branch_chapter_snapshot_version
            ON branch_chapter_version_scenes(branch_chapter_version_id, scene_index);
        """
    )
    chapter_versions = connection.execute(
        """
        SELECT v.id, v.branch_chapter_id, v.created_at, c.current_version, v.version
        FROM branch_chapter_versions v
        JOIN branch_chapters c ON c.id = v.branch_chapter_id
        ORDER BY v.id
        """
    ).fetchall()
    for chapter_version in chapter_versions:
        scenes = connection.execute(
            """
            SELECT id, scene_index, current_version
            FROM branch_scenes
            WHERE branch_chapter_id = ? AND deleted_at IS NULL
            ORDER BY scene_index, id
            """,
            (chapter_version["branch_chapter_id"],),
        ).fetchall()
        for fallback_index, scene in enumerate(scenes, start=1):
            selected = connection.execute(
                """
                SELECT id FROM branch_scene_versions
                WHERE branch_scene_id = ? AND created_at <= ?
                ORDER BY created_at DESC, version DESC LIMIT 1
                """,
                (scene["id"], chapter_version["created_at"]),
            ).fetchone()
            if selected is None:
                selected = connection.execute(
                    """
                    SELECT id FROM branch_scene_versions
                    WHERE branch_scene_id = ? AND version = ?
                    """,
                    (scene["id"], scene["current_version"]),
                ).fetchone()
            if selected is None:
                continue
            connection.execute(
                """
                INSERT OR IGNORE INTO branch_chapter_version_scenes(
                    branch_chapter_version_id, branch_scene_id,
                    branch_scene_version_id, scene_index
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    chapter_version["id"],
                    scene["id"],
                    selected["id"],
                    scene["scene_index"] or fallback_index,
                ),
            )


def _migrate_to_v37(connection: sqlite3.Connection) -> None:
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            DROP TABLE IF EXISTS plot_generation_runs_v37;
            CREATE TABLE plot_generation_runs_v37 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                branch_id INTEGER,
                operation_type TEXT NOT NULL DEFAULT 'plot_generation'
                    CHECK (operation_type = 'plot_generation'),
                generation_mode TEXT NOT NULL CHECK (generation_mode IN (
                    'bounded_insert', 'open_continuation', 'fork', 'fork_and_rejoin'
                )),
                output_topology TEXT NOT NULL CHECK (output_topology IN ('in_place', 'branch')),
                start_anchor_json TEXT NOT NULL,
                return_anchor_json TEXT,
                start_state_json TEXT NOT NULL DEFAULT '{}',
                required_return_state_json TEXT NOT NULL DEFAULT '{}',
                target_skeleton_json TEXT NOT NULL,
                context_json TEXT NOT NULL DEFAULT '{}',
                seams_json TEXT NOT NULL DEFAULT '[]',
                issues_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'awaiting_skeleton' CHECK (status IN (
                    'awaiting_skeleton', 'planning_blocked', 'awaiting_seams',
                    'ready', 'generating', 'repair_required', 'completed',
                    'failed', 'cancelled'
                )),
                stage TEXT NOT NULL DEFAULT 'start',
                user_direction TEXT NOT NULL DEFAULT '',
                selected_character_ids_json TEXT NOT NULL DEFAULT '[]',
                selected_material_ids_json TEXT NOT NULL DEFAULT '[]',
                style_profile_id INTEGER,
                scene_plan_json TEXT NOT NULL DEFAULT '{}',
                fact_ledger_json TEXT NOT NULL DEFAULT '{}',
                result_json TEXT NOT NULL DEFAULT '{}',
                range_operation TEXT NOT NULL DEFAULT 'insert_between'
                    CHECK (range_operation IN ('insert_between', 'replace_range')),
                generated_progress_json TEXT NOT NULL DEFAULT '{"chapters":[],"scenes":[]}',
                next_scene_cursor INTEGER NOT NULL DEFAULT 0,
                generation_attempt INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE SET NULL
            );

            INSERT INTO plot_generation_runs_v37 (
                id, project_id, branch_id, operation_type, generation_mode,
                output_topology, start_anchor_json, return_anchor_json,
                start_state_json, required_return_state_json, target_skeleton_json,
                context_json, seams_json, issues_json, status, stage,
                user_direction, selected_character_ids_json,
                selected_material_ids_json, style_profile_id, scene_plan_json,
                fact_ledger_json, result_json, range_operation, created_at, updated_at
            )
            SELECT
                id, project_id, branch_id, operation_type, generation_mode,
                output_topology, start_anchor_json, return_anchor_json,
                start_state_json, required_return_state_json, target_skeleton_json,
                context_json, seams_json, issues_json,
                CASE
                    WHEN status = 'blocked' AND stage = 'confirm_target_skeleton'
                        THEN 'planning_blocked'
                    WHEN status = 'blocked' AND stage = 'consistency_check'
                        THEN 'repair_required'
                    WHEN status = 'blocked' THEN 'failed'
                    ELSE status
                END,
                stage, user_direction, selected_character_ids_json,
                selected_material_ids_json, style_profile_id, scene_plan_json,
                fact_ledger_json, result_json, range_operation, created_at, updated_at
            FROM plot_generation_runs;

            DROP TABLE plot_generation_runs;
            ALTER TABLE plot_generation_runs_v37 RENAME TO plot_generation_runs;
            CREATE INDEX IF NOT EXISTS idx_plot_generation_project_status
                ON plot_generation_runs(project_id, status);
            """
        )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_to_v38(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS chapter_rewrite_versions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            chapter_id INTEGER NOT NULL,
            version INTEGER NOT NULL,
            parent_version_id INTEGER,
            source_kind TEXT NOT NULL DEFAULT 'ai',
            source_operation TEXT NOT NULL CHECK (source_operation IN (
                'plot_generation', 'prose_rewrite', 'canon_change',
                'manual', 'migration', 'restore'
            )),
            source_run_id INTEGER,
            source_base_kind TEXT NOT NULL CHECK (source_base_kind IN (
                'original', 'rewrite_version'
            )),
            source_base_version_id INTEGER,
            source_hash TEXT NOT NULL,
            rewritten_text TEXT NOT NULL,
            content_hash TEXT NOT NULL,
            facts_before_json TEXT NOT NULL DEFAULT '{}',
            facts_after_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (chapter_id, version),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (parent_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL,
            FOREIGN KEY (source_base_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_chapter_rewrite_versions_chapter
            ON chapter_rewrite_versions(chapter_id, version DESC);
        CREATE INDEX IF NOT EXISTS idx_chapter_rewrite_versions_run
            ON chapter_rewrite_versions(source_operation, source_run_id);
        """
    )
    rows = connection.execute(
        """
        SELECT c.id AS chapter_id, c.project_id, c.original_text, c.rewritten_text,
               cr.created_at
        FROM chapters c
        LEFT JOIN chapter_rewrites cr ON cr.chapter_id = c.id
        WHERE c.rewritten_text IS NOT NULL AND TRIM(c.rewritten_text) <> ''
        """
    ).fetchall()
    for row in rows:
        existing = connection.execute(
            "SELECT id FROM chapter_rewrite_versions WHERE chapter_id = ? LIMIT 1",
            (row["chapter_id"],),
        ).fetchone()
        if existing is not None:
            continue
        source_text = str(row["original_text"])
        rewritten_text = str(row["rewritten_text"])
        connection.execute(
            """
            INSERT INTO chapter_rewrite_versions(
                project_id, chapter_id, version, source_kind, source_operation,
                source_base_kind, source_hash, rewritten_text, content_hash,
                facts_before_json, facts_after_json, created_at
            ) VALUES (?, ?, 1, 'legacy', 'migration', 'original', ?, ?, ?, '{}', '{}', COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                row["project_id"],
                row["chapter_id"],
                hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
                rewritten_text,
                hashlib.sha256(rewritten_text.encode("utf-8")).hexdigest(),
                row["created_at"],
            ),
        )


def _migrate_to_v39(connection: sqlite3.Connection) -> None:
    _add_column_if_missing(
        connection, "chapter_rewrites", "current_version_id", "current_version_id INTEGER"
    )
    _add_column_if_missing(
        connection, "chapter_rewrites", "current_version", "current_version INTEGER NOT NULL DEFAULT 0"
    )
    _add_column_if_missing(
        connection, "branch_chapter_versions", "fact_chain_status",
        "fact_chain_status TEXT NOT NULL DEFAULT 'consistent' CHECK (fact_chain_status IN ('consistent', 'needs_recompute'))",
    )
    _add_column_if_missing(
        connection, "branch_scene_versions", "source_operation",
        "source_operation TEXT NOT NULL DEFAULT 'generation'",
    )
    _add_column_if_missing(
        connection, "branch_chapter_versions", "source_operation",
        "source_operation TEXT NOT NULL DEFAULT 'generation'",
    )
    for name, definition in (
        ("source_chapter_id", "source_chapter_id INTEGER"),
        ("source_base_kind", "source_base_kind TEXT"),
        ("source_base_version_id", "source_base_version_id INTEGER"),
        ("source_hash", "source_hash TEXT"),
        ("source_text_snapshot", "source_text_snapshot TEXT"),
        ("require_source_head_match", "require_source_head_match INTEGER NOT NULL DEFAULT 0"),
        ("expected_source_head_version_id", "expected_source_head_version_id INTEGER"),
        ("result_version_id", "result_version_id INTEGER"),
    ):
        _add_column_if_missing(connection, "plot_generation_runs", name, definition)
    for name, definition in (
        ("source_base_kind", "source_base_kind TEXT"),
        ("source_base_version_id", "source_base_version_id INTEGER"),
        ("source_hash", "source_hash TEXT"),
        ("source_text_snapshot", "source_text_snapshot TEXT"),
        ("require_source_head_match", "require_source_head_match INTEGER NOT NULL DEFAULT 0"),
        ("expected_source_head_version_id", "expected_source_head_version_id INTEGER"),
        ("result_version_id", "result_version_id INTEGER"),
        ("generation_attempt", "generation_attempt INTEGER NOT NULL DEFAULT 0"),
    ):
        _add_column_if_missing(connection, "prose_rewrite_runs", name, definition)
    _add_column_if_missing(
        connection, "canon_change_runs", "source_snapshots_json",
        "source_snapshots_json TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        connection, "canon_change_patches", "source_base_version_id",
        "source_base_version_id INTEGER",
    )
    _add_column_if_missing(
        connection, "canon_change_patches", "result_version_id",
        "result_version_id INTEGER",
    )
    connection.execute(
        """
        UPDATE chapter_rewrites
        SET current_version_id = (
                SELECT v.id FROM chapter_rewrite_versions v
                WHERE v.chapter_id = chapter_rewrites.chapter_id
                ORDER BY v.version DESC LIMIT 1
            ),
            current_version = COALESCE((
                SELECT v.version FROM chapter_rewrite_versions v
                WHERE v.chapter_id = chapter_rewrites.chapter_id
                ORDER BY v.version DESC LIMIT 1
            ), 0)
        """
    )
    connection.commit()
    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            DROP TABLE IF EXISTS prose_rewrite_runs_v39;
            CREATE TABLE prose_rewrite_runs_v39 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                chapter_id INTEGER NOT NULL,
                operation_type TEXT NOT NULL DEFAULT 'prose_rewrite' CHECK (operation_type = 'prose_rewrite'),
                source_skeleton_json TEXT NOT NULL,
                preservation_policy_json TEXT NOT NULL,
                target_skeleton_json TEXT NOT NULL,
                rewrite_plan_json TEXT NOT NULL DEFAULT '{}',
                rewritten_text TEXT,
                issues_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN (
                    'planned', 'generating', 'blocked', 'completed', 'failed', 'cancelled'
                )),
                source_base_kind TEXT,
                source_base_version_id INTEGER,
                source_hash TEXT,
                source_text_snapshot TEXT,
                require_source_head_match INTEGER NOT NULL DEFAULT 0,
                expected_source_head_version_id INTEGER,
                result_version_id INTEGER,
                generation_attempt INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            );
            INSERT INTO prose_rewrite_runs_v39
            SELECT id, project_id, chapter_id, operation_type, source_skeleton_json,
                   preservation_policy_json, target_skeleton_json, rewrite_plan_json,
                   rewritten_text, issues_json, status, source_base_kind,
                   source_base_version_id, source_hash, source_text_snapshot,
                   require_source_head_match, expected_source_head_version_id,
                   result_version_id, generation_attempt,
                   created_at, updated_at
            FROM prose_rewrite_runs;
            DROP TABLE prose_rewrite_runs;
            ALTER TABLE prose_rewrite_runs_v39 RENAME TO prose_rewrite_runs;

            DROP TABLE IF EXISTS canon_change_runs_v39;
            CREATE TABLE canon_change_runs_v39 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                branch_id INTEGER,
                operation_type TEXT NOT NULL DEFAULT 'canon_change' CHECK (operation_type = 'canon_change'),
                old_fact_json TEXT NOT NULL,
                new_fact_json TEXT NOT NULL,
                effective_order INTEGER NOT NULL DEFAULT 0,
                fact_ledger_json TEXT NOT NULL DEFAULT '{}',
                consistency_issues_json TEXT NOT NULL DEFAULT '[]',
                status TEXT NOT NULL DEFAULT 'reviewing' CHECK (status IN (
                    'scanning', 'reviewing', 'blocked', 'ready_to_apply',
                    'applying', 'applied', 'failed', 'cancelled'
                )),
                source_snapshots_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (branch_id) REFERENCES story_branches(id) ON DELETE CASCADE
            );
            INSERT INTO canon_change_runs_v39
            SELECT id, project_id, branch_id, operation_type, old_fact_json,
                   new_fact_json, effective_order, fact_ledger_json,
                   consistency_issues_json,
                   CASE WHEN status = 'scanned' THEN 'reviewing' ELSE status END,
                   source_snapshots_json, created_at, updated_at
            FROM canon_change_runs;
            DROP TABLE canon_change_runs;
            ALTER TABLE canon_change_runs_v39 RENAME TO canon_change_runs;
            """
        )
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_to_v40(connection: sqlite3.Connection) -> None:
    """Add immutable rewrite-local semantic spans and repair legacy facts."""
    if not _table_exists(connection, "chapter_rewrite_versions"):
        return
    _add_column_if_missing(
        connection,
        "chapter_rewrite_versions",
        "fact_chain_status",
        "fact_chain_status TEXT NOT NULL DEFAULT 'needs_recompute' "
        "CHECK (fact_chain_status IN ('consistent', 'needs_recompute'))",
    )
    if _table_exists(connection, "story_skeletons"):
        _add_column_if_missing(
            connection,
            "story_skeletons",
            "source_rewrite_version_id",
            "source_rewrite_version_id INTEGER",
        )
    for table_name in ("plot_generation_runs", "prose_rewrite_runs"):
        if _table_exists(connection, table_name):
            _add_column_if_missing(
                connection, table_name, "source_map_hash", "source_map_hash TEXT"
            )
    for name, definition in (
        ("resolved_start_anchor_json", "resolved_start_anchor_json TEXT"),
        ("resolved_return_anchor_json", "resolved_return_anchor_json TEXT"),
    ):
        if _table_exists(connection, "plot_generation_runs"):
            _add_column_if_missing(connection, "plot_generation_runs", name, definition)
    if _table_exists(connection, "canon_change_runs"):
        _add_column_if_missing(
            connection,
            "canon_change_runs",
            "source_map_hashes_json",
            "source_map_hashes_json TEXT NOT NULL DEFAULT '{}'",
        )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS chapter_rewrite_version_segments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            rewrite_version_id INTEGER NOT NULL,
            segment_kind TEXT NOT NULL CHECK (
                segment_kind IN ('scene', 'event_node', 'generated_event')
            ),
            source_scene_id INTEGER,
            skeleton_version_id INTEGER,
            node_id TEXT,
            segment_index INTEGER NOT NULL,
            start_offset INTEGER NOT NULL CHECK (start_offset >= 0),
            end_offset INTEGER NOT NULL CHECK (end_offset >= start_offset),
            mapping_method TEXT NOT NULL CHECK (
                mapping_method IN ('identity', 'shifted', 'structural', 'semantic')
            ),
            confidence REAL NOT NULL DEFAULT 1.0 CHECK (
                confidence >= 0.0 AND confidence <= 1.0
            ),
            needs_remap INTEGER NOT NULL DEFAULT 0 CHECK (needs_remap IN (0, 1)),
            state_method TEXT NOT NULL DEFAULT 'explicit',
            state_before_json TEXT NOT NULL DEFAULT '{}',
            state_after_json TEXT NOT NULL DEFAULT '{}',
            facts_before_json TEXT NOT NULL DEFAULT '{}',
            facts_after_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (rewrite_version_id, segment_kind, segment_index),
            FOREIGN KEY (rewrite_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE CASCADE,
            FOREIGN KEY (source_scene_id) REFERENCES scenes(id) ON DELETE SET NULL,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE SET NULL
        );
        CREATE INDEX IF NOT EXISTS idx_rewrite_segments_version
            ON chapter_rewrite_version_segments(rewrite_version_id);
        CREATE INDEX IF NOT EXISTS idx_rewrite_segments_version_kind
            ON chapter_rewrite_version_segments(rewrite_version_id, segment_kind, segment_index);
        CREATE INDEX IF NOT EXISTS idx_rewrite_segments_scene
            ON chapter_rewrite_version_segments(source_scene_id, rewrite_version_id);
        CREATE INDEX IF NOT EXISTS idx_rewrite_segments_node
            ON chapter_rewrite_version_segments(skeleton_version_id, node_id, rewrite_version_id);

        CREATE TABLE IF NOT EXISTS rewrite_version_skeletons (
            rewrite_version_id INTEGER NOT NULL,
            skeleton_version_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (rewrite_version_id, skeleton_version_id),
            FOREIGN KEY (rewrite_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE CASCADE,
            FOREIGN KEY (skeleton_version_id) REFERENCES story_skeleton_versions(id) ON DELETE CASCADE
        );
        """
    )
    # v38 intentionally stored empty fact snapshots.  v40 performs a
    # best-effort compensation before immutability triggers are installed.
    versions = connection.execute(
        """
        SELECT v.id, v.chapter_id, v.rewritten_text, v.source_operation,
               v.facts_before_json, v.facts_after_json, c.original_text
        FROM chapter_rewrite_versions v
        JOIN chapters c ON c.id = v.chapter_id
        ORDER BY v.id
        """
    ).fetchall()
    for version in versions:
        scene_rows = connection.execute(
            """
            SELECT s.id, s.scene_index, s.original_start_offset,
                   s.original_end_offset, l.facts_json
            FROM scenes s
            LEFT JOIN scene_fact_ledgers l ON l.id = (
                SELECT l2.id FROM scene_fact_ledgers l2
                WHERE l2.scene_id = s.id ORDER BY l2.ledger_version DESC LIMIT 1
            )
            WHERE s.chapter_id = ? AND s.deleted_at IS NULL
            ORDER BY s.scene_index, s.id
            """,
            (version["chapter_id"],),
        ).fetchall()
        ledgers = [_safe_json_object(row["facts_json"]) for row in scene_rows]
        before = _safe_json_object(version["facts_before_json"])
        after = _safe_json_object(version["facts_after_json"])
        reliable_before = bool(before)
        if not before and ledgers:
            required = ledgers[0].get("required_start_state")
            if isinstance(required, dict) and required:
                before = required
                reliable_before = True
        if not after and ledgers:
            after = ledgers[-1]
        status = "consistent" if reliable_before and bool(after) else "needs_recompute"
        connection.execute(
            """
            UPDATE chapter_rewrite_versions
            SET facts_before_json = ?, facts_after_json = ?, fact_chain_status = ?
            WHERE id = ?
            """,
            (
                json.dumps(before, ensure_ascii=False),
                json.dumps(after, ensure_ascii=False),
                status,
                version["id"],
            ),
        )
        if str(version["rewritten_text"]) != str(version["original_text"]):
            continue
        previous: dict[str, object] = before
        for index, row in enumerate(scene_rows):
            current = ledgers[index] if index < len(ledgers) else {}
            connection.execute(
                """
                INSERT OR IGNORE INTO chapter_rewrite_version_segments(
                    rewrite_version_id, segment_kind, source_scene_id,
                    segment_index, start_offset, end_offset, mapping_method,
                    confidence, state_before_json, state_after_json,
                    facts_before_json, facts_after_json
                ) VALUES (?, 'scene', ?, ?, ?, ?, 'identity', 1.0, ?, ?, ?, ?)
                """,
                (
                    version["id"], row["id"], index,
                    row["original_start_offset"], row["original_end_offset"],
                    json.dumps(previous, ensure_ascii=False),
                    json.dumps(current, ensure_ascii=False),
                    json.dumps(previous, ensure_ascii=False),
                    json.dumps(current, ensure_ascii=False),
                ),
            )
            previous = current

    connection.executescript(
        """
        CREATE TRIGGER IF NOT EXISTS prevent_chapter_rewrite_version_update
        BEFORE UPDATE ON chapter_rewrite_versions
        BEGIN
            SELECT RAISE(ABORT, 'chapter rewrite versions are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS prevent_chapter_rewrite_version_delete
        BEFORE DELETE ON chapter_rewrite_versions
        BEGIN
            SELECT RAISE(ABORT, 'chapter rewrite versions are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS prevent_rewrite_segment_update
        BEFORE UPDATE ON chapter_rewrite_version_segments
        BEGIN
            SELECT RAISE(ABORT, 'rewrite version semantic maps are immutable');
        END;
        CREATE TRIGGER IF NOT EXISTS prevent_rewrite_segment_delete
        BEFORE DELETE ON chapter_rewrite_version_segments
        BEGIN
            SELECT RAISE(ABORT, 'rewrite version semantic maps are immutable');
        END;
        """
    )


def _ensure_chapter_workflow_state_schema(connection: sqlite3.Connection) -> None:
    scene_foreign_key = (
        "FOREIGN KEY (active_scene_id) REFERENCES scenes(id) ON DELETE SET NULL"
        if _table_exists(connection, "scenes")
        else ""
    )
    connection.execute(
        f"""
        CREATE TABLE IF NOT EXISTS chapter_workflow_state (
            chapter_id INTEGER PRIMARY KEY,
            active_scene_id INTEGER,
            current_stage TEXT NOT NULL DEFAULT 'not_started' CHECK (current_stage IN (
                'not_started', 'preanalysis', 'direction', 'special_analysis',
                'target_design', 'writing', 'review', 'confirmed'
            )),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
            {',' if scene_foreign_key else ''} {scene_foreign_key}
        )
        """
    )
    _validate_chapter_workflow_state_columns(connection)
    connection.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_chapter_workflow_stage
            ON chapter_workflow_state(current_stage, updated_at)
        """
    )
    connection.execute(
        """
        INSERT OR IGNORE INTO chapter_workflow_state (chapter_id)
        SELECT id FROM chapters
        """
    )


def _validate_chapter_workflow_state_columns(connection: sqlite3.Connection) -> None:
    columns = {
        str(row[1]): {"not_null": int(row[3]), "pk": int(row[5])}
        for row in connection.execute("PRAGMA table_info(chapter_workflow_state)").fetchall()
    }
    expected_columns = {"chapter_id", "active_scene_id", "current_stage", "updated_at"}
    if set(columns) != expected_columns:
        raise RuntimeError("chapter_workflow_state has an incompatible column layout")
    if columns["chapter_id"]["pk"] != 1:
        raise RuntimeError("chapter_workflow_state.chapter_id must be the primary key")
    if columns["current_stage"]["not_null"] != 1 or columns["updated_at"]["not_null"] != 1:
        raise RuntimeError("chapter_workflow_state required columns must be NOT NULL")


def _validate_chapter_workflow_state_schema(connection: sqlite3.Connection) -> None:
    indexes = {
        str(row[1])
        for row in connection.execute("PRAGMA index_list(chapter_workflow_state)").fetchall()
    }
    if "idx_chapter_workflow_stage" not in indexes:
        raise RuntimeError("chapter_workflow_state workflow index is missing")


def _migrate_to_v41(connection: sqlite3.Connection) -> None:
    """Persist chapter-level progress for the chapter-centric creative workspace."""
    _ensure_chapter_workflow_state_schema(connection)


def _migrate_to_v42(connection: sqlite3.Connection) -> None:
    """Add lightweight scene preanalysis and per-scene creative intent."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scene_preanalyses (
            scene_id INTEGER PRIMARY KEY,
            summary TEXT NOT NULL DEFAULT '',
            characters_json TEXT NOT NULL DEFAULT '[]',
            location TEXT NOT NULL DEFAULT '',
            time_text TEXT NOT NULL DEFAULT '',
            scene_type TEXT NOT NULL DEFAULT '',
            basic_events_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'stale')),
            user_edited INTEGER NOT NULL DEFAULT 0 CHECK (user_edited IN (0, 1)),
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS creative_intents (
            scene_id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL CHECK (strategy IN (
                'faithful', 'plot_adjust', 'expansion', 'reimagine'
            )),
            user_instruction TEXT NOT NULL DEFAULT '',
            selected_character_ids_json TEXT NOT NULL DEFAULT '[]',
            selected_plot_material_ids_json TEXT NOT NULL DEFAULT '[]',
            selected_scene_material_ids_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_creative_intents_strategy
            ON creative_intents(strategy, updated_at);
        """
    )


def _migrate_to_v43(connection: sqlite3.Connection) -> None:
    """Introduce simple master, workflow-task, and common-task prompts."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS prompt_definitions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            kind TEXT NOT NULL CHECK (kind IN ('master', 'workflow_task', 'common_task')),
            workflow_key TEXT,
            task_key TEXT,
            content TEXT NOT NULL DEFAULT '',
            input_description TEXT NOT NULL DEFAULT '',
            is_default INTEGER NOT NULL DEFAULT 0 CHECK (is_default IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_prompt_definition_default_master
            ON prompt_definitions(kind)
            WHERE kind = 'master' AND is_default = 1 AND deleted_at IS NULL;
        CREATE INDEX IF NOT EXISTS idx_prompt_definition_lookup
            ON prompt_definitions(kind, workflow_key, task_key, is_default, updated_at);

        CREATE TABLE IF NOT EXISTS project_master_prompts (
            project_id INTEGER PRIMARY KEY,
            content TEXT NOT NULL DEFAULT '',
            source_prompt_definition_id INTEGER,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_prompt_definition_id) REFERENCES prompt_definitions(id) ON DELETE SET NULL
        );

        INSERT INTO prompt_definitions (
            name, description, kind, content, input_description, is_default
        ) SELECT
            '默认总提示词', '适用于普通小说创作的工程级规则', 'master',
            '保持事实一致、人物行为可信、语言自然；遵守用户本次明确要求。',
            '所有新工作流任务都会携带此文本。', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM prompt_definitions WHERE kind = 'master' AND deleted_at IS NULL
        );

        INSERT INTO prompt_definitions (
            name, description, kind, task_key, content, input_description, is_default
        ) SELECT
            '场景预分析', '轻量识别场景基础信息', 'common_task', 'scene_preanalysis',
            '只判断场景摘要、人物、地点、时间、场景类型和基础事件；不要生成改写方案。',
            '当前场景完整 Source 文本及其原文范围。', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM prompt_definitions
            WHERE kind = 'common_task' AND task_key = 'scene_preanalysis' AND deleted_at IS NULL
        );

        INSERT INTO prompt_definitions (
            name, description, kind, workflow_key, task_key,
            content, input_description, is_default
        ) SELECT
            '贴合原文 / 人物专项分析', '识别人物修改涉及的 Source 关联',
            'workflow_task', 'faithful', 'character_modification_analysis',
            '识别显式与隐式人物关联、动作、对白、状态、物品、空间关系和关联事件；只陈述 Source 事实与目标人物卡差异，不替用户设计修改方案。',
            '当前场景 Source、CreativeIntent、源人物和目标人物卡。', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM prompt_definitions
            WHERE kind = 'workflow_task' AND workflow_key = 'faithful'
              AND task_key = 'character_modification_analysis' AND deleted_at IS NULL
        );
        """
    )


def _migrate_to_v44(connection: sqlite3.Connection) -> None:
    """Add the faithful character-modification analysis vertical slice."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS character_modification_analyses (
            scene_id INTEGER PRIMARY KEY,
            source_character TEXT NOT NULL,
            target_character_card_id INTEGER NOT NULL,
            target_character_name TEXT NOT NULL,
            explicit_mentions_json TEXT NOT NULL DEFAULT '[]',
            implicit_references_json TEXT NOT NULL DEFAULT '[]',
            actions_json TEXT NOT NULL DEFAULT '[]',
            dialogue_json TEXT NOT NULL DEFAULT '[]',
            states_json TEXT NOT NULL DEFAULT '[]',
            objects_json TEXT NOT NULL DEFAULT '[]',
            spatial_relations_json TEXT NOT NULL DEFAULT '[]',
            related_events_json TEXT NOT NULL DEFAULT '[]',
            target_character_conflicts_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'stale')),
            user_edited INTEGER NOT NULL DEFAULT 0 CHECK (user_edited IN (0, 1)),
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (target_character_card_id) REFERENCES character_cards(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_character_modification_status
            ON character_modification_analyses(status, updated_at);
        """
    )


def _migrate_to_v45(connection: sqlite3.Connection) -> None:
    """Persist authoritative progress independently for every active scene."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scene_workflow_state (
            scene_id INTEGER PRIMARY KEY,
            current_stage TEXT NOT NULL DEFAULT 'not_started' CHECK (current_stage IN (
                'not_started', 'preanalysis', 'direction', 'special_analysis',
                'target_design', 'writing', 'review', 'confirmed'
            )),
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_scene_workflow_stage
            ON scene_workflow_state(current_stage, updated_at);
        """
    )
    if not _table_exists(connection, "scenes"):
        return
    deleted_filter = "WHERE deleted_at IS NULL" if _column_exists(connection, "scenes", "deleted_at") else ""
    connection.execute(
        f"""
        INSERT OR IGNORE INTO scene_workflow_state (scene_id, current_stage)
        SELECT id, 'not_started' FROM scenes {deleted_filter}
        """
    )
    if all(
        _table_exists(connection, name)
        for name in ("scene_preanalyses", "creative_intents", "character_modification_analyses")
    ):
        connection.execute(
            f"""
            UPDATE scene_workflow_state
            SET current_stage = CASE
                WHEN (SELECT status FROM character_modification_analyses WHERE scene_id = scene_workflow_state.scene_id) = 'confirmed'
                    THEN 'target_design'
                WHEN EXISTS (SELECT 1 FROM character_modification_analyses WHERE scene_id = scene_workflow_state.scene_id)
                    THEN 'special_analysis'
                WHEN EXISTS (SELECT 1 FROM creative_intents WHERE scene_id = scene_workflow_state.scene_id)
                    THEN 'direction'
                WHEN (SELECT status FROM scene_preanalyses WHERE scene_id = scene_workflow_state.scene_id) = 'confirmed'
                    THEN 'direction'
                WHEN EXISTS (SELECT 1 FROM scene_preanalyses WHERE scene_id = scene_workflow_state.scene_id)
                    THEN 'preanalysis'
                ELSE current_stage
            END
            WHERE scene_id IN (SELECT id FROM scenes {deleted_filter})
            """
        )
    if _table_exists(connection, "chapter_workflow_state"):
        connection.execute(
            """
            UPDATE scene_workflow_state
            SET current_stage = COALESCE((
                    SELECT chapter.current_stage
                    FROM chapter_workflow_state chapter
                    WHERE chapter.active_scene_id = scene_workflow_state.scene_id
                ), current_stage),
                updated_at = CURRENT_TIMESTAMP
            WHERE EXISTS (
                SELECT 1 FROM chapter_workflow_state chapter
                WHERE chapter.active_scene_id = scene_workflow_state.scene_id
            )
            """
        )


def _migrate_to_v46(connection: sqlite3.Connection) -> None:
    """Add strategy-shaped scene targets without changing the immutable Source layer."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS scene_targets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL UNIQUE,
            strategy TEXT NOT NULL CHECK (strategy IN (
                'faithful', 'plot_adjust', 'expansion', 'reimagine'
            )),
            user_instruction TEXT NOT NULL DEFAULT '',
            design_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'confirmed', 'stale')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            confirmed_at TEXT,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_scene_targets_status
            ON scene_targets(status, updated_at);

        INSERT INTO prompt_definitions (
            name, description, kind, workflow_key, task_key,
            content, input_description, is_default
        ) SELECT
            '贴合原文 / 目标设计', '根据已确认专项分析生成 ChangeSet 草案',
            'workflow_task', 'faithful', 'target_design',
            '把已确认的 Source 事实与差异转成明确的 preserve、adapt 或 modify 目标项。Target 回答最终要改成什么，不要生成正文或写作规划。',
            '工程总提示词、Source、已确认专项分析、CreativeIntent、目标人物卡和用户已选资源。', 1
        WHERE NOT EXISTS (
            SELECT 1 FROM prompt_definitions
            WHERE kind = 'workflow_task' AND workflow_key = 'faithful'
              AND task_key = 'target_design' AND deleted_at IS NULL
        );
        """
    )


def _migrate_to_v47(connection: sqlite3.Connection) -> None:
    """Add semantic writing plans and a Source-separated authoritative current draft."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS writing_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL UNIQUE,
            target_id INTEGER NOT NULL,
            strategy TEXT NOT NULL CHECK (strategy IN ('faithful','plot_adjust','expansion','reimagine')),
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','ready','stale')),
            coverage_json TEXT NOT NULL DEFAULT '{}',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (target_id) REFERENCES scene_targets(id) ON DELETE RESTRICT
        );
        CREATE INDEX IF NOT EXISTS idx_writing_plans_status ON writing_plans(status, updated_at);

        CREATE TABLE IF NOT EXISTS writing_plan_blocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            plan_id INTEGER NOT NULL,
            scene_id INTEGER NOT NULL,
            block_order INTEGER NOT NULL,
            title TEXT NOT NULL DEFAULT '',
            source_start_offset INTEGER NOT NULL,
            source_end_offset INTEGER NOT NULL,
            source_text_snapshot TEXT NOT NULL DEFAULT '',
            operation TEXT NOT NULL CHECK (operation IN ('preserve','transform','rewrite','insert','delete')),
            instruction TEXT NOT NULL DEFAULT '',
            preserve_constraints_json TEXT NOT NULL DEFAULT '[]',
            target_requirements_json TEXT NOT NULL DEFAULT '[]',
            resource_refs_json TEXT NOT NULL DEFAULT '[]',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(plan_id, block_order),
            FOREIGN KEY (plan_id) REFERENCES writing_plans(id) ON DELETE CASCADE,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_writing_blocks_source ON writing_plan_blocks(scene_id, source_start_offset, source_end_offset);

        CREATE TABLE IF NOT EXISTS scene_current_drafts (
            scene_id INTEGER PRIMARY KEY,
            text TEXT NOT NULL DEFAULT '',
            based_on_target_id INTEGER NOT NULL,
            based_on_plan_id INTEGER NOT NULL,
            block_spans_json TEXT NOT NULL DEFAULT '[]',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed','stale')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE,
            FOREIGN KEY (based_on_target_id) REFERENCES scene_targets(id) ON DELETE RESTRICT,
            FOREIGN KEY (based_on_plan_id) REFERENCES writing_plans(id) ON DELETE RESTRICT
        );

        INSERT INTO prompt_definitions (name, description, kind, workflow_key, task_key, content, input_description, is_default)
        SELECT '贴合原文 / 写作规划', '将 Target 映射到语义 Source blocks', 'workflow_task', 'faithful', 'writing_plan',
               '把已确认 Target 映射为语义正文区块操作。不要重复设计剧情目标；覆盖完整 Source，合理使用 preserve、transform、rewrite、insert、delete。',
               'Source、已确认 Target、专项分析、人物卡与素材。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='faithful' AND task_key='writing_plan' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions (name, description, kind, workflow_key, task_key, content, input_description, is_default)
        SELECT '贴合原文 / 局部修改', '以 Source block 为主体执行明确修改', 'workflow_task', 'faithful', 'transform_block',
               '使用 Source block 作为正文主体，只修改本 block 明确指定内容；不要写一个意义类似的新段落，只返回当前 block。',
               'Source block、Target、当前 block、人物卡和邻接上下文。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='faithful' AND task_key='transform_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions (name, description, kind, workflow_key, task_key, content, input_description, is_default)
        SELECT '贴合原文 / 区块重写', '保留事件功能与硬约束的局部重写', 'workflow_task', 'faithful', 'rewrite_block',
               '只重写当前 Source block；保留列出的剧情功能、事件、空间关系、对手行为、结果和 Target constraints。',
               'Source block、Target、preserve constraints、target requirements 和邻接上下文。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='faithful' AND task_key='rewrite_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions (name, description, kind, workflow_key, task_key, content, input_description, is_default)
        SELECT '通用 / 插入区块', '只生成 insertion content', 'common_task', NULL, 'insert_block',
               '只生成指定 insertion block，不要复述或重写相邻 Source。', 'Target、当前 block 与邻接上下文。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='common_task' AND task_key='insert_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions (name, description, kind, workflow_key, task_key, content, input_description, is_default)
        SELECT '通用 / 选中文本修改', '只修改 Current Draft 选中区间', 'common_task', NULL, 'selected_text_edit',
               '按用户要求只返回选中区间的新文本，不要返回前后文。', '选中文本、Current Draft 前后文、Target、人物与用户要求。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='common_task' AND task_key='selected_text_edit' AND deleted_at IS NULL);
        """
    )


def _migrate_to_v48(connection: sqlite3.Connection) -> None:
    """Add user-authored review marks for traditional Source-to-Draft review."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS review_marks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL,
            source_start_offset INTEGER NOT NULL,
            source_end_offset INTEGER NOT NULL,
            source_text TEXT NOT NULL DEFAULT '',
            target_start_offset INTEGER NOT NULL,
            target_end_offset INTEGER NOT NULL,
            user_note TEXT NOT NULL DEFAULT '',
            resolved INTEGER NOT NULL DEFAULT 0 CHECK (resolved IN (0,1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_review_marks_scene ON review_marks(scene_id, resolved, created_at);

        INSERT INTO prompt_definitions (name, description, kind, task_key, content, input_description, is_default)
        SELECT '通用 / 审查局部重改', '按 ReviewMark 定向处理正文区间', 'common_task', 'review_rework',
               '只返回当前选中区间的新版本。使用对应 Source、当前 Draft 区间、前后文、Target、Writing Plan 和用户备注；不要重写整场景。',
               'Source 对应区间、Current Draft 当前区间与前后文、Target、Writing Plan、用户要求或备注。', 1
        WHERE NOT EXISTS (SELECT 1 FROM prompt_definitions WHERE kind='common_task' AND task_key='review_rework' AND deleted_at IS NULL);
        """
    )


def _migrate_to_v49(connection: sqlite3.Connection) -> None:
    """Add strategy-specific analysis persistence and plot-adjustment prompts."""
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS strategy_scene_analyses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scene_id INTEGER NOT NULL UNIQUE,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust','expansion','reimagine')),
            analysis_json TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','confirmed','stale')),
            user_edited INTEGER NOT NULL DEFAULT 0 CHECK (user_edited IN (0,1)),
            confirmed_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_strategy_scene_analyses ON strategy_scene_analyses(strategy,status,updated_at);

        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 专项分析','分析当前事件结构及受影响事件','workflow_task','plot_adjust','special_analysis',
               '只分析 Source 当前剧情结构：source_events、causal_links、participants、preconditions、downstream_dependencies、affected_events。不要提出目标剧情。',
               'Source、Preanalysis、CreativeIntent 和用户资源。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='special_analysis' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 目标设计','生成结构化 TargetSkeleton','workflow_task','plot_adjust','target_design',
               '根据已确认分析与用户要求生成有序 TargetSkeleton。节点包含 id、order、summary、participants、outcome、source_relation；source_relation 只能是 inherited、modified、inserted。',
               'Source、已确认剧情分析、CreativeIntent 与 plot_skeleton 素材。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='target_design' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 写作规划','把 Source 与 TargetSkeleton 映射为统一 blocks','workflow_task','plot_adjust','writing_plan',
               '把 Source→Target mapping 表达为 preserve、rewrite、delete、insert、transform 的语义 blocks，覆盖 Source 并按目标节点插入。',
               'Source、TargetSkeleton 与专项分析。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='writing_plan' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 局部修改','执行 plot_adjust transform block','workflow_task','plot_adjust','transform_block','以 Source block 为主体执行已确认的局部变化，只返回当前 block。','当前 block、TargetSkeleton 与邻接上下文。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='transform_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 区块重写','执行 plot_adjust rewrite block','workflow_task','plot_adjust','rewrite_block','按 TargetSkeleton 重写当前 block，并保留列出的 Source constraints；只返回当前 block。','当前 Source block、目标节点与约束。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='rewrite_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '调整剧情 / 插入区块','生成 TargetSkeleton 插入节点','workflow_task','plot_adjust','insert_block','只生成指定插入节点的正文，不重写相邻 Source。','目标节点与邻接上下文。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='plot_adjust' AND task_key='insert_block' AND deleted_at IS NULL);
        """
    )


def _migrate_to_v50(connection: sqlite3.Connection) -> None:
    """Seed expansion analysis, insertion planning, generation, and seam prompts."""
    connection.executescript(
        """
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '增加剧情 / 专项分析','分析插入点前后的状态桥接','workflow_task','expansion','special_analysis',
               '提取 entry_state、exit_constraints、character_relations、active_events、unresolved_goals、available_hooks。只分析 Source，不设计新增事件。','Source、Preanalysis 与 CreativeIntent。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='expansion' AND task_key='special_analysis' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '增加剧情 / 目标设计','生成局部 InsertionBlock','workflow_task','expansion','target_design',
               '只设计 InsertionBlock：insert_after、insert_before、entry_state、new_events、exit_constraints。不要复制整份 Scene Skeleton；exit_constraints 必须明确可编辑。','Source、已确认桥接分析、用户要求与 plot_skeleton 素材。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='expansion' AND task_key='target_design' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '增加剧情 / 写作规划','把 InsertionBlock 映射到 Source 保留块','workflow_task','expansion','writing_plan',
               'Source 原有 blocks 使用 preserve，在指定位置添加一个 insert block。不要无意义 transform 或 rewrite A/B/C。','Source、InsertionBlock 与桥接约束。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='expansion' AND task_key='writing_plan' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '增加剧情 / 插入正文','只生成 Insertion content','workflow_task','expansion','insert_block',
               '只生成 new_events 对应的 insertion content，满足 entry_state 与 exit_constraints；不复述或重写相邻 Source。','InsertionBlock、前一 Current Draft 尾部与后一 Source 开头。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='expansion' AND task_key='insert_block' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '增加剧情 / 接缝修复','只修复插入内容接缝','workflow_task','expansion','seam_repair',
               '只处理 Insert 与相邻 Preserve 的接缝附近，不得重写整个场景。','接缝两侧短上下文与 exit constraints。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='expansion' AND task_key='seam_repair' AND deleted_at IS NULL);
        """
    )


def _migrate_to_v51(connection: sqlite3.Connection) -> None:
    """Seed reimagination boundary, skeleton, planning, and full-scene prompts."""
    connection.executescript(
        """
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '重新构思 / 专项分析','提取必须继承的边界条件','workflow_task','reimagine','special_analysis',
               '只提取 initial_state、required_characters、location、time、inherited_facts、required_end_state、downstream_constraints。不要设计新剧情。','Source、Preanalysis 与 CreativeIntent。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='reimagine' AND task_key='special_analysis' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '重新构思 / 目标设计','生成 BoundaryConditions + TargetSkeleton','workflow_task','reimagine','target_design',
               '保留已确认 boundary conditions，并生成有序 TargetSkeleton。明确 required end state 与 downstream constraints，不生成正文。','Source、已确认边界分析、人物卡、素材与用户要求。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='reimagine' AND task_key='target_design' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '重新构思 / 写作规划','判断 Source 保留量并规划整场生成','workflow_task','reimagine','writing_plan',
               '如果 Source 几乎不保留，返回覆盖完整 Source 的 rewrite block，使 Rusty 使用 full_scene_generation；不要伪造高 Preserve 比例。','Source、BoundaryConditions 与 TargetSkeleton。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='reimagine' AND task_key='writing_plan' AND deleted_at IS NULL);
        INSERT INTO prompt_definitions(name,description,kind,workflow_key,task_key,content,input_description,is_default)
        SELECT '重新构思 / 整场生成','按边界与目标骨架生成新场景','workflow_task','reimagine','full_scene_generation',
               '生成完整场景正文，严格满足 BoundaryConditions、TargetSkeleton、人物卡、当前上下文和总提示词。只返回正文。','Source 参考、BoundaryConditions、TargetSkeleton、Writing Plan 与当前上下文。',1
        WHERE NOT EXISTS(SELECT 1 FROM prompt_definitions WHERE kind='workflow_task' AND workflow_key='reimagine' AND task_key='full_scene_generation' AND deleted_at IS NULL);
        """
    )


def _migrate_to_v52(connection: sqlite3.Connection) -> None:
    """Repair databases whose migration ledger advanced without chapter workflow state."""
    _ensure_chapter_workflow_state_schema(connection)
    _validate_chapter_workflow_state_schema(connection)


def _migrate_to_v53(connection: sqlite3.Connection) -> None:
    """Unify character stable fields and persist ordered extraction dimensions."""
    if not (
        _table_exists(connection, "character_cards")
        and _table_exists(connection, "character_extraction_settings")
    ):
        return
    _add_column_if_missing(
        connection,
        "character_cards",
        "stable_fields_json",
        "stable_fields_json TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        connection,
        "character_extraction_settings",
        "dimensions_json",
        "dimensions_json TEXT NOT NULL DEFAULT '[]'",
    )
    default_dimensions = [
        {"id": "appearance", "label": "外貌", "instruction": "只提取原文明确描述的外貌特征。", "sort_order": 0, "enabled": True, "is_default": True},
        {"id": "relationships", "label": "人物关系", "instruction": "只记录目标人物与其他人物的明确关系。", "sort_order": 1, "enabled": True, "is_default": True},
        {"id": "personality", "label": "性格", "instruction": "基于明确行为和叙述提取性格，不进行猜测。", "sort_order": 2, "enabled": True, "is_default": True},
        {"id": "speech_style", "label": "语言风格", "instruction": "提取措辞、语气和说话习惯。", "sort_order": 3, "enabled": True, "is_default": True},
        {"id": "action_constraints", "label": "动作习惯 / 动作约束", "instruction": "提取反复出现的动作习惯与明确动作约束。", "sort_order": 4, "enabled": True, "is_default": True},
        {"id": "abilities_background", "label": "能力与背景", "instruction": "提取有文本证据的能力、经历与背景。", "sort_order": 5, "enabled": True, "is_default": True},
        {"id": "anti_ooc_rules", "label": "反 OOC 规则", "instruction": "根据明确证据总结不可违背的行为边界。", "sort_order": 6, "enabled": True, "is_default": True},
    ]
    connection.execute(
        """
        UPDATE character_extraction_settings
        SET dimensions_json = ?
        WHERE id = 1 AND (dimensions_json IS NULL OR trim(dimensions_json) IN ('', '[]'))
        """,
        (json.dumps(default_dimensions, ensure_ascii=False),),
    )
    rows = connection.execute(
        """
        SELECT id, stable_fields_json, setting_text, relationship_notes, personality,
               speech_style, action_constraints, anti_ooc_rules, profile_json,
               custom_fields_json
        FROM character_cards
        """
    ).fetchall()
    for row in rows:
        if _safe_json_list(row["stable_fields_json"]):
            continue
        profile = _safe_json_object(row["profile_json"])
        values = {
            "appearance": str(profile.get("appearance") or ""),
            "relationships": str(row["relationship_notes"] or ""),
            "personality": str(row["personality"] or ""),
            "speech_style": str(row["speech_style"] or ""),
            "action_constraints": str(row["action_constraints"] or ""),
            "abilities_background": str(row["setting_text"] or profile.get("abilities") or profile.get("background") or ""),
            "anti_ooc_rules": str(row["anti_ooc_rules"] or ""),
        }
        fields = [
            {"id": item["id"], "label": item["label"], "value": values[item["id"]], "sort_order": index}
            for index, item in enumerate(default_dimensions)
        ]
        known_ids = {field["id"] for field in fields}
        for custom in _safe_json_list(row["custom_fields_json"]):
            field_id = str(custom.get("id") or f"legacy_custom_{len(fields)}")
            if field_id in known_ids:
                field_id = f"legacy_{field_id}_{len(fields)}"
            known_ids.add(field_id)
            fields.append({
                "id": field_id,
                "label": str(custom.get("label") or field_id),
                "value": str(custom.get("value") or ""),
                "sort_order": len(fields),
            })
        connection.execute(
            "UPDATE character_cards SET stable_fields_json = ? WHERE id = ?",
            (json.dumps(fields, ensure_ascii=False), int(row["id"])),
        )


def _migrate_to_v54(connection: sqlite3.Connection) -> None:
    """Replace scene references with modular author styles without losing user data."""
    material_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'materials'"
    ).fetchone()
    material_sql = str(material_sql_row[0] or "") if material_sql_row else ""
    if "'author_style'" not in material_sql:
        tag_links = connection.execute(
            "SELECT material_id, tag_id, created_at FROM material_tag_links"
        ).fetchall()
        category_links = connection.execute(
            "SELECT material_id, category_id, created_at FROM material_category_links"
        ).fetchall()
        rows = connection.execute("SELECT * FROM materials ORDER BY id").fetchall()
        connection.execute("DROP TABLE material_tag_links")
        connection.execute("DROP TABLE material_category_links")
        connection.execute("DROP TABLE IF EXISTS materials_v54")
        connection.execute(
            """
            CREATE TABLE materials_v54 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_type TEXT NOT NULL CHECK (material_type IN ('plot_skeleton', 'author_style')),
                scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
                project_id INTEGER,
                name TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
                raw_text TEXT NOT NULL DEFAULT '',
                content_json TEXT NOT NULL DEFAULT '{}',
                analysis_status TEXT NOT NULL DEFAULT 'analyzed' CHECK (analysis_status IN ('unanalyzed', 'analyzed')),
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
                deleted_at TEXT,
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (source_material_id) REFERENCES materials_v54(id) ON DELETE SET NULL
            )
            """
        )
        for row in rows:
            old_type = str(row["material_type"])
            content = _safe_json_object(row["content_json"])
            if old_type == "scene_reference":
                content = {
                    "schema_version": 1,
                    "summary": "",
                    "dimensions": [],
                    "legacy_scene_reference": content,
                }
            connection.execute(
                """
                INSERT INTO materials_v54 (
                    id, material_type, scope, project_id, name, description, detail_level,
                    raw_text, content_json, analysis_status, source_metadata_json,
                    import_metadata_json, source_material_id, source_version, legacy_outline_id,
                    timeline_start_chapter, timeline_end_chapter, sort_order, version,
                    created_at, updated_at, deleted_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["id"], "author_style" if old_type == "scene_reference" else old_type,
                    row["scope"], row["project_id"], row["name"], row["description"],
                    row["detail_level"], row["raw_text"], json.dumps(content, ensure_ascii=False),
                    row["analysis_status"], row["source_metadata_json"], row["import_metadata_json"],
                    row["source_material_id"], row["source_version"], row["legacy_outline_id"],
                    row["timeline_start_chapter"], row["timeline_end_chapter"], row["sort_order"],
                    row["version"], row["created_at"], row["updated_at"], row["deleted_at"],
                ),
            )
        connection.execute("DROP TABLE materials")
        connection.execute("ALTER TABLE materials_v54 RENAME TO materials")
        connection.executescript(
            """
            CREATE INDEX IF NOT EXISTS idx_materials_scope_project_timeline
                ON materials(scope, project_id, timeline_start_chapter, sort_order);
            CREATE INDEX IF NOT EXISTS idx_materials_public_type
                ON materials(scope, material_type, updated_at);
            CREATE TABLE material_tag_links (
                material_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (material_id, tag_id),
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
            );
            CREATE TABLE material_category_links (
                material_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (material_id, category_id),
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
            );
            CREATE INDEX IF NOT EXISTS idx_material_category_links_category
                ON material_category_links(category_id);
            CREATE INDEX IF NOT EXISTS idx_material_category_links_material
                ON material_category_links(material_id);
            """
        )
        connection.executemany(
            "INSERT INTO material_tag_links(material_id, tag_id, created_at) VALUES (?, ?, ?)",
            [(row["material_id"], row["tag_id"], row["created_at"]) for row in tag_links],
        )
        connection.executemany(
            "INSERT INTO material_category_links(material_id, category_id, created_at) VALUES (?, ?, ?)",
            [(row["material_id"], row["category_id"], row["created_at"]) for row in category_links],
        )

    category_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'material_categories'"
    ).fetchone()
    if category_sql_row and "'author_style'" not in str(category_sql_row[0] or ""):
        links = connection.execute("SELECT * FROM material_category_links").fetchall()
        rows = connection.execute("SELECT * FROM material_categories").fetchall()
        connection.execute("DROP TABLE material_category_links")
        connection.execute("DROP INDEX IF EXISTS idx_material_categories_type_name_active")
        connection.execute("DROP INDEX IF EXISTS idx_material_categories_type_sort")
        connection.execute("ALTER TABLE material_categories RENAME TO material_categories_v53")
        connection.executescript(
            """
            CREATE TABLE material_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                material_type TEXT NOT NULL CHECK (material_type IN ('plot_skeleton', 'author_style')),
                name TEXT NOT NULL,
                normalized_name TEXT NOT NULL,
                sort_order INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                deleted_at TEXT
            );
            CREATE UNIQUE INDEX idx_material_categories_type_name_active
                ON material_categories(material_type, normalized_name) WHERE deleted_at IS NULL;
            CREATE INDEX idx_material_categories_type_sort
                ON material_categories(material_type, sort_order);
            INSERT INTO material_categories
            SELECT id, CASE material_type WHEN 'scene_reference' THEN 'author_style' ELSE material_type END,
                   name, normalized_name, sort_order, created_at, updated_at, deleted_at
            FROM material_categories_v53;
            DROP TABLE material_categories_v53;
            CREATE TABLE material_category_links (
                material_id INTEGER NOT NULL,
                category_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (material_id, category_id),
                FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
                FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
            );
            CREATE INDEX idx_material_category_links_category ON material_category_links(category_id);
            CREATE INDEX idx_material_category_links_material ON material_category_links(material_id);
            """
        )
        connection.executemany(
            "INSERT INTO material_category_links(material_id, category_id, created_at) VALUES (?, ?, ?)",
            [(row["material_id"], row["category_id"], row["created_at"]) for row in links],
        )

    filter_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'project_material_filters'"
    ).fetchone()
    if filter_sql_row and "'author_style'" not in str(filter_sql_row[0] or ""):
        connection.executescript(
            """
            DROP INDEX IF EXISTS idx_project_material_filter_tags_tag;
            ALTER TABLE project_material_filter_tags RENAME TO project_material_filter_tags_v53;
            ALTER TABLE project_material_filters RENAME TO project_material_filters_v53;
            CREATE TABLE project_material_filters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                material_type TEXT NOT NULL CHECK (material_type IN ('plot_skeleton', 'author_style')),
                match_mode TEXT NOT NULL DEFAULT 'any' CHECK (match_mode IN ('any', 'all')),
                manual_material_ids_json TEXT NOT NULL DEFAULT '[]',
                include_scene_keywords INTEGER NOT NULL DEFAULT 1,
                include_applicable_scene_tags INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (project_id, material_type),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
            );
            INSERT INTO project_material_filters
            SELECT id, project_id,
                   CASE material_type WHEN 'scene_reference' THEN 'author_style' ELSE material_type END,
                   match_mode, manual_material_ids_json, include_scene_keywords,
                   include_applicable_scene_tags, created_at, updated_at
            FROM project_material_filters_v53;
            CREATE TABLE project_material_filter_tags (
                filter_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (filter_id, tag_id),
                FOREIGN KEY (filter_id) REFERENCES project_material_filters(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
            );
            INSERT INTO project_material_filter_tags SELECT * FROM project_material_filter_tags_v53;
            DROP TABLE project_material_filter_tags_v53;
            DROP TABLE project_material_filters_v53;
            CREATE INDEX idx_project_material_filter_tags_tag ON project_material_filter_tags(tag_id);
            """
        )

    if _table_exists(connection, "material_ai_settings"):
        settings_cursor = connection.execute("SELECT * FROM material_ai_settings")
        settings_columns = [str(column[0]) for column in settings_cursor.description or ()]
        old_settings = {
            str(values["task_type"]): values
            for values in (
                dict(zip(settings_columns, row, strict=True))
                for row in settings_cursor.fetchall()
            )
        }
    else:
        old_settings = {}
    settings_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'material_ai_settings'"
    ).fetchone()
    if not settings_sql_row or "'author_style_extraction'" not in str(settings_sql_row[0] or ""):
        connection.execute("DROP TABLE IF EXISTS material_ai_settings")
        connection.execute(
            """
            CREATE TABLE material_ai_settings (
                task_type TEXT PRIMARY KEY CHECK (task_type IN ('plot_skeleton_extraction', 'author_style_extraction')),
                model_id INTEGER,
                detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
                system_prompt TEXT NOT NULL DEFAULT '',
                base_instruction TEXT NOT NULL DEFAULT '',
                dimensions_json TEXT NOT NULL DEFAULT '[]',
                extra_requirements TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
            )
            """
        )

    defaults = _material_ai_v54_defaults()
    legacy_sources = {
        "plot_skeleton_extraction": old_settings.get("narrative_to_plot_skeleton"),
        "author_style_extraction": old_settings.get("source_text_to_scene_material"),
    }
    for task_type, default in defaults.items():
        legacy = legacy_sources[task_type]
        legacy_keys = set(legacy) if legacy is not None else set()
        connection.execute(
            """
            INSERT OR IGNORE INTO material_ai_settings (
                task_type, model_id, detail_level, system_prompt, base_instruction,
                dimensions_json, extra_requirements, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
            """,
            (
                task_type,
                legacy["model_id"] if legacy is not None and "model_id" in legacy_keys else None,
                legacy["detail_level"] if legacy is not None and "detail_level" in legacy_keys else "standard",
                default["system_prompt"], default["base_instruction"],
                json.dumps(default["dimensions"], ensure_ascii=False),
                legacy["custom_requirements"] if legacy is not None and "custom_requirements" in legacy_keys else "",
                legacy["updated_at"] if legacy is not None and "updated_at" in legacy_keys else None,
            ),
        )


def _material_ai_v54_defaults() -> dict[str, dict[str, object]]:
    plot_names = [
        ("overall-structure", "整体剧情结构", "分析这段剧情整体要完成什么叙事目标，抽象出开始状态、发展过程、核心变化和结束状态，不保留没有复用价值的具体人名和专有名词。"),
        ("time-progression", "时间与阶段推进", "分析剧情按什么阶段推进，各阶段之间是否发生时间变化、等待、追赶、延迟、突然中断等，整理事件的先后顺序。"),
        ("space-transition", "地点与空间转换", "分析人物在不同空间之间如何移动，以及地点改变对剧情推进产生什么作用；具体地点应尽量抽象为可复用的空间类型。"),
        ("goals-actions", "人物目标与行动", "分析各关键人物当前想完成什么、采取了什么行动，以及行动如何推动下一步剧情；具体人物身份尽量抽象成剧情角色。"),
        ("causal-chain", "事件与因果链", "按照“发生什么 → 为什么发生 → 导致什么”的方式整理关键事件，保留真正推动剧情的因果关系。"),
        ("conflict-resistance", "冲突与阻力", "分析人物目标受到什么阻碍，冲突如何出现、升级和变化，区分外部阻力、人物之间的矛盾以及内部选择冲突。"),
        ("turns-information", "转折与信息变化", "提取使剧情方向发生改变的信息、发现、失败、误判、选择、介入或意外，并说明该转折如何改变后续行动。"),
        ("climax-outcome-hook", "高潮、结果与后续钩子", "分析当前剧情的主要高潮如何形成、最终得到什么结果，以及是否留下可以继续推动后续剧情的未完成问题或新目标。"),
    ]
    style_names = [
        ("sentence-features", "句子特征", "分析长句、短句的使用倾向和组合方式；句子长度变化规律；常用标点及其作用；是否偏好断句、连续短句、长串修饰或复句；偏好直写、比喻、类比还是间接表达；常见类比对象属于器物、动物、自然、食物、动作还是抽象概念；总结具有辨识度的句法习惯，并给出代表性原文实例。"),
        ("wording", "词汇与措辞特征", "分析整体用词是朴素、华丽、口语化、书面化、古典化还是现代化；常用动词、形容词、副词和程度词的特点；是否偏爱特定类型的词汇组合；人物、动作、身体、环境等对象通常使用什么性质的词语描述；总结具有辨识度的常用表达，并给出原文实例。"),
        ("paragraph-rhythm", "段落与行文节奏", "分析段落通常长还是短；一个段落通常承担一个动作、一个信息还是多个连续事件；对白、动作、心理和环境如何穿插；高潮、过渡、平静场景时段落长度如何变化；是否习惯以短句或特定信息收尾；总结作者控制阅读节奏的方式，并给出实例。"),
        ("narration-viewpoint", "叙事方式与视角", "分析常用叙事人称和视角距离；叙述者是否解释人物行为和情绪；偏向直接告诉读者还是通过动作、语言和环境让读者判断；是否频繁进入人物内心；观察范围如何在人物、环境和事件之间移动；总结作者组织叙述信息的基本方式，并给出实例。"),
        ("information-order", "信息展开与描写顺序", "分析作者描述一个人物、地点、物品或事件时通常从哪里开始、按照什么顺序展开；是整体到局部还是局部到整体；是否存在固定的视线移动方式；重要信息是先说结论再补细节，还是逐层揭示；总结典型的信息展开路径，并给出实例。"),
        ("appearance-body", "人物外貌与身体描写", "分析作者描写人物外貌时关注哪些部位；通常从哪里开始，按照怎样的顺序描写面部、身体、衣着、动作和整体气质；偏重静态外貌还是动态姿态；身体特征如何与动作、视线和环境结合；常用哪些词汇、修辞和类比方式，并给出原文实例。"),
        ("action-behavior", "人物动作与行为描写", "分析人物行动通常描写到什么细致程度；是否拆分连续动作；是否强调身体部位、姿势、力量、速度或动作结果；动作与对白、心理、环境如何穿插；作者如何通过小动作表现人物性格和状态；总结动作描写的典型结构，并给出实例。"),
        ("dialogue", "对话风格", "分析对白长度、轮次和节奏；人物说话是否完整、简短、含蓄、直接或带有大量语气词；对白与动作、神态、心理描写如何组合；作者如何表现潜台词、停顿、打断、犹豫或情绪变化；是否经常省略说话人提示；总结对话组织规律并给出实例。"),
        ("psychology-emotion", "心理与情绪表达", "分析作者如何表现人物情绪和心理活动；偏向直接说明、内心独白、身体反应、动作表现还是环境映射；情绪通常突然释放还是逐渐积累；强烈情绪和克制情绪分别如何处理；总结常见表现路径以及用词特点，并给出实例。"),
        ("environment-atmosphere", "环境与氛围描写", "分析环境描写的信息选择、观察顺序和篇幅；重点使用视觉、声音、气味、触觉还是温度等感官；环境是单独描写还是随着人物行动逐渐呈现；如何利用环境制造压迫、暧昧、轻松、危险、孤独等氛围；总结常用描写方法并给出实例。"),
        ("scene-rhythm", "场景推进与节奏控制", "分析一个完整场景通常如何开始、发展、转折和结束；作者如何在对白、动作、描写和信息揭示之间调整速度；冲突发生前是否蓄势；高潮部分是否缩短句段或增加动作密度；缓慢场景如何避免停滞；总结典型的场景节奏模式并给出实例。"),
        ("rhetoric-signature", "修辞与作者辨识度", "综合分析反复出现、最能区别于普通写法的表达习惯，包括比喻、拟人、夸张、反差、重复、排比、留白等；分析作者特别偏爱的意象、类比对象、句式或表达动作；不要泛泛总结“细腻”“生动”等标签，而要指出具体如何实现，并给出最能体现这些规律的原文实例。"),
    ]
    shared_style_rules = (
        "必须分析具体、可操作的写作规律，不得仅使用“细腻、自然、生动、节奏明快、文笔优美”等抽象评价替代分析。\n\n"
        "需要说明作者具体“怎么写”：\n- 从哪里开始；\n- 按什么顺序展开；\n- 使用什么词；\n- 如何组织句子；\n"
        "- 如何组织段落；\n- 如何切换描写对象；\n- 如何控制信息与节奏。\n\n"
        "每个主要规律应尽可能给出能够直接体现该规律的原文实例。\n\n"
        "原文实例必须来自用户提供的文本，不得编造、不允许改写后冒充原文。如果输入文本无法支持某项结论，应明确说明样本不足，而不是补全。"
    )
    return {
        "plot_skeleton_extraction": {
            "system_prompt": "你负责从用户文本提取可复用剧情骨架，只使用输入支持的事件与因果，不补写剧情。",
            "base_instruction": "从原文抽象人物、地点和物品，保留事件顺序、因果、冲突、转折、高潮与结果；避免摘要化或空泛化。",
            "dimensions": [{"id": item[0], "name": item[1], "requirement": item[2]} for item in plot_names],
        },
        "author_style_extraction": {
            "system_prompt": "你负责分析输入文本的作者写作风格，并返回严格结构化 JSON。",
            "base_instruction": "分析输入文本的作者写作风格，以便后续写作复现其可操作的表达规律。\n\n" + shared_style_rules,
            "dimensions": [{"id": item[0], "name": item[1], "requirement": item[2]} for item in style_names],
        },
    }


def _migrate_to_v55(connection: sqlite3.Connection) -> None:
    """Remove character-card assets and make reusable materials author-style only."""
    connection.execute("PRAGMA defer_foreign_keys = ON")

    # Keep chapter character-state facts, but sever the deleted asset identity.
    if _table_exists(connection, "character_story_states"):
        connection.executescript(
            """
            DROP TABLE IF EXISTS character_story_states_v55;
            CREATE TABLE character_story_states_v55 (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                scene_id INTEGER NOT NULL,
                character_name TEXT NOT NULL,
                state_json TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (scene_id, character_name),
                FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                FOREIGN KEY (scene_id) REFERENCES scenes(id) ON DELETE CASCADE
            );
            INSERT INTO character_story_states_v55 (
                id, project_id, scene_id, character_name, state_json, created_at, updated_at
            )
            SELECT id, project_id, scene_id, character_name, state_json, created_at, updated_at
            FROM character_story_states;
            DROP TABLE character_story_states;
            ALTER TABLE character_story_states_v55 RENAME TO character_story_states;
            CREATE INDEX IF NOT EXISTS idx_character_states_project_name
                ON character_story_states(project_id, character_name, scene_id);
            """
        )

    # This table was the Character Card-specific branch of the old scene workflow.
    connection.execute("DROP TABLE IF EXISTS character_modification_analyses")
    for table in (
        "project_character_bindings",
        "character_category_links",
        "character_tag_links",
        "character_categories",
        "character_tags",
        "character_extraction_settings",
        "character_cards",
    ):
        connection.execute(f"DROP TABLE IF EXISTS {table}")

    plot_ids = [
        int(row[0])
        for row in connection.execute(
            "SELECT id FROM materials WHERE material_type = 'plot_skeleton'"
        ).fetchall()
    ]
    if plot_ids:
        placeholders = ",".join("?" for _ in plot_ids)
        for table in ("material_tag_links", "material_category_links", "rewrite_plan_materials"):
            if _table_exists(connection, table):
                connection.execute(
                    f"DELETE FROM {table} WHERE material_id IN ({placeholders})",
                    plot_ids,
                )
        connection.execute(
            f"UPDATE materials SET source_material_id = NULL WHERE source_material_id IN ({placeholders})",
            plot_ids,
        )
        connection.execute(
            f"DELETE FROM materials WHERE id IN ({placeholders})",
            plot_ids,
        )

    material_links = (
        connection.execute("SELECT material_id, tag_id, created_at FROM material_tag_links").fetchall()
        if _table_exists(connection, "material_tag_links") else []
    )
    category_links = (
        connection.execute("SELECT material_id, category_id, created_at FROM material_category_links").fetchall()
        if _table_exists(connection, "material_category_links") else []
    )
    connection.execute("DROP TABLE IF EXISTS material_tag_links")
    connection.execute("DROP TABLE IF EXISTS material_category_links")
    connection.execute("DROP TABLE IF EXISTS materials_v55")
    connection.execute(
        """
        CREATE TABLE materials_v55 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT NOT NULL CHECK (material_type = 'author_style'),
            scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
            project_id INTEGER,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            raw_text TEXT NOT NULL DEFAULT '',
            content_json TEXT NOT NULL DEFAULT '{}',
            analysis_status TEXT NOT NULL DEFAULT 'analyzed' CHECK (analysis_status IN ('unanalyzed', 'analyzed')),
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
            deleted_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_material_id) REFERENCES materials_v55(id) ON DELETE SET NULL
        )
        """
    )
    connection.execute(
        """
        INSERT INTO materials_v55
        SELECT * FROM materials WHERE material_type = 'author_style'
        """
    )
    connection.execute("DROP TABLE materials")
    connection.execute("ALTER TABLE materials_v55 RENAME TO materials")
    connection.executescript(
        """
        CREATE INDEX idx_materials_scope_project_timeline
            ON materials(scope, project_id, timeline_start_chapter, sort_order);
        CREATE INDEX idx_materials_public_type
            ON materials(scope, material_type, updated_at);
        CREATE TABLE material_tag_links (
            material_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_id, tag_id),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
        );
        """
    )
    connection.executemany(
        "INSERT INTO material_tag_links(material_id, tag_id, created_at) VALUES (?, ?, ?)",
        [(row["material_id"], row["tag_id"], row["created_at"]) for row in material_links],
    )

    category_rows = (
        connection.execute(
            "SELECT * FROM material_categories WHERE material_type = 'author_style' ORDER BY id"
        ).fetchall()
        if _table_exists(connection, "material_categories") else []
    )
    connection.execute("DROP TABLE IF EXISTS material_categories")
    connection.executescript(
        """
        CREATE TABLE material_categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT NOT NULL CHECK (material_type = 'author_style'),
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX idx_material_categories_type_name_active
            ON material_categories(material_type, normalized_name) WHERE deleted_at IS NULL;
        CREATE INDEX idx_material_categories_type_sort
            ON material_categories(material_type, sort_order);
        CREATE TABLE material_category_links (
            material_id INTEGER NOT NULL,
            category_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_id, category_id),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (category_id) REFERENCES material_categories(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_material_category_links_category ON material_category_links(category_id);
        CREATE INDEX idx_material_category_links_material ON material_category_links(material_id);
        """
    )
    connection.executemany(
        """
        INSERT INTO material_categories(
            id, material_type, name, normalized_name, sort_order, created_at, updated_at, deleted_at
        ) VALUES (?, 'author_style', ?, ?, ?, ?, ?, ?)
        """,
        [
            (row["id"], row["name"], row["normalized_name"], row["sort_order"],
             row["created_at"], row["updated_at"], row["deleted_at"])
            for row in category_rows
        ],
    )
    valid_category_ids = {int(row["id"]) for row in category_rows}
    connection.executemany(
        "INSERT INTO material_category_links(material_id, category_id, created_at) VALUES (?, ?, ?)",
        [
            (row["material_id"], row["category_id"], row["created_at"])
            for row in category_links if int(row["category_id"]) in valid_category_ids
        ],
    )

    filter_rows = (
        connection.execute(
            "SELECT * FROM project_material_filters WHERE material_type = 'author_style' ORDER BY id"
        ).fetchall()
        if _table_exists(connection, "project_material_filters") else []
    )
    filter_tags = (
        connection.execute("SELECT * FROM project_material_filter_tags").fetchall()
        if _table_exists(connection, "project_material_filter_tags") else []
    )
    connection.execute("DROP TABLE IF EXISTS project_material_filter_tags")
    connection.execute("DROP TABLE IF EXISTS project_material_filters")
    connection.executescript(
        """
        CREATE TABLE project_material_filters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_id INTEGER NOT NULL,
            material_type TEXT NOT NULL CHECK (material_type = 'author_style'),
            match_mode TEXT NOT NULL DEFAULT 'any' CHECK (match_mode IN ('any', 'all')),
            manual_material_ids_json TEXT NOT NULL DEFAULT '[]',
            include_scene_keywords INTEGER NOT NULL DEFAULT 1,
            include_applicable_scene_tags INTEGER NOT NULL DEFAULT 1,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (project_id, material_type),
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
        );
        CREATE TABLE project_material_filter_tags (
            filter_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (filter_id, tag_id),
            FOREIGN KEY (filter_id) REFERENCES project_material_filters(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_project_material_filter_tags_tag ON project_material_filter_tags(tag_id);
        """
    )
    connection.executemany(
        """
        INSERT INTO project_material_filters(
            id, project_id, material_type, match_mode, manual_material_ids_json,
            include_scene_keywords, include_applicable_scene_tags, created_at, updated_at
        ) VALUES (?, ?, 'author_style', ?, ?, ?, ?, ?, ?)
        """,
        [
            (row["id"], row["project_id"], row["match_mode"], row["manual_material_ids_json"],
             row["include_scene_keywords"], row["include_applicable_scene_tags"],
             row["created_at"], row["updated_at"])
            for row in filter_rows
        ],
    )
    valid_filter_ids = {int(row["id"]) for row in filter_rows}
    connection.executemany(
        "INSERT INTO project_material_filter_tags(filter_id, tag_id, created_at) VALUES (?, ?, ?)",
        [
            (row["filter_id"], row["tag_id"], row["created_at"])
            for row in filter_tags if int(row["filter_id"]) in valid_filter_ids
        ],
    )

    author_settings = connection.execute(
        "SELECT * FROM material_ai_settings WHERE task_type = 'author_style_extraction'"
    ).fetchone()
    connection.execute("DROP TABLE IF EXISTS material_ai_settings")
    connection.execute(
        """
        CREATE TABLE material_ai_settings (
            task_type TEXT PRIMARY KEY CHECK (task_type = 'author_style_extraction'),
            model_id INTEGER,
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            system_prompt TEXT NOT NULL DEFAULT '',
            base_instruction TEXT NOT NULL DEFAULT '',
            dimensions_json TEXT NOT NULL DEFAULT '[]',
            extra_requirements TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (model_id) REFERENCES ai_models(id) ON DELETE SET NULL
        )
        """
    )
    if author_settings is not None:
        connection.execute(
            """
            INSERT INTO material_ai_settings VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            tuple(author_settings),
        )
    else:
        default = _material_ai_v54_defaults()["author_style_extraction"]
        connection.execute(
            """
            INSERT INTO material_ai_settings(
                task_type, detail_level, system_prompt, base_instruction, dimensions_json
            ) VALUES ('author_style_extraction', 'standard', ?, ?, ?)
            """,
            (default["system_prompt"], default["base_instruction"],
             json.dumps(default["dimensions"], ensure_ascii=False)),
        )


def _migrate_to_v56(connection: sqlite3.Connection) -> None:
    """Replace the scene creative workflow with a chapter-only workflow."""
    connection.execute("PRAGMA defer_foreign_keys = ON")
    for table in (
        "review_marks",
        "scene_current_drafts",
        "writing_plan_blocks",
        "writing_plans",
        "scene_targets",
        "strategy_scene_analyses",
        "creative_intents",
        "scene_preanalyses",
        "scene_workflow_state",
    ):
        connection.execute(f"DROP TABLE IF EXISTS {table}")

    connection.execute("DROP TABLE IF EXISTS chapter_workflow_state")
    connection.executescript(
        """
        CREATE TABLE chapter_workflow_state (
            chapter_id INTEGER PRIMARY KEY,
            current_stage TEXT NOT NULL DEFAULT 'not_started' CHECK (current_stage IN (
                'not_started', 'summary', 'direction', 'special_analysis',
                'style', 'writing', 'review', 'confirmed'
            )),
            source_base_kind TEXT CHECK (source_base_kind IN ('original', 'rewrite_version')),
            source_base_version_id INTEGER,
            source_hash TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (source_base_version_id) REFERENCES chapter_rewrite_versions(id) ON DELETE SET NULL
        );
        CREATE INDEX idx_chapter_workflow_stage
            ON chapter_workflow_state(current_stage, updated_at);
        INSERT INTO chapter_workflow_state(chapter_id)
            SELECT id FROM chapters;

        CREATE TABLE chapter_workflow_summaries (
            chapter_id INTEGER PRIMARY KEY,
            plot_summary TEXT NOT NULL DEFAULT '',
            main_characters_json TEXT NOT NULL DEFAULT '[]',
            key_events_json TEXT NOT NULL DEFAULT '[]',
            relationships_json TEXT NOT NULL DEFAULT '[]',
            start_state_json TEXT NOT NULL DEFAULT '{}',
            end_state_json TEXT NOT NULL DEFAULT '{}',
            important_facts_json TEXT NOT NULL DEFAULT '[]',
            open_threads_json TEXT NOT NULL DEFAULT '[]',
            source_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE chapter_creative_intents (
            chapter_id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust', 'expansion', 'reimagine')),
            user_instruction TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE chapter_special_analyses (
            chapter_id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust', 'expansion', 'reimagine')),
            outline_detail_level TEXT CHECK (outline_detail_level IN ('brief', 'detailed')),
            source_outline_json TEXT NOT NULL DEFAULT '[]',
            target_outline_json TEXT NOT NULL DEFAULT '[]',
            constraints_json TEXT NOT NULL DEFAULT '{}',
            analysis_notes_json TEXT NOT NULL DEFAULT '[]',
            source_hash TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE chapter_style_contexts (
            chapter_id INTEGER PRIMARY KEY,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust', 'expansion', 'reimagine')),
            style_mode TEXT NOT NULL CHECK (style_mode IN ('source_auto', 'selected_author_style')),
            source_scope TEXT NOT NULL CHECK (source_scope IN ('document', 'chapter')),
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

        CREATE TABLE chapter_writings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL UNIQUE,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust', 'expansion', 'reimagine')),
            writing_plan_json TEXT NOT NULL DEFAULT '[]',
            result_text TEXT NOT NULL DEFAULT '',
            created_chapter_id INTEGER,
            source_hash TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'reviewed', 'confirmed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE,
            FOREIGN KEY (created_chapter_id) REFERENCES chapters(id) ON DELETE SET NULL
        );

        CREATE TABLE chapter_reviews (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chapter_id INTEGER NOT NULL UNIQUE,
            strategy TEXT NOT NULL CHECK (strategy IN ('plot_adjust', 'expansion', 'reimagine')),
            summary TEXT NOT NULL DEFAULT '',
            metrics_json TEXT NOT NULL DEFAULT '{}',
            source_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chapter_id) REFERENCES chapters(id) ON DELETE CASCADE
        );

        CREATE TABLE chapter_review_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            review_id INTEGER NOT NULL,
            severity TEXT NOT NULL CHECK (severity IN ('info', 'warning', 'error')),
            category TEXT NOT NULL,
            start_offset INTEGER,
            end_offset INTEGER,
            description TEXT NOT NULL,
            suggested_fix TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'repaired', 'dismissed')),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (review_id) REFERENCES chapter_reviews(id) ON DELETE CASCADE
        );
        CREATE INDEX idx_chapter_review_issues
            ON chapter_review_issues(review_id, status, id);
        """
    )

    if _table_exists(connection, "prompt_definitions"):
        connection.execute(
            """
            UPDATE prompt_definitions
            SET is_default = 0, deleted_at = COALESCE(deleted_at, CURRENT_TIMESTAMP)
            WHERE kind = 'workflow_task'
               OR (kind = 'common_task' AND task_key IN (
                    'scene_preanalysis', 'insert_block', 'selected_text_edit', 'review_rework'
               ))
            """
        )
        connection.execute(
            "UPDATE prompt_definitions SET is_default = 0 WHERE kind = 'master' AND deleted_at IS NULL"
        )
        prompts = [
            ("章节创作总提示词", "章节 Workflow 的共同边界", "master", None, None,
             "只使用提供的事实与当前有效章节正文；用户明确要求优先。严格遵守输出契约和当前阶段边界，不把总结当原文，不使用角色卡或剧情骨架素材。",
             "所有章节创作阶段的共同规则。"),
            ("章节内容总结", "总结当前有效章节正文", "common_task", None, "chapter_summary",
             "只回答这一章发生了什么：剧情、人物、事件、关系、起止状态、事实和未决线索。不得提出改写方案或创作正文。",
             "当前有效章节正文。"),
            ("调整剧情 / 专项分析", "生成原始与目标大纲", "workflow_task", "plot_adjust", "special_analysis",
             "生成带稳定 ID 和来源 span 的 source_outline，以及 preserve/modify/delete/insert 的 target_outline 与 source-target mapping。未要求改变的内容默认 preserve。", "总结、原文和用户要求。"),
            ("调整剧情 / 写作规划", "形成文本级 patch 计划", "workflow_task", "plot_adjust", "writing_plan",
             "把目标大纲映射为覆盖原文的 preserve/modify/delete/insert 文本区块。preserve 必须带准确原文 span。", "原文与专项分析。"),
            ("调整剧情 / 写作", "只生成变化区块", "workflow_task", "plot_adjust", "writing",
             "只生成指定 modify 或 insert 区块正文，不复述 preserve 区块。", "单个变化区块、相邻文本、风格快照。"),
            ("调整剧情 / 审查", "审查 patch 结果", "workflow_task", "plot_adjust", "review",
             "检查 preserve 是否误改、替换是否完整、事件保留、接缝、新增无依据剧情与实际保留率。", "原文、计划和结果。"),
            ("调整剧情 / 定向修复", "只修复一个审查问题", "workflow_task", "plot_adjust", "review_repair",
             "只返回指定问题范围的替换文本，不得重写整章。", "问题、目标范围和短上下文。"),
            ("增加剧情 / 专项分析", "设计下一章大纲", "workflow_task", "expansion", "special_analysis",
             "从当前章事件与结束状态生成 source_outline，并设计新下一章 target_outline；不得修改当前章。", "总结、当前章和用户要求。"),
            ("增加剧情 / 写作", "生成新的下一章", "workflow_task", "expansion", "writing",
             "根据承接状态、目标大纲和原作风格生成完整的新下一章正文，不改写当前章。", "总结、目标大纲、事实和风格快照。"),
            ("增加剧情 / 审查", "审查新下一章", "workflow_task", "expansion", "review",
             "检查承接、人物关系与状态、事实、上一章不变、目标大纲和原作风格。", "当前章、新章节和目标。"),
            ("增加剧情 / 定向修复", "只修复一个审查问题", "workflow_task", "expansion", "review_repair",
             "只返回指定问题范围的替换文本，不得重写整章。", "问题、目标范围和短上下文。"),
            ("重新构思 / 专项分析", "锁定边界并重设计大纲", "workflow_task", "reimagine", "special_analysis",
             "提取并锁定 start_conditions、core_purpose、required_end_state、hard_constraints，再按 brief 或 detailed 粒度生成全新 target_outline。", "总结、原文、粒度和用户要求。"),
            ("重新构思 / 写作", "重建当前整章", "workflow_task", "reimagine", "writing",
             "按锁定边界、目标大纲、用户要求与选定作者风格生成完整章节正文。", "边界、目标大纲和作者风格快照。"),
            ("重新构思 / 审查", "审查整章重建", "workflow_task", "reimagine", "review",
             "检查起始条件、核心目的、结束状态、硬约束、目标大纲和选定作者风格。", "原文边界、新正文和目标。"),
            ("重新构思 / 定向修复", "只修复一个审查问题", "workflow_task", "reimagine", "review_repair",
             "只返回指定问题范围的替换文本，不得重写整章。", "问题、目标范围和短上下文。"),
        ]
        connection.executemany(
            """
            INSERT INTO prompt_definitions(
                name, description, kind, workflow_key, task_key,
                content, input_description, is_default
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            """,
            prompts,
        )


def _migrate_to_v57(connection: sqlite3.Connection) -> None:
    """Replace model review with human comparison and reduce prompts to six fixed slots."""
    connection.execute("DROP TABLE IF EXISTS chapter_review_issues")
    connection.execute("DROP TABLE IF EXISTS chapter_reviews")
    if not _table_exists(connection, "prompt_definitions"):
        return
    connection.execute(
        """UPDATE prompt_definitions SET is_default=0, deleted_at=COALESCE(deleted_at,CURRENT_TIMESTAMP)
           WHERE deleted_at IS NULL"""
    )
    prompts = [
        ("系统提示词", "所有章节创作 AI 请求最高优先级携带", "master", None, None,
         "只使用提供的事实与当前有效章节正文；用户明确要求优先。严格遵守当前任务和输出契约，不虚构未提供事实，不跨阶段擅自创作。",
         "所有章节创作 AI 请求。"),
        ("内容总结", "进入工程后的第一步", "common_task", None, "chapter_summary",
         "只总结这一章发生了什么：剧情、人物、事件、关系、起止状态、重要事实和未决线索。不得提出改写方案或创作正文。",
         "当前有效章节正文。"),
        ("调整剧情", "生成可逐条编辑的原始大纲与目标大纲", "workflow_task", "plot_adjust", "special_analysis",
         "提取带稳定 ID 和来源位置的原始大纲；根据用户要求生成目标大纲。未要求改变的节点默认保留，目标节点明确标记保留、修改、删除或新增。",
         "章节总结、当前原文和用户具体要求。"),
        ("增加剧情", "分析当前章并设计新的下一章大纲", "workflow_task", "expansion", "special_analysis",
         "提取当前章重要事件、结束状态和未决线索作为原始大纲，并设计承接它的新下一章目标大纲；不得修改当前章节。",
         "章节总结、当前原文和用户具体要求。"),
        ("重新构思", "锁定边界并重新设计当前章大纲", "workflow_task", "reimagine", "special_analysis",
         "提取起始条件、核心目的、必要结束状态和硬约束；按用户选择的粒度生成原始大纲，再设计新的目标事件链。",
         "章节总结、当前原文、大纲粒度和用户具体要求。"),
        ("写作", "三个方向共用的正文生成规则", "common_task", None, "writing",
         "严格执行已确认的目标大纲和用户要求。调整剧情只生成修改或新增区块；增加剧情生成新的下一章；重新构思生成完整当前章。保持事实边界并遵循提供的作者风格快照。",
         "原文、目标大纲、用户要求、写作计划和作者风格快照。"),
    ]
    connection.executemany(
        """INSERT INTO prompt_definitions(
               name,description,kind,workflow_key,task_key,content,input_description,is_default
           ) VALUES(?,?,?,?,?,?,?,1)""",
        prompts,
    )


def _safe_json_list(value: object) -> list[dict[str, object]]:
    try:
        parsed = json.loads(str(value or "[]"))
    except (TypeError, ValueError):
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _safe_json_object(value: object) -> dict[str, object]:
    try:
        parsed = json.loads(str(value or "{}"))
    except (TypeError, ValueError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _ensure_v14_tag_tables(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS material_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_material_tags_normalized_active
            ON material_tags(normalized_name)
            WHERE deleted_at IS NULL;
        CREATE TABLE IF NOT EXISTS material_tag_links (
            material_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (material_id, tag_id),
            FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES material_tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS character_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_character_tags_normalized_active
            ON character_tags(normalized_name)
            WHERE deleted_at IS NULL;
        CREATE TABLE IF NOT EXISTS character_tag_links (
            character_card_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (character_card_id, tag_id),
            FOREIGN KEY (character_card_id) REFERENCES character_cards(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES character_tags(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS document_tags (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            normalized_name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            deleted_at TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_document_tags_normalized_active
            ON document_tags(normalized_name)
            WHERE deleted_at IS NULL;
        CREATE TABLE IF NOT EXISTS document_tag_links (
            document_id INTEGER NOT NULL,
            tag_id INTEGER NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (document_id, tag_id),
            FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
            FOREIGN KEY (tag_id) REFERENCES document_tags(id) ON DELETE CASCADE
        );
        """
    )


def _migrate_materials_to_v14(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "materials"):
        return
    _add_column_if_missing(connection, "materials", "raw_text", "raw_text TEXT NOT NULL DEFAULT ''")
    _add_column_if_missing(
        connection,
        "materials",
        "analysis_status",
        "analysis_status TEXT NOT NULL DEFAULT 'analyzed' CHECK (analysis_status IN ('unanalyzed', 'analyzed'))",
    )
    table_sql_row = connection.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'materials'"
    ).fetchone()
    table_sql = str(table_sql_row[0] or "") if table_sql_row is not None else ""
    if "'scene_reference'" in table_sql and "'snippet'" not in table_sql and "'outline'" not in table_sql:
        _migrate_material_categories_to_tags(connection)
        return

    legacy_category_links = (
        connection.execute(
            "SELECT material_id, category_id, created_at FROM material_category_links"
        ).fetchall()
        if _table_exists(connection, "material_category_links")
        else []
    )
    old_count = int(connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
    connection.execute("DROP TABLE IF EXISTS materials_v14")
    connection.execute(
        """
        CREATE TABLE materials_v14 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            material_type TEXT NOT NULL CHECK (material_type IN ('scene_reference', 'plot_skeleton')),
            scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
            project_id INTEGER,
            name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            detail_level TEXT NOT NULL DEFAULT 'standard' CHECK (detail_level IN ('brief', 'standard', 'detailed')),
            raw_text TEXT NOT NULL DEFAULT '',
            content_json TEXT NOT NULL DEFAULT '{}',
            analysis_status TEXT NOT NULL DEFAULT 'analyzed' CHECK (analysis_status IN ('unanalyzed', 'analyzed')),
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
            deleted_at TEXT,
            FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
            FOREIGN KEY (source_material_id) REFERENCES materials(id) ON DELETE SET NULL
        )
        """
    )
    columns = {row[1] for row in connection.execute("PRAGMA table_info(materials)")}
    select_raw_text = "raw_text" if "raw_text" in columns else "''"
    select_analysis_status = (
        "CASE WHEN analysis_status IN ('unanalyzed', 'analyzed') THEN analysis_status ELSE 'analyzed' END"
        if "analysis_status" in columns
        else "'analyzed'"
    )
    connection.execute(
        f"""
        INSERT INTO materials_v14 (
            id, material_type, scope, project_id, name, description, detail_level,
            raw_text, content_json, analysis_status, source_metadata_json,
            import_metadata_json, source_material_id, source_version, legacy_outline_id,
            timeline_start_chapter, timeline_end_chapter, sort_order, version,
            created_at, updated_at, deleted_at
        )
        SELECT
            id,
            CASE material_type
                WHEN 'snippet' THEN 'scene_reference'
                WHEN 'outline' THEN 'plot_skeleton'
                ELSE 'plot_skeleton'
            END,
            scope, project_id, name, description, detail_level,
            {select_raw_text}, content_json, {select_analysis_status},
            source_metadata_json,
            CASE
                WHEN material_type = 'outline' AND instr(import_metadata_json, 'legacy_material_type') = 0
                THEN json_set(COALESCE(NULLIF(import_metadata_json, ''), '{{}}'), '$.legacy_material_type', 'outline')
                ELSE import_metadata_json
            END,
            source_material_id, source_version, legacy_outline_id,
            timeline_start_chapter, timeline_end_chapter, sort_order, version,
            created_at, updated_at, deleted_at
        FROM materials
        """
    )
    new_count = int(connection.execute("SELECT COUNT(*) FROM materials_v14").fetchone()[0])
    if old_count != new_count:
        raise RuntimeError("v14 material migration row count mismatch")
    connection.execute("DROP TABLE materials")
    connection.execute("ALTER TABLE materials_v14 RENAME TO materials")
    connection.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_materials_scope_project_timeline
            ON materials(scope, project_id, timeline_start_chapter, sort_order);
        CREATE INDEX IF NOT EXISTS idx_materials_public_type
            ON materials(scope, material_type, updated_at);
        """
    )
    _migrate_material_categories_to_tags(connection, legacy_category_links)


def _migrate_material_categories_to_tags(
    connection: sqlite3.Connection,
    link_rows: list[sqlite3.Row] | None = None,
) -> None:
    if not (_table_exists(connection, "material_categories") and _table_exists(connection, "material_category_links")):
        return
    rows = connection.execute(
        "SELECT id, trim(name) AS name, sort_order FROM material_categories WHERE deleted_at IS NULL AND trim(name) <> ''"
    ).fetchall()
    category_to_tag: dict[int, int] = {}
    for row in rows:
        name = str(row["name"])
        normalized = _normalized_tag_name(name)
        connection.execute(
            """
            INSERT INTO material_tags (name, normalized_name, sort_order)
            VALUES (?, ?, ?)
            ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
            DO UPDATE SET name = excluded.name
            """,
            (name, normalized, int(row["sort_order"])),
        )
        tag_id = connection.execute(
            "SELECT id FROM material_tags WHERE normalized_name = ? AND deleted_at IS NULL",
            (normalized,),
        ).fetchone()["id"]
        category_to_tag[int(row["id"])] = int(tag_id)
    rows_to_link = link_rows
    if rows_to_link is None:
        rows_to_link = connection.execute(
            "SELECT material_id, category_id, created_at FROM material_category_links"
        ).fetchall()
    for row in rows_to_link:
        tag_id = category_to_tag.get(int(row["category_id"]))
        if tag_id is None:
            continue
        exists = connection.execute(
            "SELECT 1 FROM materials WHERE id = ?",
            (int(row["material_id"]),),
        ).fetchone()
        if exists is not None:
            connection.execute(
                "INSERT OR IGNORE INTO material_tag_links (material_id, tag_id, created_at) VALUES (?, ?, ?)",
                (int(row["material_id"]), tag_id, row["created_at"]),
            )


def _migrate_character_cards_to_v14(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "character_cards"):
        return
    for column, definition in [
        ("identity", "identity TEXT NOT NULL DEFAULT ''"),
        ("age", "age TEXT NOT NULL DEFAULT ''"),
        ("setting_text", "setting_text TEXT NOT NULL DEFAULT ''"),
        ("custom_fields_json", "custom_fields_json TEXT NOT NULL DEFAULT '[]'"),
        ("raw_text", "raw_text TEXT NOT NULL DEFAULT ''"),
        ("analysis_status", "analysis_status TEXT NOT NULL DEFAULT 'analyzed' CHECK (analysis_status IN ('unanalyzed', 'analyzed'))"),
        ("cover_path", "cover_path TEXT"),
        ("cover_updated_at", "cover_updated_at TEXT"),
    ]:
        _add_column_if_missing(connection, "character_cards", column, definition)
    rows = connection.execute("SELECT * FROM character_cards").fetchall()
    for row in rows:
        profile = _loads_json_dict(str(row["profile_json"] or "{}"))
        identity = str(row["identity"] or "").strip() or str(profile.get("身份") or profile.get("identity") or "").strip()
        age = str(row["age"] or "").strip() or str(profile.get("年龄") or profile.get("age") or "").strip()
        setting_text = str(row["setting_text"] or "").strip() or str(row["description"] or "").strip()
        existing_fields = _loads_json_list(str(row["custom_fields_json"] or "[]"))
        seen = {str(item.get("label", "")).strip().lower() for item in existing_fields if isinstance(item, dict)}
        fields = list(existing_fields)

        def add_field(label: str, value: object) -> None:
            text = str(value or "").strip()
            key = label.strip().lower()
            if text and key and key not in seen:
                fields.append({"id": f"legacy_{len(fields)}", "label": label, "value": text, "sort_order": len(fields)})
                seen.add(key)

        add_field("人物关系", row["relationship_notes"])
        add_field("性格", row["personality"])
        add_field("语言风格", row["speech_style"])
        add_field("动作约束", row["action_constraints"])
        add_field("防 OOC", row["anti_ooc_rules"])
        for key, value in profile.items():
            if str(key) in {"身份", "年龄", "identity", "age"}:
                continue
            add_field(str(key), value)
        connection.execute(
            """
            UPDATE character_cards
            SET identity = ?, age = ?, setting_text = ?, custom_fields_json = ?
            WHERE id = ?
            """,
            (identity, age, setting_text, json.dumps(fields, ensure_ascii=False), int(row["id"])),
        )


def _migrate_document_tags_to_v14(connection: sqlite3.Connection) -> None:
    if not _table_exists(connection, "document_categories"):
        return
    category_to_tag: dict[int, int] = {}
    for row in connection.execute(
        "SELECT id, trim(name) AS name, sort_order FROM document_categories WHERE deleted_at IS NULL AND trim(name) <> ''"
    ).fetchall():
        name = str(row["name"])
        normalized = _normalized_tag_name(name)
        connection.execute(
            """
            INSERT INTO document_tags (name, normalized_name, sort_order)
            VALUES (?, ?, ?)
            ON CONFLICT(normalized_name) WHERE deleted_at IS NULL
            DO UPDATE SET name = excluded.name
            """,
            (name, normalized, int(row["sort_order"])),
        )
        tag_id = connection.execute(
            "SELECT id FROM document_tags WHERE normalized_name = ? AND deleted_at IS NULL",
            (normalized,),
        ).fetchone()["id"]
        category_to_tag[int(row["id"])] = int(tag_id)
    if not _table_exists(connection, "document_category_links"):
        return
    for row in connection.execute("SELECT document_id, category_id, created_at FROM document_category_links").fetchall():
        tag_id = category_to_tag.get(int(row["category_id"]))
        if tag_id is not None:
            connection.execute(
                "INSERT OR IGNORE INTO document_tag_links (document_id, tag_id, created_at) VALUES (?, ?, ?)",
                (int(row["document_id"]), tag_id, row["created_at"]),
            )


def _table_exists(connection: sqlite3.Connection, table_name: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone() is not None


def _normalized_tag_name(name: str) -> str:
    return " ".join(name.strip().split()).casefold()


def _loads_json_dict(text: str) -> dict[str, object]:
    try:
        value = json.loads(text)
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def _loads_json_list(text: str) -> list[dict[str, object]]:
    try:
        value = json.loads(text)
    except Exception:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []

MIGRATIONS = {
    2: _migrate_to_v2,
    3: _migrate_to_v3,
    4: _migrate_to_v4,
    5: _migrate_to_v5,
    6: _migrate_to_v6,
    7: _migrate_to_v7,
    8: _migrate_to_v8,
    9: _migrate_to_v9,
    10: _migrate_to_v10,
    11: _migrate_to_v11,
    12: _migrate_to_v12,
    13: _migrate_to_v13,
    14: _migrate_to_v14,
    15: _migrate_to_v15,
    16: _migrate_to_v16,
    17: _migrate_to_v17,
    18: _migrate_to_v18,
    19: _migrate_to_v19,
    20: _migrate_to_v20,
    21: _migrate_to_v21,
    22: _migrate_to_v22,
    23: _migrate_to_v23,
    24: _migrate_to_v24,
    25: _migrate_to_v25,
    26: _migrate_to_v26,
    27: _migrate_to_v27,
    28: _migrate_to_v28,
    29: _migrate_to_v29,
    30: _migrate_to_v30,
    31: _migrate_to_v31,
    32: _migrate_to_v32,
    33: _migrate_to_v33,
    34: _migrate_to_v34,
    35: _migrate_to_v35,
    36: _migrate_to_v36,
    37: _migrate_to_v37,
    38: _migrate_to_v38,
    39: _migrate_to_v39,
    40: _migrate_to_v40,
    41: _migrate_to_v41,
    42: _migrate_to_v42,
    43: _migrate_to_v43,
    44: _migrate_to_v44,
    45: _migrate_to_v45,
    46: _migrate_to_v46,
    47: _migrate_to_v47,
    48: _migrate_to_v48,
    49: _migrate_to_v49,
    50: _migrate_to_v50,
    51: _migrate_to_v51,
    52: _migrate_to_v52,
    53: _migrate_to_v53,
    54: _migrate_to_v54,
    55: _migrate_to_v55,
    56: _migrate_to_v56,
    57: _migrate_to_v57,
}


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create all database objects for the current schema version."""
    with connection:
        connection.executescript(SCHEMA_SQL)
        connection.executescript(DEFAULT_SEED_SQL)
        row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        applied_version = int(row[0]) if row is not None and row[0] is not None else 0
        database_row = connection.execute("PRAGMA database_list").fetchone()
        database_path = str(database_row[2]) if database_row is not None and database_row[2] else ":memory:"
        if database_path != ":memory:":
            database_path = str(Path(database_path).resolve())
        if applied_version < CURRENT_SCHEMA_VERSION:
            logger.info(
                "Migrating Rusty database path=%s schema=%d->%d",
                database_path,
                applied_version,
                CURRENT_SCHEMA_VERSION,
            )
        for version in range(applied_version + 1, CURRENT_SCHEMA_VERSION + 1):
            migration = MIGRATIONS.get(version)
            if migration is not None:
                migration(connection)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (version,),
            )
        logger.debug(
            "Rusty database initialized path=%s schema_version=%d",
            database_path,
            CURRENT_SCHEMA_VERSION,
        )


def initialize_database_file(database_path: str | Path) -> None:
    with session(database_path) as connection:
        initialize_database(connection)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Initialize a Rusty SQLite database.")
    parser.add_argument("database", type=Path, help="Path to the SQLite database file.")
    args = parser.parse_args(argv)
    initialize_database_file(args.database)
    print(f"Initialized database: {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
