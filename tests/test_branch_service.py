from __future__ import annotations

import sqlite3
import json
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
from rusty.db.schema import _migrate_to_v30


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
        parent_scene = self.service.save_scene(
            parent["id"],
            title="Parent scene",
            generated_text="The parent route continues.",
            facts_after={"route": "parent"},
        )
        child = self.service.create_branch(
            project_id=self.project_id,
            parent_branch_id=parent["id"],
            base_source_version_id=parent_scene["version_id"],
            name="child",
            branch_mode="fork",
            start_anchor=self.anchor("text_offset", text_offset=4, side="at"),
        )
        self.assertEqual("rejoin", parent["downstream_strategy"])
        self.assertEqual(parent["id"], child["parent_branch_id"])
        self.assertEqual("branch", child["base_source_kind"])
        self.assertEqual(parent_scene["version_id"], child["base_source_version_id"])
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

    def test_branch_chapters_order_scenes_and_versions(self) -> None:
        branch = self.service.create_branch(
            project_id=self.project_id,
            name="chapter route",
            branch_mode="open_continuation",
            start_anchor=self.anchor("document_end"),
        )
        first = self.service.create_chapter(
            branch["id"],
            title="New chapter one",
            summary="First expansion chapter",
            facts_before={"location": "gate"},
            facts_after={"location": "road"},
        )
        second = self.service.create_chapter(
            branch["id"],
            title="New chapter two",
            summary="Second expansion chapter",
            facts_before={"location": "road"},
            facts_after={"location": "inn"},
        )
        first_scene = self.service.save_scene(
            branch["id"],
            branch_chapter_id=first["id"],
            title="Departure",
            generated_text="The traveler departs.",
        )
        second_scene = self.service.save_scene(
            branch["id"],
            branch_chapter_id=first["id"],
            title="Crossroads",
            generated_text="The traveler reaches the crossroads.",
        )
        self.service.save_scene(
            branch["id"],
            branch_chapter_id=second["id"],
            title="Arrival",
            generated_text="The traveler reaches the inn.",
        )
        chapters = self.service.list_chapters(branch["id"])
        self.assertEqual(["New chapter one", "New chapter two"], [c["title"] for c in chapters])
        self.assertEqual([1, 2], [first_scene["scene_index"], second_scene["scene_index"]])
        self.assertEqual(2, len(chapters[0]["scenes"]))
        export = self.service.compose_export(branch["id"])
        self.assertEqual(self.chapter.original_text, export["baseline_history"][0]["original_text"])
        self.assertEqual(2, len(export["branch_chapters"]))

        revised = self.service.save_chapter_version(
            first["id"],
            title="Revised chapter one",
            summary="Revised summary",
            facts_before={"location": "gate"},
            facts_after={"location": "bridge"},
        )
        restored = self.service.restore_chapter_version(first["id"], first["version_id"])
        self.assertEqual(2, revised["version"])
        self.assertEqual(3, restored["version"])
        self.assertEqual("First expansion chapter", restored["summary"])
        self.assertEqual("restore", restored["source_kind"])

    def test_child_branch_can_anchor_to_parent_chapter_and_scene(self) -> None:
        parent = self.service.create_branch(
            project_id=self.project_id,
            name="parent content",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        chapter = self.service.create_chapter(parent["id"], title="Parent chapter")
        scene = self.service.save_scene(
            parent["id"],
            branch_chapter_id=chapter["id"],
            title="Parent scene",
            generated_text="Parent branch text.",
        )
        child_from_chapter = self.service.create_branch(
            project_id=self.project_id,
            parent_branch_id=parent["id"],
            name="chapter child",
            branch_mode="fork",
            start_anchor=self.anchor(
                "branch_chapter", branch_chapter_id=chapter["id"]
            ),
        )
        child_from_scene = self.service.create_branch(
            project_id=self.project_id,
            parent_branch_id=parent["id"],
            base_source_version_id=scene["version_id"],
            name="scene child",
            branch_mode="fork",
            start_anchor=self.anchor(
                "branch_scene",
                branch_scene_id=scene["id"],
                source_version_id=scene["version_id"],
            ),
        )
        self.assertEqual(chapter["id"], child_from_chapter["start_anchor"]["branch_chapter_id"])
        self.assertEqual(scene["id"], child_from_scene["start_anchor"]["branch_scene_id"])

    def test_v30_migrates_legacy_branch_scenes_without_losing_text_or_facts(self) -> None:
        branch = self.service.create_branch(
            project_id=self.project_id,
            name="legacy scenes",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        scene = self.service.save_scene(
            branch["id"],
            title="Legacy generated scene",
            generated_text="Legacy generated text.",
            facts_after={"legacy_fact": "preserved"},
        )
        connection = sqlite3.connect(self.database)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = OFF")
            connection.execute(
                "UPDATE branch_scenes SET branch_chapter_id = NULL, scene_index = NULL WHERE id = ?",
                (scene["id"],),
            )
            connection.execute(
                "DELETE FROM branch_chapter_versions WHERE branch_chapter_id = ?",
                (scene["branch_chapter_id"],),
            )
            connection.execute(
                "DELETE FROM branch_chapters WHERE id = ?",
                (scene["branch_chapter_id"],),
            )
            _migrate_to_v30(connection)
            connection.commit()
            migrated = connection.execute(
                """
                SELECT s.branch_chapter_id, s.scene_index,
                       v.generated_text, v.facts_after_json
                FROM branch_scenes s
                JOIN branch_scene_versions v ON v.branch_scene_id = s.id
                WHERE s.id = ?
                """,
                (scene["id"],),
            ).fetchone()
        finally:
            connection.close()
        self.assertIsNotNone(migrated["branch_chapter_id"])
        self.assertEqual(1, migrated["scene_index"])
        self.assertEqual("Legacy generated text.", migrated["generated_text"])
        self.assertEqual(
            {"legacy_fact": "preserved"}, json.loads(migrated["facts_after_json"])
        )

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

    def test_anchor_resources_must_belong_to_target_project(self) -> None:
        other_project_id, other_chapter, other_scenes, other_skeleton_version = (
            self._create_other_project()
        )
        invalid_anchors = [
            self.anchor("chapter_end", chapter_id=other_chapter.id),
            self.anchor("scene_end", scene_id=other_scenes[0].id),
            self.anchor(
                "skeleton_node",
                skeleton_version_id=other_skeleton_version,
                node_id="other-node",
            ),
        ]
        for anchor in invalid_anchors:
            with self.subTest(anchor_type=anchor["anchor_type"]):
                with self.assertRaisesRegex(ValueError, "target project"):
                    self.service.create_branch(
                        project_id=self.project_id,
                        name="cross-project",
                        branch_mode="fork",
                        start_anchor=anchor,
                    )
        self.assertNotEqual(self.project_id, other_project_id)

    def test_skeleton_anchor_requires_existing_node(self) -> None:
        with self.assertRaisesRegex(ValueError, "node_id does not exist"):
            self.service.create_branch(
                project_id=self.project_id,
                name="missing node",
                branch_mode="fork",
                start_anchor=self.anchor(
                    "skeleton_node",
                    skeleton_version_id=self.skeleton_version_id,
                    node_id="missing-node",
                ),
            )

    def test_anchor_offsets_hash_and_return_order_are_validated(self) -> None:
        invalid_offsets = [-1, len(self.chapter.original_text) + 1]
        for offset in invalid_offsets:
            with self.subTest(offset=offset):
                with self.assertRaisesRegex(ValueError, "text_offset"):
                    self.service.create_branch(
                        project_id=self.project_id,
                        name="invalid offset",
                        branch_mode="fork",
                        start_anchor=self.anchor(
                            "text_offset",
                            chapter_id=self.chapter.id,
                            text_offset=offset,
                            side="after",
                        ),
                    )
        with self.assertRaisesRegex(ValueError, "text_offset"):
            self.service.create_branch(
                project_id=self.project_id,
                name="scene offset",
                branch_mode="fork",
                start_anchor=self.anchor(
                    "scene_end",
                    scene_id=self.scenes[0].id,
                    text_offset=self.scenes[0].original_end_offset + 1,
                ),
            )
        with self.assertRaisesRegex(ValueError, "source_hash"):
            self.service.create_branch(
                project_id=self.project_id,
                name="stale hash",
                branch_mode="fork",
                start_anchor=self.anchor(
                    "chapter_end", chapter_id=self.chapter.id, source_hash="stale"
                ),
            )
        created = self.service.create_branch(
            project_id=self.project_id,
            name="server hash",
            branch_mode="fork",
            start_anchor=self.anchor("scene_end", scene_id=self.scenes[0].id),
        )
        self.assertEqual(
            self.service.source_hash(self.scenes[0].original_text),
            created["start_anchor"]["source_hash"],
        )
        with self.assertRaisesRegex(ValueError, "earlier"):
            self.service.create_branch(
                project_id=self.project_id,
                name="reverse rejoin",
                branch_mode="fork_and_rejoin",
                start_anchor=self.anchor("chapter_end", chapter_id=self.chapter.id),
                return_anchor=self.anchor("chapter_start", chapter_id=self.chapter.id),
            )

    def test_delete_rejects_unfinished_run_then_soft_deletes_content(self) -> None:
        branch = self.service.create_branch(
            project_id=self.project_id,
            name="running",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        chapter = self.service.create_chapter(branch["id"], title="generated")
        scene = self.service.save_scene(
            branch["id"],
            branch_chapter_id=chapter["id"],
            title="generated scene",
            generated_text="Generated branch text.",
        )
        connection = sqlite3.connect(self.database)
        try:
            cursor = connection.execute(
                """
                INSERT INTO plot_generation_runs(
                    project_id, branch_id, generation_mode, output_topology,
                    start_anchor_json, target_skeleton_json
                ) VALUES (?, ?, 'fork', 'branch', '{}', '{}')
                """,
                (self.project_id, branch["id"]),
            )
            run_id = int(cursor.lastrowid)
            connection.commit()
        finally:
            connection.close()
        with self.assertRaisesRegex(ValueError, "unfinished"):
            self.service.delete_branch(branch["id"])
        connection = sqlite3.connect(self.database)
        try:
            connection.execute(
                "UPDATE plot_generation_runs SET status = 'completed' WHERE id = ?",
                (run_id,),
            )
            connection.commit()
        finally:
            connection.close()
        self.service.delete_branch(branch["id"])
        with self.assertRaises(FileNotFoundError):
            self.service.get_branch(branch["id"])
        self.assertEqual([], self.service.list_scenes(branch["id"]))
        connection = sqlite3.connect(self.database)
        try:
            deleted = connection.execute(
                "SELECT deleted_at FROM branch_scenes WHERE id = ?", (scene["id"],)
            ).fetchone()[0]
            original = connection.execute(
                "SELECT original_text FROM chapters WHERE id = ?", (self.chapter.id,)
            ).fetchone()[0]
        finally:
            connection.close()
        self.assertIsNotNone(deleted)
        self.assertEqual(self.chapter.original_text, original)

    def test_child_branch_rejects_another_parent_scene_version(self) -> None:
        first = self.service.create_branch(
            project_id=self.project_id,
            name="first parent",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        second = self.service.create_branch(
            project_id=self.project_id,
            name="second parent",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        second_scene = self.service.save_scene(
            second["id"], title="second", generated_text="second route"
        )
        with self.assertRaisesRegex(ValueError, "specified parent branch"):
            self.service.create_branch(
                project_id=self.project_id,
                parent_branch_id=first["id"],
                name="invalid child",
                branch_mode="fork",
                start_anchor=self.anchor(
                    "text_offset",
                    text_offset=0,
                    source_version_id=second_scene["version_id"],
                ),
            )

    def test_base_source_version_must_exist_in_parent_branch(self) -> None:
        parent = self.service.create_branch(
            project_id=self.project_id,
            name="parent",
            branch_mode="fork",
            start_anchor=self.anchor("document_end"),
        )
        with self.assertRaisesRegex(FileNotFoundError, "Base source version"):
            self.service.create_branch(
                project_id=self.project_id,
                parent_branch_id=parent["id"],
                base_source_version_id=999999,
                name="invalid base",
                branch_mode="fork",
                start_anchor=self.anchor("document_end"),
            )

    def _create_other_project(self):
        other_root = self.root / "other"
        other_root.mkdir()
        other_source = other_root / "other.txt"
        other_source.write_text(
            "1. Other\nAnother gate opens.\n\nAnother traveler enters.",
            encoding="utf-8",
        )
        projects = ProjectService(self.database)
        project_id = projects.create_project(
            projects.preview_book(other_source),
            other_root,
            project_kind="branch",
        )
        chapter = projects.list_chapters(project_id)[0]
        scenes = SceneService(self.database).split_chapter(
            chapter.id,
            proposed_boundaries=[chapter.original_text.index("Another traveler")],
        )
        skeleton = RewriteWorkflowService(self.database).create_skeleton(
            project_id=project_id,
            chapter_id=chapter.id,
            scene_id=scenes[0].id,
            nodes=[{"id": "other-node", "event": "Another gate opens."}],
        )
        return project_id, chapter, scenes, skeleton.version_id

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
