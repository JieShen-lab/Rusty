from __future__ import annotations

import copy
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.shared_analysis_service import SkeletonExtractionService
from rusty.services.structured_skeleton import validate_structured_skeleton


def skeleton_fixture() -> dict:
    return {
        "metadata": {"title": "Courtyard transition", "schema_version": 1},
        "event_nodes": [
            {
                "id": "enter",
                "order": 1,
                "event_type": "action",
                "summary": "The protagonist enters the courtyard.",
                "participants": ["protagonist"],
                "location": "courtyard",
                "time_state": {"phase": "night"},
                "causes": [],
                "effects": ["ambush"],
                "locked": True,
                "source_span": {"start": 0, "end": 12},
                "confidence": 1.0,
            },
            {
                "id": "ambush",
                "order": 2,
                "event_type": "conflict",
                "summary": "Hidden attackers spring the ambush.",
                "participants": ["protagonist", "attackers"],
                "location": "courtyard",
                "time_state": {"phase": "night"},
                "causes": ["enter"],
                "effects": [],
                "locked": False,
                "source_span": None,
                "confidence": 0.8,
            },
        ],
        "causal_links": [
            {"source_id": "enter", "target_id": "ambush", "relation": "enables"}
        ],
        "character_state_changes": [],
        "location_changes": [],
        "time_changes": [],
        "object_changes": [],
        "knowledge_changes": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "open_threads": [{"id": "attackers_identity"}],
        "resolved_threads": [],
        "required_start_state": {"location": "courtyard entrance"},
        "required_end_state": {"location": "courtyard"},
        "editable_points": [{"after_node_id": "enter"}],
        "source_references": [{"chapter_id": 1, "start": 0, "end": 12}],
    }


class StructuredSkeletonServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.source = self.root / "book.txt"
        self.source.write_text("1. One\nThe protagonist enters the courtyard.", encoding="utf-8")
        self.projects = ProjectService(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_structured_skeleton_versions_edit_confirm_and_trace_source(self) -> None:
        project_id = self.projects.create_project(
            self.projects.preview_book(self.source), self.root, project_kind="rewrite"
        )
        chapter_id = self.projects.list_chapters(project_id)[0].id
        service = SkeletonExtractionService(self.database)
        original = service.save_extraction(
            project_id=project_id,
            chapter_id=chapter_id,
            scene_id=None,
            skeleton=skeleton_fixture(),
        )
        edited_value = skeleton_fixture()
        edited_value["event_nodes"][1]["summary"] = "The attackers descend from the roof."
        workflow = RewriteWorkflowService(self.database)
        edited = workflow.revise_structured_skeleton(
            original.skeleton_id, edited_value, change_note="user edit"
        )
        confirmed = workflow.confirm_skeleton(original.skeleton_id, edited.version)
        first = workflow.get_skeleton_version(original.skeleton_id, 1)

        self.assertEqual(1, first.version)
        self.assertEqual(
            "Hidden attackers spring the ambush.",
            first.structured["event_nodes"][1]["summary"],
        )
        self.assertEqual("confirmed", confirmed.status)
        self.assertEqual(edited_value, confirmed.structured)
        self.assertEqual(
            {"location": "courtyard entrance"},
            confirmed.structured["required_start_state"],
        )
        self.assertEqual(
            {"location": "courtyard"}, confirmed.structured["required_end_state"]
        )

    def test_validation_rejects_invalid_order_causality_and_missing_fields(self) -> None:
        missing = skeleton_fixture()
        del missing["required_end_state"]
        with self.assertRaisesRegex(ValueError, "missing fields"):
            validate_structured_skeleton(missing)

        order = skeleton_fixture()
        order["event_nodes"][1]["order"] = 1
        with self.assertRaisesRegex(ValueError, "strictly increasing"):
            validate_structured_skeleton(order)

        causal = skeleton_fixture()
        causal["event_nodes"][1]["causes"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "unknown causal"):
            validate_structured_skeleton(causal)

    def test_legacy_plot_summary_is_read_without_fabricated_nodes(self) -> None:
        project_id = self.projects.create_project(
            self.projects.preview_book(self.source), self.root, project_kind="rewrite"
        )
        chapter_id = self.projects.list_chapters(project_id)[0].id
        connection = sqlite3.connect(self.database)
        connection.execute(
            "INSERT INTO chapter_summaries(chapter_id, plot_summary) VALUES (?, ?)",
            (chapter_id, "Legacy prose-only analysis."),
        )
        connection.commit()
        connection.close()

        result = RewriteWorkflowService(self.database).get_preferred_chapter_skeleton(
            chapter_id
        )

        self.assertEqual("legacy_plot_summary", result["format"])
        self.assertEqual("Legacy prose-only analysis.", result["plot_summary"])
        self.assertIsNone(result["structured"])

    def test_shared_skeleton_analysis_accepts_rewrite_and_branch_projects(self) -> None:
        service = SkeletonExtractionService(self.database)
        for kind in ("rewrite", "branch"):
            project_id = self.projects.create_project(
                self.projects.preview_book(self.source),
                self.root,
                project_name=kind,
                project_kind=kind,
            )
            chapter_id = self.projects.list_chapters(project_id)[0].id
            version = service.save_extraction(
                project_id=project_id,
                chapter_id=chapter_id,
                scene_id=None,
                skeleton=copy.deepcopy(skeleton_fixture()),
            )
            self.assertEqual(1, version.version)
            self.assertEqual("draft", version.status)


if __name__ == "__main__":
    unittest.main()
