from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService
from rusty.db import session


def skeleton(summary: str, start: dict, end: dict) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [
            {
                "id": "new_event",
                "order": 1,
                "event_type": "conflict",
                "summary": summary,
                "participants": ["人物"],
                "location": "院子",
                "time_state": {},
                "causes": [],
                "effects": [],
                "locked": False,
                "source_span": None,
                "confidence": 1.0,
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
        "required_start_state": start,
        "required_end_state": end,
        "editable_points": [],
        "source_references": [],
    }


class FakePlotLLM:
    def __init__(self) -> None:
        self.force_bad_return = False
        self.stages: list[str] = []
        self.required_end: dict = {}

    def generate_json(self, stage: str, payload: dict) -> dict:
        self.stages.append(stage)
        if stage == "propose_target_skeleton":
            context = payload["context"]
            end = context.get("return_state_constraints") or {
                "route": "fork",
                "location": "城外",
            }
            return skeleton(payload["user_direction"], context["start_state"], end)
        if stage == "propose_seams":
            source = payload["context"]["start_anchor_context"]["text"]
            source_hash = BranchService.source_hash(source)
            start = int(payload["start_anchor"].get("text_offset") or 0)
            seams = [
                {
                    "seam_kind": "entry",
                    "operation": "insert_after",
                    "original_text": "",
                    "proposed_text": "进入新剧情。",
                    "source_range": {"start": start, "end": start},
                    "source_hash": source_hash,
                    "reason": "entry",
                    "status": "draft",
                }
            ]
            if payload["return_anchor"] is not None:
                returned = int(payload["return_anchor"].get("text_offset") or len(source))
                seams.append(
                    {
                        **seams[0],
                        "seam_kind": "return",
                        "proposed_text": "回到原路线。",
                        "source_range": {"start": returned, "end": returned},
                        "reason": "return",
                    }
                )
            return {"seams": seams}
        if stage == "generate_scene_plan":
            self.required_end = dict(payload["target_skeleton"]["required_end_state"])
            return {
                "chapters": [
                    {
                        "title": "新路线",
                        "summary": "按用户方向展开",
                        "scenes": [{"title": "新场景", "direction": "执行目标细纲"}],
                    }
                ]
            }
        if stage == "generate_next_scene":
            return {"text": f"生成正文：{payload['target_skeleton']['event_nodes'][0]['summary']}"}
        if stage == "update_fact_ledger":
            facts = dict(payload["facts_before"])
            facts.update({"route": "fork", "location": "城外"})
            facts.update(self.required_end)
            return {"facts_after": facts}
        if stage == "consistency_check":
            final_state = dict(payload["final_state"])
            if self.force_bad_return:
                final_state["location"] = "院子"
            return {"issues": [], "final_state": final_state}
        raise AssertionError(stage)


class PlotGenerationOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.source = self.root / "book.txt"
        self.original = "人物进入院子。\n\n人物随后返回客栈。"
        self.source.write_text(f"1. 第一章\n{self.original}", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.llm = FakePlotLLM()
        self.orchestrator = PlotGenerationOrchestrator(
            self.database, ai_client=self.llm
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, kind: str) -> tuple[int, int]:
        workspace = self.root / f"{kind}-{len(list(self.root.iterdir()))}"
        workspace.mkdir()
        project_id = self.projects.create_project(
            self.projects.preview_book(self.source),
            workspace,
            project_name=kind,
            project_kind=kind,
        )
        chapter = self.projects.list_chapters(project_id)[0]
        scenes = SceneService(self.database).split_chapter(
            chapter.id, proposed_boundaries=[self.original.index("人物随后")]
        )
        SceneService(self.database).save_fact_ledger(
            scenes[-1].id,
            {
                "location": "客栈",
                "alive": True,
                "required_start_state": {"location": "客栈", "alive": True},
                "required_end_state": {"location": "客栈", "alive": True},
                "open_threads": ["旅程"],
                "foreshadowing": [],
            },
        )
        return project_id, chapter.id

    def confirm(self, run: dict) -> dict:
        proposed = self.orchestrator.confirm_target_skeleton(
            run["id"], run["target_skeleton"]
        )
        seams = [{**item, "status": "confirmed"} for item in proposed["seams"]]
        return self.orchestrator.confirm_seams(
            run["id"], seams, current_source_text=self.original
        )

    def test_a_bounded_insert_plans_and_generates_without_frontend_ai_results(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        offset = self.original.index("\n")
        anchor = {
            "anchor_type": "text_offset",
            "chapter_id": chapter_id,
            "text_offset": offset,
        }
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor=anchor,
            return_anchor=dict(anchor),
            user_direction="人物遭遇一场伏击战。",
        )
        self.assertIn("伏击战", run["target_skeleton"]["event_nodes"][0]["summary"])
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        rewritten = completed["result"]["rewritten_text"]
        self.assertIn("生成正文", rewritten)
        self.assertIn("进入新剧情。", rewritten)
        self.assertIn("回到原路线。", rewritten)
        self.assertIn("人物进入院子。", rewritten)
        self.assertIn("人物随后返回客栈。", rewritten)
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)
        self.assertEqual("complete", completed["stage"])

    def test_b_open_continuation_builds_branch_chapter_without_original_scene_input(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="人物离开客栈继续旅行。",
        )
        self.assertNotIn("current_original_scene", run["context"])
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        chapters = BranchService(self.database).list_chapters(completed["branch_id"])
        self.assertEqual(1, len(chapters))
        self.assertEqual(1, len(chapters[0]["scenes"]))
        self.assertIn("进入新剧情。", chapters[0]["scenes"][0]["generated_text"])
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)

    def test_c_fork_inherits_only_state_before_anchor(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
            user_direction="人物选择另一条路线。",
        )
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        scene = BranchService(self.database).list_scenes(completed["branch_id"])[0]
        self.assertEqual("fork", scene["facts_after"]["route"])
        self.assertNotIn("returned_to_inn", scene["facts_after"])

    def test_d_rejoin_checks_required_state_before_and_after_generation(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork_and_rejoin",
            start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="人物绕路后返回。",
        )
        self.assertEqual({"location": "客栈", "alive": True}, run["required_return_state"])
        self.confirm(run)
        self.llm.force_bad_return = True
        blocked = self.orchestrator.execute(run["id"])
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("return_state_mismatch", blocked["issues"][0]["type"])
        self.assertEqual([], BranchService(self.database).list_chapters(blocked["branch_id"]))

        self.llm.force_bad_return = False
        completed = self.orchestrator.execute(run["id"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)

    def test_invalid_ai_skeleton_is_not_persisted(self) -> None:
        project_id, _ = self.create_project("branch")

        class InvalidLLM(FakePlotLLM):
            def generate_json(self, stage: str, payload: dict) -> dict:
                if stage == "propose_target_skeleton":
                    return {"event_nodes": []}
                return super().generate_json(stage, payload)

        orchestrator = PlotGenerationOrchestrator(
            self.database, ai_client=InvalidLLM()
        )
        with self.assertRaises(ValueError):
            orchestrator.start(
                project_id=project_id,
                generation_mode="open_continuation",
                start_anchor={"anchor_type": "document_end"},
                user_direction="continue",
            )
        with session(self.database) as connection:
            count = connection.execute("SELECT COUNT(*) FROM plot_generation_runs").fetchone()[0]
        self.assertEqual(0, count)

    def test_seam_rejection_edit_and_hash_guard_affect_composed_result(self) -> None:
        project_id, _ = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="继续。",
        )
        proposed = self.orchestrator.confirm_target_skeleton(
            run["id"], run["target_skeleton"]
        )
        rejected = [{**proposed["seams"][0], "status": "rejected"}]
        self.orchestrator.confirm_seams(
            run["id"], rejected, current_source_text=self.original
        )
        completed = self.orchestrator.execute(run["id"])
        scene = BranchService(self.database).list_scenes(completed["branch_id"])[0]
        self.assertNotIn("进入新剧情。", scene["generated_text"])

        second = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="再次继续。",
        )
        proposed = self.orchestrator.confirm_target_skeleton(
            second["id"], second["target_skeleton"]
        )
        edited = [
            {
                **proposed["seams"][0],
                "status": "confirmed",
                "proposed_text": "用户编辑后的接缝。",
            }
        ]
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.orchestrator.confirm_seams(
                second["id"], edited, current_source_text="changed source"
            )
        self.orchestrator.confirm_seams(
            second["id"], edited, current_source_text=self.original
        )
        completed = self.orchestrator.execute(second["id"])
        scene = BranchService(self.database).list_scenes(completed["branch_id"])[0]
        self.assertIn("用户编辑后的接缝。", scene["generated_text"])
        self.assertEqual(self.original, self.projects.list_chapters(project_id)[0].original_text)


if __name__ == "__main__":
    unittest.main()
