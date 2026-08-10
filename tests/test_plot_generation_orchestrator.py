from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.scene_service import SceneService
from rusty.db import session
from rusty.services.chapter_version_service import ChapterVersionService


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
        self.scene_count = 1
        self.chapter_count = 1
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
                        "title": f"新路线 {chapter_index}",
                        "summary": "按用户方向展开",
                        "scenes": [
                            {"title": f"新场景 {index}", "direction": "执行目标细纲"}
                            for index in range(1, self.scene_count + 1)
                        ],
                    }
                    for chapter_index in range(1, self.chapter_count + 1)
                ]
            }
        if stage == "generate_next_scene":
            return {"text": f"生成正文：{payload['target_skeleton']['event_nodes'][0]['summary']}（{payload['scene']['title']}）"}
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
        offset = self.original.rfind("\n\n") + 2
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

    def test_consecutive_bounded_inserts_accumulate_on_immutable_rewrite_versions(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        first_offset = self.original.index("人物随后返回客栈。")
        run1 = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": first_offset,
            },
            return_anchor={
                "anchor_type": "chapter_end",
                "chapter_id": chapter_id,
            },
            user_direction="伏击 A",
        )
        self.confirm(run1)
        completed1 = self.orchestrator.execute(run1["id"])
        first_text = completed1["result"]["rewritten_text"]
        self.assertIn("伏击 A", first_text)

        second_offset = first_text.index("人物随后返回客栈。")
        run2 = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": second_offset,
            },
            return_anchor={
                "anchor_type": "chapter_end",
                "chapter_id": chapter_id,
            },
            user_direction="追逐 B",
        )
        self.confirm(run2)
        completed2 = self.orchestrator.execute(run2["id"])
        second_text = completed2["result"]["rewritten_text"]

        self.assertIn("伏击 A", second_text)
        self.assertIn("追逐 B", second_text)
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)
        with session(self.database) as connection:
            versions = connection.execute(
                """
                SELECT id, parent_version_id, source_run_id, rewritten_text
                FROM chapter_rewrite_versions
                WHERE chapter_id = ? ORDER BY version
                """,
                (chapter_id,),
            ).fetchall()
        self.assertEqual(2, len(versions))
        self.assertEqual(run1["id"], versions[0]["source_run_id"])
        self.assertEqual(run2["id"], versions[1]["source_run_id"])
        self.assertEqual(versions[0]["id"], versions[1]["parent_version_id"])

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
        repair = self.orchestrator.execute(run["id"])
        self.assertEqual("repair_required", repair["status"])
        self.assertEqual("return_state_mismatch", repair["issues"][0]["type"])
        self.assertEqual([], BranchService(self.database).list_chapters(repair["branch_id"]))
        with self.assertRaisesRegex(ValueError, "confirmed before generation"):
            self.orchestrator.execute(run["id"])
        self.llm.force_bad_return = False
        ready = self.orchestrator.retry(run["id"])
        self.assertEqual("ready", ready["status"])
        self.assertEqual(1, ready["generation_attempt"])
        self.assertEqual(0, ready["next_scene_cursor"])
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

    def test_plot_state_machine_allows_planning_revision_and_rejects_execute(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork_and_rejoin",
            start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="绕路后回接",
        )
        invalid = {**run["target_skeleton"], "required_end_state": {"location": "荒野"}}
        blocked = self.orchestrator.confirm_target_skeleton(run["id"], invalid)
        self.assertEqual("planning_blocked", blocked["status"])
        with self.assertRaisesRegex(ValueError, "confirmed before generation"):
            self.orchestrator.execute(run["id"])
        revised = {**invalid, "required_end_state": dict(run["required_return_state"])}
        awaiting = self.orchestrator.confirm_target_skeleton(run["id"], revised)
        self.assertEqual("awaiting_seams", awaiting["status"])

    def test_completed_and_cancelled_runs_are_terminal_and_history_is_preserved(self) -> None:
        project_id, _chapter_id = self.create_project("branch")
        first = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="第一次",
        )
        self.confirm(first)
        completed = self.orchestrator.execute(first["id"])
        self.assertEqual("completed", completed["status"])
        with self.assertRaisesRegex(ValueError, "confirmed before generation"):
            self.orchestrator.execute(first["id"])
        second = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="第二次",
        )
        cancelled = self.orchestrator.cancel(second["id"])
        self.assertEqual("cancelled", cancelled["status"])
        with self.assertRaisesRegex(ValueError, "confirmed before generation"):
            self.orchestrator.execute(second["id"])
        history = self.orchestrator.list_runs(project_id)
        self.assertEqual([second["id"], first["id"]], [item["id"] for item in history])

    def test_seam_reviews_require_complete_unique_atomic_set(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter_id},
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="双接缝",
        )
        proposed = self.orchestrator.confirm_target_skeleton(run["id"], run["target_skeleton"])
        entry, returned = proposed["seams"]
        with self.assertRaisesRegex(ValueError, "Every generation seam"):
            self.orchestrator.confirm_seams(
                run["id"], [{"seam_id": entry["id"], "decision": "confirmed"}]
            )
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            self.orchestrator.confirm_seams(
                run["id"],
                [
                    {"seam_id": entry["id"], "decision": "confirmed"},
                    {"seam_id": entry["id"], "decision": "rejected"},
                ],
            )
        self.assertTrue(
            all(item["status"] == "draft" for item in self.orchestrator.get_run(run["id"])["seams"])
        )
        ready = self.orchestrator.confirm_seams(
            run["id"],
            [
                {"seam_id": entry["id"], "decision": "confirmed"},
                {"seam_id": returned["id"], "decision": "rejected"},
            ],
        )
        self.assertEqual("ready", ready["status"])
        self.assertEqual({"confirmed", "rejected"}, {item["status"] for item in ready["seams"]})

    def test_incremental_generation_pauses_resumes_and_commits_only_after_consistency(self) -> None:
        self.llm.scene_count = 3
        project_id, _chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="三场景计划",
        )
        self.confirm(run)
        first = self.orchestrator.generate_next(run["id"])
        self.assertEqual("generating", first["status"])
        self.assertEqual(1, first["next_scene_cursor"])
        self.assertEqual(1, len(first["generated_progress"]["scenes"]))
        self.assertEqual([], BranchService(self.database).list_chapters(first["branch_id"]))

        second = self.orchestrator.execute(run["id"], max_scenes=1)
        self.assertEqual("generating", second["status"])
        self.assertEqual(2, second["next_scene_cursor"])
        self.assertEqual([], BranchService(self.database).list_chapters(second["branch_id"]))

        completed = self.orchestrator.execute(run["id"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual(3, completed["next_scene_cursor"])
        chapters = BranchService(self.database).list_chapters(completed["branch_id"])
        self.assertEqual(3, len(chapters[0]["scenes"]))
        self.assertEqual(
            ["新场景 1", "新场景 2", "新场景 3"],
            [scene["title"] for scene in chapters[0]["scenes"]],
        )

    def test_child_from_historical_chapter_snapshot_keeps_text_and_facts_aligned(self) -> None:
        project_id, _chapter_id = self.create_project("branch")
        branches = BranchService(self.database)
        parent = branches.create_branch(
            project_id=project_id,
            name="parent",
            branch_mode="fork",
            start_anchor={"anchor_type": "document_end"},
        )
        chapter = branches.create_chapter(
            parent["id"], title="history", facts_after={"location": "initial"}
        )
        scene = branches.save_scene(
            parent["id"],
            branch_chapter_id=chapter["id"],
            title="history scene",
            generated_text="historical text v1",
            facts_after={"location": "v1", "secret": "old"},
        )
        chapter_v1 = branches.get_chapter(chapter["id"])
        branches.save_scene_version(
            scene["id"],
            generated_text="historical text v2",
            facts_after={"location": "v2", "secret": "new"},
        )
        chapter_v2 = branches.get_chapter(chapter["id"])

        runs = []
        for version in (chapter_v1, chapter_v2):
            runs.append(
                self.orchestrator.start(
                    project_id=project_id,
                    generation_mode="fork",
                    parent_branch_id=parent["id"],
                    start_anchor={
                        "anchor_type": "branch_chapter",
                        "branch_chapter_id": chapter["id"],
                        "source_version_id": version["version_id"],
                        "side": "after",
                    },
                    user_direction="从历史章节派生",
                )
            )
        self.assertIn("historical text v1", runs[0]["context"]["previous_generated_scene"])
        self.assertEqual("v1", runs[0]["start_state"]["location"])
        self.assertIn("historical text v2", runs[1]["context"]["previous_generated_scene"])
        self.assertEqual("v2", runs[1]["start_state"]["location"])
        self.assertNotEqual(
            runs[0]["start_anchor"]["source_hash"], runs[1]["start_anchor"]["source_hash"]
        )

    def test_concurrent_runs_use_source_head_cas_and_do_not_overwrite_winner(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        offset = self.original.rfind("\n\n") + 2

        def start(direction: str) -> dict:
            run = self.orchestrator.start(
                project_id=project_id,
                generation_mode="bounded_insert",
                start_anchor={
                    "anchor_type": "text_offset",
                    "chapter_id": chapter_id,
                    "text_offset": offset,
                },
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
                user_direction=direction,
            )
            self.confirm(run)
            return run

        run_a = start("run A")
        run_b = start("run B")
        winner = self.orchestrator.execute(run_b["id"])
        loser = self.orchestrator.execute(run_a["id"])
        self.assertEqual("completed", winner["status"])
        self.assertEqual("failed", loser["status"])
        self.assertEqual("source_version_conflict", loser["issues"][0]["type"])
        current = ChapterVersionService(self.database).list_versions(chapter_id)[0]
        self.assertEqual(winner["result_version_id"], current["id"])
        self.assertIn("run B", current["rewritten_text"])
        self.assertNotIn("run A", current["rewritten_text"])

    def test_plot_can_explicitly_derive_from_historical_rewrite_version(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        self.projects.save_chapter_rewrite(chapter_id, "historical v1 marker")
        versions = ChapterVersionService(self.database)
        v1 = versions.list_versions(chapter_id)[0]
        self.projects.save_chapter_rewrite(chapter_id, "current v2 marker")
        v2 = versions.list_versions(chapter_id)[0]
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": len("historical v1 marker"),
            },
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="historical branch edit",
            source={"kind": "rewrite_version", "version_id": v1["id"]},
        )
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        derived = versions.get_version(completed["result_version_id"])
        self.assertEqual(v1["id"], derived["parent_version_id"])
        self.assertIn("historical v1 marker", derived["rewritten_text"])
        self.assertEqual("current v2 marker", versions.get_version(v2["id"])["rewritten_text"])

    def test_historical_derivation_freezes_separate_expected_current_head(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        self.projects.save_chapter_rewrite(chapter_id, "historical v1 marker")
        versions = ChapterVersionService(self.database)
        v1 = versions.list_versions(chapter_id)[0]
        self.projects.save_chapter_rewrite(chapter_id, "current v2 marker")
        v2 = versions.list_versions(chapter_id)[0]
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": len("historical v1 marker"),
            },
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="stale historical derivation",
            source={"kind": "rewrite_version", "version_id": v1["id"]},
        )
        self.assertEqual(v1["id"], run["source_base_version_id"])
        self.assertEqual(v2["id"], run["expected_source_head_version_id"])
        self.confirm(run)
        self.projects.save_chapter_rewrite(chapter_id, "new concurrent v3 marker")
        v3 = versions.list_versions(chapter_id)[0]
        failed = self.orchestrator.execute(run["id"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual("source_version_conflict", failed["issues"][0]["type"])
        self.assertTrue(versions.get_version(v3["id"])["is_current"])
        self.assertEqual(3, len(versions.list_versions(chapter_id)))

    def test_branch_finalization_rolls_back_all_chapters_when_one_insert_fails(self) -> None:
        self.llm.chapter_count = 3
        project_id, _chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={"anchor_type": "document_end"},
            user_direction="three chapter atomic commit",
        )
        self.confirm(run)
        original = BranchService._create_generated_chapter_in_connection
        calls = 0

        def fail_second(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError("injected chapter two failure")
            return original(*args, **kwargs)

        with mock.patch.object(
            BranchService,
            "_create_generated_chapter_in_connection",
            side_effect=fail_second,
        ):
            with self.assertRaisesRegex(RuntimeError, "chapter two"):
                self.orchestrator.execute(run["id"])
        failed = self.orchestrator.get_run(run["id"])
        self.assertEqual("failed", failed["status"])
        self.assertEqual([], BranchService(self.database).list_chapters(run["branch_id"]))
        self.assertEqual(3, len(failed["generated_progress"]["chapters"]))

    def test_rewrite_version_and_run_completion_roll_back_together(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": self.original.rfind("\n\n") + 2,
            },
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="atomic rewrite",
        )
        self.confirm(run)
        original_transition = self.orchestrator._transition_in_connection

        def fail_completion(connection, run_id, **kwargs):
            if kwargs.get("to_status") == "completed":
                raise RuntimeError("injected run completion failure")
            return original_transition(connection, run_id, **kwargs)

        with mock.patch.object(
            self.orchestrator,
            "_transition_in_connection",
            side_effect=fail_completion,
        ):
            with self.assertRaisesRegex(RuntimeError, "completion failure"):
                self.orchestrator.execute(run["id"])
        self.assertEqual([], ChapterVersionService(self.database).list_versions(chapter_id))
        self.assertIsNone(self.projects.get_chapter(chapter_id).rewritten_text)
        self.assertEqual("failed", self.orchestrator.get_run(run["id"])["status"])

    def test_cancel_winning_race_leaves_no_formal_rewrite_output(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": self.original.rfind("\n\n") + 2,
            },
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="cancel race",
        )
        self.confirm(run)
        entered_generation = threading.Event()
        release_generation = threading.Event()
        original_generate = self.llm.generate_json

        def blocked_generate(stage, payload):
            if stage == "generate_next_scene":
                entered_generation.set()
                release_generation.wait(timeout=5)
            return original_generate(stage, payload)

        errors: list[Exception] = []

        def execute() -> None:
            try:
                self.orchestrator.execute(run["id"])
            except Exception as exc:  # expected when cancellation wins
                errors.append(exc)

        with mock.patch.object(self.llm, "generate_json", side_effect=blocked_generate):
            worker = threading.Thread(target=execute)
            worker.start()
            self.assertTrue(entered_generation.wait(timeout=5))
            cancelled = self.orchestrator.cancel(run["id"])
            release_generation.set()
            worker.join(timeout=5)

        self.assertEqual("cancelled", cancelled["status"])
        self.assertTrue(errors)
        self.assertEqual([], ChapterVersionService(self.database).list_versions(chapter_id))
        self.assertIsNone(self.projects.get_chapter(chapter_id).rewritten_text)

    def test_completed_commit_winning_race_rejects_late_cancel(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor={
                "anchor_type": "text_offset",
                "chapter_id": chapter_id,
                "text_offset": self.original.rfind("\n\n") + 2,
            },
            return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter_id},
            user_direction="commit race",
        )
        self.confirm(run)
        completed = self.orchestrator.execute(run["id"])
        with self.assertRaisesRegex(ValueError, "transition"):
            self.orchestrator.cancel(run["id"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual(1, len(ChapterVersionService(self.database).list_versions(chapter_id)))
        self.assertIsNotNone(self.projects.get_chapter(chapter_id).rewritten_text)


if __name__ == "__main__":
    unittest.main()
