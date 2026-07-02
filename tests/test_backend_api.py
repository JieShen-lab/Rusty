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


if __name__ == "__main__":
    unittest.main()
