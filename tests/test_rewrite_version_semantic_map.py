from __future__ import annotations

import sys
import tempfile
import unittest
import copy
import sqlite3
from pathlib import Path

from tests.support import initialized_database

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.context_service import ContextService
from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator
from rusty.services.scene_service import SceneService
from rusty.services.shared_analysis_service import SkeletonExtractionService
from rusty.services.rewrite_version_map_service import (
    AnchorUnmapped,
    RewriteVersionMapService,
)
from rusty.db import session


def _skeleton(start: int, end: int) -> dict:
    return {
        "metadata": {"schema_version": 1},
        "event_nodes": [
            {
                "id": "conflict",
                "order": 1,
                "event_type": "conflict",
                "summary": "张三与李四发生争执。",
                "participants": ["张三", "李四"],
                "location": "大厅",
                "time_state": {},
                "causes": [],
                "effects": [],
                "locked": True,
                "source_span": {"start": start, "end": end},
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
        "required_start_state": {"location": "hall"},
        "required_end_state": {"location": "hall"},
        "editable_points": [],
        "source_references": [],
    }


class RewriteVersionSemanticMapRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = initialized_database(self.root / "rusty.db")
        self.original = "张三进入大厅。\n\n张三与李四争吵。\n\n张三离开大厅。"
        source = self.root / "book.txt"
        source.write_text(f"1. 第一章\n{self.original}", encoding="utf-8")
        self.projects = ProjectService(self.database)
        self.project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind="rewrite"
        )
        self.chapter_id = self.projects.list_chapters(self.project_id)[0].id
        self.scenes = SceneService(self.database).split_chapter(
            self.chapter_id,
            proposed_boundaries=[
                self.original.index("张三与李四"),
                self.original.index("张三离开"),
            ],
        )
        self.context = ContextService(self.database)
        self.versions = ChapterVersionService(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def _current_snapshot(self) -> dict:
        return self.versions.resolve_chapter_source(
            self.chapter_id, {"kind": "current"}
        ).to_dict()

    def _prose_rewrite(
        self, *, skeleton: dict, rewritten_text: str, rewritten_span: tuple[int, int]
    ) -> dict:
        observed = copy.deepcopy(skeleton)
        observed["event_nodes"][0]["source_span"] = {
            "start": rewritten_span[0],
            "end": rewritten_span[1],
        }

        class FakeProse:
            def generate_json(self, stage: str, payload: dict) -> dict:
                if stage == "prose_rewrite_plan":
                    return {
                        "target_skeleton": copy.deepcopy(skeleton),
                        "rewrite_plan": {"style": "expanded"},
                    }
                if stage == "prose_rewrite_generate":
                    return {"rewritten_text": rewritten_text}
                if stage == "extract_observed_skeleton":
                    return copy.deepcopy(observed)
                raise AssertionError(stage)

        service = ProseRewriteOrchestrator(self.database, ai_client=FakeProse())
        run = service.plan(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            source_skeleton=skeleton,
            preservation_policy={},
            user_direction="full prose rewrite",
        )
        return service.execute(run["id"])

    def test_a_scene_anchor_survives_full_prose_rewrite_without_text_search(self) -> None:
        rewritten = (
            "张三推门走进宽阔的大厅。\n\n"
            "他很快与李四爆发了激烈争执。\n\n"
            "最终张三转身离去。"
        )
        source_skeleton = _skeleton(
            self.original.index("张三与李四"),
            self.original.index("张三与李四") + len("张三与李四争吵。"),
        )
        rewritten_start = rewritten.index("他很快与李四")
        rewritten_end = rewritten.index("。\n\n最终") + 1
        completed = self._prose_rewrite(
            skeleton=source_skeleton,
            rewritten_text=rewritten,
            rewritten_span=(rewritten_start, rewritten_end),
        )
        self.assertEqual("completed", completed["status"])

        resolved = self.context._resolve_generation_anchor(
            self.project_id,
            {
                "anchor_type": "scene_end",
                "scene_id": self.scenes[1].id,
                "source_version_id": self._current_snapshot()["source_version_id"],
                "side": "after",
            },
            branch_id=None,
            rewrite_source_snapshot=self._current_snapshot(),
        )

        self.assertEqual(rewritten.index("。\n\n最终") + 1, resolved["offset"])
        self.assertEqual("rewrite_version", resolved["source_kind"])

    def test_b_skeleton_anchor_uses_rewrite_local_span(self) -> None:
        extracted = SkeletonExtractionService(self.database).save_extraction(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            scene_id=self.scenes[1].id,
            skeleton=_skeleton(10, 20),
        )
        rewritten = "前文被大幅扩展，长度已经完全不同。" + ("铺垫" * 11) + "激烈冲突在此发生。尾声"
        rewritten_start = rewritten.index("激烈冲突在此发生。")
        expected_end = rewritten_start + len("激烈冲突在此发生。")
        completed = self._prose_rewrite(
            skeleton=_skeleton(10, 20),
            rewritten_text=rewritten,
            rewritten_span=(rewritten_start, expected_end),
        )
        self.assertEqual("completed", completed["status"])
        snapshot = self._current_snapshot()

        resolved = self.context._resolve_generation_anchor(
            self.project_id,
            {
                "anchor_type": "skeleton_node",
                "skeleton_version_id": extracted.version_id,
                "node_id": "conflict",
                "source_version_id": snapshot["source_version_id"],
                "side": "after",
            },
            branch_id=None,
            rewrite_source_snapshot=snapshot,
        )

        self.assertGreater(expected_end, 40)
        self.assertEqual(expected_end, resolved["offset"])

    def test_c_middle_scene_anchor_uses_local_state_not_chapter_end(self) -> None:
        ledgers = [
            {"location": "home"},
            {"location": "school"},
            {"location": "hospital"},
        ]
        scene_service = SceneService(self.database)
        for scene, facts in zip(self.scenes, ledgers, strict=True):
            scene_service.save_fact_ledger(scene.id, facts)
        self.projects.save_chapter_rewrite(self.chapter_id, self.original)
        snapshot = self._current_snapshot()

        resolved = self.context._resolve_generation_anchor(
            self.project_id,
            {
                "anchor_type": "scene_start",
                "scene_id": self.scenes[1].id,
                "source_version_id": snapshot["source_version_id"],
                "side": "before",
            },
            branch_id=None,
            rewrite_source_snapshot=snapshot,
        )

        self.assertEqual("home", resolved["state"]["location"])
        self.assertNotEqual("hospital", resolved["state"]["location"])

    def test_bounded_insert_shifts_later_spans_and_records_generated_state(self) -> None:
        service = SceneService(self.database)
        for scene, location in zip(
            self.scenes, ["home", "school", "hospital"], strict=True
        ):
            service.save_fact_ledger(scene.id, {"location": location})
        self.projects.save_chapter_rewrite(self.chapter_id, self.original)
        base = self.versions.list_versions(self.chapter_id)[0]
        maps = RewriteVersionMapService(self.database)
        base_scene_3 = maps.resolve_scene_span(base["id"], self.scenes[2].id)
        insert_offset = self.original.index("张三与李四") + 2
        addition = "突然发生伏击。"
        rewritten = self.original[:insert_offset] + addition + self.original[insert_offset:]
        with session(self.database) as connection:
            created = self.versions.append_chapter_rewrite_version(
                connection,
                chapter_id=self.chapter_id,
                rewritten_text=rewritten,
                source_operation="plot_generation",
                source_run_id=101,
                source_base_kind="rewrite_version",
                source_base_version_id=base["id"],
                source_hash=base["content_hash"],
                facts_before=base["facts_before"],
                facts_after=base["facts_after"],
                expected_head_version_id=base["id"],
                mapping_strategy="transformed",
                map_changes=[{
                    "start": insert_offset,
                    "end": insert_offset,
                    "replacement_length": len(addition),
                }],
                generated_segment={
                    "node_id": "ambush",
                    "start_offset": insert_offset,
                    "end_offset": insert_offset + len(addition),
                    "state_before": {"location": "home"},
                    "state_after": {"location": "school"},
                },
            )
        shifted_scene_3 = maps.resolve_scene_span(created["id"], self.scenes[2].id)
        generated = next(
            item for item in maps.list_segments(created["id"])
            if item["segment_kind"] == "generated_event"
        )
        self.assertEqual(
            base_scene_3.start_offset + len(addition), shifted_scene_3.start_offset
        )
        self.assertEqual("shifted", shifted_scene_3.mapping_method)
        self.assertEqual({"location": "home"}, generated["state_before"])
        self.assertEqual({"location": "school"}, generated["state_after"])

    def test_replace_overlap_is_explicitly_marked_for_remap(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, self.original)
        base = self.versions.list_versions(self.chapter_id)[0]
        target = self.scenes[1]
        replacement = "冲突被彻底改写。"
        rewritten = (
            self.original[: target.original_start_offset]
            + replacement
            + self.original[target.original_end_offset :]
        )
        with session(self.database) as connection:
            created = self.versions.append_chapter_rewrite_version(
                connection,
                chapter_id=self.chapter_id,
                rewritten_text=rewritten,
                source_operation="plot_generation",
                source_run_id=102,
                source_base_kind="rewrite_version",
                source_base_version_id=base["id"],
                source_hash=base["content_hash"],
                facts_before=base["facts_before"],
                facts_after=base["facts_after"],
                expected_head_version_id=base["id"],
                fact_chain_status="needs_recompute",
                mapping_strategy="transformed",
                map_changes=[{
                    "start": target.original_start_offset,
                    "end": target.original_end_offset,
                    "replacement_length": len(replacement),
                }],
            )
        overlap = next(
            item for item in RewriteVersionMapService(self.database).list_segments(created["id"])
            if item["segment_kind"] == "scene"
            and item["source_scene_id"] == target.id
        )
        self.assertTrue(overlap["needs_remap"])
        self.assertEqual("semantic", overlap["mapping_method"])
        with self.assertRaisesRegex(AnchorUnmapped, "anchor_unmapped"):
            RewriteVersionMapService(self.database).resolve_scene_span(
                created["id"], target.id
            )

    def test_scene_and_node_before_after_states_share_version_map(self) -> None:
        ledgers = [
            {"location": "home"},
            {"location": "school"},
            {"location": "hospital"},
        ]
        service = SceneService(self.database)
        for scene, facts in zip(self.scenes, ledgers, strict=True):
            service.save_fact_ledger(scene.id, facts)
        extracted = SkeletonExtractionService(self.database).save_extraction(
            project_id=self.project_id,
            chapter_id=self.chapter_id,
            scene_id=self.scenes[1].id,
            skeleton=_skeleton(
                self.scenes[1].original_start_offset,
                self.scenes[1].original_end_offset,
            ),
        )
        rewritten = self.original
        completed = self._prose_rewrite(
            skeleton=_skeleton(
                self.scenes[1].original_start_offset,
                self.scenes[1].original_end_offset,
            ),
            rewritten_text=rewritten,
            rewritten_span=(
                self.scenes[1].original_start_offset,
                self.scenes[1].original_end_offset,
            ),
        )
        self.assertEqual("completed", completed["status"])
        snapshot = self._current_snapshot()
        for anchor, expected in (
            ({"anchor_type": "scene_start", "scene_id": self.scenes[1].id, "side": "before"}, "home"),
            ({"anchor_type": "scene_end", "scene_id": self.scenes[1].id, "side": "after"}, "school"),
            ({"anchor_type": "skeleton_node", "skeleton_version_id": extracted.version_id, "node_id": "conflict", "side": "before"}, "home"),
            ({"anchor_type": "skeleton_node", "skeleton_version_id": extracted.version_id, "node_id": "conflict", "side": "after"}, "school"),
        ):
            with self.subTest(anchor=anchor):
                resolved = self.context._resolve_generation_anchor(
                    self.project_id,
                    {**anchor, "source_version_id": snapshot["source_version_id"]},
                    branch_id=None,
                    rewrite_source_snapshot=snapshot,
                )
                self.assertEqual(expected, resolved["state"]["location"])

    def test_text_offset_uses_nearest_local_segment_state(self) -> None:
        service = SceneService(self.database)
        for scene, location in zip(
            self.scenes, ["home", "school", "hospital"], strict=True
        ):
            service.save_fact_ledger(scene.id, {"location": location})
        self.projects.save_chapter_rewrite(self.chapter_id, self.original)
        snapshot = self._current_snapshot()
        offset = self.scenes[1].original_start_offset + 1
        resolved = self.context._resolve_generation_anchor(
            self.project_id,
            {
                "anchor_type": "text_offset",
                "chapter_id": self.chapter_id,
                "text_offset": offset,
                "source_version_id": snapshot["source_version_id"],
                "side": "before",
            },
            branch_id=None,
            rewrite_source_snapshot=snapshot,
        )
        self.assertEqual("home", resolved["state"]["location"])
        self.assertNotEqual("hospital", resolved["state"]["location"])

    def test_rewrite_versions_and_semantic_segments_are_database_immutable(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, self.original)
        version = self.versions.list_versions(self.chapter_id)[0]
        segment = RewriteVersionMapService(self.database).list_segments(version["id"])[0]
        connection = sqlite3.connect(self.database)
        try:
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "UPDATE chapter_rewrite_versions SET rewritten_text = 'tampered' WHERE id = ?",
                    (version["id"],),
                )
            connection.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "DELETE FROM chapter_rewrite_versions WHERE id = ?",
                    (version["id"],),
                )
            connection.rollback()
            with self.assertRaisesRegex(sqlite3.IntegrityError, "immutable"):
                connection.execute(
                    "UPDATE chapter_rewrite_version_segments SET start_offset = 1 WHERE id = ?",
                    (segment["id"],),
                )
        finally:
            connection.close()

    def test_manual_clear_creates_restore_version_without_deleting_head(self) -> None:
        self.projects.save_chapter_rewrite(self.chapter_id, "人工版本")
        first = self.versions.list_versions(self.chapter_id)[0]
        self.projects.save_chapter_rewrite(self.chapter_id, "")
        versions = self.versions.list_versions(self.chapter_id)
        restored = versions[0]
        self.assertEqual(2, len(versions))
        self.assertEqual("restore", restored["source_operation"])
        self.assertEqual(self.original, restored["rewritten_text"])
        self.assertTrue(restored["is_current"])
        self.assertEqual("人工版本", first["rewritten_text"])


if __name__ == "__main__":
    unittest.main()
