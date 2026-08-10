from __future__ import annotations

from copy import deepcopy
from typing import Any


SKELETON_LIST_FIELDS = (
    "causal_links",
    "character_state_changes",
    "location_changes",
    "time_changes",
    "object_changes",
    "knowledge_changes",
    "relationship_changes",
    "foreshadowing",
    "open_threads",
    "resolved_threads",
    "editable_points",
    "source_references",
)
EVENT_FIELDS = (
    "id",
    "order",
    "event_type",
    "summary",
    "participants",
    "location",
    "time_state",
    "causes",
    "effects",
    "locked",
    "source_span",
    "confidence",
)


def validate_structured_skeleton(value: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Structured skeleton must be an object.")
    required = {
        "metadata",
        "event_nodes",
        *SKELETON_LIST_FIELDS,
        "required_start_state",
        "required_end_state",
    }
    missing = sorted(required.difference(value))
    if missing:
        raise ValueError(f"Structured skeleton is missing fields: {', '.join(missing)}")
    if not isinstance(value["metadata"], dict):
        raise ValueError("metadata must be an object.")
    if not isinstance(value["required_start_state"], dict) or not isinstance(
        value["required_end_state"], dict
    ):
        raise ValueError("required start/end states must be objects.")
    for field in SKELETON_LIST_FIELDS:
        if not isinstance(value[field], list):
            raise ValueError(f"{field} must be a list.")
    if not isinstance(value["event_nodes"], list) or not value["event_nodes"]:
        raise ValueError("event_nodes must contain at least one event.")

    normalized = deepcopy(value)
    ids: set[str] = set()
    orders: list[int] = []
    for raw_node in normalized["event_nodes"]:
        if not isinstance(raw_node, dict):
            raise ValueError("Each event node must be an object.")
        missing_node = [field for field in EVENT_FIELDS if field not in raw_node]
        if missing_node:
            raise ValueError(
                f"Event node is missing fields: {', '.join(missing_node)}"
            )
        node_id = str(raw_node["id"]).strip()
        if not node_id or node_id in ids:
            raise ValueError("Event node ids must be non-empty and unique.")
        ids.add(node_id)
        order = raw_node["order"]
        if not isinstance(order, int) or isinstance(order, bool):
            raise ValueError("Event node order must be an integer.")
        orders.append(order)
        for field in ("participants", "causes", "effects"):
            if not isinstance(raw_node[field], list):
                raise ValueError(f"Event node {field} must be a list.")
        confidence = raw_node["confidence"]
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            raise ValueError("Event node confidence must be between 0 and 1.")
        raw_node["id"] = node_id
        raw_node["locked"] = bool(raw_node["locked"])

    if orders != sorted(orders) or len(set(orders)) != len(orders):
        raise ValueError("Event node order must be strictly increasing and unique.")
    for node in normalized["event_nodes"]:
        unknown = (set(map(str, node["causes"])) | set(map(str, node["effects"]))) - ids
        if unknown:
            raise ValueError(
                f"Event node {node['id']} references unknown causal nodes: {sorted(unknown)}"
            )
    for link in normalized["causal_links"]:
        if not isinstance(link, dict):
            raise ValueError("Each causal link must be an object.")
        source = str(link.get("source_id") or "")
        target = str(link.get("target_id") or "")
        if source not in ids or target not in ids:
            raise ValueError("Causal links must reference existing event nodes.")
    return normalized


def legacy_skeleton_result(plot_summary: str | None) -> dict[str, Any]:
    """Expose old prose analysis without inventing structured event nodes."""
    return {
        "format": "legacy_plot_summary",
        "plot_summary": plot_summary or "",
        "structured": None,
    }
