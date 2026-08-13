from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY_ROOT))
sys.path.insert(0, str(REPOSITORY_ROOT / "src"))

from examples.xianxia.seed_demo import seed_demo
from rusty.services import (
    AnchorService,
    ModelService,
    PipelineService,
    ProjectService,
    PromptService,
    StyleExtractionService,
    StyleTemplateService,
)
from rusty.services.ai_client import AIClient, AIResponse


EXAMPLE_ROOT = REPOSITORY_ROOT / "examples" / "xianxia"


class XianxiaAIClient(AIClient):
    def __init__(self, expected_rewrite: str, extracted_style: dict[str, object]) -> None:
        self.expected_rewrite = expected_rewrite.strip()
        self.extracted_style = extracted_style
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        user_text = "\n".join(message["content"] for message in messages if message["role"] == "user")
        if "Required style_profile dimensions:" in user_text:
            return AIResponse(json.dumps(self.extracted_style, ensure_ascii=False), {"total_tokens": 260}, 18)
        if "USER SUMMARY RULES" in user_text:
            response = {
                "plot_skeleton": "顾长青和苏晚照在黑石巷拦截携带玄墟残图的韩烬，韩烬拔刀突袭。",
                "key_events": ["拦截韩烬", "索要残图", "韩烬拔刀突袭"],
                "characters": [
                    {"name": "顾长青", "role": "拦截者"},
                    {"name": "苏晚照", "role": "同伴"},
                    {"name": "韩烬", "role": "持图者"},
                ],
            }
            return AIResponse(json.dumps(response, ensure_ascii=False), {"total_tokens": 120}, 12)
        if "AVAILABLE CATEGORIES" in user_text:
            response = {
                "analysis": {
                    "has_target_content": True,
                    "categories": ["combat", "dialogue", "cultivation"],
                    "markers": [
                        {
                            "category_id": "combat",
                            "category_name": "斗法与近身战",
                            "expand_description": "韩烬以短刀近身突袭，顾长青需要依照决策习惯应对。",
                            "evidence": "韩烬拔出短刀冲了上来。",
                        },
                        {
                            "category_id": "dialogue",
                            "category_name": "人物对话",
                            "expand_description": "顾长青向韩烬索要玄墟残图。",
                            "evidence": "把残图交出来。",
                        },
                    ],
                    "reasoning": "本章同时包含对话交涉、近身战和凝脉境术法约束。",
                }
            }
            return AIResponse(json.dumps(response, ensure_ascii=False), {"total_tokens": 90}, 9)
        if "RUSTY OUTPUT CONTRACT" in user_text:
            start = user_text.index("--- ORIGINAL CHAPTER:")
            original_section = user_text[start:].split("\n", 1)[1]
            original = original_section.rsplit("\n--- END ORIGINAL CHAPTER ---", 1)[0]
            response = {"anchor": original, "expanded": self.expected_rewrite}
            return AIResponse(json.dumps(response, ensure_ascii=False), {"total_tokens": 800}, 45)
        raise AssertionError(f"Unexpected xianxia request: {user_text[:200]}")


class XianxiaExampleTests(unittest.TestCase):
    def test_xianxia_world_character_technique_and_decision_rules_compile_and_rewrite(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "rusty.db"
            self.assertFalse(database_path.exists())
            seeded = seed_demo(database_path, root / "workspace", example_path=EXAMPLE_ROOT)
            project_id = seeded["project_id"]

            ModelService(database_path).create_model(
                display_name="Xianxia fake model",
                provider="openai_compatible",
                base_url="https://example.test/v1",
                model_name="xianxia-fake",
                is_default=True,
            )
            expected = (EXAMPLE_ROOT / "expected_rewrite.txt").read_text(encoding="utf-8").strip()
            extracted_style = json.loads(
                (EXAMPLE_ROOT / "extracted_style_baseline.json").read_text(encoding="utf-8")
            )
            ai_client = XianxiaAIClient(expected, extracted_style)
            style_template_id = StyleExtractionService(database_path, ai_client=ai_client).extract_from_file(
                EXAMPLE_ROOT / "style_source_excerpt.txt",
                name="古典斗法动作因果实测",
                detail_level="detailed",
            )
            StyleTemplateService(database_path).bind_project_style(project_id, style_template_id)
            pipeline = PipelineService(database_path, ai_client=ai_client)

            run_result = pipeline.run_project(project_id)
            chapter = ProjectService(database_path).list_chapters(project_id)[0]
            outputs = pipeline.get_chapter_ai_outputs(chapter.id)
            attempts = pipeline.list_generation_attempts(chapter.id)
            rewrite_attempt = [attempt for attempt in attempts if attempt["stage"] == "rewrite"][-1]
            system_text = rewrite_attempt["request"]["messages"][0]["content"]
            user_text = rewrite_attempt["request"]["messages"][1]["content"]
            prompt_template = PromptService(database_path).get_template(seeded["prompt_template_id"])
            outline_template = AnchorService(database_path).get_project_outline_template(project_id)
            character_cards = AnchorService(database_path).list_project_character_cards(project_id)
            style_template = StyleTemplateService(database_path).get_project_style_template(project_id)

        extraction_user_text = "\n".join(
            message["content"] for message in ai_client.calls[0] if message["role"] == "user"
        )
        self.assertIn("那怪闻言，展长枪就刺行者；行者举铁棒劈面相迎。", extraction_user_text)
        self.assertNotIn("青冥洲", extraction_user_text)
        self.assertNotIn("顾长青", extraction_user_text)

        self.assertEqual(1, run_result.processed)
        self.assertEqual(0, run_result.failed)
        self.assertEqual(expected, chapter.rewritten_text)
        self.assertEqual("anchor_expand", outputs.rewrite_mode)
        self.assertEqual(["combat", "dialogue", "cultivation"], outputs.scene_labels)
        self.assertEqual("combat", outputs.scene_markers[0]["category_id"])

        self.assertIsNotNone(prompt_template)
        self.assertEqual({}, prompt_template.story_anchor)
        self.assertEqual([], prompt_template.characters)
        self.assertIsNotNone(outline_template)
        self.assertEqual(3, len(character_cards))
        self.assertIsNotNone(style_template)
        self.assertIn("触发—出手—应对—结果", style_template.style_profile_json)

        self.assertIn("[RUSTY NATIVE RULES: rusty.native.rewrite.v1]", system_text)
        self.assertIn("[USER-OWNED SYSTEM RULES]", system_text)
        self.assertIn("Style template (古典斗法动作因果基准):", user_text)
        self.assertIn("每次攻击都要写出对手的即时应对", user_text)
        self.assertIn("青冥洲", user_text)
        self.assertIn("玄墟天门", user_text)
        self.assertIn("青崖叠浪掌", user_text)
        self.assertIn("不得写成火焰、雷电或金色巨掌", user_text)
        self.assertIn("踏虚七步", user_text)
        self.assertIn("不得写成空间穿梭", user_text)
        self.assertIn("玄霜剑式·封江", user_text)
        self.assertIn("近身突袭，距离三尺以内", user_text)
        self.assertIn("先以左脚踢膝或勾踝", user_text)
        self.assertIn("常用两到八字的短句", user_text)
        self.assertIn("人物对话", user_text)
        self.assertIn("韩烬拔出短刀冲了上来", user_text)

        self.assertIn("先退了半步", chapter.rewritten_text)
        self.assertIn("左脚贴着积水扫出", chapter.rewritten_text)
        self.assertIn("没有凭空消失", chapter.rewritten_text)
        self.assertIn("半息之后", chapter.rewritten_text)
        self.assertIn("右臂经脉发麻", chapter.rewritten_text)
        self.assertNotIn("金色巨掌", chapter.rewritten_text)
        self.assertNotIn("瞬移", chapter.rewritten_text)
        self.assertNotIn("行者", chapter.rewritten_text)
        self.assertNotIn("铁棒", chapter.rewritten_text)


if __name__ == "__main__":
    unittest.main()
