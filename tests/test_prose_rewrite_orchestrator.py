from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import (
    ProseRewriteOrchestrator,
    compare_skeletons,
)


def skeleton() -> dict:
    nodes = []
    for order, (node_id, summary) in enumerate(
        [("discover", "Hero discovers the letter."), ("leave", "Hero leaves town.")],
        1,
    ):
        nodes.append(
            {
                "id": node_id,
                "order": order,
                "event_type": "revelation" if order == 1 else "action",
                "summary": summary,
                "participants": ["Hero"],
                "location": "town",
                "time_state": {},
                "causes": [] if order == 1 else ["discover"],
                "effects": ["leave"] if order == 1 else [],
                "locked": order == 1,
                "source_span": None,
                "confidence": 1.0,
                "motivation": "protect the family",
                "knowledge_changes": ["letter known"] if order == 1 else [],
            }
        )
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": nodes,
        "causal_links": [
            {"source_id": "discover", "target_id": "leave", "relation": "causes"}
        ],
        "character_state_changes": [],
        "location_changes": [],
        "time_changes": [],
        "object_changes": [],
        "knowledge_changes": [{"character": "Hero", "fact": "letter"}],
        "relationship_changes": [],
        "foreshadowing": [{"id": "seal"}],
        "open_threads": [],
        "resolved_threads": [],
        "required_start_state": {"location": "town"},
        "required_end_state": {"location": "road", "letter_owned": True},
        "editable_points": [],
        "source_references": [],
    }


POLICY = {
    "events": True,
    "event_order": True,
    "character_motivations": True,
    "behavior_results": True,
    "knowledge_reveal_order": True,
    "causal_links": True,
    "foreshadowing": True,
    "required_start_state": True,
    "required_end_state": True,
    "locked_node_ids": ["discover"],
}


class ProseRewriteOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        source = self.root / "book.txt"
        source.write_text("1. One\nOriginal baseline.", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind="rewrite"
        )
        self.chapter_id = self.projects.list_chapters(self.project_id)[0].id
        self.service = ProseRewriteOrchestrator(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan(self):
        value = skeleton()
        return self.service.plan(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            source_skeleton=value,
            preservation_policy=POLICY,
            target_skeleton=copy.deepcopy(value),
            rewrite_plan={"style": "sparse noir", "pov": "third person"},
        )

    def test_preserves_events_and_states_while_changing_style(self) -> None:
        run = self.plan()
        completed = self.service.execute(
            run["id"],
            rewritten_text="Rain veiled the letter. By dawn, the hero was gone.",
            observed_skeleton=skeleton(),
        )
        chapter = self.projects.get_chapter(self.chapter_id)
        self.assertEqual("completed", completed["status"])
        self.assertEqual([], completed["issues"])
        self.assertIn("Rain", chapter.rewritten_text)
        self.assertEqual("Original baseline.", chapter.original_text)

    def test_detects_missing_added_and_reordered_events(self) -> None:
        expected = skeleton()
        missing = copy.deepcopy(expected)
        missing["event_nodes"] = missing["event_nodes"][:1]
        missing["event_nodes"][0]["effects"] = []
        missing["causal_links"] = []
        issues = compare_skeletons(expected, missing, POLICY)
        self.assertIn("missing_event", {issue["type"] for issue in issues})

        added = copy.deepcopy(expected)
        extra = copy.deepcopy(added["event_nodes"][-1])
        extra.update({"id": "fight", "order": 3, "summary": "Hero fights guards.", "causes": [], "effects": []})
        added["event_nodes"].append(extra)
        issues = compare_skeletons(expected, added, POLICY)
        self.assertIn("added_key_event", {issue["type"] for issue in issues})

        reordered = copy.deepcopy(expected)
        reordered["event_nodes"].reverse()
        for order, node in enumerate(reordered["event_nodes"], 1):
            node["order"] = order
        issues = compare_skeletons(expected, reordered, POLICY)
        self.assertIn("event_order_changed", {issue["type"] for issue in issues})

    def test_detects_knowledge_and_boundary_state_drift_without_writing(self) -> None:
        run = self.plan()
        drifted = skeleton()
        drifted["event_nodes"][0]["knowledge_changes"] = []
        drifted["required_start_state"] = {"location": "forest"}
        drifted["required_end_state"] = {"location": "sea"}
        blocked = self.service.execute(
            run["id"], rewritten_text="Invalid structural rewrite.", observed_skeleton=drifted
        )
        types = {issue["type"] for issue in blocked["issues"]}
        self.assertEqual("blocked", blocked["status"])
        self.assertIn("knowledge_reveal_order_changed", types)
        self.assertIn("required_start_state_changed", types)
        self.assertIn("required_end_state_changed", types)
        self.assertIsNone(self.projects.get_chapter(self.chapter_id).rewritten_text)

    def test_locked_node_cannot_be_removed_from_target_plan(self) -> None:
        source = skeleton()
        target = copy.deepcopy(source)
        target["event_nodes"] = target["event_nodes"][1:]
        target["event_nodes"][0]["order"] = 1
        target["event_nodes"][0]["causes"] = []
        target["causal_links"] = []
        with self.assertRaisesRegex(ValueError, "preservation policy"):
            self.service.plan(
                project_id=self.project_id,
                chapter_id=self.chapter_id,
                source_skeleton=source,
                preservation_policy=POLICY,
                target_skeleton=target,
                rewrite_plan={},
            )


if __name__ == "__main__":
    unittest.main()
