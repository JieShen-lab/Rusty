from __future__ import annotations

import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import (
    BRANCH_CONTEXT_KEYS,
    PlotGenerationOrchestrator,
)
from rusty.services.project_service import ProjectService


def target_skeleton(summary: str) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [
            {
                "id": "new_event",
                "order": 1,
                "event_type": "conflict",
                "summary": summary,
                "participants": ["人物"],
                "location": "院子",
                "time_state": {},
                "causes": [],
                "effects": [],
                "locked": False,
                "source_span": None,
                "confidence": 1.0,
            }
        ],
        "causal_links": [],
        "character_state_changes": [],
        "location_changes": [],
        "time_changes": [],
        "object_changes": [],
        "knowledge_changes": [],
        "relationship_changes": [],
        "foreshadowing": [],
        "open_threads": [],
        "resolved_threads": [],
        "required_start_state": {"location": "院子"},
        "required_end_state": {"location": "客栈"},
        "editable_points": [],
        "source_references": [],
    }


def branch_context(**overrides):
    context = {key: {} for key in BRANCH_CONTEXT_KEYS}
    context.update(
        {
            "previous_text_tail": "人物进入院子。",
            "start_state": {"location": "院子", "alive": True},
            "fact_ledger": {"route": "baseline"},
            "user_direction": "继续冒险",
        }
    )
    context.update(overrides)
    return context


class PlotGenerationOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.source = self.root / "book.txt"
        self.original = "人物进入院子。\n人物随后返回客栈。"
        self.source.write_text(f"1. 第一章\n{self.original}", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.orchestrator = PlotGenerationOrchestrator(self.database)
        self.source_hash = BranchService.source_hash(self.original)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def create_project(self, kind: str) -> tuple[int, int]:
        project_id = self.projects.create_project(
            self.projects.preview_book(self.source),
            self.root,
            project_name=kind,
            project_kind=kind,
        )
        return project_id, self.projects.list_chapters(project_id)[0].id

    def seams(self):
        return [
            {
                "seam_kind": "entry",
                "status": "confirmed",
                "source_hash": self.source_hash,
            },
            {
                "seam_kind": "return",
                "status": "confirmed",
                "source_hash": self.source_hash,
            },
        ]

    def test_a_bounded_insert_battle_preserves_unrelated_original(self) -> None:
        project_id, chapter_id = self.create_project("rewrite")
        offset = self.original.index("\n")
        anchor = {
            "anchor_type": "text_offset",
            "chapter_id": chapter_id,
            "text_offset": offset,
            "source_hash": self.source_hash,
        }
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="bounded_insert",
            start_anchor=anchor,
            return_anchor=copy.deepcopy(anchor),
            target_skeleton=target_skeleton("人物遭遇一场伏击战。"),
            context={
                "rewrite_source_context": self.original,
                "start_state": {"location": "院子"},
            },
            required_return_state={"location": "客栈"},
        )
        self.assertIn("伏击战", run["target_skeleton"]["event_nodes"][0]["summary"])
        self.orchestrator.confirm_seams(
            run["id"], self.seams(), current_source_text=self.original
        )
        completed = self.orchestrator.execute(
            run["id"],
            generated_scenes=[{"title": "伏击", "text": "\n伏兵从墙后杀出。\n"}],
            final_state={"location": "客栈"},
        )
        rewritten = completed["result"]["rewritten_text"]
        self.assertIn("伏兵", rewritten)
        self.assertIn("人物进入院子。", rewritten)
        self.assertIn("人物随后返回客栈。", rewritten)
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)
        self.assertEqual("in_place", completed["output_topology"])

    def test_b_open_continuation_needs_no_current_original_scene(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="open_continuation",
            start_anchor={
                "anchor_type": "document_end",
                "chapter_id": chapter_id,
                "source_hash": self.source_hash,
            },
            target_skeleton=target_skeleton("人物离开客栈继续旅行。"),
            context=branch_context(fact_ledger={"location": "客栈", "alive": True}),
        )
        self.assertNotIn("current_original_scene", run["context"])
        self.orchestrator.confirm_seams(
            run["id"], self.seams()[:1], current_source_text=self.original
        )
        completed = self.orchestrator.execute(
            run["id"],
            generated_scenes=[{"title": "续程", "text": "人物踏上新路。"}],
            final_state={"location": "城外"},
        )
        self.assertEqual("branch", completed["output_topology"])
        self.assertEqual(
            "客栈", completed["context"]["fact_ledger"]["location"]
        )
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)

    def test_c_mid_story_fork_has_independent_future_facts(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork",
            start_anchor={
                "anchor_type": "chapter_start",
                "chapter_id": chapter_id,
                "source_hash": self.source_hash,
            },
            target_skeleton=target_skeleton("人物选择另一条路线。"),
            context=branch_context(
                fact_ledger={"shared_before": True},
                open_threads=["new route"],
            ),
        )
        self.orchestrator.confirm_seams(
            run["id"], self.seams()[:1], current_source_text=self.original
        )
        completed = self.orchestrator.execute(
            run["id"],
            generated_scenes=[
                {
                    "title": "岔路",
                    "text": "人物没有返回客栈。",
                    "facts_after": {"shared_before": True, "route": "fork"},
                }
            ],
            final_state={"route": "fork"},
        )
        scene = BranchService(self.database).list_scenes(completed["branch_id"])[0]
        self.assertEqual("fork", scene["facts_after"]["route"])
        self.assertNotIn("returned_to_inn", scene["facts_after"])
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)

    def test_d_rejoin_blocks_until_required_return_state_is_met(self) -> None:
        project_id, chapter_id = self.create_project("branch")
        run = self.orchestrator.start(
            project_id=project_id,
            generation_mode="fork_and_rejoin",
            start_anchor={
                "anchor_type": "chapter_start",
                "chapter_id": chapter_id,
                "source_hash": self.source_hash,
            },
            return_anchor={
                "anchor_type": "chapter_end",
                "chapter_id": chapter_id,
                "source_hash": self.source_hash,
            },
            target_skeleton=target_skeleton("人物绕路后返回。"),
            context=branch_context(return_state_constraints={"location": "客栈", "alive": True}),
            required_return_state={"location": "客栈", "alive": True},
        )
        self.orchestrator.confirm_seams(
            run["id"], self.seams(), current_source_text=self.original
        )
        blocked = self.orchestrator.execute(
            run["id"],
            generated_scenes=[{"title": "绕路", "text": "人物仍在院子。"}],
            final_state={"location": "院子", "alive": True},
        )
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("return_state_mismatch", blocked["issues"][0]["type"])

        completed = self.orchestrator.execute(
            run["id"],
            generated_scenes=[{"title": "归返", "text": "人物回到客栈。"}],
            final_state={"location": "客栈", "alive": True},
        )
        self.assertEqual("completed", completed["status"])
        self.assertEqual(self.original, self.projects.get_chapter(chapter_id).original_text)


if __name__ == "__main__":
    unittest.main()
