from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.secrets import InMemorySecretStore
from rusty.services import ModelService, PromptService
from rusty.services.ai_client import AIResponse


class FakeModelTestClient:
    def __init__(self, should_fail: bool = False) -> None:
        self.should_fail = should_fail
        self.calls = []

    def chat(self, model, api_key, messages):
        self.calls.append((model, api_key, messages))
        if self.should_fail:
            raise RuntimeError("connection failed")
        return AIResponse(text="OK", token_usage={}, elapsed_ms=12)


class ModelPromptServiceTests(unittest.TestCase):
    def test_model_crud_stores_api_key_outside_main_database(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            secret_store = InMemorySecretStore()
            service = ModelService(database_path, secret_store=secret_store)

            model_id = service.create_model(
                display_name="OpenAI",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="gpt-test",
                api_key="secret-value",
                is_default=True,
            )
            models = service.list_models()
            api_key = service.get_api_key(model_id)
            connection = sqlite3.connect(database_path)
            try:
                row = connection.execute(
                    "SELECT api_key_secret_ref FROM ai_models WHERE id = ?",
                    (model_id,),
                ).fetchone()
            finally:
                connection.close()

            service.update_model(
                model_id=model_id,
                display_name="OpenAI Updated",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="gpt-test-2",
                api_key=None,
                temperature=0.2,
                timeout_seconds=30,
                is_default=False,
            )
            updated = service.list_models()[0]
            service.delete_model(model_id)
            remaining_models = service.list_models()

        self.assertEqual(1, len(models))
        self.assertTrue(models[0].has_api_key)
        self.assertEqual("secret-value", api_key)
        self.assertIsNotNone(row)
        self.assertNotEqual("secret-value", row[0])
        self.assertEqual("OpenAI Updated", updated.display_name)
        self.assertEqual(0.2, updated.temperature)
        self.assertEqual([], remaining_models)

    def test_model_connection_uses_saved_api_key_and_reports_failures(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            secret_store = InMemorySecretStore()
            service = ModelService(database_path, secret_store=secret_store)
            model_id = service.create_model(
                display_name="OpenAI",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="gpt-test",
                api_key="secret-value",
            )
            success_client = FakeModelTestClient()
            success = service.test_connection(model_id, ai_client=success_client)
            failure = service.test_connection(model_id, ai_client=FakeModelTestClient(should_fail=True))

        self.assertTrue(success.ok)
        self.assertEqual("OK", success.message)
        self.assertEqual(12, success.elapsed_ms)
        self.assertEqual("secret-value", success_client.calls[0][1])
        self.assertFalse(failure.ok)
        self.assertEqual("connection failed", failure.message)

    def test_model_reports_missing_key_when_secret_reference_is_stale(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            secret_store = InMemorySecretStore()
            service = ModelService(database_path, secret_store=secret_store)
            model_id = service.create_model(
                display_name="OpenAI",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="gpt-test",
                api_key="secret-value",
            )

            configured = service.get_model(model_id)
            stored_key = next(iter(secret_store.values))
            secret_store.delete_secret(f"memory:{stored_key}")
            missing = service.get_model(model_id)
            client = FakeModelTestClient()
            connection_result = service.test_connection(model_id, ai_client=client)

        self.assertIsNotNone(configured)
        self.assertTrue(configured.has_api_key)
        self.assertIsNotNone(missing)
        self.assertFalse(missing.has_api_key)
        self.assertFalse(connection_result.ok)
        self.assertIn("No API key", connection_result.message)
        self.assertEqual([], client.calls)

    def test_model_keys_are_isolated_between_databases(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            secret_store = InMemorySecretStore()
            first = ModelService(root / "first.db", secret_store=secret_store)
            second = ModelService(root / "second.db", secret_store=secret_store)
            first_id = first.create_model(
                display_name="First",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="first-model",
                api_key="first-secret",
            )
            second_id = second.create_model(
                display_name="Second",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="second-model",
                api_key="second-secret",
            )

            self.assertEqual(1, first_id)
            self.assertEqual(1, second_id)
            self.assertEqual("first-secret", first.get_api_key(first_id))
            self.assertEqual("second-secret", second.get_api_key(second_id))

            first.delete_model(first_id)

            self.assertEqual("second-secret", second.get_api_key(second_id))

    def test_prompt_template_and_project_prompt_crud(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = PromptService(database_path)
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
                )
                project_id = int(cursor.lastrowid)

            template_id = service.create_template(
                name="Default",
                global_rules="global",
                summary_rules="summary",
                rewrite_rules="rewrite",
                is_default=True,
            )
            template = service.get_template(template_id)
            service.update_template(
                template_id,
                name="Default v2",
                global_rules="global2",
                summary_rules="summary2",
                rewrite_rules="rewrite2",
                is_default=False,
            )
            updated = service.get_template(template_id)
            service.save_project_prompt(project_id, "global_override", "project text")
            project_prompts = service.list_project_prompts(project_id)
            service.delete_template(template_id)
            remaining_templates = service.list_templates()

        self.assertIsNotNone(template)
        self.assertEqual("Default", template.name)
        self.assertFalse(hasattr(template, "scene_detection_rules"))
        self.assertIsNotNone(updated)
        self.assertEqual("Default v2", updated.name)
        self.assertEqual(2, updated.version)
        self.assertEqual({"global_override": "project text"}, project_prompts)
        self.assertEqual([], remaining_templates)


if __name__ == "__main__":
    unittest.main()
