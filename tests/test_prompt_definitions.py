from __future__ import annotations

import json
import os
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

from tests.support import initialized_database

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db.schema import CURRENT_SCHEMA_VERSION, _migrate_to_v43
from rusty.services.prompt_compiler import PromptCompiler
from rusty.services.prompt_definition_service import PromptDefinitionService
from rusty.services.project_service import ProjectService


class PromptDefinitionTests(unittest.TestCase):
    def test_v43_migration_seeds_three_simple_prompt_kinds(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("CREATE TABLE projects (id INTEGER PRIMARY KEY)")
        _migrate_to_v43(connection)
        _migrate_to_v43(connection)
        kinds = {row[0] for row in connection.execute("SELECT kind FROM prompt_definitions")}
        self.assertEqual({"master", "workflow_task", "common_task"}, kinds)
        self.assertGreaterEqual(CURRENT_SCHEMA_VERSION, 43)

    def test_crud_project_copy_and_export_have_no_sync_layer(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n原文。", encoding="utf-8")
            database = initialized_database(root / "rusty.db")
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root)
            service = PromptDefinitionService(database)

            master = service.create_definition(
                name="自定义总提示词", description="", kind="master", content="初始规则",
                input_description="全部任务", is_default=False,
            )
            workflow = service.create_definition(
                name="剧情调整", description="", kind="workflow_task", workflow_key="plot_adjust",
                task_key="custom_analysis", content="任务规则", input_description="Source", is_default=False,
            )
            common = service.create_definition(
                name="摘要", description="", kind="common_task", task_key="summary_test",
                content="摘要规则", input_description="Source", is_default=False,
            )
            copied = service.initialize_project_master(project_id, master.id)
            service.update_definition(master.id, **{**master.__dict__, "content": "库中已修改"})
            project_edited = service.save_project_master(project_id, "工程独立修改")
            exported = service.export_project_master(project_id, name="工程导出")
            round_trip = service.import_definition(service.export_definition(workflow.id))
            service.delete_definition(common.id)
            deleted = service.get_definition(common.id)

        self.assertEqual("初始规则", copied["content"])
        self.assertEqual("工程独立修改", project_edited["content"])
        self.assertEqual("工程独立修改", exported.content)
        self.assertEqual("custom_analysis", round_trip.task_key)
        self.assertIsNone(deleted)

    def test_compiler_order_and_program_owned_output_contract(self) -> None:
        request = PromptCompiler().compile_creative_json(
            stage="chapter_summary",
            system_prompt="全局规则",
            task_prompt="用户可编辑任务规则：不要返回 JSON。",
            payload={"source_text": "原文"},
            user_instruction="本次要求",
            output_contract='JSON object: {"summary": string}',
            prompt_definition_id=8,
        )
        system, user = request.message_list()
        self.assertLess(system["content"].index("GLOBAL SYSTEM PROMPT"), system["content"].index("RUSTY OUTPUT AND SAFETY RULES"))
        self.assertLess(system["content"].index("RUSTY OUTPUT AND SAFETY RULES"), system["content"].index("CURRENT TASK PROMPT"))
        self.assertLess(user["content"].index("DYNAMIC CONTEXT"), user["content"].index("USER INSTRUCTION"))
        self.assertLess(user["content"].index("USER INSTRUCTION"), user["content"].index("OUTPUT CONTRACT"))
        self.assertEqual('JSON object: {"summary": string}', request.expected_output)
        self.assertEqual("rusty.native.creative.v1", request.ruleset_id)

    def test_plain_text_compiler_keeps_story_blocks_plain_and_only_serializes_author_style(self) -> None:
        request = PromptCompiler().compile_creative_text(
            stage="writing",
            system_prompt="系统规则",
            task_prompt="生成正文",
            payload={
                "source_text": "章节原文",
                "target_outline": "1. 新事件",
                "author_style": {"voice": "克制"},
            },
            user_instruction="",
            output_contract="只返回正文",
        )
        user = request.message_list()[1]["content"]
        self.assertIn("## 当前章节原文\n章节原文", user)
        self.assertIn("## 新大纲及细节\n1. 新事件", user)
        self.assertIn('## 作者风格\n{\n  "voice": "克制"\n}', user)
        self.assertNotIn('"source_text"', user)

        extraction = PromptCompiler().compile_creative_json(
            stage="author_style_extraction",
            system_prompt="系统规则",
            task_prompt="",
            payload={"sample_text": "整本原文", "extraction_prompt": "提取风格"},
            user_instruction="",
            output_contract="返回作者风格 JSON",
            plain_context=True,
        ).message_list()[1]["content"]
        self.assertIn("## 整本小说原文\n整本原文", extraction)
        self.assertIn("## 作者风格提取提示词\n提取风格", extraction)
        self.assertNotIn('"sample_text"', extraction)

    def test_project_creation_copies_selected_master_prompt(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            source = root / "book.txt"
            source.write_text("第一章\n原文。", encoding="utf-8")
            database = initialized_database(root / "rusty.db")
            prompts = PromptDefinitionService(database)
            master = prompts.create_definition(
                name="创建时总提示词", description="", kind="master", content="创建时复制",
                input_description="全部任务", is_default=False,
            )
            os.environ["RUSTY_API_TOKEN"] = "test-token"
            os.environ["RUSTY_DATABASE_PATH"] = str(database)
            from backend.api import create_app

            with TestClient(create_app(database)) as client:
                headers = {"X-Rusty-Token": "test-token"}
                preview = client.post(
                    "/api/projects/preview",
                    json={"source_path": str(source), "workspace_path": str(root)},
                    headers=headers,
                ).json()
                created = client.post(
                    "/api/projects",
                    json={
                        "preview_token": preview["preview_token"],
                        "project_kind": "rewrite",
                        "master_prompt_definition_id": master.id,
                    },
                    headers=headers,
                )
                project_id = created.json()["id"]
                copied = client.get(f"/api/projects/{project_id}/master-prompt").json()

        self.assertEqual(200, created.status_code)
        self.assertEqual("创建时复制", copied["content"])


if __name__ == "__main__":
    unittest.main()
