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
from rusty.services.anchor_service import AnchorService
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
        if stage == "scene_preanalysis":
            return {
                "summary": "人物进入院子并检查院门。",
                "characters": ["人物"],
                "location": "院子",
                "time": "当前",
                "scene_type": "探索",
                "basic_events": ["人物进入院子", "人物检查院门"],
            }
        if stage == "character_modification_analysis":
            return {
                "explicit_mentions": [{"id": "explicit-1", "summary": "人物进入院子", "source_text": "人物进入院子", "start_offset": 0, "end_offset": 6, "inferred": False}],
                "implicit_references": [{"id": "implicit-1", "summary": "“他”指人物", "source_text": "他检查了院门", "start_offset": 9, "end_offset": 15, "inferred": True}],
                "actions": [], "dialogue": [], "states": [], "objects": [],
                "spatial_relations": [], "related_events": [],
                "target_character_conflicts": [{"id": "conflict-1", "summary": "行动方式存在差异", "source_text": "检查了院门", "start_offset": 10, "end_offset": 15, "inferred": False, "source_state": "直接检查", "target_state": "谨慎观察", "difference": "存在差异"}],
            }
        if stage == "special_analysis":
            strategy = payload["creative_intent"]["strategy"]
            if strategy == "plot_adjust":
                return {"source_events": ["进入院子", "检查院门"], "causal_links": ["进入→检查"],
                        "participants": ["人物"], "preconditions": [], "downstream_dependencies": ["旧设定仍有效"],
                        "affected_events": ["检查院门"]}
            if strategy == "expansion":
                return {"entry_state": ["人物已进入院子"], "exit_constraints": ["旧设定仍有效"],
                        "character_relations": [], "active_events": ["检查院门"], "unresolved_goals": [],
                        "available_hooks": ["门外脚步声"]}
            return {"initial_state": ["人物进入院子"], "required_characters": ["李四"], "location": "院子",
                    "time": "当前", "inherited_facts": ["旧设定仍有效"], "required_end_state": ["院门已检查"],
                    "downstream_constraints": ["人物仍返回客栈"]}
        if stage == "target_design":
            strategy = payload["creative_intent"]["strategy"]
            if strategy == "plot_adjust":
                return {"nodes": [
                    {"id":"enter","order":1,"summary":"人物进入院子","participants":["人物"],"outcome":"进入","source_relation":"inherited"},
                    {"id":"inspect","order":2,"summary":"李四发现院门暗记","participants":["李四"],"outcome":"发现线索","source_relation":"modified"}],
                    "source_mapping":[{"source_event_id":"source-1","target_node_id":"enter"},{"source_event_id":"source-2","target_node_id":"inspect"}],
                    "summary":["检查院门改为发现暗记"]}
            if strategy == "expansion":
                return {"insert_after":"人物进入院子","insert_before":"他检查了院门","entry_state":["人物已进入院子"],
                        "new_events":[{"id":"noise","order":1,"summary":"门外传来脚步声"}],
                        "exit_constraints":["旧设定仍有效","人物仍会检查院门"],"summary":["在进入与检查之间增加脚步声"]}
            if strategy == "reimagine":
                return {"boundary_conditions":{"initial_state":["人物进入院子"],"required_characters":["李四"],"location":"院子",
                        "time":"当前","inherited_facts":["旧设定仍有效"],"required_end_state":["院门已检查"],
                        "downstream_constraints":["人物仍返回客栈"]},
                        "nodes":[{"id":"new-1","order":1,"summary":"李四识破院中伏击","participants":["李四"],
                                  "outcome":"解除危机","source_relation":"modified"}],"summary":["重新构思院中冲突"]}
            return {"items": [
                {"id": "character", "label": "人物", "operation": "modify", "source_value": "人物", "target_value": "李四"},
                {"id": "entry", "label": "进入院子", "operation": "preserve", "source_value": "进入院子", "target_value": ""},
                {"id": "action", "label": "检查院门", "operation": "adapt", "source_value": "检查了院门", "target_value": "谨慎观察"},
            ], "summary": ["人物 → 李四", "进入院子保持", "检查动作适配"]}
        if stage == "writing_plan":
            source = payload["source_text"]
            strategy = payload["target"]["strategy"]
            if strategy == "plot_adjust":
                return {"blocks":[{"title":"调整院门事件","source_start_offset":0,"source_end_offset":len(source),
                                   "source_text_snapshot":source,"operation":"rewrite","preserve_constraints":["进入院子"]}]}
            if strategy == "expansion":
                split = source.index("他检查")
                return {"blocks":[
                    {"title":"进入院子","source_start_offset":0,"source_end_offset":split,"source_text_snapshot":source[:split],"operation":"preserve"},
                    {"title":"脚步声","source_start_offset":split,"source_end_offset":split,"source_text_snapshot":"","operation":"insert","target_requirements":["门外脚步声"]},
                    {"title":"检查院门","source_start_offset":split,"source_end_offset":len(source),"source_text_snapshot":source[split:],"operation":"preserve"}]}
            if strategy == "reimagine":
                return {"blocks":[{"title":"整场重新构思","source_start_offset":0,"source_end_offset":len(source),
                                   "source_text_snapshot":source,"operation":"rewrite","preserve_constraints":["边界条件"]}]}
            split = source.index("他检查")
            return {"blocks": [
                {"title": "进入院子", "source_start_offset": 0, "source_end_offset": split, "source_text_snapshot": source[:split], "operation": "preserve"},
                {"title": "检查院门", "source_start_offset": split, "source_end_offset": len(source), "source_text_snapshot": source[split:], "operation": "transform", "instruction": "人物改为李四，动作适配"},
            ]}
        if stage == "transform_block":
            return {"text": "李四谨慎地检查了院门。\n\n"}
        if stage == "rewrite_block":
            return {"text": "人物进入院子后，李四在院门上发现了一枚暗记。\n\n"}
        if stage == "insert_block":
            return {"text": "门外忽然传来一阵脚步声。\n\n"}
        if stage == "full_scene_generation":
            return {"text": "李四进入院子，识破伏击并检查院门，随后仍返回客栈。"}
        if stage == "selected_text_edit":
            return {"text": "李四仔细检查"}
        if stage == "review_rework":
            return {"text": "李四贴近院门仔细观察。"}
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
        AnchorService(database).create_character_card(
            "李四",
            description="谨慎的剑客",
            personality="谨慎",
            action_constraints="先观察再行动",
            setting_text="李四使用剑。",
            scope="project",
            project_id=project_id,
        )
        chapter = projects.list_chapters(project_id)[0]
        scene_service = SceneService(database)
        split_at = chapter.original_text.index("旧设定")
        scenes = scene_service.split_chapter(chapter.id, proposed_boundaries=[split_at])
        scene_service.confirm_boundaries(chapter.id)
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
