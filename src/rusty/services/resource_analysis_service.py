from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from rusty.db import default_database_path
from rusty.services.material_service import (
    Material,
    MaterialService,
    merge_author_style_content,
    normalize_material_content,
)
from rusty.services.structured_model_service import StructuredModelResult, StructuredModelService


logger = logging.getLogger(__name__)

AUTHOR_STYLE_SCHEMA = {
    "type": "object",
    "required": ["overall_style", "dimensions"],
    "additionalProperties": False,
    "properties": {
        "overall_style": {"type": "string"},
        "dimensions": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "analysis", "features", "examples"],
                "additionalProperties": False,
                "properties": {
                    "id": {"type": "string"},
                    "analysis": {"type": "string"},
                    "features": {"type": "array", "items": {"type": "string"}},
                    "examples": {"type": "array", "items": {"type": "string"}},
                },
            },
        },
    },
}


class ResourceAnalysisService:
    """AI analysis for the sole reusable asset type: author styles."""

    def __init__(
        self, database_path: str | Path | None = None, *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.material_service = MaterialService(self.database_path)
        self.model_service = structured_model_service or StructuredModelService(self.database_path)

    def analyze_material(self, material_id: int, *, model_id: int | None = None) -> tuple[Material, StructuredModelResult]:
        proposal = self.propose_material_analysis(material_id, model_id=model_id)
        result = proposal.pop("_result")
        self.apply_material_analysis(
            material_id, content=proposal["proposal"], model_id=result.model_id,
            invocation_id=result.invocation_id,
        )
        updated = self.material_service.get_material(material_id)
        if updated is None:
            raise RuntimeError("Material disappeared after analysis.")
        return updated, result

    def propose_material_analysis(self, material_id: int, *, model_id: int | None = None) -> dict[str, Any]:
        material = self.material_service.get_material(material_id)
        if material is None:
            raise FileNotFoundError(f"Material not found: {material_id}")
        if material.material_type != "author_style":
            raise ValueError("Only author_style materials can be analyzed.")
        settings = self.material_service.get_ai_settings("author_style_extraction")
        result = self.model_service.run(
            invocation_kind="material_analysis", stage="author_style",
            messages=_material_messages(material, settings.dimensions), output_schema=AUTHOR_STYLE_SCHEMA,
            validator=lambda value: _validate_author_style(value, settings.dimensions),
            model_id=model_id, project_id=material.project_id,
            resource_type="material", resource_id=material.id,
        )
        existing = normalize_material_content("author_style", json.loads(material.content_json))
        return {
            "material_id": material.id, "model_id": result.model_id,
            "invocation_id": result.invocation_id, "proposal": result.value,
            "existing": existing, "_result": result,
        }

    def apply_material_analysis(
        self, material_id: int, *, content: dict[str, Any], model_id: int, invocation_id: int,
    ) -> Material:
        self.material_service.analyze_material(
            material_id, content=content, model_id=model_id, invocation_id=invocation_id,
        )
        updated = self.material_service.get_material(material_id)
        if updated is None:
            raise RuntimeError("Material disappeared after analysis.")
        return updated


def _material_messages(
    material: Material,
    dimensions: tuple[dict[str, str], ...],
) -> list[dict[str, str]]:
    configured_dimensions = "\n\n".join(
        f"{index}. {item['name']}\nID: {item['id']}\n提取要求：{item['requirement']}"
        for index, item in enumerate(dimensions, 1)
    )
    return [
        {"role": "system", "content": (
            "Analyze one complete author style profile. Describe concrete writing methods and "
            "quote examples exactly from the source. Style must not introduce story facts. "
            "First produce a separate top-level overall_style describing the stable macro-level writing rules "
            "for narrative organization, viewpoint, information flow, sentence and paragraph rhythm, dialogue and "
            "description balance, emotion, scene transitions, information density, and overall expression. "
            "It must be grounded in the sample, not author identity or external knowledge, not a mechanical "
            "concatenation of dimensions, and not a vague literary evaluation. "
            "Return strict JSON with overall_style and dimensions. Each dimension must contain only id, analysis, "
            "features, and examples. Use the configured stable ID exactly; do not return name or requirement. "
            "Do not return summary."
        )},
        {"role": "user", "content": (
            f"Name: {material.name}\nExisting description: {material.description}"
            f"\n\nConfigured dimensions:\n{configured_dimensions or '无'}"
            f"\n\nOriginal source text:\n{material.raw_text}"
        )},
    ]


def _validate_author_style(
    value: dict[str, Any],
    configured_dimensions: tuple[dict[str, str], ...],
) -> dict[str, Any]:
    if "dimensions" not in value:
        raise ValueError("Missing required fields: dimensions")
    overall_style = str(value.get("overall_style") or "").strip()
    if not overall_style:
        logger.warning("Author style analysis response omitted overall_style; preserving an empty field.")
    if not isinstance(value["dimensions"], list):
        raise ValueError("dimensions must be an array.")
    for index, item in enumerate(value["dimensions"]):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError(f"dimensions[{index}] requires a stable id.")
        _string_list(item.get("features", []))
        _string_list(item.get("examples", []))
    return merge_author_style_content(
        {"overall_style": overall_style, "dimensions": value["dimensions"]},
        configured_dimensions,
    )


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Expected an array.")
    return [str(item).strip() for item in value if str(item).strip()]
