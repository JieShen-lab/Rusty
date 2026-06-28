from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services import ModelService, PipelineService, PromptService, ProjectService
from rusty.services.ai_client import AIClient, AIResponse


class FakeAIClient(AIClient):
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.calls = []

    def chat(self, model, api_key, messages):
        self.calls.append((model, messages))
        user_text = messages[-1]["content"]
        if self.fail_on and self.fail_on in user_text:
            raise RuntimeError("fake failure")
        if "Return JSON" in user_text:
            text = '{"needs_rewrite": true, "labels": ["expand"], "reasoning": "needs detail"}'
        elif "Rewrite" in user_text:
            text = "Rewritten chapter text."
        else:
            text = "Structured summary."
        return AIResponse(text=text, token_usage={"total_tokens": 3}, elapsed_ms=5)


class PipelineServiceTests(unittest.TestCase):
    def test_chapter_pipeline_persists_outputs_and_merge(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nOriginal text.", encoding="utf-8")

            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            PromptService(database_path).create_template(
                name="Default",
                summary_rules="Summarize",
                scene_detection_rules="Detect",
                rewrite_rules="Rewrite",
                is_default=True,
            )
            pipeline = PipelineService(database_path, ai_client=FakeAIClient())

            summary = pipeline.summarize_chapter(chapter_id)
            scene = pipeline.detect_scene(chapter_id)
            rewrite = pipeline.rewrite_chapter(chapter_id)
            merged = pipeline.merge_project_text(project_id)

            connection = sqlite3.connect(database_path)
            try:
                status_rows = connection.execute(
                    "SELECT stage, status FROM chapter_stage_status ORDER BY stage"
                ).fetchall()
                errors = connection.execute("SELECT COUNT(*) FROM chapter_errors").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual("Structured summary.", summary)
        self.assertIn("needs_rewrite", scene)
        self.assertEqual("Rewritten chapter text.", rewrite)
        self.assertIn("Rewritten chapter text.", merged)
        self.assertEqual(0, errors)
        self.assertEqual(
            [("rewrite", "completed"), ("scene_detection", "completed"), ("summary", "completed")],
            status_rows,
        )

    def test_pipeline_records_errors_and_supports_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nOriginal text.", encoding="utf-8")

            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            PromptService(database_path).create_template(
                name="Default",
                summary_rules="Summarize",
                scene_detection_rules="Detect",
                rewrite_rules="Rewrite",
                is_default=True,
            )

            failing = PipelineService(database_path, ai_client=FakeAIClient(fail_on="Summarize"))
            with self.assertRaises(RuntimeError):
                failing.summarize_chapter(chapter_id)

            retrying = PipelineService(database_path, ai_client=FakeAIClient())
            retried = retrying.retry_chapter_stage(chapter_id, "summary")
            result = retrying.run_project(project_id, should_pause=lambda: True)
            diagnostics_errors = retrying.list_chapter_errors(chapter_id)
            historical_errors = retrying.list_chapter_errors(chapter_id, include_resolved=True)
            diagnostics_statuses = retrying.list_chapter_stage_statuses(chapter_id)

            connection = sqlite3.connect(database_path)
            try:
                errors = connection.execute("SELECT COUNT(*) FROM chapter_errors").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual("Structured summary.", retried)
        self.assertEqual(1, errors)
        self.assertTrue(result.paused)
        self.assertEqual([], diagnostics_errors)
        self.assertEqual(1, len(historical_errors))
        self.assertEqual("summary", historical_errors[0].stage)
        self.assertIsNotNone(historical_errors[0].resolved_at)
        self.assertTrue(any(status.stage == "summary" for status in diagnostics_statuses))

    def test_pipeline_prefers_project_model_and_prompt_settings(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nOriginal text.", encoding="utf-8")

            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            model_service = ModelService(database_path)
            model_service.create_model(
                display_name="Default",
                provider="openai_compatible",
                base_url="https://api.default.test/v1",
                model_name="default-model",
                is_default=True,
            )
            project_model_id = model_service.create_model(
                display_name="Project",
                provider="openai_compatible",
                base_url="https://api.project.test/v1",
                model_name="project-model",
            )
            prompt_service = PromptService(database_path)
            prompt_service.create_template(name="Default", summary_rules="Default summary", is_default=True)
            project_template_id = prompt_service.create_template(name="Project", summary_rules="Project summary")
            project_service.update_project_settings(
                project_id=project_id,
                model_id=project_model_id,
                prompt_template_id=project_template_id,
            )

            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)
            pipeline.summarize_chapter(chapter_id)

        used_model, messages = fake_client.calls[0]
        self.assertEqual("project-model", used_model.model_name)
        self.assertIn("Project summary", messages[-1]["content"])


if __name__ == "__main__":
    unittest.main()
