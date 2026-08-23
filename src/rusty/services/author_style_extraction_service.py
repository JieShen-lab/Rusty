from __future__ import annotations

import secrets
import threading
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from rusty.db import default_database_path
from rusty.services.ai_request_executor import AIRequestExecutor
from rusty.services.material_service import MaterialService, merge_author_style_content
from rusty.services.project_service import ProjectService
from rusty.services.structured_model_service import StructuredModelService


AUTHOR_STYLE_SCHEMA = {
    "type": "object",
    "required": ["overall_style", "dimensions"],
    "properties": {
        "overall_style": {"type": "string"},
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "analysis", "features", "examples"],
            },
        },
    },
}
PREVIEW_TTL_SECONDS = 15 * 60


@dataclass(frozen=True)
class AuthorStyleExtractionResult:
    overall_style: str
    dimensions: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "work": "",
            "overall_style": self.overall_style,
            "dimensions": [dict(item) for item in self.dimensions],
        }


@dataclass(frozen=True)
class AuthorStyleCandidate:
    candidate_id: str
    name: str
    description: str
    content: dict[str, Any]


@dataclass(frozen=True)
class AuthorStylePreview:
    preview_token: str
    candidates: tuple[AuthorStyleCandidate, ...]


@dataclass
class _StoredPreview:
    expires_at: float
    candidate_id: str
    raw_text: str
    source_metadata: dict[str, Any]
    settings_snapshot: dict[str, Any]
    consumed: bool = False


_PREVIEWS: dict[tuple[str, str], _StoredPreview] = {}
_PREVIEWS_LOCK = threading.Lock()


class AuthorStyleExtractionService:
    """The single author-style prompt, model, parser, merge, and normalization pipeline."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        executor: AIRequestExecutor | None = None,
        ai_client: Any | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.executor = executor or AIRequestExecutor(self.database_path, ai_client=ai_client)
        self.structured = StructuredModelService(self.database_path, executor=self.executor)
        self.materials = MaterialService(self.database_path)
        self.projects = ProjectService(self.database_path)

    def extract(self, sample_text: str, *, model_id: int | None = None) -> AuthorStyleExtractionResult:
        source = sample_text.replace("\r\n", "\n").replace("\r", "\n").strip()
        if not source:
            raise ValueError("Author style extraction text is empty.")
        settings = self.materials.get_ai_settings("author_style_extraction")
        messages = [{"role": "user", "content": self._build_task_prompt(source, settings)}]
        result = self.structured.run(
            messages=messages,
            output_schema=AUTHOR_STYLE_SCHEMA,
            validator=lambda value: self._validate_result(value, settings.dimensions),
            model_id=model_id if model_id is not None else settings.model_id,
        )
        value = result.value
        return AuthorStyleExtractionResult(
            overall_style=str(value["overall_style"]),
            dimensions=tuple(dict(item) for item in value["dimensions"]),
        )

    def preview_from_file(
        self,
        source_path: str | Path,
        *,
        name: str,
        model_id: int | None = None,
    ) -> AuthorStylePreview:
        book = self.projects.preview_book(source_path)
        source = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters).strip()
        extracted = self.extract(source, model_id=model_id)
        settings = self.materials.get_ai_settings("author_style_extraction")
        candidate_id = secrets.token_hex(8)
        token = secrets.token_urlsafe(24)
        expires = time.monotonic() + PREVIEW_TTL_SECONDS
        source_metadata = {
            "source_type": "file",
            "source_file_name": book.source_path.name,
            "source_path": str(book.source_path),
            "source_format": book.source_format,
            "book_title": book.title,
        }
        settings_snapshot = asdict(settings)
        key = (str(self.database_path.resolve()), token)
        with _PREVIEWS_LOCK:
            self._prune_previews()
            _PREVIEWS[key] = _StoredPreview(
                expires_at=expires,
                candidate_id=candidate_id,
                raw_text=source,
                source_metadata=source_metadata,
                settings_snapshot=settings_snapshot,
            )
        return AuthorStylePreview(
            preview_token=token,
            candidates=(AuthorStyleCandidate(
                candidate_id=candidate_id,
                name=name.strip(),
                description="",
                content=extracted.to_dict(),
            ),),
        )

    def apply_preview(
        self,
        *,
        preview_token: str,
        candidates: list[dict[str, Any]],
        selected_candidate_ids: list[str],
    ) -> dict[str, list[dict[str, Any]]]:
        key = (str(self.database_path.resolve()), preview_token)
        with _PREVIEWS_LOCK:
            self._prune_previews()
            stored = _PREVIEWS.get(key)
            if stored is None or stored.consumed:
                raise ValueError("Author style preview token is invalid or already used.")
            if selected_candidate_ids != [stored.candidate_id]:
                raise ValueError("Exactly the previewed author style candidate must be selected.")
            candidate = next(
                (item for item in candidates if str(item.get("candidate_id")) == stored.candidate_id),
                None,
            )
            if candidate is None:
                raise ValueError("The selected author style candidate is missing.")
            stored.consumed = True
        try:
            material_id = self.materials.create_material(
                name=str(candidate.get("name") or "").strip(),
                description=str(candidate.get("description") or ""),
                detail_level=str(stored.settings_snapshot["detail_level"]),
                raw_text=stored.raw_text,
                content=merge_author_style_content(
                    candidate.get("content"), stored.settings_snapshot["dimensions"]
                ),
                source_metadata=stored.source_metadata,
            )
        except Exception:
            with _PREVIEWS_LOCK:
                stored.consumed = False
            raise
        return {
            "created": [{"candidate_id": stored.candidate_id, "material_id": material_id}],
            "errors": [],
        }

    @staticmethod
    def _build_task_prompt(sample_text: str, settings: Any) -> str:
        dimensions = "\n\n".join(
            f"{index}. {item['name']}\nID: {item['id']}\n提取要求：{item['requirement']}"
            for index, item in enumerate(settings.dimensions, 1)
        )
        return (
            "[TASK: AUTHOR STYLE EXTRACTION]\n"
            f"细化程度：{settings.detail_level}\n\n"
            f"[EXTRACTION RULES]\n{settings.extraction_rules}\n\n"
            f"[BASE INSTRUCTION]\n{settings.base_instruction}\n\n"
            f"[DIMENSIONS]\n{dimensions or '无'}\n\n"
            f"[EXTRA REQUIREMENTS]\n{settings.extra_requirements or '无'}\n\n"
            "[OUTPUT CONTRACT]\n"
            "Return one JSON object with overall_style and dimensions. Each dimension must contain "
            "only id, analysis, features, and examples. Use the configured stable IDs. Do not return "
            "name, requirement, summary, author biography, or unsupported facts. examples must be exact excerpts.\n\n"
            f"[COMPLETE SAMPLE TEXT]\n{sample_text}"
        )

    @staticmethod
    def _validate_result(value: dict[str, Any], dimensions: tuple[dict[str, str], ...]) -> dict[str, Any]:
        overall_style = value.get("overall_style")
        if not isinstance(overall_style, str):
            raise ValueError("overall_style must be a string.")
        raw_dimensions = value.get("dimensions")
        if not isinstance(raw_dimensions, list):
            raise ValueError("dimensions must be an array.")
        returned: dict[str, dict[str, Any]] = {}
        for item in raw_dimensions:
            if not isinstance(item, dict):
                raise ValueError("Every dimension result must be an object.")
            dimension_id = str(item.get("id") or "").strip()
            if dimension_id and dimension_id not in returned:
                returned[dimension_id] = item
        normalized: list[dict[str, Any]] = []
        for configured in dimensions:
            item = returned.get(str(configured["id"]), {})
            normalized.append({
                "id": str(configured["id"]),
                "name": str(configured["name"]),
                "analysis": str(item.get("analysis") or "").strip(),
                "features": AuthorStyleExtractionService._strings(item.get("features")),
                "examples": AuthorStyleExtractionService._strings(item.get("examples")),
            })
        return {"overall_style": overall_style.strip(), "dimensions": normalized}

    @staticmethod
    def _strings(value: Any) -> list[str]:
        return [str(item).strip() for item in value if str(item).strip()] if isinstance(value, list) else []

    @staticmethod
    def _prune_previews() -> None:
        now = time.monotonic()
        for key in [key for key, value in _PREVIEWS.items() if value.expires_at <= now]:
            _PREVIEWS.pop(key, None)
