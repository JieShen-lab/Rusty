from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from backend.api import create_app
from rusty.services.ai_client import AIResponse
from rusty.services.model_service import ModelService
from rusty.services.pipeline_service import PipelineService
from rusty.services.project_service import ProjectService
from rusty.services.prompt_package_extraction_service import PromptPackageExtractionService
from rusty.services.prompt_service import PROMPT_PACKAGE_SCHEMA, PromptService


class RecordingAIClient:
    def __init__(self, extraction_payload: dict | None = None) -> None:
        self.calls: list[list[dict[str, str]]] = []
        self.extraction_payload = extraction_payload

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        user = messages[-1]["content"]
        if self.extraction_payload is not None:
            return AIResponse(json.dumps(self.extraction_payload, ensure_ascii=False), {}, 10)
        if "needs_rewrite" in user:
            return AIResponse('{"needs_rewrite": true, "labels": ["combat"], "reasoning": "battle"}', {}, 10)
        if "剧情扩展方案" in user:
            return AIResponse("强化冲突，并让主角在关键节点作出选择。", {}, 10)
        return AIResponse("改写后的章节正文内容。", {}, 10)


class PromptPackageTests(unittest.TestCase):
    def test_prompt_package_round_trip_preserves_rules_and_anchors(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = PromptService(database_path)
            template_id = service.create_template(
                name="Novel A",
                description="Unified package",
                global_rules="Keep facts.",
                rewrite_rules="General rewrite.",
                story_anchor={"mainline": ["A chooses"]},
                characters=[{"name": "Alice", "is_main": True}],
                scene_rules=[
                    {
                        "scene_key": "combat",
                        "display_name": "战斗场景",
                        "detection_prompt": "Detect battle.",
                        "rewrite_prompt": "Use clear action causality.",
                    }
                ],
            )
            content = service.export_template(template_id)
            imported_id = service.import_template_text(content)
            imported = service.get_template(imported_id)
            with patch.dict(os.environ, {"RUSTY_DATABASE_PATH": str(database_path)}):
                api_response = TestClient(create_app(database_path)).get("/api/prompts")

        self.assertIsNotNone(imported)
        self.assertEqual(PROMPT_PACKAGE_SCHEMA, json.loads(content)["schema"])
        self.assertEqual("A chooses", imported.story_anchor["mainline"][0])
        self.assertEqual("Alice", imported.characters[0]["name"])
        self.assertEqual("combat", imported.scene_rules[0].scene_key)
        self.assertEqual("Use clear action causality.", imported.scene_rules[0].rewrite_prompt)
        self.assertEqual(200, api_response.status_code)
        api_rules = [rule for item in api_response.json() for rule in item["scene_rules"]]
        self.assertIn("combat", [rule["scene_key"] for rule in api_rules])

    def test_plot_expansion_and_rewrite_use_structured_package(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. One\nAlice enters a battle.", encoding="utf-8")
            database_path = root / "rusty.db"
            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://example.test/v1",
                model_name="fake",
                is_default=True,
            )
            template_id = PromptService(database_path).create_template(
                name="Package",
                scene_detection_rules="Detect scenes.",
                rewrite_rules="General rewrite.",
                story_anchor={"mainline": ["Alice must choose"]},
                characters=[{"name": "Alice", "is_main": True}],
                scene_rules=[
                    {
                        "scene_key": "combat",
                        "display_name": "战斗场景",
                        "detection_prompt": "Detect battle.",
                        "rewrite_prompt": "Combat-specific rewrite.",
                    }
                ],
                is_default=True,
            )
            project_service.update_project_settings(project_id, prompt_template_id=template_id, processing_mode="rewrite")
            client = RecordingAIClient()
            pipeline = PipelineService(database_path, ai_client=client)
            pipeline.detect_scene(chapter_id)
            pipeline.expand_chapter_plot(chapter_id)
            pipeline.rewrite_chapter(chapter_id)
            outputs = pipeline.get_chapter_ai_outputs(chapter_id)

        rewrite_text = client.calls[-1][-1]["content"]
        self.assertTrue(outputs.plot_expansion_enabled)
        self.assertIn("强化冲突", outputs.expanded_plot)
        self.assertIn("Combat-specific rewrite.", rewrite_text)
        self.assertIn("Alice must choose", rewrite_text)
        self.assertIn("本章剧情扩展方案", rewrite_text)

    def test_analysis_project_extraction_creates_and_binds_package(self) -> None:
        payload = {
            "schema": PROMPT_PACKAGE_SCHEMA,
            "schema_version": 1,
            "name": "ignored",
            "system_rules": "Keep facts.",
            "summary_rules": "Summarize.",
            "scene_recognition": {"general_rules": "Detect.", "categories": []},
            "rewrite_rules": {"general": "Rewrite.", "specific": []},
            "story_anchor": {"mainline": ["Start"]},
            "characters": [{"name": "Alice"}],
            "metadata": {},
        }
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. One\nAlice starts her journey.", encoding="utf-8")
            database_path = root / "rusty.db"
            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source, root)
            project_service.update_project_settings(project_id, processing_mode="summary")
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://example.test/v1",
                model_name="fake",
                is_default=True,
            )
            service = PromptPackageExtractionService(database_path, ai_client=RecordingAIClient(payload))
            template_id = service.extract_from_project(project_id)
            template = PromptService(database_path).get_template(template_id)
            settings = project_service.get_project_settings(project_id)

        self.assertEqual("book", template.name)
        self.assertEqual(project_id, template.source_project_id)
        self.assertEqual(template_id, settings.prompt_template_id)
        self.assertEqual("summary", settings.processing_mode)


if __name__ == "__main__":
    unittest.main()
