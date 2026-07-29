from __future__ import annotations

import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rusty.db import session
from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.anchor_service import AnchorService
from rusty.services.material_service import MATERIAL_TYPES, MaterialService
from rusty.services.model_service import ModelConfig, ModelService
from rusty.services.project_service import ProjectService, default_database_path

MAX_ANCHOR_SAMPLE_CHARS = 16000
MAX_CHARACTER_EXTRACTION_TEXT_CHARS = 50000
MAX_CHARACTER_CANDIDATES = 20
CHARACTER_PREVIEW_TTL_SECONDS = 15 * 60
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
DEFAULT_CHARACTER_SYSTEM_PROMPT = (
    "[RUSTY NATIVE RULES: rusty.native.character_extraction.v2]\n"
    "You extract reusable character cards and return strict JSON only. "
    "Never invent facts unsupported by the source. Missing dimensions must be empty. "
    "Merge aliases that refer to the same person."
)
MATERIAL_DIMENSIONS = {
    "plot_skeleton": [
        "premise",
        "stages",
        "conflicts",
        "turning_points",
        "climax",
        "resolution",
        "hooks",
    ],
    "scene_reference": [
        "summary",
        "writing_guidance",
        "key_beats",
        "source_cues",
        "applicable_conditions",
        "avoidances",
    ],
}


@dataclass(frozen=True)
class CharacterExtractionSettings:
    model_id: int | None = None
    detail_level: str = "standard"
    max_candidates: int = 8
    extract_all_characters: bool = True
    generate_tags: bool = True
    generate_appearance: bool = True
    generate_relationships: bool = True
    generate_personality: bool = True
    generate_speech_style: bool = True
    generate_action_constraints: bool = True
    generate_anti_ooc_rules: bool = True
    generate_abilities_background: bool = True
    custom_requirements: str = ""
    system_prompt: str = DEFAULT_CHARACTER_SYSTEM_PROMPT


@dataclass(frozen=True)
class CharacterExtractionCandidate:
    candidate_id: str
    selected: bool
    name: str
    aliases: list[str]
    description: str
    identity: str
    age: str
    setting_text: str
    relationship_notes: str
    personality: str
    speech_style: str
    action_constraints: str
    anti_ooc_rules: str
    profile: dict[str, Any]
    custom_fields: list[dict[str, Any]]
    suggested_tags: list[str]
    evidence_summary: str


@dataclass(frozen=True)
class CharacterExtractionPreview:
    preview_token: str
    source_summary: dict[str, Any]
    candidates: list[CharacterExtractionCandidate]


@dataclass
class _StoredCharacterPreview:
    expires_at: float
    candidate_ids: set[str]
    source_metadata: dict[str, Any]
    source_summary: dict[str, Any]
    import_metadata: dict[str, Any]
    raw_text: str


_CHARACTER_PREVIEWS: dict[tuple[str, str], _StoredCharacterPreview] = {}


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
        self.material_service = MaterialService(self.database_path)
        self.ai_client = ai_client or OpenAICompatibleClient()

    def extract_materials_from_text(
        self,
        sample_text: str,
        *,
        material_type: str,
        scope: str = "public",
        project_id: int | None = None,
        name: str | None = None,
        detail_level: str = "standard",
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> list[int]:
        if material_type not in MATERIAL_TYPES:
            raise ValueError(f"Unsupported material type: {material_type}")
        sample = _sample_text(sample_text)
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._material_messages(sample, material_type, detail_level, name),
        )
        extracted = _parse_json_object(response.text, "Material extraction")
        items = extracted.get("materials")
        if not isinstance(items, list) or not items:
            raise ValueError("Material extraction response must contain a non-empty materials list.")
        shared_source_metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "sample_character_count": len(sample),
            "detail_level": detail_level,
            "material_type": material_type,
        }
        import_metadata = {
            "created_by": f"ai_{material_type}_extraction",
            "prompt_ruleset": f"rusty.native.material.{material_type}.v1",
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        material_ids: list[int] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                continue
            item_name = str(item.get("name") or name or "").strip()
            if not item_name:
                continue
            content = item.get("content")
            if not isinstance(content, dict):
                content = {
                    key: value
                    for key, value in item.items()
                    if key not in {"name", "description", "timeline_start_chapter", "timeline_end_chapter"}
                }
            material_ids.append(
                self.material_service.create_material(
                    material_type=material_type,
                    scope=scope,
                    project_id=project_id,
                    name=item_name,
                    description=str(item.get("description") or ""),
                    detail_level=detail_level,
                    raw_text=sample,
                    content=content,
                    analysis_status="analyzed",
                    source_metadata=shared_source_metadata,
                    import_metadata=import_metadata,
                    timeline_start_chapter=_positive_int_or_none(item.get("timeline_start_chapter")),
                    timeline_end_chapter=_positive_int_or_none(item.get("timeline_end_chapter")),
                    sort_order=index,
                )
            )
        if not material_ids:
            raise ValueError("Material extraction did not produce any valid materials.")
        return material_ids

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

    def get_character_extraction_settings(self) -> CharacterExtractionSettings:
        with session(self.database_path) as connection:
            row = connection.execute(
                "SELECT * FROM character_extraction_settings WHERE id = 1"
            ).fetchone()
        if row is None:
            return CharacterExtractionSettings()
        return CharacterExtractionSettings(
            model_id=row["model_id"],
            detail_level=str(row["detail_level"]),
            max_candidates=int(row["max_candidates"]),
            extract_all_characters=bool(row["extract_all_characters"]),
            generate_tags=bool(row["generate_tags"]),
            generate_appearance=bool(row["generate_appearance"]),
            generate_relationships=bool(row["generate_relationships"]),
            generate_personality=bool(row["generate_personality"]),
            generate_speech_style=bool(row["generate_speech_style"]),
            generate_action_constraints=bool(row["generate_action_constraints"]),
            generate_anti_ooc_rules=bool(row["generate_anti_ooc_rules"]),
            generate_abilities_background=bool(row["generate_abilities_background"]),
            custom_requirements=str(row["custom_requirements"]),
            system_prompt=str(row["system_prompt"] or DEFAULT_CHARACTER_SYSTEM_PROMPT),
        )

    def update_character_extraction_settings(
        self,
        **values: Any,
    ) -> CharacterExtractionSettings:
        current = asdict(self.get_character_extraction_settings())
        current.update(values)
        detail_level = str(current["detail_level"])
        if detail_level not in {"brief", "standard", "detailed"}:
            raise ValueError(f"Unsupported detail level: {detail_level}")
        max_candidates = max(1, min(MAX_CHARACTER_CANDIDATES, int(current["max_candidates"])))
        model_id = current.get("model_id")
        if model_id is not None and self.model_service.get_model(int(model_id)) is None:
            raise ValueError(f"Model not found: {model_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO character_extraction_settings (
                    id, model_id, detail_level, max_candidates,
                    extract_all_characters, generate_tags, generate_appearance,
                    generate_relationships, generate_personality, generate_speech_style,
                    generate_action_constraints, generate_anti_ooc_rules,
                    generate_abilities_background, custom_requirements, system_prompt
                ) VALUES (1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    model_id = excluded.model_id,
                    detail_level = excluded.detail_level,
                    max_candidates = excluded.max_candidates,
                    extract_all_characters = excluded.extract_all_characters,
                    generate_tags = excluded.generate_tags,
                    generate_appearance = excluded.generate_appearance,
                    generate_relationships = excluded.generate_relationships,
                    generate_personality = excluded.generate_personality,
                    generate_speech_style = excluded.generate_speech_style,
                    generate_action_constraints = excluded.generate_action_constraints,
                    generate_anti_ooc_rules = excluded.generate_anti_ooc_rules,
                    generate_abilities_background = excluded.generate_abilities_background,
                    custom_requirements = excluded.custom_requirements,
                    system_prompt = excluded.system_prompt,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    model_id,
                    detail_level,
                    max_candidates,
                    int(bool(current["extract_all_characters"])),
                    int(bool(current["generate_tags"])),
                    int(bool(current["generate_appearance"])),
                    int(bool(current["generate_relationships"])),
                    int(bool(current["generate_personality"])),
                    int(bool(current["generate_speech_style"])),
                    int(bool(current["generate_action_constraints"])),
                    int(bool(current["generate_anti_ooc_rules"])),
                    int(bool(current["generate_abilities_background"])),
                    str(current["custom_requirements"] or ""),
                    str(current["system_prompt"] or DEFAULT_CHARACTER_SYSTEM_PROMPT),
                ),
            )
        return self.get_character_extraction_settings()

    def reset_character_extraction_settings(self) -> CharacterExtractionSettings:
        with session(self.database_path) as connection:
            connection.execute("DELETE FROM character_extraction_settings WHERE id = 1")
        return CharacterExtractionSettings()

    def preview_characters_from_text(
        self,
        sample_text: str,
        name: str | None = None,
        detail_level: str | None = None,
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> CharacterExtractionPreview:
        normalized_text = sample_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            raise ValueError("Character extraction text is empty.")
        if len(normalized_text) > MAX_CHARACTER_EXTRACTION_TEXT_CHARS:
            raise ValueError(
                f"Character extraction text must be {MAX_CHARACTER_EXTRACTION_TEXT_CHARS:,} characters or fewer."
            )
        settings = self.get_character_extraction_settings()
        selected_detail = detail_level or settings.detail_level
        sample = _sample_text(normalized_text)
        model = self._resolve_model(model_id if model_id is not None else settings.model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._character_messages(sample, selected_detail, name, settings),
        )
        extracted = _parse_json_object(response.text, "Character extraction")
        characters = extracted.get("characters")
        if not isinstance(characters, list) or not characters:
            raise ValueError("Character extraction response must contain a non-empty characters list.")
        metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "sample_character_count": len(sample),
            "detail_level": selected_detail,
        }
        import_metadata = {
            "created_by": "ai_character_extraction",
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        candidates: list[CharacterExtractionCandidate] = []
        for item in characters[: settings.max_candidates]:
            if not isinstance(item, dict):
                continue
            candidate_name = str(item.get("name") or "").strip()
            if not candidate_name:
                continue
            profile = _object_or_empty(item.get("profile"))
            candidates.append(
                CharacterExtractionCandidate(
                    candidate_id=secrets.token_hex(8),
                    selected=True,
                    name=candidate_name,
                    aliases=_string_list(item.get("aliases")),
                    description=str(item.get("description") or ""),
                    identity=str(item.get("identity") or profile.get("identity") or ""),
                    age=str(item.get("age") or profile.get("age") or ""),
                    setting_text=str(item.get("setting_text") or ""),
                    relationship_notes=str(item.get("relationship_notes") or ""),
                    personality=str(item.get("personality") or ""),
                    speech_style=str(item.get("speech_style") or ""),
                    action_constraints=str(item.get("action_constraints") or ""),
                    anti_ooc_rules=str(item.get("anti_ooc_rules") or ""),
                    profile=profile,
                    custom_fields=_custom_fields(item.get("custom_fields")),
                    suggested_tags=(
                        _suggested_tags(item.get("suggested_tags"))
                        if settings.generate_tags
                        else []
                    ),
                    evidence_summary=str(item.get("evidence_summary") or ""),
                )
            )
        if name and name.strip():
            target = name.strip().casefold()
            candidates = [
                candidate
                for candidate in candidates
                if candidate.name.casefold() == target
                or target in {alias.casefold() for alias in candidate.aliases}
            ][:1]
        if not candidates:
            raise ValueError("Character extraction did not produce any valid character cards.")
        token = secrets.token_urlsafe(24)
        source_summary = _extraction_source_summary(metadata)
        _CHARACTER_PREVIEWS[(str(self.database_path.resolve()), token)] = _StoredCharacterPreview(
            expires_at=time.monotonic() + CHARACTER_PREVIEW_TTL_SECONDS,
            candidate_ids={candidate.candidate_id for candidate in candidates},
            source_metadata=metadata,
            source_summary=source_summary,
            import_metadata=import_metadata,
            raw_text=sample,
        )
        return CharacterExtractionPreview(
            preview_token=token,
            source_summary=source_summary,
            candidates=candidates,
        )

    def apply_character_extraction(
        self,
        *,
        preview_token: str,
        candidates: list[dict[str, Any]],
        selected_candidate_ids: list[str],
        scope: str,
        project_id: int | None,
        category_ids: list[int] | None = None,
    ) -> dict[str, list[dict[str, Any]]]:
        key = (str(self.database_path.resolve()), preview_token)
        stored = _CHARACTER_PREVIEWS.get(key)
        if stored is None:
            raise ValueError("Character extraction preview token is invalid.")
        if stored.expires_at <= time.monotonic():
            _CHARACTER_PREVIEWS.pop(key, None)
            raise ValueError("Character extraction preview token has expired.")
        selected_ids = list(dict.fromkeys(selected_candidate_ids))
        if not set(selected_ids).issubset(stored.candidate_ids):
            raise ValueError("Character extraction preview token or candidate selection was tampered with.")
        if scope not in {"public", "project"}:
            raise ValueError(f"Unsupported character scope: {scope}")
        if scope == "project" and project_id is None:
            raise ValueError("Project character extraction requires a project.")
        if scope == "project" and category_ids:
            raise ValueError("Project characters cannot belong to public character categories.")
        valid_categories = {category.id for category in self.anchor_service.list_character_categories()}
        if not set(category_ids or []).issubset(valid_categories):
            raise ValueError("One or more character categories do not exist.")

        by_id = {
            str(candidate.get("candidate_id") or ""): candidate
            for candidate in candidates
            if isinstance(candidate, dict)
        }
        created: list[dict[str, Any]] = []
        errors: list[dict[str, Any]] = []
        for candidate_id in selected_ids:
            candidate = by_id.get(candidate_id)
            if candidate is None:
                errors.append({"candidate_id": candidate_id, "error": "Candidate payload is missing."})
                continue
            name = str(candidate.get("name") or "").strip()
            if not name:
                errors.append({"candidate_id": candidate_id, "error": "Character name is required."})
                continue
            try:
                tag_ids = [
                    int(self.anchor_service.create_character_tag(tag_name)["id"])
                    for tag_name in _suggested_tags(candidate.get("confirmed_tags"))
                ]
                card_id = self.anchor_service.create_character_card(
                    name=name,
                    aliases=_string_list(candidate.get("aliases")),
                    description=str(candidate.get("description") or ""),
                    relationship_notes=str(candidate.get("relationship_notes") or ""),
                    personality=str(candidate.get("personality") or ""),
                    speech_style=str(candidate.get("speech_style") or ""),
                    action_constraints=str(candidate.get("action_constraints") or ""),
                    anti_ooc_rules=str(candidate.get("anti_ooc_rules") or ""),
                    profile=_object_or_empty(candidate.get("profile")),
                    source_metadata=stored.source_metadata,
                    import_metadata=stored.import_metadata,
                    scope=scope,
                    project_id=project_id,
                    identity=str(candidate.get("identity") or ""),
                    age=str(candidate.get("age") or ""),
                    setting_text=str(candidate.get("setting_text") or ""),
                    custom_fields=_custom_fields(candidate.get("custom_fields")),
                    raw_text=stored.raw_text,
                    analysis_status="analyzed",
                    tag_ids=tag_ids,
                )
                if scope == "public":
                    for category_id in category_ids or []:
                        self.anchor_service.set_character_category(card_id, category_id, True)
                created.append({"candidate_id": candidate_id, "card_id": card_id})
            except Exception as exc:
                errors.append({"candidate_id": candidate_id, "error": str(exc)})
        return {"created": created, "errors": errors}

    def extract_characters_from_text(
        self,
        sample_text: str,
        name: str | None = None,
        detail_level: str = "standard",
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
        scope: str = "public",
        project_id: int | None = None,
    ) -> list[int]:
        preview = self.preview_characters_from_text(
            sample_text,
            name=name,
            detail_level=detail_level,
            model_id=model_id,
            source_metadata=source_metadata,
        )
        result = self.apply_character_extraction(
            preview_token=preview.preview_token,
            candidates=[
                {**asdict(candidate), "confirmed_tags": []}
                for candidate in preview.candidates
            ],
            selected_candidate_ids=[candidate.candidate_id for candidate in preview.candidates],
            scope=scope,
            project_id=project_id,
            category_ids=[],
        )
        if result["errors"]:
            raise ValueError(str(result["errors"][0]["error"]))
        return [int(item["card_id"]) for item in result["created"]]

    def extract_characters_from_file(
        self,
        source_path: str | Path,
        name: str | None = None,
        detail_level: str = "standard",
        model_id: int | None = None,
        scope: str = "public",
        project_id: int | None = None,
    ) -> list[int]:
        book = self.project_service.preview_book(source_path)
        sample = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters)
        return self.extract_characters_from_text(
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
            scope=scope,
            project_id=project_id,
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
            {
                "role": "system",
                "content": (
                    "[RUSTY NATIVE RULES: rusty.native.outline_extraction.v1]\n"
                    "You extract reusable plot outline anchors. Return strict JSON only."
                ),
            },
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

    def _character_messages(
        self,
        sample_text: str,
        detail_level: str,
        name: str | None = None,
        settings: CharacterExtractionSettings | None = None,
    ) -> list[dict[str, str]]:
        settings = settings or self.get_character_extraction_settings()
        dimensions = [
            "aliases",
            "role_in_story",
            "identity",
            "age",
            "setting_text",
        ]
        if settings.generate_appearance:
            dimensions.append("appearance")
        if settings.generate_relationships:
            dimensions.append("relationships")
        if settings.generate_personality:
            dimensions.append("personality")
        if settings.generate_speech_style:
            dimensions.append("speech_style")
        if settings.generate_action_constraints:
            dimensions.append("action_constraints")
        if settings.generate_anti_ooc_rules:
            dimensions.append("anti_ooc_rules")
        if settings.generate_abilities_background:
            dimensions.extend(["abilities", "background"])
        dimensions_text = "\n".join(f"- {item}" for item in dimensions)
        target_rule = (
            f"Only extract the target character named “{name.strip()}”; use aliases and context to merge references to that person."
            if name and name.strip()
            else "Extract every identifiable character with enough textual evidence; merge aliases that refer to the same person."
        )
        tag_rule = (
            "Return 0-8 short suggested_tags useful for retrieval (for example protagonist, antagonist, first-person, calm, combat). "
            "Never use sentences as tags and never infer unsupported tags."
            if settings.generate_tags
            else "Return suggested_tags as an empty array."
        )
        return [
            {
                "role": "system",
                "content": settings.system_prompt or DEFAULT_CHARACTER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    "Extract structured character cards from the sample prose.\n"
                    f"{target_rule}\n"
                    f"Detail level: {detail_level}\n"
                    f"Maximum candidates: {settings.max_candidates}\n"
                    "Required character dimensions:\n"
                    f"{dimensions_text}\n\n"
                    "Return JSON with key characters, an array of objects. Each object must include: "
                    "name, aliases, description, identity, age, setting_text, relationship_notes, personality, "
                    "speech_style, action_constraints, anti_ooc_rules, profile, custom_fields, suggested_tags, evidence_summary.\n"
                    "Analyze each character dimension independently. Put uncertain or absent dimensions as empty strings, empty arrays, or empty objects; do not speculate.\n"
                    "The profile object should contain reusable visual fields such as identity, appearance, abilities, goals, background, strengths, weaknesses, and evidence when supported.\n"
                    f"{tag_rule}\n"
                    f"Additional requirements: {settings.custom_requirements or 'None'}\n\n"
                    f"Sample prose:\n{sample_text}"
                ),
            },
        ]

    @staticmethod
    def _material_messages(
        sample_text: str,
        material_type: str,
        detail_level: str,
        name: str | None,
    ) -> list[dict[str, str]]:
        dimensions = "\n".join(f"- {item}" for item in MATERIAL_DIMENSIONS[material_type])
        requested_name = name.strip() if name and name.strip() else "derive from source"
        shape = (
            "scene_reference content keys: summary, writing_guidance, key_beats, source_cues, applicable_conditions, avoidances."
            if material_type == "scene_reference"
            else "plot_skeleton content keys: premise, stages, conflicts, turning_points, climax, resolution, hooks."
        )
        return [
            {
                "role": "system",
                "content": (
                    f"[RUSTY NATIVE RULES: rusty.native.material.{material_type}.v1]\n"
                    "Extract reusable writing resources from prose. Return strict JSON only. "
                    "Do not invent unsupported facts and do not return Markdown."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Material type: {material_type}\n"
                    f"Suggested name: {requested_name}\n"
                    f"Detail level: {detail_level}\n"
                    "Required dimensions:\n"
                    f"{dimensions}\n\n"
                    f"{shape}\n"
                    "Return JSON: {\"materials\":[{\"name\":\"\", \"description\":\"\", \"content\":{}, \"evidence\":[], \"confidence\":0.0}]}\n\n"
                    f"Source prose:\n{sample_text}"
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


def _suggested_tags(value: Any) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for item in _string_list(value)[:8]:
        name = " ".join(item.strip().split())
        key = name.casefold()
        if not name or len(name) > 40 or key in seen:
            continue
        tags.append(name)
        seen.add(key)
    return tags


def _custom_fields(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    fields: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            continue
        label = " ".join(str(item.get("label") or "").strip().split())
        if not label or label.casefold() in seen:
            continue
        seen.add(label.casefold())
        fields.append(
            {
                "id": str(item.get("id") or f"field_{len(fields)}"),
                "label": label,
                "value": str(item.get("value") or ""),
                "sort_order": len(fields),
            }
        )
    return fields


def _extraction_source_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    source_type = str(metadata.get("source_type") or "paste")
    if source_type == "document" or metadata.get("document_id") is not None:
        document_title = str(metadata.get("document_title") or "文档选区")
        chapter_title = str(metadata.get("chapter_title") or "").strip()
        return {
            "kind": "document_selection",
            "label": f"《{document_title}》{f' · {chapter_title}' if chapter_title else ''}",
            "document_id": metadata.get("document_id"),
            "chapter_id": metadata.get("chapter_id"),
        }
    if source_type == "file":
        filename = str(metadata.get("source_file_name") or "本地文件")
        return {"kind": "file_import", "label": f"文件 {filename}"}
    return {"kind": "ai_extraction", "label": "AI 文本提取"}


def _priority(value: Any) -> int:
    try:
        priority = int(value)
    except (TypeError, ValueError):
        return 50
    return max(0, min(100, priority))


def _positive_int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
