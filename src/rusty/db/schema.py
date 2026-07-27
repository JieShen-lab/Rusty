from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .connection import session

CURRENT_SCHEMA_VERSION = 14

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
    identity TEXT NOT NULL DEFAULT '',
    age TEXT NOT NULL DEFAULT '',
    setting_text TEXT NOT NULL DEFAULT '',
    custom_fields_json TEXT NOT NULL DEFAULT '[]',
    raw_text TEXT NOT NULL DEFAULT '',
    analysis_status TEXT NOT NULL DEFAULT 'analyzed'
        CHECK (analysis_status IN ('unanalyzed', 'analyzed')),
    cover_path TEXT,
    cover_updated_at TEXT,
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    import_metadata_json TEXT NOT NULL DEFAULT '{}',
    scope TEXT NOT NULL DEFAULT 'public' CHECK (scope IN ('public', 'project')),
    project_id INTEGER,
    source_character_card_id INTEGER,
    source_version INTEGER,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
);

CREATE TABLE IF NOT EXISTS materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_type TEXT NOT NULL CHECK (material_type IN ('scene_reference', 'plot_skeleton')),
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
    start_offset INTEGER,
    end_offset INTEGER,
    word_count INTEGER NOT NULL DEFAULT 0,
    UNIQUE (revision_id, chapter_index),
    FOREIGN KEY (document_id) REFERENCES library_documents(id) ON DELETE CASCADE,
    FOREIGN KEY (revision_id) REFERENCES library_document_revisions(id) ON DELETE CASCADE
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
        CREATE INDEX IF NOT EXISTS idx_document_categories_parent_order
            ON document_categories(parent_id, sort_order, name);
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
}


def initialize_database(connection: sqlite3.Connection) -> None:
    """Create all database objects for the current schema version."""
    with connection:
        connection.executescript(SCHEMA_SQL)
        connection.executescript(DEFAULT_SEED_SQL)
        row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        applied_version = int(row[0]) if row is not None and row[0] is not None else 0
        for version in range(applied_version + 1, CURRENT_SCHEMA_VERSION + 1):
            migration = MIGRATIONS.get(version)
            if migration is not None:
                migration(connection)
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (?)",
                (version,),
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
