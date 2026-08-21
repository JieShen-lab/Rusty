from __future__ import annotations

import sqlite3

from rusty.db.schema import CURRENT_SCHEMA_VERSION, DEFAULT_SEED_SQL, MIGRATIONS, SCHEMA_SQL, initialize_database


def test_fresh_v61_has_program_controlled_plain_text_workflow() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)

    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert CURRENT_SCHEMA_VERSION == 61
    assert {
        "chapter_workflow_state", "chapter_workflow_summaries", "chapter_creative_intents",
        "chapter_special_analyses", "chapter_style_contexts", "chapter_writings",
    } <= tables
    assert not ({
        "scene_preanalyses", "creative_intents", "scene_workflow_state", "scene_targets",
        "writing_plans", "writing_plan_blocks", "scene_current_drafts", "review_marks",
        "strategy_scene_analyses",
    } & tables)
    assert "chapter_reviews" not in tables
    assert "chapter_review_issues" not in tables
    state_columns = {row[1] for row in connection.execute("PRAGMA table_info(chapter_workflow_state)")}
    assert "active_scene_id" not in state_columns
    assert {"source_base_kind", "source_base_version_id", "source_hash"} <= state_columns

    current = connection.execute(
        "SELECT kind,workflow_key,task_key,content FROM prompt_definitions WHERE deleted_at IS NULL ORDER BY id"
    ).fetchall()
    assert len(current) == 6
    assert [(row["kind"], row["workflow_key"], row["task_key"]) for row in current] == [
        ("master", None, None),
        ("common_task", None, "chapter_summary"),
        ("workflow_task", "plot_adjust", "special_analysis"),
        ("workflow_task", "expansion", "special_analysis"),
        ("workflow_task", "plot_rewrite", "special_analysis"),
        ("common_task", None, "writing"),
    ]
    assert not any("角色卡" in row["content"] and row["kind"] == "workflow_task" for row in current)
    summary_prompt = next(row["content"] for row in current if row["task_key"] == "chapter_summary")
    assert "主要人物" in summary_prompt
    assert "关键事件" in summary_prompt
    assert "不要生成原文大纲" in summary_prompt
    assert "重要事实" not in summary_prompt
    assert "未决线索" not in summary_prompt
    summary_columns = {row[1] for row in connection.execute("PRAGMA table_info(chapter_workflow_summaries)")}
    analysis_columns = {row[1] for row in connection.execute("PRAGMA table_info(chapter_special_analyses)")}
    assert {"plot_summary", "main_characters", "key_events"} <= summary_columns
    assert "source_outline" not in summary_columns
    assert "source_outline_json" not in summary_columns
    assert "target_outline" in analysis_columns
    assert "source_outline" in analysis_columns
    assert "outline_detail_level" not in analysis_columns
    assert "target_outline_json" not in analysis_columns
    assert "constraints_json" not in analysis_columns
    assert "analysis_notes_json" not in analysis_columns


def test_v59_to_v60_converts_structured_outlines_to_numbered_text() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, 60):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'kept')")
    connection.execute("INSERT INTO chapters(id,project_id,chapter_index,title,original_text) VALUES(1,1,1,'C1','text')")
    connection.execute(
        """INSERT INTO chapter_workflow_summaries(
               chapter_id,plot_summary,main_characters_json,key_events_json,source_outline_json,
               relationships_json,start_state_json,end_state_json,important_facts_json,open_threads_json,source_hash
           ) VALUES(1,'summary','[]','[]','[{"id":"src-1","type":"event","event":"原文事件","detail":"细节"}]','[]','{}','{}','[]','[]','hash')"""
    )
    connection.execute(
        """INSERT INTO chapter_special_analyses(
               chapter_id,strategy,outline_detail_level,target_outline_json,source_hash
           ) VALUES(1,'plot_adjust',NULL,'{"outline":[{"id":"tgt-1","event":"新事件"}]}','hash')"""
    )

    MIGRATIONS[60](connection)

    summary = connection.execute("SELECT source_outline FROM chapter_workflow_summaries WHERE chapter_id=1").fetchone()
    analysis = connection.execute("SELECT target_outline FROM chapter_special_analyses WHERE chapter_id=1").fetchone()
    assert summary["source_outline"] == "1. 原文事件"
    assert analysis["target_outline"] == "1. 新事件"
    assert "id" not in summary["source_outline"]
    assert "type" not in summary["source_outline"]


def test_v60_to_v61_moves_adjustment_outline_and_converts_summary_blocks_to_text() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, 61):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'kept')")
    connection.execute("INSERT INTO chapters(id,project_id,chapter_index,title,original_text) VALUES(1,1,1,'C1','text')")
    connection.execute(
        """INSERT INTO chapter_workflow_summaries(
               chapter_id,plot_summary,main_characters_json,key_events_json,source_outline,
               relationships_json,start_state_json,end_state_json,important_facts_json,open_threads_json,source_hash
           ) VALUES(1,'总结','["甲：主角"]','["进入房间","发现线索"]','1. 进入房间','[]','{}','{}','[]','[]','hash')"""
    )
    connection.execute(
        """INSERT INTO chapter_special_analyses(
               chapter_id,strategy,outline_detail_level,target_outline,source_hash
           ) VALUES(1,'plot_adjust',NULL,'1. 调整后的事件','hash')"""
    )

    MIGRATIONS[61](connection)

    summary = connection.execute(
        "SELECT plot_summary,main_characters,key_events FROM chapter_workflow_summaries WHERE chapter_id=1"
    ).fetchone()
    analysis = connection.execute(
        "SELECT source_outline,target_outline FROM chapter_special_analyses WHERE chapter_id=1"
    ).fetchone()
    assert tuple(summary) == ("总结", "甲：主角", "1. 进入房间\n2. 发现线索")
    assert tuple(analysis) == ("1. 进入房间", "1. 调整后的事件")


def test_v58_to_v59_preserves_workflow_and_renames_reimagine() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, 59):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'kept')")
    connection.execute("INSERT INTO chapters(id,project_id,chapter_index,title,original_text) VALUES(1,1,1,'C1','text')")
    connection.execute(
        """INSERT INTO chapter_workflow_summaries(
               chapter_id,plot_summary,main_characters_json,key_events_json,relationships_json,
               start_state_json,end_state_json,important_facts_json,open_threads_json,source_hash
           ) VALUES(1,'summary','[]','[]','[]','{}','{}','[]','[]','hash')"""
    )
    connection.execute("INSERT INTO chapter_creative_intents VALUES(1,'reimagine','rewrite','now')")
    connection.execute(
        """INSERT INTO chapter_special_analyses VALUES(
               1,'reimagine','brief','[{"id":"s1","event":"原文事件"}]',
               '[{"id":"t1","event":"新事件"}]','{"tone":"紧张"}','["保留结尾"]','hash','now'
           )"""
    )
    connection.execute(
        """INSERT INTO chapter_style_contexts VALUES(
               1,'reimagine','selected_author_style','chapter',NULL,NULL,'{}','{}','author prompt','hash','created','updated'
           )"""
    )
    connection.execute(
        """INSERT INTO chapter_writings VALUES(
               1,1,'reimagine','[]','draft',NULL,'hash','draft','created','updated'
           )"""
    )

    MIGRATIONS[59](connection)

    summary = connection.execute("SELECT source_outline_json FROM chapter_workflow_summaries WHERE chapter_id=1").fetchone()
    analysis = connection.execute("SELECT strategy,target_outline_json FROM chapter_special_analyses WHERE chapter_id=1").fetchone()
    assert '原文事件' in summary["source_outline_json"]
    assert analysis["strategy"] == "plot_rewrite"
    assert '新事件' in analysis["target_outline_json"]
    assert 'tone' in analysis["target_outline_json"]
    assert connection.execute("SELECT strategy FROM chapter_creative_intents WHERE chapter_id=1").fetchone()[0] == "plot_rewrite"
    assert connection.execute("SELECT strategy FROM chapter_style_contexts WHERE chapter_id=1").fetchone()[0] == "plot_rewrite"
    assert connection.execute("SELECT strategy FROM chapter_writings WHERE chapter_id=1").fetchone()[0] == "plot_rewrite"
    prompt = connection.execute(
        "SELECT name FROM prompt_definitions WHERE workflow_key='plot_rewrite' AND deleted_at IS NULL"
    ).fetchone()
    assert prompt is not None and "重写剧情" in prompt["name"]


def test_v55_to_v56_preserves_chapters_and_legacy_scenes_but_drops_scene_workflow() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, 56):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
        connection.execute("INSERT OR IGNORE INTO schema_migrations(version) VALUES(?)", (version,))
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'kept')")
    connection.execute(
        "INSERT INTO chapters(id,project_id,chapter_index,title,original_text) VALUES(10,1,1,'kept','source')"
    )
    connection.execute(
        """INSERT INTO scenes(id,project_id,chapter_id,scene_index,title,original_start_offset,
           original_end_offset,original_text) VALUES(100,1,10,1,'legacy',0,6,'source')"""
    )
    connection.execute("INSERT INTO scene_workflow_state(scene_id,current_stage) VALUES(100,'direction')")

    MIGRATIONS[56](connection)

    assert connection.execute("SELECT title FROM chapters WHERE id=10").fetchone()[0] == "kept"
    assert connection.execute("SELECT title FROM scenes WHERE id=100").fetchone()[0] == "legacy"
    assert connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='scene_workflow_state'"
    ).fetchone() is None
    state = connection.execute("SELECT current_stage,source_hash FROM chapter_workflow_state WHERE chapter_id=10").fetchone()
    assert tuple(state) == ("not_started", "")


def test_v56_to_v57_removes_model_review_tables_and_preserves_review_stage() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA_SQL)
    connection.executescript(DEFAULT_SEED_SQL)
    for version in range(1, 57):
        migration = MIGRATIONS.get(version)
        if migration is not None:
            migration(connection)
    connection.execute("INSERT INTO projects(id,name) VALUES(1,'kept')")
    connection.execute("INSERT INTO chapters(id,project_id,chapter_index,title,original_text) VALUES(1,1,1,'C1','text')")
    connection.execute("INSERT INTO chapter_workflow_state(chapter_id,current_stage) VALUES(1,'review')")

    MIGRATIONS[57](connection)

    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "chapter_reviews" not in tables
    assert "chapter_review_issues" not in tables
    assert connection.execute("SELECT current_stage FROM chapter_workflow_state WHERE chapter_id=1").fetchone()[0] == "review"
