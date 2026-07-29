from __future__ import annotations

from pathlib import Path
from typing import Any

from rusty.services.analysis_service import AnalysisService
from rusty.services.pipeline_service import PipelineService
from rusty.services.project_service import default_database_path
from rusty.services.rewrite_workflow_service import RewriteWorkflowService, SkeletonVersion
from rusty.services.scene_service import SceneService
from rusty.services.structured_skeleton import validate_structured_skeleton


class DocumentAnalysisService:
    """Project-kind-neutral entry point for chapter/document analysis."""

    def __init__(self, database_path: str | Path | None = None, *, ai_client=None) -> None:
        path = Path(database_path) if database_path is not None else default_database_path()
        self.pipeline = PipelineService(path, ai_client=ai_client)

    def analyze_project(self, project_id: int):
        return self.pipeline.run_document_analysis(project_id)


class SceneAnalysisService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.scenes = SceneService(database_path)

    def analyze_chapter(self, chapter_id: int, *, boundaries=None):
        return self.scenes.split_chapter(chapter_id, proposed_boundaries=boundaries)


class SkeletonExtractionService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.workflow = RewriteWorkflowService(database_path)

    def save_extraction(
        self,
        *,
        project_id: int,
        chapter_id: int,
        scene_id: int | None,
        skeleton: dict[str, Any],
        source_kind: str = "ai_extraction",
    ) -> SkeletonVersion:
        return self.workflow.create_structured_skeleton(
            project_id=project_id,
            chapter_id=chapter_id,
            scene_id=scene_id,
            skeleton=validate_structured_skeleton(skeleton),
            source_kind=source_kind,
        )

    def extract_from_text(
        self,
        *,
        project_id: int,
        text: str,
        workflow_ai,
        expected_skeleton: dict[str, Any],
    ) -> dict[str, Any]:
        result = workflow_ai.generate_json(
            project_id=project_id,
            stage="extract_observed_skeleton",
            payload={"text": text, "expected_skeleton": expected_skeleton},
            output_contract="A complete StructuredSkeleton JSON object describing only the supplied text.",
        )
        return validate_structured_skeleton(
            result.get("observed_skeleton", result)
        )


class StyleAnalysisService(AnalysisService):
    pass


class CharacterAnalysisService:
    """Stable role for character analysis; persisted dynamic state remains scene-owned."""

    def __init__(self, database_path: str | Path | None = None) -> None:
        self.scenes = SceneService(database_path)

    def save_state(self, scene_id: int, character_name: str, state: dict[str, Any]):
        return self.scenes.save_character_state(scene_id, character_name, state)


class FactLedgerService:
    def __init__(self, database_path: str | Path | None = None) -> None:
        self.scenes = SceneService(database_path)

    def save(self, scene_id: int, facts: dict[str, Any], *, source_kind: str = "analysis"):
        return self.scenes.save_fact_ledger(scene_id, facts, source_kind=source_kind)

    def get(self, scene_id: int) -> dict[str, Any]:
        return self.scenes.get_fact_ledger(scene_id)
