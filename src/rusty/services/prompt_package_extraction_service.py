from __future__ import annotations

from pathlib import Path

from rusty.services.ai_client import AIClient
from rusty.services.analysis_service import AnalysisService


class PromptPackageExtractionService:
    """Compatibility wrapper for the pre-v7 extraction entry point.

    New code should call :class:`AnalysisService`. The wrapper intentionally
    synthesizes only reusable rewrite prompts from chapter style analyses; it
    never extracts story or character anchors into a reusable template.
    """

    def __init__(self, database_path: str | Path | None = None, ai_client: AIClient | None = None) -> None:
        self.analysis_service = AnalysisService(database_path, ai_client=ai_client)

    def extract_from_project(self, project_id: int, model_id: int | None = None) -> int:
        return self.analysis_service.synthesize_project(project_id, model_id=model_id)
