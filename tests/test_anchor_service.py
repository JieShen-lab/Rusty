from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services import AnchorService


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


def _create_project(database_path: Path) -> int:
    with session(database_path) as connection:
        cursor = connection.execute(
            "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
        )
        return int(cursor.lastrowid)


if __name__ == "__main__":
    unittest.main()
