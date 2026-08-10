from __future__ import annotations

import os
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import uvicorn

from backend.api import create_app
from rusty.db import session
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.model_service import ModelService
from rusty.services.prompt_service import PromptService
from rusty.services.analysis_service import AnalysisService
from rusty.services.scene_service import SceneService


SKELETON = {
    "metadata": {},
    "event_nodes": [
        {
            "id": "event-1",
            "order": 1,
            "event_type": "conflict",
            "summary": "人物面对新冲突",
            "participants": ["人物"],
            "location": "院子",
            "time_state": {},
            "causes": [],
            "effects": [],
            "locked": True,
            "source_span": {"start": 0, "end": 1},
            "confidence": 1,
        }
    ],
    "causal_links": [],
    "character_state_changes": [],
    "location_changes": [],
    "time_changes": [],
    "object_changes": [],
    "knowledge_changes": [],
    "relationship_changes": [],
    "foreshadowing": [],
    "open_threads": [],
    "resolved_threads": [],
    "required_start_state": {},
    "required_end_state": {},
    "editable_points": [],
    "source_references": [],
}


class RealE2EFakeLLM:
    def __init__(self):
        self.required_end = {}

    def generate_json(self, stage, payload):
        if stage == "propose_target_skeleton":
            target = deepcopy(SKELETON)
            target["event_nodes"][0]["summary"] = payload["user_direction"]
            target["required_start_state"] = dict(payload["context"].get("start_state") or {})
            target["required_end_state"] = dict(payload["context"].get("return_state_constraints") or {})
            return {"target_skeleton": target}
        if stage == "generate_scene_plan":
            self.required_end = dict(payload["target_skeleton"].get("required_end_state") or {})
            return {"chapters": [{"title": "新章节", "summary": "新路线", "scenes": [{"title": "新场景", "direction": "推进冲突"}]}]}
        if stage == "generate_next_scene":
            summary = payload["target_skeleton"]["event_nodes"][0]["summary"]
            return {"text": f"人物遭遇伏击并化解危机。目标：{summary}"}
        if stage == "update_fact_ledger":
            return {"facts_after": {**payload["facts_before"], **self.required_end, "ambush_resolved": True}}
        if stage == "consistency_check":
            return {"issues": [], "final_state": {**payload["final_state"], "ambush_resolved": True}}
        if stage == "prose_rewrite_plan":
            return {"target_skeleton": payload["source_skeleton"], "rewrite_plan": {"style": "简洁"}}
        if stage == "prose_rewrite_generate":
            return {
                "rewritten_text": (
                    f"{payload['source_text']}\n\n人物踏入院中，警觉地观察四周。"
                )
            }
        if stage == "extract_observed_skeleton":
            observed = deepcopy(payload["expected_skeleton"])
            for node in observed.get("event_nodes", []):
                node["source_span"] = {"start": 0, "end": len(payload["text"])}
                node["confidence"] = 0.85
            return {"observed_skeleton": observed}
        raise AssertionError(f"Unhandled FakeLLM stage: {stage}")


def seed(database: Path) -> None:
    ModelService(database).create_model(
        "Fake E2E Model", "openai_compatible", "http://127.0.0.1/fake", "fake", is_default=True
    )
    PromptService(database).create_template("Fake Rewrite Prompt", is_default=True)
    AnalysisService(database).create_template("Fake Analysis Prompt", is_default=True)
    projects = ProjectService(database)
    workflow = RewriteWorkflowService(database)
    sources = database.parent
    sources.mkdir(parents=True, exist_ok=True)
    for index, kind in enumerate(
        ["rewrite", "rewrite", "rewrite", "branch", "branch", "branch", "branch", "rewrite"],
        1,
    ):
        source = sources / f"source-{index}.txt"
        source.write_text(
            "1. 第一章\n人物进入院子。\n\n他检查了院门。\n\n旧设定仍有效。\n\n人物返回客栈。",
            encoding="utf-8",
        )
        project_id = projects.create_project(
            projects.preview_book(source),
            sources,
            project_name=f"真实 E2E {index}",
            project_kind=kind,
        )
        chapter = projects.list_chapters(project_id)[0]
        scene_service = SceneService(database)
        split_at = chapter.original_text.index("旧设定")
        scenes = scene_service.split_chapter(chapter.id, proposed_boundaries=[split_at])
        scene_service.save_fact_ledger(
            scenes[0].id,
            {
                "location": "院子",
                "gate_checked": True,
                "required_start_state": {"location": "院门"},
                "required_end_state": {"location": "院子", "gate_checked": True},
            },
        )
        scene_service.save_fact_ledger(
            scenes[1].id,
            {
                "location": "客栈",
                "original_future_event": True,
                "required_start_state": {"location": "客栈", "gate_checked": True},
                "required_end_state": {"location": "客栈", "original_future_event": True},
            },
        )
        if index == 2:
            version = workflow.create_structured_skeleton(
                project_id=project_id,
                chapter_id=chapter.id,
                scene_id=None,
                skeleton=SKELETON,
                scope="chapter",
            )
            workflow.confirm_skeleton(version.skeleton_id, version.version)
        if index == 8:
            with session(database) as connection:
                connection.execute(
                    "UPDATE projects SET project_kind = 'legacy_extract' WHERE id = ?",
                    (project_id,),
                )
                connection.execute(
                    "INSERT INTO chapter_summaries(chapter_id, plot_summary) VALUES (?, '旧分析结果')",
                    (chapter.id,),
                )


if __name__ == "__main__":
    runtime_name = os.environ.get("RUSTY_E2E_RUNTIME_NAME", "real-e2e")
    database = ROOT / "tmp" / runtime_name / "rusty.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    os.environ.setdefault("RUSTY_API_TOKEN", "real-e2e-token")
    os.environ.setdefault("RUSTY_API_ALLOWED_ORIGINS", "http://127.0.0.1:4174")
    seed(database)
    uvicorn.run(
        create_app(database, workflow_ai_client=RealE2EFakeLLM()),
        host="127.0.0.1",
        port=int(os.environ.get("RUSTY_API_PORT", "8766")),
        log_level="warning",
    )
