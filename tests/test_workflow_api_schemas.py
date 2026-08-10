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

    def test_fork_and_rejoin_requires_return_anchor(self) -> None:
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

    def test_invalid_patch_decision_is_rejected(self) -> None:
        response = self.client.post(
            "/api/canon-change/patches/1/review",
            headers=self.headers,
            json={"decision": "apply_everything"},
        )
        self.assert_validation_error(response)

    def test_invalid_seam_decision_is_rejected_without_source_text_payload(self) -> None:
        response = self.client.post(
            "/api/plot-generation/runs/1/seams",
            headers=self.headers,
            json={"reviews": [{"seam_id": 1, "decision": "apply"}]},
        )
        self.assert_validation_error(response)

    def test_legacy_authoritative_source_text_is_rejected(self) -> None:
        response = self.client.post(
            "/api/plot-generation/runs/1/seams",
            headers=self.headers,
            json={
                "reviews": [{"seam_id": 1, "decision": "confirmed"}],
                "current_source_text": "untrusted",
            },
        )
        self.assert_validation_error(response)

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
