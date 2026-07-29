from __future__ import annotations

import sqlite3
import os
import sys
import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.project_service import ProjectService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.scene_service import SceneService


class BranchServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.source = self.root / "book.txt"
        self.original = "The gate opens.\n\nThe traveler enters."
        self.source.write_text(f"1. One\n{self.original}", encoding="utf-8")
        projects = ProjectService(self.database)
        self.project_id = projects.create_project(
            projects.preview_book(self.source), self.root, project_kind="branch"
        )
        self.chapter = projects.list_chapters(self.project_id)[0]
        scene_service = SceneService(self.database)
        self.scenes = scene_service.split_chapter(
            self.chapter.id,
            proposed_boundaries=[self.chapter.original_text.index("The traveler")],
        )
        workflow = RewriteWorkflowService(self.database)
        skeleton = workflow.create_skeleton(
            project_id=self.project_id,
            chapter_id=self.chapter.id,
            scene_id=self.scenes[0].id,
            nodes=[{"id": "gate", "event": "The gate opens."}],
        )
        self.skeleton_version_id = skeleton.version_id
        self.service = BranchService(self.database)
        self.hash = self.service.source_hash(self.chapter.original_text)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def anchor(self, anchor_type: str, **values):
        return {
            "anchor_type": anchor_type,
            "source_hash": self.hash,
            **values,
        }

    def test_document_chapter_scene_and_skeleton_anchors_create_branches(self) -> None:
        anchors = [
            self.anchor("document_end"),
            self.anchor("chapter_end", chapter_id=self.chapter.id),
            self.anchor("scene_end", scene_id=self.scenes[0].id),
            self.anchor(
                "skeleton_node",
                skeleton_version_id=self.skeleton_version_id,
                node_id="gate",
            ),
        ]
        created = [
            self.service.create_branch(
                project_id=self.project_id,
                name=f"branch-{index}",
                branch_mode="fork",
                start_anchor=anchor,
            )
            for index, anchor in enumerate(anchors)
        ]
        self.assertEqual(
            ["document_end", "chapter_end", "scene_end", "skeleton_node"],
            [item["start_anchor"]["anchor_type"] for item in created],
        )
        self.assertTrue(all(item["return_anchor"] is None for item in created))

    def test_rejoin_and_child_branch_preserve_parent_topology(self) -> None:
        parent = self.service.create_branch(
            project_id=self.project_id,
            name="parent",
            branch_mode="fork_and_rejoin",
            start_anchor=self.anchor("scene_start", scene_id=self.scenes[0].id),
            return_anchor=self.anchor("chapter_end", chapter_id=self.chapter.id),
        )
        child = self.service.create_branch(
            project_id=self.project_id,
            parent_branch_id=parent["id"],
            base_source_version_id=7,
            name="child",
            branch_mode="fork",
            start_anchor=self.anchor("text_offset", text_offset=4, side="at"),
        )
        self.assertEqual("rejoin", parent["downstream_strategy"])
        self.assertEqual(parent["id"], child["parent_branch_id"])
        self.assertEqual("branch", child["base_source_kind"])
        self.assertEqual(7, child["base_source_version_id"])
        with self.assertRaisesRegex(ValueError, "child branches"):
            self.service.delete_branch(parent["id"])

    def test_branch_content_is_independent_and_delete_does_not_touch_original(self) -> None:
        branch = self.service.create_branch(
            project_id=self.project_id,
            name="continuation",
            branch_mode="open_continuation",
            start_anchor=self.anchor("document_end"),
        )
        saved = self.service.save_scene(
            branch["id"],
            title="New road",
            generated_text="The traveler chooses another road.",
            facts_after={"route": "east"},
        )
        listed = self.service.list_scenes(branch["id"])
        self.assertEqual(saved["generated_text"], listed[0]["generated_text"])

        self.service.delete_branch(branch["id"])
        connection = sqlite3.connect(self.database)
        try:
            original = connection.execute(
                "SELECT original_text FROM chapters WHERE id = ?", (self.chapter.id,)
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertEqual(self.chapter.original_text, original)

    def test_seam_requires_matching_source_hash_and_explicit_review(self) -> None:
        branch = self.service.create_branch(
            project_id=self.project_id,
            name="seam",
            branch_mode="fork",
            start_anchor=self.anchor("chapter_start", chapter_id=self.chapter.id),
        )
        seam = self.service.create_seam(
            branch["id"],
            seam_kind="entry",
            operation="replace_range",
            original_text=self.chapter.original_text,
            proposed_text="A revised bridge.",
            source_range={"start": 0, "end": len(self.chapter.original_text)},
            source_hash=self.hash,
            reason="Connect the new route.",
        )
        self.assertEqual("draft", seam["status"])
        with self.assertRaisesRegex(ValueError, "hash mismatch"):
            self.service.review_seam(
                seam["id"], decision="confirmed", current_source_text="changed"
            )
        rejected = self.service.review_seam(
            seam["id"], decision="rejected", current_source_text="changed"
        )
        self.assertEqual("rejected", rejected["status"])

        second = self.service.create_seam(
            branch["id"],
            seam_kind="entry",
            operation="insert_after",
            original_text=self.chapter.original_text,
            proposed_text="Bridge.",
            source_range={"start": len(self.chapter.original_text)},
            source_hash=self.hash,
            reason="Transition",
        )
        confirmed = self.service.review_seam(
            second["id"],
            decision="confirmed",
            current_source_text=self.chapter.original_text,
        )
        self.assertEqual("confirmed", confirmed["status"])

    def test_missing_parent_and_invalid_anchor_are_rejected(self) -> None:
        with self.assertRaises(FileNotFoundError):
            self.service.create_branch(
                project_id=self.project_id,
                parent_branch_id=999,
                name="orphan",
                branch_mode="fork",
                start_anchor=self.anchor("document_end"),
            )
        with self.assertRaisesRegex(ValueError, "chapter_id"):
            self.service.create_branch(
                project_id=self.project_id,
                name="invalid",
                branch_mode="fork",
                start_anchor=self.anchor("chapter_end"),
            )

    def test_branch_api_lists_and_persists_created_branch(self) -> None:
        os.environ["RUSTY_API_TOKEN"] = "test-token"
        from backend.api import create_app

        client = TestClient(create_app(self.database))
        response = client.post(
            f"/api/projects/{self.project_id}/branches",
            headers={"X-Rusty-Token": "test-token"},
            json={
                "name": "API branch",
                "branch_mode": "open_continuation",
                "start_anchor": {"anchor_type": "document_end"},
            },
        )
        listed = client.get(f"/api/projects/{self.project_id}/branches")
        self.assertEqual(200, response.status_code)
        self.assertEqual("API branch", response.json()["name"])
        self.assertIn(
            "API branch", [branch["name"] for branch in listed.json()]
        )


if __name__ == "__main__":
    unittest.main()
