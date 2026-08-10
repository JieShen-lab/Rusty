from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.canon_change_orchestrator import CanonChangeOrchestrator
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.context_service import ContextService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator
from rusty.services.rewrite_version_map_service import RewriteVersionMapService
from rusty.services.scene_service import SceneService
from rusty.services.shared_analysis_service import SkeletonExtractionService


def _skeleton(source_span: dict | None = None) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [{
            "id": "arrival", "order": 1, "event_type": "action",
            "summary": "Hero arrives.", "participants": ["Hero"],
            "location": "yard", "time_state": {}, "causes": [], "effects": [],
            "locked": True, "source_span": source_span, "confidence": 1.0,
        }],
        "causal_links": [], "character_state_changes": [], "location_changes": [],
        "time_changes": [], "object_changes": [], "knowledge_changes": [],
        "relationship_changes": [], "foreshadowing": [], "open_threads": [],
        "resolved_threads": [], "required_start_state": {"location": "gate"},
        "required_end_state": {"location": "inn"}, "editable_points": [],
        "source_references": [],
    }


class ChainPlotAI:
    def generate_json(self, stage: str, payload: dict) -> dict:
        if stage == "propose_target_skeleton":
            target = _skeleton()
            target["event_nodes"][0].update(
                {"id": payload["user_direction"], "summary": payload["user_direction"]}
            )
            target["required_start_state"] = copy.deepcopy(payload["context"]["start_state"])
            target["required_end_state"] = copy.deepcopy(
                payload["context"].get("return_state_constraints") or {}
            )
            return {"target_skeleton": target}
        if stage == "propose_seams":
            text = payload["context"]["start_anchor_context"]["text"]
            start = int(payload["start_anchor"].get("text_offset") or 0)
            returned = int(payload["return_anchor"].get("text_offset") or len(text))
            digest = BranchService.source_hash(text)
            return {"seams": [
                {"seam_kind": "entry", "operation": "insert_after", "original_text": "",
                 "proposed_text": "[entry]", "source_range": {"start": start, "end": start},
                 "source_hash": digest, "reason": "entry", "status": "draft"},
                {"seam_kind": "return", "operation": "insert_before", "original_text": "",
                 "proposed_text": "[return]", "source_range": {"start": returned, "end": returned},
                 "source_hash": digest, "reason": "return", "status": "draft"},
            ]}
        if stage == "generate_scene_plan":
            return {"chapters": [{"title": "insert", "summary": "insert", "scenes": [
                {"title": "insert", "direction": payload["target_skeleton"]["event_nodes"][0]["summary"]}
            ]}]}
        if stage == "generate_next_scene":
            return {"text": f"<{payload['scene']['direction']}>"}
        if stage == "update_fact_ledger":
            return {"facts_after": {**payload["facts_before"], "inserted": True}}
        if stage == "consistency_check":
            return {"issues": [], "final_state": payload["final_state"]}
        raise AssertionError(stage)


class ChainProseAI:
    def __init__(self, skeleton: dict) -> None:
        self.skeleton = skeleton

    def generate_json(self, stage: str, payload: dict) -> dict:
        if stage == "prose_rewrite_plan":
            return {"target_skeleton": copy.deepcopy(self.skeleton), "rewrite_plan": {"style": "expanded"}}
        if stage == "prose_rewrite_generate":
            return {"rewritten_text": f"{payload['source_text']}\n\nSTYLE_MARKER"}
        if stage == "extract_observed_skeleton":
            observed = copy.deepcopy(payload["expected_skeleton"])
            observed["event_nodes"][0]["source_span"] = {"start": 0, "end": len(payload["text"])}
            observed["event_nodes"][0]["confidence"] = 0.9
            return {"observed_skeleton": observed}
        raise AssertionError(stage)


class ChainCanonAI:
    def generate_json(self, stage: str, payload: dict) -> dict:
        if stage == "canon_consistency_check":
            return {"issues": []}
        if stage == "canon_semantic_impact":
            text = payload["candidate"]["text"]
            old = payload["old_fact"]["value"]
            start = text.find(old)
            if start < 0:
                return {"impacts": []}
            return {"impacts": [{
                "source_range": {"start": start, "end": start + len(old)},
                "original_text": old, "replacement_text": payload["new_fact"]["value"],
                "impact_type": "direct_fact", "reason": "canon", "confidence": 1.0,
                "evidence": [old], "requires_confirmation": True,
            }]}
        raise AssertionError(stage)


class VersionAwareWorkflowChainTests(unittest.TestCase):
    def test_plot_prose_scene_anchor_plot_canon_stays_on_one_version_state_chain(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "rusty.db"
            source = root / "book.txt"
            original = "Hero enters yard.\n\nHero returns to inn."
            source.write_text(f"1. One\n{original}", encoding="utf-8")
            projects = ProjectService(database)
            project_id = projects.create_project(
                projects.preview_book(source), root, project_kind="rewrite"
            )
            chapter = projects.list_chapters(project_id)[0]
            scene_service = SceneService(database)
            scenes = scene_service.split_chapter(
                chapter.id, proposed_boundaries=[original.index("Hero returns")]
            )
            scene_service.save_fact_ledger(scenes[0].id, {"location": "yard"})
            scene_service.save_fact_ledger(scenes[1].id, {"location": "inn"})
            source_skeleton = _skeleton({"start": 0, "end": scenes[0].original_end_offset})
            extracted = SkeletonExtractionService(database).save_extraction(
                project_id=project_id, chapter_id=chapter.id,
                scene_id=scenes[0].id, skeleton=source_skeleton,
            )

            plot = PlotGenerationOrchestrator(database, ai_client=ChainPlotAI())

            def finish_plot(run: dict) -> dict:
                planned = plot.confirm_target_skeleton(run["id"], run["target_skeleton"])
                ready = plot.confirm_seams(run["id"], [
                    {"seam_id": seam["id"], "decision": "confirmed"}
                    for seam in planned["seams"]
                ])
                self.assertEqual("ready", ready["status"])
                return plot.execute(run["id"])

            first = finish_plot(plot.start(
                project_id=project_id, generation_mode="bounded_insert",
                start_anchor={"anchor_type": "scene_end", "scene_id": scenes[0].id, "side": "after"},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter.id},
                user_direction="PLOT_A",
            ))
            self.assertEqual("completed", first["status"])

            prose = ProseRewriteOrchestrator(database, ai_client=ChainProseAI(source_skeleton))
            prose_run = prose.plan(
                project_id=project_id, chapter_id=chapter.id, source_skeleton=source_skeleton,
                preservation_policy={}, user_direction="full prose",
            )
            prose_done = prose.execute(prose_run["id"])
            self.assertEqual("completed", prose_done["status"])

            versions = ChapterVersionService(database)
            prose_version = versions.list_versions(chapter.id)[0]
            preview = ContextService(database).preview_story_anchor(
                project_id=project_id, source={"kind": "current"},
                anchor={"anchor_type": "scene_end", "scene_id": scenes[0].id,
                        "source_version_id": prose_version["id"], "side": "after"},
            )
            self.assertEqual(prose_version["id"], preview["resolved_version_id"])
            self.assertEqual("yard", preview["state_after"]["location"])

            second_run = plot.start(
                project_id=project_id, generation_mode="bounded_insert",
                start_anchor={"anchor_type": "scene_end", "scene_id": scenes[0].id,
                              "source_version_id": prose_version["id"], "side": "after"},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter.id,
                               "source_version_id": prose_version["id"]},
                user_direction="PLOT_B",
            )
            self.assertEqual(prose_version["id"], second_run["source_base_version_id"])
            second = finish_plot(second_run)
            self.assertEqual("completed", second["status"])

            canon = CanonChangeOrchestrator(database, ai_client=ChainCanonAI())
            canon_run = canon.scan(
                project_id=project_id,
                old_fact={"subject": "style", "attribute": "marker", "value": "STYLE_MARKER"},
                new_fact={"subject": "style", "attribute": "marker", "value": "CANON_MARKER"},
                effective_order=1,
            )
            for patch in canon_run["patches"]:
                canon.review_patch(patch["id"], decision="accepted")
            applied = canon.apply(canon_run["id"])
            self.assertEqual("applied", applied["status"])

            history = versions.list_versions(chapter.id)
            self.assertEqual(
                ["canon_change", "plot_generation", "prose_rewrite", "plot_generation"],
                [item["source_operation"] for item in history],
            )
            for current, parent in zip(history[:-1], history[1:], strict=True):
                self.assertEqual(parent["id"], current["parent_version_id"])
            self.assertIn("PLOT_A", history[0]["rewritten_text"])
            self.assertIn("PLOT_B", history[0]["rewritten_text"])
            self.assertIn("CANON_MARKER", history[0]["rewritten_text"])
            self.assertNotIn("STYLE_MARKER", history[0]["rewritten_text"])
            self.assertEqual(original, projects.get_chapter(chapter.id).original_text)
            self.assertTrue(RewriteVersionMapService(database).resolve_scene_span(
                history[0]["id"], scenes[0].id
            ))
            self.assertIsNotNone(extracted.version_id)


if __name__ == "__main__":
    unittest.main()
