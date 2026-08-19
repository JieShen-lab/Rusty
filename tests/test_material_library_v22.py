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
from tests.support import initialized_database


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
            service = MaterialService(initialized_database(Path(directory) / "rusty.db"))
            style_category = service.create_category("author_style", "动作风格")
            material_id = service.create_material(
                material_type="author_style",
                scope="public",
                name="动作风格",
                content={"summary": "短促动作。", "dimensions": []},
                category_ids=[style_category.id],
            )
            material = service.get_material(material_id)
            assert material is not None
            self.assertEqual((style_category.id,), material.category_ids)
            with self.assertRaisesRegex(ValueError, "Unsupported material type"):
                service.create_category("plot_skeleton", "removed")
            service.delete_category(style_category.id)
            material = service.get_material(material_id)
            self.assertIsNotNone(material)
            assert material is not None
            self.assertEqual((), material.category_ids)

    def test_tag_groups_are_independent_and_project_filter_excludes_unanalyzed(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = initialized_database(Path(directory) / "rusty.db")
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
                material_type="author_style",
                scope="public",
                name="近身战",
                content={"summary": "短距离交锋。"},
                analysis_status="analyzed",
                tag_ids=[general.id],
            )
            pending_id = service.create_material(
                material_type="author_style",
                scope="public",
                name="待整理战斗",
                content={},
                analysis_status="unanalyzed",
                tag_ids=[general.id],
            )
            service.set_project_material_filter(
                project_id,
                "author_style",
                tag_ids=[general.id],
                manual_material_ids=[],
            )
            self.assertEqual(
                [analyzed_id],
                [item.id for item in service.list_materials_for_project(project_id, material_type="author_style")],
            )
            service.set_project_material_filter(
                project_id,
                "author_style",
                tag_ids=[],
                manual_material_ids=[pending_id],
            )
            self.assertEqual(
                [pending_id],
                [item.id for item in service.list_materials_for_project(project_id, material_type="author_style")],
            )

    def test_preview_is_pure_apply_is_confirmed_and_token_is_single_use(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = initialized_database(Path(directory) / "rusty.db")
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            service = MaterialService(database_path)
            category = service.create_category("author_style", "叙事风格")
            fake = FakeMaterialPreviewClient()
            extraction = AnchorExtractionService(database_path, ai_client=fake)
            preview = extraction.preview_materials_from_text(
                "主角进入遗迹，遭遇守卫；同行者对路线发生争执。",
                task_type="author_style_extraction",
            )
            self.assertEqual([], service.list_materials())
            self.assertEqual([], service.list_tags())
            first = preview.candidates[0]
            result = extraction.apply_material_extraction(
                preview_token=preview.preview_token,
                candidates=[
                    {
                        **candidate.__dict__,
                        "confirmed_general_tags": ["冒险"] if candidate.candidate_id == first.candidate_id else [],
                        "confirmed_applicable_scene_tags": ["遗迹"] if candidate.candidate_id == first.candidate_id else [],
                        "category_ids": [category.id] if candidate.candidate_id == first.candidate_id else [],
                    }
                    for candidate in preview.candidates
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
            self.assertIn("author_style_extraction", prompt)

    def test_ai_settings_persist_for_author_style_without_reset_flow(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = initialized_database(Path(directory) / "rusty.db")
            service = MaterialService(database_path)
            self.assertEqual(1, len(service.list_ai_settings()))
            updated = service.update_ai_settings(
                "author_style_extraction",
                model_id=None,
                detail_level="detailed",
                extra_requirements="只保留原文支持的表达规律。",
                system_prompt="严格分析作者风格。",
                base_instruction="分析可操作的写作方法。",
                dimensions=[{"id": "sentence", "name": "句子特征", "requirement": "分析句式。"}],
            )
            self.assertEqual("detailed", updated.detail_level)
            persisted = MaterialService(database_path).get_ai_settings("author_style_extraction")
            self.assertEqual("sentence", persisted.dimensions[0]["id"])
            self.assertFalse(hasattr(service, "reset_ai_settings"))

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
            self.assertIsNone(connection.execute("SELECT id FROM materials WHERE id=3").fetchone())
            self.assertIsNone(
                connection.execute(
                    "SELECT id FROM project_material_filters WHERE material_type='plot_skeleton'"
                ).fetchone()
            )
            connection.close()


if __name__ == "__main__":
    unittest.main()
