from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from rusty.db import session
from rusty.services.branch_service import BranchService
from rusty.services.canon_change_orchestrator import CanonChangeOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.chapter_version_service import ChapterVersionService


class FakeCanonLLM:
    """Deterministic semantic fixture; production scanning contains no phrase rules."""

    REWRITES = {
        "左臂受伤": ("腿部受伤", "direct_fact"),
        "剑怎么也举不起来": ("腿上使不上力，无法站稳", "action_consequence"),
        "袖口渐渐洇红": ("裤腿渐渐洇红", "physical_symptom"),
        "扶住他的手肘": ("架住他的肩膀", "other_character_reaction"),
        "剪开染血的衣袖": ("剪开染血的裤腿", "treatment"),
        "终于又能双手持剑": ("终于又能稳稳站立", "recovery_progress"),
        "他仍信任乙": ("他不再信任乙", "relationship_effect"),
        "钥匙还在甲腰间": ("钥匙已经交给乙", "possession_or_equipment"),
        "他当然知道暗门在哪": ("他并不知道暗门在哪", "knowledge_state"),
    }

    def generate_json(self, stage, payload):
        if stage == "canon_consistency_check":
            old_value = str(payload["old_fact"].get("value", ""))
            issues = [
                {"type": "old_fact_remains"}
                for target in payload["projected_targets"]
                if old_value and old_value in target["text"]
            ]
            return {"issues": issues}
        if stage != "canon_semantic_impact":
            raise AssertionError(stage)
        text = payload["candidate"]["text"]
        attribute = payload["old_fact"].get("attribute")
        impacts = []
        for original, (replacement, impact_type) in self.REWRITES.items():
            if attribute != "injury" and impact_type not in {
                f"{attribute}_effect",
                f"{attribute}_state",
                "possession_or_equipment" if attribute == "possession" else "",
            }:
                continue
            start = text.find(original)
            if start < 0:
                continue
            impacts.append(
                {
                    "source_range": {"start": start, "end": start + len(original)},
                    "original_text": original,
                    "replacement_text": replacement,
                    "impact_type": impact_type,
                    "reason": "semantic consequence",
                    "confidence": 0.98,
                    "evidence": [original],
                    "requires_confirmation": True,
                }
            )
        return {"impacts": impacts}


class OverlapLLM(FakeCanonLLM):
    def generate_json(self, stage, payload):
        if stage != "canon_semantic_impact":
            return super().generate_json(stage, payload)
        text = payload["candidate"]["text"]
        if "左臂受伤" not in text:
            return {"impacts": []}
        start = text.index("左臂受伤")
        common = {
            "replacement_text": "腿伤",
            "impact_type": "direct_fact",
            "reason": "overlap fixture",
            "confidence": 1.0,
            "evidence": ["fixture"],
            "requires_confirmation": True,
        }
        return {
            "impacts": [
                {
                    **common,
                    "source_range": {"start": start, "end": start + 4},
                    "original_text": text[start : start + 4],
                },
                {
                    **common,
                    "source_range": {"start": start + 2, "end": start + 4},
                    "original_text": text[start + 2 : start + 4],
                },
            ]
        }


class CanonChangeOrchestratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory(dir=Path.cwd())
        self.root = Path(self.temp.name)
        self.database = self.root / "rusty.db"
        self.projects = ProjectService(self.database)
        self.service = CanonChangeOrchestrator(
            self.database, ai_client=FakeCanonLLM()
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def project(self, chapters: list[tuple[str, str]], kind: str = "rewrite"):
        source = self.root / f"{kind}-{len(list(self.root.glob('*.txt')))}.txt"
        source.write_text(
            "\n".join(f"{index}. {title}\n{text}" for index, (title, text) in enumerate(chapters, 1)),
            encoding="utf-8",
        )
        project_id = self.projects.create_project(
            self.projects.preview_book(source), self.root, project_kind=kind
        )
        return project_id, self.projects.list_chapters(project_id)

    @staticmethod
    def facts(value: str):
        return {"subject": "他", "attribute": "injury", "value": value}

    def scan_injury(self, project_id: int, **kwargs):
        return self.service.scan(
            project_id=project_id,
            old_fact=self.facts("左臂受伤"),
            new_fact=self.facts("腿部受伤"),
            effective_order=1,
            **kwargs,
        )

    def test_semantic_synonyms_pronouns_and_unrelated_same_word(self) -> None:
        project_id, _ = self.project(
            [(
                "One",
                "他左臂受伤。剑怎么也举不起来。袖口渐渐洇红。"
                "同伴扶住他的手肘，医师剪开染血的衣袖。"
                "后来终于又能双手持剑。另一个人的手臂很强壮。",
            )]
        )
        run = self.scan_injury(project_id)
        self.assertEqual(
            {
                "direct_fact",
                "action_consequence",
                "physical_symptom",
                "other_character_reaction",
                "treatment",
                "recovery_progress",
            },
            {patch["impact_type"] for patch in run["patches"]},
        )
        self.assertTrue(all(patch["confidence"] > 0.9 for patch in run["patches"]))
        self.assertFalse(any(patch["original_text"] == "手臂" for patch in run["patches"]))

    def test_multi_chapter_apply_is_atomic_and_rescan_is_clean(self) -> None:
        project_id, chapters = self.project(
            [("One", "他左臂受伤。"), ("Two", "剑怎么也举不起来。")]
        )
        run = self.scan_injury(project_id)
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        applied = self.service.apply(run["id"])
        self.assertEqual("applied", applied["status"])
        self.assertIn("腿部受伤", self.projects.get_chapter(chapters[0].id).rewritten_text)
        self.assertIn("无法站稳", self.projects.get_chapter(chapters[1].id).rewritten_text)
        self.assertEqual([], self.scan_injury(project_id)["patches"])

    def test_hash_conflict_rolls_back_every_target(self) -> None:
        project_id, chapters = self.project(
            [("One", "他左臂受伤。"), ("Two", "剑怎么也举不起来。")]
        )
        run = self.scan_injury(project_id)
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        original_first = self.projects.get_chapter(chapters[0].id).original_text
        self.projects.save_chapter_rewrite(chapters[1].id, "用户已经修改第二章。")
        blocked = self.service.apply(run["id"])
        self.assertEqual("blocked", blocked["status"])
        self.assertIsNone(self.projects.get_chapter(chapters[0].id).rewritten_text)
        self.assertEqual(original_first, self.projects.get_chapter(chapters[0].id).original_text)

    def test_overlapping_patches_are_rejected_without_write(self) -> None:
        project_id, chapters = self.project([("One", "他左臂受伤。")])
        service = CanonChangeOrchestrator(self.database, ai_client=OverlapLLM())
        run = service.scan(
            project_id=project_id,
            old_fact=self.facts("左臂受伤"),
            new_fact=self.facts("腿部受伤"),
            effective_order=1,
        )
        for patch in run["patches"]:
            service.review_patch(patch["id"], decision="accepted")
        blocked = service.apply(run["id"])
        self.assertEqual("overlapping_patches", blocked["consistency_issues"][0]["type"])
        self.assertIsNone(self.projects.get_chapter(chapters[0].id).rewritten_text)

    def test_branch_version_preserves_existing_fact_ledger(self) -> None:
        project_id, chapters = self.project([("One", "Baseline.")], kind="branch")
        branches = BranchService(self.database)
        branch = branches.create_branch(
            project_id=project_id,
            name="A",
            branch_mode="fork",
            start_anchor={
                "anchor_type": "document_end",
                "source_hash": branches.source_hash(chapters[0].original_text),
            },
        )
        scene = branches.save_scene(
            branch["id"],
            title="Generated",
            generated_text="他左臂受伤。",
            facts_after={"weather": "rain"},
        )
        run = self.scan_injury(project_id, branch_id=branch["id"])
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        self.assertEqual("applied", self.service.apply(run["id"])["status"])
        current = branches.list_scenes(branch["id"])[0]
        self.assertEqual(2, current["current_version"])
        self.assertEqual("rain", current["facts_after"]["weather"])
        self.assertEqual("腿部受伤", current["facts_after"]["injury"]["value"])
        self.assertIn("腿部受伤", current["generated_text"])

    def test_relationship_possession_knowledge_and_effective_point(self) -> None:
        project_id, chapters = self.project(
            [
                ("Before", "他仍信任乙。钥匙还在甲腰间。他当然知道暗门在哪。"),
                ("After", "他仍信任乙。钥匙还在甲腰间。他当然知道暗门在哪。"),
            ]
        )
        cases = [
            ("relationship", "他仍信任乙", "他不再信任乙", "relationship_effect"),
            ("possession", "钥匙还在甲腰间", "钥匙已经交给乙", "possession_or_equipment"),
            ("knowledge", "他当然知道暗门在哪", "他并不知道暗门在哪", "knowledge_state"),
        ]
        for attribute, old, new, impact_type in cases:
            run = self.service.scan(
                project_id=project_id,
                old_fact={"attribute": attribute, "value": old},
                new_fact={"attribute": attribute, "value": new},
                effective_order=2,
            )
            self.assertEqual({chapters[1].id}, {p["target_id"] for p in run["patches"]})
            self.assertEqual({impact_type}, {p["impact_type"] for p in run["patches"]})

    def test_canon_appends_to_current_rewrite_version_without_mutating_parent(self) -> None:
        old_text = next(iter(FakeCanonLLM.REWRITES))
        replacement = FakeCanonLLM.REWRITES[old_text][0]
        project_id, chapters = self.project([("One", old_text)])
        chapter_id = chapters[0].id
        self.projects.save_chapter_rewrite(chapter_id, f"Prose v1: {old_text}")
        versions = ChapterVersionService(self.database)
        v1 = versions.list_versions(chapter_id)[0]
        run = self.scan_injury(project_id)
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        applied = self.service.apply(run["id"])
        v2 = versions.list_versions(chapter_id)[0]
        self.assertEqual("applied", applied["status"])
        self.assertEqual(v1["id"], v2["parent_version_id"])
        self.assertEqual("canon_change", v2["source_operation"])
        self.assertIn(old_text, versions.get_version(v1["id"])["rewritten_text"])
        self.assertIn(replacement, v2["rewritten_text"])

    def test_branch_canon_reversions_all_downstream_facts_and_closes_chain(self) -> None:
        project_id, chapters = self.project([("One", "Baseline")], kind="branch")
        branches = BranchService(self.database)
        branch = branches.create_branch(
            project_id=project_id,
            name="fact chain",
            branch_mode="fork",
            start_anchor={"anchor_type": "document_end"},
        )
        chapter = branches.create_chapter(branch["id"], title="generated")
        old_text = next(iter(FakeCanonLLM.REWRITES))
        replacement = FakeCanonLLM.REWRITES[old_text][0]
        source_fact = self.facts(old_text)
        scenes = []
        for index, (text, location) in enumerate(
            [
                (old_text, "A"),
                ("He crosses the quiet hall.", "B"),
                ("He reaches the tower.", "C"),
            ],
            1,
        ):
            scenes.append(
                branches.save_scene(
                    branch["id"],
                    branch_chapter_id=chapter["id"],
                    title=f"scene {index}",
                    generated_text=text,
                    facts_after={"location": location, "injury": source_fact},
                )
            )
        run = self.scan_injury(project_id, branch_id=branch["id"])
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        applied = self.service.apply(run["id"])
        current_scenes = branches.list_scenes(branch["id"])
        current_chapter = branches.get_chapter(chapter["id"])
        self.assertEqual("applied", applied["status"])
        self.assertEqual([2, 2, 2], [scene["current_version"] for scene in current_scenes])
        self.assertEqual(
            [replacement] * 3,
            [scene["facts_after"]["injury"]["value"] for scene in current_scenes],
        )
        self.assertEqual("C", current_chapter["facts_after"]["location"])
        self.assertEqual("consistent", current_chapter["fact_chain_status"])
        self.assertEqual(
            scenes[1]["generated_text"], current_scenes[1]["generated_text"]
        )

    def test_applied_and_cancelled_runs_are_terminal(self) -> None:
        project_id, _chapters = self.project(
            [("One", next(iter(FakeCanonLLM.REWRITES)))]
        )
        run = self.scan_injury(project_id)
        for patch in run["patches"]:
            self.service.review_patch(patch["id"], decision="accepted")
        applied = self.service.apply(run["id"])
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.service.apply(applied["id"])
        pending = self.scan_injury(project_id)
        cancelled = self.service.cancel(pending["id"])
        self.assertEqual("cancelled", cancelled["status"])
        with self.assertRaisesRegex(ValueError, "not ready"):
            self.service.apply(cancelled["id"])


if __name__ == "__main__":
    unittest.main()
