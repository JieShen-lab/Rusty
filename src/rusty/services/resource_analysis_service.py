from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rusty.services.anchor_service import AnchorService, CharacterCard
from rusty.services.material_service import Material, MaterialService
from rusty.db import default_database_path
from rusty.services.structured_model_service import StructuredModelResult, StructuredModelService


AUTHOR_STYLE_SCHEMA = {
    "type": "object",
    "required": ["summary", "dimensions"],
}
PLOT_SKELETON_SCHEMA = {
    "type": "object",
    "required": [
        "summary",
        "event_nodes",
        "entry_conditions",
        "exit_state",
        "character_impacts",
        "open_threads",
    ],
}
CHARACTER_SCHEMA = {
    "type": "object",
    "required": ["name", "identity", "age", "setting", "custom_fields"],
}


class ResourceAnalysisService:
    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.material_service = MaterialService(self.database_path)
        self.anchor_service = AnchorService(self.database_path)
        self.model_service = structured_model_service or StructuredModelService(self.database_path)

    def analyze_material(self, material_id: int, *, model_id: int | None = None) -> tuple[Material, StructuredModelResult]:
        proposal = self.propose_material_analysis(material_id, model_id=model_id)
        result = proposal.pop("_result")
        self.apply_material_analysis(
            material_id,
            content=proposal["proposal"],
            model_id=result.model_id,
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
        schema = AUTHOR_STYLE_SCHEMA if material.material_type == "author_style" else PLOT_SKELETON_SCHEMA
        result = self.model_service.run(
            invocation_kind="material_analysis",
            stage=material.material_type,
            messages=_material_messages(material),
            output_schema=schema,
            validator=(
                _validate_author_style
                if material.material_type == "author_style"
                else _validate_plot_skeleton
            ),
            model_id=model_id,
            project_id=material.project_id,
            resource_type="material",
            resource_id=material.id,
        )
        return {
            "material_id": material.id,
            "model_id": result.model_id,
            "invocation_id": result.invocation_id,
            "proposal": result.value,
            "existing": json.loads(material.content_json),
            "_result": result,
        }

    def apply_material_analysis(
        self,
        material_id: int,
        *,
        content: dict[str, Any],
        model_id: int,
        invocation_id: int,
    ) -> Material:
        self.material_service.analyze_material(
            material_id,
            content=content,
            model_id=model_id,
            invocation_id=invocation_id,
        )
        updated = self.material_service.get_material(material_id)
        if updated is None:
            raise RuntimeError("Material disappeared after analysis.")
        return updated

    def propose_character_analysis(
        self,
        card_id: int,
        *,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        card = self.anchor_service.get_character_card(card_id)
        if card is None:
            raise FileNotFoundError(f"Character card not found: {card_id}")
        result = self.model_service.run(
            invocation_kind="character_analysis",
            stage="character_card",
            messages=_character_messages(card),
            output_schema=CHARACTER_SCHEMA,
            validator=_validate_character,
            model_id=model_id,
            project_id=card.project_id,
            resource_type="character",
            resource_id=card.id,
        )
        merged, conflicts = _merge_character(card, result.value)
        return {
            "invocation_id": result.invocation_id,
            "model_id": result.model_id,
            "proposal": result.value,
            "merged": merged,
            "conflicts": conflicts,
        }


def _material_messages(material: Material) -> list[dict[str, str]]:
    tags = " / ".join(material.tags) or "none"
    if material.material_type == "author_style":
        role = (
            "Analyze one complete author style profile. Describe concrete writing methods and "
            "quote examples exactly from the source. Style must not introduce story facts."
        )
        fields = "summary, dimensions[{id,name,requirement,analysis,features[],examples[]}]"
    else:
        role = (
            "Analyze a plot skeleton that may introduce new story events. Preserve causal order "
            "and explicitly mark required nodes."
        )
        fields = (
            "summary, event_nodes[{id,event,causes[],results[],characters[],required}], "
            "entry_conditions[], exit_state{}, character_impacts{}, open_threads[]"
        )
    return [
        {
            "role": "system",
            "content": (
                f"{role}\nReturn strict JSON only with fields: {fields}. "
                "Do not infer unsupported facts."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Name: {material.name}\n"
                f"Existing description: {material.description}\n"
                f"Tags: {tags}\n\n"
                f"Original source text:\n{material.raw_text}"
            ),
        },
    ]


def _character_messages(card: CharacterCard) -> list[dict[str, str]]:
    existing = {
        "name": card.name,
        "identity": card.identity,
        "age": card.age,
        "setting": card.setting_text,
        "custom_fields": card.custom_fields,
    }
    return [
        {
            "role": "system",
            "content": (
                "Extract one reusable character card from evidence. Return strict JSON only with "
                "name, identity, age, setting, custom_fields[{label,value}]. "
                "Use empty strings for unsupported fixed fields and do not overwrite user facts."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Existing card:\n{json.dumps(existing, ensure_ascii=False)}\n\n"
                f"Source text:\n{card.raw_text}"
            ),
        },
    ]


def _validate_author_style(value: dict[str, Any]) -> dict[str, Any]:
    required = tuple(AUTHOR_STYLE_SCHEMA["required"])
    _require_keys(value, required)
    if not isinstance(value["dimensions"], list):
        raise ValueError("dimensions must be an array.")
    dimensions: list[dict[str, Any]] = []
    for index, item in enumerate(value["dimensions"]):
        if not isinstance(item, dict) or not str(item.get("id") or "").strip():
            raise ValueError(f"dimensions[{index}] requires a stable id.")
        dimensions.append({
            "id": str(item["id"]).strip(),
            "name": str(item.get("name") or "").strip(),
            "requirement": str(item.get("requirement") or "").strip(),
            "analysis": str(item.get("analysis") or "").strip(),
            "features": _string_list(item.get("features", [])),
            "examples": _string_list(item.get("examples", [])),
        })
    return {
        "summary": _string(value["summary"]),
        "dimensions": dimensions,
    }


def _validate_plot_skeleton(value: dict[str, Any]) -> dict[str, Any]:
    required = tuple(PLOT_SKELETON_SCHEMA["required"])
    _require_keys(value, required)
    nodes = value["event_nodes"]
    if not isinstance(nodes, list) or not nodes:
        raise ValueError("event_nodes must be a non-empty array.")
    normalized_nodes = []
    for index, item in enumerate(nodes):
        if not isinstance(item, dict) or not str(item.get("event") or "").strip():
            raise ValueError(f"event_nodes[{index}] requires an event.")
        normalized_nodes.append(
            {
                "id": str(item.get("id") or f"event-{index + 1}"),
                "event": str(item["event"]).strip(),
                "causes": _string_list(item.get("causes", [])),
                "results": _string_list(item.get("results", [])),
                "characters": _string_list(item.get("characters", [])),
                "required": bool(item.get("required", True)),
            }
        )
    if not isinstance(value["exit_state"], dict) or not isinstance(value["character_impacts"], dict):
        raise ValueError("exit_state and character_impacts must be objects.")
    return {
        "summary": _string(value["summary"]),
        "event_nodes": normalized_nodes,
        "entry_conditions": _string_list(value["entry_conditions"]),
        "exit_state": value["exit_state"],
        "character_impacts": value["character_impacts"],
        "open_threads": _string_list(value["open_threads"]),
    }


def _validate_character(value: dict[str, Any]) -> dict[str, Any]:
    _require_keys(value, tuple(CHARACTER_SCHEMA["required"]))
    fields = value["custom_fields"]
    if not isinstance(fields, list):
        raise ValueError("custom_fields must be an array.")
    normalized = []
    seen: set[str] = set()
    for index, item in enumerate(fields):
        if not isinstance(item, dict):
            raise ValueError(f"custom_fields[{index}] must be an object.")
        label = _string(item.get("label"))
        if not label:
            raise ValueError(f"custom_fields[{index}].label is required.")
        key = " ".join(label.split()).casefold()
        if key in seen:
            raise ValueError(f"Duplicate custom field: {label}")
        seen.add(key)
        normalized.append(
            {
                "id": str(item.get("id") or f"ai-{index + 1}"),
                "label": label,
                "value": _string(item.get("value")),
                "sort_order": index,
            }
        )
    return {
        "name": _string(value["name"]),
        "identity": _string(value["identity"]),
        "age": _string(value["age"]),
        "setting_text": _string(value["setting"]),
        "custom_fields": normalized,
    }


def _merge_character(card: CharacterCard, proposal: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, str]]]:
    merged = {
        "name": card.name or proposal["name"],
        "identity": card.identity or proposal["identity"],
        "age": card.age or proposal["age"],
        "setting_text": card.setting_text or proposal["setting_text"],
        "custom_fields": [dict(item) for item in card.custom_fields],
    }
    conflicts: list[dict[str, str]] = []
    for key in ("name", "identity", "age", "setting_text"):
        current = str(getattr(card, "setting_text" if key == "setting_text" else key) or "")
        incoming = str(proposal[key] or "")
        if current and incoming and current != incoming:
            conflicts.append({"field": key, "existing": current, "proposed": incoming})
    by_label = {
        " ".join(str(item.get("label") or "").split()).casefold(): item
        for item in merged["custom_fields"]
    }
    for field in proposal["custom_fields"]:
        key = " ".join(str(field["label"]).split()).casefold()
        current = by_label.get(key)
        if current is None:
            merged["custom_fields"].append(field)
        elif str(current.get("value") or "") != str(field.get("value") or ""):
            conflicts.append(
                {
                    "field": f"custom:{field['label']}",
                    "existing": str(current.get("value") or ""),
                    "proposed": str(field.get("value") or ""),
                }
            )
    for index, field in enumerate(merged["custom_fields"]):
        field["sort_order"] = index
    return merged, conflicts


def _require_keys(value: dict[str, Any], required: tuple[str, ...]) -> None:
    missing = [key for key in required if key not in value]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")


def _string(value: Any) -> str:
    return str(value or "").strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        raise ValueError("Expected an array.")
    return [str(item).strip() for item in value if str(item).strip()]
