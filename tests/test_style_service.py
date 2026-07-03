from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services import StyleTemplateService


class StyleTemplateServiceTests(unittest.TestCase):
    def test_style_template_crud_export_import_and_project_binding(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
                )
                project_id = int(cursor.lastrowid)

            template_id = service.create_template(
                name="Author style",
                description="Structured style",
                detail_level="detailed",
                global_prompt="Keep narrative voice consistent.",
                rewrite_prompt="Use short, sharp dialogue.",
                style_profile={"dialogue_style": "sharp"},
                generated_prompt="Generated style prompt.",
                source_metadata={"source_type": "paste"},
            )
            service.bind_project_style(project_id, template_id)
            bound = service.get_project_style_template(project_id)
            exported = service.export_template(template_id)
            imported_id = service.import_template_text(exported)
            imported = service.get_template(imported_id)

            service.update_template(
                template_id,
                name="Author style v2",
                detail_level="standard",
                rewrite_prompt="Use clipped pacing.",
            )
            updated = service.get_template(template_id)
            service.delete_template(template_id)
            unbound = service.get_project_style_template(project_id)

        self.assertIsNotNone(bound)
        self.assertEqual("Author style", bound.name)
        self.assertIn("rusty.style_template", exported)
        self.assertIsNotNone(imported)
        self.assertEqual("Author style", imported.name)
        self.assertIsNotNone(updated)
        self.assertEqual("Author style v2", updated.name)
        self.assertEqual(2, updated.version)
        self.assertIsNone(unbound)

    def test_import_legacy_template_maps_known_fields_without_enabling_breakthrough(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            legacy_payload = {
                "name": "Legacy style",
                "rewriteTemplate": {
                    "commonPrompt": "Legacy rewrite rules.",
                    "categoryPrompts": {"dialogue": "Legacy dialogue rule."},
                },
                "identifyTemplate": {
                    "categories": [{"key": "dialogue", "name": "Dialogue"}],
                },
                "breakthroughTemplate": "Imported only as compatibility text.",
            }

            template_id = service.import_template_text(json.dumps(legacy_payload, ensure_ascii=False))
            template = service.get_template(template_id)
            metadata = json.loads(template.import_metadata_json) if template else {}
            profile = json.loads(template.style_profile_json) if template else {}

        self.assertIsNotNone(template)
        self.assertEqual("Legacy style", template.name)
        self.assertEqual("Legacy rewrite rules.", template.rewrite_prompt)
        self.assertEqual("Legacy rewrite rules.", template.generated_prompt)
        self.assertIn("legacy_category_prompts", profile)
        self.assertIn("legacy_identify_categories", profile)
        self.assertEqual("legacy", metadata["import_schema"])
        self.assertIn("legacy_breakthroughTemplate", metadata)

    def test_import_rejects_malformed_json(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            service = StyleTemplateService(Path(directory) / "rusty.db")

            with self.assertRaises(ValueError):
                service.import_template_text("{not valid json")

    def test_binding_rejects_deleted_project_or_template(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            service = StyleTemplateService(database_path)
            with session(database_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO projects (name, status, current_stage) VALUES ('Book', 'draft', 'import')"
                )
                project_id = int(cursor.lastrowid)
            template_id = service.create_template(name="Style")
            service.delete_template(template_id)

            with self.assertRaises(ValueError):
                service.bind_project_style(project_id, template_id)
            with self.assertRaises(ValueError):
                service.bind_project_style(project_id + 100, template_id)


if __name__ == "__main__":
    unittest.main()
