from __future__ import annotations

import sqlite3

from rusty.db.schema import CURRENT_SCHEMA_VERSION, DEFAULT_SEED_SQL, MIGRATIONS, SCHEMA_SQL, initialize_database


def test_fresh_v57_has_chapter_only_workflow_and_six_fixed_prompts() -> None:
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    initialize_database(connection)

    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert CURRENT_SCHEMA_VERSION == 57
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
        ("workflow_task", "reimagine", "special_analysis"),
        ("common_task", None, "writing"),
    ]
    assert not any("角色卡" in row["content"] and row["kind"] == "workflow_task" for row in current)


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
