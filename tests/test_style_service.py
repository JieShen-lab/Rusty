from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services import ModelService, StyleExtractionService, StyleTemplateService
from rusty.services.ai_client import AIClient, AIResponse


class FakeStyleAIClient(AIClient):
    def __init__(self, invalid_json: bool = False) -> None:
        self.invalid_json = invalid_json
        self.calls = []

    def chat(self, model, api_key, messages):
        self.calls.append((model, api_key, messages))
        user_text = messages[-1]["content"]
        if "Write a short validation sample" in user_text:
            return AIResponse(text="A short styled sample.", token_usage={"total_tokens": 4}, elapsed_ms=7)
        if self.invalid_json:
            return AIResponse(text="not json", token_usage={}, elapsed_ms=1)
        return AIResponse(
            text=json.dumps(
                {
                    "name": "Extracted style",
                    "description": "Extracted description",
                    "global_prompt": "Extracted global.",
                    "rewrite_prompt": "Extracted rewrite.",
                    "generated_prompt": "Generated extracted prompt.",
                    "style_profile": {
                        "sentence_rhythm": "short",
                        "dialogue_style": "direct",
                    },
                },
                ensure_ascii=False,
            ),
            token_usage={"total_tokens": 11},
            elapsed_ms=9,
        )


class StyleTemplateServiceTests(unittest.TestCase):
    def test_style_template_crud_export_import_and_project_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
                )
                project_id = int(cursor.lastrowid)

            template_id = service.create_template(
                name="Author style",
                description="Structured style",
                detail_level="detailed",
                global_prompt="Keep narrative voice consistent.",
                rewrite_prompt="Use short, sharp dialogue.",
                style_profile={"dialogue_style": "sharp"},
                generated_prompt="Generated style prompt.",
                source_metadata={"source_type": "paste"},
            )
            service.bind_project_style(project_id, template_id)
            bound = service.get_project_style_template(project_id)
            exported = service.export_template(template_id)
            imported_id = service.import_template_text(exported)
            imported = service.get_template(imported_id)

            service.update_template(
                template_id,
                name="Author style v2",
                detail_level="standard",
                rewrite_prompt="Use clipped pacing.",
            )
            updated = service.get_template(template_id)
            service.delete_template(template_id)
            unbound = service.get_project_style_template(project_id)

        self.assertIsNotNone(bound)
        self.assertEqual("Author style", bound.name)
        self.assertIn("rusty.style_template", exported)
        self.assertIsNotNone(imported)
        self.assertEqual("Author style", imported.name)
        self.assertIsNotNone(updated)
        self.assertEqual("Author style v2", updated.name)
        self.assertEqual(2, updated.version)
        self.assertIsNone(unbound)

    def test_import_legacy_template_maps_known_fields_without_enabling_breakthrough(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            legacy_payload = {
                "name": "Legacy style",
                "rewriteTemplate": {
                    "commonPrompt": "Legacy rewrite rules.",
                    "categoryPrompts": {"dialogue": "Legacy dialogue rule."},
                },
                "identifyTemplate": {
                    "categories": [{"key": "dialogue", "name": "Dialogue"}],
                },
                "breakthroughTemplate": "Imported only as compatibility text.",
            }

            template_id = service.import_template_text(json.dumps(legacy_payload, ensure_ascii=False))
            template = service.get_template(template_id)
            metadata = json.loads(template.import_metadata_json) if template else {}
            profile = json.loads(template.style_profile_json) if template else {}

        self.assertIsNotNone(template)
        self.assertEqual("Legacy style", template.name)
        self.assertEqual("Legacy rewrite rules.", template.rewrite_prompt)
        self.assertEqual("Legacy rewrite rules.", template.generated_prompt)
        self.assertIn("legacy_category_prompts", profile)
        self.assertIn("legacy_identify_categories", profile)
        self.assertEqual("legacy", metadata["import_schema"])
        self.assertIn("legacy_breakthroughTemplate", metadata)

    def test_import_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            service = StyleTemplateService(Path(directory) / "rusty.db")

            with self.assertRaises(ValueError):
                service.import_template_text("{not valid json")

    def test_binding_rejects_deleted_project_or_template(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
                )
                project_id = int(cursor.lastrowid)
            template_id = service.create_template(name="Style")
            service.delete_template(template_id)

            with self.assertRaises(ValueError):
                service.bind_project_style(project_id, template_id)
            with self.assertRaises(ValueError):
                service.bind_project_style(project_id + 100, template_id)

    def test_ai_style_extraction_from_text_creates_structured_template(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            fake_client = FakeStyleAIClient()
            extraction = StyleExtractionService(database_path, ai_client=fake_client)

            template_id = extraction.extract_from_text(
                "Sample prose with a recognizable style.",
                name="Seed style",
                detail_level="detailed",
            )
            template = StyleTemplateService(database_path).get_template(template_id)
            metadata = json.loads(template.import_metadata_json) if template else {}
            source_metadata = json.loads(template.source_metadata_json) if template else {}
            profile = json.loads(template.style_profile_json) if template else {}

        self.assertIsNotNone(template)
        self.assertEqual("Extracted style", template.name)
        self.assertEqual("detailed", template.detail_level)
        self.assertEqual("Extracted global.", template.global_prompt)
        self.assertEqual("Generated extracted prompt.", template.generated_prompt)
        self.assertEqual("short", profile["sentence_rhythm"])
        self.assertEqual("ai_style_extraction", metadata["created_by"])
        self.assertEqual("paste", source_metadata["source_type"])
        self.assertIn("Required style_profile dimensions", fake_client.calls[0][2][-1]["content"])

    def test_ai_style_extraction_from_file_uses_import_parser_sample(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "style.txt"
            source_path.write_text("1. One\nFile sample prose.", encoding="utf-8")
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            extraction = StyleExtractionService(database_path, ai_client=FakeStyleAIClient())

            template_id = extraction.extract_from_file(source_path, name="File style")
            template = StyleTemplateService(database_path).get_template(template_id)
            source_metadata = json.loads(template.source_metadata_json) if template else {}

        self.assertIsNotNone(template)
        self.assertEqual("file", source_metadata["source_type"])
        self.assertEqual("txt", source_metadata["source_format"])
        self.assertEqual("style.txt", source_metadata["source_file_name"])

    def test_trial_write_uses_existing_style_template(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            style_service = StyleTemplateService(database_path)
            template_id = style_service.create_template(
                name="Style",
                global_prompt="Global style.",
                generated_prompt="Use this style.",
                style_profile={"dialogue_style": "direct"},
            )
            fake_client = FakeStyleAIClient()
            extraction = StyleExtractionService(database_path, ai_client=fake_client)

            sample = extraction.trial_write(template_id, "Two characters meet.", target_chars=120)

        self.assertEqual("A short styled sample.", sample)
        self.assertIn("around 120", fake_client.calls[0][2][-1]["content"])
        self.assertIn("Use this style.", fake_client.calls[0][2][-1]["content"])

    def test_ai_style_extraction_rejects_invalid_json_response(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            extraction = StyleExtractionService(database_path, ai_client=FakeStyleAIClient(invalid_json=True))

            with self.assertRaises(ValueError):
                extraction.extract_from_text("Sample prose.", name="Bad")


if __name__ == "__main__":
    unittest.main()
