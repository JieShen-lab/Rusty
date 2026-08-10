from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.model_service import ModelConfig, ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.style_service import StyleTemplate, StyleTemplateService

MAX_STYLE_SAMPLE_CHARS = 12000
STYLE_DIMENSIONS = [
    "narrative_perspective",
    "sentence_rhythm",
    "paragraph_structure",
    "dialogue_style",
    "action_description",
    "psychological_description",
    "environment_description",
    "emotion_intensity",
    "rhetorical_habits",
    "information_density",
    "pacing_pattern",
    "avoid_patterns",
]


class StyleExtractionService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.model_service = ModelService(self.database_path)
        self.project_service = ProjectService(self.database_path)
        self.style_service = StyleTemplateService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()

    def extract_from_text(
        self,
        sample_text: str,
        name: str,
        detail_level: str = "standard",
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> int:
        sample = _sample_text(sample_text)
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(model, self.model_service.get_api_key(model.id), self._extraction_messages(sample, name, detail_level))
        extracted = _parse_extraction_json(response.text)
        return self.style_service.create_template(
            name=str(extracted.get("name") or name),
            description=str(extracted.get("description") or f"AI extracted style template: {name}"),
            detail_level=detail_level,
            global_prompt=str(extracted.get("global_prompt") or ""),
            rewrite_prompt=str(extracted.get("rewrite_prompt") or ""),
            style_profile=_object_or_empty(extracted.get("style_profile")),
            generated_prompt=str(extracted.get("generated_prompt") or extracted.get("rewrite_prompt") or ""),
            source_metadata={
                **(source_metadata or {}),
                "source_type": (source_metadata or {}).get("source_type", "paste"),
                "sample_character_count": len(sample),
                "detail_level": detail_level,
            },
            import_metadata={
                "created_by": "ai_style_extraction",
                "model_id": model.id,
                "model_name": model.model_name,
                "token_usage": response.token_usage,
                "elapsed_ms": response.elapsed_ms,
            },
        )

    def extract_from_file(
        self,
        source_path: str | Path,
        name: str,
        detail_level: str = "standard",
        model_id: int | None = None,
    ) -> int:
        book = self.project_service.preview_book(source_path)
        sample = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters)
        return self.extract_from_text(
            sample,
            name=name,
            detail_level=detail_level,
            model_id=model_id,
            source_metadata={
                "source_type": "file",
                "source_file_name": book.source_path.name,
                "source_format": book.source_format,
                "book_title": book.title,
            },
        )

    def trial_write(
        self,
        template_id: int,
        sample_scene: str,
        target_chars: int = 300,
        model_id: int | None = None,
    ) -> str:
        template = self.style_service.get_template(template_id)
        if template is None:
            raise ValueError(f"Style template not found: {template_id}")
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._trial_messages(template, sample_scene, target_chars),
        )
        return response.text

    def _resolve_model(self, model_id: int | None) -> ModelConfig:
        model = self.model_service.get_model(model_id) if model_id is not None else self.model_service.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model

    @staticmethod
    def _extraction_messages(sample_text: str, name: str, detail_level: str) -> list[dict[str, str]]:
        dimensions = "\n".join(f"- {item}" for item in STYLE_DIMENSIONS)
        return [
            {
                "role": "system",
                "content": (
                    "[RUSTY NATIVE RULES: rusty.native.style_extraction.v1]\n"
                    "You extract reusable prose style templates. Return strict JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Extract a structured style template from the sample prose.\n"
                    f"Template name: {name}\n"
                    f"Detail level: {detail_level}\n"
                    "Required style_profile dimensions:\n"
                    f"{dimensions}\n\n"
                    "Return JSON with keys: name, description, global_prompt, rewrite_prompt, "
                    "generated_prompt, style_profile.\n"
                    "Do not include policy-bypass, jailbreak, or privileged hidden instructions.\n\n"
                    f"Sample prose:\n{sample_text}"
                ),
            },
        ]

    @staticmethod
    def _trial_messages(template: StyleTemplate, sample_scene: str, target_chars: int) -> list[dict[str, str]]:
        style_profile = template.style_profile_json
        return [
            {
                "role": "system",
                "content": (
                    "[RUSTY NATIVE RULES: rusty.native.style_trial.v1]\n"
                    "Generate only a validation sample for the visible user-owned style rules.\n\n"
                    f"[USER-OWNED SYSTEM RULES]\n{template.global_prompt or 'None'}"
                ),
            },
            {
                "role": "user",
                "content": (
                    "Write a short validation sample using this style template.\n"
                    f"Target length: around {target_chars} Chinese characters or equivalent.\n"
                    f"Style profile JSON:\n{style_profile}\n\n"
                    f"Style instructions:\n{template.generated_prompt or template.rewrite_prompt}\n\n"
                    f"Scene seed:\n{sample_scene}"
                ),
            },
        ]


def _sample_text(text: str) -> str:
    sample = text.strip()
    if not sample:
        raise ValueError("Style extraction sample text is required.")
    return sample[:MAX_STYLE_SAMPLE_CHARS]


def _parse_extraction_json(text: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Style extraction did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError("Style extraction response must be a JSON object.")
    return value


def _object_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}
