from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from support import initialized_database
from rusty.db import session
from rusty.db.schema import AUTHOR_STYLE_DIMENSIONS
from rusty.models import ParsedBook, ParsedChapter
from rusty.services.ai_client import AIResponse
from rusty.services.author_style_extraction_service import AuthorStyleExtractionService
from rusty.services.creative_workflow_service import CreativeWorkflowService, WorkflowSourceConflict
from rusty.services.material_service import MaterialService
from rusty.services.project_service import ProjectService


class QueueExecutor:
    def __init__(self, responses: list[str]) -> None:
        self.responses = iter(responses)
        self.calls: list[list[dict[str, str]]] = []

    def execute(self, messages, **kwargs):
        self.calls.append(messages)
        return AIResponse(next(self.responses), {}, 1)


def style_json() -> str:
    return json.dumps({
        "overall_style": "克制",
        "dimensions": [
            {"id": item["id"], "analysis": item["id"], "features": [], "examples": []}
            for item in AUTHOR_STYLE_DIMENSIONS
        ],
    }, ensure_ascii=False)


def create_project(database: Path, directory: Path) -> int:
    source = directory / "source.txt"
    source.write_text("第一章\n原始正文。", encoding="utf-8")
    book = ParsedBook(
        title="测试小说",
        author="作者",
        language="zh-CN",
        source_path=source,
        source_format="txt",
        source_encoding="utf-8",
        chapters=[ParsedChapter(index=1, title="第一章", text="原始正文。")],
    )
    return ProjectService(database).create_project(book, directory / "workspace")


def first_chapter(database: Path, project_id: int) -> int:
    with session(database) as connection:
        return int(connection.execute(
            "SELECT id FROM chapters WHERE project_id=? ORDER BY chapter_index", (project_id,)
        ).fetchone()[0])


class CreativeWorkflowCanonicalTests(unittest.TestCase):
    def test_three_strategies_source_modes_conflict_and_human_review(self) -> None:
        cases = {
            "plot_adjust": ["【旧大纲】\n旧\n【新大纲及细节】\n新", style_json(), "调整后的正文"],
            "expansion": ["新增章节大纲", style_json(), "新增章节正文"],
            "plot_rewrite": ["重写大纲", "重写后的正文"],
        }
        for strategy, responses in cases.items():
            with self.subTest(strategy=strategy), tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
                root = Path(directory)
                database = initialized_database(root / "rusty.db")
                project_id = create_project(database, root)
                chapter_id = first_chapter(database, project_id)
                executor = QueueExecutor(responses)
                workflow = CreativeWorkflowService(database, executor=executor)
                self.assertIsInstance(workflow.author_styles, AuthorStyleExtractionService)
                workflow.save_chapter_summary(chapter_id, {
                    "plot_summary": "总结", "key_events": "事件", "main_characters": "人物",
                })
                workflow.save_chapter_direction(chapter_id, strategy=strategy, user_instruction="按要求修改")
                analysis = workflow.run_special_analysis(chapter_id)
                self.assertEqual(strategy, analysis["strategy"])

                if strategy == "plot_rewrite":
                    material_id = MaterialService(database).create_material(
                        name="保存作者", raw_text="样本", content={"work": "作品", "overall_style": "风格", "dimensions": []},
                    )
                    style = workflow.resolve_style(chapter_id, author_style_material_id=material_id)
                    self.assertEqual("selected_author_style", style["style_mode"])
                else:
                    style = workflow.resolve_style(chapter_id)
                    self.assertEqual("source_auto", style["style_mode"])
                    self.assertEqual(12, len(style["extraction_settings_snapshot"]["dimensions"]))

                writing = workflow.generate_chapter(chapter_id)
                self.assertNotIn("writing_plan", writing)
                model_calls_before_review = len(executor.calls)
                workflow.save_writing(chapter_id, writing["result_text"] + " 人工修改")
                confirmed = workflow.confirm_chapter(chapter_id)
                self.assertEqual("confirmed", confirmed["current_stage"])
                self.assertEqual(model_calls_before_review, len(executor.calls))

    def test_changed_source_blocks_stale_workflow(self) -> None:
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as directory:
            root = Path(directory)
            database = initialized_database(root / "rusty.db")
            project_id = create_project(database, root)
            chapter_id = first_chapter(database, project_id)
            workflow = CreativeWorkflowService(database, executor=QueueExecutor([]))
            workflow.save_chapter_summary(chapter_id, {
                "plot_summary": "总结", "key_events": "事件", "main_characters": "人物",
            })
            with session(database) as connection:
                connection.execute("UPDATE chapters SET original_text='外部修改后的正文' WHERE id=?", (chapter_id,))
            with self.assertRaises(WorkflowSourceConflict):
                workflow.save_chapter_direction(chapter_id, strategy="plot_adjust", user_instruction="继续")


if __name__ == "__main__":
    unittest.main()
