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
from rusty.db import session
from rusty.services.project_service import ProjectService


class LegacyAnalysisMigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "legacy.db"
        self.source = self.root / "legacy.txt"
        self.source.write_text("1. 第一章\n原始正文。", encoding="utf-8")
        projects = ProjectService(self.database)
        project_id = projects.create_project(
            projects.preview_book(self.source), self.root, project_kind="rewrite"
        )
        chapter_id = projects.list_chapters(project_id)[0].id
        with session(self.database) as connection:
            connection.execute(
                "UPDATE projects SET project_kind = 'legacy_extract' WHERE id = ?",
                (project_id,),
            )
            connection.execute(
                """
                INSERT INTO chapter_summaries(
                    chapter_id, plot_summary, characters_json, key_events_json
                ) VALUES (?, '人物发现线索', '[{"name":"甲"}]', '["发现"]')
                """,
                (chapter_id,),
            )
            connection.execute(
                """
                INSERT INTO project_style_syntheses(project_id, synthesis_json)
                VALUES (?, '{"tone":"克制"}')
                """,
                (project_id,),
            )
            connection.execute(
                """
                INSERT INTO project_custom_prompts(project_id, prompt_key, prompt_text)
                VALUES (?, 'summary', '已有提示词')
                """,
                (project_id,),
            )
            skeleton = connection.execute(
                """
                INSERT INTO story_skeletons(project_id, chapter_id, scope, status)
                VALUES (?, ?, 'chapter', 'confirmed')
                """,
                (project_id, chapter_id),
            )
            connection.execute(
                """
                INSERT INTO story_skeleton_versions(
                    skeleton_id, version, nodes_json, skeleton_json, confirmed_at
                ) VALUES (?, 1, '[]', '{"event_nodes":[]}', CURRENT_TIMESTAMP)
                """,
                (int(skeleton.lastrowid),),
            )
        self.project_id = project_id
        self.chapter_id = chapter_id
        os.environ["RUSTY_API_TOKEN"] = "legacy-token"
        self.client = TestClient(create_app(self.database))
        self.headers = {"X-Rusty-Token": "legacy-token"}

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_export_returns_analysis_not_novel_txt(self) -> None:
        response = self.client.get(
            f"/api/projects/{self.project_id}/legacy-analysis/export"
        )
        self.assertEqual(200, response.status_code, response.text)
        payload = response.json()
        self.assertEqual("rusty.legacy_analysis_export.v1", payload["schema"])
        self.assertEqual("人物发现线索", payload["chapter_analyses"][0]["plot_summary"])
        self.assertEqual("克制", payload["style_analysis"]["synthesis"]["tone"])
        self.assertEqual("已有提示词", payload["generated_prompts"][0]["prompt_text"])
        self.assertEqual(1, len(payload["structured_skeletons"]))
        self.assertNotIn("output_path", payload)

    def test_create_rewrite_or_branch_with_independent_source_and_analysis(self) -> None:
        for kind, copy_analysis in (("rewrite", True), ("branch", False)):
            response = self.client.post(
                f"/api/projects/{self.project_id}/legacy-analysis/create-project",
                headers=self.headers,
                json={
                    "target_project_kind": kind,
                    "copy_source_text": True,
                    "copy_analysis_results": copy_analysis,
                },
            )
            self.assertEqual(200, response.status_code, response.text)
            created = response.json()
            self.assertNotEqual(self.project_id, created["id"])
            self.assertEqual(kind, created["project_kind"])
            service = ProjectService(self.database)
            copied = service.list_chapters(created["id"])[0]
            self.assertEqual("原始正文。", copied.original_text)
            self.assertIsNone(copied.rewritten_text)
            with session(self.database) as connection:
                count = connection.execute(
                    """
                    SELECT COUNT(*) FROM chapter_summaries s
                    JOIN chapters c ON c.id = s.chapter_id
                    WHERE c.project_id = ?
                    """,
                    (created["id"],),
                ).fetchone()[0]
                self.assertEqual(1 if copy_analysis else 0, count)
                connection.execute(
                    "UPDATE chapters SET rewritten_text = '独立修改' WHERE id = ?",
                    (copied.id,),
                )
        self.assertEqual(
            "原始正文。",
            ProjectService(self.database).get_chapter(self.chapter_id).original_text,
        )

    def test_rejects_non_legacy_source_and_unknown_fields(self) -> None:
        response = self.client.post(
            f"/api/projects/{self.project_id}/legacy-analysis/create-project",
            headers=self.headers,
            json={
                "target_project_kind": "rewrite",
                "copy_source_text": True,
                "copy_analysis_results": True,
                "unexpected": True,
            },
        )
        self.assertEqual(422, response.status_code)


if __name__ == "__main__":
    unittest.main()
