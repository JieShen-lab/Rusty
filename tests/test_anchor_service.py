from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services import AnchorExtractionService, AnchorService, ModelService
from rusty.services.ai_client import AIClient, AIResponse


class FakeAnchorAIClient(AIClient):
    def __init__(self, invalid_json: bool = False) -> None:
        self.invalid_json = invalid_json
        self.calls = []

    def chat(self, model, api_key, messages):
        self.calls.append((model, api_key, messages))
        user_text = messages[-1]["content"]
        if self.invalid_json:
            return AIResponse(text="not json", token_usage={}, elapsed_ms=1)
        if "structured character cards" in user_text:
            return AIResponse(
                text=json.dumps(
                    {
                        "characters": [
                            {
                                "name": "Alice",
                                "aliases": ["A"],
                                "description": "Main character.",
                                "priority": 90,
                                "is_main": True,
                                "relationship_notes": "Protects Bob.",
                                "personality": "Decisive.",
                                "speech_style": "Short sentences.",
                                "action_constraints": "Acts quickly.",
                                "anti_ooc_rules": "Do not make her passive.",
                                "profile": {"role": "lead"},
                            },
                            {
                                "name": "Bob",
                                "aliases": ["Bobby"],
                                "description": "Secondary character.",
                                "priority": 40,
                                "is_main": False,
                                "relationship_notes": "Trusts Alice.",
                                "personality": "Careful.",
                                "speech_style": "Plain.",
                                "action_constraints": "Avoids rash action.",
                                "anti_ooc_rules": "Do not make him reckless.",
                                "profile": {"role": "support"},
                            },
                        ]
                    },
                    ensure_ascii=False,
                ),
                token_usage={"total_tokens": 17},
                elapsed_ms=11,
            )
        return AIResponse(
            text=json.dumps(
                {
                    "name": "Extracted outline",
                    "description": "Extracted plot anchor.",
                    "anchor_prompt": "Keep the choice and its fallout.",
                    "outline": {"fixed_plot_beats": ["choice", "fallout"]},
                },
                ensure_ascii=False,
            ),
            token_usage={"total_tokens": 13},
            elapsed_ms=9,
        )


class AnchorServiceTests(unittest.TestCase):
    def test_outline_template_crud_and_project_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)

            outline_id = service.create_outline_template(
                name="Main outline",
                description="Project plot anchor",
                detail_level="detailed",
                outline={"beats": ["meet", "choice"]},
                anchor_prompt="Keep the original plot beats.",
            )
            service.bind_project_outline(project_id, outline_id)
            bound = service.get_project_outline_template(project_id)

            service.update_outline_template(
                outline_id,
                name="Main outline v2",
                detail_level="standard",
                outline={"beats": ["meet", "choice", "fallout"]},
                anchor_prompt="Preserve cause and effect.",
            )
            updated = service.get_outline_template(outline_id)
            service.delete_outline_template(outline_id)
            unbound = service.get_project_outline_template(project_id)

        self.assertIsNotNone(bound)
        self.assertEqual("Main outline", bound.name)
        self.assertIsNotNone(updated)
        self.assertEqual("Main outline v2", updated.name)
        self.assertEqual(2, updated.version)
        self.assertEqual(["meet", "choice", "fallout"], json.loads(updated.outline_json)["beats"])
        self.assertIsNone(unbound)

    def test_character_card_crud_binding_and_relevance_filtering(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)

            main_id = service.create_character_card(
                name="Alice",
                aliases=["A"],
                priority=90,
                is_main=True,
                personality="Decisive.",
            )
            matched_id = service.create_character_card(
                name="Bob",
                aliases=["Bobby"],
                priority=40,
                speech_style="Soft spoken.",
            )
            ignored_id = service.create_character_card(name="Carol", priority=40)
            service.bind_project_character(project_id, ignored_id, sort_order=3)
            service.bind_project_character(project_id, matched_id, sort_order=2)
            service.bind_project_character(project_id, main_id, sort_order=1)

            relevant = service.list_relevant_project_character_cards(
                project_id,
                "Bobby enters the room without Alice being named by alias.",
            )
            service.update_character_card(matched_id, name="Bob", aliases=["Robert"], priority=40)
            updated = service.get_character_card(matched_id)
            service.delete_character_card(matched_id)
            bound_after_delete = service.list_project_character_cards(project_id)

        self.assertEqual(["Alice", "Bob"], [card.name for card in relevant])
        self.assertIsNotNone(updated)
        self.assertEqual(["Robert"], updated.aliases)
        self.assertEqual(["Alice", "Carol"], [card.name for card in bound_after_delete])

    def test_bind_rejects_missing_project_or_deleted_card(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)
            card_id = service.create_character_card(name="Alice")
            service.delete_character_card(card_id)

            with self.assertRaises(ValueError):
                service.bind_project_character(project_id, card_id)
            with self.assertRaises(ValueError):
                service.bind_project_character(project_id + 100, card_id)

    def test_character_copy_creates_independent_versioned_project_copy(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)
            public_id = service.create_character_card(
                name="Alice",
                aliases=["A"],
                description="Original",
                profile={"identity": "captain"},
            )

            project_copy_id = service.copy_character_card(
                public_id,
                target_scope="project",
                target_project_id=project_id,
            )
            service.update_character_card(
                public_id,
                name="Alice v2",
                aliases=["A"],
                description="Changed public card",
            )
            project_copy = service.get_character_card(project_copy_id)

        self.assertIsNotNone(project_copy)
        assert project_copy is not None
        self.assertEqual("project", project_copy.scope)
        self.assertEqual(project_id, project_copy.project_id)
        self.assertEqual(public_id, project_copy.source_character_card_id)
        self.assertEqual(1, project_copy.source_version)
        self.assertEqual("Alice", project_copy.name)
        self.assertEqual("Original", project_copy.description)
        self.assertEqual({"identity": "captain"}, project_copy.profile)

    def test_character_categories_atomic_project_copy_and_project_summary(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)
            lead = service.create_character_category("Lead")
            historical = service.create_character_category("Historical")
            tag = service.create_character_tag("Calm")
            public_id = service.create_character_card(name="Alice", tag_ids=[tag["id"]])
            service.set_character_category(public_id, lead.id, True)
            service.set_character_category(public_id, historical.id, True)

            public = service.get_character_card(public_id)
            project_copy_id = service.copy_public_character_to_project(public_id, project_id)
            project_copy = service.get_character_card(project_copy_id)
            bound = service.list_project_character_cards(project_id)
            filtered = service.list_character_cards(scope="public", category_id=lead.id)

            self.assertIsNotNone(public)
            self.assertEqual((lead.id, historical.id), public.category_ids)
            self.assertEqual(("Calm",), public.tags)
            self.assertEqual([public_id], [card.id for card in filtered])
            self.assertIsNotNone(project_copy)
            self.assertEqual("project", project_copy.scope)
            self.assertEqual(public_id, project_copy.source_character_card_id)
            self.assertEqual(1, project_copy.source_version)
            self.assertEqual(("Calm",), project_copy.tags)
            self.assertEqual((), project_copy.category_ids)
            self.assertIn(project_copy_id, [card.id for card in bound])

            with self.assertRaisesRegex(ValueError, "Only public"):
                service.set_character_category(project_copy_id, lead.id, True)

            service.delete_character_category(lead.id)
            self.assertIsNotNone(service.get_character_card(public_id))
            self.assertEqual((historical.id,), service.get_character_card(public_id).category_ids)

            summaries = service.list_character_project_summaries()
            summary = next(item for item in summaries if item.project_id == project_id)
            self.assertEqual(1, summary.character_count)
            service.unbind_project_character(project_id, project_copy_id)
            summary = next(
                item
                for item in service.list_character_project_summaries()
                if item.project_id == project_id
            )
            self.assertEqual(0, summary.character_count)

    def test_public_character_copy_failure_leaves_no_half_created_card(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = AnchorService(database_path)
            project_id = _create_project(database_path)
            public_id = service.create_character_card(name="Alice")
            service.save_character_cover(
                public_id,
                b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + (1).to_bytes(4, "big") + (1).to_bytes(4, "big"),
            )
            with session(database_path) as connection:
                before = int(connection.execute("SELECT COUNT(*) FROM character_cards").fetchone()[0])

            with patch.object(Path, "write_bytes", side_effect=OSError("simulated cover failure")):
                with self.assertRaisesRegex(OSError, "simulated cover failure"):
                    service.copy_public_character_to_project(public_id, project_id)

            with session(database_path) as connection:
                after = int(connection.execute("SELECT COUNT(*) FROM character_cards").fetchone()[0])
                bindings = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM project_character_bindings WHERE project_id = ?",
                        (project_id,),
                    ).fetchone()[0]
                )
            self.assertEqual(before, after)
            self.assertEqual(0, bindings)

    def test_ai_outline_extraction_from_text_creates_structured_template(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            fake_client = FakeAnchorAIClient()
            extraction = AnchorExtractionService(database_path, ai_client=fake_client)

            outline_id = extraction.extract_outline_from_text(
                "Alice makes a choice and Bob reacts.",
                name="Seed outline",
                detail_level="detailed",
            )
            outline = AnchorService(database_path).get_outline_template(outline_id)
            metadata = json.loads(outline.import_metadata_json) if outline else {}
            source_metadata = json.loads(outline.source_metadata_json) if outline else {}
            outline_json = json.loads(outline.outline_json) if outline else {}

        self.assertIsNotNone(outline)
        self.assertEqual("Extracted outline", outline.name)
        self.assertEqual("detailed", outline.detail_level)
        self.assertEqual("Keep the choice and its fallout.", outline.anchor_prompt)
        self.assertEqual(["choice", "fallout"], outline_json["fixed_plot_beats"])
        self.assertEqual("ai_outline_extraction", metadata["created_by"])
        self.assertEqual("paste", source_metadata["source_type"])
        self.assertIn("Required outline dimensions", fake_client.calls[0][2][-1]["content"])

    def test_ai_character_extraction_from_text_creates_character_cards(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            fake_client = FakeAnchorAIClient()
            extraction = AnchorExtractionService(database_path, ai_client=fake_client)

            card_ids = extraction.extract_characters_from_text(
                "Alice protects Bob. Bobby answers carefully.",
                name="Alice",
                detail_level="standard",
            )
            service = AnchorService(database_path)
            cards = [service.get_character_card(card_id) for card_id in card_ids]
            alice_metadata = json.loads(cards[0].import_metadata_json) if cards[0] else {}
            alice_source = json.loads(cards[0].source_metadata_json) if cards[0] else {}

        self.assertEqual(2, len(card_ids))
        self.assertEqual(["Alice", "Bob"], [card.name for card in cards if card])
        self.assertEqual(["A"], cards[0].aliases)
        self.assertTrue(cards[0].is_main)
        self.assertEqual(90, cards[0].priority)
        self.assertEqual("Protects Bob.", cards[0].relationship_notes)
        self.assertEqual("ai_character_extraction", alice_metadata["created_by"])
        self.assertEqual("paste", alice_source["source_type"])
        self.assertIn("Required character dimensions", fake_client.calls[0][2][-1]["content"])
        self.assertIn("Only extract the target character named “Alice”", fake_client.calls[0][2][-1]["content"])

    def test_ai_anchor_extraction_from_file_uses_import_parser_sample(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            source_path = root / "anchor.txt"
            source_path.write_text("1. One\nAlice meets Bob.", encoding="utf-8")
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            extraction = AnchorExtractionService(database_path, ai_client=FakeAnchorAIClient())

            outline_id = extraction.extract_outline_from_file(source_path, name="File outline")
            card_ids = extraction.extract_characters_from_file(source_path)
            service = AnchorService(database_path)
            outline = service.get_outline_template(outline_id)
            card = service.get_character_card(card_ids[0])
            outline_source = json.loads(outline.source_metadata_json) if outline else {}
            card_source = json.loads(card.source_metadata_json) if card else {}

        self.assertEqual("file", outline_source["source_type"])
        self.assertEqual("txt", outline_source["source_format"])
        self.assertEqual("anchor.txt", outline_source["source_file_name"])
        self.assertEqual("file", card_source["source_type"])
        self.assertEqual("anchor.txt", card_source["source_file_name"])

    def test_ai_anchor_extraction_rejects_invalid_json_response(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            ModelService(database_path).create_model(
                display_name="Fake",
                provider="openai_compatible",
                base_url="https://api.example.test/v1",
                model_name="fake-model",
                is_default=True,
            )
            extraction = AnchorExtractionService(database_path, ai_client=FakeAnchorAIClient(invalid_json=True))

            with self.assertRaises(ValueError):
                extraction.extract_outline_from_text("Sample prose.", name="Bad")
            with self.assertRaises(ValueError):
                extraction.extract_characters_from_text("Sample prose.")


def _create_project(database_path: Path) -> int:
    with session(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
        )
        return int(cursor.lastrowid)


if __name__ == "__main__":
    unittest.main()
