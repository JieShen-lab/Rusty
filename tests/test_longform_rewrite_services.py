from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.models import ParsedBook, ParsedChapter
from rusty.services.anchor_service import AnchorService
from rusty.services.context_service import ContextService, PromptBlock, PromptBudgeter, SceneTooLongError
from rusty.services.material_service import MaterialService
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.scene_service import SceneService


class LongformRewriteServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database_path = initialized_database(self.root / "rusty.db")
        self.source_path = self.root / "source.txt"
        self.source_path.write_text("source", encoding="utf-8")
        self.project_service = ProjectService(self.database_path)
        self.project_id = self.project_service.create_project(
            ParsedBook(
                title="Long form",
                author="Tester",
                language="zh",
                source_path=self.source_path,
                source_format="txt",
                source_encoding="utf-8",
                chapters=[
                    ParsedChapter(
                        index=1,
                        title="Chapter 1",
                        text=(
                            "Alice enters the hall.\n\n"
                            "“Where is the key?” Alice asks.\n\n"
                            "Meanwhile, Bob reaches the river.\n\n"
                            "At night, Bob hides the key."
                        ),
                    )
                ],
            ),
            self.root,
        )
        self.chapter = self.project_service.list_chapters(self.project_id)[0]

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_original_source_is_immutable_and_rewrite_is_versioned_separately(self) -> None:
        source = SceneService(self.database_path).get_source_version(self.chapter.id)
        self.assertEqual(self.chapter.original_text, source["original_text"])
        self.project_service.save_chapter_rewrite(self.chapter.id, "A different draft.")
        self.assertEqual(self.chapter.original_text, self.project_service.get_chapter(self.chapter.id).original_text)
        with session(self.database_path) as connection:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute("UPDATE chapters SET original_text = 'mutated' WHERE id = ?", (self.chapter.id,))

    def test_scene_boundaries_are_saved_and_confirmed_boundaries_survive_reanalysis(self) -> None:
        service = SceneService(self.database_path)
        starts = [self.chapter.original_text.index("Meanwhile"), self.chapter.original_text.index("At night")]
        proposed = service.split_chapter(self.chapter.id, proposed_boundaries=starts, source="ai")
        self.assertEqual(3, len(proposed))
        confirmed = service.confirm_boundaries(self.chapter.id)
        self.assertTrue(all(scene.user_confirmed for scene in confirmed))
        after_reanalysis = service.split_chapter(self.chapter.id, proposed_boundaries=[starts[0]], source="ai")
        self.assertEqual([scene.id for scene in confirmed], [scene.id for scene in after_reanalysis])
        self.assertEqual(self.chapter.original_text, "".join(scene.original_text for scene in confirmed))

    def test_fact_ledger_and_dynamic_character_state_are_separate_from_character_card(self) -> None:
        scene_service = SceneService(self.database_path)
        scene = scene_service.split_chapter(self.chapter.id)[0]
        card_service = AnchorService(self.database_path)
        card_id = card_service.create_character_card(name="Alice", personality="Patient")
        facts = scene_service.save_fact_ledger(
            scene.id,
            {
                "events": ["Alice enters"],
                "knowledge_states": {"Alice": ["the key is missing"]},
                "required_end_state": {"location": "hall"},
            },
        )
        state = scene_service.save_character_state(
            scene.id,
            "Alice",
            {"injuries": ["left arm"], "location": "hall", "possessions": ["map"]},
            character_card_id=card_id,
        )
        self.assertEqual(["Alice enters"], facts["events"])
        self.assertEqual(["left arm"], state["injuries"])
        self.assertEqual("Patient", card_service.get_character_card(card_id).personality)

    def test_prompt_budget_keeps_required_blocks_and_drops_complete_optional_blocks(self) -> None:
        compiled = PromptBudgeter().compile(
            [
                PromptBlock("system_rules", "system rules", 1, True),
                PromptBlock("user_instruction", "user request", 2, True),
                PromptBlock("current_original_scene", "scene text", 3, True),
                PromptBlock("global_summary", "summary " * 500, 15),
            ],
            model_context_tokens=120,
            reserved_output_tokens=50,
        )
        included = {block.key for block in compiled.included_blocks()}
        self.assertEqual(
            {"system_rules", "user_instruction", "current_original_scene"},
            included,
        )
        dropped = next(block for block in compiled.blocks if block.key == "global_summary")
        self.assertEqual("dropped_over_budget", dropped.decision)
        with self.assertRaises(SceneTooLongError):
            PromptBudgeter().compile(
                [PromptBlock("current_original_scene", "汉" * 200, 3, True)],
                model_context_tokens=120,
                reserved_output_tokens=20,
            )

    def test_sliding_window_uses_previous_rewrite_and_next_original_preview(self) -> None:
        scene_service = SceneService(self.database_path)
        starts = [self.chapter.original_text.index("Meanwhile"), self.chapter.original_text.index("At night")]
        scenes = scene_service.adjust_boundaries(self.chapter.id, starts)
        workflow = RewriteWorkflowService(self.database_path)
        skeleton = workflow.create_skeleton(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scenes[0].id,
            nodes=[{"id": "n1", "event": "Alice enters"}],
        )
        confirmed = workflow.confirm_skeleton(skeleton.skeleton_id)
        plan_id = workflow.create_skeleton_rewrite_plan(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scenes[0].id,
            skeleton_version_id=confirmed.version_id,
            plan=_plan(),
        )
        workflow.confirm_plan(plan_id)
        workflow.save_rewrite_version(
            scenes[0].id,
            "Rewritten Alice ending.",
            plan_id=plan_id,
            skeleton_version_id=confirmed.version_id,
        )
        window = ContextService(self.database_path).build_sliding_window(scenes[1].id)
        self.assertTrue(window["previous_rewritten_tail"].endswith("Rewritten Alice ending."))
        self.assertTrue(window["current_original_scene"].startswith("Meanwhile"))
        self.assertTrue(window["next_original_preview"].startswith("At night"))

    def test_manual_retrieval_precedes_layered_automatic_results(self) -> None:
        scene = SceneService(self.database_path).split_chapter(self.chapter.id)[0]
        material_id = MaterialService(self.database_path).create_material(
            material_type="scene_reference",
            scope="project",
            project_id=self.project_id,
            name="Key clue",
            description="The key belongs to Bob.",
            content={"events": [{"event": "Bob hides the key"}]},
        )
        results = ContextService(self.database_path).retrieve(
            scene.id,
            keywords=["key"],
            manual_material_ids=[material_id],
        )
        self.assertEqual("manual", results[0]["retrieval_type"])
        self.assertEqual(str(material_id), results[0]["source_id"])
        self.assertEqual(1.0, results[0]["confidence"])

    def test_two_rewrite_modes_require_confirmed_skeleton_and_plan(self) -> None:
        scene = SceneService(self.database_path).split_chapter(self.chapter.id)[0]
        workflow = RewriteWorkflowService(self.database_path)
        skeleton = workflow.create_skeleton(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scene.id,
            nodes=[{"id": "n1", "event": "Alice enters"}],
        )
        with self.assertRaises(ValueError):
            workflow.create_skeleton_rewrite_plan(
                project_id=self.project_id,
                chapter_id=self.chapter.id,
                scene_id=scene.id,
                skeleton_version_id=skeleton.version_id,
                plan=_plan(),
            )
        confirmed = workflow.confirm_skeleton(skeleton.skeleton_id)
        skeleton_plan = workflow.create_skeleton_rewrite_plan(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scene.id,
            skeleton_version_id=confirmed.version_id,
            plan=_plan(),
        )
        self.assertEqual("skeleton_rewrite", workflow.get_plan(skeleton_plan)["mode"])
        material_id = MaterialService(self.database_path).create_material(
            material_type="plot_skeleton",
            scope="project",
            project_id=self.project_id,
            name="Inserted event",
            content={"events": [{"event": "Bob hides the key"}]},
        )
        expansion_plan = workflow.create_expansion_plan(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scene.id,
            skeleton_version_id=confirmed.version_id,
            plan=_plan(),
            material_mappings=[
                {
                    "material_id": material_id,
                    "insertion_after_node": "n1",
                    "usage_mode": "required",
                    "event_nodes": [{"id": "m1", "event": "Bob hides the key"}],
                    "impact": {"characters": ["Bob"], "events": ["hide"], "states": {"key": "hidden"}},
                }
            ],
        )
        self.assertEqual("expansion", workflow.get_plan(expansion_plan)["mode"])

    def test_consistency_schema_and_targeted_repair_preserve_version_diff(self) -> None:
        scene = SceneService(self.database_path).split_chapter(self.chapter.id)[0]
        workflow = RewriteWorkflowService(self.database_path)
        skeleton = workflow.confirm_skeleton(
            workflow.create_skeleton(
                project_id=self.project_id,
                chapter_id=self.chapter.id,
                scene_id=scene.id,
                nodes=[{"id": "n1", "event": "Alice enters"}],
            ).skeleton_id
        )
        plan_id = workflow.create_skeleton_rewrite_plan(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scene.id,
            skeleton_version_id=skeleton.version_id,
            plan=_plan(),
        )
        workflow.confirm_plan(plan_id)
        source_version_id = workflow.save_rewrite_version(
            scene.id,
            "Paragraph one.\n\nParagraph two.\n\nParagraph three.",
            plan_id=plan_id,
            skeleton_version_id=skeleton.version_id,
        )
        check = _consistency(revision_required=True)
        workflow.save_consistency_check(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=scene.id,
            check_scope="scene",
            result=check,
        )
        repair_id = workflow.targeted_repair(
            scene_id=scene.id,
            source_version_id=source_version_id,
            paragraph_start=1,
            paragraph_end=1,
            issues=["missing event"],
            replacement_text="Fixed paragraph two.",
            affected_facts={"events": ["fixed"]},
        )
        with session(self.database_path) as connection:
            repair = connection.execute("SELECT * FROM targeted_repairs WHERE id = ?", (repair_id,)).fetchone()
            versions = connection.execute(
                "SELECT rewritten_text FROM scene_rewrite_versions WHERE scene_id = ? ORDER BY version",
                (scene.id,),
            ).fetchall()
        self.assertEqual("Paragraph two.", repair["before_text"])
        self.assertEqual(2, len(versions))
        self.assertIn("Fixed paragraph two.", versions[-1]["rewritten_text"])
        self.assertIn("Paragraph one.", versions[-1]["rewritten_text"])


def _plan() -> dict[str, object]:
    return {
        "sequence": ["n1"],
        "preserve": ["Alice enters"],
        "modify": [],
        "add": [],
        "material_insertions": [],
        "character_changes": {},
        "expected_end_state": {"location": "hall"},
    }


def _consistency(revision_required: bool) -> dict[str, object]:
    return {
        "missing_events": [],
        "altered_facts": [],
        "unsupported_additions": [],
        "character_conflicts": [],
        "knowledge_conflicts": [],
        "timeline_conflicts": [],
        "transition_issues": [],
        "style_repetition": [],
        "revision_required": revision_required,
    }


if __name__ == "__main__":
    unittest.main()
