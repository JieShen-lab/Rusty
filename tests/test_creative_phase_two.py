from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v47, _migrate_to_v48
from rusty.services.anchor_service import AnchorService
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


SOURCE = "张三被王五逼到墙边。\n王五第二刀横扫而来。\n张三握紧长刀借墙反冲。"


class RecordingAI:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage, payload))
        if stage == "writing_plan":
            a = "张三被王五逼到墙边。\n"
            b = "王五第二刀横扫而来。\n"
            c = "张三握紧长刀借墙反冲。"
            return {"blocks": [
                {"title": "被逼退", "source_start_offset": 0, "source_end_offset": len(a), "source_text_snapshot": a, "operation": "preserve"},
                {"title": "第二刀", "source_start_offset": len(a), "source_end_offset": len(a+b), "source_text_snapshot": b, "operation": "transform", "instruction": "保持王五第二刀"},
                {"title": "借墙反击", "source_start_offset": len(a+b), "source_end_offset": len(SOURCE), "source_text_snapshot": c, "operation": "rewrite", "preserve_constraints": ["借墙反冲", "王五仍在场"], "target_requirements": ["李四使用剑"]},
            ]}
        if stage == "transform_block":
            return {"text": "王五第二刀横扫而来。\n"}
        if stage == "rewrite_block":
            return {"text": "李四拔剑借墙反冲。"}
        if stage == "selected_text_edit":
            return {"text": "李四迅速拔剑"}
        if stage == "review_rework":
            return {"text": "李四贴墙避开刀锋。"}
        raise AssertionError(stage)


class CreativePhaseTwoTests(unittest.TestCase):
    def test_v47_migration_adds_plan_blocks_and_current_drafts(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
            CREATE TABLE scenes(id INTEGER PRIMARY KEY);
            CREATE TABLE scene_targets(id INTEGER PRIMARY KEY);
            CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY, name TEXT, description TEXT, kind TEXT,
              workflow_key TEXT, task_key TEXT, content TEXT, input_description TEXT, is_default INTEGER, deleted_at TEXT);
        """)
        _migrate_to_v47(connection)
        _migrate_to_v47(connection)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"writing_plans", "writing_plan_blocks", "scene_current_drafts"}.issubset(tables))
        self.assertEqual(5, connection.execute("SELECT COUNT(*) FROM prompt_definitions").fetchone()[0])
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 47)

    def test_v48_migration_adds_minimal_review_marks(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""
          CREATE TABLE scenes(id INTEGER PRIMARY KEY);
          CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY, name TEXT, description TEXT, kind TEXT,
            workflow_key TEXT, task_key TEXT, content TEXT, input_description TEXT, is_default INTEGER, deleted_at TEXT);
        """)
        _migrate_to_v48(connection); _migrate_to_v48(connection)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(review_marks)")}
        self.assertEqual({"id","scene_id","source_start_offset","source_end_offset","source_text","target_start_offset","target_end_offset","user_note","resolved","created_at","updated_at"}, columns)
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM prompt_definitions WHERE task_key='review_rework'").fetchone()[0])
        self.assertEqual(48, CURRENT_SCHEMA_VERSION)

    def test_block_generation_preserves_source_without_ai_and_uses_manual_draft_context(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, ai = self._prepared(Path(directory))
            plan = service.run_writing_plan(scene_id)
            ai.calls.clear()
            draft = service.generate_current_draft(scene_id)
            generation_stages = [stage for stage, _ in ai.calls]
            original_a = SOURCE.splitlines(keepends=True)[0]
            self.assertTrue(draft["text"].startswith(original_a))
            self.assertEqual(["transform_block", "rewrite_block"], generation_stages)
            self.assertIn("王五第二刀", ai.calls[0][1]["current_source_block"])
            self.assertIn("借墙反冲", ai.calls[1][1]["preserve_constraints"])

            manually_edited = "【用户修改】张三稳住脚步。\n" + draft["text"][len(original_a):]
            saved = service.save_current_draft(scene_id, {**draft, "text": manually_edited})
            block_b = plan["blocks"][1]
            b_start = saved["text"].index("王五第二刀")
            b_end = b_start + len("王五第二刀横扫而来。\n")
            ai.calls.clear()
            regenerated = service.regenerate_writing_block(scene_id, block_b["id"], current_start_offset=b_start, current_end_offset=b_end)

            self.assertTrue(regenerated["text"].startswith("【用户修改】张三稳住脚步。\n"))
            self.assertIn("【用户修改】张三稳住脚步。", ai.calls[0][1]["previous_current_draft_tail"])
            target = service.get_target(scene_id)
            service.save_target(scene_id, {**target, "design": {**target["design"], "summary": ["用户修改了目标"]}})
            self.assertEqual("stale", service.get_writing_plan(scene_id)["status"])
            self.assertEqual(regenerated["text"], service.get_current_draft(scene_id)["text"])

    def test_selected_edit_only_replaces_requested_current_draft_range(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id)
            draft = service.generate_current_draft(scene_id)
            start = draft["text"].index("李四拔剑")
            end = start + len("李四拔剑")
            edited = service.edit_selected_draft_text(scene_id, start_offset=start, end_offset=end, user_instruction="动作更快，不增加攻击")
            self.assertEqual(draft["text"][:start], edited["text"][:start])
            self.assertEqual(draft["text"][end:], edited["text"][start + len("李四迅速拔剑"):])

    def test_traditional_diff_review_marks_restore_local_rework_undo_and_confirm(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, ai = self._prepared(Path(directory))
            service.run_writing_plan(scene_id)
            draft = service.generate_current_draft(scene_id)
            calls_before_review = len(ai.calls)
            diff = service.start_review(scene_id)
            self.assertEqual(calls_before_review, len(ai.calls))
            self.assertTrue(any(chunk["tag"] != "equal" for chunk in diff["chunks"]))

            source_piece = "张三被王五逼到墙边。"
            target_end = draft["text"].index("\n")
            mark = service.save_review_mark(scene_id, {"source_start_offset": 0, "source_end_offset": len(source_piece),
                "target_start_offset": 0, "target_end_offset": target_end, "user_note": "这里贴墙动作不能删除。"})
            restored = service.restore_review_source(scene_id, mark["id"])
            self.assertTrue(restored["text"].startswith(source_piece))

            second = service.save_review_mark(scene_id, {"source_start_offset": 0, "source_end_offset": len(source_piece),
                "target_start_offset": 0, "target_end_offset": len(source_piece), "user_note": "换成李四但保留贴墙。"})
            result = service.rework_review_range(scene_id, target_start_offset=0, target_end_offset=len(source_piece), mark_id=second["id"])
            self.assertTrue(result["draft"]["text"].startswith("李四贴墙避开刀锋。"))
            undone = service.save_current_draft(scene_id, {**result["draft"], "text": result["before_text"]})
            self.assertEqual(result["before_text"], undone["text"])

            unresolved = service.save_review_mark(scene_id, {"source_start_offset": 0, "source_end_offset": 2,
                "target_start_offset": 0, "target_end_offset": 2, "user_note": "仍需人工查看"})
            confirmed = service.confirm_scene(scene_id)
            self.assertGreaterEqual(confirmed["unresolved_marks"], 1)
            self.assertEqual("confirmed", confirmed["draft"]["status"])
            self.assertFalse(next(item for item in service.list_review_marks(scene_id) if item["id"] == unresolved["id"])["resolved"])

    @staticmethod
    def _prepared(root: Path) -> tuple[CreativeWorkflowService, int, RecordingAI]:
        source = root / "book.txt"
        source.write_text(f"第一章\n{SOURCE}", encoding="utf-8")
        database = root / "rusty.db"
        projects = ProjectService(database)
        project_id = projects.create_project(projects.preview_book(source), root)
        chapter = projects.list_chapters(project_id)[0]
        scenes = SceneService(database)
        scene = scenes.split_chapter(chapter.id)[0]
        scenes.confirm_boundaries(chapter.id)
        card_id = AnchorService(database).create_character_card(name="李四", scope="project", project_id=project_id, setting_text="惯用剑。")
        ai = RecordingAI()
        service = CreativeWorkflowService(database, ai_client=ai)
        service.save_preanalysis(scene.id, {"summary": "战斗", "characters": ["张三", "王五"], "basic_events": ["王五攻击", "张三借墙反冲"]})
        service.confirm_preanalysis(scene.id)
        service.save_intent(scene.id, {"strategy": "faithful", "user_instruction": "张三改为李四，长刀改剑。", "selected_character_ids": [card_id]})
        empty = {key: [] for key in service.__class__.__dict__.get("CHARACTER_ANALYSIS_CATEGORIES", [])}
        analysis = {"source_character": "张三", "target_character_card_id": card_id,
                    "explicit_mentions": [], "implicit_references": [], "actions": [], "dialogue": [], "states": [],
                    "objects": [], "spatial_relations": [], "related_events": [], "target_character_conflicts": [], **empty}
        service.save_character_modification_analysis(scene.id, analysis)
        service.confirm_character_modification_analysis(scene.id)
        target = service.save_target(scene.id, {"strategy": "faithful", "design": {"items": [
            {"label": "人物", "operation": "modify", "source_value": "张三", "target_value": "李四"},
            {"label": "敌方第二刀", "operation": "preserve", "source_value": "王五第二刀横扫而来。", "target_value": ""},
            {"label": "武器", "operation": "modify", "source_value": "长刀", "target_value": "剑"},
        ], "summary": ["人物与武器修改，事件保持"]}})
        service.confirm_target(scene.id)
        return service, scene.id, ai


if __name__ == "__main__":
    unittest.main()
