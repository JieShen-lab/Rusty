from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v47, _migrate_to_v48, _migrate_to_v49, _migrate_to_v50, _migrate_to_v51
from rusty.db import session
from rusty.services.anchor_service import AnchorService
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService
from rusty.services.material_service import MaterialService


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


class PlotAdjustAI:
    def __init__(self) -> None: self.calls: list[tuple[str, dict]] = []
    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage, payload))
        if stage == "special_analysis": return {"source_events": ["A","B","C","D"], "causal_links": ["A→B"], "participants": ["李四","王五"], "preconditions": [], "downstream_dependencies": ["D"], "affected_events": ["B","C"]}
        if stage == "target_design": return {"nodes": [
            {"id":"a","order":1,"summary":"A","participants":[],"outcome":"","source_relation":"inherited"},
            {"id":"b","order":2,"summary":"B2","participants":["李四"],"outcome":"","source_relation":"modified"},
            {"id":"x","order":3,"summary":"X","participants":["王五"],"outcome":"","source_relation":"inserted"},
            {"id":"d","order":4,"summary":"D2","participants":[],"outcome":"","source_relation":"modified"}],
            "source_mapping": [{"source_event_id":"source-1","target_node_id":"a"},{"source_event_id":"source-2","target_node_id":"b"},{"source_event_id":"source-3","target_node_id":None},{"source_event_id":"source-4","target_node_id":"d"}],
            "summary": ["保留 A，改写 B，删除 C，插入 X，调整 D"]}
        if stage == "writing_plan": return {"blocks": [
            {"title":"A","source_start_offset":0,"source_end_offset":2,"source_text_snapshot":"A\n","operation":"preserve"},
            {"title":"B","source_start_offset":2,"source_end_offset":4,"source_text_snapshot":"B\n","operation":"rewrite","preserve_constraints":["承接 A"]},
            {"title":"C","source_start_offset":4,"source_end_offset":6,"source_text_snapshot":"C\n","operation":"delete"},
            {"title":"X","source_start_offset":6,"source_end_offset":6,"source_text_snapshot":"","operation":"insert","target_requirements":["新增 X"]},
            {"title":"D","source_start_offset":6,"source_end_offset":7,"source_text_snapshot":"D","operation":"transform"}]}
        if stage == "rewrite_block": return {"text":"B2\n"}
        if stage == "insert_block": return {"text":"X\n"}
        if stage == "transform_block": return {"text":"D2"}
        raise AssertionError(stage)


class ExpansionAI:
    def __init__(self) -> None: self.calls: list[tuple[str, dict]] = []
    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage,payload))
        if stage == "special_analysis": return {"entry_state":["B 已发生"],"exit_constraints":["C 仍可继续"],"character_relations":[],"active_events":["冲突"],"unresolved_goals":[],"available_hooks":["窗外动静"]}
        if stage == "target_design": return {"insert_after":"B","insert_before":"C","entry_state":["B 已发生"],"new_events":[{"id":"x","order":1,"summary":"X"},{"id":"y","order":2,"summary":"Y"}],"exit_constraints":["C 仍可继续","幕后身份未知"],"summary":["在 B 与 C 之间新增 X/Y"]}
        if stage == "writing_plan": return {"blocks":[
            {"title":"A/B","source_start_offset":0,"source_end_offset":4,"source_text_snapshot":"A\nB\n","operation":"preserve"},
            {"title":"X/Y","source_start_offset":4,"source_end_offset":4,"source_text_snapshot":"","operation":"insert","target_requirements":["X","Y","C 仍可继续"]},
            {"title":"C","source_start_offset":4,"source_end_offset":5,"source_text_snapshot":"C","operation":"preserve"}]}
        if stage == "insert_block": return {"text":"X\nY\n"}
        raise AssertionError(stage)


class ReimagineAI:
    def __init__(self) -> None: self.calls: list[tuple[str,dict]]=[]
    def generate_json(self,stage:str,payload:dict)->dict:
        self.calls.append((stage,payload))
        if stage=="special_analysis": return {"initial_state":["李四在酒楼"],"required_characters":["李四","王五"],"location":"酒楼","time":"夜","inherited_facts":["幕后身份未知"],"required_end_state":["王五离开"],"downstream_constraints":["下一场可继续"]}
        if stage=="target_design": return {"boundary_conditions":{"initial_state":["李四在酒楼"],"required_characters":["李四","王五"],"location":"酒楼","time":"夜","inherited_facts":["幕后身份未知"],"required_end_state":["王五离开"],"downstream_constraints":["下一场可继续"]},"nodes":[{"id":"n1","order":1,"summary":"李四识破伏击","participants":["李四","王五"],"outcome":"交手","source_relation":"modified"}],"summary":["在酒楼重新构思交手"]}
        if stage=="writing_plan": return {"blocks":[{"title":"整场重新构思","source_start_offset":0,"source_end_offset":len(payload["source_text"]),"source_text_snapshot":payload["source_text"],"operation":"rewrite","preserve_constraints":["边界条件"]}]}
        if stage=="full_scene_generation": return {"text":"酒楼灯影摇曳，李四识破王五的伏击。交手后，王五翻窗离开。"}
        raise AssertionError(stage)


class ContextAI:
    def __init__(self) -> None: self.calls: list[tuple[str, dict]] = []
    def generate_json(self, stage: str, payload: dict) -> dict:
        self.calls.append((stage, payload))
        if stage == "target_design":
            return {"items":[{"id":"all","label":"全文","operation":"adapt","source_value":"Source","target_value":"按人物适配"}],"summary":["适配"]}
        if stage == "writing_plan":
            source = payload["source_text"]
            return {"blocks":[{"title":"all","source_start_offset":0,"source_end_offset":len(source),
                               "source_text_snapshot":source,"operation":"transform"}]}
        if stage == "transform_block": return {"text":"CONTEXT-GENERATED"}
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
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 48)

    def test_v49_migration_adds_strategy_analysis_and_plot_prompts(self) -> None:
        connection = sqlite3.connect(":memory:"); connection.row_factory = sqlite3.Row; connection.execute("PRAGMA foreign_keys=ON")
        connection.executescript("""CREATE TABLE scenes(id INTEGER PRIMARY KEY); CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY,name TEXT,description TEXT,kind TEXT,workflow_key TEXT,task_key TEXT,content TEXT,input_description TEXT,is_default INTEGER,deleted_at TEXT);""")
        _migrate_to_v49(connection); _migrate_to_v49(connection)
        self.assertIsNotNone(connection.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='strategy_scene_analyses'").fetchone())
        self.assertEqual(6, connection.execute("SELECT COUNT(*) FROM prompt_definitions WHERE workflow_key='plot_adjust'").fetchone()[0])
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 49)

    def test_v50_migration_seeds_expansion_prompt_tasks(self) -> None:
        connection = sqlite3.connect(":memory:"); connection.row_factory=sqlite3.Row
        connection.executescript("""CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY,name TEXT,description TEXT,kind TEXT,workflow_key TEXT,task_key TEXT,content TEXT,input_description TEXT,is_default INTEGER,deleted_at TEXT);""")
        _migrate_to_v50(connection); _migrate_to_v50(connection)
        self.assertEqual({"special_analysis","target_design","writing_plan","insert_block","seam_repair"}, {row[0] for row in connection.execute("SELECT task_key FROM prompt_definitions WHERE workflow_key='expansion'")})
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 50)

    def test_v51_migration_seeds_reimagine_prompt_tasks(self) -> None:
        connection=sqlite3.connect(":memory:"); connection.row_factory=sqlite3.Row
        connection.executescript("""CREATE TABLE prompt_definitions(id INTEGER PRIMARY KEY,name TEXT,description TEXT,kind TEXT,workflow_key TEXT,task_key TEXT,content TEXT,input_description TEXT,is_default INTEGER,deleted_at TEXT);""")
        _migrate_to_v51(connection); _migrate_to_v51(connection)
        self.assertEqual({"special_analysis","target_design","writing_plan","full_scene_generation"},{row[0] for row in connection.execute("SELECT task_key FROM prompt_definitions WHERE workflow_key='reimagine'")})
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION,51)

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

    def test_plot_adjust_reuses_target_plan_draft_and_expresses_all_mappings(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory); source = root / "book.txt"; source.write_text("第一章\nA\nB\nC\nD", encoding="utf-8")
            database = root / "rusty.db"; projects = ProjectService(database); project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]; scenes = SceneService(database); scene = scenes.split_chapter(chapter.id)[0]; scenes.confirm_boundaries(chapter.id)
            ai = PlotAdjustAI(); service = CreativeWorkflowService(database, ai_client=ai)
            service.save_preanalysis(scene.id, {"summary":"四个事件","characters":[],"basic_events":["A","B","C","D"]}); service.confirm_preanalysis(scene.id)
            service.save_intent(scene.id, {"strategy":"plot_adjust","user_instruction":"修改 B，删除 C，增加 X。"})
            service.run_strategy_analysis(scene.id); analysis = service.confirm_strategy_analysis(scene.id)
            target = service.run_target_design(scene.id); service.confirm_target(scene.id)
            plan = service.run_writing_plan(scene.id); ai.calls.clear(); draft = service.generate_current_draft(scene.id)
            self.assertEqual(["preserve","rewrite","delete","insert","transform"], [block["operation"] for block in plan["blocks"]])
            self.assertEqual("A\nB2\nX\nD2", draft["text"])
            self.assertEqual(["rewrite_block","insert_block","transform_block"], [stage for stage, _ in ai.calls])
            self.assertEqual("confirmed", analysis["status"])
            self.assertEqual("modified", target["design"]["nodes"][1]["source_relation"])

    def test_expansion_inserts_only_new_content_and_keeps_source_blocks_verbatim(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root=Path(directory); source=root/"book.txt"; source.write_text("第一章\nA\nB\nC",encoding="utf-8")
            database=root/"rusty.db"; projects=ProjectService(database); project_id=projects.create_project(projects.preview_book(source),root)
            chapter=projects.list_chapters(project_id)[0]; scenes=SceneService(database); scene=scenes.split_chapter(chapter.id)[0]; scenes.confirm_boundaries(chapter.id)
            ai=ExpansionAI(); service=CreativeWorkflowService(database,ai_client=ai)
            service.save_preanalysis(scene.id,{"summary":"ABC","characters":[],"basic_events":["A","B","C"]}); service.confirm_preanalysis(scene.id)
            service.save_intent(scene.id,{"strategy":"expansion","user_instruction":"在 B 后增加 X/Y。"})
            service.run_strategy_analysis(scene.id); service.confirm_strategy_analysis(scene.id)
            target=service.run_target_design(scene.id); service.confirm_target(scene.id); plan=service.run_writing_plan(scene.id)
            ai.calls.clear(); draft=service.generate_current_draft(scene.id)
            self.assertEqual("A\nB\nX\nY\nC",draft["text"])
            self.assertEqual(["preserve","insert","preserve"],[block["operation"] for block in plan["blocks"]])
            self.assertEqual(["insert_block"],[stage for stage,_ in ai.calls])
            self.assertEqual(["C 仍可继续","幕后身份未知"],target["design"]["exit_constraints"])
            self.assertEqual("A\nB\nC",scenes.get_scene(scene.id).original_text)

    def test_reimagine_passes_boundaries_to_full_generation_and_keeps_source_separate(self) -> None:
        original="李四走进酒楼。王五坐在窗边。"
        with tempfile.TemporaryDirectory(dir=Path.cwd(),ignore_cleanup_errors=True) as directory:
            root=Path(directory); source=root/"book.txt"; source.write_text(f"第一章\n{original}",encoding="utf-8")
            database=root/"rusty.db"; projects=ProjectService(database); project_id=projects.create_project(projects.preview_book(source),root)
            chapter=projects.list_chapters(project_id)[0]; scenes=SceneService(database); scene=scenes.split_chapter(chapter.id)[0]; scenes.confirm_boundaries(chapter.id)
            card_id=AnchorService(database).create_character_card(name="李四",scope="project",project_id=project_id,setting_text="善于观察。")
            ai=ReimagineAI(); service=CreativeWorkflowService(database,ai_client=ai)
            service.save_preanalysis(scene.id,{"summary":"酒楼相遇","characters":["李四","王五"],"location":"酒楼","basic_events":["相遇"]}); service.confirm_preanalysis(scene.id)
            service.save_intent(scene.id,{"strategy":"reimagine","user_instruction":"重新设计交手。","selected_character_ids":[card_id]})
            service.run_strategy_analysis(scene.id); service.confirm_strategy_analysis(scene.id)
            service.run_target_design(scene.id); service.confirm_target(scene.id); service.run_writing_plan(scene.id)
            ai.calls.clear(); draft=service.generate_current_draft(scene.id)
            self.assertEqual(["full_scene_generation"],[stage for stage,_ in ai.calls])
            payload=ai.calls[0][1]
            self.assertEqual("酒楼",payload["boundary_conditions"]["location"])
            self.assertEqual(["王五离开"],payload["boundary_conditions"]["required_end_state"])
            self.assertIn("李四识破伏击",payload["target_skeleton"][0]["summary"])
            self.assertIn("善于观察", json.dumps(payload["character_cards"], ensure_ascii=False))
            self.assertEqual(original,scenes.get_scene(scene.id).original_text)
            self.assertNotEqual(original,draft["text"])

    def test_downstream_invalidation_keeps_stale_draft_until_regeneration(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id)
            original_draft = service.generate_current_draft(scene_id)
            analysis = service.get_character_modification_analysis(scene_id)
            analysis["actions"] = [{"id":"changed","summary":"补充动作","source_text":"借墙反冲",
                                    "start_offset": SOURCE.index("借墙反冲"),
                                    "end_offset": SOURCE.index("借墙反冲") + len("借墙反冲"), "inferred":False}]
            service.save_character_modification_analysis(scene_id, analysis)
            self.assertEqual("stale", service.get_target(scene_id)["status"])
            self.assertEqual("stale", service.get_writing_plan(scene_id)["status"])
            self.assertEqual("stale", service.get_current_draft(scene_id)["status"])
            self.assertEqual(original_draft["text"], service.get_current_draft(scene_id)["text"])

            service.confirm_character_modification_analysis(scene_id)
            target = service.get_target(scene_id)
            service.save_target(scene_id, {**target, "design": {**target["design"], "summary": ["新目标"]}})
            service.confirm_target(scene_id)
            service.run_writing_plan(scene_id, replace_existing=True)
            self.assertEqual("stale", service.get_current_draft(scene_id)["status"])
            refreshed = service.generate_current_draft(scene_id, replace_existing=True)
            self.assertEqual("draft", refreshed["status"])

            plan = service.get_writing_plan(scene_id)
            plan["blocks"][0]["instruction"] = "用户调整规划"
            service.save_writing_plan(scene_id, plan)
            self.assertEqual("stale", service.get_current_draft(scene_id)["status"])
            edited = service.save_current_draft(scene_id, {**service.get_current_draft(scene_id), "text": refreshed["text"] + "手改"})
            self.assertEqual("stale", edited["status"])
            with self.assertRaisesRegex(ValueError, "stale Current Draft"):
                service.confirm_scene(scene_id)

    def test_preanalysis_and_intent_changes_invalidate_every_downstream_layer(self) -> None:
        for changed_level in ("preanalysis", "intent"):
            with self.subTest(changed_level=changed_level), tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
                service, scene_id, _ = self._prepared(Path(directory))
                service.run_writing_plan(scene_id); service.generate_current_draft(scene_id)
                if changed_level == "preanalysis":
                    value = service.get_preanalysis(scene_id); value["summary"] += "（修改）"; service.save_preanalysis(scene_id, value)
                else:
                    value = service.get_intent(scene_id); value["user_instruction"] += "并保持节奏"; service.save_intent(scene_id, value)
                self.assertEqual("stale", service.get_character_modification_analysis(scene_id)["status"])
                self.assertEqual("stale", service.get_target(scene_id)["status"])
                self.assertEqual("stale", service.get_writing_plan(scene_id)["status"])
                self.assertEqual("stale", service.get_current_draft(scene_id)["status"])

    def test_writing_plan_rejects_gap_overlap_order_and_invalid_insert(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            target = service.get_target(scene_id)
            def block(start: int, end: int, operation: str = "preserve") -> dict:
                return {"title":"block","source_start_offset":start,"source_end_offset":end,
                        "source_text_snapshot":"" if operation == "insert" else SOURCE[start:end],"operation":operation}
            invalid_plans = (
                [block(0, 3), block(4, len(SOURCE))],
                [block(0, 5), block(4, len(SOURCE))],
                [block(4, len(SOURCE)), block(0, 4)],
                [{**block(2, 3), "operation":"insert", "source_text_snapshot":""}, block(0, len(SOURCE))],
            )
            for blocks in invalid_plans:
                with self.assertRaises(ValueError):
                    service.save_writing_plan(scene_id, {"target_id":target["id"],"strategy":"faithful","blocks":blocks})
            valid = service.save_writing_plan(scene_id, {"target_id":target["id"],"strategy":"faithful",
                "blocks":[block(0, 4), block(4, 4, "insert"), block(4, len(SOURCE))]})
            self.assertEqual(["preserve","insert","preserve"], [item["operation"] for item in valid["blocks"]])

    def test_target_change_invalidates_ready_plan_and_fresh_draft(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id); service.generate_current_draft(scene_id)
            target = service.get_target(scene_id)
            service.save_target(scene_id, {**target, "design": {**target["design"], "summary": ["独立修改 Target"]}})
            self.assertEqual("stale", service.get_writing_plan(scene_id)["status"])
            self.assertEqual("stale", service.get_current_draft(scene_id)["status"])

    def test_review_offsets_are_scene_local_and_marks_follow_replacements(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            long_source = SOURCE * 6
            source = root / "book.txt"; source.write_text("第一章\n" + ("前" * 100) + long_source + long_source, encoding="utf-8")
            database = root / "rusty.db"; projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]; scenes = SceneService(database)
            created_scenes = scenes.split_chapter(chapter.id, proposed_boundaries=[
                {"start_offset":0,"end_offset":100,"title":"前场","reasons":[]},
                {"start_offset":100,"end_offset":100 + len(long_source),"title":"后场","reasons":[]},
                {"start_offset":100 + len(long_source),"end_offset":100 + 2 * len(long_source),"title":"更后场","reasons":[]},
            ])
            scene = created_scenes[1]
            scenes.confirm_boundaries(chapter.id)
            card_id = AnchorService(database).create_character_card(name="李四",scope="project",project_id=project_id,setting_text="惯用剑。")
            service = CreativeWorkflowService(database, ai_client=RecordingAI()); scene_id = scene.id
            self.assertEqual(100, service.scenes.get_scene(scene_id).original_start_offset)
            service.save_preanalysis(scene_id,{"summary":"后部场景","characters":["张三"],"basic_events":["战斗"]}); service.confirm_preanalysis(scene_id)
            service.save_intent(scene_id,{"strategy":"faithful","user_instruction":"替换人物","selected_character_ids":[card_id]})
            service.save_character_modification_analysis(scene_id,{"source_character":"张三","target_character_card_id":card_id,
                "explicit_mentions":[],"implicit_references":[],"actions":[],"dialogue":[],"states":[],"objects":[],
                "spatial_relations":[],"related_events":[],"target_character_conflicts":[]})
            service.confirm_character_modification_analysis(scene_id)
            service.save_target(scene_id,{"strategy":"faithful","design":{"items":[{"label":"人物","operation":"adapt","source_value":"张三","target_value":"李四"}],"summary":["适配"]}}); service.confirm_target(scene_id)
            target = service.get_target(scene_id)
            service.save_writing_plan(scene_id, {"target_id":target["id"],"strategy":"faithful","blocks":[{
                "title":"all","source_start_offset":0,"source_end_offset":len(long_source),
                "source_text_snapshot":long_source,"operation":"preserve"}]})
            draft = service.generate_current_draft(scene_id)
            source_start, source_end = 20, 30
            first = service.save_review_mark(scene_id, {"source_start_offset":source_start,"source_end_offset":source_end,
                "target_start_offset":0,"target_end_offset":2,"user_note":"first"})
            second = service.save_review_mark(scene_id, {"source_start_offset":150,"source_end_offset":160,
                "target_start_offset":5,"target_end_offset":7,"user_note":"second"})
            self.assertEqual(long_source[source_start:source_end], first["source_text"])
            self.assertEqual(long_source[150:160], second["source_text"])
            service.replace_draft_range(scene_id, 0, 2, "LONGER", current_mark_id=first["id"])
            marks = {item["id"]: item for item in service.list_review_marks(scene_id)}
            self.assertEqual((0, len("LONGER")), (marks[first["id"]]["target_start_offset"], marks[first["id"]]["target_end_offset"]))
            self.assertEqual((5 + len("LONGER") - 2, 7 + len("LONGER") - 2),
                             (marks[second["id"]]["target_start_offset"], marks[second["id"]]["target_end_offset"]))

            later_scene = created_scenes[2]
            service.save_preanalysis(later_scene.id,{"summary":"更后部场景","characters":["张三"],"basic_events":["战斗"]}); service.confirm_preanalysis(later_scene.id)
            service.save_intent(later_scene.id,{"strategy":"faithful","user_instruction":"替换人物","selected_character_ids":[card_id]})
            service.save_character_modification_analysis(later_scene.id,{"source_character":"张三","target_character_card_id":card_id,
                "explicit_mentions":[],"implicit_references":[],"actions":[],"dialogue":[],"states":[],"objects":[],
                "spatial_relations":[],"related_events":[],"target_character_conflicts":[]})
            service.confirm_character_modification_analysis(later_scene.id)
            service.save_target(later_scene.id,{"strategy":"faithful","design":{"items":[{"label":"人物","operation":"adapt","source_value":"张三","target_value":"李四"}],"summary":["适配"]}}); service.confirm_target(later_scene.id)
            later_target = service.get_target(later_scene.id)
            service.save_writing_plan(later_scene.id,{"target_id":later_target["id"],"strategy":"faithful","blocks":[{
                "title":"all","source_start_offset":0,"source_end_offset":len(long_source),"source_text_snapshot":long_source,"operation":"preserve"}]})
            service.generate_current_draft(later_scene.id)
            later_mark = service.save_review_mark(later_scene.id,{"source_start_offset":150,"source_end_offset":160,
                "target_start_offset":10,"target_end_offset":20,"user_note":"later"})
            self.assertGreater(service.scenes.get_scene(later_scene.id).original_start_offset, 100)
            self.assertEqual((150,160),(later_mark["source_start_offset"],later_mark["source_end_offset"]))
            self.assertEqual(long_source[150:160],later_mark["source_text"])

    def test_review_rework_undo_and_adopt_control_resolution(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id); draft = service.generate_current_draft(scene_id)
            mark = service.save_review_mark(scene_id, {"source_start_offset":0,"source_end_offset":2,
                "target_start_offset":0,"target_end_offset":2,"user_note":"重改"})
            result = service.rework_review_range(scene_id, target_start_offset=0, target_end_offset=2, mark_id=mark["id"])
            pending = next(item for item in service.list_review_marks(scene_id) if item["id"] == mark["id"])
            self.assertFalse(pending["resolved"])
            self.assertEqual(len("李四贴墙避开刀锋。"), pending["target_end_offset"])
            service.save_current_draft(scene_id, {**result["draft"], "text":result["before_text"]})
            self.assertFalse(next(item for item in service.list_review_marks(scene_id) if item["id"] == mark["id"])["resolved"])
            again = service.rework_review_range(scene_id, target_start_offset=0, target_end_offset=2, mark_id=mark["id"])
            service.resolve_review_marks(scene_id, again["mark_ids"])
            self.assertTrue(next(item for item in service.list_review_marks(scene_id) if item["id"] == mark["id"])["resolved"])

    def test_material_and_character_context_are_routed_to_correct_stages(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            scene = service.scenes.get_scene(scene_id)
            materials = MaterialService(service.database_path)
            plot_id = materials.create_material(material_type="plot_skeleton",scope="public",name="Plot",
                                                raw_text="PLOT-CONTENT-ONLY",content={"premise":"PLOT-CONTENT-ONLY"})
            scene_id_ref = materials.create_material(material_type="scene_reference",scope="public",name="SceneRef",
                                                     raw_text="SCENE-REFERENCE-CONTENT")
            intent = service.get_intent(scene_id)
            with session(service.database_path) as connection:
                connection.execute("UPDATE creative_intents SET selected_plot_material_ids_json=?,selected_scene_material_ids_json=? WHERE scene_id=?",
                                   (json.dumps([plot_id]), json.dumps([scene_id_ref]), scene_id))
            ai = ContextAI(); service = CreativeWorkflowService(service.database_path, ai_client=ai)
            service.run_target_design(scene_id, replace_existing=True)
            target_payload = ai.calls[-1][1]
            self.assertIn("PLOT-CONTENT-ONLY", json.dumps(target_payload, ensure_ascii=False))
            self.assertNotIn("SCENE-REFERENCE-CONTENT", json.dumps(target_payload, ensure_ascii=False))
            self.assertIn("惯用剑", json.dumps(target_payload["character_cards"], ensure_ascii=False))
            service.confirm_target(scene_id)
            service.run_writing_plan(scene_id, replace_existing=True)
            writing_payload = ai.calls[-1][1]
            self.assertIn("SCENE-REFERENCE-CONTENT", json.dumps(writing_payload["scene_references"], ensure_ascii=False))
            service.generate_current_draft(scene_id)
            generation_payload = ai.calls[-1][1]
            self.assertIn("SCENE-REFERENCE-CONTENT", json.dumps(generation_payload["scene_references"], ensure_ascii=False))
            self.assertIn("惯用剑", json.dumps(generation_payload["character_cards"], ensure_ascii=False))

    def test_preanalysis_and_character_analysis_noop_saves_preserve_confirmation(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            stage_before = service.get_scene_state(scene_id)["current_stage"]
            preanalysis = service.get_preanalysis(scene_id)
            saved_preanalysis = service.save_preanalysis(scene_id, preanalysis)
            self.assertEqual("confirmed", saved_preanalysis["status"])
            self.assertEqual(preanalysis["confirmed_at"], saved_preanalysis["confirmed_at"])
            self.assertEqual(preanalysis["updated_at"], saved_preanalysis["updated_at"])
            self.assertEqual(stage_before, service.get_scene_state(scene_id)["current_stage"])

            analysis = service.get_character_modification_analysis(scene_id)
            target_before = service.get_target(scene_id)
            saved_analysis = service.save_character_modification_analysis(scene_id, analysis)
            self.assertEqual("confirmed", saved_analysis["status"])
            self.assertEqual(analysis["confirmed_at"], saved_analysis["confirmed_at"])
            self.assertEqual(analysis["updated_at"], saved_analysis["updated_at"])
            self.assertEqual("confirmed", service.get_target(scene_id)["status"])
            self.assertEqual(target_before["updated_at"], service.get_target(scene_id)["updated_at"])
            self.assertEqual(stage_before, service.get_scene_state(scene_id)["current_stage"])

    def test_strategy_analysis_noop_save_preserves_confirmation_and_downstream(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory); source = root / "book.txt"; source.write_text("第一章\nA\nB\nC\nD", encoding="utf-8")
            database = root / "rusty.db"; projects = ProjectService(database); project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]; scenes = SceneService(database); scene = scenes.split_chapter(chapter.id)[0]; scenes.confirm_boundaries(chapter.id)
            service = CreativeWorkflowService(database, ai_client=PlotAdjustAI())
            service.save_preanalysis(scene.id,{"summary":"四个事件","characters":[],"basic_events":["A","B","C","D"]}); service.confirm_preanalysis(scene.id)
            service.save_intent(scene.id,{"strategy":"plot_adjust","user_instruction":"修改 B，删除 C，增加 X。"})
            service.run_strategy_analysis(scene.id); service.confirm_strategy_analysis(scene.id)
            service.run_target_design(scene.id); service.confirm_target(scene.id); service.run_writing_plan(scene.id); service.generate_current_draft(scene.id)
            analysis = service.get_strategy_analysis(scene.id)
            target_before, plan_before, draft_before = service.get_target(scene.id), service.get_writing_plan(scene.id), service.get_current_draft(scene.id)
            stage_before = service.get_scene_state(scene.id)["current_stage"]
            saved = service.save_strategy_analysis(scene.id, analysis)
            self.assertEqual("confirmed", saved["status"])
            self.assertEqual(analysis["confirmed_at"], saved["confirmed_at"])
            self.assertEqual(analysis["updated_at"], saved["updated_at"])
            self.assertEqual("confirmed", service.get_target(scene.id)["status"])
            self.assertEqual("ready", service.get_writing_plan(scene.id)["status"])
            self.assertEqual("draft", service.get_current_draft(scene.id)["status"])
            self.assertEqual((target_before["updated_at"], plan_before["updated_at"], draft_before["updated_at"]),
                             (service.get_target(scene.id)["updated_at"], service.get_writing_plan(scene.id)["updated_at"], service.get_current_draft(scene.id)["updated_at"]))
            self.assertEqual(stage_before, service.get_scene_state(scene.id)["current_stage"])

    def test_target_and_writing_plan_noop_saves_preserve_ready_fresh_state(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id); service.generate_current_draft(scene_id)
            target, plan, draft = service.get_target(scene_id), service.get_writing_plan(scene_id), service.get_current_draft(scene_id)
            stage_before = service.get_scene_state(scene_id)["current_stage"]
            saved_target = service.save_target(scene_id, target)
            self.assertEqual("confirmed", saved_target["status"])
            self.assertEqual(target["confirmed_at"], saved_target["confirmed_at"])
            self.assertEqual(target["updated_at"], saved_target["updated_at"])
            self.assertEqual("ready", service.get_writing_plan(scene_id)["status"])
            self.assertEqual("draft", service.get_current_draft(scene_id)["status"])
            self.assertEqual(stage_before, service.get_scene_state(scene_id)["current_stage"])

            saved_plan = service.save_writing_plan(scene_id, plan)
            self.assertEqual("ready", saved_plan["status"])
            self.assertEqual(plan["updated_at"], saved_plan["updated_at"])
            self.assertEqual(draft["updated_at"], service.get_current_draft(scene_id)["updated_at"])
            self.assertEqual("draft", service.get_current_draft(scene_id)["status"])
            changed_plan = {**saved_plan, "blocks":[{**block, "instruction": "真实变化" if index == 0 else block["instruction"]}
                                                   for index, block in enumerate(saved_plan["blocks"])]}
            service.save_writing_plan(scene_id, changed_plan)
            self.assertEqual("stale", service.get_current_draft(scene_id)["status"])

    def test_current_draft_noop_save_preserves_confirmed_and_stale_states(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            service, scene_id, _ = self._prepared(Path(directory))
            service.run_writing_plan(scene_id); service.generate_current_draft(scene_id); service.confirm_scene(scene_id)
            confirmed = service.get_current_draft(scene_id)
            saved_confirmed = service.save_current_draft(scene_id, confirmed)
            self.assertEqual("confirmed", saved_confirmed["status"])
            self.assertEqual(confirmed["updated_at"], saved_confirmed["updated_at"])
            self.assertEqual("confirmed", service.get_scene_state(scene_id)["current_stage"])

            target = service.get_target(scene_id)
            service.save_target(scene_id,{**target,"design":{**target["design"],"summary":["真实修改"]}})
            stale = service.get_current_draft(scene_id)
            stage_before = service.get_scene_state(scene_id)["current_stage"]
            saved_stale = service.save_current_draft(scene_id, stale)
            self.assertEqual("stale", saved_stale["status"])
            self.assertEqual(stale["updated_at"], saved_stale["updated_at"])
            self.assertEqual(stage_before, service.get_scene_state(scene_id)["current_stage"])

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
