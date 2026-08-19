from __future__ import annotations

import sqlite3
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from rusty.db import initialize_database_file, session
from rusty.services.creative_workflow_service import CreativeWorkflowService, REVIEW_FOCUS, WorkflowSourceConflict
from rusty.services.material_service import MaterialService
from rusty.services.project_service import ProjectService


class WorkflowAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []
        self.patch_blocks = [
            {"operation": "preserve", "start_offset": 0, "end_offset": 4, "instruction": ""},
            {"operation": "modify", "start_offset": 4, "end_offset": 7, "instruction": "replace"},
            {"operation": "preserve", "start_offset": 7, "end_offset": 11, "instruction": ""},
        ]

    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage, payload))
        if stage == "chapter_summary":
            return {
                "plot_summary": "summary", "main_characters": ["甲"], "key_events": ["event"],
                "relationships": [], "start_state": {"place": "A"}, "end_state": {"place": "B"},
                "important_facts": ["fact"], "open_threads": ["thread"],
            }
        if stage == "special_analysis":
            strategy = payload["strategy"]
            target = [{"id": "t1", "operation": "preserve", "source_ids": ["s1"]}]
            constraints = {}
            if strategy == "reimagine":
                target = [{"id": "t1", "summary": "new chain"}]
                constraints = {
                    "start_conditions": ["A"], "core_purpose": "goal",
                    "required_end_state": ["B"], "hard_constraints": ["fact"],
                }
            elif strategy == "expansion":
                target = [{"id": "next-1", "summary": "next chapter"}]
            return {
                "source_outline": [{"id": "s1", "start_offset": 0, "end_offset": 11}],
                "target_outline": target, "constraints": constraints, "analysis_notes": [],
            }
        if stage == "author_style_extraction":
            return {"style_snapshot": {"voice": "source"}, "generated_guidance": "follow source"}
        if stage == "writing_plan":
            return {"blocks": self.patch_blocks}
        if stage == "writing":
            if payload.get("operation") == "modify":
                return {"text": "XXX"}
            if payload.get("operation") == "insert":
                return {"text": "INSERT"}
            strategy = payload["special_analysis"]["strategy"]
            if strategy == "expansion":
                return {"text": getattr(self, "expansion_text", "NEW CHAPTER"), "title": "Inserted"}
            return {"text": "REIMAGINED"}
        if stage == "review":
            return {
                "summary": "one issue", "metrics": {"ok": False},
                "issues": [{"severity": "warning", "category": "continuity", "start_offset": 0,
                            "end_offset": 3, "description": "fix it", "suggested_fix": "better"}],
            }
        if stage == "review_repair":
            return {"replacement_text": "FIX"}
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
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy=strategy, user_instruction="do it")
    service.run_special_analysis(chapter_id, outline_detail_level="brief" if strategy == "reimagine" else None)
    service.resolve_style(chapter_id, author_style_material_id=material_id)


def test_workflow_is_chapter_only_and_accepts_exactly_three_strategies(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)

    summary = service.run_chapter_summary(chapter_id)
    assert summary["main_characters"] == ["甲"]
    assert service.get_chapter_workflow(chapter_id)["current_stage"] == "summary"
    assert not hasattr(service, "scenes")
    with pytest.raises(ValueError, match="plot_adjust"):
        service.save_chapter_direction(chapter_id, strategy="faithful", user_instruction="legacy")
    for strategy in ("plot_adjust", "expansion", "reimagine"):
        saved = service.save_chapter_direction(chapter_id, strategy=strategy, user_instruction="x")
        assert saved == {"chapter_id": chapter_id, "strategy": strategy, "user_instruction": "x", "updated_at": saved["updated_at"]}
        assert "selected_character_ids" not in saved
        assert "selected_plot_material_ids" not in saved


def test_plot_adjust_copies_preserve_spans_and_only_generates_changed_block(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, chapter_id, "plot_adjust")
    ai.calls.clear()

    writing = service.generate_chapter(chapter_id)

    assert writing["result_text"] == "AAA XXX CCC"
    assert writing["writing_plan"][0]["result_text"] == "AAA "
    writing_calls = [payload for stage, payload in ai.calls if stage == "writing"]
    assert len(writing_calls) == 1
    assert writing_calls[0]["operation"] == "modify"
    with session(database) as connection:
        assert connection.execute("SELECT original_text FROM chapters WHERE id=?", (chapter_id,)).fetchone()[0] == "AAA BBB CCC"


def test_expansion_creates_new_chapter_without_changing_source_and_shifts_following_indices(tmp_path: Path) -> None:
    database, ids = make_project(tmp_path, ["FIRST", "SECOND"])
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, ids[0], "expansion")

    writing = service.generate_chapter(ids[0])

    assert writing["created_chapter_id"] not in ids
    with session(database) as connection:
        rows = connection.execute("SELECT id,chapter_index,title,original_text FROM chapters ORDER BY chapter_index").fetchall()
    assert [(row["chapter_index"], row["original_text"]) for row in rows] == [(1, "FIRST"), (2, "NEW CHAPTER"), (3, "SECOND")]
    assert rows[1]["title"] == "Inserted"

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


def test_reimagine_requires_and_snapshots_analyzed_author_style(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    service = CreativeWorkflowService(database, ai_client=ai)
    service.run_chapter_summary(chapter_id)
    service.save_chapter_direction(chapter_id, strategy="reimagine", user_instruction="new")
    analysis = service.run_special_analysis(chapter_id, outline_detail_level="brief")
    assert analysis["outline_detail_level"] == "brief"
    assert analysis["constraints"]["hard_constraints"] == ["fact"]
    with pytest.raises(ValueError, match="requires"):
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
    assert writing["result_text"] == "REIMAGINED"
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


def test_source_hash_conflict_is_explicit(tmp_path: Path) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    service = CreativeWorkflowService(database, ai_client=WorkflowAI())
    service.run_chapter_summary(chapter_id)
    ProjectService(database).save_chapter_rewrite(chapter_id, "changed")
    with pytest.raises(WorkflowSourceConflict, match="当前章节已变化"):
        service.save_chapter_direction(chapter_id, strategy="plot_adjust", user_instruction="x")
    assert service.get_chapter_workflow(chapter_id)["source_changed"] is True


@pytest.mark.parametrize("strategy", ["plot_adjust", "expansion", "reimagine"])
def test_review_uses_strategy_specific_focus_and_repair_is_targeted(tmp_path: Path, strategy: str) -> None:
    database, (chapter_id,) = make_project(tmp_path)
    ai = WorkflowAI()
    material_id = None
    if strategy == "reimagine":
        material_id = MaterialService(database).create_material(
            material_type="author_style", scope="public", name="S", raw_text="x",
            content={"summary": "s", "dimensions": []}, analysis_status="analyzed",
        )
    service = CreativeWorkflowService(database, ai_client=ai)
    prepare(service, chapter_id, strategy, material_id=material_id)
    writing = service.generate_chapter(chapter_id)
    review = service.review_chapter(chapter_id)
    focus = next(payload["review_focus"] for stage, payload in ai.calls if stage == "review")
    assert focus == REVIEW_FOCUS[strategy]
    repaired = service.repair_review_issue(chapter_id, review["issues"][0]["issue_id"])
    assert repaired["writing"]["result_text"] == "FIX" + writing["result_text"][3:]
    assert service.get_review(chapter_id)["issues"][0]["status"] == "repaired"


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
