from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services import AnchorExtractionService, MaterialService, ModelService
from rusty.services.ai_client import AIClient, AIResponse


class FakeMaterialAIClient(AIClient):
    def chat(self, model, api_key, messages):
        return AIResponse(
            text=json.dumps(
                {
                    "materials": [
                        {
                            "name": "遗迹探索",
                            "description": "进入遗迹并突破机关。",
                            "timeline_start_chapter": 11,
                            "timeline_end_chapter": 18,
                            "content": {
                                "prerequisites": ["获得线索"],
                                "stages": ["进入", "受阻", "突破"],
                                "climax": "守护兽现身",
                            },
                        }
                    ]
                },
                ensure_ascii=False,
            ),
            token_usage={"total_tokens": 21},
            elapsed_ms=8,
        )


class MaterialServiceTests(unittest.TestCase):
    def test_legacy_project_copy_is_normalized_into_unified_library(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = MaterialService(database_path)
            with session(database_path) as connection:
                project_id = int(
                    connection.execute(
                        "INSERT INTO projects (name, status, current_stage) VALUES ('测试工程', 'imported', 'split')"
                    ).lastrowid
                )
            tag = service.create_tag("冒险")
            public_id = service.create_material(
                material_type="plot_skeleton",
                scope="public",
                name="遗迹探索",
                description="公共骨架",
                content={"stages": ["进入", "探索"]},
                tag_ids=[tag.id],
            )
            project_copy_id = service.copy_material(
                public_id,
                target_scope="project",
                target_project_id=project_id,
            )
            service.update_material(
                public_id,
                name="遗迹探索 v2",
                description="公共骨架更新",
                detail_level="detailed",
                content={"stages": ["进入", "探索", "高潮"]},
                tag_ids=[tag.id],
            )

            public = service.get_material(public_id)
            project_copy = service.get_material(project_copy_id)
            self.assertIsNotNone(public)
            self.assertIsNotNone(project_copy)
            assert public is not None and project_copy is not None
            self.assertEqual(("冒险",), public.tags)
            self.assertEqual("public", project_copy.scope)
            self.assertIsNone(project_copy.project_id)
            self.assertEqual(
                project_id,
                json.loads(project_copy.source_metadata_json)["legacy_project_id"],
            )
            self.assertEqual(public_id, project_copy.source_material_id)
            self.assertEqual(1, project_copy.source_version)
            self.assertEqual("遗迹探索", project_copy.name)
            self.assertEqual("遗迹探索 v2", public.name)

    def test_type_specific_ai_extraction_creates_timeline_material(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            extraction = AnchorExtractionService(database_path, ai_client=FakeMaterialAIClient())
            material_ids = extraction.extract_materials_from_text(
                "第十一章，主角循着线索进入遗迹。",
                material_type="plot_skeleton",
            )
            material = MaterialService(database_path).get_material(material_ids[0])
            self.assertIsNotNone(material)
            assert material is not None
            self.assertEqual("遗迹探索", material.name)
            self.assertEqual(11, material.timeline_start_chapter)
            self.assertEqual(18, material.timeline_end_chapter)
            self.assertIn("plot_skeleton", material.import_metadata_json)


if __name__ == "__main__":
    unittest.main()
