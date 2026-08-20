from __future__ import annotations

import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.context_service import ContextService
from rusty.services.material_service import MaterialService
from rusty.services.model_service import ModelService
from rusty.models import ParsedBook, ParsedChapter
from rusty.services.project_service import ProjectService
from rusty.services.scene_service import SceneService
from rusty.services.scene_rewrite_orchestrator import SceneRewriteOrchestrator
from rusty.services.rewrite_workflow_service import CONSISTENCY_KEYS, SCENE_ANALYSIS_KEYS, RewriteWorkflowService
from rusty.services.document_library_service import DocumentLibraryService
from rusty.services.document_split_ai_service import DocumentSplitAIService
from backend.schemas import MaterialUpdateRequest
from pydantic import ValidationError
from rusty.services.resource_analysis_service import ResourceAnalysisService
from rusty.services.structured_model_service import StructuredModelService


class QueueAI(AIClient):
    def __init__(self, *responses: object) -> None:
        self.responses = list(responses)
        self.messages: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.messages.append(messages)
        value = self.responses.pop(0)
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return AIResponse(text=text, token_usage={"total_tokens": 17}, elapsed_ms=9)


class PhaseTwoRemediationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = initialized_database(self.root / "rusty.db")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_material_types_and_legacy_outline_json_import(self) -> None:
        service = MaterialService(self.database)
        with self.assertRaises(ValueError):
            service.create_material(material_type="outline", scope="public", name="bad", content={})
        with self.assertRaises(ValidationError):
            MaterialUpdateRequest.model_validate({
                "name": "试图改类型", "content": {}, "material_type": "plot_skeleton",
            })
        result = service.import_json_items(
            [
                {"material_type": "outline", "name": "旧大纲", "raw_text": "原始内容"},
                {"material_type": "author_style", "name": "动作风格"},
                {"material_type": "unknown", "name": "非法项"},
            ],
            default_scope="public",
        )
        self.assertEqual(1, len(result["imported"]))
        self.assertEqual(2, len(result["errors"]))
        imported = service.get_material(result["imported"][0]["id"])
        self.assertEqual("author_style", imported.material_type)

    def test_real_material_analysis_repairs_schema_and_keeps_audit(self) -> None:
        ModelService(self.database).create_model(
            display_name="fake", provider="openai_compatible", base_url="https://example.test/v1",
            model_name="fake", is_default=True,
        )
        material_id = MaterialService(self.database).create_material(
            material_type="author_style", scope="public", name="雨夜文风", raw_text="雨打在石阶上。", content={"summary": "", "dimensions": []},
        )
        valid = {"summary": "雨夜动作写法", "dimensions": [{"id": "sentence", "name": "句子特征", "requirement": "分析句式", "analysis": "短句", "features": ["节奏快"], "examples": ["雨打在石阶上。"]}]}
        fake = QueueAI("not json", valid)
        structured = StructuredModelService(self.database, ai_client=fake)
        updated, result = ResourceAnalysisService(self.database, structured_model_service=structured).analyze_material(material_id)
        self.assertTrue(result.repaired)
        self.assertEqual("雨夜动作写法", json.loads(updated.content_json)["summary"])
        with session(self.database) as connection:
            audit = connection.execute("SELECT status, response_text, token_usage_json FROM model_invocations WHERE id = ?", (result.invocation_id,)).fetchone()
        self.assertEqual("completed", audit["status"])
        self.assertIn("total_tokens", audit["token_usage_json"])

    def test_empty_user_instruction_is_compiled_as_required_nonempty_block(self) -> None:
        source = self.root / "source.txt"
        source.write_text("第一幕。\n\n第二幕。", encoding="utf-8")
        project_id = ProjectService(self.database).create_project(
            ParsedBook(
                title="测试", author="", language="zh", source_path=source, source_format="txt",
                source_encoding="utf-8", chapters=[ParsedChapter(index=1, title="第一章", text="第一幕。\n\n第二幕。")],
            ),
            self.root / "workspace",
        )
        chapter = ProjectService(self.database).list_chapters(project_id)[0]
        scene = SceneService(self.database).split_chapter(chapter.id)[0]
        service = ContextService(self.database)
        result = service.compile_scene_context(
            scene.id,
            stage="rewrite",
            system_rules="保留事实",
            user_instruction="",
            task={"must_preserve_events": [], "required_end_state": {}},
            model_context_tokens=4096,
            reserved_output_tokens=512,
        )
        block = next(item for item in result["blocks"] if item["key"] == "user_instruction")
        self.assertTrue(block["required"])
        self.assertTrue(block["content"].strip())
        self.assertEqual("included", block["decision"])

    def test_tag_rename_delete_only_changes_associations(self) -> None:
        service = MaterialService(self.database)
        tag_id = service.create_tag(" 气氛 ").id
        material_id = service.create_material(
            material_type="author_style", scope="public", name="灯影", content={}, tag_ids=[tag_id],
        )
        service.rename_tag(tag_id, "夜景")
        self.assertIn("夜景", service.get_material(material_id).tags)
        service.delete_tag(tag_id)
        self.assertIsNotNone(service.get_material(material_id))
        self.assertEqual((), service.get_material(material_id).tags)

    def test_scene_orchestrator_enforces_confirmation_gates_and_executes_models(self) -> None:
        source = self.root / "novel.txt"
        source.write_text("林舟推门而入。\n\n他看见桌上的钥匙。", encoding="utf-8")
        project_service = ProjectService(self.database)
        project_id = project_service.create_project(
            ParsedBook(
                title="长篇", author="", language="zh", source_path=source, source_format="txt",
                source_encoding="utf-8", chapters=[ParsedChapter(index=1, title="第一章", text=source.read_text(encoding="utf-8"))],
            ),
            self.root / "workspace",
        )
        chapter = project_service.list_chapters(project_id)[0]
        scene_service = SceneService(self.database)
        scene = scene_service.split_chapter(chapter.id)[0]
        scene_service.confirm_boundaries(chapter.id)
        ModelService(self.database).create_model(
            display_name="fake", provider="openai_compatible", base_url="https://example.test/v1",
            model_name="fake", is_default=True,
        )
        analysis = {key: [] for key in SCENE_ANALYSIS_KEYS}
        analysis["required_start_state"] = {}
        analysis["required_end_state"] = {}
        responses = QueueAI(
            analysis,
            {"event_nodes": [{"id": "n1", "event": "林舟进入房间", "required": True}]},
            {
                "sequence": ["进入", "发现钥匙"], "preserve": ["发现钥匙"], "modify": [],
                "add": [], "material_insertions": [], "character_changes": {}, "expected_end_state": {},
            },
            {"text": "林舟推门而入，目光落在桌上的钥匙上。", "facts_after": {"events": ["发现钥匙"]}},
            {**{key: [] for key in CONSISTENCY_KEYS}, "revision_required": False},
        )
        orchestrator = SceneRewriteOrchestrator(
            self.database,
            structured_model_service=StructuredModelService(self.database, ai_client=responses),
        )
        run = orchestrator.start(scene.id, mode="skeleton_rewrite")
        with self.assertRaises(ValueError):
            orchestrator.generate_plan(run["id"], skeleton_version_id=run["skeleton_version_id"])
        confirmed = RewriteWorkflowService(self.database).confirm_skeleton(run["skeleton_id"])
        planned = orchestrator.generate_plan(run["id"], skeleton_version_id=confirmed.version_id)
        with self.assertRaises(ValueError):
            orchestrator.execute(run["id"])
        RewriteWorkflowService(self.database).confirm_plan(planned["plan_id"])
        completed = orchestrator.execute(run["id"])
        self.assertEqual("completed", completed["status"])
        self.assertEqual(5, len(responses.messages))
        history = orchestrator.list_scene_history(scene.id)
        self.assertIn("林舟推门而入", history[-1]["rewritten_text"])

    def test_ai_document_split_preview_is_non_mutating_and_apply_creates_revision(self) -> None:
        text = "第一章\n林舟进门。\n第二章\n他找到钥匙。"
        source = self.root / "document.txt"
        source.write_text(text, encoding="utf-8")
        ModelService(self.database).create_model(
            display_name="fake", provider="openai_compatible", base_url="https://example.test/v1",
            model_name="fake", is_default=True,
        )
        with patch.dict("os.environ", {"RUSTY_DOCUMENT_LIBRARY_PATH": str(self.root / "library")}):
            document_service = DocumentLibraryService(self.database)
            document = document_service.import_document(source).document
            current_chapter = document_service.list_chapters(document.id)[0]
            content = document_service.get_content(document.id, current_chapter.id)
            split = max(1, len(content.body_text) // 2)
            fake = QueueAI({"chapters": [
                {"title": "前半章", "start_offset": 0, "end_offset": split},
                {"title": "后半章", "start_offset": split, "end_offset": len(content.body_text)},
            ]})
            before = document_service.list_revisions(document.id)
            service = DocumentSplitAIService(
                self.database,
                structured_model_service=StructuredModelService(self.database, ai_client=fake),
            )
            proposal = service.preview(document.id, chapter_id=current_chapter.id, prompt="按事件转折分章")
            self.assertEqual(len(before), len(document_service.list_revisions(document.id)))
            applied = service.apply(proposal["proposal_id"])
            self.assertEqual(len(before) + 1, len(document_service.list_revisions(document.id)))
            self.assertEqual(3, len(applied["chapters"]))
            self.assertEqual(["前半章", "后半章"], [item["title"] for item in applied["chapters"][:2]])


if __name__ == "__main__":
    unittest.main()
