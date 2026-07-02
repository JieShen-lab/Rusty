from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - depends on optional extra
    TestClient = None


@unittest.skipIf(TestClient is None, "FastAPI optional dependency is not installed")
class BackendApiTests(unittest.TestCase):
    def test_health_and_token_rejection(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)

            health = client.get("/api/health")
            rejected = client.post("/api/projects/preview", json={"source_path": str(root / "book.txt")})

        self.assertEqual(200, health.status_code)
        self.assertEqual({"ok": True, "app": "Rusty"}, health.json())
        self.assertEqual(403, rejected.status_code)

    def test_preview_create_and_project_visibility(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. One\nOriginal text.", encoding="utf-8")
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            preview = client.post("/api/projects/preview", json={"source_path": str(source)}, headers=headers)
            token = preview.json()["preview_token"]
            created = client.post("/api/projects", json={"preview_token": token, "project_name": "API Book"}, headers=headers)
            projects = client.get("/api/projects")
            chapters = client.get(f"/api/projects/{created.json()['id']}/chapters")

        self.assertEqual(200, preview.status_code)
        self.assertEqual(200, created.status_code)
        self.assertEqual("API Book", created.json()["name"])
        self.assertEqual(1, len(projects.json()))
        self.assertEqual(1, len(chapters.json()))

    def test_model_and_prompt_crud_do_not_expose_api_key(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            model_payload = {
                "display_name": "API Model",
                "provider": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "model_name": "example-model",
                "api_key": "secret-value",
                "temperature": 0.7,
                "max_tokens": None,
                "timeout_seconds": 60,
                "is_default": True,
            }
            created_model = client.post("/api/models", json=model_payload, headers=headers)
            models = client.get("/api/models")

            prompt_payload = {
                "name": "API Prompt",
                "global_rules": "Global",
                "summary_rules": "Summary",
                "scene_detection_rules": "Scene",
                "rewrite_rules": "Rewrite",
                "is_default": True,
            }
            created_prompt = client.post("/api/prompts", json=prompt_payload, headers=headers)
            prompts = client.get("/api/prompts")

            deleted_model = client.post(f"/api/models/{created_model.json()['id']}/delete", headers=headers)
            deleted_prompt = client.post(f"/api/prompts/{created_prompt.json()['id']}/delete", headers=headers)

        self.assertEqual(200, created_model.status_code)
        self.assertTrue(created_model.json()["has_api_key"])
        self.assertNotIn("secret-value", str(created_model.json()))
        self.assertEqual(1, len(models.json()))
        self.assertNotIn("secret-value", str(models.json()))
        self.assertEqual(200, created_prompt.status_code)
        self.assertEqual("API Prompt", created_prompt.json()["name"])
        self.assertEqual(1, len(prompts.json()))
        self.assertEqual(200, deleted_model.status_code)
        self.assertEqual(200, deleted_prompt.status_code)


if __name__ == "__main__":
    unittest.main()
