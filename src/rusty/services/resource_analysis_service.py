from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.db import default_database_path
from rusty.services.material_service import Material, MaterialService
from rusty.services.structured_model_service import StructuredModelResult, StructuredModelService


AUTHOR_STYLE_SCHEMA = {"type": "object", "required": ["summary", "dimensions"]}


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
        result = self.model_service.run(
            invocation_kind="material_analysis", stage="author_style",
            messages=_material_messages(material), output_schema=AUTHOR_STYLE_SCHEMA,
            validator=_validate_author_style, model_id=model_id, project_id=material.project_id,
            resource_type="material", resource_id=material.id,
        )
        return {
            "material_id": material.id, "model_id": result.model_id,
            "invocation_id": result.invocation_id, "proposal": result.value,
            "existing": json.loads(material.content_json), "_result": result,
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


def _material_messages(material: Material) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": (
            "Analyze one complete author style profile. Describe concrete writing methods and "
            "quote examples exactly from the source. Style must not introduce story facts. "
            "Return strict JSON with summary and dimensions[{id,name,requirement,analysis,features[],examples[]}]."
        )},
        {"role": "user", "content": (
            f"Name: {material.name}\nExisting description: {material.description}\n"
            f"Tags: {' / '.join(material.tags) or 'none'}\n\nOriginal source text:\n{material.raw_text}"
        )},
    ]


def _validate_author_style(value: dict[str, Any]) -> dict[str, Any]:
    if "summary" not in value or "dimensions" not in value:
        raise ValueError("Missing required fields: summary, dimensions")
    if not isinstance(value["dimensions"], list):
        raise ValueError("dimensions must be an array.")
    dimensions: list[dict[str, Any]] = []
    for index, item in enumerate(value["dimensions"]):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError(f"dimensions[{index}] requires a stable id.")
        dimensions.append({
            "id": str(item["id"]).strip(), "name": str(item.get("name") or "").strip(),
            "requirement": str(item.get("requirement") or "").strip(),
            "analysis": str(item.get("analysis") or "").strip(),
            "features": _string_list(item.get("features", [])),
            "examples": _string_list(item.get("examples", [])),
        })
    return {"summary": str(value["summary"] or "").strip(), "dimensions": dimensions}


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Expected an array.")
    return [str(item).strip() for item in value if str(item).strip()]
