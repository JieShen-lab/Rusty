from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.anchor_service import AnchorService
from rusty.services.model_service import ModelConfig, ModelService
from rusty.services.project_service import ProjectService, default_database_path

MAX_ANCHOR_SAMPLE_CHARS = 16000
OUTLINE_DIMENSIONS = [
    "fixed_plot_beats",
    "causal_chain",
    "timeline",
    "relationship_progression",
    "must_keep_details",
    "forbidden_changes",
    "chapter_expansion_hooks",
]
CHARACTER_DIMENSIONS = [
    "aliases",
    "role_in_story",
    "relationships",
    "personality",
    "speech_style",
    "action_habits",
    "emotional_triggers",
    "anti_ooc_rules",
]


class AnchorExtractionService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        ai_client: AIClient | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.model_service = ModelService(self.database_path)
        self.project_service = ProjectService(self.database_path)
        self.anchor_service = AnchorService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()

    def extract_outline_from_text(
        self,
        sample_text: str,
        name: str,
        detail_level: str = "standard",
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> int:
        sample = _sample_text(sample_text)
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._outline_messages(sample, name, detail_level),
        )
        extracted = _parse_json_object(response.text, "Outline extraction")
        return self.anchor_service.create_outline_template(
            name=str(extracted.get("name") or name),
            description=str(extracted.get("description") or f"AI extracted outline template: {name}"),
            detail_level=detail_level,
            outline=_object_or_empty(extracted.get("outline")),
            anchor_prompt=str(extracted.get("anchor_prompt") or ""),
            source_metadata={
                **(source_metadata or {}),
                "source_type": (source_metadata or {}).get("source_type", "paste"),
                "sample_character_count": len(sample),
                "detail_level": detail_level,
            },
            import_metadata={
                "created_by": "ai_outline_extraction",
                "model_id": model.id,
                "model_name": model.model_name,
                "token_usage": response.token_usage,
                "elapsed_ms": response.elapsed_ms,
            },
        )

    def extract_outline_from_file(
        self,
        source_path: str | Path,
        name: str,
        detail_level: str = "standard",
        model_id: int | None = None,
    ) -> int:
        book = self.project_service.preview_book(source_path)
        sample = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters)
        return self.extract_outline_from_text(
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

    def extract_characters_from_text(
        self,
        sample_text: str,
        detail_level: str = "standard",
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[int]:
        sample = _sample_text(sample_text)
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._character_messages(sample, detail_level),
        )
        extracted = _parse_json_object(response.text, "Character extraction")
        characters = extracted.get("characters")
        if not isinstance(characters, list) or not characters:
            raise ValueError("Character extraction response must contain a non-empty characters list.")
        metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "sample_character_count": len(sample),
            "detail_level": detail_level,
        }
        import_metadata = {
            "created_by": "ai_character_extraction",
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        card_ids: list[int] = []
        for item in characters:
            if not isinstance(item, dict):
                continue
            card_ids.append(
                self.anchor_service.create_character_card(
                    name=str(item.get("name") or ""),
                    aliases=_string_list(item.get("aliases")),
                    description=str(item.get("description") or ""),
                    priority=_priority(item.get("priority")),
                    is_main=bool(item.get("is_main")),
                    relationship_notes=str(item.get("relationship_notes") or ""),
                    personality=str(item.get("personality") or ""),
                    speech_style=str(item.get("speech_style") or ""),
                    action_constraints=str(item.get("action_constraints") or ""),
                    anti_ooc_rules=str(item.get("anti_ooc_rules") or ""),
                    profile=_object_or_empty(item.get("profile")),
                    source_metadata=metadata,
                    import_metadata=import_metadata,
                )
            )
        if not card_ids:
            raise ValueError("Character extraction did not produce any valid character cards.")
        return card_ids

    def extract_characters_from_file(
        self,
        source_path: str | Path,
        detail_level: str = "standard",
        model_id: int | None = None,
    ) -> list[int]:
        book = self.project_service.preview_book(source_path)
        sample = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters)
        return self.extract_characters_from_text(
            sample,
            detail_level=detail_level,
            model_id=model_id,
            source_metadata={
                "source_type": "file",
                "source_file_name": book.source_path.name,
                "source_format": book.source_format,
                "book_title": book.title,
            },
        )

    def _resolve_model(self, model_id: int | None) -> ModelConfig:
        model = self.model_service.get_model(model_id) if model_id is not None else self.model_service.get_default_model()
        if model is None:
            raise ValueError("No model configured.")
        return model

    @staticmethod
    def _outline_messages(sample_text: str, name: str, detail_level: str) -> list[dict[str, str]]:
        dimensions = "\n".join(f"- {item}" for item in OUTLINE_DIMENSIONS)
        return [
            {"role": "system", "content": "You extract reusable plot outline anchors. Return strict JSON only."},
            {
                "role": "user",
                "content": (
                    "Extract a structured outline template from the sample prose.\n"
                    f"Template name: {name}\n"
                    f"Detail level: {detail_level}\n"
                    "Required outline dimensions:\n"
                    f"{dimensions}\n\n"
                    "Return JSON with keys: name, description, anchor_prompt, outline.\n"
                    "The anchor_prompt must be usable during rewrite to preserve plot, timeline, causality, and required details.\n\n"
                    f"Sample prose:\n{sample_text}"
                ),
            },
        ]

    @staticmethod
    def _character_messages(sample_text: str, detail_level: str) -> list[dict[str, str]]:
        dimensions = "\n".join(f"- {item}" for item in CHARACTER_DIMENSIONS)
        return [
            {"role": "system", "content": "You extract reusable character cards. Return strict JSON only."},
            {
                "role": "user",
                "content": (
                    "Extract structured character cards from the sample prose.\n"
                    f"Detail level: {detail_level}\n"
                    "Required character dimensions:\n"
                    f"{dimensions}\n\n"
                    "Return JSON with key characters, an array of objects. Each object must include: "
                    "name, aliases, description, priority, is_main, relationship_notes, personality, "
                    "speech_style, action_constraints, anti_ooc_rules, profile.\n"
                    "Use priority 80-100 for main or always-relevant characters; 0-79 for ordinary characters.\n\n"
                    f"Sample prose:\n{sample_text}"
                ),
            },
        ]


def _sample_text(text: str) -> str:
    sample = text.strip()
    if not sample:
        raise ValueError("Anchor extraction sample text is required.")
    return sample[:MAX_ANCHOR_SAMPLE_CHARS]


def _parse_json_object(text: str, label: str) -> dict[str, Any]:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:].strip()
    try:
        value = json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} did not return valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} response must be a JSON object.")
    return value


def _object_or_empty(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _string_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, priority))
