from __future__ import annotations

import json
from pathlib import Path

import pytest

from rusty.services.ai_client import AIClient, AIResponse
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services.material_service import MaterialService
from rusty.services.model_service import ModelService
from tests.support import initialized_database


class StyleAI(AIClient):
    def __init__(self) -> None:
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, model, api_key, messages):
        self.calls.append(messages)
        return AIResponse(
            text=json.dumps({
                "materials": [{
                    "name": "作者风格", "description": "简洁克制",
                    "content": {"schema_version": 1, "summary": "简洁", "dimensions": [
                        {"id": "sentence", "name": "句式", "requirement": "分析句式",
                         "analysis": "短句", "features": ["短"], "examples": ["样本文本"]}
                    ]},
                    "suggested_general_tags": ["简洁"], "suggested_applicable_scene_tags": ["叙事"],
                    "confidence": 0.9,
                }]
            }, ensure_ascii=False),
            token_usage={"total_tokens": 1}, elapsed_ms=1,
        )


def service(tmp_path: Path) -> tuple[Path, AnchorExtractionService, StyleAI]:
    database = initialized_database(tmp_path / "rusty.db")
    ModelService(database).create_model(
        display_name="Fake", provider="openai_compatible", base_url="https://example.invalid/v1",
        model_name="fake", is_default=True,
    )
    ai = StyleAI()
    return database, AnchorExtractionService(database, ai_client=ai), ai


def test_author_style_preview_is_pure_and_apply_token_is_single_use(tmp_path: Path) -> None:
    database, extraction, _ = service(tmp_path)
    preview = extraction.preview_materials_from_text("样本文本", task_type="author_style_extraction")
    assert MaterialService(database).list_materials() == []
    candidate = preview.candidates[0]
    payload = [{**candidate.__dict__, "confirmed_general_tags": ["简洁"],
                "confirmed_applicable_scene_tags": ["叙事"], "category_ids": []}]
    result = extraction.apply_material_extraction(
        preview_token=preview.preview_token, candidates=payload,
        selected_candidate_ids=[candidate.candidate_id],
    )
    material = MaterialService(database).get_material(result["created"][0]["material_id"])
    assert material is not None
    assert material.material_type == "author_style"
    assert material.raw_text == "样本文本"
    assert material.general_tags == ("简洁",)
    with pytest.raises(ValueError, match="already used"):
        extraction.apply_material_extraction(
            preview_token=preview.preview_token, candidates=payload,
            selected_candidate_ids=[candidate.candidate_id],
        )


def test_apply_uses_preview_settings_snapshot_and_preserves_full_source(tmp_path: Path) -> None:
    database, extraction, ai = service(tmp_path)
    settings = extraction.material_service.get_ai_settings("author_style_extraction")
    extraction.material_service.update_ai_settings(
        "author_style_extraction", model_id=settings.model_id, detail_level="detailed",
        system_prompt=settings.system_prompt, base_instruction=settings.base_instruction,
        dimensions=[dict(item) for item in settings.dimensions], extra_requirements=settings.extra_requirements,
    )
    source = "甲" * 50000
    preview = extraction.preview_materials_from_text(source, task_type="author_style_extraction")
    candidate = preview.candidates[0]
    extraction.material_service.update_ai_settings(
        "author_style_extraction", model_id=settings.model_id, detail_level="brief",
        system_prompt=settings.system_prompt, base_instruction=settings.base_instruction,
        dimensions=[dict(item) for item in settings.dimensions], extra_requirements=settings.extra_requirements,
    )
    result = extraction.apply_material_extraction(
        preview_token=preview.preview_token,
        candidates=[{**candidate.__dict__, "confirmed_general_tags": [],
                     "confirmed_applicable_scene_tags": [], "category_ids": []}],
        selected_candidate_ids=[candidate.candidate_id],
    )
    material = MaterialService(database).get_material(result["created"][0]["material_id"])
    assert material is not None
    assert material.detail_level == "detailed"
    assert material.raw_text == source
    assert json.loads(material.source_metadata_json)["model_sample_character_count"] == 16000
    assert len(ai.calls[0][-1]["content"].split("Source text:\n", 1)[1]) == 16000


def test_only_author_style_extraction_settings_exist(tmp_path: Path) -> None:
    database, extraction, _ = service(tmp_path)
    assert [item.task_type for item in MaterialService(database).list_ai_settings()] == ["author_style_extraction"]
    with pytest.raises(ValueError, match="Unsupported material extraction task"):
        extraction.preview_materials_from_text("x", task_type="plot_skeleton_extraction")
