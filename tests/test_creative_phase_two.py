from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v47
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
        self.assertEqual(47, CURRENT_SCHEMA_VERSION)

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
