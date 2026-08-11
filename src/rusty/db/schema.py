from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .connection import session

CURRENT_SCHEMA_VERSION = 46

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
    FOREIGN KEY (character_card_id) REFERENCES character_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES character_categories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_character_category_links_category
    ON character_category_links(category_id);
CREATE INDEX IF NOT EXISTS idx_character_category_links_character
    ON character_category_links(character_card_id);

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


def _migrate_to_v41(connection: sqlite3.Connection) -> None:
    """Persist chapter-level progress for the chapter-centric creative workspace."""
    scene_foreign_key = (
        "FOREIGN KEY (active_scene_id) REFERENCES scenes(id) ON DELETE SET NULL"
        if _table_exists(connection, "scenes")
        else ""
    )
    connection.executescript(
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
        );
        CREATE INDEX IF NOT EXISTS idx_chapter_workflow_stage
            ON chapter_workflow_state(current_stage, updated_at);
        INSERT OR IGNORE INTO chapter_workflow_state (chapter_id)
        SELECT id FROM chapters;
        """
    )


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
