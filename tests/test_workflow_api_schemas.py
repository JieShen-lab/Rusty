from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from backend.api import create_app
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService


class WorkflowAPISchemaTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database = Path(self.tempdir.name) / "workflow-api.db"
        os.environ["RUSTY_API_TOKEN"] = "workflow-schema-token"
        self.client = TestClient(create_app(self.database))
        self.headers = {"X-Rusty-Token": "workflow-schema-token"}

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def assert_validation_error(self, response) -> None:
        self.assertEqual(422, response.status_code, response.text)
        body = response.json()
        self.assertIsInstance(body.get("detail"), list)
        self.assertTrue(body["detail"])

    def plot_payload(self, mode: str) -> dict:
        return {
            "project_id": 1,
            "generation_mode": mode,
            "start_anchor": {"anchor_type": "document_end"},
            "user_direction": "continue",
        }

    def test_missing_required_field_is_rejected(self) -> None:
        response = self.client.post(
            "/api/projects/1/branches",
            headers=self.headers,
            json={"branch_mode": "fork", "start_anchor": {"anchor_type": "document_end"}},
        )
        self.assert_validation_error(response)

    def test_prose_source_requires_explicit_skeleton_version(self) -> None:
        response = self.client.post(
            "/api/prose-rewrite/runs",
            headers=self.headers,
            json={
                "project_id": 1,
                "chapter_id": 1,
                "source_skeleton": {},
                "preservation_policy": {},
                "source": {"kind": "current"},
            },
        )
        self.assert_validation_error(response)

    def test_invalid_generation_mode_is_rejected(self) -> None:
        payload = self.plot_payload("parallel_universe")
        response = self.client.post(
            "/api/plot-generation/runs", headers=self.headers, json=payload
        )
        self.assert_validation_error(response)

    def test_invalid_anchor_type_is_rejected(self) -> None:
        response = self.client.post(
            "/api/projects/1/branches",
            headers=self.headers,
            json={
                "name": "invalid anchor",
                "branch_mode": "fork",
                "start_anchor": {"anchor_type": "paragraph_middle"},
            },
        )
        self.assert_validation_error(response)

    def test_removed_fork_and_rejoin_mode_is_rejected(self) -> None:
        response = self.client.post(
            "/api/plot-generation/runs",
            headers=self.headers,
            json=self.plot_payload("fork_and_rejoin"),
        )
        self.assert_validation_error(response)

    def test_open_continuation_rejects_return_anchor(self) -> None:
        payload = self.plot_payload("open_continuation")
        payload["return_anchor"] = {"anchor_type": "chapter_end", "chapter_id": 1}
        response = self.client.post(
            "/api/plot-generation/runs", headers=self.headers, json=payload
        )
        self.assert_validation_error(response)

    def test_removed_canon_endpoint_is_not_exposed(self) -> None:
        response = self.client.post(
            "/api/canon-change/patches/1/review",
            headers=self.headers,
            json={"decision": "apply_everything"},
        )
        self.assertEqual(404, response.status_code)

    def test_removed_seam_review_endpoint_is_not_exposed(self) -> None:
        response = self.client.post(
            "/api/plot-generation/runs/1/seams",
            headers=self.headers,
            json={"reviews": [{"seam_id": 1, "decision": "apply"}]},
        )
        self.assertEqual(404, response.status_code)

    def test_unknown_fields_are_rejected_at_each_nested_boundary(self) -> None:
        response = self.client.post(
            "/api/projects/1/branches",
            headers=self.headers,
            json={
                "name": "unknown",
                "branch_mode": "fork",
                "start_anchor": {
                    "anchor_type": "document_end",
                    "untrusted_offset": 3,
                },
                "unexpected": True,
            },
        )
        self.assert_validation_error(response)

    def test_anchor_preview_resolves_current_rewrite_version_semantic_span(self) -> None:
        root = Path(self.tempdir.name)
        source = root / "anchor-preview.txt"
        source.write_text(
            "1. One\n张三进入大厅。\n\n张三与李四争吵。\n\n张三离开大厅。",
            encoding="utf-8",
        )
        projects = ProjectService(self.database)
        project_id = projects.create_project(
            projects.preview_book(source), root, project_kind="rewrite"
        )
        chapter = projects.list_chapters(project_id)[0]
        scenes = SceneService(self.database).split_chapter(
            chapter.id,
            proposed_boundaries=[9, 19],
        )
        rewritten = "张三推门进入大厅。\n\n他与李四激烈争吵。\n\n最终张三离去。"
        projects.save_chapter_rewrite(chapter.id, rewritten)
        version_id = ChapterVersionService(self.database).resolve_chapter_source(
            chapter.id, {"kind": "current"}
        ).source_version_id
        self.assertIsNotNone(version_id)
        response = self.client.post(
            "/api/story-anchors/preview",
            headers=self.headers,
            json={
                "project_id": project_id,
                "source": {"kind": "current"},
                "anchor": {
                    "anchor_type": "scene_end",
                    "scene_id": scenes[1].id,
                    "source_version_id": version_id,
                    "side": "after",
                },
            },
        )
        self.assertEqual(400, response.status_code, response.text)
        self.assertIn("anchor_unmapped", response.json()["message"])

    def test_anchor_preview_rejects_unknown_nested_fields(self) -> None:
        response = self.client.post(
            "/api/story-anchors/preview",
            headers=self.headers,
            json={
                "project_id": 1,
                "source": {"kind": "current", "trusted": True},
                "anchor": {"anchor_type": "document_end"},
            },
        )
        self.assert_validation_error(response)

    def test_source_selection_is_a_strict_discriminated_union(self) -> None:
        for source in (
            {"kind": "rewrite_version"},
            {"kind": "current", "version_id": 3},
            {"kind": "unknown"},
            {"kind": "original", "unexpected": True},
        ):
            with self.subTest(source=source):
                payload = self.plot_payload("open_continuation")
                payload["source"] = source
                response = self.client.post(
                    "/api/plot-generation/runs",
                    headers=self.headers,
                    json=payload,
                )
                self.assert_validation_error(response)


if __name__ == "__main__":
    unittest.main()
