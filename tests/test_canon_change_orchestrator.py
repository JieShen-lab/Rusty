from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.services.branch_service import BranchService
from rusty.services.canon_change_orchestrator import CanonChangeOrchestrator
from rusty.services.project_service import ProjectService


class CanonChangeOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.projects = ProjectService(self.database)
        self.service = CanonChangeOrchestrator(self.database)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def project(self, text: str, kind: str = "rewrite"):
        source = self.root / f"{kind}-{len(list(self.root.glob('*.txt')))}.txt"
        source.write_text(text, encoding="utf-8")
        project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind=kind
        )
        return project_id, self.projects.list_chapters(project_id)

    def test_arm_injury_to_leg_injury_scans_semantic_consequences_and_applies_selection(self) -> None:
        text = (
            "1. One\n"
            "他左臂受伤，无法抬剑，袖口渗血。\n"
            "同伴扶住手肘，医师剪开衣袖。\n"
            "数日后他重新持剑。\n"
            "另一人的手臂十分强壮。"
        )
        project_id, chapters = self.project(text)
        chapter = chapters[0]
        run = self.service.scan(
            project_id=project_id,
            old_fact={"subject": "他", "attribute": "injury", "value": "左臂受伤"},
            new_fact={"subject": "他", "attribute": "injury", "value": "腿部受伤"},
            effective_order=1,
        )
        impact_types = {patch["impact_type"] for patch in run["patches"]}
        self.assertEqual(
            {
                "direct_fact",
                "action_consequence",
                "physical_symptom",
                "other_character_reaction",
                "treatment",
                "recovery_progress",
            },
            impact_types,
        )
        self.assertFalse(any(patch["original_text"] == "手臂" for patch in run["patches"]))

        rejected_id = next(
            patch["id"]
            for patch in run["patches"]
            if patch["impact_type"] == "recovery_progress"
        )
        for patch in run["patches"]:
            self.service.review_patch(
                patch["id"],
                decision="rejected" if patch["id"] == rejected_id else "accepted",
            )
        applied = self.service.apply(run["id"])
        rewritten = self.projects.get_chapter(chapter.id).rewritten_text
        self.assertEqual("applied", applied["status"])
        self.assertIn("腿部受伤", rewritten)
        self.assertIn("难以站稳", rewritten)
        self.assertIn("裤腿渗血", rewritten)
        self.assertIn("剪开裤腿", rewritten)
        self.assertIn("重新持剑", rewritten)
        self.assertIn("手臂十分强壮", rewritten)
        self.assertEqual(text.split("\n", 1)[1], self.projects.get_chapter(chapter.id).original_text)
        self.assertEqual("腿部受伤", applied["fact_ledger"]["injury"]["value"])
        self.assertEqual([], applied["consistency_issues"])

    def test_source_hash_mismatch_blocks_patch(self) -> None:
        project_id, chapters = self.project("1. One\n他左臂受伤。")
        run = self.service.scan(
            project_id=project_id,
            old_fact={"attribute": "injury", "value": "左臂受伤"},
            new_fact={"attribute": "injury", "value": "腿部受伤"},
            effective_order=1,
        )
        self.service.review_patch(run["patches"][0]["id"], decision="accepted")
        self.projects.save_chapter_rewrite(chapters[0].id, "文本已被用户修改。")
        blocked = self.service.apply(run["id"])
        self.assertEqual("blocked", blocked["status"])
        self.assertEqual("source_hash_mismatch", blocked["consistency_issues"][0]["type"])

    def test_relationship_possession_knowledge_and_effective_point(self) -> None:
        project_id, chapters = self.project(
            "1. Before\n甲信任乙，钥匙属于甲，甲知道密道。\n"
            "2. After\n甲信任乙，钥匙属于甲，甲知道密道。"
        )
        cases = [
            ("relationship", "甲信任乙", "甲不再信任乙", "relationship_effect"),
            ("possession", "钥匙属于甲", "钥匙属于乙", "possession_or_equipment"),
            ("knowledge", "甲知道密道", "甲不知道密道", "knowledge_state"),
        ]
        for attribute, old, new, impact in cases:
            run = self.service.scan(
                project_id=project_id,
                old_fact={"attribute": attribute, "value": old},
                new_fact={"attribute": attribute, "value": new},
                effective_order=2,
            )
            self.assertEqual({chapters[1].id}, {patch["target_id"] for patch in run["patches"]})
            self.assertEqual({impact}, {patch["impact_type"] for patch in run["patches"]})

    def test_branch_change_only_scans_target_route(self) -> None:
        project_id, chapters = self.project("1. One\nBaseline.", kind="branch")
        branch_service = BranchService(self.database)
        source_hash = branch_service.source_hash(chapters[0].original_text)
        branch_ids = []
        for name in ("A", "B"):
            branch = branch_service.create_branch(
                project_id=project_id,
                name=name,
                branch_mode="fork",
                start_anchor={"anchor_type": "document_end", "source_hash": source_hash},
            )
            branch_service.save_scene(
                branch["id"], title=name, generated_text="甲信任乙。"
            )
            branch_ids.append(branch["id"])
        run = self.service.scan(
            project_id=project_id,
            branch_id=branch_ids[0],
            old_fact={"attribute": "relationship", "value": "甲信任乙"},
            new_fact={"attribute": "relationship", "value": "甲不再信任乙"},
            effective_order=1,
        )
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        self.service.apply(run["id"])
        self.assertIn("不再信任", branch_service.list_scenes(branch_ids[0])[0]["generated_text"])
        self.assertEqual("甲信任乙。", branch_service.list_scenes(branch_ids[1])[0]["generated_text"])


if __name__ == "__main__":
    unittest.main()
