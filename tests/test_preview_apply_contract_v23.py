from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from backend.schemas import MaterialExtractionPreviewOut
from rusty.db import session
from rusty.db.schema import CURRENT_SCHEMA_VERSION, initialize_database
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services import anchor_extraction_service as extraction_module
from rusty.services.anchor_service import AnchorService
from rusty.services.material_service import MATERIAL_AI_DEFAULTS, MaterialService
from rusty.services.model_service import ModelService
from tests.support import initialized_database


class ContractAIClient(AIClient):
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        user_prompt = messages[-1]["content"]
        if "structured character cards" in user_prompt:
            payload = {
                "characters": [
                    {"name": "Alpha", "suggested_tags": ["主角"]},
                    {"name": "Beta", "suggested_tags": ["配角"]},
                ]
            }
        else:
            payload = {
                "materials": [
                    {
                        "name": "Material Alpha",
                        "content": {"premise": "A", "stages": [{"title": "Start", "summary": "A1"}]},
                        "suggested_general_tags": ["主线"],
                        "suggested_applicable_scene_tags": ["开场"],
                        "evidence": [{"quote": "A"}],
                        "confidence": 2,
                        "warnings": ["需要复核"],
                    },
                    {
                        "name": "Material Beta",
                        "content": {"premise": "B"},
                        "suggested_general_tags": ["支线"],
                    },
                ]
            }
        return AIResponse(
            text=json.dumps(payload, ensure_ascii=False),
            token_usage={"total_tokens": 1},
            elapsed_ms=1,
        )


class PreviewApplyContractV23Tests(unittest.TestCase):
    def _service(self, directory: str) -> tuple[Path, AnchorExtractionService, ContractAIClient]:
        database_path = initialized_database(Path(directory) / "rusty.db")
        ModelService(database_path).create_model(
            display_name="Fake",
            provider="openai_compatible",
            base_url="https://example.invalid/v1",
            model_name="fake",
            is_default=True,
        )
        client = ContractAIClient()
        return database_path, AnchorExtractionService(database_path, ai_client=client), client

    def test_character_token_is_consumed_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            preview = extraction.preview_characters_from_text("Alpha meets Beta.")
            payload = [{**candidate.__dict__, "confirmed_tags": []} for candidate in preview.candidates]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            first = extraction.apply_character_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
                scope="public",
                project_id=None,
            )
            self.assertEqual(2, len(first["created"]))
            with self.assertRaisesRegex(ValueError, "already used"):
                extraction.apply_character_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=selected,
                    scope="public",
                    project_id=None,
                )
            self.assertEqual(2, len(AnchorService(database_path).list_character_cards()))

    def test_material_token_is_consumed_only_after_success(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            preview = extraction.preview_materials_from_text(
                "A then B.",
                task_type="narrative_to_plot_skeleton",
            )
            payload = [
                {
                    **candidate.__dict__,
                    "confirmed_general_tags": [],
                    "confirmed_applicable_scene_tags": [],
                    "category_ids": [],
                }
                for candidate in preview.candidates
            ]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            first = extraction.apply_material_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
            )
            self.assertEqual(2, len(first["created"]))
            with self.assertRaisesRegex(ValueError, "already used"):
                extraction.apply_material_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=selected,
                )
            self.assertEqual(2, len(MaterialService(database_path).list_materials()))

    def test_material_apply_uses_preview_detail_level_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            task_type = "narrative_to_plot_skeleton"
            settings = extraction.material_service.get_ai_settings(task_type)

            def set_detail_level(detail_level: str) -> None:
                extraction.material_service.update_ai_settings(
                    task_type,
                    model_id=settings.model_id,
                    detail_level=detail_level,
                    max_candidates=settings.max_candidates,
                    system_prompt=settings.system_prompt,
                    custom_requirements=settings.custom_requirements,
                )

            set_detail_level("detailed")
            preview = extraction.preview_materials_from_text(
                "A then B.", task_type=task_type
            )
            preview.prompt_snapshot["detail_level"] = "brief"
            set_detail_level("brief")
            payload = [
                {
                    **candidate.__dict__,
                    "confirmed_general_tags": [],
                    "confirmed_applicable_scene_tags": [],
                    "category_ids": [],
                }
                for candidate in preview.candidates
            ]

            with patch.object(
                extraction.material_service,
                "get_ai_settings",
                side_effect=AssertionError("apply must not reread mutable settings"),
            ):
                result = extraction.apply_material_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=[
                        candidate.candidate_id for candidate in preview.candidates
                    ],
                )

            self.assertEqual(2, len(result["created"]))
            self.assertEqual(
                {"detailed"},
                {
                    material.detail_level
                    for material in MaterialService(database_path).list_materials()
                },
            )

    def test_preview_lookup_and_creation_prune_only_expired_tokens(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            character = extraction.preview_characters_from_text("Alpha meets Beta.")
            character_key = (str(database_path.resolve()), character.preview_token)
            extraction_module._CHARACTER_PREVIEWS[character_key].expires_at = 0.0

            extraction.preview_characters_from_text("Alpha meets Beta again.")
            self.assertNotIn(character_key, extraction_module._CHARACTER_PREVIEWS)

            material = extraction.preview_materials_from_text(
                "A then B.", task_type="narrative_to_plot_skeleton"
            )
            material_key = (str(database_path.resolve()), material.preview_token)
            extraction_module._MATERIAL_PREVIEWS[material_key].expires_at = 0.0
            with self.assertRaisesRegex(ValueError, "expired"):
                extraction.apply_material_extraction(
                    preview_token=material.preview_token,
                    candidates=[],
                    selected_candidate_ids=[],
                )
            self.assertNotIn(material_key, extraction_module._MATERIAL_PREVIEWS)

    def test_character_token_rejects_concurrent_apply(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            with session(database_path) as connection:
                project_id = int(
                    connection.execute(
                        "INSERT INTO projects(name, status, current_stage) VALUES ('P', 'imported', 'split')"
                    ).lastrowid
                )
            preview = extraction.preview_characters_from_text("Alpha meets Beta.")
            payload = [
                {**candidate.__dict__, "confirmed_tags": ["atomic"]}
                for candidate in preview.candidates
            ]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            entered = threading.Event()
            release = threading.Event()
            original = extraction.anchor_service.create_extracted_character_batch

            def blocked_batch(**kwargs):
                entered.set()
                self.assertTrue(release.wait(5), "character batch was not released")
                return original(**kwargs)

            def apply():
                return extraction.apply_character_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=selected,
                    scope="project",
                    project_id=project_id,
                )

            with patch.object(
                extraction.anchor_service,
                "create_extracted_character_batch",
                side_effect=blocked_batch,
            ), ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(apply)
                self.assertTrue(entered.wait(5), "character batch did not start")
                second = executor.submit(apply)
                with self.assertRaisesRegex(ValueError, "currently being applied"):
                    second.result(timeout=5)
                release.set()
                result = first.result(timeout=5)

            self.assertEqual(2, len(result["created"]))
            key = (str(database_path.resolve()), preview.preview_token)
            self.assertEqual("consumed", extraction_module._CHARACTER_PREVIEWS[key].state)
            with session(database_path) as connection:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM character_cards").fetchone()[0])
                self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM character_tags").fetchone()[0])
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM character_tag_links").fetchone()[0])
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM project_character_bindings").fetchone()[0])

    def test_material_token_rejects_concurrent_apply(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            category = MaterialService(database_path).create_category("plot_skeleton", "atomic")
            preview = extraction.preview_materials_from_text(
                "A then B.",
                task_type="narrative_to_plot_skeleton",
            )
            payload = [
                {
                    **candidate.__dict__,
                    "confirmed_general_tags": ["atomic"],
                    "confirmed_applicable_scene_tags": ["opening"],
                    "category_ids": [category.id],
                }
                for candidate in preview.candidates
            ]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            entered = threading.Event()
            release = threading.Event()
            original = extraction.material_service.create_extracted_material_batch

            def blocked_batch(**kwargs):
                entered.set()
                self.assertTrue(release.wait(5), "material batch was not released")
                return original(**kwargs)

            def apply():
                return extraction.apply_material_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=selected,
                )

            with patch.object(
                extraction.material_service,
                "create_extracted_material_batch",
                side_effect=blocked_batch,
            ), ThreadPoolExecutor(max_workers=2) as executor:
                first = executor.submit(apply)
                self.assertTrue(entered.wait(5), "material batch did not start")
                second = executor.submit(apply)
                with self.assertRaisesRegex(ValueError, "currently being applied"):
                    second.result(timeout=5)
                release.set()
                result = first.result(timeout=5)

            self.assertEqual(2, len(result["created"]))
            key = (str(database_path.resolve()), preview.preview_token)
            self.assertEqual("consumed", extraction_module._MATERIAL_PREVIEWS[key].state)
            with session(database_path) as connection:
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM material_tags").fetchone()[0])
                self.assertEqual(4, connection.execute("SELECT COUNT(*) FROM material_tag_links").fetchone()[0])
                self.assertEqual(2, connection.execute("SELECT COUNT(*) FROM material_category_links").fetchone()[0])

    def test_first_character_candidate_failure_is_attributed_and_token_can_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            anchor_service = AnchorService(database_path)
            with session(database_path) as connection:
                project_id = int(
                    connection.execute(
                        "INSERT INTO projects(name, status, current_stage) VALUES ('P', 'imported', 'split')"
                    ).lastrowid
                )
                connection.execute(
                    """
                    CREATE TRIGGER fail_character_candidate
                    BEFORE INSERT ON character_cards
                    WHEN NEW.name = 'FAIL'
                    BEGIN SELECT RAISE(ABORT, 'forced character failure'); END
                    """
                )
            preview = extraction.preview_characters_from_text("Alpha meets Beta.")
            payload = [
                {
                    **candidate.__dict__,
                    "name": "FAIL" if index == 0 else candidate.name,
                    "confirmed_tags": ["原子标签"],
                }
                for index, candidate in enumerate(preview.candidates)
            ]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            failed = extraction.apply_character_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
                scope="project",
                project_id=project_id,
            )
            self.assertEqual([], failed["created"])
            self.assertEqual(selected[0], failed["errors"][0]["candidate_id"])
            self.assertNotEqual(selected[-1], failed["errors"][0]["candidate_id"])
            with session(database_path) as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM character_cards").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM character_tags").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM project_character_bindings").fetchone()[0])
                connection.execute("DROP TRIGGER fail_character_candidate")
            key = (str(database_path.resolve()), preview.preview_token)
            self.assertEqual("pending", extraction_module._CHARACTER_PREVIEWS[key].state)
            payload[0]["name"] = "Alpha fixed"
            retried = extraction.apply_character_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
                scope="project",
                project_id=project_id,
            )
            self.assertEqual(2, len(retried["created"]))
            self.assertEqual(2, len(anchor_service.list_project_character_cards(project_id)))

    def test_validation_failure_keeps_token_for_corrected_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            _, extraction, _ = self._service(directory)
            preview = extraction.preview_characters_from_text("Alpha meets Beta.")
            payload = [{**candidate.__dict__, "confirmed_tags": []} for candidate in preview.candidates]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            with self.assertRaisesRegex(ValueError, "duplicate candidate_id"):
                extraction.apply_character_extraction(
                    preview_token=preview.preview_token,
                    candidates=[payload[0], payload[0]],
                    selected_candidate_ids=selected,
                    scope="public",
                    project_id=None,
                )
            retried = extraction.apply_character_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
                scope="public",
                project_id=None,
            )
            self.assertEqual(2, len(retried["created"]))

    def test_first_material_candidate_failure_is_attributed_and_token_can_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            material_service = MaterialService(database_path)
            category = material_service.create_category("plot_skeleton", "主线")
            with session(database_path) as connection:
                connection.execute(
                    """
                    CREATE TRIGGER fail_material_candidate
                    BEFORE INSERT ON materials
                    WHEN NEW.name = 'FAIL'
                    BEGIN SELECT RAISE(ABORT, 'forced material failure'); END
                    """
                )
            preview = extraction.preview_materials_from_text(
                "A then B.",
                task_type="narrative_to_plot_skeleton",
            )
            payload = [
                {
                    **candidate.__dict__,
                    "name": "FAIL" if index == 0 else candidate.name,
                    "confirmed_general_tags": ["原子标签"],
                    "confirmed_applicable_scene_tags": ["开场"],
                    "category_ids": [category.id],
                }
                for index, candidate in enumerate(preview.candidates)
            ]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            failed = extraction.apply_material_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
            )
            self.assertEqual([], failed["created"])
            self.assertEqual(selected[0], failed["errors"][0]["candidate_id"])
            self.assertNotEqual(selected[-1], failed["errors"][0]["candidate_id"])
            with session(database_path) as connection:
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM materials").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM material_tags").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM material_tag_links").fetchone()[0])
                self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM material_category_links").fetchone()[0])
                connection.execute("DROP TRIGGER fail_material_candidate")
            key = (str(database_path.resolve()), preview.preview_token)
            self.assertEqual("pending", extraction_module._MATERIAL_PREVIEWS[key].state)
            payload[0]["name"] = "Material Alpha fixed"
            retried = extraction.apply_material_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
            )
            self.assertEqual(2, len(retried["created"]))

    def test_batch_level_failure_has_no_candidate_id_and_can_retry(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, _ = self._service(directory)
            preview = extraction.preview_characters_from_text("Alpha meets Beta.")
            payload = [{**candidate.__dict__, "confirmed_tags": []} for candidate in preview.candidates]
            selected = [candidate.candidate_id for candidate in preview.candidates]
            with patch.object(
                extraction.anchor_service,
                "create_extracted_character_batch",
                side_effect=sqlite3.OperationalError("shared commit failure"),
            ):
                failed = extraction.apply_character_extraction(
                    preview_token=preview.preview_token,
                    candidates=payload,
                    selected_candidate_ids=selected,
                    scope="public",
                    project_id=None,
                )
            self.assertEqual([], failed["created"])
            self.assertEqual("", failed["errors"][0]["candidate_id"])
            self.assertIn("complete character batch was rolled back", failed["errors"][0]["error"])
            key = (str(database_path.resolve()), preview.preview_token)
            self.assertEqual("pending", extraction_module._CHARACTER_PREVIEWS[key].state)
            retried = extraction.apply_character_extraction(
                preview_token=preview.preview_token,
                candidates=payload,
                selected_candidate_ids=selected,
                scope="public",
                project_id=None,
            )
            self.assertEqual(2, len(retried["created"]))

    def test_full_source_is_saved_while_model_sample_is_limited(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path, extraction, client = self._service(directory)
            source = "甲" * 50000
            character_preview = extraction.preview_characters_from_text(source)
            character_payload = [
                {**candidate.__dict__, "confirmed_tags": []}
                for candidate in character_preview.candidates
            ]
            character_result = extraction.apply_character_extraction(
                preview_token=character_preview.preview_token,
                candidates=character_payload,
                selected_candidate_ids=[character_preview.candidates[0].candidate_id],
                scope="public",
                project_id=None,
            )
            card = AnchorService(database_path).get_character_card(
                int(character_result["created"][0]["card_id"])
            )
            assert card is not None
            self.assertEqual(source, card.raw_text)
            self.assertEqual(50000, card.source_metadata["source_character_count"])
            self.assertEqual(16000, card.source_metadata["model_sample_character_count"])
            self.assertTrue(card.source_metadata["source_truncated_for_model"])
            character_sample = client.calls[0][-1]["content"].split("Sample prose:\n", 1)[1]
            self.assertEqual(16000, len(character_sample))

            material_preview = extraction.preview_materials_from_text(
                source,
                task_type="narrative_to_plot_skeleton",
            )
            material_payload = [
                {
                    **candidate.__dict__,
                    "confirmed_general_tags": [],
                    "confirmed_applicable_scene_tags": [],
                    "category_ids": [],
                }
                for candidate in material_preview.candidates
            ]
            material_result = extraction.apply_material_extraction(
                preview_token=material_preview.preview_token,
                candidates=material_payload,
                selected_candidate_ids=[material_preview.candidates[0].candidate_id],
            )
            material = MaterialService(database_path).get_material(
                int(material_result["created"][0]["material_id"])
            )
            assert material is not None
            self.assertEqual(source, material.raw_text)
            metadata = json.loads(material.source_metadata_json)
            self.assertEqual(50000, metadata["source_character_count"])
            self.assertEqual(16000, metadata["model_sample_character_count"])
            material_sample = client.calls[1][-1]["content"].split("Source text:\n", 1)[1]
            self.assertEqual(16000, len(material_sample))

    def test_source_over_limit_is_rejected_without_preview(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            _, extraction, client = self._service(directory)
            oversized = "甲" * 50001
            with self.assertRaisesRegex(ValueError, "50,000"):
                extraction.preview_characters_from_text(oversized)
            with self.assertRaisesRegex(ValueError, "50,000"):
                extraction.preview_materials_from_text(
                    oversized,
                    task_type="narrative_to_plot_skeleton",
                )
            self.assertEqual([], client.calls)

    def test_material_settings_are_independent_persistent_and_resettable(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = initialized_database(Path(directory) / "rusty.db")
            service = MaterialService(database_path)
            for index, task_type in enumerate(sorted(MATERIAL_AI_DEFAULTS)):
                service.update_ai_settings(
                    task_type,
                    model_id=None,
                    detail_level=("brief", "standard", "detailed")[index],
                    max_candidates=index + 2,
                    system_prompt=f"system-{index}",
                    user_prompt_template=f"user-{index}",
                    analysis_dimensions=[f"dimension-{index}"],
                    generate_general_tags=index != 1,
                    generate_applicable_scene_tags=index == 2,
                    custom_requirements=f"custom-{index}",
                )
            persisted = {
                item.task_type: item
                for item in MaterialService(database_path).list_ai_settings()
            }
            self.assertEqual({"system-0", "system-1", "system-2"}, {item.system_prompt for item in persisted.values()})
            reset_task = "source_text_to_scene_material"
            reset = service.reset_ai_settings(reset_task)
            self.assertEqual(
                tuple(MATERIAL_AI_DEFAULTS[reset_task]["analysis_dimensions"]),
                reset.analysis_dimensions,
            )
            self.assertTrue(reset.generate_general_tags)
            self.assertTrue(reset.generate_applicable_scene_tags)

    def test_v22_generate_tags_migrates_to_both_v23_switches(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = Path(directory) / "rusty.db"
            connection = sqlite3.connect(database_path)
            connection.row_factory = sqlite3.Row
            connection.executescript(
                """
                CREATE TABLE schema_migrations(version INTEGER PRIMARY KEY);
                INSERT INTO schema_migrations(version) VALUES (22);
                CREATE TABLE material_ai_settings (
                    task_type TEXT PRIMARY KEY,
                    model_id INTEGER,
                    detail_level TEXT NOT NULL DEFAULT 'standard',
                    max_candidates INTEGER NOT NULL DEFAULT 6,
                    generate_tags INTEGER NOT NULL DEFAULT 1,
                    custom_requirements TEXT NOT NULL DEFAULT '',
                    system_prompt TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                INSERT INTO material_ai_settings(task_type, generate_tags)
                VALUES
                    ('narrative_to_plot_skeleton', 0),
                    ('plot_text_to_normalized_skeleton', 1),
                    ('source_text_to_scene_material', 1);
                """
            )
            initialize_database(connection)
            rows = connection.execute(
                """
                SELECT task_type, generate_tags, generate_general_tags,
                       generate_applicable_scene_tags, analysis_dimensions_json
                FROM material_ai_settings ORDER BY task_type
                """
            ).fetchall()
            version = connection.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
            connection.close()
            self.assertEqual(CURRENT_SCHEMA_VERSION, version)
            for row in rows:
                self.assertEqual(row["generate_tags"], row["generate_general_tags"])
                self.assertEqual(row["generate_tags"], row["generate_applicable_scene_tags"])
                self.assertIsInstance(json.loads(row["analysis_dimensions_json"]), list)

    def test_material_preview_schema_contains_complete_contract(self) -> None:
        value = MaterialExtractionPreviewOut(
            preview_token="token",
            expires_at="2030-01-01T00:00:00+00:00",
            task_type="narrative_to_plot_skeleton",
            material_type="plot_skeleton",
            source_summary={"kind": "project_selection", "label": "工程选区"},
            prompt_snapshot={"system_prompt": "safe"},
            candidates=[
                {
                    "candidate_id": "candidate",
                    "material_type": "plot_skeleton",
                    "name": "A",
                    "evidence": [{"quote": "A"}],
                    "confidence": 0.75,
                    "warnings": [],
                }
            ],
        )
        self.assertEqual("2030-01-01T00:00:00+00:00", value.expires_at)
        self.assertEqual(0.75, value.candidates[0].confidence)
        self.assertEqual([{"quote": "A"}], value.candidates[0].evidence)

    def test_structured_material_round_trip_preserves_unedited_fields_and_legacy_extra(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            service = MaterialService(initialized_database(Path(directory) / "rusty.db"))
            material_id = service.create_material(
                material_type="plot_skeleton",
                scope="public",
                name="Detailed plot",
                content={
                    "premise": "Original",
                    "stages": [
                        {
                            "id": "stage-fixed",
                            "title": "Opening",
                            "summary": "Before",
                            "causes": ["Cause"],
                            "effects": ["Effect"],
                            "characters": ["A"],
                            "locations": ["Harbor"],
                            "must_keep_details": ["Bell"],
                            "forbidden_changes": ["No rain"],
                            "unknown_stage_field": {"keep": True},
                        }
                    ],
                    "legacy_extra": {"old_key": ["keep"]},
                },
            )
            material = service.get_material(material_id)
            assert material is not None
            content = json.loads(material.content_json)
            stages = [dict(item) for item in content["stages"]]
            stages[0]["summary"] = "After"
            service.update_material(
                material_id,
                name=material.name,
                description=material.description,
                detail_level=material.detail_level,
                raw_text=material.raw_text,
                content={**content, "stages": stages},
                analysis_status=material.analysis_status,
                tag_ids=[],
                category_ids=[],
            )
            updated = service.get_material(material_id)
            assert updated is not None
            updated_content = json.loads(updated.content_json)
            updated_stage = updated_content["stages"][0]
            self.assertEqual("stage-fixed", updated_stage["id"])
            self.assertEqual("After", updated_stage["summary"])
            self.assertEqual(["Cause"], updated_stage["causes"])
            self.assertEqual({"keep": True}, updated_stage["unknown_stage_field"])
            self.assertEqual({"old_key": ["keep"]}, updated_content["legacy_extra"])

    def test_publish_missing_or_failed_cover_leaves_no_public_half_record(self) -> None:
        png = b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + (1).to_bytes(4, "big") + (1).to_bytes(4, "big")
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            database_path = initialized_database(Path(directory) / "rusty.db")
            service = AnchorService(database_path)
            with session(database_path) as connection:
                project_id = int(
                    connection.execute(
                        "INSERT INTO projects(name, status, current_stage) VALUES ('P', 'imported', 'split')"
                    ).lastrowid
                )
            source_id = service.create_character_card(
                name="Project source",
                scope="project",
                project_id=project_id,
            )
            with session(database_path) as connection:
                connection.execute(
                    "UPDATE character_cards SET cover_path = 'assets/character-covers/missing.png' WHERE id = ?",
                    (source_id,),
                )
            with self.assertRaisesRegex(ValueError, "missing"):
                service.publish_project_character_to_public(source_id, ["name", "cover"])
            self.assertEqual(0, len(service.list_character_cards(scope="public")))

            service.save_character_cover(source_id, png)
            original_write = Path.write_bytes

            def fail_after_write(path: Path, data: bytes) -> int:
                original_write(path, data)
                raise OSError("forced cover write failure")

            with patch.object(Path, "write_bytes", fail_after_write):
                with self.assertRaisesRegex(OSError, "forced cover write failure"):
                    service.publish_project_character_to_public(source_id, ["name", "cover"])
            self.assertEqual(0, len(service.list_character_cards(scope="public")))
            cover_files = list((database_path.parent / "assets" / "character-covers").glob("*"))
            self.assertEqual(1, len(cover_files))


if __name__ == "__main__":
    unittest.main()
