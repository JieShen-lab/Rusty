from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from rusty.services.ai_client import AIResponse
from rusty.services.model_service import ModelService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.prompt_compiler import CompiledRequest, PromptCompiler
from rusty.services.scene_service import SceneService
from rusty.services.workflow_ai import WorkflowAI


def _skeleton(summary: str = "生成事件") -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [{
            "id": "event-1", "order": 1, "event_type": "event",
            "summary": summary, "participants": [], "location": "",
            "time_state": {}, "causes": [], "effects": [], "locked": False,
            "source_span": None, "confidence": 1.0,
        }],
        "causal_links": [], "character_state_changes": [], "location_changes": [],
        "time_changes": [], "object_changes": [], "knowledge_changes": [],
        "relationship_changes": [], "foreshadowing": [], "open_threads": [],
        "resolved_threads": [], "required_start_state": {}, "required_end_state": {},
        "editable_points": [], "source_references": [],
    }


class ChatOnlyClient:
    """Exercises the real compiler/chat path; intentionally has no generate_json method."""

    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, _model, _api_key, messages: list[dict[str, str]]) -> AIResponse:
        self.calls.append(messages)
        return AIResponse(text=json.dumps(self.response), token_usage={}, elapsed_ms=1)


class WorkflowCompilerCompatibilityTests(unittest.TestCase):
    def test_compile_workflow_json_returns_complete_request(self) -> None:
        request = PromptCompiler().compile_workflow_json(
            stage="legacy_stage",
            payload={"source": "原文", "direction": "保持事实"},
            output_contract="JSON object with result",
        )

        self.assertIsInstance(request, CompiledRequest)
        self.assertEqual("legacy_stage", request.stage)
        self.assertEqual("rusty.native.workflow.v1", request.ruleset_id)
        self.assertEqual("JSON object with result", request.expected_output)
        self.assertEqual(["system", "user"], [item["role"] for item in request.message_list()])
        self.assertIn("WORKFLOW STAGE: legacy_stage", request.message_list()[1]["content"])

    def test_workflow_ai_chat_only_client_uses_legacy_compiler(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            database = Path(directory) / "rusty.db"
            ModelService(database).create_model(
                "Chat only", "openai_compatible", "http://invalid.test", "chat-only",
                is_default=True,
            )
            client = ChatOnlyClient({"result": "ok"})
            result = WorkflowAI(database, ai_client=client).generate_json(
                project_id=0,
                stage="legacy_stage",
                payload={"value": 1},
                output_contract="JSON object with result",
            )

        self.assertEqual({"result": "ok"}, result)
        self.assertEqual(1, len(client.calls))
        self.assertIn("structured novel-workflow component", client.calls[0][0]["content"])
        self.assertIn("OUTPUT CONTRACT", client.calls[0][1]["content"])

    def test_plot_orchestrator_start_uses_chat_only_compiler_path(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd(), ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            database = root / "rusty.db"
            source = root / "book.txt"
            source.write_text("1. 第一章\n人物进入院子。\n\n人物返回客栈。", encoding="utf-8")
            ModelService(database).create_model(
                "Chat only", "openai_compatible", "http://invalid.test", "chat-only",
                is_default=True,
            )
            projects = ProjectService(database)
            project_id = projects.create_project(projects.preview_book(source), root / "workspace")
            chapter = projects.list_chapters(project_id)[0]
            scenes = SceneService(database).split_chapter(
                chapter.id,
                proposed_boundaries=[chapter.original_text.index("人物返回")],
            )
            SceneService(database).save_fact_ledger(scenes[0].id, {"location": "院子"})
            SceneService(database).save_fact_ledger(scenes[1].id, {"location": "客栈"})
            client = ChatOnlyClient({"target_skeleton": _skeleton("保持真实 chat 路径")})
            run = PlotGenerationOrchestrator(database, ai_client=client).start(
                project_id=project_id,
                generation_mode="bounded_insert",
                start_anchor={"anchor_type": "chapter_start", "chapter_id": chapter.id},
                return_anchor={"anchor_type": "chapter_end", "chapter_id": chapter.id},
                user_direction="保持真实 chat 路径",
            )

        self.assertEqual("awaiting_skeleton", run["status"])
        self.assertEqual("保持真实 chat 路径", run["target_skeleton"]["event_nodes"][0]["summary"])
        self.assertEqual(1, len(client.calls))
        self.assertIn("WORKFLOW STAGE: propose_target_skeleton", client.calls[0][1]["content"])


if __name__ == "__main__":
    unittest.main()
