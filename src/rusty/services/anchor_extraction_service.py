from __future__ import annotations

import copy
import json
import secrets
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from typing import Any

from rusty.db import session
from rusty.services.ai_client import AIClient, OpenAICompatibleClient
from rusty.services.anchor_service import AnchorService
from rusty.services.extraction_apply_error import CandidateApplyError
from rusty.services.material_service import (
    MATERIAL_AI_TASK_TYPES,
    MATERIAL_TYPES,
    MaterialService,
    merge_author_style_content,
    normalize_material_content,
)
from rusty.services.model_service import ModelConfig, ModelService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService

MAX_ANCHOR_SAMPLE_CHARS = 16000
MAX_CHARACTER_EXTRACTION_TEXT_CHARS = 50000
CHARACTER_PREVIEW_TTL_SECONDS = 15 * 60
MATERIAL_PREVIEW_TTL_SECONDS = 15 * 60
MAX_MATERIAL_EXTRACTION_TEXT_CHARS = 50000
OUTLINE_DIMENSIONS = [
    "fixed_plot_beats",
    "causal_chain",
    "timeline",
    "relationship_progression",
    "must_keep_details",
    "forbidden_changes",
    "chapter_expansion_hooks",
]
DEFAULT_CHARACTER_DIMENSIONS = (
    {"id": "appearance", "label": "外貌", "instruction": "只提取原文明确描述的外貌特征。", "sort_order": 0, "enabled": True, "is_default": True},
    {"id": "relationships", "label": "人物关系", "instruction": "只记录目标人物与其他人物的明确关系。", "sort_order": 1, "enabled": True, "is_default": True},
    {"id": "personality", "label": "性格", "instruction": "基于明确行为和叙述提取性格，不进行猜测。", "sort_order": 2, "enabled": True, "is_default": True},
    {"id": "speech_style", "label": "语言风格", "instruction": "提取措辞、语气和说话习惯。", "sort_order": 3, "enabled": True, "is_default": True},
    {"id": "action_constraints", "label": "动作习惯 / 动作约束", "instruction": "提取反复出现的动作习惯与明确动作约束。", "sort_order": 4, "enabled": True, "is_default": True},
    {"id": "abilities_background", "label": "能力与背景", "instruction": "提取有文本证据的能力、经历与背景。", "sort_order": 5, "enabled": True, "is_default": True},
    {"id": "anti_ooc_rules", "label": "反 OOC 规则", "instruction": "根据明确证据总结不可违背的行为边界。", "sort_order": 6, "enabled": True, "is_default": True},
)
DEFAULT_CHARACTER_SYSTEM_PROMPT = (
    "[RUSTY NATIVE RULES: rusty.native.character_extraction.v2]\n"
    "You extract exactly one explicitly named character and return strict JSON only. "
    "Never invent facts unsupported by the source. Missing dimensions must be empty. "
    "Other people may only appear as relationship evidence for the target character."
)
MATERIAL_DIMENSIONS = {"author_style": ["dimensions"]}


@dataclass(frozen=True)
class CharacterExtractionSettings:
    model_id: int | None = None
    detail_level: str = "standard"
    custom_requirements: str = ""
    system_prompt: str = DEFAULT_CHARACTER_SYSTEM_PROMPT
    dimensions: tuple[dict[str, Any], ...] = DEFAULT_CHARACTER_DIMENSIONS


@dataclass(frozen=True)
class CharacterExtractionDraft:
    name: str
    aliases: list[str]
    description: str
    identity: str
    age: str
    stable_fields: list[dict[str, Any]]
    source_metadata: dict[str, Any]
    import_metadata: dict[str, Any]
    raw_text: str


@dataclass(frozen=True)
class CharacterExtractionPreview:
    preview_token: str
    expires_at: str
    character: CharacterExtractionDraft


@dataclass
class _StoredCharacterPreview:
    expires_at: float
    expires_at_iso: str
    state: str
    source_metadata: dict[str, Any]
    source_summary: dict[str, Any]
    import_metadata: dict[str, Any]
    raw_text: str
    lock: Any = field(default_factory=Lock, repr=False)


_CHARACTER_PREVIEWS: dict[tuple[str, str], _StoredCharacterPreview] = {}
_CHARACTER_PREVIEWS_LOCK = Lock()


@dataclass(frozen=True)
class MaterialExtractionCandidate:
    candidate_id: str
    material_type: str
    selected: bool
    name: str
    description: str
    content: dict[str, Any]
    evidence: list[dict[str, Any]]
    evidence_summary: str
    confidence: float
    warnings: list[str]


@dataclass(frozen=True)
class MaterialExtractionPreview:
    preview_token: str
    expires_at: str
    task_type: str
    material_type: str
    source_summary: dict[str, Any]
    prompt_snapshot: dict[str, Any]
    candidates: list[MaterialExtractionCandidate]


@dataclass
class _StoredMaterialPreview:
    expires_at: float
    expires_at_iso: str
    state: str
    task_type: str
    material_type: str
    candidate_ids: set[str]
    source_metadata: dict[str, Any]
    source_summary: dict[str, Any]
    import_metadata: dict[str, Any]
    raw_text: str
    prompt_snapshot: dict[str, Any]
    lock: Any = field(default_factory=Lock, repr=False)


_MATERIAL_PREVIEWS: dict[tuple[str, str], _StoredMaterialPreview] = {}
_MATERIAL_PREVIEWS_LOCK = Lock()


def _prune_expired_previews(previews: dict[tuple[str, str], Any]) -> None:
    now = time.monotonic()
    for key in [key for key, stored in previews.items() if stored.expires_at <= now]:
        previews.pop(key, None)


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

    def preview_materials_from_text(
        self,
        sample_text: str,
        *,
        task_type: str,
        name: str | None = None,
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> MaterialExtractionPreview:
        if task_type not in MATERIAL_AI_TASK_TYPES:
            raise ValueError(f"Unsupported material extraction task: {task_type}")
        normalized_text = sample_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            raise ValueError("Material extraction text is empty.")
        if len(normalized_text) > MAX_MATERIAL_EXTRACTION_TEXT_CHARS:
            raise ValueError(
                f"Material extraction text must be {MAX_MATERIAL_EXTRACTION_TEXT_CHARS:,} characters or fewer."
            )
        material_type = "author_style"
        settings = self.material_service.get_ai_settings(task_type)
        full_source_text = normalized_text
        model_sample = _sample_text(full_source_text)
        model = self._resolve_model(model_id if model_id is not None else settings.model_id)
        messages = self._material_preview_messages(
            model_sample,
            task_type=task_type,
            material_type=material_type,
            detail_level=settings.detail_level,
            name=name,
            system_prompt=settings.system_prompt,
            base_instruction=settings.base_instruction,
            dimensions=settings.dimensions,
            extra_requirements=settings.extra_requirements,
        )
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            messages,
        )
        extracted = _parse_json_object(response.text, "Material extraction preview")
        items = extracted.get("materials")
        if not isinstance(items, list) or not items:
            raise ValueError("Material extraction response must contain a non-empty materials list.")
        candidates: list[MaterialExtractionCandidate] = []
        for item in items[:1]:
            if not isinstance(item, dict):
                continue
            candidate_name = str(item.get("name") or name or "").strip()
            if not candidate_name:
                continue
            raw_content = item.get("content")
            if not isinstance(raw_content, dict):
                raw_content = {
                    key: value
                    for key, value in item.items()
                    if key not in {
                        "name", "description", "evidence_summary",
                    }
                }
            if material_type == "author_style":
                normalized_content = merge_author_style_content(raw_content, settings.dimensions)
            else:
                normalized_content = normalize_material_content(material_type, raw_content)
            normalized_content["work"] = ""
            warnings = _string_list(item.get("warnings"))
            returned_dimensions = raw_content.get("dimensions") if isinstance(raw_content, dict) else None
            returned_ids = {
                str(dimension.get("id") or "").strip()
                for dimension in returned_dimensions
                if isinstance(dimension, dict) and str(dimension.get("id") or "").strip()
            } if isinstance(returned_dimensions, list) else set()
            configured_ids = [str(dimension["id"]).strip() for dimension in settings.dimensions]
            missing_ids = [dimension_id for dimension_id in configured_ids if dimension_id not in returned_ids]
            unknown_ids = sorted(returned_ids.difference(configured_ids))
            if missing_ids:
                warnings.append(f"AI 未返回配置维度：{', '.join(missing_ids)}；已按空结果保留。")
            if unknown_ids:
                warnings.append(f"AI 返回了未知维度 ID：{', '.join(unknown_ids)}；已忽略。")
            if not normalized_content.get("overall_style"):
                warnings.append("AI 未返回 overall_style；整体风格暂为空，请在作者档案中补充。")
            candidates.append(
                MaterialExtractionCandidate(
                    candidate_id=secrets.token_hex(8),
                    material_type=material_type,
                    selected=True,
                    name=candidate_name,
                    description=str(item.get("description") or ""),
                    content=normalized_content,
                    evidence=[],
                    evidence_summary=str(item.get("evidence_summary") or ""),
                    confidence=_confidence(item.get("confidence")),
                    warnings=warnings,
                )
            )
        if not candidates:
            raise ValueError("Material extraction did not produce any valid candidates.")
        metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "source_character_count": len(full_source_text),
            "model_sample_character_count": len(model_sample),
            "source_truncated_for_model": len(model_sample) < len(full_source_text),
            "sample_character_count": len(model_sample),
            "task_type": task_type,
            "material_type": material_type,
        }
        source_summary = _material_extraction_source_summary(metadata)
        import_metadata = {
            "created_by": "ai_material_extraction",
            "task_type": task_type,
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        token = secrets.token_urlsafe(24)
        expires_at_monotonic, expires_at_iso = _preview_expiry(MATERIAL_PREVIEW_TTL_SECONDS)
        prompt_snapshot = {
            "task_type": task_type,
            "material_type": material_type,
            "model_id": model.id,
            "detail_level": settings.detail_level,
            "system_prompt": settings.system_prompt,
            "base_instruction": settings.base_instruction,
            "dimensions": [dict(item) for item in settings.dimensions],
            "extra_requirements": settings.extra_requirements,
            "messages": [
                {"role": message["role"], "content": message["content"]}
                for message in messages
            ],
        }
        with _MATERIAL_PREVIEWS_LOCK:
            _prune_expired_previews(_MATERIAL_PREVIEWS)
            _MATERIAL_PREVIEWS[
                (str(self.database_path.resolve()), token)
            ] = _StoredMaterialPreview(
                expires_at=expires_at_monotonic,
                expires_at_iso=expires_at_iso,
                state="pending",
                task_type=task_type,
                material_type=material_type,
                candidate_ids={item.candidate_id for item in candidates},
                source_metadata=metadata,
                source_summary=source_summary,
                import_metadata=import_metadata,
                raw_text=full_source_text,
                prompt_snapshot=copy.deepcopy(prompt_snapshot),
            )
        return MaterialExtractionPreview(
            preview_token=token,
            expires_at=expires_at_iso,
            task_type=task_type,
            material_type=material_type,
            source_summary=source_summary,
            prompt_snapshot=copy.deepcopy(prompt_snapshot),
            candidates=candidates,
        )

    def apply_material_extraction(
        self,
        *,
        preview_token: str,
        candidates: list[dict[str, Any]],
        selected_candidate_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        key = (str(self.database_path.resolve()), preview_token)
        with _MATERIAL_PREVIEWS_LOCK:
            stored = _MATERIAL_PREVIEWS.get(key)
            _prune_expired_previews(_MATERIAL_PREVIEWS)
        if stored is None:
            raise ValueError("Material extraction preview token is invalid.")
        with stored.lock:
            _ensure_preview_can_start_apply(stored, "Material")
            selected_ids, by_id = _validated_candidate_payloads(
                candidates,
                selected_candidate_ids,
                stored.candidate_ids,
                label="Material",
            )
            prepared: list[dict[str, Any]] = []
            for sort_order, candidate_id in enumerate(selected_ids):
                candidate = by_id[candidate_id]
                name = str(candidate.get("name") or "").strip()
                if not name:
                    raise ValueError(f"Material candidate {candidate_id} requires a name.")
                candidate_type = str(candidate.get("material_type") or stored.material_type)
                if candidate_type != stored.material_type:
                    raise ValueError("Material candidate type does not match the preview.")
                snapshot_dimensions = stored.prompt_snapshot.get("dimensions", [])
                if stored.material_type == "author_style":
                    content = merge_author_style_content(
                        candidate.get("content"), snapshot_dimensions
                    )
                else:
                    content = normalize_material_content(
                        stored.material_type, candidate.get("content")
                    )
                prepared.append(
                    {
                        "candidate_id": candidate_id,
                        "name": name,
                        "description": str(candidate.get("description") or ""),
                        "content": content,
                        "sort_order": sort_order,
                        "category_ids": list(
                            dict.fromkeys(int(value) for value in candidate.get("category_ids", []))
                        ),
                    }
                )
            stored.state = "applying"
        try:
            material_ids = self.material_service.create_extracted_material_batch(
                material_type=stored.material_type,
                candidates=prepared,
                detail_level=str(stored.prompt_snapshot["detail_level"]),
                raw_text=stored.raw_text,
                source_metadata=stored.source_metadata,
                import_metadata=stored.import_metadata,
            )
        except CandidateApplyError as exc:
            with stored.lock:
                stored.state = "pending"
            return {
                "created": [],
                "errors": [{"candidate_id": exc.candidate_id, "error": str(exc)}],
            }
        except Exception as exc:  # noqa: BLE001
            with stored.lock:
                stored.state = "pending"
            return {
                "created": [],
                "errors": [
                    {
                        "candidate_id": "",
                        "error": f"The complete material batch was rolled back: {exc}",
                    }
                ],
            }
        with stored.lock:
            stored.state = "consumed"
        return {
            "created": [
                {"candidate_id": candidate_id, "material_id": material_id}
                for candidate_id, material_id in zip(selected_ids, material_ids, strict=True)
            ],
            "errors": [],
        }

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
        full_source_text = sample_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if len(full_source_text) > MAX_MATERIAL_EXTRACTION_TEXT_CHARS:
            raise ValueError(
                f"Material extraction text must be {MAX_MATERIAL_EXTRACTION_TEXT_CHARS:,} characters or fewer."
            )
        model_sample = _sample_text(full_source_text)
        settings = (
            self.material_service.get_ai_settings("author_style_extraction")
            if material_type == "author_style"
            else None
        )
        model = self._resolve_model(model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._material_messages(
                model_sample,
                material_type,
                detail_level,
                name,
                dimensions=settings.dimensions if settings is not None else None,
            ),
        )
        extracted = _parse_json_object(response.text, "Material extraction")
        items = extracted.get("materials")
        if not isinstance(items, list) or not items:
            raise ValueError("Material extraction response must contain a non-empty materials list.")
        shared_source_metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "source_character_count": len(full_source_text),
            "model_sample_character_count": len(model_sample),
            "source_truncated_for_model": len(model_sample) < len(full_source_text),
            "sample_character_count": len(model_sample),
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
            if material_type == "author_style" and settings is not None:
                content = merge_author_style_content(content, settings.dimensions)
            material_ids.append(
                self.material_service.create_material(
                    material_type=material_type,
                    scope=scope,
                    project_id=project_id,
                    name=item_name,
                    description=str(item.get("description") or ""),
                    detail_level=detail_level,
                    raw_text=full_source_text,
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
        dimensions = _dimension_definitions(row["dimensions_json"])
        return CharacterExtractionSettings(
            model_id=row["model_id"],
            detail_level=str(row["detail_level"]),
            custom_requirements=str(row["custom_requirements"]),
            system_prompt=str(row["system_prompt"] or DEFAULT_CHARACTER_SYSTEM_PROMPT),
            dimensions=dimensions,
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
        dimensions = _normalize_dimensions(current.get("dimensions"))
        model_id = current.get("model_id")
        if model_id is not None and self.model_service.get_model(int(model_id)) is None:
            raise ValueError(f"Model not found: {model_id}")
        with session(self.database_path) as connection:
            connection.execute(
                """
                INSERT INTO character_extraction_settings (
                    id, model_id, detail_level, custom_requirements,
                    system_prompt, dimensions_json
                ) VALUES (1, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    model_id = excluded.model_id,
                    detail_level = excluded.detail_level,
                    custom_requirements = excluded.custom_requirements,
                    system_prompt = excluded.system_prompt,
                    dimensions_json = excluded.dimensions_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    model_id,
                    detail_level,
                    str(current["custom_requirements"] or ""),
                    str(current["system_prompt"] or DEFAULT_CHARACTER_SYSTEM_PROMPT),
                    json.dumps(dimensions, ensure_ascii=False),
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
        target_character_name: str,
        detail_level: str | None = None,
        model_id: int | None = None,
        source_metadata: dict[str, Any] | None = None,
    ) -> CharacterExtractionPreview:
        target_name = target_character_name.strip()
        if not target_name:
            raise ValueError("Target character name is required.")
        normalized_text = sample_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not normalized_text:
            raise ValueError("Character extraction text is empty.")
        if len(normalized_text) > MAX_CHARACTER_EXTRACTION_TEXT_CHARS:
            raise ValueError(
                f"Character extraction text must be {MAX_CHARACTER_EXTRACTION_TEXT_CHARS:,} characters or fewer."
            )
        settings = self.get_character_extraction_settings()
        selected_detail = detail_level or settings.detail_level
        full_source_text = normalized_text
        model_sample = _sample_text(full_source_text)
        model = self._resolve_model(model_id if model_id is not None else settings.model_id)
        response = self.ai_client.chat(
            model,
            self.model_service.get_api_key(model.id),
            self._character_messages(model_sample, selected_detail, target_name, settings),
        )
        extracted = _parse_json_object(response.text, "Character extraction")
        if "candidates" in extracted or "characters" in extracted:
            raise ValueError("Character extraction must return one character object, not candidates.")
        if extracted.get("evidence_found") is False:
            raise ValueError(f'The source text does not contain enough evidence for "{target_name}".')
        returned_name = str(extracted.get("name") or "").strip()
        aliases = _string_list(extracted.get("aliases"))
        if returned_name.casefold() != target_name.casefold() and target_name.casefold() not in {
            alias.casefold() for alias in aliases
        }:
            raise ValueError("Character extraction returned a different character than the requested target.")
        metadata = {
            **(source_metadata or {}),
            "source_type": (source_metadata or {}).get("source_type", "paste"),
            "source_character_count": len(full_source_text),
            "model_sample_character_count": len(model_sample),
            "source_truncated_for_model": len(model_sample) < len(full_source_text),
            "sample_character_count": len(model_sample),
            "detail_level": selected_detail,
        }
        import_metadata = {
            "created_by": "ai_character_extraction",
            "model_id": model.id,
            "model_name": model.model_name,
            "token_usage": response.token_usage,
            "elapsed_ms": response.elapsed_ms,
        }
        enabled_dimensions = [item for item in settings.dimensions if item["enabled"]]
        returned_fields = extracted.get("stable_fields")
        if not isinstance(returned_fields, list):
            raise ValueError("Character extraction response must contain stable_fields.")
        returned_by_id: dict[str, dict[str, Any]] = {}
        enabled_ids = {str(item["id"]) for item in enabled_dimensions}
        for field in returned_fields:
            if not isinstance(field, dict):
                raise ValueError("Every stable field must be an object.")
            dimension_id = str(field.get("dimension_id") or field.get("id") or "").strip()
            if dimension_id not in enabled_ids:
                raise ValueError(f"Unexpected character dimension: {dimension_id or '(empty)' }")
            returned_by_id[dimension_id] = field
        stable_fields = [
            {
                "id": str(dimension["id"]),
                "label": str(dimension["label"]),
                "value": str(returned_by_id.get(str(dimension["id"]), {}).get("value") or ""),
                "sort_order": index,
            }
            for index, dimension in enumerate(enabled_dimensions)
        ]
        token = secrets.token_urlsafe(24)
        expires_at_monotonic, expires_at_iso = _preview_expiry(CHARACTER_PREVIEW_TTL_SECONDS)
        source_summary = _extraction_source_summary(metadata)
        with _CHARACTER_PREVIEWS_LOCK:
            _prune_expired_previews(_CHARACTER_PREVIEWS)
            _CHARACTER_PREVIEWS[
                (str(self.database_path.resolve()), token)
            ] = _StoredCharacterPreview(
                expires_at=expires_at_monotonic,
                expires_at_iso=expires_at_iso,
                state="pending",
                source_metadata=metadata,
                source_summary=source_summary,
                import_metadata=import_metadata,
                raw_text=full_source_text,
            )
        return CharacterExtractionPreview(
            preview_token=token,
            expires_at=expires_at_iso,
            character=CharacterExtractionDraft(
                name=target_name,
                aliases=aliases,
                description=str(extracted.get("description") or ""),
                identity=str(extracted.get("identity") or ""),
                age=str(extracted.get("age") or ""),
                stable_fields=stable_fields,
                source_metadata=metadata,
                import_metadata=import_metadata,
                raw_text=full_source_text,
            ),
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
        """Deprecated: previews are drafts and are saved through the normal character API."""
        raise ValueError("Character extraction apply is deprecated; save the edited draft through /api/characters.")
        key = (str(self.database_path.resolve()), preview_token)
        with _CHARACTER_PREVIEWS_LOCK:
            stored = _CHARACTER_PREVIEWS.get(key)
            _prune_expired_previews(_CHARACTER_PREVIEWS)
        if stored is None:
            raise ValueError("Character extraction preview token is invalid.")
        with stored.lock:
            _ensure_preview_can_start_apply(stored, "Character")
            if scope not in {"public", "project"}:
                raise ValueError(f"Unsupported character scope: {scope}")
            if scope == "project" and project_id is None:
                raise ValueError("Project character extraction requires a project.")
            if scope == "project" and category_ids:
                raise ValueError("Project characters cannot belong to public character categories.")
            selected_ids, by_id = _validated_candidate_payloads(
                candidates,
                selected_candidate_ids,
                stored.candidate_ids,
                label="Character",
            )
            prepared: list[dict[str, Any]] = []
            for candidate_id in selected_ids:
                candidate = by_id[candidate_id]
                name = str(candidate.get("name") or "").strip()
                if not name:
                    raise ValueError(f"Character candidate {candidate_id} requires a name.")
                prepared.append(
                    {
                        **candidate,
                        "candidate_id": candidate_id,
                        "name": name,
                        "aliases": _string_list(candidate.get("aliases")),
                        "profile": _object_or_empty(candidate.get("profile")),
                        "custom_fields": _custom_fields(candidate.get("custom_fields")),
                    }
                )
            stored.state = "applying"
        try:
            card_ids = self.anchor_service.create_extracted_character_batch(
                candidates=prepared,
                scope=scope,
                project_id=project_id,
                category_ids=list(dict.fromkeys(category_ids or [])),
                source_metadata=stored.source_metadata,
                import_metadata=stored.import_metadata,
                raw_text=stored.raw_text,
            )
        except CandidateApplyError as exc:
            with stored.lock:
                stored.state = "pending"
            return {
                "created": [],
                "errors": [{"candidate_id": exc.candidate_id, "error": str(exc)}],
            }
        except Exception as exc:  # noqa: BLE001
            with stored.lock:
                stored.state = "pending"
            return {
                "created": [],
                "errors": [
                    {
                        "candidate_id": "",
                        "error": f"The complete character batch was rolled back: {exc}",
                    }
                ],
            }
        with stored.lock:
            stored.state = "consumed"
        return {
            "created": [
                {"candidate_id": candidate_id, "card_id": card_id}
                for candidate_id, card_id in zip(selected_ids, card_ids, strict=True)
            ],
            "errors": [],
        }

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
        target_name = (name or "").strip()
        if not target_name:
            raise ValueError("Target character name is required.")
        preview = self.preview_characters_from_text(
            sample_text,
            target_character_name=target_name,
            detail_level=detail_level,
            model_id=model_id,
            source_metadata=source_metadata,
        )
        draft = preview.character
        card_id = self.anchor_service.create_character_card(
            name=draft.name,
            aliases=draft.aliases,
            description=draft.description,
            identity=draft.identity,
            age=draft.age,
            stable_fields=draft.stable_fields,
            source_metadata=draft.source_metadata,
            import_metadata=draft.import_metadata,
            raw_text=draft.raw_text,
            scope=scope,
            project_id=project_id,
        )
        return [card_id]

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
        name: str,
        settings: CharacterExtractionSettings | None = None,
    ) -> list[dict[str, str]]:
        settings = settings or self.get_character_extraction_settings()
        target_name = name.strip()
        enabled_dimensions = [item for item in settings.dimensions if item["enabled"]]
        dimensions_text = "\n".join(
            f'- {item["id"]} ({item["label"]}): {item["instruction"] or "No additional instruction."}'
            for item in enabled_dimensions
        )
        stable_schema = [
            {"dimension_id": item["id"], "label": item["label"], "value": ""}
            for item in enabled_dimensions
        ]
        return [
            {
                "role": "system",
                "content": settings.system_prompt or DEFAULT_CHARACTER_SYSTEM_PROMPT,
            },
            {
                "role": "user",
                "content": (
                    f'Only extract the character named "{target_name}". Other people may only be used as relationship evidence for the target; never create another character.\n'
                    f"Detail level: {detail_level}\n"
                    "Enabled stable dimensions:\n"
                    f"{dimensions_text}\n\n"
                    "Return exactly one JSON object and no Markdown, code fence, explanation, or text outside JSON. "
                    "The object must contain only: evidence_found, name, aliases, identity, age, description, stable_fields. "
                    f"stable_fields must follow this schema and order: {json.dumps(stable_schema, ensure_ascii=False)}.\n"
                    "If a field has no direct evidence, return an empty string or empty array. Never guess for completeness. "
                    "Set evidence_found=false if the named character cannot be found; never switch to another person. "
                    f'The name field must identify "{target_name}" and aliases for the same person must be merged.\n'
                    f"Additional requirements: {settings.custom_requirements or 'None'}\n\n"
                    f"Source text:\n{sample_text}"
                ),
            },
        ]

    @staticmethod
    def _material_preview_messages(
        sample_text: str,
        *,
        task_type: str,
        material_type: str,
        detail_level: str,
        name: str | None,
        system_prompt: str,
        base_instruction: str,
        dimensions: tuple[dict[str, str], ...],
        extra_requirements: str,
    ) -> list[dict[str, str]]:
        requested_name = name.strip() if name and name.strip() else "derive from source"
        dimension_text = "\n\n".join(
            f"{index}. {item['name']}\nID: {item['id']}\n提取要求：{item['requirement']}"
            for index, item in enumerate(dimensions, 1)
        )
        output_protocol = (
            '{"materials":[{"name":"","description":"","content":{"schema_version":1,'
            '"overall_style":"","dimensions":[{"id":"输入维度 id",'
            '"analysis":"","features":[],"examples":[]}]},"evidence_summary":"",'
            '"confidence":0.0,"warnings":[]}]}'
        )
        separation_rule = (
            "只创建一份完整作者风格档案。必须单独返回顶层 overall_style，不能把它放进 dimensions。"
            "dimensions 必须使用输入的稳定 ID，不得自行创建或修改维度 ID。"
            "维度名称 name 与提取要求 requirement 已由系统配置提供，不属于模型输出；"
            "每个维度只返回 id、analysis、features、examples，不返回 name 或 requirement。"
            "examples 只能逐字引用输入文本，不得包含来源位置字段。"
            "不返回 summary。作品名称由系统根据来源文件设置，不是 AI 输出。"
        )
        return [
            {
                "role": "system",
                "content": (
                    f"{system_prompt}\n\n{separation_rule}\n"
                    "只返回严格 JSON。缺少依据时保持空值或说明样本不足，不得编造。"
                ),
            },
            {
                "role": "user",
                "content": (
                    f"任务：{task_type}\n素材类型：{material_type}\n建议名称：{requested_name}\n细化程度：{detail_level}\n\n"
                    f"任务说明：\n{base_instruction}\n\n分析维度：\n{dimension_text}\n\n"
                    f"附加要求：\n{extra_requirements or '无'}\n\n输出协议：\n{output_protocol}\n\n"
                    f"Source text:\n{sample_text}"
                ),
            },
        ]

    @staticmethod
    def _material_messages(
        sample_text: str,
        material_type: str,
        detail_level: str,
        name: str | None,
        dimensions: tuple[dict[str, str], ...] | None = None,
    ) -> list[dict[str, str]]:
        configured_dimensions = dimensions or ()
        dimensions_text = "\n\n".join(
            f"{index}. {item['name']}\nID: {item['id']}\n提取要求：{item['requirement']}"
            for index, item in enumerate(configured_dimensions, 1)
        )
        dimensions_text = dimensions_text or "\n".join(
            f"- {item}" for item in MATERIAL_DIMENSIONS[material_type]
        )
        requested_name = name.strip() if name and name.strip() else "derive from source"
        shape = (
            "author_style content keys: overall_style, dimensions[{id,analysis,features[],examples[]}]. "
            "overall_style is a separate top-level field, not a dimension; do not return summary. "
            "Each dimension returns only id, analysis, features, and examples. "
            "Dimension name and requirement come from system configuration and are not model output."
        )
        return [
            {
                "role": "system",
                "content": (
                    f"[RUSTY NATIVE RULES: rusty.native.material.{material_type}.v1]\n"
                    "Extract reusable writing resources from prose. Return strict JSON only. "
                    "Do not invent unsupported facts and do not return Markdown. "
                    "For author_style, overall_style must be a separate top-level field and must summarize "
                    "the stable macro-level writing rules from the sample; it is not a dimension."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Material type: {material_type}\n"
                    f"Suggested name: {requested_name}\n"
                    f"Detail level: {detail_level}\n"
                    "Required dimensions:\n"
                    f"{dimensions_text}\n\n"
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


def _preview_expiry(ttl_seconds: int) -> tuple[float, str]:
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
    return time.monotonic() + ttl_seconds, expires_at.isoformat()


def _ensure_preview_can_start_apply(stored: Any, label: str) -> None:
    if stored.state == "consumed":
        raise ValueError(f"{label} extraction preview token was already used.")
    if stored.state == "applying":
        raise ValueError(f"{label} extraction preview token is currently being applied.")
    if stored.expires_at <= time.monotonic():
        raise ValueError(f"{label} extraction preview token has expired.")


def _validated_candidate_payloads(
    candidates: list[dict[str, Any]],
    selected_candidate_ids: list[str],
    expected_candidate_ids: set[str],
    *,
    label: str,
) -> tuple[list[str], dict[str, dict[str, Any]]]:
    if not candidates:
        raise ValueError(f"{label} candidate payload is empty or tampered.")
    payload_ids: list[str] = []
    by_id: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            raise ValueError(f"{label} candidate payload must contain objects.")
        candidate_id = str(candidate.get("candidate_id") or "").strip()
        if not candidate_id:
            raise ValueError(f"{label} candidate_id is required.")
        if candidate_id in by_id:
            raise ValueError(f"{label} candidate payload contains duplicate candidate_id: {candidate_id}.")
        payload_ids.append(candidate_id)
        by_id[candidate_id] = candidate
    if set(payload_ids) != expected_candidate_ids:
        missing = sorted(expected_candidate_ids - set(payload_ids))
        forged = sorted(set(payload_ids) - expected_candidate_ids)
        details = []
        if missing:
            details.append(f"missing={','.join(missing)}")
        if forged:
            details.append(f"unknown={','.join(forged)}")
        raise ValueError(f"{label} candidate payload does not match preview ({'; '.join(details)}).")
    selected_ids = [str(value).strip() for value in selected_candidate_ids]
    if not selected_ids:
        raise ValueError(f"At least one {label.lower()} candidate must be selected.")
    if any(not value for value in selected_ids):
        raise ValueError(f"{label} selected candidate_id is required.")
    if len(selected_ids) != len(set(selected_ids)):
        raise ValueError(f"{label} selection contains duplicate candidate_id.")
    if not set(selected_ids).issubset(expected_candidate_ids):
        raise ValueError(f"{label} selection contains a candidate not present in the preview.")
    return selected_ids, by_id


def _structured_evidence(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for item in value:
        if isinstance(item, dict):
            result.append(dict(item))
        elif str(item).strip():
            result.append({"summary": str(item).strip()})
    return result


def _confidence(value: Any) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return 0.0


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


def _material_extraction_source_summary(metadata: dict[str, Any]) -> dict[str, Any]:
    document_id = _positive_int_or_none(metadata.get("document_id"))
    chapter_id = _positive_int_or_none(metadata.get("chapter_id"))
    document_title = str(metadata.get("document_title") or "").strip()
    chapter_title = str(metadata.get("chapter_title") or "").strip()
    if document_id is not None or metadata.get("source_type") == "document":
        label = f"《{document_title}》" if document_title else "文档选区"
        if chapter_title:
            label += f" · {chapter_title}"
        return {
            "kind": "document_selection",
            "label": label,
            "document_id": document_id,
            "chapter_id": chapter_id,
            "project_id": _positive_int_or_none(metadata.get("project_id")),
        }
    if metadata.get("source_type") == "file":
        filename = (
            metadata.get("file_name")
            or metadata.get("source_file_name")
            or metadata.get("source_path")
            or "本地文件"
        )
        return {
            "kind": "file_import",
            "label": f"文件 {Path(str(filename)).name}",
        }
    if metadata.get("source_type") == "project" or metadata.get("project_id") is not None:
        project_name = metadata.get("project_name") or metadata.get("source_project_name")
        return {
            "kind": "project_selection",
            "label": f"工程“{project_name}”选区" if project_name else "工程选区",
            "project_id": _positive_int_or_none(
                metadata.get("project_id") or metadata.get("source_project_id")
            ),
        }
    return {"kind": "pasted_text", "label": "粘贴文本"}


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


def _dimension_definitions(value: Any) -> tuple[dict[str, Any], ...]:
    try:
        parsed = json.loads(str(value or "[]")) if not isinstance(value, (list, tuple)) else value
    except (TypeError, ValueError):
        parsed = []
    return tuple(_normalize_dimensions(parsed or DEFAULT_CHARACTER_DIMENSIONS))


def _normalize_dimensions(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, (list, tuple)):
        value = DEFAULT_CHARACTER_DIMENSIONS
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"Character dimension {index + 1} must be an object.")
        dimension_id = str(item.get("id") or "").strip()
        label = " ".join(str(item.get("label") or "").strip().split())
        if not dimension_id or not label:
            raise ValueError(f"Character dimension {index + 1} requires an id and label.")
        if dimension_id in seen:
            raise ValueError(f"Duplicate character dimension id: {dimension_id}")
        seen.add(dimension_id)
        normalized.append({
            "id": dimension_id,
            "label": label,
            "instruction": str(item.get("instruction") or "").strip(),
            "sort_order": len(normalized),
            "enabled": bool(item.get("enabled", True)),
            "is_default": bool(item.get("is_default", False)),
        })
    return normalized


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
        filename = str(
            metadata.get("file_name")
            or metadata.get("source_file_name")
            or metadata.get("source_path")
            or "本地文件"
        )
        return {"kind": "file_import", "label": f"文件 {Path(filename).name}"}
    if source_type == "project" or metadata.get("project_id") is not None:
        project_name = metadata.get("project_name") or metadata.get("source_project_name")
        return {
            "kind": "project_selection",
            "label": f"工程“{project_name}”" if project_name else "工程选区",
            "project_id": _positive_int_or_none(
                metadata.get("project_id") or metadata.get("source_project_id")
            ),
        }
    return {"kind": "ai_extraction", "label": "AI 文本提取"}


def _positive_int_or_none(value: Any) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None
