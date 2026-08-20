from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests.support import initialized_database
from rusty.db import session
from rusty.services import AnchorExtractionService, AnchorService, ModelService
from rusty.services.ai_client import AIClient, AIResponse


class FakeOutlineAI(AIClient):
    def __init__(self, invalid: bool = False) -> None:
        self.invalid = invalid

    def chat(self, model, api_key, messages):
        if self.invalid:
            return AIResponse(text="not json", token_usage={}, elapsed_ms=1)
        return AIResponse(text=json.dumps({
            "name": "Extracted outline", "description": "Plot anchor",
            "anchor_prompt": "Keep cause and effect.",
            "outline": {"fixed_plot_beats": ["choice", "fallout"]},
        }), token_usage={}, elapsed_ms=1)


def _project(database: Path) -> int:
    with session(database) as connection:
        return int(connection.execute("INSERT INTO projects(name) VALUES('P')").lastrowid)


class AnchorServiceTests(unittest.TestCase):
    def test_outline_template_crud_and_project_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            service = AnchorService(database)
            project_id = _project(database)
            outline_id = service.create_outline_template(
                name="Main", detail_level="detailed", outline={"beats": ["meet"]},
                anchor_prompt="Keep the original plot beats.",
            )
            service.bind_project_outline(project_id, outline_id)
            self.assertEqual("Main", service.get_project_outline_template(project_id).name)
            service.update_outline_template(outline_id, name="Main v2", outline={"beats": ["meet", "choice"]})
            self.assertEqual(2, service.get_outline_template(outline_id).version)
            service.delete_outline_template(outline_id)
            self.assertIsNone(service.get_project_outline_template(project_id))

    def test_ai_outline_extraction_from_text_and_file(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database = initialized_database(root / "rusty.db")
            ModelService(database).create_model(
                display_name="Fake", provider="openai_compatible",
                base_url="https://example.test/v1", model_name="fake", is_default=True,
            )
            source = root / "source.txt"
            source.write_text("A choice causes fallout.", encoding="utf-8")
            extraction = AnchorExtractionService(database, ai_client=FakeOutlineAI())
            text_id = extraction.extract_outline_from_text(source.read_text(encoding="utf-8"), name="Text")
            file_id = extraction.extract_outline_from_file(source, name="File")
            service = AnchorService(database)
            self.assertEqual(["choice", "fallout"], json.loads(service.get_outline_template(text_id).outline_json)["fixed_plot_beats"])
            self.assertEqual("file", json.loads(service.get_outline_template(file_id).source_metadata_json)["source_type"])

    def test_ai_outline_extraction_rejects_invalid_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database = initialized_database(Path(directory) / "rusty.db")
            ModelService(database).create_model(
                display_name="Fake", provider="openai_compatible",
                base_url="https://example.test/v1", model_name="fake", is_default=True,
            )
            with self.assertRaises(ValueError):
                AnchorExtractionService(database, ai_client=FakeOutlineAI(True)).extract_outline_from_text("text", name="Bad")


if __name__ == "__main__":
    unittest.main()
