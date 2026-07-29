from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.db.schema import CURRENT_SCHEMA_VERSION, initialize_database
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.material_service import MaterialService
from rusty.services.model_service import ModelService


class FakeMaterialPreviewClient(AIClient):
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        return AIResponse(
            text=json.dumps(
                {
                    "materials": [
                        {
                            "name": "遗迹冲突",
                            "description": "进入遗迹并面对守卫。",
                            "content": {
                                "premise": "主角追踪线索进入遗迹。",
                                "stages": ["进入", "受阻", "突破"],
                            },
                            "suggested_general_tags": ["冒险", " 冲突 "],
                            "suggested_applicable_scene_tags": ["遗迹", "战斗"],
                            "evidence_summary": "原文明确出现遗迹、守卫和突破。",
                        },
                        {
                            "name": "同行者争执",
                            "description": "同行者对路线发生争执。",
                            "content": {"premise": "路线选择造成分歧。"},
                            "suggested_general_tags": ["关系"],
                            "suggested_applicable_scene_tags": ["对话"],
                            "evidence_summary": "原文包含路线争执。",
                        },
                    ]
                },
                ensure_ascii=False,
            ),
            token_usage={"total_tokens": 40},
            elapsed_ms=10,
        )


class MaterialLibraryV22Tests(unittest.TestCase):
    def test_category_type_rules_and_delete_preserves_material(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            service = MaterialService(Path(directory) / "rusty.db")
            plot_category = service.create_category("plot_skeleton", "主线")
            scene_category = service.create_category("scene_reference", "战斗场景")
            material_id = service.create_material(
                material_type="plot_skeleton",
                scope="public",
                name="主线骨架",
                content={"premise": "选择带来后果。"},
                category_ids=[plot_category.id],
            )
            material = service.get_material(material_id)
            assert material is not None
            self.assertEqual((plot_category.id,), material.category_ids)
            with self.assertRaisesRegex(ValueError, "type"):
                service.set_material_category(material_id, scene_category.id, True)
            service.delete_category(plot_category.id)
            material = service.get_material(material_id)
            self.assertIsNotNone(material)
            assert material is not None
            self.assertEqual((), material.category_ids)

    def test_tag_groups_are_independent_and_project_filter_excludes_unanalyzed(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = MaterialService(database_path)
            with session(database_path) as connection:
                project_id = int(
                    connection.execute(
                        "INSERT INTO projects (name, status, current_stage) VALUES ('P', 'imported', 'split')"
                    ).lastrowid
                )
            general = service.create_tag("战斗", tag_group="general")
            applicable = service.create_tag("战斗", tag_group="applicable_scene")
            self.assertNotEqual(general.id, applicable.id)
            analyzed_id = service.create_material(
                material_type="scene_reference",
                scope="public",
                name="近身战",
                content={"summary": "短距离交锋。"},
                analysis_status="analyzed",
                tag_ids=[general.id],
            )
            pending_id = service.create_material(
                material_type="scene_reference",
                scope="public",
                name="待整理战斗",
                content={},
                analysis_status="unanalyzed",
                tag_ids=[general.id],
            )
            service.set_project_material_filter(
                project_id,
                "scene_reference",
                tag_ids=[general.id],
                manual_material_ids=[],
            )
            self.assertEqual(
                [analyzed_id],
                [item.id for item in service.list_materials_for_project(project_id, material_type="scene_reference")],
            )
            service.set_project_material_filter(
                project_id,
                "scene_reference",
                tag_ids=[],
                manual_material_ids=[pending_id],
            )
            self.assertEqual(
                [pending_id],
                [item.id for item in service.list_materials_for_project(project_id, material_type="scene_reference")],
            )

    def test_preview_is_pure_apply_is_confirmed_and_token_is_single_use(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            service = MaterialService(database_path)
            category = service.create_category("plot_skeleton", "主线")
            fake = FakeMaterialPreviewClient()
            extraction = AnchorExtractionService(database_path, ai_client=fake)
            preview = extraction.preview_materials_from_text(
                "主角进入遗迹，遭遇守卫；同行者对路线发生争执。",
                task_type="narrative_to_plot_skeleton",
            )
            self.assertEqual([], service.list_materials())
            self.assertEqual([], service.list_tags())
            first = preview.candidates[0]
            result = extraction.apply_material_extraction(
                preview_token=preview.preview_token,
                candidates=[
                    {
                        **first.__dict__,
                        "confirmed_general_tags": ["冒险"],
                        "confirmed_applicable_scene_tags": ["遗迹"],
                        "category_ids": [category.id],
                    }
                ],
                selected_candidate_ids=[first.candidate_id],
            )
            self.assertEqual(1, len(result["created"]))
            self.assertEqual([], result["errors"])
            material = service.get_material(int(result["created"][0]["material_id"]))
            assert material is not None
            self.assertEqual(("冒险",), material.general_tags)
            self.assertEqual(("遗迹",), material.applicable_scene_tags)
            self.assertEqual((category.id,), material.category_ids)
            with self.assertRaisesRegex(ValueError, "already used"):
                extraction.apply_material_extraction(
                    preview_token=preview.preview_token,
                    candidates=[],
                    selected_candidate_ids=[],
                )
            prompt = "\n".join(item["content"] for item in fake.calls[0])
            self.assertIn("Never derive scene material", prompt)

    def test_ai_settings_persist_and_reset_for_exact_three_tasks(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = MaterialService(database_path)
            self.assertEqual(3, len(service.list_ai_settings()))
            updated = service.update_ai_settings(
                "source_text_to_scene_material",
                model_id=None,
                detail_level="detailed",
                max_candidates=9,
                generate_tags=False,
                custom_requirements="只保留有直接证据的感官线索。",
                system_prompt="严格提取场景写法。",
            )
            self.assertEqual(9, updated.max_candidates)
            persisted = MaterialService(database_path).get_ai_settings("source_text_to_scene_material")
            self.assertFalse(persisted.generate_tags)
            reset = service.reset_ai_settings("source_text_to_scene_material")
            self.assertEqual("standard", reset.detail_level)
            self.assertTrue(reset.generate_tags)

    def test_v21_to_v22_migration_unifies_project_material_and_builds_filter(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT DEFAULT CURRENT_TIMESTAMP);
                INSERT INTO schema_migrations(version) VALUES (21);
                CREATE TABLE projects(
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'imported',
                    current_stage TEXT NOT NULL DEFAULT 'split',
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                );
                INSERT INTO projects(id, name) VALUES (7, '旧工程');
                CREATE TABLE materials(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    material_type TEXT NOT NULL, scope TEXT NOT NULL, project_id INTEGER,
                    name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '',
                    detail_level TEXT NOT NULL DEFAULT 'standard', raw_text TEXT NOT NULL DEFAULT '',
                    content_json TEXT NOT NULL DEFAULT '{}', analysis_status TEXT NOT NULL DEFAULT 'analyzed',
                    source_metadata_json TEXT NOT NULL DEFAULT '{}', import_metadata_json TEXT NOT NULL DEFAULT '{}',
                    source_material_id INTEGER, source_version INTEGER, legacy_outline_id INTEGER,
                    timeline_start_chapter INTEGER, timeline_end_chapter INTEGER,
                    sort_order INTEGER NOT NULL DEFAULT 0, version INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                );
                INSERT INTO materials(id, material_type, scope, project_id, name)
                VALUES (3, 'plot_skeleton', 'project', 7, '旧骨架');
                CREATE TABLE material_tags(
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL,
                    normalized_name TEXT NOT NULL, sort_order INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    deleted_at TEXT
                );
                CREATE UNIQUE INDEX idx_material_tags_normalized_active
                    ON material_tags(normalized_name) WHERE deleted_at IS NULL;
                INSERT INTO material_tags(id, name, normalized_name) VALUES (4, '主线', '主线');
                CREATE TABLE material_tag_links(
                    material_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY(material_id, tag_id)
                );
                INSERT INTO material_tag_links(material_id, tag_id) VALUES (3, 4);
                """
            )
            initialize_database(connection)
            self.assertEqual(
                CURRENT_SCHEMA_VERSION,
                int(connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]),
            )
            row = connection.execute(
                "SELECT scope, project_id, source_metadata_json FROM materials WHERE id = 3"
            ).fetchone()
            self.assertEqual("public", row["scope"])
            self.assertIsNone(row["project_id"])
            self.assertEqual(7, json.loads(row["source_metadata_json"])["legacy_project_id"])
            linked = connection.execute(
                """
                SELECT f.project_id, f.material_type, ft.tag_id
                FROM project_material_filters f
                JOIN project_material_filter_tags ft ON ft.filter_id = f.id
                """
            ).fetchone()
            self.assertEqual((7, "plot_skeleton", 4), tuple(linked))
            connection.close()


if __name__ == "__main__":
    unittest.main()
