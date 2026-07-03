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

    def test_style_template_api_crud_import_export_and_project_binding(self) -> None:
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

            rejected = client.post(
                "/api/styles",
                json={"name": "Rejected"},
            )
            preview = client.post("/api/projects/preview", json={"source_path": str(source)}, headers=headers)
            created_project = client.post(
                "/api/projects",
                json={"preview_token": preview.json()["preview_token"], "project_name": "Styled Book"},
                headers=headers,
            )
            project_id = created_project.json()["id"]

            style_payload = {
                "name": "API Style",
                "description": "For tests",
                "detail_level": "detailed",
                "global_prompt": "Style global.",
                "rewrite_prompt": "Style rewrite.",
                "style_profile": {"dialogue_style": "sharp"},
                "generated_prompt": "Generated style prompt.",
                "source_metadata": {"source_type": "paste"},
                "import_metadata": {},
            }
            created_style = client.post("/api/styles", json=style_payload, headers=headers)
            style_id = created_style.json()["id"]
            listed = client.get("/api/styles")
            fetched = client.get(f"/api/styles/{style_id}")
            rejected_bind = client.post(
                f"/api/projects/{project_id}/style",
                json={"style_template_id": style_id},
            )
            bound = client.post(
                f"/api/projects/{project_id}/style",
                json={"style_template_id": style_id},
                headers=headers,
            )
            project_style = client.get(f"/api/projects/{project_id}/style")
            rejected_export = client.post(f"/api/styles/{style_id}/export")
            exported = client.post(f"/api/styles/{style_id}/export", headers=headers)
            rejected_import = client.post(
                "/api/styles/import",
                json={"content": exported.json()["content"]},
            )
            imported = client.post(
                "/api/styles/import",
                json={"content": exported.json()["content"]},
                headers=headers,
            )
            updated = client.post(
                f"/api/styles/{style_id}",
                json={**style_payload, "name": "API Style v2", "detail_level": "standard"},
                headers=headers,
            )
            unbound = client.post(
                f"/api/projects/{project_id}/style",
                json={"style_template_id": None},
                headers=headers,
            )
            deleted = client.post(f"/api/styles/{style_id}/delete", headers=headers)

        self.assertEqual(403, rejected.status_code)
        self.assertEqual(200, created_style.status_code)
        self.assertEqual("API Style", created_style.json()["name"])
        self.assertEqual({"dialogue_style": "sharp"}, created_style.json()["style_profile"])
        self.assertEqual(1, len(listed.json()))
        self.assertEqual("API Style", fetched.json()["name"])
        self.assertEqual(403, rejected_bind.status_code)
        self.assertEqual(style_id, bound.json()["style_template"]["id"])
        self.assertEqual(style_id, project_style.json()["style_template"]["id"])
        self.assertEqual(403, rejected_export.status_code)
        self.assertIn("rusty.style_template", exported.json()["content"])
        self.assertEqual(403, rejected_import.status_code)
        self.assertEqual("API Style", imported.json()["name"])
        self.assertEqual("API Style v2", updated.json()["name"])
        self.assertEqual("standard", updated.json()["detail_level"])
        self.assertIsNone(unbound.json()["style_template"])
        self.assertEqual(200, deleted.status_code)

    def test_style_import_rejects_bad_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)

            response = client.post(
                "/api/styles/import",
                json={"content": "{bad json"},
                headers={"X-Rusty-Token": "test-token"},
            )

        self.assertEqual(400, response.status_code)
        self.assertEqual("validation_error", response.json()["error"])


if __name__ == "__main__":
    unittest.main()
