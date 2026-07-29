from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

import uvicorn

from backend.api import create_app
from rusty.db import session
from rusty.services.branch_service import BranchService
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService


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
            "source_span": None,
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
    def generate_json(self, stage, payload):
        if stage == "propose_target_skeleton":
            return {"target_skeleton": SKELETON}
        if stage == "propose_seams":
            text = payload["context"]["start_anchor_context"]["text"]
            digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            seams = [{
                "seam_kind": "entry",
                "operation": "insert_before",
                "original_text": "",
                "proposed_text": "【进入新剧情】",
                "source_range": {"start": 0, "end": 0},
                "source_hash": digest,
                "reason": "连接新增剧情",
                "status": "draft",
            }]
            if payload["generation_mode"] in {"bounded_insert", "fork_and_rejoin"}:
                seams.append({
                    "seam_kind": "return",
                    "operation": "insert_after",
                    "original_text": "",
                    "proposed_text": "【返回原路线】",
                    "source_range": {"start": 0, "end": 0},
                    "source_hash": digest,
                    "reason": "连接原路线",
                    "status": "draft",
                })
            return {"seams": seams}
        if stage == "generate_scene_plan":
            return {"chapters": [{"title": "新章节", "summary": "新路线", "scenes": [{"title": "新场景", "direction": "推进冲突"}]}]}
        if stage == "generate_next_scene":
            return {"text": "人物遭遇伏击并化解危机。"}
        if stage == "update_fact_ledger":
            return {"facts_after": {**payload["facts_before"], "ambush_resolved": True}}
        if stage == "consistency_check":
            return {"issues": [], "final_state": {**payload["final_state"], "ambush_resolved": True}}
        if stage == "prose_rewrite_plan":
            return {"target_skeleton": payload["source_skeleton"], "rewrite_plan": {"style": "简洁"}}
        if stage == "prose_rewrite_generate":
            return {"rewritten_text": "人物踏入院中，警觉地观察四周。"}
        if stage == "extract_observed_skeleton":
            return {"observed_skeleton": payload["expected_skeleton"]}
        if stage == "prose_rewrite_repair":
            return {"rewritten_text": payload["rewritten_text"]}
        if stage == "canon_semantic_impact":
            text = payload["candidate"]["text"]
            old = str(payload["old_fact"].get("value", ""))
            start = text.find(old)
            if start < 0:
                return {"impacts": []}
            return {"impacts": [{
                "source_range": {"start": start, "end": start + len(old)},
                "original_text": old,
                "replacement_text": str(payload["new_fact"].get("value", "")),
                "impact_type": "direct_fact",
                "reason": "旧事实直接出现",
                "confidence": 1,
                "evidence": [old],
                "requires_confirmation": True,
            }]}
        if stage == "canon_consistency_check":
            old = str(payload["old_fact"].get("value", ""))
            return {"issues": [] if all(old not in item["text"] for item in payload["projected_targets"]) else [{"type": "old_fact_remains"}]}
        raise AssertionError(f"Unhandled FakeLLM stage: {stage}")


def seed(database: Path) -> None:
    projects = ProjectService(database)
    workflow = RewriteWorkflowService(database)
    sources = ROOT / "tmp" / "real-e2e"
    sources.mkdir(parents=True, exist_ok=True)
    for index, kind in enumerate(
        ["rewrite", "rewrite", "rewrite", "branch", "branch", "branch", "branch", "rewrite"],
        1,
    ):
        source = sources / f"source-{index}.txt"
        source.write_text(
            "1. 第一章\n人物进入院子。旧设定仍有效。人物返回客栈。",
            encoding="utf-8",
        )
        project_id = projects.create_project(
            projects.preview_book(source),
            sources,
            project_name=f"真实 E2E {index}",
            project_kind=kind,
        )
        chapter = projects.list_chapters(project_id)[0]
        if index == 2:
            version = workflow.create_structured_skeleton(
                project_id=project_id,
                chapter_id=chapter.id,
                scene_id=None,
                skeleton=SKELETON,
                scope="chapter",
            )
            workflow.confirm_skeleton(version.skeleton_id, version.version)
        if index == 7:
            branches = BranchService(database)
            parent = branches.create_branch(
                project_id=project_id,
                name="父分支",
                branch_mode="fork",
                start_anchor={
                    "anchor_type": "chapter_end",
                    "chapter_id": chapter.id,
                    "source_hash": branches.source_hash(chapter.original_text),
                },
            )
            parent_chapter = branches.create_chapter(
                parent["id"], title="父分支章节", facts_after={"parent": True}
            )
            branches.save_scene(
                parent["id"],
                branch_chapter_id=parent_chapter["id"],
                title="父分支场景",
                generated_text="父分支新场景。",
                facts_after={"parent": True},
            )
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
    database = ROOT / "tmp" / "real-e2e" / "rusty.db"
    database.parent.mkdir(parents=True, exist_ok=True)
    if database.exists():
        database.unlink()
    os.environ["RUSTY_API_TOKEN"] = "real-e2e-token"
    os.environ["RUSTY_API_ALLOWED_ORIGINS"] = "http://127.0.0.1:4174"
    seed(database)
    uvicorn.run(
        create_app(database, workflow_ai_client=RealE2EFakeLLM()),
        host="127.0.0.1",
        port=8766,
        log_level="warning",
    )
