from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from support import initialized_database
from rusty.db.schema import AUTHOR_STYLE_DIMENSIONS
from rusty.services.ai_client import AIResponse
from rusty.services.author_style_extraction_service import AuthorStyleExtractionService
from rusty.services.material_service import MaterialService


class StyleClient:
    def chat(self, model, api_key, messages):
        value = {
            "overall_style": "克制而紧凑",
            "dimensions": [
                {
                    "id": item["id"],
                    "name": "模型不得决定名称",
                    "requirement": "模型不得返回要求",
                    "analysis": f"analysis:{item['id']}",
                    "features": [],
                    "examples": [],
                }
                for item in AUTHOR_STYLE_DIMENSIONS
            ],
        }
        return AIResponse(json.dumps(value, ensure_ascii=False), {}, 1)


def add_local_model(database: Path) -> None:
    from rusty.db import session

    with session(database) as connection:
        connection.execute(
            """INSERT INTO ai_models(display_name,provider,base_url,model_name,is_default)
               VALUES('Local','openai_compatible','http://127.0.0.1:11434/v1','test',1)"""
        )


class AuthorStyleCanonicalTests(unittest.TestCase):
    def test_extract_uses_one_settings_read_and_merges_stable_names(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            add_local_model(database)
            client = StyleClient()
            service = AuthorStyleExtractionService(database, ai_client=client)
            original = service.materials.get_ai_settings
            with patch.object(service.materials, "get_ai_settings", wraps=original) as get_settings:
                outcome = service.extract("一段完整的作者样本文本。")

            self.assertEqual(1, get_settings.call_count)
            configured = outcome.settings_snapshot["dimensions"]
            self.assertEqual([item["id"] for item in configured], [item["id"] for item in outcome.result.dimensions])
            self.assertEqual([item["name"] for item in configured], [item["name"] for item in outcome.result.dimensions])
            self.assertNotIn("requirement", outcome.result.dimensions[0])

    def test_settings_export_round_trip_uses_current_format(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            service = MaterialService(database)
            exported = service.export_author_style_settings()
            self.assertEqual(2, exported["schema_version"])
            self.assertEqual("author_style_extraction", exported["config_type"])
            self.assertEqual(
                {"detail_level", "extraction_rules", "base_instruction", "dimensions", "extra_requirements"},
                set(exported) - {"schema_version", "config_type"},
            )
            imported = service.import_author_style_settings(exported)
            self.assertEqual(exported["extraction_rules"], imported.extraction_rules)

    def test_author_page_preview_delegates_to_the_canonical_extraction_pipeline(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database = initialized_database(root / "rusty.db")
            add_local_model(database)
            source = root / "sample.txt"
            source.write_text("第一章\n作者样本文本。", encoding="utf-8")
            service = AuthorStyleExtractionService(database, ai_client=StyleClient())
            with patch.object(service, "extract", wraps=service.extract) as extract:
                preview = service.preview_from_file(source, name="样本作者")
            self.assertEqual(1, extract.call_count)
            self.assertEqual("样本作者", preview.candidates[0].name)


if __name__ == "__main__":
    unittest.main()
