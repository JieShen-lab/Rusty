from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from rusty.db import session
from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


def structured_skeleton(summary: str, start: dict, end: dict) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [{
            "id": "generated-event", "order": 1, "event_type": "event",
            "summary": summary, "participants": ["Alpha"], "location": "yard",
            "time_state": {}, "causes": [], "effects": [], "locked": False,
            "source_span": None, "confidence": 1.0,
        }],
        "causal_links": [], "character_state_changes": [],
        "location_changes": [], "time_changes": [], "object_changes": [],
        "knowledge_changes": [], "relationship_changes": [],
        "foreshadowing": [], "open_threads": [], "resolved_threads": [],
        "required_start_state": start, "required_end_state": end,
        "editable_points": [], "source_references": [],
    }


class FakePlotAI:
    def __init__(self) -> None:
        self.consistency_issues: list[dict] = []
        self.scene_count = 1

    def generate_json(self, stage: str, payload: dict) -> dict:
        if stage == "propose_target_skeleton":
            context = payload["context"]
            return {"target_skeleton": structured_skeleton(
                payload["user_direction"],
                context["start_state"],
                context.get("return_state_constraints") or {"route": "generated"},
            )}
        if stage == "generate_scene_plan":
            return {"chapters": [{
                "title": "Generated chapter", "summary": "Plan",
                "scenes": [
                    {"title": f"Scene {index}", "direction": "Follow the confirmed plan"}
                    for index in range(1, self.scene_count + 1)
                ],
            }]}
        if stage == "generate_next_scene":
            return {"text": f"<{payload['target_skeleton']['event_nodes'][0]['summary']}>"}
        if stage == "update_fact_ledger":
            return {"facts_after": {**payload["facts_before"], "route": "generated"}}
        if stage == "consistency_check":
            return {"issues": self.consistency_issues, "final_state": payload["final_state"]}
        raise AssertionError(stage)


class PlotGenerationOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.source = self.root / "book.txt"
        self.original = "Alpha enters the yard.\n\nAlpha checks the gate.\n\nAlpha returns to the inn."
        self.source.write_text(f"1. One\n{self.original}", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.ai = FakePlotAI()
        self.plot = PlotGenerationOrchestrator(self.database, ai_client=self.ai)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, kind: str) -> tuple[int, int, list]:
        workspace = self.root / f"{kind}-{len(list(self.root.iterdir()))}"
        workspace.mkdir()
        project_id = self.projects.create_project(
            self.projects.preview_book(self.source), workspace, project_kind=kind,
        )
        chapter = self.projects.list_chapters(project_id)[0]
        scenes = SceneService(self.database).split_chapter(
            chapter.id,
            proposed_boundaries=[self.original.index("Alpha returns")],
        )
        SceneService(self.database).save_fact_ledger(
            scenes[0].id, {
                "location": "yard",
                "gate_checked": True,
                "required_end_state": {"location": "yard", "gate_checked": True},
            },
        )
        SceneService(self.database).save_fact_ledger(
            scenes[1].id, {
                "location": "inn",
                "alive": True,
                "required_end_state": {"location": "inn", "alive": True},
            },
        )
        return project_id, chapter.id, scenes

    def finish(self, run: dict) -> dict:
        ready = self.plot.confirm_target_skeleton(run["id"], run["target_skeleton"])
        self.assertEqual("ready", ready["status"])
        self.assertEqual([], ready["seams"])
        return self.plot.execute(run["id"])

    def test_bounded_insert_preserves_original_and_skips_seam_stage(self) -> None:
        project_id, chapter_id, _ = self.create_project("rewrite")
        offset = self.original.index("Alpha returns")
        run = self.plot.start(
            project_id=project_id, generation_mode="bounded_insert",
            start_anchor={"anchor_type": "text_offset", "chapter_id": chapter_id, "text_offset": offset},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="AMBUSH",
        )
        done = self.finish(run)
        text = done["result"]["rewritten_text"]
        self.assertIn("Alpha checks the gate.", text)
        self.assertIn("<AMBUSH>", text)
        self.assertIn("Alpha returns to the inn.", text)
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)

    def test_replace_range_only_removes_explicit_selection(self) -> None:
        project_id, chapter_id, _ = self.create_project("rewrite")
        start = self.original.index("Alpha checks")
        end = self.original.index("Alpha returns")
        run = self.plot.start(
            project_id=project_id, generation_mode="bounded_insert",
            range_operation="replace_range",
            start_anchor={"anchor_type": "text_offset", "chapter_id": chapter_id, "text_offset": start},
            return_anchor={"anchor_type": "text_offset", "chapter_id": chapter_id, "text_offset": end},
            user_direction="REPLACEMENT",
        )
        text = self.finish(run)["result"]["rewritten_text"]
        self.assertNotIn("Alpha checks the gate.", text)
        self.assertIn("<REPLACEMENT>", text)
        self.assertIn("Alpha returns to the inn.", text)

    def test_consistency_findings_are_saved_as_warnings(self) -> None:
        project_id, chapter_id, _ = self.create_project("rewrite")
        self.ai.consistency_issues = [{"type": "style_shift"}]
        run = self.plot.start(
            project_id=project_id, generation_mode="bounded_insert",
            start_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="SOFT WARNING",
        )
        done = self.finish(run)
        self.assertEqual("completed", done["status"])
        self.assertEqual("style_shift", done["issues"][0]["type"])
        self.assertIsNotNone(done["result_version_id"])

    def test_incremental_generation_commits_only_after_last_scene(self) -> None:
        project_id, _, _ = self.create_project("branch")
        self.ai.scene_count = 2
        run = self.plot.start(
            project_id=project_id, generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"}, user_direction="CONTINUE",
        )
        ready = self.plot.confirm_target_skeleton(run["id"], run["target_skeleton"])
        first = self.plot.generate_next(run["id"])
        self.assertEqual("generating", first["status"])
        self.assertEqual([], BranchService(self.database).list_chapters(int(run["branch_id"])))
        done = self.plot.generate_next(run["id"])
        self.assertEqual("completed", done["status"])
        self.assertEqual(2, len(BranchService(self.database).list_chapters(int(run["branch_id"]))[0]["scenes"]))
        self.assertEqual("ready", ready["status"])

    def test_existing_branch_continuation_appends_to_same_route_and_inherits_facts(self) -> None:
        project_id, _, _ = self.create_project("branch")
        first = self.finish(self.plot.start(
            project_id=project_id, generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"}, user_direction="FIRST",
        ))
        branch_id = int(first["branch_id"])
        chapter = BranchService(self.database).list_chapters(branch_id)[-1]
        scene = chapter["scenes"][-1]
        second_run = self.plot.start(
            project_id=project_id, generation_mode="open_continuation", branch_id=branch_id,
            start_anchor={
                "anchor_type": "branch_scene", "branch_scene_id": scene["id"],
                "source_version_id": scene["version_id"], "side": "after",
            },
            user_direction="SECOND",
        )
        self.assertEqual(branch_id, second_run["branch_id"])
        self.assertEqual(scene["facts_after"], second_run["start_state"])
        self.finish(second_run)
        self.assertEqual(2, len(BranchService(self.database).list_chapters(branch_id)))
        self.assertEqual(1, len(BranchService(self.database).list_branches(project_id)))

    def test_fork_uses_selected_scene_state_without_original_future(self) -> None:
        project_id, _, scenes = self.create_project("branch")
        run = self.plot.start(
            project_id=project_id, generation_mode="fork",
            start_anchor={"anchor_type": "scene_end", "scene_id": scenes[0].id},
            user_direction="IF ROUTE",
        )
        self.assertEqual("yard", run["start_state"]["location"])
        self.assertNotIn("alive", run["start_state"])

    def test_removed_advanced_modes_are_rejected(self) -> None:
        project_id, chapter_id, _ = self.create_project("branch")
        with self.assertRaisesRegex(ValueError, "Unsupported generation mode"):
            self.plot.start(
                project_id=project_id, generation_mode="fork_and_rejoin",
                start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
                user_direction="legacy mode",
            )
        branch = BranchService(self.database).create_branch(
            project_id=project_id, name="root", branch_mode="fork",
            start_anchor={"anchor_type": "document_end"},
        )
        with self.assertRaisesRegex(ValueError, "Child branches are not supported"):
            BranchService(self.database).create_branch(
                project_id=project_id, name="child", branch_mode="fork",
                start_anchor={"anchor_type": "document_end"}, parent_branch_id=branch["id"],
            )

    def test_cancelled_run_never_commits_formal_output(self) -> None:
        project_id, chapter_id, _ = self.create_project("rewrite")
        run = self.plot.start(
            project_id=project_id, generation_mode="bounded_insert",
            start_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="CANCEL",
        )
        cancelled = self.plot.cancel(run["id"])
        self.assertEqual("cancelled", cancelled["status"])
        with self.assertRaisesRegex(ValueError, "Target skeleton"):
            self.plot.execute(run["id"])
        with session(self.database) as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM chapter_rewrite_versions WHERE chapter_id = ?", (chapter_id,),
            ).fetchone()[0]
        self.assertEqual(0, count)

    def test_concurrent_source_snapshot_cannot_overwrite_new_head(self) -> None:
        project_id, chapter_id, _ = self.create_project("rewrite")
        kwargs = {
            "project_id": project_id, "generation_mode": "bounded_insert",
            "start_anchor": {"anchor_type": "chapter_end", "chapter_id": chapter_id},
            "return_anchor": {"anchor_type": "chapter_end", "chapter_id": chapter_id},
        }
        first = self.plot.start(**kwargs, user_direction="FIRST")
        second = self.plot.start(**kwargs, user_direction="SECOND")
        self.finish(second)
        stale = self.finish(first)
        self.assertEqual("failed", stale["status"])
        self.assertEqual("source_version_conflict", stale["issues"][0]["type"])
        self.assertIn("SECOND", self.projects.get_chapter(chapter_id).rewritten_text)
        self.assertNotIn("FIRST", self.projects.get_chapter(chapter_id).rewritten_text)


if __name__ == "__main__":
    unittest.main()
