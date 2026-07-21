from __future__ import annotations

import sqlite3
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services import AnchorService, ModelService, PipelineService, PromptService, ProjectService, StyleTemplateService
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.pipeline_service import RewriteOutputError, _apply_rewrite_response


class FakeAIClient(AIClient):
    def __init__(self, fail_on: str | None = None, scene_needs_rewrite: bool = True) -> None:
        self.fail_on = fail_on
        self.scene_needs_rewrite = scene_needs_rewrite
        self.calls = []

    def chat(self, model, api_key, messages):
        self.calls.append((model, messages))
        user_text = "\n".join(message["content"] for message in messages if message["role"] == "user")
        if self.fail_on and self.fail_on in user_text:
            raise RuntimeError("fake failure")
        if "AVAILABLE CATEGORIES" in user_text:
            text = (
                '{"analysis":{"has_target_content":true,"categories":["expand"],'
                '"markers":[{"category_id":"expand","category_name":"Expand",'
                '"expand_description":"needs detail","evidence":"Original text."}],'
                '"reasoning":"needs detail"}}'
                if self.scene_needs_rewrite
                else '{"analysis":{"has_target_content":false,"categories":[],"markers":[],'
                '"reasoning":"preserve original"}}'
            )
        elif "RUSTY OUTPUT CONTRACT" in user_text:
            match = re.search(
                r"--- ORIGINAL CHAPTER: .*? ---\n(.*?)\n--- END ORIGINAL CHAPTER ---",
                user_text,
                re.DOTALL,
            )
            anchor = match.group(1) if match else "Original text."
            text = json.dumps({"anchor": anchor, "expanded": "Rewritten chapter text."})
        else:
            text = "Structured summary."
        return AIResponse(text=text, token_usage={"total_tokens": 3}, elapsed_ms=5)


class SequenceAIClient(AIClient):
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        if not self.responses:
            raise AssertionError("No fake response remains")
        return AIResponse(text=self.responses.pop(0), token_usage={"total_tokens": 5}, elapsed_ms=7)


class PipelineServiceTests(unittest.TestCase):
    def test_refusal_detection_does_not_reject_fictional_dialogue_inside_valid_json(self) -> None:
        with self.assertRaises(RewriteOutputError) as refusal:
            _apply_rewrite_response("Original text.", "I'm sorry, but I can't assist with that.", "anchor_expand")
        accepted = _apply_rewrite_response(
            "Original text.",
            json.dumps({"anchor": "Original text.", "expanded": "她说：我无法协助。"}, ensure_ascii=False),
            "anchor_expand",
        )

        self.assertEqual("refusal_detected", refusal.exception.code)
        self.assertEqual("她说：我无法协助。", accepted["rewritten_text"])

    def test_summary_project_only_runs_summary_stage(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nAlpha.\n\n2. Two\nBeta.", encoding="utf-8")

            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            project_service.update_project_settings(project_id, processing_mode="summary")
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
                rewrite_rules="Rewrite",
                is_default=True,
            )
            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)

            result = pipeline.run_summary_project(project_id)
            chapters = project_service.list_chapters(project_id)
            outputs = [pipeline.get_chapter_ai_outputs(chapter.id) for chapter in chapters]
            project = project_service.get_project(project_id)

        self.assertEqual(2, result.processed)
        self.assertEqual(0, result.failed)
        self.assertEqual(2, len(fake_client.calls))
        self.assertTrue(all(output.plot_summary == "Structured summary." for output in outputs))
        self.assertTrue(all(output.needs_rewrite is None for output in outputs))
        self.assertTrue(all(chapter.rewritten_text is None for chapter in chapters))
        self.assertIsNotNone(project)
        self.assertEqual("summarized", project.status)
        self.assertEqual(2, project.completed_chapters)

    def test_project_pipeline_rejects_missing_prompt_before_processing(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nOriginal text.", encoding="utf-8")

            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            pipeline = PipelineService(database_path, ai_client=FakeAIClient())

            with self.assertRaisesRegex(ValueError, "No prompt template configured"):
                pipeline.run_project(project_id)

            project = project_service.get_project(project_id)

        self.assertIsNotNone(project)
        self.assertEqual("imported", project.status)

    def test_manual_stage_records_missing_prompt_error(self) -> None:
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
            pipeline = PipelineService(database_path, ai_client=FakeAIClient())

            with self.assertRaisesRegex(ValueError, "No prompt template configured"):
                pipeline.summarize_chapter(chapter_id)

            errors = pipeline.list_chapter_errors(chapter_id)
            statuses = pipeline.list_chapter_stage_statuses(chapter_id)

        self.assertEqual(1, len(errors))
        self.assertEqual("summary", errors[0].stage)
        self.assertIn("No prompt template configured", errors[0].message)
        self.assertEqual("failed", statuses[0].status)

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
                rewrite_rules="Rewrite",
                is_default=True,
            )
            pipeline = PipelineService(database_path, ai_client=FakeAIClient())

            summary = pipeline.summarize_chapter(chapter_id)
            scene = pipeline.detect_scene(chapter_id)
            rewrite = pipeline.rewrite_chapter(chapter_id)
            merged = pipeline.merge_project_text(project_id)
            outputs = pipeline.get_chapter_ai_outputs(chapter_id)

            connection = sqlite3.connect(database_path)
            try:
                status_rows = connection.execute(
                    "SELECT stage, status FROM chapter_stage_status ORDER BY stage"
                ).fetchall()
                rewrite_row = connection.execute(
                    """
                    SELECT rewrite_source, prompt_snapshot_json, anchor_snapshot_json
                    FROM chapter_rewrites
                    WHERE chapter_id = ?
                    """,
                    (chapter_id,),
                ).fetchone()
                errors = connection.execute("SELECT COUNT(*) FROM chapter_errors").fetchone()[0]
            finally:
                connection.close()

        self.assertEqual("Structured summary.", summary)
        self.assertIn("has_target_content", scene)
        self.assertEqual("Rewritten chapter text.", rewrite)
        self.assertIn("Rewritten chapter text.", merged)
        self.assertEqual("Structured summary.", outputs.plot_summary)
        self.assertTrue(outputs.needs_rewrite)
        self.assertEqual(["expand"], outputs.scene_labels)
        self.assertEqual("needs detail", outputs.scene_reasoning)
        self.assertEqual("expand", outputs.scene_markers[0]["category_id"])
        self.assertEqual("ai", outputs.rewrite_source)
        self.assertIsNotNone(outputs.rewritten_word_count)
        self.assertGreater(outputs.rewritten_word_count, 0)
        self.assertEqual("ai", rewrite_row[0])
        self.assertIn("RUSTY OUTPUT CONTRACT", rewrite_row[1])
        self.assertIn("rusty.native.rewrite.v1", rewrite_row[1])
        self.assertEqual(
            {"style_template": None, "outline_template": None, "character_cards": []},
            json.loads(rewrite_row[2]),
        )
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

    def test_run_project_marks_chapters_kept_original_when_scene_does_not_need_rewrite(self) -> None:
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
                rewrite_rules="Rewrite",
                is_default=True,
            )

            fake_client = FakeAIClient(scene_needs_rewrite=False)
            pipeline = PipelineService(database_path, ai_client=fake_client)
            result = pipeline.run_project(project_id)
            chapter = project_service.get_chapter(chapter_id)
            project = project_service.get_project(project_id)

        self.assertEqual(1, result.processed)
        self.assertEqual(1, result.skipped)
        self.assertEqual(0, result.failed)
        self.assertIsNotNone(chapter)
        self.assertEqual("kept_original", chapter.status)
        self.assertIsNone(chapter.rewritten_text)
        self.assertIsNotNone(project)
        self.assertEqual(1, project.completed_chapters)
        self.assertEqual(2, len(fake_client.calls))

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

    def test_pipeline_applies_project_prompt_overrides(self) -> None:
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
            prompt_service = PromptService(database_path)
            prompt_service.create_template(
                name="Default",
                global_rules="Base global",
                summary_rules="Base summary",
                rewrite_rules="Base rewrite",
                scene_rules=[{
                    "scene_key": "combat",
                    "display_name": "Combat",
                    "detection_prompt": "Detect combat.",
                }],
                is_default=True,
            )
            prompt_service.save_project_prompt(project_id, "global_override", "Project global")
            prompt_service.save_project_prompt(project_id, "summary_rules", "Project summary")
            prompt_service.save_project_prompt(project_id, "scene_detection_rules", "Project scene")
            prompt_service.save_project_prompt(project_id, "rewrite_rules", "Project rewrite")

            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)
            pipeline.summarize_chapter(chapter_id)
            pipeline.detect_scene(chapter_id)
            pipeline.rewrite_chapter(chapter_id)

        summary_messages = fake_client.calls[0][1]
        scene_messages = fake_client.calls[1][1]
        rewrite_messages = fake_client.calls[2][1]
        self.assertIn("Base global", summary_messages[0]["content"])
        self.assertIn("Project global", summary_messages[0]["content"])
        self.assertIn("Base summary", summary_messages[-1]["content"])
        self.assertIn("Project summary", summary_messages[-1]["content"])
        self.assertIn("Detect combat.", scene_messages[-1]["content"])
        self.assertNotIn("Project scene", scene_messages[-1]["content"])
        self.assertIn("Base rewrite", rewrite_messages[-1]["content"])
        self.assertIn("Project rewrite", rewrite_messages[-1]["content"])

    def test_rewrite_injects_bound_style_template_and_records_snapshot(self) -> None:
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
                global_rules="Base global",
                rewrite_rules="Base rewrite",
                is_default=True,
            )
            style_service = StyleTemplateService(database_path)
            style_id = style_service.create_template(
                name="Sharp style",
                detail_level="detailed",
                global_prompt="Style global rule.",
                rewrite_prompt="Style rewrite rule.",
                generated_prompt="Generated style instruction.",
                style_profile={"sentence_rhythm": "short"},
            )
            style_service.bind_project_style(project_id, style_id)

            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)
            pipeline.rewrite_chapter(chapter_id)

            connection = sqlite3.connect(database_path)
            try:
                anchor_snapshot_json = connection.execute(
                    """
                    SELECT anchor_snapshot_json
                    FROM chapter_rewrites
                    WHERE chapter_id = ?
                    """,
                    (chapter_id,),
                ).fetchone()[0]
            finally:
                connection.close()

        messages = fake_client.calls[0][1]
        anchor_snapshot = json.loads(anchor_snapshot_json)
        self.assertIn("Base global", messages[0]["content"])
        self.assertIn("Style global rule.", messages[0]["content"])
        self.assertIn("Style template (Sharp style)", messages[-1]["content"])
        self.assertIn("Generated style instruction.", messages[-1]["content"])
        self.assertEqual(style_id, anchor_snapshot["style_template"]["id"])
        self.assertEqual("Sharp style", anchor_snapshot["style_template"]["name"])

    def test_rewrite_injects_outline_and_relevant_character_cards_only(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nBobby makes a choice. Original text.", encoding="utf-8")

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
                global_rules="Base global",
                summary_rules="Summarize",
                rewrite_rules="Base rewrite",
                is_default=True,
            )
            anchor_service = AnchorService(database_path)
            outline_id = anchor_service.create_outline_template(
                name="Arc outline",
                detail_level="detailed",
                outline={"fixed_beats": ["Bobby chooses"]},
                anchor_prompt="Keep the choice as the chapter pivot.",
            )
            main_id = anchor_service.create_character_card(
                name="Alice",
                priority=90,
                is_main=True,
                personality="Direct and protective.",
            )
            matched_id = anchor_service.create_character_card(
                name="Bob",
                aliases=["Bobby"],
                priority=40,
                speech_style="Careful, plain speech.",
            )
            ignored_id = anchor_service.create_character_card(
                name="Carol",
                priority=40,
                speech_style="Should not appear.",
            )
            anchor_service.bind_project_outline(project_id, outline_id)
            anchor_service.bind_project_character(project_id, main_id, sort_order=1)
            anchor_service.bind_project_character(project_id, matched_id, sort_order=2)
            anchor_service.bind_project_character(project_id, ignored_id, sort_order=3)

            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)
            pipeline.summarize_chapter(chapter_id)
            pipeline.detect_scene(chapter_id)
            pipeline.rewrite_chapter(chapter_id)

            connection = sqlite3.connect(database_path)
            try:
                anchor_snapshot_json = connection.execute(
                    """
                    SELECT anchor_snapshot_json
                    FROM chapter_rewrites
                    WHERE chapter_id = ?
                    """,
                    (chapter_id,),
                ).fetchone()[0]
            finally:
                connection.close()

        summary_messages = fake_client.calls[0][1]
        scene_messages = fake_client.calls[1][1]
        rewrite_messages = fake_client.calls[2][1]
        rewrite_user_text = rewrite_messages[-1]["content"]
        anchor_snapshot = json.loads(anchor_snapshot_json)

        self.assertNotIn("Arc outline", summary_messages[-1]["content"])
        self.assertNotIn("Character anchors", scene_messages[-1]["content"])
        self.assertIn("Plot outline anchor (Arc outline)", rewrite_user_text)
        self.assertIn("Keep the choice as the chapter pivot.", rewrite_user_text)
        self.assertIn("Name: Alice", rewrite_user_text)
        self.assertIn("Name: Bob", rewrite_user_text)
        self.assertNotIn("Name: Carol", rewrite_user_text)
        self.assertEqual(outline_id, anchor_snapshot["outline_template"]["id"])
        self.assertEqual(["Alice", "Bob"], [card["name"] for card in anchor_snapshot["character_cards"]])

    def test_rewrite_uses_project_targets_and_records_target_word_count(self) -> None:
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
            PromptService(database_path).create_template(name="Default", rewrite_rules="Rewrite", is_default=True)
            project_service.update_project_settings(
                project_id=project_id,
                target_word_count=10,
                min_expansion_ratio=1.1,
            )

            fake_client = FakeAIClient()
            pipeline = PipelineService(database_path, ai_client=fake_client)
            pipeline.rewrite_chapter(chapter_id)

            connection = sqlite3.connect(database_path)
            try:
                target_word_count, actual_word_count, expansion_ratio = connection.execute(
                    """
                    SELECT target_word_count, actual_word_count, expansion_ratio
                    FROM chapter_rewrites
                    WHERE chapter_id = ?
                    """,
                    (chapter_id,),
                ).fetchone()
            finally:
                connection.close()

        user_text = fake_client.calls[0][1][-1]["content"]
        self.assertIn("Target length: at least 10", user_text)
        self.assertIn("Minimum expansion ratio: 1.10x", user_text)
        self.assertEqual(10, target_word_count)
        self.assertGreaterEqual(actual_word_count, 10)
        self.assertGreaterEqual(expansion_ratio, 1.1)

    def test_rewrite_target_validation_records_error(self) -> None:
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
            PromptService(database_path).create_template(name="Default", rewrite_rules="Rewrite", is_default=True)
            project_service.update_project_settings(project_id=project_id, target_word_count=10_000)

            pipeline = PipelineService(database_path, ai_client=FakeAIClient())
            with self.assertRaises(ValueError):
                pipeline.rewrite_chapter(chapter_id)
            errors = pipeline.list_chapter_errors(chapter_id)

        self.assertEqual(1, len(errors))
        self.assertEqual("rewrite", errors[0].stage)
        self.assertIn("shorter than target", errors[0].message)

    def test_anchor_rewrite_repairs_invalid_output_and_records_exact_attempts(self) -> None:
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
                global_rules="User global rule.",
                rewrite_rules="User rewrite rule.",
                is_default=True,
            )
            project_service.update_project_settings(project_id, max_attempts=2, rewrite_mode="anchor_expand")
            fake_client = SequenceAIClient(
                [
                    '{"anchor":"missing text","expanded":"first try"}',
                    '{"anchor":"Original text.","expanded":"Expanded original text."}',
                ]
            )
            pipeline = PipelineService(database_path, ai_client=fake_client)

            result = pipeline.rewrite_chapter(chapter_id)
            attempts = pipeline.list_generation_attempts(chapter_id, "rewrite")
            preview = pipeline.preview_chapter_prompt(chapter_id, "rewrite")

        self.assertEqual("Expanded original text.", result)
        self.assertEqual(2, len(attempts))
        self.assertEqual("anchor_missing", attempts[0]["error_type"])
        self.assertIsNone(attempts[1]["error_type"])
        self.assertEqual("anchor_missing", attempts[1]["request"]["provenance"]["repair_for"])
        self.assertEqual("fake-model", attempts[1]["request"]["model"]["model_name"])
        self.assertNotIn("api_key", attempts[1]["request"]["model"])
        self.assertEqual("rusty.native.rewrite.v1", preview["ruleset_id"])
        self.assertIn("[RUSTY NATIVE RULES", preview["messages"][0]["content"])
        self.assertIn("[USER-OWNED SYSTEM RULES]", preview["messages"][0]["content"])
        self.assertIn("User global rule.", preview["messages"][0]["content"])
        self.assertIn("User rewrite rule.", preview["messages"][1]["content"])

    def test_anchor_rewrite_rejects_ambiguous_anchor(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nAgain and Again.", encoding="utf-8")
            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            ModelService(database_path).create_model(
                display_name="Fake", provider="openai_compatible", base_url="https://example.test/v1",
                model_name="fake", is_default=True,
            )
            PromptService(database_path).create_template(name="Default", rewrite_rules="Expand.", is_default=True)
            project_service.update_project_settings(project_id, max_attempts=1)
            pipeline = PipelineService(
                database_path,
                ai_client=SequenceAIClient(['{"anchor":"Again","expanded":"Once more"}']),
            )

            with self.assertRaisesRegex(ValueError, "occurs 2 times"):
                pipeline.rewrite_chapter(chapter_id)
            attempts = pipeline.list_generation_attempts(chapter_id, "rewrite")

        self.assertEqual("anchor_ambiguous", attempts[0]["error_type"])

    def test_full_rewrite_mode_preserves_legacy_whole_chapter_behavior(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "book.txt"
            source_path.write_text("1. One\nOriginal text.", encoding="utf-8")
            project_service = ProjectService(database_path)
            project_id = project_service.import_book(source_path, root)
            chapter_id = project_service.list_chapters(project_id)[0].id
            ModelService(database_path).create_model(
                display_name="Fake", provider="openai_compatible", base_url="https://example.test/v1",
                model_name="fake", is_default=True,
            )
            PromptService(database_path).create_template(name="Default", rewrite_rules="Rewrite.", is_default=True)
            project_service.update_project_settings(project_id, rewrite_mode="full_rewrite", max_attempts=1)
            pipeline = PipelineService(database_path, ai_client=SequenceAIClient(["A complete replacement chapter."]))

            result = pipeline.rewrite_chapter(chapter_id)
            outputs = pipeline.get_chapter_ai_outputs(chapter_id)

        self.assertEqual("A complete replacement chapter.", result)
        self.assertEqual("full_rewrite", outputs.rewrite_mode)
        self.assertEqual("A complete replacement chapter.", outputs.rewrite_expanded)


if __name__ == "__main__":
    unittest.main()
