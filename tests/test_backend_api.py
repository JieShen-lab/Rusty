from __future__ import annotations

import importlib
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.ai_client import AIClient, AIResponse
from rusty.db import session

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:  # pragma: no cover - depends on optional extra
    TestClient = None


class FakeStyleAIClient(AIClient):
    def chat(self, model, api_key, messages):
        user_text = messages[-1]["content"]
        if "Write a short validation sample" in user_text:
            return AIResponse(text="Styled trial text.", token_usage={"total_tokens": 3}, elapsed_ms=5)
        if "structured outline template" in user_text:
            return AIResponse(
                text=(
                    '{"name":"API Extracted Outline","description":"Extracted outline",'
                    '"anchor_prompt":"Keep the fixed beats.",'
                    '"outline":{"fixed_plot_beats":["choice","fallout"],"must_keep_details":["lamp"]}}'
                ),
                token_usage={"total_tokens": 12},
                elapsed_ms=6,
            )
        if "Only extract the character named" in user_text:
            return AIResponse(
                text=(
                    '{"evidence_found":true,"name":"Alice","aliases":["A"],"identity":"Lead","age":"",'
                    '"description":"Main role","stable_fields":['
                    '{"dimension_id":"appearance","label":"外貌","value":""},'
                    '{"dimension_id":"relationships","label":"人物关系","value":"Protects Bob."},'
                    '{"dimension_id":"personality","label":"性格","value":"Direct."},'
                    '{"dimension_id":"speech_style","label":"语言风格","value":"Short."},'
                    '{"dimension_id":"action_constraints","label":"动作习惯 / 动作约束","value":"Acts quickly."},'
                    '{"dimension_id":"abilities_background","label":"能力与背景","value":""},'
                    '{"dimension_id":"anti_ooc_rules","label":"反 OOC 规则","value":"Do not make her passive."}],'
                    '"suggested_tags":["主角"]}'
                ),
                token_usage={"total_tokens": 18},
                elapsed_ms=7,
            )
        return AIResponse(
            text=(
                '{"name":"API Extracted Style","description":"Extracted by API",'
                '"global_prompt":"API global.","rewrite_prompt":"API rewrite.",'
                '"generated_prompt":"API generated.",'
                '"style_profile":{"sentence_rhythm":"short","dialogue_style":"direct"}}'
            ),
            token_usage={"total_tokens": 9},
            elapsed_ms=8,
        )


def create_rewrite_prompt(client, headers) -> int:
    response = client.post(
        "/api/prompts",
        json={"name": "Test Rewrite Prompt", "global_rules": "Keep facts.", "rewrite_rules": "Rewrite clearly."},
        headers=headers,
    )
    return int(response.json()["id"])


def create_analysis_prompt(client, headers) -> int:
    response = client.post(
        "/api/analysis-prompts",
        json={
            "name": "Test Analysis Prompt",
            "analysis_dimensions": "Action, dialogue, relationships, rhythm.",
            "evidence_rules": "Cite short evidence and remove names from reusable rules.",
            "synthesis_rules": "Keep repeated patterns only.",
            "output_requirements": "Return strict JSON.",
        },
        headers=headers,
    )
    return int(response.json()["id"])


@unittest.skipIf(TestClient is None, "FastAPI optional dependency is not installed")
class BackendApiTests(unittest.TestCase):
    def test_create_app_bootstraps_database_once(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            api = importlib.import_module("backend.api")
            database_path = Path(directory) / "rusty.db"
            with mock.patch(
                "backend.api.initialize_database_file",
                wraps=api.initialize_database_file,
            ) as bootstrap:
                api.create_app(database_path)

        bootstrap.assert_called_once_with(database_path)

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
            created = client.post(
                "/api/projects",
                json={
                    "preview_token": token,
                    "project_name": "API Book",
                    "project_kind": "branch",
                },
                headers=headers,
            )
            projects = client.get("/api/projects")
            chapters = client.get(f"/api/projects/{created.json()['id']}/chapters")
            detail = client.get(f"/api/projects/{created.json()['id']}")

        self.assertEqual(200, preview.status_code)
        self.assertEqual(200, created.status_code)
        self.assertEqual("API Book", created.json()["name"])
        self.assertEqual("branch", created.json()["project_kind"])
        self.assertEqual(1, len(projects.json()))
        self.assertEqual("branch", projects.json()[0]["project_kind"])
        self.assertEqual(1, len(chapters.json()))
        self.assertEqual("branch", detail.json()["project"]["project_kind"])
        self.assertEqual("manual", detail.json()["settings"]["processing_mode"])

    def test_configured_txt_split_is_preserved_when_project_is_created(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "configured-split.txt"
            source.write_text("第一章 起\n甲。\n\n第二章 承\n乙。", encoding="utf-8")
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            preview = client.post(
                "/api/projects/preview",
                json={
                    "source_path": str(source),
                    "workspace_path": str(root / "workspace"),
                    "split": {
                        "mode": "simple",
                        "line_prefix": "第",
                        "number_style": "chinese",
                        "title_suffixes": ["章"],
                    },
                },
                headers=headers,
            )
            prompt_id = create_rewrite_prompt(client, headers)
            created = client.post(
                "/api/projects",
                json={
                    "preview_token": preview.json()["preview_token"],
                    "project_name": "Configured split",
                    "purpose": "rewrite",
                    "prompt_template_id": prompt_id,
                },
                headers=headers,
            )
            project_id = created.json()["id"]
            chapters = client.get(f"/api/projects/{project_id}/chapters").json()
            detail = client.get(f"/api/projects/{project_id}").json()

        self.assertEqual(200, preview.status_code)
        self.assertEqual("simple", preview.json()["split_mode"])
        self.assertEqual(["第一章 起", "第二章 承"], [item["title"] for item in preview.json()["chapters"]])
        self.assertEqual(200, created.status_code)
        self.assertEqual(["第一章 起", "第二章 承"], [item["title"] for item in chapters])
        self.assertNotEqual(1, detail["settings"]["txt_split_rule_id"])

    def test_export_plan_api_controls_export_order_titles_and_exclusions(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text(
                "1. One\nAlpha text.\n\n2. Two\nBeta text.\n\n3. Three\nGamma text.",
                encoding="utf-8",
            )
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            preview = client.post("/api/projects/preview", json={"source_path": str(source)}, headers=headers)
            prompt_id = create_rewrite_prompt(client, headers)
            created = client.post(
                "/api/projects",
                json={"preview_token": preview.json()["preview_token"], "project_name": "Export Book", "prompt_template_id": prompt_id},
                headers=headers,
            )
            project_id = created.json()["id"]
            chapters = client.get(f"/api/projects/{project_id}/chapters").json()
            prompt_preview = client.get(f"/api/chapters/{chapters[0]['id']}/prompt-preview?stage=rewrite")
            generation_attempts = client.get(f"/api/chapters/{chapters[0]['id']}/generation-attempts?stage=rewrite")
            default_plan = client.get(f"/api/projects/{project_id}/export-plan")
            save_without_token = client.post(
                f"/api/projects/{project_id}/export-plan",
                json={"items": default_plan.json()},
            )
            updated_plan = [
                {
                    "chapter_id": chapters[1]["id"],
                    "export_order": 1,
                    "export_title": "Renamed Two",
                    "include_in_export": True,
                },
                {
                    "chapter_id": chapters[0]["id"],
                    "export_order": 2,
                    "export_title": chapters[0]["title"],
                    "include_in_export": False,
                },
                {
                    "chapter_id": chapters[2]["id"],
                    "export_order": 3,
                    "export_title": "Renamed Three",
                    "include_in_export": True,
                },
            ]
            saved_plan = client.post(
                f"/api/projects/{project_id}/export-plan",
                json={"items": updated_plan},
                headers=headers,
            )
            exported = client.post(f"/api/projects/{project_id}/export/txt", headers=headers)
            exported_text = Path(exported.json()["output_path"]).read_text(encoding="utf-8")

        self.assertEqual(200, default_plan.status_code)
        self.assertEqual(200, prompt_preview.status_code)
        self.assertEqual("rusty.native.rewrite.v1", prompt_preview.json()["ruleset_id"])
        self.assertEqual([], generation_attempts.json())
        self.assertEqual(["1. One", "2. Two", "3. Three"], [item["export_title"] for item in default_plan.json()])
        self.assertEqual(["original", "original", "original"], [item["source_status"] for item in default_plan.json()])
        self.assertEqual(403, save_without_token.status_code)
        self.assertEqual(200, saved_plan.status_code)
        self.assertEqual(["Renamed Two", "1. One", "Renamed Three"], [item["export_title"] for item in saved_plan.json()])
        self.assertEqual([True, False, True], [item["include_in_export"] for item in saved_plan.json()])
        self.assertIn("Renamed Two", exported_text)
        self.assertIn("Renamed Three", exported_text)
        self.assertNotIn("Alpha text.", exported_text)

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
        self.assertNotIn("scene_detection_rules", created_prompt.json())
        self.assertEqual(1, len(prompts.json()))
        self.assertNotIn("scene_detection_rules", prompts.json()[0])
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
            prompt_id = create_rewrite_prompt(client, headers)
            created_project = client.post(
                "/api/projects",
                json={"preview_token": preview.json()["preview_token"], "project_name": "Styled Book", "prompt_template_id": prompt_id},
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

    def test_style_extraction_and_trial_write_api(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db", style_ai_client=FakeStyleAIClient())
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            model_payload = {
                "display_name": "API Model",
                "provider": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "model_name": "example-model",
                "api_key": None,
                "temperature": 0.7,
                "max_tokens": None,
                "timeout_seconds": 60,
                "is_default": True,
            }
            client.post("/api/models", json=model_payload, headers=headers)
            rejected = client.post(
                "/api/styles/extract",
                json={"name": "Rejected", "sample_text": "sample"},
            )
            invalid_source = client.post(
                "/api/styles/extract",
                json={"name": "Invalid", "sample_text": "sample", "source_path": str(root / "book.txt")},
                headers=headers,
            )
            extracted = client.post(
                "/api/styles/extract",
                json={"name": "Seed", "detail_level": "detailed", "sample_text": "Sample style prose."},
                headers=headers,
            )
            template_id = extracted.json()["id"]
            trial = client.post(
                f"/api/styles/{template_id}/trial-write",
                json={"sample_scene": "A character opens a door.", "target_chars": 120},
                headers=headers,
            )
            rejected_trial = client.post(
                f"/api/styles/{template_id}/trial-write",
                json={"sample_scene": "A character opens a door."},
            )

        self.assertEqual(403, rejected.status_code)
        self.assertEqual(400, invalid_source.status_code)
        self.assertEqual(200, extracted.status_code)
        self.assertEqual("API Extracted Style", extracted.json()["name"])
        self.assertEqual("detailed", extracted.json()["detail_level"])
        self.assertEqual("short", extracted.json()["style_profile"]["sentence_rhythm"])
        self.assertEqual("ai_style_extraction", extracted.json()["import_metadata"]["created_by"])
        self.assertEqual(200, trial.status_code)
        self.assertEqual({"ok": True, "text": "Styled trial text."}, trial.json())
        self.assertEqual(403, rejected_trial.status_code)

    def test_style_extraction_from_file_api_uses_validated_source_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "style.txt"
            source.write_text("1. One\nFile sample prose.", encoding="utf-8")
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db", style_ai_client=FakeStyleAIClient())
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}
            model_payload = {
                "display_name": "API Model",
                "provider": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "model_name": "example-model",
                "api_key": None,
                "temperature": 0.7,
                "max_tokens": None,
                "timeout_seconds": 60,
                "is_default": True,
            }
            client.post("/api/models", json=model_payload, headers=headers)

            unsupported = client.post(
                "/api/styles/extract",
                json={"name": "Bad", "source_path": str(root / "style.pdf")},
                headers=headers,
            )
            extracted = client.post(
                "/api/styles/extract",
                json={"name": "File seed", "source_path": str(source)},
                headers=headers,
            )

        self.assertEqual(400, unsupported.status_code)
        self.assertEqual(200, extracted.status_code)
        self.assertEqual("file", extracted.json()["source_metadata"]["source_type"])
        self.assertEqual("style.txt", extracted.json()["source_metadata"]["source_file_name"])

    def test_outline_and_character_anchor_api_crud_and_project_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("1. One\nBobby makes a choice.", encoding="utf-8")
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db")
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}

            preview = client.post("/api/projects/preview", json={"source_path": str(source)}, headers=headers)
            prompt_id = create_rewrite_prompt(client, headers)
            created_project = client.post(
                "/api/projects",
                json={"preview_token": preview.json()["preview_token"], "project_name": "Anchor Book", "prompt_template_id": prompt_id},
                headers=headers,
            )
            project_id = created_project.json()["id"]

            outline_payload = {
                "name": "API Outline",
                "description": "Plot anchor",
                "detail_level": "detailed",
                "outline": {"beats": ["choice"]},
                "anchor_prompt": "Keep Bobby's choice.",
                "source_metadata": {},
                "import_metadata": {},
            }
            rejected_outline = client.post("/api/outlines", json=outline_payload)
            created_outline = client.post("/api/outlines", json=outline_payload, headers=headers)
            outline_id = created_outline.json()["id"]
            listed_outlines = client.get("/api/outlines")
            updated_outline = client.post(
                f"/api/outlines/{outline_id}",
                json={**outline_payload, "name": "API Outline v2", "detail_level": "standard"},
                headers=headers,
            )
            rejected_outline_bind = client.post(
                f"/api/projects/{project_id}/outline",
                json={"outline_template_id": outline_id},
            )
            bound_outline = client.post(
                f"/api/projects/{project_id}/outline",
                json={"outline_template_id": outline_id},
                headers=headers,
            )
            project_outline = client.get(f"/api/projects/{project_id}/outline")

            alice_payload = {
                "name": "Alice",
                "aliases": ["A"],
                "description": "Main role",
                "priority": 90,
                "is_main": True,
                "relationship_notes": "",
                "personality": "Direct.",
                "speech_style": "",
                "action_constraints": "",
                "anti_ooc_rules": "",
                "profile": {"role": "main"},
                "source_metadata": {},
                "import_metadata": {},
            }
            bob_payload = {
                "name": "Bob",
                "aliases": ["Bobby"],
                "description": "",
                "priority": 40,
                "is_main": False,
                "relationship_notes": "",
                "personality": "",
                "speech_style": "Plain.",
                "action_constraints": "",
                "anti_ooc_rules": "",
                "profile": {},
                "source_metadata": {},
                "import_metadata": {},
            }
            rejected_character = client.post("/api/characters", json=alice_payload)
            alice = client.post("/api/characters", json=alice_payload, headers=headers)
            bob = client.post("/api/characters", json=bob_payload, headers=headers)
            alice_id = alice.json()["id"]
            bob_id = bob.json()["id"]
            listed_characters = client.get("/api/characters")
            copied_character = client.post(
                f"/api/characters/{alice_id}/copy",
                json={"target_scope": "project", "target_project_id": project_id},
                headers=headers,
            )
            imported_character = client.post(
                "/api/characters/import",
                json={**bob_payload, "name": "Imported Bob"},
                headers=headers,
            )
            updated_bob = client.post(
                f"/api/characters/{bob_id}",
                json={**bob_payload, "aliases": ["Robert"], "priority": 45},
                headers=headers,
            )
            rejected_character_bind = client.post(
                f"/api/projects/{project_id}/characters",
                json={"character_card_id": alice_id, "sort_order": 1},
            )
            client.post(
                f"/api/projects/{project_id}/characters",
                json={"character_card_id": alice_id, "sort_order": 1},
                headers=headers,
            )
            bound_characters = client.post(
                f"/api/projects/{project_id}/characters",
                json={"character_card_id": bob_id, "sort_order": 2},
                headers=headers,
            )
            unbound_characters = client.post(
                f"/api/projects/{project_id}/characters/{bob_id}/unbind",
                headers=headers,
            )
            unbound_outline = client.post(
                f"/api/projects/{project_id}/outline",
                json={"outline_template_id": None},
                headers=headers,
            )
            deleted_outline = client.post(f"/api/outlines/{outline_id}/delete", headers=headers)
            deleted_alice = client.post(f"/api/characters/{alice_id}/delete", headers=headers)

        self.assertEqual(403, rejected_outline.status_code)
        self.assertEqual(200, created_outline.status_code)
        self.assertEqual("API Outline", created_outline.json()["name"])
        self.assertEqual({"beats": ["choice"]}, created_outline.json()["outline"])
        self.assertEqual(1, len(listed_outlines.json()))
        self.assertEqual("API Outline v2", updated_outline.json()["name"])
        self.assertEqual("standard", updated_outline.json()["detail_level"])
        self.assertEqual(403, rejected_outline_bind.status_code)
        self.assertEqual(outline_id, bound_outline.json()["outline_template"]["id"])
        self.assertEqual(outline_id, project_outline.json()["outline_template"]["id"])
        self.assertEqual(403, rejected_character.status_code)
        self.assertEqual("Alice", alice.json()["name"])
        self.assertEqual(["A"], alice.json()["aliases"])
        self.assertEqual(2, len(listed_characters.json()))
        self.assertEqual("project", copied_character.json()["scope"])
        self.assertEqual(project_id, copied_character.json()["project_id"])
        self.assertEqual(alice_id, copied_character.json()["source_character_card_id"])
        self.assertEqual("Imported Bob", imported_character.json()["name"])
        self.assertEqual("json_import", imported_character.json()["import_metadata"]["created_by"])
        self.assertEqual(["Robert"], updated_bob.json()["aliases"])
        self.assertEqual(45, updated_bob.json()["priority"])
        self.assertEqual(403, rejected_character_bind.status_code)
        self.assertEqual(["Alice", "Alice", "Bob"], [item["name"] for item in bound_characters.json()["character_cards"]])
        self.assertEqual(["Alice", "Alice"], [item["name"] for item in unbound_characters.json()["character_cards"]])
        self.assertIsNone(unbound_outline.json()["outline_template"])
        self.assertEqual(200, deleted_outline.status_code)
        self.assertEqual(200, deleted_alice.status_code)

    def test_character_category_summary_and_atomic_copy_api(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            os.environ["RUSTY_DATABASE_PATH"] = str(database_path)
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(database_path)
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, updated_at) VALUES ('Character project', '2026-07-29 12:00:00')"
                )
                project_id = int(cursor.lastrowid)

            category = client.post(
                "/api/character-categories",
                json={"name": "Lead"},
                headers=headers,
            )
            tag = client.post(
                "/api/character-tags",
                json={"name": "Calm"},
                headers=headers,
            )
            card = client.post(
                "/api/characters",
                json={"name": "Alice", "tag_ids": [tag.json()["id"]]},
                headers=headers,
            )
            card_id = card.json()["id"]
            assigned = client.post(
                f"/api/characters/{card_id}/categories/{category.json()['id']}",
                json={"selected": True},
                headers=headers,
            )
            copied = client.post(
                f"/api/characters/{card_id}/copy-to-project",
                json={"target_project_id": project_id},
                headers=headers,
            )
            project_cards = client.get(f"/api/projects/{project_id}/characters")
            summaries = client.get("/api/character-projects/summary")
            deleted_category = client.post(
                f"/api/character-categories/{category.json()['id']}/delete",
                headers=headers,
            )
            original_after_delete = client.get(f"/api/characters/{card_id}")

        self.assertEqual(200, category.status_code)
        self.assertEqual(["Lead"], assigned.json()["categories"])
        self.assertEqual(["Calm"], assigned.json()["tags"])
        self.assertEqual("project", copied.json()["scope"])
        self.assertEqual(card_id, copied.json()["source_character_card_id"])
        self.assertEqual([], copied.json()["categories"])
        self.assertEqual(["Calm"], copied.json()["tags"])
        self.assertEqual([copied.json()["id"]], [item["id"] for item in project_cards.json()["character_cards"]])
        summary = next(item for item in summaries.json() if item["project_id"] == project_id)
        self.assertEqual(1, summary["character_count"])
        self.assertEqual(200, deleted_category.status_code)
        self.assertEqual(card_id, original_after_delete.json()["id"])
        self.assertEqual([], original_after_delete.json()["categories"])

    def test_anchor_extraction_api_from_text_and_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            source = root / "anchor.txt"
            source.write_text("1. One\nAlice protects Bobby near a lamp.", encoding="utf-8")
            os.environ["RUSTY_DATABASE_PATH"] = str(root / "rusty.db")
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            api = importlib.import_module("backend.api")
            app = api.create_app(root / "rusty.db", anchor_ai_client=FakeStyleAIClient())
            client = TestClient(app)
            headers = {"X-Rusty-Token": "test-token"}
            model_payload = {
                "display_name": "API Model",
                "provider": "openai_compatible",
                "base_url": "https://api.example.test/v1",
                "model_name": "example-model",
                "api_key": None,
                "temperature": 0.7,
                "max_tokens": None,
                "timeout_seconds": 60,
                "is_default": True,
            }
            client.post("/api/models", json=model_payload, headers=headers)

            rejected_outline = client.post(
                "/api/outlines/extract",
                json={"name": "Rejected", "sample_text": "sample"},
            )
            invalid_source = client.post(
                "/api/outlines/extract",
                json={"name": "Invalid", "sample_text": "sample", "source_path": str(source)},
                headers=headers,
            )
            extracted_outline = client.post(
                "/api/outlines/extract",
                json={"name": "Seed outline", "detail_level": "detailed", "sample_text": "Alice chooses."},
                headers=headers,
            )
            rejected_characters = client.post("/api/characters/extract/preview", json={"target_character_name": "Alice", "source_text": "Alice protects Bob."})
            missing_target = client.post("/api/characters/extract/preview", json={"source_text": "Alice protects Bob."}, headers=headers)
            before_preview = len(client.get("/api/characters").json())
            extracted_character = client.post("/api/characters/extract/preview", json={"target_character_name": "Alice", "source_text": "Alice protects Bob.", "source_metadata": {"source_type": "file", "source_file_name": "anchor.txt"}}, headers=headers)
            after_preview = len(client.get("/api/characters").json())
            draft = extracted_character.json()["character"]
            saved_character = client.post("/api/characters", json={**draft, "priority": 50, "is_main": False, "relationship_notes": "Protects Bob.", "personality": "Direct.", "speech_style": "Short.", "action_constraints": "Acts quickly.", "anti_ooc_rules": "Do not make her passive.", "profile": {}, "scope": "public", "project_id": None, "custom_fields": [], "analysis_status": "analyzed", "tag_ids": []}, headers=headers)

        self.assertEqual(403, rejected_outline.status_code)
        self.assertEqual(400, invalid_source.status_code)
        self.assertEqual(200, extracted_outline.status_code)
        self.assertEqual("API Extracted Outline", extracted_outline.json()["name"])
        self.assertEqual("detailed", extracted_outline.json()["detail_level"])
        self.assertEqual(["choice", "fallout"], extracted_outline.json()["outline"]["fixed_plot_beats"])
        self.assertEqual("ai_outline_extraction", extracted_outline.json()["import_metadata"]["created_by"])
        self.assertEqual(403, rejected_characters.status_code)
        self.assertEqual(422, missing_target.status_code)
        self.assertEqual(200, extracted_character.status_code)
        self.assertNotIn("candidates", extracted_character.json())
        self.assertEqual("Alice", extracted_character.json()["character"]["name"])
        self.assertEqual(before_preview, after_preview)
        self.assertEqual(200, saved_character.status_code)
        self.assertEqual("Alice", saved_character.json()["name"])


if __name__ == "__main__":
    unittest.main()
