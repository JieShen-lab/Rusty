from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.rewrite_version_map_service import RewriteVersionMapService


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
        self.payloads: dict[str, list[dict]] = {}

    def generate_json(self, stage: str, payload: dict) -> dict:
        self.payloads.setdefault(stage, []).append(copy.deepcopy(payload))
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
            if self.mode == "random_ids":
                replacements = {
                    node["id"]: f"random-{index * 777}"
                    for index, node in enumerate(observed["event_nodes"], 1)
                }
                for node in observed["event_nodes"]:
                    node["id"] = replacements[node["id"]]
                    node["causes"] = [replacements.get(item, item) for item in node["causes"]]
                    node["effects"] = [replacements.get(item, item) for item in node["effects"]]
                observed["event_nodes"][0]["source_span"] = {"start": 0, "end": 10}
                observed["event_nodes"][1]["source_span"] = {"start": 10, "end": 20}
                for link in observed["causal_links"]:
                    link["source_id"] = replacements.get(link["source_id"], link["source_id"])
                    link["target_id"] = replacements.get(link["target_id"], link["target_id"])
                return observed
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
        self.database = initialized_database(self.root / "rusty.db")
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

    def test_observed_node_ids_are_normalized_before_snapshot_persistence(self) -> None:
        self.llm.mode = "random_ids"
        completed = self.service.execute(self.plan()["id"])
        self.assertEqual("completed", completed["status"])
        maps = RewriteVersionMapService(self.database)
        structure = maps.get_rewrite_structure(completed["result_version_id"])
        persisted_ids = {
            node["id"] for node in structure["structured"]["event_nodes"]
        }
        segment_ids = {
            item["node_id"]
            for item in maps.list_segments(completed["result_version_id"])
            if item["segment_kind"] == "event_node"
            and item["skeleton_version_id"] == structure["skeleton_version_id"]
        }
        self.assertEqual({"discover", "leave"}, persisted_ids)
        self.assertEqual(persisted_ids, segment_ids)

    def test_detects_missing_added_and_reordered_events(self) -> None:
        expectations = {
            "missing": "missing_event",
            "added": "added_key_event",
            "reordered": "event_order_changed",
        }
        for mode, issue_type in expectations.items():
            with self.subTest(mode=mode):
                self.llm.mode = mode
                completed = self.service.execute(self.plan()["id"])
                self.assertEqual("completed", completed["status"])
                self.assertIn(issue_type, {item["type"] for item in completed["issues"]})
                self.assertTrue(all(item["severity"] == "warning" for item in completed["issues"]))

    def test_detects_knowledge_and_boundary_state_changes(self) -> None:
        self.llm.mode = "knowledge"
        completed = self.service.execute(self.plan()["id"])
        self.assertIn(
            "knowledge_reveal_order_changed",
            {item["type"] for item in completed["issues"]},
        )
        self.llm.mode = "states"
        completed = self.service.execute(self.plan()["id"])
        types = {item["type"] for item in completed["issues"]}
        self.assertIn("required_start_state_changed", types)
        self.assertIn("required_end_state_changed", types)

    def test_creative_drift_is_visible_without_hidden_auto_repair(self) -> None:
        self.llm.mode = "missing"
        completed = self.service.execute(self.plan()["id"])
        self.assertEqual("completed", completed["status"])
        self.assertTrue(completed["issues"])
        self.assertNotIn("prose_rewrite_repair", self.llm.payloads)

    def test_plan_uses_source_skeleton_without_ai_target_duplication(self) -> None:
        invalid = skeleton()
        invalid["event_nodes"] = invalid["event_nodes"][1:]
        invalid["event_nodes"][0]["order"] = 1
        invalid["event_nodes"][0]["causes"] = []
        invalid["causal_links"] = []
        self.llm.plan_target = invalid
        planned = self.plan()
        self.assertEqual(skeleton(), planned["target_skeleton"])
        self.assertEqual(skeleton(), self.llm.payloads["prose_rewrite_plan"][-1]["source_skeleton"])

    def test_uses_effective_source_and_appends_to_immutable_version_lineage(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "Plot result containing ambush A.")
        parent = ChapterVersionService(self.database).list_versions(self.chapter_id)[0]

        run = self.plan()
        self.assertEqual(
            "Plot result containing ambush A.",
            self.llm.payloads["prose_rewrite_plan"][-1]["source_text"],
        )
        completed = self.service.execute(run["id"])
        versions = ChapterVersionService(self.database).list_versions(self.chapter_id)
        current = versions[0]
        self.assertEqual("completed", completed["status"])
        self.assertEqual(parent["id"], current["parent_version_id"])
        self.assertEqual("prose_rewrite", current["source_operation"])
        self.assertEqual(completed["result_version_id"], current["id"])

    def test_explicit_historical_source_preserves_true_parent(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "version one")
        v1 = ChapterVersionService(self.database).list_versions(self.chapter_id)[0]
        self.projects.save_chapter_rewrite(self.chapter_id, "version two")
        v2 = ChapterVersionService(self.database).list_versions(self.chapter_id)[0]
        run = self.service.plan(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            source_skeleton=skeleton(),
            preservation_policy=POLICY,
            source_selection={"kind": "rewrite_version", "version_id": v1["id"]},
        )
        completed = self.service.execute(run["id"])
        v3 = ChapterVersionService(self.database).get_version(
            completed["result_version_id"]
        )
        self.assertEqual(v1["id"], v3["parent_version_id"])
        self.assertEqual("version two", ChapterVersionService(self.database).get_version(v2["id"])["rewritten_text"])

    def test_completed_and_cancelled_runs_cannot_execute(self) -> None:
        completed = self.service.execute(self.plan()["id"])
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.service.execute(completed["id"])
        planned = self.plan()
        cancelled = self.service.cancel(planned["id"])
        self.assertEqual("cancelled", cancelled["status"])
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.service.execute(planned["id"])

    def test_version_insert_and_run_completion_are_one_transaction(self) -> None:
        run = self.plan()
        original = self.service.chapter_versions.append_chapter_rewrite_version

        def insert_then_fail(connection, **kwargs):
            original(connection, **kwargs)
            raise RuntimeError("injected prose completion failure")

        with mock.patch.object(
            self.service.chapter_versions,
            "append_chapter_rewrite_version",
            side_effect=insert_then_fail,
        ):
            with self.assertRaisesRegex(RuntimeError, "completion failure"):
                self.service.execute(run["id"])
        self.assertEqual(
            [], ChapterVersionService(self.database).list_versions(self.chapter_id)
        )
        self.assertIsNone(self.projects.get_chapter(self.chapter_id).rewritten_text)
        self.assertEqual("failed", self.service.get_run(run["id"])["status"])


if __name__ == "__main__":
    unittest.main()
