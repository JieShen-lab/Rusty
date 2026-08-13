from __future__ import annotations

import sys
import tempfile
import unittest
import os
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_version_map_service import RewriteVersionMapService
from rusty.services.scene_service import SceneService
from rusty.services.shared_analysis_service import SkeletonExtractionService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator
from fastapi.testclient import TestClient
from backend.api import create_app


def _structure(start: int, end: int) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [{
            "id": "argument", "order": 1, "event_type": "conflict",
            "summary": "Alice argues.", "participants": ["Alice"],
            "location": "hall", "time_state": {}, "causes": [], "effects": [],
            "locked": True, "source_span": {"start": start, "end": end},
            "confidence": 1.0,
        }],
        "causal_links": [], "character_state_changes": [], "location_changes": [],
        "time_changes": [], "object_changes": [], "knowledge_changes": [],
        "relationship_changes": [], "foreshadowing": [], "open_threads": [],
        "resolved_threads": [], "required_start_state": {}, "required_end_state": {},
        "editable_points": [], "source_references": [],
    }


class RewriteSnapshotProvenanceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = initialized_database(self.root / "rusty.db")
        self.original = "Alice enters.\n\nAlice argues.\n\nAlice leaves."
        source = self.root / "book.txt"
        source.write_text(f"1. Chapter\n{self.original}", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind="rewrite"
        )
        self.chapter = self.projects.list_chapters(self.project_id)[0]
        self.scenes = SceneService(self.database).split_chapter(
            self.chapter.id,
            proposed_boundaries=[
                self.original.index("Alice argues."),
            ],
        )
        event_start = self.original.index("Alice argues.")
        SkeletonExtractionService(self.database).save_extraction(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=self.scenes[1].id,
            skeleton=_structure(event_start, event_start + len("Alice argues.")),
        )
        self.versions = ChapterVersionService(self.database)
        self.maps = RewriteVersionMapService(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_historical_restore_clones_map_and_structure_exactly(self) -> None:
        self.projects.save_chapter_rewrite(
            self.chapter.id,
            "Alice strides inside. Alice loudly argues. Alice departs.",
        )
        v1 = self.versions.list_versions(self.chapter.id)[0]
        self.projects.save_chapter_rewrite(
            self.chapter.id,
            "Alice strides inside. An alarm sounds. Alice loudly argues. Alice departs.",
        )

        restored = self.versions.restore_version(v1["id"])

        self.assertEqual(v1["rewritten_text"], restored["rewritten_text"])
        source_segments = self.maps.list_segments(v1["id"])
        restored_segments = self.maps.list_segments(restored["id"])
        comparable = lambda item: {
            key: value for key, value in item.items()
            if key not in {"id", "rewrite_version_id", "skeleton_version_id"}
        }
        self.assertEqual(
            [comparable(item) for item in source_segments],
            [comparable(item) for item in restored_segments],
        )
        source_structure = self.maps.get_rewrite_structure(v1["id"])
        restored_structure = self.maps.get_rewrite_structure(restored["id"])
        self.assertEqual(source_structure["structured"], restored_structure["structured"])
        self.assertNotEqual(
            source_structure["skeleton_version_id"],
            restored_structure["skeleton_version_id"],
        )

    def test_restore_original_uses_identity_scene_offsets(self) -> None:
        # The source is one paragraph but has three semantic scenes, so a
        # paragraph-count heuristic cannot accidentally satisfy this test.
        self.projects.save_chapter_rewrite(self.chapter.id, "A wholly different draft.")
        self.projects.save_chapter_rewrite(self.chapter.id, "")
        restored = self.versions.list_versions(self.chapter.id)[0]
        scene_segments = {
            item["source_scene_id"]: item
            for item in self.maps.list_segments(restored["id"])
            if item["segment_kind"] == "scene"
        }

        self.assertEqual(len(self.scenes), len(scene_segments))
        for scene in self.scenes:
            segment = scene_segments[scene.id]
            self.assertEqual(scene.original_start_offset, segment["start_offset"])
            self.assertEqual(scene.original_end_offset, segment["end_offset"])
            self.assertEqual("identity", segment["mapping_method"])
            self.assertEqual(1.0, segment["confidence"])
        structure = self.maps.get_rewrite_structure(restored["id"])
        node = next(
            item for item in self.maps.list_segments(restored["id"])
            if item["segment_kind"] == "event_node"
            and item["skeleton_version_id"] == structure["skeleton_version_id"]
        )
        expected_start = self.original.index("Alice argues.")
        self.assertEqual(expected_start, node["start_offset"])
        self.assertEqual(expected_start + len("Alice argues."), node["end_offset"])
        self.assertEqual("identity", node["mapping_method"])

    def test_arbitrary_manual_edit_marks_overlaps_unresolved(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter.id, self.original)
        middle = self.scenes[1]
        edited = (
            self.original[: middle.original_start_offset]
            + "The confrontation changes completely. "
            + self.original[middle.original_end_offset :]
        )

        self.projects.save_chapter_rewrite(self.chapter.id, edited)

        current = self.versions.list_versions(self.chapter.id)[0]
        overlap = next(
            item for item in self.maps.list_segments(current["id"])
            if item["segment_kind"] == "scene"
            and item["source_scene_id"] == middle.id
        )
        self.assertTrue(overlap["needs_remap"])
        self.assertLessEqual(overlap["confidence"], 0.5)
        self.assertEqual("semantic", overlap["mapping_method"])
        self.assertEqual("needs_recompute", current["fact_chain_status"])

    def test_historical_versions_load_only_their_own_structure(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter.id, self.original)
        v1 = self.versions.list_versions(self.chapter.id)[0]
        structure_v1 = self.maps.get_rewrite_structure(v1["id"])
        self.projects.save_chapter_rewrite(
            self.chapter.id, self.original.replace("Alice leaves.", "Alice stays.")
        )
        v2 = self.versions.list_versions(self.chapter.id)[0]
        structure_v2 = self.maps.get_rewrite_structure(v2["id"])

        self.assertNotEqual(
            structure_v1["skeleton_version_id"], structure_v2["skeleton_version_id"]
        )
        os.environ["RUSTY_API_TOKEN"] = "snapshot-token"
        client = TestClient(create_app(self.database))
        response = client.get(f"/api/chapter-rewrite-versions/{v1['id']}/skeleton")
        self.assertEqual(200, response.status_code, response.text)
        self.assertEqual(v1["id"], response.json()["rewrite_version_id"])
        self.assertEqual(
            structure_v1["skeleton_version_id"], response.json()["skeleton_version_id"]
        )

        prose = ProseRewriteOrchestrator(self.database, ai_client=object())
        with self.assertRaisesRegex(ValueError, "does not belong"):
            prose.plan(
                project_id=self.project_id,
                chapter_id=self.chapter.id,
                source_skeleton=structure_v1["structured"],
                source_skeleton_version_id=structure_v1["skeleton_version_id"],
                source_selection={"kind": "rewrite_version", "version_id": v2["id"]},
                preservation_policy={},
            )


if __name__ == "__main__":
    unittest.main()
