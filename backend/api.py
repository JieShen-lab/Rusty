from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rusty.db import session
from rusty.models import ChapterRecord, ExportPlanItem, ParsedBook, ProjectSummary
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services.anchor_service import AnchorService, CharacterCard, OutlineTemplate
from rusty.services.analysis_service import AnalysisService
from rusty.services.model_service import ModelService
from rusty.services.pipeline_service import PipelineService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.prompt_service import PromptService
from rusty.services.style_extraction_service import StyleExtractionService
from rusty.services.style_service import StyleTemplate, StyleTemplateService

from .schemas import (
    ChapterAIOutputsOut,
    AnalysisPromptTemplateOut,
    AnalysisPromptTemplateWriteRequest,
    AnchorExtractRequest,
    CharacterCardOut,
    CharacterCardsExtractOut,
    CharacterCardWriteRequest,
    ChapterDetailOut,
    ChapterErrorOut,
    ChapterOut,
    CreateProjectRequest,
    ErrorResponse,
    ExportPlanItemOut,
    ExportPlanUpdateRequest,
    ExportResponse,
    HealthResponse,
    ModelTestResponse,
    ModelOut,
    ModelWriteRequest,
    PreviewChapterOut,
    PreviewRequest,
    PreviewResponse,
    ProjectDetailOut,
    ProjectCharacterBindingRequest,
    ProjectCharacterBindingsOut,
    ProjectOutlineBindingOut,
    ProjectOutlineBindingRequest,
    ProjectOut,
    ProjectPromptWriteRequest,
    ProjectSettingsUpdateRequest,
    ProjectStyleBindingOut,
    ProjectStyleBindingRequest,
    PromptTemplateOut,
    PromptTemplateWriteRequest,
    PromptPackageExtractRequest,
    PromptPackageImportRequest,
    PlotExpansionRequest,
    TargetSkeletonWriteRequest,
    OutlineTemplateOut,
    OutlineTemplateWriteRequest,
    PipelineRunResponse,
    RetryStageRequest,
    RewriteTextRequest,
    StageStatusOut,
    StyleTemplateExtractRequest,
    StyleTemplateExportResponse,
    StyleTemplateImportRequest,
    StyleTemplateOut,
    StyleTrialWriteRequest,
    StyleTemplateWriteRequest,
    StyleAnalysisOut,
    StyleAnalysisReviewRequest,
    TextResultResponse,
)

APP_NAME = "Rusty"
API_TOKEN_HEADER = "X-Rusty-Token"
PREVIEW_TTL_SECONDS = 15 * 60
SUPPORTED_IMPORT_SUFFIXES = {".txt", ".epub", ".docx"}
STYLE_EXTRACTION_MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173")
_GENERATED_TOKEN = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class PreviewState:
    source_path: Path
    workspace_path: Path | None
    fingerprint: str
    expires_at: float


_PREVIEWS: dict[str, PreviewState] = {}


def current_api_token() -> str:
    return os.environ.get("RUSTY_API_TOKEN") or _GENERATED_TOKEN


def create_app(
    database_path: str | Path | None = None,
    style_ai_client=None,
    anchor_ai_client=None,
    prompt_package_ai_client=None,
) -> FastAPI:
    db_path = Path(os.environ.get("RUSTY_DATABASE_PATH", database_path or default_database_path()))
    project_service = ProjectService(db_path)
    pipeline_service = PipelineService(db_path)
    model_service = ModelService(db_path)
    prompt_service = PromptService(db_path)
    analysis_service = AnalysisService(db_path, ai_client=prompt_package_ai_client or style_ai_client)
    style_service = StyleTemplateService(db_path)
    style_extraction_service = StyleExtractionService(db_path, ai_client=style_ai_client)
    anchor_service = AnchorService(db_path)
    anchor_extraction_service = AnchorExtractionService(db_path, ai_client=anchor_ai_client or style_ai_client)

    app = FastAPI(
        title="Rusty UI-R2 API",
        version="0.1.0",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type", API_TOKEN_HEADER],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": detail.get("error", "http_error"),
                "message": detail.get("message", str(exc.detail)),
                "details": detail.get("details"),
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(_: Request, exc: ValueError) -> JSONResponse:
        return _error_response(400, "validation_error", str(exc))

    @app.exception_handler(FileNotFoundError)
    async def file_not_found_handler(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return _error_response(404, "file_not_found", str(exc))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        return _error_response(500, "internal_error", str(exc))

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, app=APP_NAME)

    @app.get("/api/projects", response_model=list[ProjectOut])
    def list_projects() -> list[ProjectOut]:
        return [_project_out(project) for project in project_service.list_projects()]

    @app.get("/api/projects/{project_id}", response_model=ProjectDetailOut)
    def get_project(project_id: int) -> ProjectDetailOut:
        project = _require_project(project_service, project_id)
        settings = project_service.get_project_settings(project_id)
        exports = project_service.list_exports(project_id)
        return ProjectDetailOut(
            project=_project_out(project),
            metadata=project_service.get_book_metadata(project_id),
            settings=settings.__dict__ if settings else None,
            exports=[record.__dict__ for record in exports],
        )

    @app.post("/api/projects/preview", response_model=PreviewResponse, dependencies=[Depends(_require_token)])
    def preview_project(payload: PreviewRequest) -> PreviewResponse:
        source_path = _validate_source_path(payload.source_path)
        workspace = _optional_workspace_path(payload.workspace_path)
        parsed = project_service.preview_book(source_path)
        token = secrets.token_urlsafe(24)
        _PREVIEWS[token] = PreviewState(
            source_path=source_path,
            workspace_path=workspace,
            fingerprint=_file_fingerprint(source_path),
            expires_at=time.time() + PREVIEW_TTL_SECONDS,
        )
        return _preview_out(parsed, token)

    @app.post("/api/projects", response_model=ProjectOut, dependencies=[Depends(_require_token)])
    def create_project(payload: CreateProjectRequest) -> ProjectOut:
        state = _consume_preview(payload.preview_token)
        if _file_fingerprint(state.source_path) != state.fingerprint:
            raise _http_error(400, "preview_mismatch", "源文件已变化，请重新预览后再创建工程。")
        workspace = _optional_workspace_path(payload.workspace_path) or state.workspace_path or state.source_path.parent
        parsed = project_service.preview_book(state.source_path)
        purpose = "extract" if payload.purpose == "summary" else payload.purpose
        if purpose == "rewrite" and payload.prompt_template_id is None:
            raise _http_error(400, "rewrite_prompt_required", "创建改写工程前请选择改写提示词。")
        if purpose == "extract" and payload.analysis_prompt_template_id is None:
            raise _http_error(400, "analysis_prompt_required", "创建提取工程前请选择风格分析提示词。")
        project_id = project_service.create_project(
            parsed,
            workspace,
            payload.project_name,
            processing_mode=purpose,
            prompt_template_id=payload.prompt_template_id,
            analysis_prompt_template_id=payload.analysis_prompt_template_id,
        )
        return _project_out(_require_project(project_service, project_id))

    @app.post("/api/projects/{project_id}/delete", dependencies=[Depends(_require_token)])
    def delete_project(project_id: int) -> dict[str, bool]:
        _require_project(project_service, project_id)
        project_service.delete_project(project_id)
        return {"ok": True}

    @app.get("/api/projects/{project_id}/chapters", response_model=list[ChapterOut])
    def list_chapters(project_id: int) -> list[ChapterOut]:
        _require_project(project_service, project_id)
        return [_chapter_out(chapter) for chapter in project_service.list_chapters(project_id)]

    @app.get("/api/projects/{project_id}/export-plan", response_model=list[ExportPlanItemOut])
    def get_project_export_plan(project_id: int) -> list[ExportPlanItemOut]:
        _require_project(project_service, project_id)
        return [_export_plan_item_out(item) for item in project_service.list_export_plan(project_id)]

    @app.post(
        "/api/projects/{project_id}/export-plan",
        response_model=list[ExportPlanItemOut],
        dependencies=[Depends(_require_token)],
    )
    def save_project_export_plan(project_id: int, payload: ExportPlanUpdateRequest) -> list[ExportPlanItemOut]:
        _require_project(project_service, project_id)
        project_service.save_export_plan(
            project_id,
            [
                ExportPlanItem(
                    chapter_id=item.chapter_id,
                    export_order=item.export_order,
                    export_title=item.export_title,
                    include_in_export=item.include_in_export,
                )
                for item in payload.items
            ],
        )
        return [_export_plan_item_out(item) for item in project_service.list_export_plan(project_id)]

    @app.get("/api/projects/{project_id}/chapters/{chapter_id}", response_model=ChapterDetailOut)
    def get_project_chapter(project_id: int, chapter_id: int) -> ChapterDetailOut:
        chapter = _require_project_chapter(project_service, project_id, chapter_id)
        return _chapter_detail(chapter, pipeline_service)

    @app.get("/api/chapters/{chapter_id}", response_model=ChapterDetailOut)
    def get_chapter(chapter_id: int) -> ChapterDetailOut:
        chapter = project_service.get_chapter(chapter_id)
        if chapter is None:
            raise _http_error(404, "chapter_not_found", f"Chapter not found: {chapter_id}")
        _require_project(project_service, chapter.project_id)
        return _chapter_detail(chapter, pipeline_service)

    @app.post("/api/projects/{project_id}/export/txt", response_model=ExportResponse, dependencies=[Depends(_require_token)])
    def export_txt(project_id: int) -> ExportResponse:
        project = _require_project(project_service, project_id)
        output_path = _safe_export_path(project, "txt")
        exported = project_service.export_txt(project_id, output_path)
        return ExportResponse(ok=True, format="txt", output_path=str(exported))

    @app.post("/api/projects/{project_id}/export/epub", response_model=ExportResponse, dependencies=[Depends(_require_token)])
    def export_epub(project_id: int) -> ExportResponse:
        project = _require_project(project_service, project_id)
        output_path = _safe_export_path(project, "epub")
        exported = project_service.export_epub(project_id, output_path)
        return ExportResponse(ok=True, format="epub", output_path=str(exported))

    @app.post("/api/projects/{project_id}/settings", response_model=ProjectDetailOut, dependencies=[Depends(_require_token)])
    def update_project_settings(project_id: int, payload: ProjectSettingsUpdateRequest) -> ProjectDetailOut:
        _require_project(project_service, project_id)
        project_service.update_project_settings(
            project_id=project_id,
            model_id=payload.model_id,
            prompt_template_id=payload.prompt_template_id,
            analysis_prompt_template_id=payload.analysis_prompt_template_id,
            processing_mode=payload.processing_mode,
            concurrency=payload.concurrency,
            target_word_count=payload.target_word_count,
            min_expansion_ratio=payload.min_expansion_ratio,
        )
        return get_project(project_id)

    @app.post("/api/projects/{project_id}/prompts", response_model=dict[str, str], dependencies=[Depends(_require_token)])
    def save_project_prompt(project_id: int, payload: ProjectPromptWriteRequest) -> dict[str, str]:
        _require_project(project_service, project_id)
        prompt_service.save_project_prompt(project_id, payload.prompt_key, payload.prompt_text)
        return prompt_service.list_project_prompts(project_id)

    @app.get("/api/projects/{project_id}/prompts", response_model=dict[str, str])
    def list_project_prompts(project_id: int) -> dict[str, str]:
        _require_project(project_service, project_id)
        return prompt_service.list_project_prompts(project_id)

    @app.post("/api/projects/{project_id}/pipeline/run", response_model=PipelineRunResponse, dependencies=[Depends(_require_token)])
    def run_project_pipeline(project_id: int) -> PipelineRunResponse:
        _require_project(project_service, project_id)
        settings = project_service.get_project_settings(project_id)
        result = (
            pipeline_service.run_summary_project(project_id)
            if settings and settings.processing_mode == "summary"
            else pipeline_service.run_project(project_id)
        )
        return PipelineRunResponse(
            ok=True,
            processed=result.processed,
            skipped=result.skipped,
            failed=result.failed,
            paused=result.paused,
        )

    @app.post("/api/projects/{project_id}/pipeline/summarize", response_model=PipelineRunResponse, dependencies=[Depends(_require_token)])
    def run_project_summary(project_id: int) -> PipelineRunResponse:
        _require_project(project_service, project_id)
        result = pipeline_service.run_summary_project(project_id)
        return PipelineRunResponse(
            ok=True,
            processed=result.processed,
            skipped=result.skipped,
            failed=result.failed,
            paused=result.paused,
        )

    @app.post("/api/projects/{project_id}/pipeline/pause", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def pause_project_pipeline(project_id: int) -> dict[str, bool]:
        _require_project(project_service, project_id)
        pipeline_service.set_project_paused(project_id, True)
        return {"ok": True}

    @app.post("/api/chapters/{chapter_id}/summarize", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def summarize_chapter(chapter_id: int) -> TextResultResponse:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        text = pipeline_service.summarize_chapter(chapter_id)
        return TextResultResponse(ok=True, text=text)

    @app.get("/api/chapters/{chapter_id}/style-analysis", response_model=StyleAnalysisOut)
    def get_chapter_style_analysis(chapter_id: int) -> StyleAnalysisOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        record = analysis_service.get_chapter_analysis(chapter_id)
        if record is None:
            raise _http_error(404, "style_analysis_not_found", "本章尚未进行风格分析。")
        return StyleAnalysisOut(**record)

    @app.post(
        "/api/chapters/{chapter_id}/style-analysis",
        response_model=StyleAnalysisOut,
        dependencies=[Depends(_require_token)],
    )
    def analyze_chapter_style(chapter_id: int, payload: PromptPackageExtractRequest) -> StyleAnalysisOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return StyleAnalysisOut(**analysis_service.analyze_chapter(chapter_id, model_id=payload.model_id))

    @app.post(
        "/api/chapters/{chapter_id}/style-analysis/review",
        response_model=StyleAnalysisOut,
        dependencies=[Depends(_require_token)],
    )
    def review_chapter_style(chapter_id: int, payload: StyleAnalysisReviewRequest) -> StyleAnalysisOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return StyleAnalysisOut(**analysis_service.review_chapter(chapter_id, payload.reviewed))

    @app.get("/api/projects/{project_id}/style-analysis/synthesis", response_model=dict[str, Any])
    def get_project_style_synthesis(project_id: int) -> dict[str, Any]:
        _require_project(project_service, project_id)
        return analysis_service.get_project_synthesis(project_id) or {}

    @app.post(
        "/api/projects/{project_id}/style-analysis/synthesize",
        response_model=PromptTemplateOut,
        dependencies=[Depends(_require_token)],
    )
    def synthesize_project_style(project_id: int, payload: PromptPackageExtractRequest) -> PromptTemplateOut:
        _require_project(project_service, project_id)
        template_id = analysis_service.synthesize_project(project_id, model_id=payload.model_id)
        template = prompt_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "style_synthesis_failed", "已生成改写提示词，但无法重新读取。")
        return PromptTemplateOut(**template.__dict__)

    @app.post("/api/chapters/{chapter_id}/detect-scene", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def detect_scene(chapter_id: int) -> TextResultResponse:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        text = pipeline_service.detect_scene(chapter_id)
        return TextResultResponse(ok=True, text=text)

    @app.post("/api/chapters/{chapter_id}/rewrite", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def rewrite_chapter(chapter_id: int) -> TextResultResponse:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        text = pipeline_service.rewrite_chapter(chapter_id)
        return TextResultResponse(ok=True, text=text)

    @app.post("/api/chapters/{chapter_id}/expand-plot", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def expand_chapter_plot(chapter_id: int, payload: PlotExpansionRequest) -> TextResultResponse:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        text = pipeline_service.expand_chapter_plot(chapter_id, enabled=payload.enabled)
        return TextResultResponse(ok=True, text=text)

    @app.post(
        "/api/chapters/{chapter_id}/target-skeleton",
        response_model=ChapterDetailOut,
        dependencies=[Depends(_require_token)],
    )
    def save_target_skeleton(chapter_id: int, payload: TargetSkeletonWriteRequest) -> ChapterDetailOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        pipeline_service.save_target_skeleton(chapter_id, payload.text, payload.enabled)
        return _chapter_detail(_require_existing_chapter(project_service, chapter_id), pipeline_service)

    @app.post("/api/chapters/{chapter_id}/retry", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def retry_chapter_stage(chapter_id: int, payload: RetryStageRequest) -> TextResultResponse:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        text = pipeline_service.retry_chapter_stage(chapter_id, payload.stage)
        return TextResultResponse(ok=True, text=text)

    @app.post("/api/chapters/{chapter_id}/rewrite-text", response_model=ChapterDetailOut, dependencies=[Depends(_require_token)])
    def save_chapter_rewrite(chapter_id: int, payload: RewriteTextRequest) -> ChapterDetailOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        project_service.save_chapter_rewrite(chapter_id, payload.rewritten_text)
        updated = _require_existing_chapter(project_service, chapter_id)
        return _chapter_detail(updated, pipeline_service)

    @app.post(
        "/api/chapters/{chapter_id}/confirm-rewrite",
        response_model=ChapterDetailOut,
        dependencies=[Depends(_require_token)],
    )
    def confirm_chapter_rewrite(chapter_id: int) -> ChapterDetailOut:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        pipeline_service.confirm_rewrite(chapter_id)
        return _chapter_detail(_require_existing_chapter(project_service, chapter_id), pipeline_service)

    @app.get("/api/models", response_model=list[ModelOut])
    def list_models() -> list[ModelOut]:
        return [ModelOut(**model.__dict__) for model in model_service.list_models()]

    @app.post("/api/models", response_model=ModelOut, dependencies=[Depends(_require_token)])
    def create_model(payload: ModelWriteRequest) -> ModelOut:
        model_id = model_service.create_model(**payload.model_dump())
        model = model_service.get_model(model_id)
        if model is None:
            raise _http_error(500, "model_create_failed", "Model was created but could not be loaded.")
        return ModelOut(**model.__dict__)

    @app.post("/api/models/{model_id}", response_model=ModelOut, dependencies=[Depends(_require_token)])
    def update_model(model_id: int, payload: ModelWriteRequest) -> ModelOut:
        model_service.update_model(model_id=model_id, **payload.model_dump())
        model = model_service.get_model(model_id)
        if model is None:
            raise _http_error(404, "model_not_found", f"Model not found: {model_id}")
        return ModelOut(**model.__dict__)

    @app.post("/api/models/{model_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_model(model_id: int) -> dict[str, bool]:
        if model_service.get_model(model_id) is None:
            raise _http_error(404, "model_not_found", f"Model not found: {model_id}")
        model_service.delete_model(model_id)
        return {"ok": True}

    @app.post("/api/models/{model_id}/test", response_model=ModelTestResponse, dependencies=[Depends(_require_token)])
    def test_model(model_id: int) -> ModelTestResponse:
        if model_service.get_model(model_id) is None:
            raise _http_error(404, "model_not_found", f"Model not found: {model_id}")
        result = model_service.test_connection(model_id)
        return ModelTestResponse(ok=result.ok, message=result.message, elapsed_ms=result.elapsed_ms)

    @app.get("/api/analysis-prompts", response_model=list[AnalysisPromptTemplateOut])
    def list_analysis_prompts() -> list[AnalysisPromptTemplateOut]:
        return [AnalysisPromptTemplateOut(**template.__dict__) for template in analysis_service.list_templates()]

    @app.post(
        "/api/analysis-prompts",
        response_model=AnalysisPromptTemplateOut,
        dependencies=[Depends(_require_token)],
    )
    def create_analysis_prompt(payload: AnalysisPromptTemplateWriteRequest) -> AnalysisPromptTemplateOut:
        template_id = analysis_service.create_template(**payload.model_dump())
        template = analysis_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "analysis_prompt_create_failed", "分析提示词已创建，但无法重新读取。")
        return AnalysisPromptTemplateOut(**template.__dict__)

    @app.post(
        "/api/analysis-prompts/{template_id}",
        response_model=AnalysisPromptTemplateOut,
        dependencies=[Depends(_require_token)],
    )
    def update_analysis_prompt(
        template_id: int,
        payload: AnalysisPromptTemplateWriteRequest,
    ) -> AnalysisPromptTemplateOut:
        analysis_service.update_template(template_id, **payload.model_dump())
        template = analysis_service.get_template(template_id)
        if template is None:
            raise _http_error(404, "analysis_prompt_not_found", f"Analysis prompt not found: {template_id}")
        return AnalysisPromptTemplateOut(**template.__dict__)

    @app.post(
        "/api/analysis-prompts/{template_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_analysis_prompt(template_id: int) -> dict[str, bool]:
        if analysis_service.get_template(template_id) is None:
            raise _http_error(404, "analysis_prompt_not_found", f"Analysis prompt not found: {template_id}")
        analysis_service.delete_template(template_id)
        return {"ok": True}

    @app.get("/api/prompts", response_model=list[PromptTemplateOut])
    def list_prompts() -> list[PromptTemplateOut]:
        return [PromptTemplateOut(**template.__dict__) for template in prompt_service.list_templates()]

    @app.post("/api/prompts", response_model=PromptTemplateOut, dependencies=[Depends(_require_token)])
    def create_prompt(payload: PromptTemplateWriteRequest) -> PromptTemplateOut:
        template_id = prompt_service.create_template(**payload.model_dump())
        template = prompt_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "prompt_create_failed", "Prompt template was created but could not be loaded.")
        return PromptTemplateOut(**template.__dict__)

    @app.post("/api/prompts/import", response_model=PromptTemplateOut, dependencies=[Depends(_require_token)])
    def import_prompt_package(payload: PromptPackageImportRequest) -> PromptTemplateOut:
        template_id = prompt_service.import_template_text(payload.content)
        template = prompt_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "prompt_import_failed", "Prompt package was imported but could not be loaded.")
        return PromptTemplateOut(**template.__dict__)

    @app.post("/api/prompts/{template_id}/export", response_model=StyleTemplateExportResponse, dependencies=[Depends(_require_token)])
    def export_prompt_package(template_id: int) -> StyleTemplateExportResponse:
        return StyleTemplateExportResponse(content=prompt_service.export_template(template_id))

    @app.post(
        "/api/projects/{project_id}/prompt-package/extract",
        response_model=PromptTemplateOut,
        dependencies=[Depends(_require_token)],
    )
    def extract_project_prompt_package(project_id: int, payload: PromptPackageExtractRequest) -> PromptTemplateOut:
        _require_project(project_service, project_id)
        template_id = analysis_service.synthesize_project(project_id, model_id=payload.model_id)
        template = prompt_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "prompt_extract_failed", "Prompt package was extracted but could not be loaded.")
        return PromptTemplateOut(**template.__dict__)

    @app.post("/api/prompts/{template_id}", response_model=PromptTemplateOut, dependencies=[Depends(_require_token)])
    def update_prompt(template_id: int, payload: PromptTemplateWriteRequest) -> PromptTemplateOut:
        prompt_service.update_template(template_id=template_id, **payload.model_dump())
        template = prompt_service.get_template(template_id)
        if template is None:
            raise _http_error(404, "prompt_not_found", f"Prompt template not found: {template_id}")
        return PromptTemplateOut(**template.__dict__)

    @app.post("/api/prompts/{template_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_prompt(template_id: int) -> dict[str, bool]:
        if prompt_service.get_template(template_id) is None:
            raise _http_error(404, "prompt_not_found", f"Prompt template not found: {template_id}")
        prompt_service.delete_template(template_id)
        return {"ok": True}

    @app.get("/api/styles", response_model=list[StyleTemplateOut])
    def list_style_templates() -> list[StyleTemplateOut]:
        return [_style_out(template) for template in style_service.list_templates()]

    @app.post("/api/styles/extract", response_model=StyleTemplateOut, dependencies=[Depends(_require_token)])
    def extract_style_template(payload: StyleTemplateExtractRequest) -> StyleTemplateOut:
        if bool(payload.sample_text and payload.sample_text.strip()) == bool(payload.source_path):
            raise _http_error(400, "invalid_style_source", "Provide exactly one of sample_text or source_path.")
        if payload.source_path:
            source_path = _validate_source_path(payload.source_path)
            if source_path.stat().st_size > STYLE_EXTRACTION_MAX_FILE_BYTES:
                raise _http_error(400, "style_source_too_large", "Style extraction source file is too large.")
            template_id = style_extraction_service.extract_from_file(
                source_path,
                name=payload.name,
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        else:
            template_id = style_extraction_service.extract_from_text(
                payload.sample_text or "",
                name=payload.name,
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        template = style_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "style_template_extract_failed", "Style template was extracted but could not be loaded.")
        return _style_out(template)

    @app.get("/api/styles/{template_id}", response_model=StyleTemplateOut)
    def get_style_template(template_id: int) -> StyleTemplateOut:
        template = style_service.get_template(template_id)
        if template is None:
            raise _http_error(404, "style_template_not_found", f"Style template not found: {template_id}")
        return _style_out(template)

    @app.post("/api/styles", response_model=StyleTemplateOut, dependencies=[Depends(_require_token)])
    def create_style_template(payload: StyleTemplateWriteRequest) -> StyleTemplateOut:
        template_id = style_service.create_template(**payload.model_dump())
        template = style_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "style_template_create_failed", "Style template was created but could not be loaded.")
        return _style_out(template)

    @app.post("/api/styles/import", response_model=StyleTemplateOut, dependencies=[Depends(_require_token)])
    def import_style_template(payload: StyleTemplateImportRequest) -> StyleTemplateOut:
        template_id = style_service.import_template_text(payload.content)
        template = style_service.get_template(template_id)
        if template is None:
            raise _http_error(500, "style_template_import_failed", "Style template was imported but could not be loaded.")
        return _style_out(template)

    @app.post("/api/styles/{template_id}", response_model=StyleTemplateOut, dependencies=[Depends(_require_token)])
    def update_style_template(template_id: int, payload: StyleTemplateWriteRequest) -> StyleTemplateOut:
        style_service.update_template(template_id=template_id, **payload.model_dump())
        template = style_service.get_template(template_id)
        if template is None:
            raise _http_error(404, "style_template_not_found", f"Style template not found: {template_id}")
        return _style_out(template)

    @app.post("/api/styles/{template_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_style_template(template_id: int) -> dict[str, bool]:
        if style_service.get_template(template_id) is None:
            raise _http_error(404, "style_template_not_found", f"Style template not found: {template_id}")
        style_service.delete_template(template_id)
        return {"ok": True}

    @app.post("/api/styles/{template_id}/export", response_model=StyleTemplateExportResponse, dependencies=[Depends(_require_token)])
    def export_style_template(template_id: int) -> StyleTemplateExportResponse:
        return StyleTemplateExportResponse(content=style_service.export_template(template_id))

    @app.post("/api/styles/{template_id}/trial-write", response_model=TextResultResponse, dependencies=[Depends(_require_token)])
    def trial_write_style_template(template_id: int, payload: StyleTrialWriteRequest) -> TextResultResponse:
        text = style_extraction_service.trial_write(
            template_id,
            sample_scene=payload.sample_scene,
            target_chars=payload.target_chars,
            model_id=payload.model_id,
        )
        return TextResultResponse(ok=True, text=text)

    @app.get("/api/projects/{project_id}/style", response_model=ProjectStyleBindingOut)
    def get_project_style(project_id: int) -> ProjectStyleBindingOut:
        _require_project(project_service, project_id)
        template = style_service.get_project_style_template(project_id)
        return ProjectStyleBindingOut(style_template=_style_out(template) if template else None)

    @app.post("/api/projects/{project_id}/style", response_model=ProjectStyleBindingOut, dependencies=[Depends(_require_token)])
    def bind_project_style(project_id: int, payload: ProjectStyleBindingRequest) -> ProjectStyleBindingOut:
        _require_project(project_service, project_id)
        if payload.style_template_id is None:
            style_service.unbind_project_style(project_id)
        else:
            style_service.bind_project_style(project_id, payload.style_template_id)
        template = style_service.get_project_style_template(project_id)
        return ProjectStyleBindingOut(style_template=_style_out(template) if template else None)

    @app.get("/api/outlines", response_model=list[OutlineTemplateOut])
    def list_outline_templates() -> list[OutlineTemplateOut]:
        return [_outline_out(template) for template in anchor_service.list_outline_templates()]

    @app.post("/api/outlines/extract", response_model=OutlineTemplateOut, dependencies=[Depends(_require_token)])
    def extract_outline_template(payload: AnchorExtractRequest) -> OutlineTemplateOut:
        if bool(payload.sample_text and payload.sample_text.strip()) == bool(payload.source_path):
            raise _http_error(400, "invalid_anchor_source", "Provide exactly one of sample_text or source_path.")
        name = payload.name or "AI extracted outline"
        if payload.source_path:
            source_path = _validate_source_path(payload.source_path)
            if source_path.stat().st_size > STYLE_EXTRACTION_MAX_FILE_BYTES:
                raise _http_error(400, "anchor_source_too_large", "Anchor extraction source file is too large.")
            template_id = anchor_extraction_service.extract_outline_from_file(
                source_path,
                name=name,
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        else:
            template_id = anchor_extraction_service.extract_outline_from_text(
                payload.sample_text or "",
                name=name,
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        template = anchor_service.get_outline_template(template_id)
        if template is None:
            raise _http_error(500, "outline_template_extract_failed", "Outline template was extracted but could not be loaded.")
        return _outline_out(template)

    @app.get("/api/outlines/{template_id}", response_model=OutlineTemplateOut)
    def get_outline_template(template_id: int) -> OutlineTemplateOut:
        template = anchor_service.get_outline_template(template_id)
        if template is None:
            raise _http_error(404, "outline_template_not_found", f"Outline template not found: {template_id}")
        return _outline_out(template)

    @app.post("/api/outlines", response_model=OutlineTemplateOut, dependencies=[Depends(_require_token)])
    def create_outline_template(payload: OutlineTemplateWriteRequest) -> OutlineTemplateOut:
        template_id = anchor_service.create_outline_template(**payload.model_dump())
        template = anchor_service.get_outline_template(template_id)
        if template is None:
            raise _http_error(500, "outline_template_create_failed", "Outline template was created but could not be loaded.")
        return _outline_out(template)

    @app.post("/api/outlines/{template_id}", response_model=OutlineTemplateOut, dependencies=[Depends(_require_token)])
    def update_outline_template(template_id: int, payload: OutlineTemplateWriteRequest) -> OutlineTemplateOut:
        anchor_service.update_outline_template(template_id=template_id, **payload.model_dump())
        template = anchor_service.get_outline_template(template_id)
        if template is None:
            raise _http_error(404, "outline_template_not_found", f"Outline template not found: {template_id}")
        return _outline_out(template)

    @app.post("/api/outlines/{template_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_outline_template(template_id: int) -> dict[str, bool]:
        if anchor_service.get_outline_template(template_id) is None:
            raise _http_error(404, "outline_template_not_found", f"Outline template not found: {template_id}")
        anchor_service.delete_outline_template(template_id)
        return {"ok": True}

    @app.get("/api/characters", response_model=list[CharacterCardOut])
    def list_character_cards() -> list[CharacterCardOut]:
        return [_character_out(card) for card in anchor_service.list_character_cards()]

    @app.post("/api/characters/extract", response_model=CharacterCardsExtractOut, dependencies=[Depends(_require_token)])
    def extract_character_cards(payload: AnchorExtractRequest) -> CharacterCardsExtractOut:
        if bool(payload.sample_text and payload.sample_text.strip()) == bool(payload.source_path):
            raise _http_error(400, "invalid_anchor_source", "Provide exactly one of sample_text or source_path.")
        if payload.source_path:
            source_path = _validate_source_path(payload.source_path)
            if source_path.stat().st_size > STYLE_EXTRACTION_MAX_FILE_BYTES:
                raise _http_error(400, "anchor_source_too_large", "Anchor extraction source file is too large.")
            card_ids = anchor_extraction_service.extract_characters_from_file(
                source_path,
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        else:
            card_ids = anchor_extraction_service.extract_characters_from_text(
                payload.sample_text or "",
                detail_level=payload.detail_level,
                model_id=payload.model_id,
            )
        cards = [anchor_service.get_character_card(card_id) for card_id in card_ids]
        return CharacterCardsExtractOut(character_cards=[_character_out(card) for card in cards if card is not None])

    @app.get("/api/characters/{card_id}", response_model=CharacterCardOut)
    def get_character_card(card_id: int) -> CharacterCardOut:
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(404, "character_card_not_found", f"Character card not found: {card_id}")
        return _character_out(card)

    @app.post("/api/characters", response_model=CharacterCardOut, dependencies=[Depends(_require_token)])
    def create_character_card(payload: CharacterCardWriteRequest) -> CharacterCardOut:
        card_id = anchor_service.create_character_card(**payload.model_dump())
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(500, "character_card_create_failed", "Character card was created but could not be loaded.")
        return _character_out(card)

    @app.post("/api/characters/{card_id}", response_model=CharacterCardOut, dependencies=[Depends(_require_token)])
    def update_character_card(card_id: int, payload: CharacterCardWriteRequest) -> CharacterCardOut:
        anchor_service.update_character_card(card_id=card_id, **payload.model_dump())
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(404, "character_card_not_found", f"Character card not found: {card_id}")
        return _character_out(card)

    @app.post("/api/characters/{card_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_character_card(card_id: int) -> dict[str, bool]:
        if anchor_service.get_character_card(card_id) is None:
            raise _http_error(404, "character_card_not_found", f"Character card not found: {card_id}")
        anchor_service.delete_character_card(card_id)
        return {"ok": True}

    @app.get("/api/projects/{project_id}/outline", response_model=ProjectOutlineBindingOut)
    def get_project_outline(project_id: int) -> ProjectOutlineBindingOut:
        _require_project(project_service, project_id)
        template = anchor_service.get_project_outline_template(project_id)
        return ProjectOutlineBindingOut(outline_template=_outline_out(template) if template else None)

    @app.post("/api/projects/{project_id}/outline", response_model=ProjectOutlineBindingOut, dependencies=[Depends(_require_token)])
    def bind_project_outline(project_id: int, payload: ProjectOutlineBindingRequest) -> ProjectOutlineBindingOut:
        _require_project(project_service, project_id)
        if payload.outline_template_id is None:
            anchor_service.unbind_project_outline(project_id)
        else:
            anchor_service.bind_project_outline(project_id, payload.outline_template_id)
        template = anchor_service.get_project_outline_template(project_id)
        return ProjectOutlineBindingOut(outline_template=_outline_out(template) if template else None)

    @app.get("/api/projects/{project_id}/characters", response_model=ProjectCharacterBindingsOut)
    def list_project_characters(project_id: int) -> ProjectCharacterBindingsOut:
        _require_project(project_service, project_id)
        return ProjectCharacterBindingsOut(
            character_cards=[_character_out(card) for card in anchor_service.list_project_character_cards(project_id)]
        )

    @app.post("/api/projects/{project_id}/characters", response_model=ProjectCharacterBindingsOut, dependencies=[Depends(_require_token)])
    def bind_project_character(project_id: int, payload: ProjectCharacterBindingRequest) -> ProjectCharacterBindingsOut:
        _require_project(project_service, project_id)
        anchor_service.bind_project_character(project_id, payload.character_card_id, payload.sort_order)
        return list_project_characters(project_id)

    @app.post("/api/projects/{project_id}/characters/{card_id}/unbind", response_model=ProjectCharacterBindingsOut, dependencies=[Depends(_require_token)])
    def unbind_project_character(project_id: int, card_id: int) -> ProjectCharacterBindingsOut:
        _require_project(project_service, project_id)
        anchor_service.unbind_project_character(project_id, card_id)
        return list_project_characters(project_id)

    return app


def _allowed_origins() -> list[str]:
    configured = os.environ.get("RUSTY_API_ALLOWED_ORIGINS")
    if not configured:
        return list(DEFAULT_ALLOWED_ORIGINS)
    return [origin.strip() for origin in configured.split(",") if origin.strip()]


def _require_token(x_rusty_token: str | None = Header(default=None, alias=API_TOKEN_HEADER)) -> None:
    if not secrets.compare_digest(x_rusty_token or "", current_api_token()):
        raise _http_error(403, "forbidden", "Missing or invalid local Rusty API token.")


def _require_project(service: ProjectService, project_id: int) -> ProjectSummary:
    project = service.get_project(project_id)
    if project is None:
        raise _http_error(404, "project_not_found", f"Project not found: {project_id}")
    return project


def _require_project_chapter(service: ProjectService, project_id: int, chapter_id: int) -> ChapterRecord:
    _require_project(service, project_id)
    chapter = service.get_chapter(chapter_id)
    if chapter is None or chapter.project_id != project_id:
        raise _http_error(404, "chapter_not_found", f"Chapter not found in project: {chapter_id}")
    return chapter


def _require_existing_chapter(service: ProjectService, chapter_id: int) -> ChapterRecord:
    chapter = service.get_chapter(chapter_id)
    if chapter is None:
        raise _http_error(404, "chapter_not_found", f"Chapter not found: {chapter_id}")
    return chapter


def _validate_source_path(source_path: str) -> Path:
    path = Path(source_path).expanduser().resolve()
    if path.suffix.lower() not in SUPPORTED_IMPORT_SUFFIXES:
        raise _http_error(400, "unsupported_format", "仅支持 TXT / EPUB / DOCX。")
    if not path.exists() or not path.is_file():
        raise FileNotFoundError(f"Source file not found: {path}")
    return path


def _optional_workspace_path(workspace_path: str | None) -> Path | None:
    if not workspace_path:
        return None
    path = Path(workspace_path).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise _http_error(400, "invalid_workspace", f"Workspace is not a directory: {path}")
    return path


def _file_fingerprint(path: Path) -> str:
    stat = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"{path}|{stat.st_size}|{stat.st_mtime_ns}|{digest.hexdigest()}"


def _consume_preview(token: str) -> PreviewState:
    state = _PREVIEWS.pop(token, None)
    if state is None:
        raise _http_error(400, "preview_invalid", "预览令牌无效，请重新预览。")
    if state.expires_at < time.time():
        raise _http_error(400, "preview_expired", "预览已过期，请重新预览。")
    return state


def _safe_export_path(project: ProjectSummary, extension: str) -> Path:
    workspace = Path(project.workspace_path or Path(project.source_path or ".").parent).expanduser().resolve()
    exports_dir = workspace / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(project.name or project.book_title or f"project-{project.id}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    base = exports_dir / f"{safe_name}-{stamp}.{extension}"
    if not base.exists():
        return base
    for index in range(2, 1000):
        candidate = exports_dir / f"{safe_name}-{stamp}-{index}.{extension}"
        if not candidate.exists():
            return candidate
    raise _http_error(409, "export_conflict", "Unable to allocate a safe export filename.")


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w\-.一-龥]+", "-", value.strip(), flags=re.UNICODE).strip(".-")
    return cleaned[:80] or "rusty-project"


def _preview_out(book: ParsedBook, token: str) -> PreviewResponse:
    return PreviewResponse(
        preview_token=token,
        title=book.title,
        author=book.author,
        language=book.language,
        source_format=book.source_format,
        source_encoding=book.source_encoding,
        total_chapters=len(book.chapters),
        total_words=book.total_words,
        chapters=[
            PreviewChapterOut(
                index=chapter.index,
                title=chapter.title,
                word_count=chapter.word_count,
                start_line=chapter.start_line,
                end_line=chapter.end_line,
            )
            for chapter in book.chapters[:20]
        ],
    )


def _project_out(project: ProjectSummary) -> ProjectOut:
    progress = project.completed_chapters / project.total_chapters if project.total_chapters else 0
    return ProjectOut(
        id=project.id,
        name=project.name,
        status=project.status,
        current_stage=project.current_stage,
        source_format=project.source_format,
        total_chapters=project.total_chapters,
        total_words=project.total_words,
        completed_chapters=project.completed_chapters,
        book_title=project.book_title,
        author=project.author,
        created_at=project.created_at,
        updated_at=project.updated_at,
        progress=progress,
    )


def _chapter_out(chapter: ChapterRecord) -> ChapterOut:
    return ChapterOut(**chapter.__dict__)


def _export_plan_item_out(item: ExportPlanItem) -> ExportPlanItemOut:
    return ExportPlanItemOut(**item.__dict__)


def _chapter_detail(chapter: ChapterRecord, pipeline_service: PipelineService) -> ChapterDetailOut:
    outputs = pipeline_service.get_chapter_ai_outputs(chapter.id)
    statuses = pipeline_service.list_chapter_stage_statuses(chapter.id)
    errors = pipeline_service.list_chapter_errors(chapter.id)
    return ChapterDetailOut(
        chapter=_chapter_out(chapter),
        ai_outputs=ChapterAIOutputsOut(**outputs.__dict__),
        stage_statuses=[StageStatusOut(**status.__dict__) for status in statuses],
        errors=[ChapterErrorOut(**error.__dict__) for error in errors],
    )


def _style_out(template: StyleTemplate) -> StyleTemplateOut:
    return StyleTemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        detail_level=template.detail_level,
        global_prompt=template.global_prompt,
        rewrite_prompt=template.rewrite_prompt,
        style_profile=_json_object(template.style_profile_json),
        generated_prompt=template.generated_prompt,
        source_metadata=_json_object(template.source_metadata_json),
        import_metadata=_json_object(template.import_metadata_json),
        version=template.version,
    )


def _outline_out(template: OutlineTemplate) -> OutlineTemplateOut:
    return OutlineTemplateOut(
        id=template.id,
        name=template.name,
        description=template.description,
        detail_level=template.detail_level,
        outline=_json_object(template.outline_json),
        anchor_prompt=template.anchor_prompt,
        source_metadata=_json_object(template.source_metadata_json),
        import_metadata=_json_object(template.import_metadata_json),
        version=template.version,
    )


def _character_out(card: CharacterCard) -> CharacterCardOut:
    return CharacterCardOut(
        id=card.id,
        name=card.name,
        aliases=_json_list(card.aliases_json),
        description=card.description,
        priority=card.priority,
        is_main=card.is_main,
        relationship_notes=card.relationship_notes,
        personality=card.personality,
        speech_style=card.speech_style,
        action_constraints=card.action_constraints,
        anti_ooc_rules=card.anti_ooc_rules,
        profile=_json_object(card.profile_json),
        source_metadata=_json_object(card.source_metadata_json),
        import_metadata=_json_object(card.import_metadata_json),
        version=card.version,
        sort_order=card.sort_order,
    )


def _json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_list(text: str) -> list[str]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        return []
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _http_error(status_code: int, error: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": error, "message": message, "details": details})


def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "message": message, "details": None})


app = create_app()
