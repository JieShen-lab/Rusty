from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import (
    CURRENT_SCHEMA_VERSION,
    _migrate_to_v41,
    _migrate_to_v42,
    _migrate_to_v44,
    _migrate_to_v45,
)
from rusty.services.anchor_service import AnchorService
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


class CreativeWorkspaceTests(unittest.TestCase):
    class FakeWorkflowAI:
        def generate_json(self, stage: str, payload: dict) -> dict:
            if stage == "character_modification_analysis":
                text = payload["source_text"]
                return {
                    "explicit_mentions": [{
                        "id": "explicit-1", "summary": "张三退到墙边", "source_text": "张三退到了墙边。",
                        "start_offset": text.index("张三"), "end_offset": text.index("张三") + len("张三退到了墙边。"), "inferred": False,
                    }],
                    "implicit_references": [{
                        "id": "implicit-1", "summary": "他指张三", "source_text": "他",
                        "start_offset": text.index("他"), "end_offset": text.index("他") + 1, "inferred": True,
                    }],
                    "actions": [], "dialogue": [], "states": [],
                    "objects": [{
                        "id": "object-1", "summary": "张三握有长刀", "source_text": "长刀",
                        "start_offset": text.index("长刀"), "end_offset": text.index("长刀") + 2, "inferred": True,
                    }],
                    "spatial_relations": [], "related_events": [],
                    "target_character_conflicts": [{
                        "id": "conflict-1", "summary": "武器存在差异", "source_text": "长刀",
                        "start_offset": text.index("长刀"), "end_offset": text.index("长刀") + 2,
                        "inferred": False, "source_state": "使用长刀", "target_state": "使用剑", "difference": "武器不同",
                    }],
                }
            if stage != "scene_preanalysis": raise AssertionError(stage)
            return {
                "summary": "王五袭击张三，张三退到墙边防守。",
                "characters": ["张三", "王五"],
                "location": "酒楼二层",
                "time": "夜间",
                "scene_type": "战斗 / 冲突",
                "basic_events": ["王五发动袭击", "张三防守"],
            }

    def test_v41_migration_backfills_chapter_state_and_is_idempotent(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY);
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                deleted_at TEXT
            );
            INSERT INTO chapters(id) VALUES (10), (20);
            """
        )

        _migrate_to_v41(connection)
        _migrate_to_v41(connection)

        rows = connection.execute(
            "SELECT chapter_id, current_stage FROM chapter_workflow_state ORDER BY chapter_id"
        ).fetchall()
        self.assertEqual([(10, "not_started"), (20, "not_started")], [tuple(row) for row in rows])
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 41)

    def test_v42_migration_adds_preanalysis_and_intent_tables(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY);
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                deleted_at TEXT
            );
            """
        )
        _migrate_to_v42(connection)
        _migrate_to_v42(connection)
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        self.assertIn("scene_preanalyses", tables)
        self.assertIn("creative_intents", tables)
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 42)

    def test_v44_migration_adds_faithful_character_analysis(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE scenes (id INTEGER PRIMARY KEY);
            CREATE TABLE character_cards (id INTEGER PRIMARY KEY);
            """
        )
        _migrate_to_v44(connection)
        _migrate_to_v44(connection)
        columns = {row[1] for row in connection.execute("PRAGMA table_info(character_modification_analyses)")}
        self.assertIn("implicit_references_json", columns)
        self.assertIn("target_character_conflicts_json", columns)
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 44)

    def test_v45_migration_adds_authoritative_scene_state(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.executescript(
            """
            CREATE TABLE chapters (id INTEGER PRIMARY KEY);
            CREATE TABLE scenes (
                id INTEGER PRIMARY KEY,
                chapter_id INTEGER NOT NULL,
                deleted_at TEXT
            );
            CREATE TABLE character_cards (id INTEGER PRIMARY KEY);
            INSERT INTO chapters(id) VALUES (10);
            INSERT INTO scenes(id, chapter_id) VALUES (100, 10), (200, 10);
            """
        )
        _migrate_to_v41(connection)
        _migrate_to_v42(connection)
        _migrate_to_v44(connection)
        connection.execute(
            "UPDATE chapter_workflow_state SET active_scene_id = 100, current_stage = 'target_design' WHERE chapter_id = 10"
        )
        _migrate_to_v45(connection)
        _migrate_to_v45(connection)

        rows = connection.execute(
            "SELECT scene_id, current_stage FROM scene_workflow_state ORDER BY scene_id"
        ).fetchall()
        self.assertEqual([(100, "target_design"), (200, "not_started")], [tuple(row) for row in rows])
        self.assertEqual(45, CURRENT_SCHEMA_VERSION)

    def test_preanalysis_edit_reanalysis_guard_confirmation_and_intent(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text(
                "第一章 夜宴\n张三退到了墙边。\n要不是因为他挡在这里，王五早已经走了。",
                encoding="utf-8",
            )
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]
            scene_service = SceneService(database)
            scene = scene_service.split_chapter(chapter.id)[0]
            scene_service.confirm_boundaries(chapter.id)
            service = CreativeWorkflowService(database, ai_client=self.FakeWorkflowAI())

            generated = service.run_preanalysis(scene.id)
            edited = service.save_preanalysis(scene.id, {**generated, "summary": "用户修改摘要"})
            with self.assertRaisesRegex(ValueError, "replace the user-edited"):
                service.run_preanalysis(scene.id)
            replaced = service.run_preanalysis(scene.id, replace_existing=True)
            confirmed = service.confirm_preanalysis(scene.id)
            intent = service.save_intent(
                scene.id,
                {
                    "strategy": "faithful",
                    "user_instruction": "把张三替换成李四，战斗过程尽量保留。",
                    "selected_character_ids": [3, 3, 2],
                    "selected_plot_material_ids": [9],
                    "selected_scene_material_ids": [7],
                },
            )
            restored = CreativeWorkflowService(database).get_intent(scene.id)
            chapter_state = service.get_chapter_state(chapter.id)
            restored_source = SceneService(database).get_scene(scene.id).original_text

        self.assertEqual("用户修改摘要", edited["summary"])
        self.assertEqual("王五袭击张三，张三退到墙边防守。", replaced["summary"])
        self.assertEqual("confirmed", confirmed["status"])
        self.assertEqual("direction", chapter_state["current_stage"])
        self.assertEqual("faithful", intent["strategy"])
        self.assertEqual([2, 3], restored["selected_character_ids"])
        self.assertEqual(scene.original_text, restored_source)

    def test_rewrite_and_branch_projects_share_persisted_chapter_workflow(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章 起宴\n张三退到了墙边。\n\n第二章 夜宴\n王五举刀。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            parsed = projects.preview_book(source)
            rewrite_id = projects.create_project(parsed, root, project_kind="rewrite")
            branch_id = projects.create_project(parsed, root, project_name="历史分支", project_kind="branch")
            service = CreativeWorkflowService(database)
            scene_service = SceneService(database)

            for project_id in (rewrite_id, branch_id):
                chapter = projects.list_chapters(project_id)[0]
                scene = scene_service.split_chapter(chapter.id)[0]
                saved = service.update_chapter_state(
                    chapter.id, active_scene_id=scene.id, current_stage="preanalysis"
                )
                restored = CreativeWorkflowService(database).get_chapter_state(chapter.id)
                self.assertEqual("preanalysis", saved["current_stage"])
                self.assertEqual(scene.id, restored["active_scene_id"])

    def test_api_keeps_legacy_extract_on_dedicated_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n原文。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            with sqlite3.connect(database) as connection:
                connection.execute(
                    "UPDATE projects SET project_kind = 'legacy_extract' WHERE id = ?", (project_id,)
                )
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            os.environ["RUSTY_DATABASE_PATH"] = str(database)
            from backend.api import create_app

            with TestClient(create_app(database)) as client:
                response = client.get(f"/api/projects/{project_id}/creative-workflow")

        self.assertEqual(409, response.status_code)
        self.assertEqual("legacy_extract_workflow", response.json()["error"])

    def test_faithful_character_analysis_keeps_source_ranges_edit_confirm_and_stale(self) -> None:
        fixture = (
            "张三退到了墙边。\n"
            "要不是因为他挡在这里，王五早已经走了。\n"
            "刚刚挡下攻击的人握紧了长刀。"
        )
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text(f"第一章\n{fixture}", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]
            scene_service = SceneService(database)
            scene = scene_service.split_chapter(chapter.id)[0]
            scene_service.confirm_boundaries(chapter.id)
            target_id = AnchorService(database).create_character_card(
                name="李四", scope="project", project_id=project_id,
                setting_text="惯用剑，倾向速度与闪避。", action_constraints="避免硬接攻击。",
            )
            service = CreativeWorkflowService(database, ai_client=self.FakeWorkflowAI())
            service.run_preanalysis(scene.id)
            service.confirm_preanalysis(scene.id)
            service.save_intent(scene.id, {
                "strategy": "faithful",
                "user_instruction": "把张三替换成李四，战斗过程尽量保留。",
                "selected_character_ids": [target_id],
            })
            generated = service.run_character_modification_analysis(
                scene.id, source_character="张三", target_character_card_id=target_id,
            )
            edited_payload = {
                **generated,
                "actions": [{
                    "id": "manual-action", "summary": "张三挡下攻击",
                    "source_text": "刚刚挡下攻击的人", "start_offset": 0, "end_offset": 0,
                    "inferred": True,
                }],
                "explicit_mentions": [],
            }
            edited = service.save_character_modification_analysis(scene.id, edited_payload)
            confirmed = service.confirm_character_modification_analysis(scene.id)
            unlocked = service.get_chapter_state(chapter.id)
            existing_intent = service.get_intent(scene.id)
            unchanged_intent = service.save_intent(scene.id, existing_intent)
            unchanged_analysis = service.get_character_modification_analysis(scene.id)
            unchanged_state = service.get_chapter_state(chapter.id)
            service.save_intent(scene.id, {
                **existing_intent,
                "user_instruction": "改为李四，但保留事件。",
            })
            stale = service.get_character_modification_analysis(scene.id)
            manually_edited_stale = service.save_character_modification_analysis(scene.id, stale)
            with self.assertRaisesRegex(ValueError, "Re-run stale"):
                service.confirm_character_modification_analysis(scene.id)
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            from backend.api import create_app
            with TestClient(create_app(database, workflow_ai_client=self.FakeWorkflowAI())) as client:
                headers = {"X-Rusty-Token": "test-token"}
                rejected = client.post(
                    f"/api/scenes/{scene.id}/character-modification-analysis/confirm",
                    headers=headers,
                )
                regenerated_response = client.post(
                    f"/api/scenes/{scene.id}/character-modification-analysis/run",
                    headers=headers,
                    json={
                        "source_character": "张三",
                        "target_character_card_id": target_id,
                        "replace_existing": True,
                    },
                )
                reconfirmed_response = client.post(
                    f"/api/scenes/{scene.id}/character-modification-analysis/confirm",
                    headers=headers,
                )
            regenerated = regenerated_response.json()
            reconfirmed = reconfirmed_response.json()

        implicit = generated["implicit_references"][0]
        weapon = generated["objects"][0]
        self.assertEqual("他", scene.original_text[implicit["start_offset"]:implicit["end_offset"]])
        self.assertEqual("长刀", scene.original_text[weapon["start_offset"]:weapon["end_offset"]])
        self.assertEqual([], edited["explicit_mentions"])
        self.assertEqual("刚刚挡下攻击的人", edited["actions"][0]["source_text"])
        self.assertEqual("confirmed", confirmed["status"])
        self.assertEqual("target_design", unlocked["current_stage"])
        self.assertEqual(existing_intent, unchanged_intent)
        self.assertEqual("confirmed", unchanged_analysis["status"])
        self.assertEqual("target_design", unchanged_state["current_stage"])
        self.assertEqual("stale", stale["status"])
        self.assertEqual("stale", manually_edited_stale["status"])
        self.assertEqual(400, rejected.status_code)
        self.assertIn("Re-run stale", rejected.json()["message"])
        self.assertEqual(200, regenerated_response.status_code)
        self.assertEqual(200, reconfirmed_response.status_code)
        self.assertEqual("draft", regenerated["status"])
        self.assertEqual("confirmed", reconfirmed["status"])

    def test_each_scene_restores_its_own_stage_in_any_order(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n场景甲。\n\n场景乙。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]
            scene_service = SceneService(database)
            scenes = scene_service.split_chapter(
                chapter.id,
                proposed_boundaries=[chapter.original_text.index("场景乙")],
            )
            scene_service.confirm_boundaries(chapter.id)
            service = CreativeWorkflowService(database)

            service.set_scene_stage(scenes[0].id, "target_design")
            service.activate_scene(scenes[1].id)
            scene_b = service.get_chapter_state(chapter.id)
            independent = service.list_scene_states(chapter.id)
            service.activate_scene(scenes[0].id)
            scene_a = service.get_chapter_state(chapter.id)

        self.assertEqual("not_started", scene_b["current_stage"])
        self.assertEqual("target_design", scene_a["current_stage"])
        self.assertEqual(
            [(scenes[0].id, "target_design"), (scenes[1].id, "not_started")],
            [(item["scene_id"], item["current_stage"]) for item in independent],
        )

    def test_adjusting_boundaries_retires_active_scene_and_initializes_replacements(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n甲段。\n\n乙段。\n\n丙段。", encoding="utf-8")
            database = root / "rusty.db"
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            chapter = projects.list_chapters(project_id)[0]
            scene_service = SceneService(database)
            old_scenes = scene_service.split_chapter(chapter.id)
            scene_service.confirm_boundaries(chapter.id)
            service = CreativeWorkflowService(database)
            service.set_scene_stage(old_scenes[0].id, "direction")

            new_scenes = scene_service.adjust_boundaries(
                chapter.id,
                [chapter.original_text.index("乙段"), chapter.original_text.index("丙段")],
            )
            service.reconcile_chapter_scenes(chapter.id)
            chapter_state = service.get_chapter_state(chapter.id)
            states = service.list_scene_states(chapter.id)

        self.assertNotIn(chapter_state["active_scene_id"], {scene.id for scene in old_scenes})
        self.assertEqual(new_scenes[0].id, chapter_state["active_scene_id"])
        self.assertTrue(all(item["current_stage"] == "not_started" for item in states))


if __name__ == "__main__":
    unittest.main()
