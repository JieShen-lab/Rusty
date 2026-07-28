from __future__ import annotations

from pathlib import Path
from typing import Any

from rusty.services.project_service import default_database_path
from rusty.services.scene_service import SceneService
from rusty.services.structured_model_service import StructuredModelService


SCENE_BOUNDARY_SCHEMA = {
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["title", "start_offset", "end_offset", "reasons"],
                "properties": {
                    "title": {"type": "string"},
                    "start_offset": {"type": "integer", "minimum": 0},
                    "end_offset": {"type": "integer", "minimum": 1},
                    "reasons": {"type": "array", "items": {"type": "string"}},
                },
            },
        }
    },
}


class SceneBoundaryAIService:
    """Ask the configured model for auditable proposed scene ranges."""

    def __init__(
        self,
        database_path: str | Path | None = None,
        *,
        structured_model_service: StructuredModelService | None = None,
    ) -> None:
        self.database_path = Path(database_path) if database_path is not None else default_database_path()
        self.scene_service = SceneService(self.database_path)
        self.model_service = structured_model_service or StructuredModelService(self.database_path)

    def analyze(
        self,
        chapter_id: int,
        *,
        model_id: int | None = None,
    ) -> dict[str, Any]:
        current = self.scene_service.list_scenes(chapter_id)
        if any(scene.user_confirmed for scene in current):
            return {"scenes": current, "model_invocation_id": None, "preserved_confirmed": True}
        source = self.scene_service.ensure_source_version(chapter_id)
        text = str(source["original_text"])
        result = self.model_service.run(
            invocation_kind="scene_boundary_analysis",
            stage="scene_boundaries",
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Identify semantic scene boundaries without rewriting source text. "
                        "Use time, location, principal characters, viewpoint, goal, conflict, "
                        "explicit transitions, and complete dialogue/action chains. Ranges must "
                        "remain in submitted order, be continuous, non-overlapping, start at 0, "
                        "and end at the exact source length. Return strict JSON only."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Chapter length: {len(text)} characters.\n"
                        "Return scenes with title, start_offset, end_offset, and reasons.\n\n"
                        f"Complete chapter source:\n{text}"
                    ),
                },
            ],
            output_schema=SCENE_BOUNDARY_SCHEMA,
            validator=lambda value: {
                "scenes": SceneService._validate_range_items(text, value.get("scenes") or [])
            },
            model_id=model_id,
            project_id=int(source["project_id"]),
            chapter_id=chapter_id,
        )
        proposed = [
            {
                **item,
                "reasons": [*item["reasons"], "ai", f"model_invocation:{result.invocation_id}"],
            }
            for item in result.value["scenes"]
        ]
        scenes = self.scene_service.split_chapter(
            chapter_id,
            proposed_boundaries=proposed,
            source="ai",
        )
        return {
            "scenes": scenes,
            "model_invocation_id": result.invocation_id,
            "preserved_confirmed": False,
        }
