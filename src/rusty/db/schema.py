from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from .connection import session


PROMPT_SLOTS = (
    ("global_system", "只使用提供的事实与当前有效章节正文；用户明确要求优先。严格遵守当前任务和输出契约，不虚构未提供事实，不跨阶段擅自创作。"),
    ("chapter_summary", "阅读当前章节原文，按提示词要求生成剧情总结、关键事件、主要人物及人物设定。提示词可以决定总结的细节、视角和侧重点。不要生成原文大纲。"),
    ("plot_adjust", "阅读当前章节原文并执行用户的调整要求。先按顺序编号总结一份用于对照的旧大纲，再生成按顺序编号且包含所需细节的新大纲。大纲使用可直接编辑的纯文本，不要返回节点对象、ID或类型字段。"),
    ("expansion", "阅读整本小说原文并执行用户要求，设计应插入当前章之后的新章节大纲。大纲按顺序编号；只返回新大纲，不要返回旧大纲或正文。"),
    ("plot_rewrite", "阅读当前章节原文并执行用户要求，生成按顺序编号的重写大纲。只返回新大纲，不要返回旧大纲或正文。"),
    ("writing", "根据程序提供的原文、新大纲及细节和作者风格生成完整小说正文。不同创作方向会提供不同组合；只使用实际提供的内容，不要输出说明、分析或JSON。"),
)

AUTHOR_STYLE_DIMENSIONS = (
    {"id": "sentence-features", "name": "句子特征", "requirement": "分析长句、短句的使用倾向和组合方式；句子长度变化规律；常用标点及其作用；是否偏好断句、连续短句、长串修饰或复句；偏好直写、比喻、类比还是间接表达；常见类比对象属于器物、动物、自然、食物、动作还是抽象概念；总结具有辨识度的句法习惯，并给出代表性原文实例。"},
    {"id": "wording", "name": "词汇与措辞特征", "requirement": "分析整体用词是朴素、华丽、口语化、书面化、古典化还是现代化；常用动词、形容词、副词和程度词的特点；是否偏爱特定类型的词汇组合；人物、动作、身体、环境等对象通常使用什么性质的词语描述；总结具有辨识度的常用表达，并给出原文实例。"},
    {"id": "paragraph-rhythm", "name": "段落与行文节奏", "requirement": "分析段落通常长还是短；一个段落通常承担一个动作、一个信息还是多个连续事件；对白、动作、心理和环境如何穿插；高潮、过渡、平静场景时段落长度如何变化；是否习惯以短句或特定信息收尾；总结作者控制阅读节奏的方式，并给出实例。"},
    {"id": "narration-viewpoint", "name": "叙事方式与视角", "requirement": "分析常用叙事人称和视角距离；叙述者是否解释人物行为和情绪；偏向直接告诉读者还是通过动作、语言和环境让读者判断；是否频繁进入人物内心；观察范围如何在人物、环境和事件之间移动；总结作者组织叙述信息的基本方式，并给出实例。"},
    {"id": "information-order", "name": "信息展开与描写顺序", "requirement": "分析作者描述一个人物、地点、物品或事件时通常从哪里开始、按照什么顺序展开；是整体到局部还是局部到整体；是否存在固定的视线移动方式；重要信息是先说结论再补细节，还是逐层揭示；总结典型的信息展开路径，并给出实例。"},
    {"id": "appearance-body", "name": "人物外貌与身体描写", "requirement": "分析作者描写人物外貌时关注哪些部位；通常从哪里开始，按照怎样的顺序描写面部、身体、衣着、动作和整体气质；偏重静态外貌还是动态姿态；身体特征如何与动作、视线和环境结合；常用哪些词汇、修辞和类比方式，并给出原文实例。"},
    {"id": "action-behavior", "name": "人物动作与行为描写", "requirement": "分析人物行动通常描写到什么细致程度；是否拆分连续动作；是否强调身体部位、姿势、力量、速度或动作结果；动作与对白、心理、环境如何穿插；作者如何通过小动作表现人物性格和状态；总结动作描写的典型结构，并给出实例。"},
    {"id": "dialogue", "name": "对话风格", "requirement": "分析对白长度、轮次和节奏；人物说话是否完整、简短、含蓄、直接或带有大量语气词；对白与动作、神态、心理描写如何组合；作者如何表现潜台词、停顿、打断、犹豫或情绪变化；是否经常省略说话人提示；总结对话组织规律并给出实例。"},
    {"id": "psychology-emotion", "name": "心理与情绪表达", "requirement": "分析作者如何表现人物情绪和心理活动；偏向直接说明、内心独白、身体反应、动作表现还是环境映射；情绪通常突然释放还是逐渐积累；强烈情绪和克制情绪分别如何处理；总结常见表现路径以及用词特点，并给出实例。"},
    {"id": "environment-atmosphere", "name": "环境与氛围描写", "requirement": "分析环境描写的信息选择、观察顺序和篇幅；重点使用视觉、声音、气味、触觉还是温度等感官；环境是单独描写还是随着人物行动逐渐呈现；如何利用环境制造压迫、暧昧、轻松、危险、孤独等氛围；总结常用描写方法并给出实例。"},
    {"id": "scene-rhythm", "name": "场景推进与节奏控制", "requirement": "分析一个完整场景通常如何开始、发展、转折和结束；作者如何在对白、动作、描写和信息揭示之间调整速度；冲突发生前是否蓄势；高潮部分是否缩短句段或增加动作密度；缓慢场景如何避免停滞；总结典型的场景节奏模式并给出实例。"},
    {"id": "rhetoric-signature", "name": "修辞与作者辨识度", "requirement": "综合分析反复出现、最能区别于普通写法的表达习惯，包括比喻、拟人、夸张、反差、重复、排比、留白等；分析作者特别偏爱的意象、类比对象、句式或表达动作；不要泛泛总结“细腻”“生动”等标签，而要指出具体如何实现，并给出最能体现这些规律的原文实例。"},
)

AUTHOR_STYLE_EXTRACTION_RULES = (
    "你负责分析输入文本的作者写作风格，并返回严格结构化 JSON。\n\n"
    "除用户配置的具体分析维度外，必须单独提取 overall_style（整体风格）。\n\n"
    "overall_style 用于综合概括样本文本在宏观层面的稳定写作规律，包括但不限于叙事方式、叙事视角、信息展开、句段节奏、对话与描写关系、情绪表达、场景转换和整体表达倾向。\n\n"
    "overall_style 必须直接基于输入样本文本总结，不能依据作者身份、生平或外部知识进行推断，不能只把各分析维度的结果机械拼接，也不能使用空泛文学评价。\n\n"
    "所有分析都必须服务于后续风格复现，并严格遵守规定的 JSON 输出结构。"
)

AUTHOR_STYLE_BASE_INSTRUCTION = (
    "分析输入文本的作者写作风格，以便后续写作复现其可操作的表达规律。\n\n"
    "首先提取整体风格（overall_style）。整体风格用于综合说明整份样本文本最稳定、最具统摄性的写作规律，应概括作者通常如何组织叙事、展开信息、安排句段节奏、处理对话与描写、表达情绪、切换场景以及控制整体信息密度。\n\n"
    "整体风格不是文学评价，也不是下面各分析维度结果的简单拼接，而是一段可以直接作为后续写作总约束使用的风格总结。\n\n"
    "随后按照用户配置的分析维度逐项分析。\n\n"
    "必须分析具体、可操作的写作规律，不得仅使用“细腻、自然、生动、节奏明快、文笔优美”等抽象评价替代分析。\n\n"
    "需要说明作者具体“怎么写”：\n- 从哪里开始；\n- 按什么顺序展开；\n- 使用什么词；\n- 如何组织句子；\n- 如何组织段落；\n- 如何切换描写对象；\n- 如何控制信息与节奏。\n\n"
    "每个主要规律应尽可能给出能够直接体现该规律的原文实例。\n\n"
    "原文实例必须来自用户提供的文本，不得编造、不允许改写后冒充原文。如果输入文本无法支持某项结论，应明确说明样本不足，而不是补全。"
)

SCHEMA_SQL = """
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
    origin_kind TEXT NOT NULL DEFAULT 'source' CHECK(origin_kind IN ('source','expansion')),
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
    raw_text TEXT NOT NULL DEFAULT '',
    content_json TEXT NOT NULL DEFAULT '{}',
    source_metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    deleted_at TEXT
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
        'not_started','summary','direction','special_analysis','style','writing','review'
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
    author_style_material_id INTEGER,
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
    result_text TEXT NOT NULL DEFAULT '',
    created_chapter_id INTEGER,
    source_hash TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft' CHECK(status IN ('draft','reviewed')),
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
    cover_palette TEXT NOT NULL DEFAULT 'slate' CHECK(cover_palette IN (
        'indigo','terracotta','jade','slate','ochre','plum','bluegray'
    )),
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

def initialize_database(connection: sqlite3.Connection) -> None:
    """Create the current application schema and seed its required defaults."""
    connection.executescript(SCHEMA_SQL)
    _seed_defaults(connection)


def _seed_defaults(connection: sqlite3.Connection) -> None:
    connection.executemany(
        "INSERT OR IGNORE INTO prompt_slots(slot_key,content) VALUES(?,?)", PROMPT_SLOTS
    )
    connection.execute(
        """INSERT OR IGNORE INTO material_ai_settings(
               task_type,detail_level,extraction_rules,base_instruction,dimensions_json,extra_requirements
           ) VALUES('author_style_extraction','standard',?,?,?,'')""",
        (
            AUTHOR_STYLE_EXTRACTION_RULES,
            AUTHOR_STYLE_BASE_INSTRUCTION,
            json.dumps(AUTHOR_STYLE_DIMENSIONS, ensure_ascii=False),
        ),
    )
    connection.execute(
        "INSERT OR IGNORE INTO chapter_workflow_state(chapter_id) SELECT id FROM chapters"
    )


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
