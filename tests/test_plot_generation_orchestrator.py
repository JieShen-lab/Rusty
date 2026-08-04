from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
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
        self.original = "人物进入院子。\n\n他检查了院门。\n\n人物随后返回客栈。"
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
            scenes[0].id,
            {
                "location": "院子",
                "gate_checked": True,
                "required_start_state": {"location": "院门"},
                "required_end_state": {"location": "院子", "gate_checked": True},
                "open_threads": ["旅程"],
                "foreshadowing": ["墙后脚步"],
            },
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

    def create_multichapter_project(self) -> tuple[int, list]:
        source = self.root / "three-chapters.txt"
        source.write_text(
            "1. 第一章\n甲处入口。\n\n2. 第二章\n乙处内容。\n\n3. 第三章\n丙处回接。",
            encoding="utf-8",
        )
        workspace = self.root / "multi-branch"
        workspace.mkdir()
        project_id = self.projects.create_project(
            self.projects.preview_book(source),
            workspace,
            project_name="multi",
            project_kind="branch",
        )
        return project_id, self.projects.list_chapters(project_id)

    def confirm(self, run: dict) -> dict:
        proposed = self.orchestrator.confirm_target_skeleton(
            run["id"], run["target_skeleton"]
        )
        seams = [{**item, "status": "confirmed"} for item in proposed["seams"]]
        return self.orchestrator.confirm_seams(
            run["id"],
            [
                {
                    "seam_id": seam["id"],
                    "decision": seam["status"],
                    "proposed_text": seam["proposed_text"],
                }
                for seam in seams
            ],
        )

    def test_a_bounded_insert_plans_and_generates_without_frontend_ai_results(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        offset = self.original.index("人物随后")
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
        self.assertIn("他检查了院门。", rewritten)
        self.assertIn("人物随后返回客栈。", rewritten)
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)
        self.assertEqual("complete", completed["stage"])

    def test_bounded_insert_defaults_to_insertion_without_deleting_source_range(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        insert_offset = self.original.index("人物随后")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": insert_offset,
            },
            return_anchor={
                "anchor_type": "chapter_end",
                "chapter_id": chapter_id,
            },
            user_direction="增加伏击战",
        )
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        rewritten = completed["result"]["rewritten_text"]
        self.assertLess(rewritten.index("人物进入院子。"), rewritten.index("他检查了院门。"))
        self.assertLess(rewritten.index("他检查了院门。"), rewritten.index("进入新剧情。"))
        self.assertLess(rewritten.index("进入新剧情。"), rewritten.index("生成正文：增加伏击战"))
        self.assertLess(rewritten.index("生成正文：增加伏击战"), rewritten.index("回到原路线。"))
        self.assertLess(rewritten.index("回到原路线。"), rewritten.index("人物随后返回客栈。"))
        chapter = self.projects.get_chapter(chapter_id)
        self.assertEqual(self.original, chapter.original_text)
        self.assertEqual(rewritten, chapter.rewritten_text)

    def test_bounded_insert_only_replaces_source_when_explicitly_requested(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        start = self.original.index("他检查了院门。")
        end = self.original.index("人物随后")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            range_operation="replace_range",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": start,
            },
            return_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": end,
            },
            user_direction="替换为伏击战",
        )
        self.confirm(run)
        rewritten = self.orchestrator.execute(run["id"])["result"]["rewritten_text"]
        self.assertNotIn("他检查了院门。", rewritten)
        self.assertIn("人物进入院子。", rewritten)
        self.assertIn("人物随后返回客栈。", rewritten)
        self.assertIn("生成正文：替换为伏击战", rewritten)

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

    def test_bounded_insert_rejects_offset_hash_and_reverse_range_boundaries(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        with self.assertRaisesRegex(ValueError, "outside the chapter"):
            self.orchestrator.start(
                project_id=project_id,
                generation_mode="bounded_insert",
                start_anchor={"anchor_type": "text_offset", "chapter_id": chapter_id, "text_offset": len(self.original) + 1, "side": "after"},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
                user_direction="invalid",
            )
        with self.assertRaisesRegex(ValueError, "source_hash"):
            self.orchestrator.start(
                project_id=project_id,
                generation_mode="bounded_insert",
                start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id, "source_hash": "stale"},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
                user_direction="invalid",
            )
        with self.assertRaisesRegex(ValueError, "earlier"):
            self.orchestrator.start(
                project_id=project_id,
                generation_mode="bounded_insert",
                range_operation="replace_range",
                start_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
                return_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
                user_direction="invalid",
            )

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

    def test_fork_from_second_scene_end_uses_selected_scene_state(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        scenes = SceneService(self.database).list_scenes(chapter_id)
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            start_anchor={"anchor_type": "scene_end", "scene_id": scenes[0].id},
            user_direction="从检查院门后改变路线",
        )
        self.assertEqual(scenes[0].id, run["context"]["start_anchor_context"]["scene_id"])
        self.assertEqual("院子", run["start_state"]["location"])
        self.assertTrue(run["start_state"]["gate_checked"])
        self.assertNotIn("alive", run["start_state"])
        self.assertEqual("scene_end", run["start_anchor"]["anchor_type"])

    def test_fork_from_skeleton_node_persists_selected_version_and_node(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        structured = skeleton("检查院门", {"location": "院门"}, {"location": "院子"})
        start = self.original.index("他检查了院门。")
        structured["event_nodes"][0]["id"] = "check-gate"
        structured["event_nodes"][0]["source_span"] = {
            "start": start,
            "end": start + len("他检查了院门。"),
        }
        version = RewriteWorkflowService(self.database).create_structured_skeleton(
            project_id=project_id,
            chapter_id=chapter_id,
            scene_id=None,
            scope="chapter",
            source_kind="test",
            skeleton=structured,
        )
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            start_anchor={
                "anchor_type": "skeleton_node",
                "skeleton_version_id": version.version_id,
                "node_id": "check-gate",
                "side": "after",
            },
            user_direction="从细纲事件后分支",
        )
        self.assertEqual(version.version_id, run["start_anchor"]["skeleton_version_id"])
        self.assertEqual("check-gate", run["start_anchor"]["node_id"])
        self.assertEqual(start + len("他检查了院门。"), run["start_anchor"]["text_offset"])

    def test_child_branch_inherits_parent_scene_text_and_facts(self) -> None:
        project_id, _ = self.create_project("branch")
        branches = BranchService(self.database)
        parent = branches.create_branch(
            project_id=project_id,
            name="父分支",
            branch_mode="fork",
            start_anchor={
                "anchor_type": "document_end",
                "source_hash": branches.source_hash(self.original),
            },
        )
        parent_chapter = branches.create_chapter(
            parent["id"],
            title="父分支章节",
            facts_after={"parent_secret_known": True, "location": "地下室"},
        )
        parent_scene = branches.save_scene(
            parent["id"],
            branch_chapter_id=parent_chapter["id"],
            title="地下室发现",
            generated_text="他在地下室得知了父分支秘密。",
            facts_after={
                "parent_secret_known": True,
                "location": "地下室",
                "open_threads": ["秘密来源"],
                "foreshadowing": ["暗门"],
            },
        )
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            parent_branch_id=parent["id"],
            start_anchor={
                "anchor_type": "branch_scene",
                "branch_scene_id": parent_scene["id"],
                "source_version_id": parent_scene["version_id"],
                "side": "after",
            },
            user_direction="从地下室建立子分支",
        )
        self.assertEqual(parent["id"], branches.get_branch(run["branch_id"])["parent_branch_id"])
        self.assertEqual("branch_scene", run["start_anchor"]["anchor_type"])
        self.assertEqual(parent_scene["version_id"], run["start_anchor"]["source_version_id"])
        self.assertEqual(parent_scene["version_id"], branches.get_branch(run["branch_id"])["base_source_version_id"])
        self.assertTrue(run["start_state"]["parent_secret_known"])
        self.assertEqual("地下室", run["start_state"]["location"])
        self.assertIn("父分支秘密", run["context"]["previous_generated_scene"])
        self.confirm(run)
        self.orchestrator.execute(run["id"])
        unchanged = branches.get_scene(parent_scene["id"])
        self.assertEqual("地下室", unchanged["facts_after"]["location"])
        self.assertEqual("他在地下室得知了父分支秘密。", unchanged["generated_text"])

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
        rejected = proposed["seams"][0]
        self.orchestrator.confirm_seams(run["id"], [{"seam_id": rejected["id"], "decision": "rejected"}])
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
        edited = [{"seam_id": proposed["seams"][0]["id"], "decision": "confirmed", "proposed_text": "用户编辑后的接缝。"}]
        original_hash = proposed["seams"][0]["source_hash"]
        with session(self.database) as connection:
            connection.execute("UPDATE branch_seams SET source_hash = 'stale' WHERE id = ?", (edited[0]["seam_id"],))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.orchestrator.confirm_seams(second["id"], edited)
        with session(self.database) as connection:
            connection.execute(
                "UPDATE branch_seams SET source_hash = ? WHERE id = ?",
                (original_hash, edited[0]["seam_id"]),
            )
        self.orchestrator.confirm_seams(second["id"], edited)
        completed = self.orchestrator.execute(second["id"])
        scene = BranchService(self.database).list_scenes(completed["branch_id"])[0]
        self.assertIn("用户编辑后的接缝。", scene["generated_text"])
        self.assertEqual(self.original, self.projects.list_chapters(project_id)[0].original_text)

    def test_cross_chapter_seams_bind_and_validate_independent_sources(self) -> None:
        project_id, chapters = self.create_multichapter_project()
        self.assertEqual(3, len(chapters))
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork_and_rejoin",
            start_anchor={"anchor_type": "chapter_end", "chapter_id": chapters[0].id},
            return_anchor={"anchor_type": "chapter_start", "chapter_id": chapters[2].id},
            user_direction="跨章分支",
        )
        proposed = self.orchestrator.confirm_target_skeleton(run["id"], run["target_skeleton"])
        entry, returned = proposed["seams"]
        self.assertEqual(chapters[0].id, entry["source_anchor"]["chapter_id"])
        self.assertEqual(chapters[2].id, returned["source_anchor"]["chapter_id"])
        self.assertNotEqual(entry["source_hash"], returned["source_hash"])
        reviews = [
            {"seam_id": entry["id"], "decision": "confirmed"},
            {"seam_id": returned["id"], "decision": "confirmed"},
        ]
        with session(self.database) as connection:
            connection.execute("UPDATE branch_seams SET source_hash = 'stale-entry' WHERE id = ?", (entry["id"],))
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.orchestrator.confirm_seams(run["id"], reviews)
        self.assertTrue(all(item["status"] == "draft" for item in self.orchestrator.get_run(run["id"])["seams"]))

    def test_scene_seams_hash_only_their_own_scene_sources(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        scenes = SceneService(self.database).list_scenes(chapter_id)
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork_and_rejoin",
            start_anchor={"anchor_type": "scene_end", "chapter_id": chapter_id, "scene_id": scenes[0].id},
            return_anchor={"anchor_type": "scene_start", "chapter_id": chapter_id, "scene_id": scenes[1].id},
            user_direction="场景间分支",
        )
        proposed = self.orchestrator.confirm_target_skeleton(run["id"], run["target_skeleton"])
        entry, returned = proposed["seams"]
        self.assertEqual(scenes[0].original_text, entry["original_text"])
        self.assertEqual(scenes[1].original_text, returned["original_text"])
        self.assertEqual({"start": 0, "end": len(scenes[0].original_text)}, entry["source_range"])
        self.assertNotEqual(entry["source_hash"], returned["source_hash"])

    def test_parent_branch_scene_version_change_invalidates_only_its_seam(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        parent = self.orchestrator.branches.create_branch(
            project_id=project_id,
            name="parent",
            branch_mode="fork",
            start_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id, "source_hash": self.orchestrator.branches.source_hash(self.original)},
        )
        parent_chapter = self.orchestrator.branches.create_chapter(parent["id"], title="parent")
        parent_scene = self.orchestrator.branches.save_scene(
            parent["id"],
            branch_chapter_id=parent_chapter["id"],
            title="parent scene",
            generated_text="父分支旧正文。",
            facts_after={"location": "地下室"},
        )
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            start_anchor={"anchor_type": "branch_scene", "branch_scene_id": parent_scene["id"], "side": "after"},
            parent_branch_id=parent["id"],
            user_direction="子分支",
        )
        proposed = self.orchestrator.confirm_target_skeleton(run["id"], run["target_skeleton"])
        seam = proposed["seams"][0]
        with session(self.database) as connection:
            next_version = connection.execute(
                "INSERT INTO branch_scene_versions(branch_scene_id, version, generated_text, facts_after_json, parent_version_id) VALUES (?, 2, ?, ?, ?)",
                (parent_scene["id"], "父分支新正文。", '{"location":"地面"}', parent_scene["version_id"]),
            )
            connection.execute("UPDATE branch_scenes SET current_version = 2 WHERE id = ?", (parent_scene["id"],))
        self.assertIsNotNone(next_version.lastrowid)
        with self.assertRaisesRegex(ValueError, "source version changed"):
            self.orchestrator.confirm_seams(run["id"], [{"seam_id": seam["id"], "decision": "confirmed"}])


if __name__ == "__main__":
    unittest.main()
