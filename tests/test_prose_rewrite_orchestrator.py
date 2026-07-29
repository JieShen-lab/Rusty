from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator


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
        "causal_links": [{"source_id": "discover", "target_id": "leave", "relation": "causes"}],
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


class FakeProseLLM:
    def __init__(self) -> None:
        self.mode = "valid"
        self.repair_success = True
        self.plan_target = skeleton()

    def generate_json(self, stage: str, payload: dict) -> dict:
        if stage == "prose_rewrite_plan":
            return {
                "target_skeleton": copy.deepcopy(self.plan_target),
                "rewrite_plan": {"style": "sparse noir", "pov": "third person"},
            }
        if stage == "prose_rewrite_generate":
            return {"rewritten_text": f"DRAFT:{self.mode}: Rain veiled the letter."}
        if stage == "prose_rewrite_repair":
            return {
                "rewritten_text": (
                    "REPAIRED: Rain veiled the letter. By dawn, the hero was gone."
                    if self.repair_success
                    else payload["rewritten_text"]
                )
            }
        if stage == "extract_observed_skeleton":
            observed = copy.deepcopy(skeleton())
            text = payload["text"]
            if text.startswith("REPAIRED") or self.mode == "valid":
                return observed
            if self.mode == "missing":
                observed["event_nodes"] = observed["event_nodes"][:1]
                observed["event_nodes"][0]["effects"] = []
                observed["causal_links"] = []
            elif self.mode == "added":
                extra = copy.deepcopy(observed["event_nodes"][-1])
                extra.update({"id": "fight", "order": 3, "causes": [], "effects": []})
                observed["event_nodes"].append(extra)
            elif self.mode == "reordered":
                observed["event_nodes"].reverse()
                for order, node in enumerate(observed["event_nodes"], 1):
                    node["order"] = order
            elif self.mode == "knowledge":
                observed["event_nodes"][0]["knowledge_changes"] = []
            elif self.mode == "states":
                observed["required_start_state"] = {"location": "forest"}
                observed["required_end_state"] = {"location": "sea"}
            return observed
        raise AssertionError(stage)


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
        self.llm = FakeProseLLM()
        self.service = ProseRewriteOrchestrator(self.database, ai_client=self.llm)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def plan(self):
        return self.service.plan(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            source_skeleton=skeleton(),
            preservation_policy=POLICY,
            user_direction="change style only",
        )

    def test_generates_prose_and_extracts_observed_skeleton_internally(self) -> None:
        completed = self.service.execute(self.plan()["id"])
        chapter = self.projects.get_chapter(self.chapter_id)
        self.assertEqual("completed", completed["status"])
        self.assertEqual([], completed["issues"])
        self.assertIn("Rain", chapter.rewritten_text)
        self.assertEqual("Original baseline.", chapter.original_text)

    def test_detects_missing_added_and_reordered_events(self) -> None:
        expectations = {
            "missing": "missing_event",
            "added": "added_key_event",
            "reordered": "event_order_changed",
        }
        for mode, issue_type in expectations.items():
            with self.subTest(mode=mode):
                self.llm.mode = mode
                blocked = self.service.execute(self.plan()["id"], auto_repair=False)
                self.assertEqual("blocked", blocked["status"])
                self.assertIn(issue_type, {item["type"] for item in blocked["issues"]})

    def test_detects_knowledge_and_boundary_state_changes(self) -> None:
        self.llm.mode = "knowledge"
        blocked = self.service.execute(self.plan()["id"], auto_repair=False)
        self.assertIn(
            "knowledge_reveal_order_changed",
            {item["type"] for item in blocked["issues"]},
        )
        self.llm.mode = "states"
        blocked = self.service.execute(self.plan()["id"], auto_repair=False)
        types = {item["type"] for item in blocked["issues"]}
        self.assertIn("required_start_state_changed", types)
        self.assertIn("required_end_state_changed", types)

    def test_auto_repair_passes_before_saving(self) -> None:
        self.llm.mode = "missing"
        completed = self.service.execute(self.plan()["id"], auto_repair=True)
        self.assertEqual("completed", completed["status"])
        self.assertTrue(completed["rewritten_text"].startswith("REPAIRED"))

    def test_failed_repair_does_not_write_chapter(self) -> None:
        self.llm.mode = "missing"
        self.llm.repair_success = False
        blocked = self.service.execute(self.plan()["id"], auto_repair=True)
        self.assertEqual("blocked", blocked["status"])
        self.assertIsNone(self.projects.get_chapter(self.chapter_id).rewritten_text)

    def test_locked_node_cannot_be_removed_by_ai_plan(self) -> None:
        invalid = skeleton()
        invalid["event_nodes"] = invalid["event_nodes"][1:]
        invalid["event_nodes"][0]["order"] = 1
        invalid["event_nodes"][0]["causes"] = []
        invalid["causal_links"] = []
        self.llm.plan_target = invalid
        with self.assertRaisesRegex(ValueError, "preservation policy"):
            self.plan()


if __name__ == "__main__":
    unittest.main()
