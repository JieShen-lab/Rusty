from __future__ import annotations

import sqlite3
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rusty.db import initialize_database_file, session
from rusty.services.creative_workflow_service import CreativeWorkflowService, WorkflowSourceConflict
from rusty.services.material_service import MaterialService
from rusty.services.project_service import ProjectService


class WorkflowAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.strategy = "plot_adjust"
        self.patch_blocks = [
            {"operation": "preserve", "start_offset": 0, "end_offset": 4, "instruction": ""},
            {"operation": "modify", "start_offset": 4, "end_offset": 7, "instruction": "replace"},
            {"operation": "preserve", "start_offset": 7, "end_offset": 11, "instruction": ""},
        ]

    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage, payload))
        if stage == "author_style_extraction":
            return {"style_snapshot": {"voice": "source"}, "generated_guidance": "follow source"}
        raise AssertionError(stage)

    def generate_text(self, stage: str, payload: dict) -> str:
        self.calls.append((stage, payload))
        if stage == "chapter_summary":
            return "【剧情总结】\nsummary\n【关键事件】\nevent\n【主要人物与设定】\n甲：主角"
        if stage == "special_analysis":
            if self.strategy == "plot_adjust":
                return "【旧大纲】\n1. 甲进入\n2. 发现线索\n【新大纲及细节】\n1. 保留主线\n2. 改变冲突"
            if self.strategy == "expansion":
                return "1. 承接当前结尾\n2. 展开下一章"
            return "1. 重写后的剧情\n2. 从 A 推进到 B"
        if stage == "writing":
            if self.strategy == "expansion":
                return getattr(self, "expansion_text", "NEW CHAPTER")
            return "REWRITTEN" if self.strategy == "plot_rewrite" else "ADJUSTED"
        raise AssertionError(stage)


def make_project(root: Path, texts: list[str] | None = None) -> tuple[Path, list[int]]:
    database = root / "rusty.db"
    source = root / "book.txt"
    source.write_text("complete source document", encoding="utf-8")
    initialize_database_file(database)
    values = texts or ["AAA BBB CCC"]
    with session(database) as connection:
        cursor = connection.execute("INSERT INTO projects(name,source_path) VALUES('book',?)", (str(source),))
        project_id = int(cursor.lastrowid)
        ids = []
        for index, text in enumerate(values, 1):
            cursor = connection.execute(
                "INSERT INTO chapters(project_id,chapter_index,title,original_text,word_count) VALUES(?,?,?,?,?)",
                (project_id, index, f"C{index}", text, len(text)),
            )
            ids.append(int(cursor.lastrowid))
    return database, ids


def prepare(service: CreativeWorkflowService, chapter_id: int, strategy: str, *, material_id: int | None = None) -> None:
    service.ai.client.strategy = strategy
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy=strategy, user_instruction="do it")
    service.run_special_analysis(chapter_id)
    service.resolve_style(chapter_id, author_style_material_id=material_id)


def test_workflow_is_chapter_only_and_accepts_exactly_three_strategies(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)

    summary = service.run_chapter_summary(chapter_id)
    assert summary["main_characters"] == "甲：主角"
    assert summary["key_events"] == "event"
    assert "source_outline" not in summary
    assert service.get_chapter_workflow(chapter_id)["current_stage"] == "summary"
    assert not hasattr(service, "scenes")
    with pytest.raises(ValueError, match="plot_adjust"):
        service.save_chapter_direction(chapter_id, strategy="faithful", user_instruction="legacy")
    for strategy in ("plot_adjust", "expansion", "plot_rewrite"):
        saved = service.save_chapter_direction(chapter_id, strategy=strategy, user_instruction="x")
        assert saved == {"chapter_id": chapter_id, "strategy": strategy, "user_instruction": "x", "updated_at": saved["updated_at"]}
        assert "selected_character_ids" not in saved
        assert "selected_plot_material_ids" not in saved


def test_plot_adjust_packages_source_outline_and_author_style(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, chapter_id, "plot_adjust")
    analysis_payload = next(payload for stage, payload in ai.calls if stage == "special_analysis")
    assert set(analysis_payload) == {"source_text"}
    assert analysis_payload["source_text"] == "AAA BBB CCC"
    ai.calls.clear()

    writing = service.generate_chapter(chapter_id)

    assert writing["result_text"] == "ADJUSTED"
    assert writing["writing_plan"] == []
    writing_calls = [payload for stage, payload in ai.calls if stage == "writing"]
    assert len(writing_calls) == 1
    assert set(writing_calls[0]) == {"source_text", "target_outline", "author_style"}
    assert writing_calls[0]["source_text"] == "AAA BBB CCC"
    assert writing_calls[0]["target_outline"] == "1. 保留主线\n2. 改变冲突"
    with session(database) as connection:
        assert connection.execute("SELECT original_text FROM chapters WHERE id=?", (chapter_id,)).fetchone()[0] == "AAA BBB CCC"


def test_structured_outline_values_are_rejected_instead_of_displayed_as_json(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    service = CreativeWorkflowService(database, ai_client=WorkflowAI())
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy="plot_adjust", user_instruction="x")

    with pytest.raises(ValueError, match="plain text"):
        service.save_special_analysis(
            chapter_id,
            {"strategy": "plot_adjust", "source_outline": "1. 原事件", "target_outline": {"id": "tgt-1", "type": "event"}},
        )


def test_expansion_creates_new_chapter_without_changing_source_and_shifts_following_indices(tmp_path: Path) -> None:
    database, ids = make_project(tmp_path, ["FIRST", "SECOND"])
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, ids[0], "expansion")
    analysis_payload = next(payload for stage, payload in ai.calls if stage == "special_analysis")
    assert set(analysis_payload) == {"document_text"}
    assert analysis_payload["document_text"] == "complete source document"

    writing = service.generate_chapter(ids[0])
    writing_payload = next(payload for stage, payload in ai.calls if stage == "writing")
    assert set(writing_payload) == {"target_outline", "author_style"}

    assert writing["created_chapter_id"] not in ids
    with session(database) as connection:
        rows = connection.execute("SELECT id,chapter_index,title,original_text FROM chapters ORDER BY chapter_index").fetchall()
    assert [(row["chapter_index"], row["original_text"]) for row in rows] == [(1, "FIRST"), (2, "NEW CHAPTER"), (3, "SECOND")]
    assert rows[1]["title"] == "第2章"

    ai.expansion_text = "REGENERATED"
    regenerated = service.generate_chapter(ids[0], replace_existing=True)
    assert regenerated["created_chapter_id"] == writing["created_chapter_id"]
    with session(database) as connection:
        created = connection.execute(
            "SELECT original_text FROM chapters WHERE id=?", (writing["created_chapter_id"],)
        ).fetchone()
        versions = connection.execute(
            "SELECT rewritten_text FROM chapter_rewrite_versions WHERE chapter_id=?",
            (writing["created_chapter_id"],),
        ).fetchall()
    assert created["original_text"] == "NEW CHAPTER"
    assert [row["rewritten_text"] for row in versions] == ["REGENERATED"]


def test_plot_rewrite_requires_author_style_and_omits_source_from_writing_payload(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    ai.strategy = "plot_rewrite"
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy="plot_rewrite", user_instruction="new")
    analysis = service.run_special_analysis(chapter_id)
    assert analysis["target_outline"] == "1. 重写后的剧情\n2. 从 A 推进到 B"
    with pytest.raises(ValueError, match="作者风格"):
        service.resolve_style(chapter_id)

    material_id = MaterialService(database).create_material(
        material_type="author_style", scope="public", name="Style", raw_text="sample",
        content={"summary": "profile", "dimensions": []}, analysis_status="analyzed",
    )
    style = service.resolve_style(chapter_id, author_style_material_id=material_id)
    MaterialService(database).update_material(
        material_id, name="Changed", description="", detail_level="standard",
        content={"summary": "changed", "dimensions": []}, raw_text="new sample",
    )
    writing = service.generate_chapter(chapter_id)
    assert writing["result_text"] == "REWRITTEN"
    writing_payload = next(payload for stage, payload in ai.calls if stage == "writing")
    assert set(writing_payload) == {"target_outline", "author_style"}
    assert style["author_style_material_id"] == material_id
    assert style["style_snapshot"]["name"] == "Style"


def test_source_auto_reuses_author_style_settings_and_falls_back_to_chapter(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, chapter_id, "plot_adjust")
    style = service.get_style(chapter_id)
    assert style is not None
    assert style["style_mode"] == "source_auto"
    assert style["source_scope"] == "document"
    assert style["extraction_settings_snapshot"]["task_type"] == "author_style_extraction"
    extraction_payload = next(payload for stage, payload in ai.calls if stage == "author_style_extraction")
    assert "extraction_prompt" in extraction_payload
    assert "complete source document" in extraction_payload["sample_text"]


def test_plot_adjust_can_use_saved_author_style_instead_of_extracting_source(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    ai.strategy = "plot_adjust"
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy="plot_adjust", user_instruction="x")
    service.run_special_analysis(chapter_id)
    material_id = MaterialService(database).create_material(
        material_type="author_style", scope="public", name="Saved", raw_text="sample",
        content={"summary": "profile", "dimensions": []}, analysis_status="analyzed",
    )

    style = service.resolve_style(chapter_id, author_style_material_id=material_id)

    assert style["style_mode"] == "selected_author_style"
    assert style["author_style_material_id"] == material_id
    assert not any(stage == "author_style_extraction" for stage, _ in ai.calls)


def test_source_hash_conflict_is_explicit(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    service = CreativeWorkflowService(database, ai_client=WorkflowAI())
    service.run_chapter_summary(chapter_id)
    ProjectService(database).save_chapter_rewrite(chapter_id, "changed")
    with pytest.raises(WorkflowSourceConflict, match="当前章节已变化"):
        service.save_chapter_direction(chapter_id, strategy="plot_adjust", user_instruction="x")
    assert service.get_chapter_workflow(chapter_id)["source_changed"] is True


@pytest.mark.parametrize("strategy", ["plot_adjust", "expansion", "plot_rewrite"])
def test_review_is_human_edit_and_confirmation_without_model_call(tmp_path: Path, strategy: str) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    material_id = None
    if strategy == "plot_rewrite":
        material_id = MaterialService(database).create_material(
            material_type="author_style", scope="public", name="S", raw_text="x",
            content={"summary": "s", "dimensions": []}, analysis_status="analyzed",
        )
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, chapter_id, strategy, material_id=material_id)
    service.generate_chapter(chapter_id)
    saved = service.save_writing(chapter_id, "HUMAN EDIT")
    assert saved["result_text"] == "HUMAN EDIT"
    assert saved["status"] == "reviewed"
    assert service.get_chapter_workflow(chapter_id)["current_stage"] == "review"
    assert not any(stage in {"review", "review_repair"} for stage, _ in ai.calls)

    confirmed = service.confirm_chapter(chapter_id)
    assert confirmed["current_stage"] == "confirmed"
    assert confirmed["writing"]["status"] == "confirmed"
    assert "review" not in confirmed


def test_legacy_scene_rows_do_not_affect_chapter_workflow(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    with session(database) as connection:
        project_id = connection.execute("SELECT project_id FROM chapters WHERE id=?", (chapter_id,)).fetchone()[0]
        connection.execute(
            """INSERT INTO scenes(project_id,chapter_id,scene_index,title,original_start_offset,
               original_end_offset,original_text) VALUES(?,?,1,'legacy',0,3,'old')""",
            (project_id, chapter_id),
        )
    service = CreativeWorkflowService(database, ai_client=WorkflowAI())
    assert service.run_chapter_summary(chapter_id)["plot_summary"] == "summary"


def test_current_api_is_chapter_centered_and_old_scene_creative_routes_are_absent(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    os.environ["RUSTY_API_TOKEN"] = "test-token"
    os.environ["RUSTY_DATABASE_PATH"] = str(database)
    from backend.api import create_app

    app = create_app(database, workflow_ai_client=WorkflowAI())
    paths = {str(getattr(route, "path", "")) for route in app.routes}
    assert f"/api/chapters/{{chapter_id}}/workflow" in paths
    assert "/api/projects/{project_id}/creative-workflow" not in paths
    assert "/api/chapters/{chapter_id}/creative-workflow" not in paths
    assert "/api/chapters/{chapter_id}/creative-scene-states" not in paths
    assert "/api/scenes/{scene_id}/creative-workflow" not in paths
    assert "/api/scenes/{scene_id}/workflow/start" not in paths
    assert not any(path.startswith("/api/scene-workflows/") for path in paths)
    with TestClient(app) as client:
        headers = {"X-Rusty-Token": "test-token"}
        summary = client.post(f"/api/chapters/{chapter_id}/workflow/summary/run", headers=headers)
        rejected = client.put(
            f"/api/chapters/{chapter_id}/workflow/direction",
            headers=headers,
            json={"strategy": "faithful", "user_instruction": "legacy"},
        )
    assert summary.status_code == 200
    assert summary.json()["plot_summary"] == "summary"
    assert rejected.status_code == 400
