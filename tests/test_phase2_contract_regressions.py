from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import initialized_database
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from backend.api import create_app
from rusty.db import session
from rusty.models import ParsedBook, ParsedChapter
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.anchor_service import AnchorService
from rusty.services.context_service import ContextService
from rusty.services.document_library_service import DocumentLibraryService
from rusty.services.material_service import MaterialService
from rusty.services.model_service import ModelService
from rusty.services.project_service import ProjectService
from rusty.services.prompt_service import PromptService, SceneRule
from rusty.services.rewrite_workflow_service import CONSISTENCY_KEYS, SCENE_ANALYSIS_KEYS, RewriteWorkflowService
from rusty.services.scene_boundary_ai_service import SceneBoundaryAIService
from rusty.services.scene_rewrite_orchestrator import SceneRewriteOrchestrator
from rusty.services.scene_service import SceneService
from rusty.services.structured_model_service import StructuredModelService
from rusty.services.style_service import StyleTemplateService


class RecordingQueueAI(AIClient):
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.messages.append(messages)
        value = self.responses.pop(0)
        return AIResponse(
            text=value if isinstance(value, str) else json.dumps(value, ensure_ascii=False),
            token_usage={"total_tokens": 23},
            elapsed_ms=7,
        )


class PhaseTwoContractRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = initialized_database(self.root / "rusty.db")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, text: str) -> tuple[int, int]:
        source = self.root / "source.txt"
        source.write_text(text, encoding="utf-8")
        project_id = ProjectService(self.database).create_project(
            ParsedBook(
                title="Contract",
                author="",
                language="zh",
                source_path=source,
                source_format="txt",
                source_encoding="utf-8",
                chapters=[ParsedChapter(index=1, title="Chapter", text=text)],
            ),
            self.root / "workspace",
        )
        chapter_id = ProjectService(self.database).list_chapters(project_id)[0].id
        return project_id, chapter_id

    def configure_model(self) -> None:
        ModelService(self.database).create_model(
            display_name="queue",
            provider="openai_compatible",
            base_url="https://example.test/v1",
            model_name="queue-model",
            is_default=True,
        )

    def create_exact_document(self) -> tuple[DocumentLibraryService, int, int, int]:
        source = self.root / f"document-{len(list(self.root.glob('document-*.txt')))}.txt"
        source.write_text("0123456789ABCDEFGHIJ", encoding="utf-8")
        with patch.dict(os.environ, {"RUSTY_DOCUMENT_LIBRARY_PATH": str(self.root / "library")}):
            service = DocumentLibraryService(self.database)
            document = service.import_document(source).document
            revision = service.list_revisions(document.id)[0]
            with session(self.database) as connection:
                connection.execute(
                    "DELETE FROM library_document_chapters WHERE revision_id = ?",
                    (revision.id,),
                )
                connection.execute(
                    "UPDATE library_documents SET chapter_count = 0 WHERE id = ?",
                    (document.id,),
                )
            service.mark_chapter(document.id, revision.id, "A", 3, 8)
            service.mark_chapter(document.id, revision.id, "B", 10, 15)
            chapters = service.list_chapters(document.id)
            return (
                service,
                document.id,
                next(item.id for item in chapters if item.title == "A"),
                next(item.id for item in chapters if item.title == "B"),
            )

    def test_create_chapter_before_preserves_exact_offsets_and_same_line_ranges(self) -> None:
        service, document_id, _, b_id = self.create_exact_document()
        old_revision = service.list_revisions(document_id)[0]
        service.create_chapter(
            document_id,
            title="Inserted",
            text="NEW",
            position="before",
            current_chapter_id=b_id,
        )
        chapters = service.list_chapters(document_id)
        a = next(item for item in chapters if item.title == "A")
        inserted = next(item for item in chapters if item.title == "Inserted")
        b = next(item for item in chapters if item.title == "B")
        inserted_text = service.get_content(document_id, inserted.id).text
        self.assertEqual((3, 8), (a.start_offset, a.end_offset))
        self.assertEqual("34567", service.get_content(document_id, a.id).text)
        self.assertEqual((10 + len(inserted_text), 15 + len(inserted_text)), (b.start_offset, b.end_offset))
        self.assertEqual("ABCDE", service.get_content(document_id, b.id).text)
        self.assertEqual(["A", "Inserted", "B"], [item.title for item in chapters])
        with session(self.database) as connection:
            old = connection.execute(
                "SELECT start_offset, end_offset FROM library_document_chapters "
                "WHERE revision_id = ? ORDER BY chapter_index",
                (old_revision.id,),
            ).fetchall()
        self.assertEqual([(3, 8), (10, 15)], [(int(row[0]), int(row[1])) for row in old])

    def test_create_chapter_after_shifts_only_following_exact_chapters(self) -> None:
        service, document_id, a_id, _ = self.create_exact_document()
        service.create_chapter(
            document_id,
            title="Inserted",
            text="AFTER",
            position="after",
            current_chapter_id=a_id,
        )
        chapters = service.list_chapters(document_id)
        a = next(item for item in chapters if item.title == "A")
        inserted = next(item for item in chapters if item.title == "Inserted")
        b = next(item for item in chapters if item.title == "B")
        delta = len(service.get_content(document_id, inserted.id).text)
        self.assertEqual((3, 8), (a.start_offset, a.end_offset))
        self.assertEqual((10 + delta, 15 + delta), (b.start_offset, b.end_offset))
        self.assertEqual("34567", service.get_content(document_id, a.id).text)
        self.assertEqual("ABCDE", service.get_content(document_id, b.id).text)

    def test_create_chapter_at_end_keeps_all_manual_ranges(self) -> None:
        service, document_id, _, _ = self.create_exact_document()
        service.create_chapter(document_id, title="Tail", text="END", position="end")
        chapters = service.list_chapters(document_id)
        a = next(item for item in chapters if item.title == "A")
        b = next(item for item in chapters if item.title == "B")
        tail = next(item for item in chapters if item.title == "Tail")
        self.assertEqual((3, 8), (a.start_offset, a.end_offset))
        self.assertEqual((10, 15), (b.start_offset, b.end_offset))
        self.assertGreaterEqual(tail.start_offset, 20)
        self.assertEqual("34567", service.get_content(document_id, a.id).text)
        self.assertEqual("ABCDE", service.get_content(document_id, b.id).text)
        self.assertIn("Tail", service.get_content(document_id, tail.id).text)

    def test_scene_stage_messages_contain_complete_unique_inputs_and_repair_chain(self) -> None:
        _, chapter_id = self.create_project("SOURCE-UNIQUE-A\n\nSOURCE-UNIQUE-B")
        scene_service = SceneService(self.database)
        scene = scene_service.split_chapter(chapter_id)[0]
        scene_service.confirm_boundaries(chapter_id)
        self.configure_model()
        analysis = {key: [] for key in SCENE_ANALYSIS_KEYS}
        analysis["risks"] = ["ANALYSIS-UNIQUE-RISK"]
        analysis["required_start_state"] = {"location": "START-UNIQUE"}
        analysis["required_end_state"] = {"location": "END-UNIQUE"}
        consistency = {key: [] for key in CONSISTENCY_KEYS}
        consistency["missing_events"] = [
            {
                "event": "ISSUE-UNIQUE",
                "paragraph_start": 0,
                "paragraph_end": 0,
            }
        ]
        consistency["revision_required"] = True
        final_check = {key: [] for key in CONSISTENCY_KEYS}
        final_check["revision_required"] = False
        queue = RecordingQueueAI(
            analysis,
            {"event_nodes": [{"id": "NODE-UNIQUE", "event": "SKELETON-UNIQUE", "required": True}]},
            {
                "sequence": ["SEQUENCE-UNIQUE"],
                "preserve": ["PRESERVE-UNIQUE"],
                "modify": ["MODIFY-UNIQUE"],
                "add": ["ADD-UNIQUE"],
                "material_insertions": [{"position": "INSERT-UNIQUE"}],
                "character_changes": {"A": "CHAR-CHANGE-UNIQUE"},
                "expected_end_state": {"location": "PLAN-END-UNIQUE"},
            },
            {
                "text": "CANDIDATE-UNIQUE-PARAGRAPH\n\nUNCHANGED-UNIQUE-PARAGRAPH",
                "facts_after": {"events": ["FACTS-AFTER-UNIQUE"]},
            },
            consistency,
            {
                "repairs": [
                    {
                        "paragraph_start": 0,
                        "paragraph_end": 0,
                        "issues": ["ISSUE-UNIQUE"],
                        "replacement_text": "REPAIRED-UNIQUE-PARAGRAPH",
                        "affected_facts": {"events": ["REPAIRED-FACT-UNIQUE"]},
                    }
                ]
            },
            final_check,
        )
        orchestrator = SceneRewriteOrchestrator(
            self.database,
            structured_model_service=StructuredModelService(self.database, ai_client=queue),
        )
        run = orchestrator.start(scene.id, mode="skeleton_rewrite", user_instruction="")
        confirmed = RewriteWorkflowService(self.database).confirm_skeleton(run["skeleton_id"])
        planned = orchestrator.generate_plan(run["id"], skeleton_version_id=confirmed.version_id)
        RewriteWorkflowService(self.database).confirm_plan(planned["plan_id"])
        completed = orchestrator.execute(run["id"], user_instruction="")
        self.assertEqual("completed", completed["status"])
        prompts = [messages[-1]["content"] for messages in queue.messages]
        self.assertIn("ANALYSIS-UNIQUE-RISK", prompts[1])
        self.assertIn("SKELETON-UNIQUE", prompts[2])
        for unique in ("SEQUENCE-UNIQUE", "MODIFY-UNIQUE", "ADD-UNIQUE", "INSERT-UNIQUE"):
            self.assertIn(unique, prompts[3])
        self.assertIn("CANDIDATE-UNIQUE-PARAGRAPH", prompts[4])
        self.assertIn("CANDIDATE-UNIQUE-PARAGRAPH", prompts[5])
        self.assertIn('"paragraph_start": 0', prompts[5])
        self.assertIn("REPAIRED-UNIQUE-PARAGRAPH", prompts[6])
        self.assertTrue(all("## USER_INSTRUCTION\n" in prompt for prompt in prompts))

    def test_planning_prompt_contains_material_mapping_and_stable_insertion(self) -> None:
        _, chapter_id = self.create_project("ORIGINAL-MAPPING-SOURCE")
        scene = SceneService(self.database).split_chapter(chapter_id)[0]
        self.configure_model()
        queue = RecordingQueueAI({})
        orchestrator = SceneRewriteOrchestrator(
            self.database,
            structured_model_service=StructuredModelService(self.database, ai_client=queue),
        )
        orchestrator._call_stage(
            scene.id,
            stage="planning",
            system_rules="planning",
            user_instruction="",
            task={
                "confirmed_skeleton": [{"id": "NODE-MAP-UNIQUE", "event": "event"}],
                "material_mappings": [
                    {
                        "material_id": 99,
                        "insertion_after_node": "NODE-MAP-UNIQUE",
                        "event_nodes": [{"event": "MATERIAL-EVENT-UNIQUE"}],
                    }
                ],
            },
            output_protocol="{}",
            validator=lambda value: value,
            model_id=None,
            character_ids=[],
            material_ids=[],
        )
        prompt = queue.messages[0][-1]["content"]
        self.assertIn("NODE-MAP-UNIQUE", prompt)
        self.assertIn("MATERIAL-EVENT-UNIQUE", prompt)

    def test_ai_scene_boundaries_call_model_and_preserve_confirmed_ranges(self) -> None:
        text = "FIRST-AI-SCENE\n\nSECOND-AI-SCENE"
        _, chapter_id = self.create_project(text)
        self.configure_model()
        split = text.index("SECOND")
        queue = RecordingQueueAI(
            {
                "scenes": [
                    {"title": "First", "start_offset": 0, "end_offset": split, "reasons": ["location"]},
                    {"title": "Second", "start_offset": split, "end_offset": len(text), "reasons": ["goal"]},
                ]
            }
        )
        service = SceneBoundaryAIService(
            self.database,
            structured_model_service=StructuredModelService(self.database, ai_client=queue),
        )
        proposed = service.analyze(chapter_id)
        self.assertIn(text, queue.messages[0][-1]["content"])
        self.assertFalse(proposed["scenes"][0].user_confirmed)
        confirmed = SceneService(self.database).confirm_boundaries(chapter_id)
        again = service.analyze(chapter_id)
        self.assertTrue(again["preserved_confirmed"])
        self.assertEqual([scene.id for scene in confirmed], [scene.id for scene in again["scenes"]])
        self.assertEqual(1, len(queue.messages))

    def test_fastapi_scene_boundary_object_contract_and_validation(self) -> None:
        text = "abcdefghi"
        project_id, chapter_id = self.create_project(text)
        with patch.dict(
            os.environ,
            {"RUSTY_API_TOKEN": "contract-token", "RUSTY_DATABASE_PATH": str(self.database)},
        ):
            client = TestClient(create_app(self.database))
            headers = {"X-Rusty-Token": "contract-token"}
            valid = [
                {"start_offset": 0, "end_offset": 3, "title": "A", "reasons": ["manual"]},
                {"start_offset": 3, "end_offset": len(text), "title": "B", "reasons": ["manual"]},
            ]
            response = client.post(
                f"/api/chapters/{chapter_id}/scenes/adjust",
                headers=headers,
                json={"boundaries": valid, "source": "user", "confirm": True},
            )
            self.assertEqual(200, response.status_code, response.text)
            self.assertEqual("abc", response.json()[0]["original_text"])
            for invalid in (
                [
                    {"start_offset": 0, "end_offset": 4, "title": "A", "reasons": []},
                    {"start_offset": 5, "end_offset": len(text), "title": "B", "reasons": []},
                ],
                [
                    {"start_offset": 0, "end_offset": 5, "title": "A", "reasons": []},
                    {"start_offset": 4, "end_offset": len(text), "title": "B", "reasons": []},
                ],
                [{"start_offset": 0, "end_offset": len(text) + 1, "title": "A", "reasons": []}],
            ):
                failed = client.post(
                    f"/api/chapters/{chapter_id}/scenes/adjust",
                    headers=headers,
                    json={"boundaries": invalid, "source": "user", "confirm": True},
                )
                self.assertIn(failed.status_code, (400, 422))
        self.assertIsNotNone(ProjectService(self.database).get_project(project_id))

    def test_exact_same_line_chapter_offsets_survive_edit_and_shift_following_chapter(self) -> None:
        source = self.root / "document.txt"
        source.write_text("0123456789ABCDEFGHIJ", encoding="utf-8")
        with patch.dict(os.environ, {"RUSTY_DOCUMENT_LIBRARY_PATH": str(self.root / "library")}):
            service = DocumentLibraryService(self.database)
            document = service.import_document(source).document
            revision = service.list_revisions(document.id)[0]
            with session(self.database) as connection:
                connection.execute("DELETE FROM library_document_chapters WHERE revision_id = ?", (revision.id,))
                connection.execute("UPDATE library_documents SET chapter_count = 0 WHERE id = ?", (document.id,))
            first = service.mark_chapter(document.id, revision.id, "inner", 3, 8)[0]
            service.mark_chapter(document.id, revision.id, "later", 10, 15)
            chapters = service.list_chapters(document.id)
            first = next(item for item in chapters if item.title == "inner")
            later = next(item for item in chapters if item.title == "later")
            self.assertEqual("34567", service.get_content(document.id, first.id).text)
            service.save_content(document.id, chapter_id=first.id, text="XYZ")
            new_chapters = service.list_chapters(document.id)
            new_first = next(item for item in new_chapters if item.title == "inner")
            new_later = next(item for item in new_chapters if item.title == "later")
            self.assertEqual("XYZ\n", service.get_content(document.id, new_first.id).text)
            self.assertEqual(later.start_offset - 1, new_later.start_offset)
            with self.assertRaisesRegex(ValueError, "overlaps"):
                service.mark_chapter(
                    document.id,
                    service.list_revisions(document.id)[0].id,
                    "overlap",
                    new_first.start_offset + 1,
                    new_first.end_offset,
                )

    def test_character_cover_copy_is_independent_and_delete_cleans_only_own_file(self) -> None:
        project_id, _ = self.create_project("cover")
        service = AnchorService(self.database)
        source_id = service.create_character_card(name="Cover Source")
        png = bytes.fromhex("89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489")
        service.save_character_cover(source_id, png)
        copy_id = service.copy_character_card(
            source_id,
            target_scope="project",
            target_project_id=project_id,
        )
        source = service.get_character_card(source_id)
        copied = service.get_character_card(copy_id)
        self.assertNotEqual(source.cover_path, copied.cover_path)
        source_file = service.character_cover_file(source_id)
        copied_file = service.character_cover_file(copy_id)
        self.assertEqual(source_file.read_bytes(), copied_file.read_bytes())
        service.delete_character_card(source_id)
        self.assertFalse(source_file.exists())
        self.assertTrue(copied_file.exists())
        service.delete_character_card(copy_id)
        self.assertFalse(copied_file.exists())

    def test_bound_style_rules_examples_and_recent_repetition_enter_context(self) -> None:
        text = "aaaabbbbcccc"
        project_id, chapter_id = self.create_project(text)
        prompt_id = PromptService(self.database).create_template(
            name="scene prompt",
            global_rules="PROMPT-GLOBAL-UNIQUE",
            rewrite_rules="PROMPT-REWRITE-UNIQUE",
            scene_rules=[
                SceneRule(
                    scene_key="general",
                    display_name="General",
                    rewrite_prompt="SCENE-RULE-UNIQUE",
                )
            ],
        )
        ProjectService(self.database).update_project_settings(
            project_id,
            prompt_template_id=prompt_id,
        )
        style_id = StyleTemplateService(self.database).create_template(
            name="style",
            global_prompt="STYLE-GLOBAL-UNIQUE",
            rewrite_prompt="STYLE-REWRITE-UNIQUE",
            style_profile={"examples": ["STYLE-EXAMPLE-UNIQUE"]},
        )
        StyleTemplateService(self.database).bind_project_style(project_id, style_id)
        scenes = SceneService(self.database).split_chapter(
            chapter_id,
            proposed_boundaries=[
                {"start_offset": 0, "end_offset": 4, "title": "one", "reasons": []},
                {"start_offset": 4, "end_offset": 8, "title": "two", "reasons": []},
                {"start_offset": 8, "end_offset": 12, "title": "three", "reasons": []},
            ],
        )
        with session(self.database) as connection:
            for scene in scenes[:2]:
                connection.execute(
                    """
                    INSERT INTO scene_style_contexts (
                        scene_id, scene_type, global_rules_json, scene_rules_json,
                        examples_json, recent_techniques_json, forbidden_repetitions_json
                    ) VALUES (?, 'general', '[]', '[]', '[]', ?, '[]')
                    """,
                    (scene.id, json.dumps(["REPEATED-TECHNIQUE-UNIQUE"])),
                )
        context = ContextService(self.database).build_style_context(scenes[-1].id)
        self.assertIn("STYLE-GLOBAL-UNIQUE", context["global_rules"])
        self.assertIn("PROMPT-GLOBAL-UNIQUE", context["global_rules"])
        self.assertIn("SCENE-RULE-UNIQUE", context["scene_rules"])
        self.assertIn("STYLE-EXAMPLE-UNIQUE", context["examples"])
        self.assertIn("repeated-technique-unique", context["forbidden_repetitions"])

    def test_plot_skeleton_and_scene_reference_remain_semantically_separate(self) -> None:
        project_id, chapter_id = self.create_project("EXPANSION-ORIGINAL")
        scene = SceneService(self.database).split_chapter(chapter_id)[0]
        SceneService(self.database).confirm_boundaries(chapter_id)
        materials = MaterialService(self.database)
        plot_id = materials.create_material(
            material_type="plot_skeleton",
            scope="public",
            name="Plot",
            raw_text="PLOT-MATERIAL-UNIQUE",
            content={
                "event_nodes": [
                    {"id": "PLOT-EVENT", "event": "PLOT-MATERIAL-UNIQUE", "required": True}
                ]
            },
        )
        reference_id = materials.create_material(
            material_type="scene_reference",
            scope="public",
            name="Reference",
            raw_text="SCENE-REFERENCE-UNIQUE",
        )
        extra_plot_id = materials.create_material(
            material_type="plot_skeleton",
            scope="public",
            name="Extra plot",
            content={"event_nodes": [{"id": "EXTRA", "event": "Extra", "required": True}]},
        )
        other_project_id, _ = self.create_project("OTHER")
        other_reference_id = materials.create_material(
            material_type="scene_reference",
            scope="project",
            project_id=other_project_id,
            name="Other project reference",
        )
        self.configure_model()
        analysis = {key: [] for key in SCENE_ANALYSIS_KEYS}
        analysis["required_start_state"] = {}
        analysis["required_end_state"] = {}
        consistency = {key: [] for key in CONSISTENCY_KEYS}
        consistency["revision_required"] = False
        queue = RecordingQueueAI(
            analysis,
            {"event_nodes": [{"id": "BASE-NODE", "event": "Base event", "required": True}]},
            {
                "sequence": ["Base event", "PLOT-MATERIAL-UNIQUE"],
                "preserve": ["Base event"],
                "modify": [],
                "add": ["PLOT-MATERIAL-UNIQUE"],
                "material_insertions": [{"material_id": plot_id, "after": "BASE-NODE"}],
                "character_changes": {},
                "expected_end_state": {},
            },
            {"text": "EXPANDED-TEXT", "facts_after": {}},
            consistency,
        )
        orchestrator = SceneRewriteOrchestrator(
            self.database,
            structured_model_service=StructuredModelService(self.database, ai_client=queue),
        )
        run = orchestrator.start(
            scene.id,
            mode="expansion",
            material_ids=[plot_id, reference_id],
        )
        confirmed = RewriteWorkflowService(self.database).confirm_skeleton(run["skeleton_id"])
        planned = orchestrator.generate_plan(
            run["id"],
            skeleton_version_id=confirmed.version_id,
            material_mappings=[
                {
                    "material_id": plot_id,
                    "insertion_after_node": "BASE-NODE",
                    "usage_mode": "required",
                    "impact": {"events": ["PLOT-MATERIAL-UNIQUE"]},
                }
            ],
            scene_reference_ids=[reference_id],
        )
        RewriteWorkflowService(self.database).confirm_plan(planned["plan_id"])
        with self.assertRaisesRegex(ValueError, "must be plot_skeleton"):
            orchestrator.execute(
                run["id"],
                plot_skeleton_material_ids=[reference_id],
                scene_reference_ids=[],
            )
        with self.assertRaisesRegex(ValueError, "must be scene_reference"):
            orchestrator.execute(
                run["id"],
                plot_skeleton_material_ids=[plot_id],
                scene_reference_ids=[extra_plot_id],
            )
        with self.assertRaisesRegex(ValueError, "both a plot skeleton and a scene reference"):
            orchestrator.execute(
                run["id"],
                plot_skeleton_material_ids=[plot_id],
                scene_reference_ids=[plot_id],
            )
        migrated_reference = materials.get_material(other_reference_id)
        self.assertIsNotNone(migrated_reference)
        assert migrated_reference is not None
        self.assertEqual("public", migrated_reference.scope)
        self.assertIsNone(migrated_reference.project_id)
        orchestrator.execute(
            run["id"],
            plot_skeleton_material_ids=[plot_id],
            scene_reference_ids=[reference_id],
        )
        planning_prompt = queue.messages[2][-1]["content"]
        rewrite_prompt = queue.messages[3][-1]["content"]
        self.assertIn("PLOT-MATERIAL-UNIQUE", planning_prompt)
        self.assertIn(f'"material_id": {plot_id}', planning_prompt)
        self.assertIn('"insertion_after_node": "BASE-NODE"', planning_prompt)
        plot_block = json.loads(_prompt_block(rewrite_prompt, "PLOT_SKELETON_MAPPINGS"))
        reference_block = json.loads(_prompt_block(rewrite_prompt, "SCENE_REFERENCE_CONSTRAINTS"))
        self.assertEqual([plot_id], [item["material_id"] for item in plot_block])
        self.assertEqual([reference_id], reference_block["material_ids"])

def _prompt_block(prompt: str, key: str) -> str:
    marker = f"## {key}\n"
    start = prompt.index(marker) + len(marker)
    end = prompt.find("\n## ", start)
    return prompt[start:] if end < 0 else prompt[start:end]


if __name__ == "__main__":
    unittest.main()
