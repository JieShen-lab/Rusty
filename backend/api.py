from __future__ import annotations

import hashlib
import base64
import binascii
import json
import logging
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
from fastapi.responses import FileResponse, JSONResponse

from rusty.db import initialize_database_file, session
from rusty.models import ChapterRecord, ExportPlanItem, ParsedBook, ProjectSummary
from rusty.services.anchor_extraction_service import AnchorExtractionService
from rusty.services.ai_client import (
    AIAuthenticationError,
    AIConnectTimeoutError,
    AIProviderError,
    AIReadTimeoutError,
    AIResponseParseError,
)
from rusty.services.anchor_service import AnchorService, CharacterCard, OutlineTemplate
from rusty.services.material_service import Material, MaterialService, compile_material_ai_prompt
from rusty.services.analysis_service import AnalysisService
from rusty.services.chapter_split_service import ChapterSplitService
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.document_library_service import (
    DocumentLibraryService,
    DocumentRevision,
    DraftConflictError,
    LibraryChapter,
    LibraryDocument,
    LibraryDocumentContent,
    LibraryDocumentDraft,
    ProcessingTemplate,
)
from rusty.services.document_split_ai_service import DocumentSplitAIService
from rusty.services.document_cleanup_ai_service import DocumentCleanupAIService
from rusty.services.model_service import ModelService
from rusty.services.pipeline_service import PipelineService
from rusty.db import default_database_path
from rusty.services.project_service import ProjectService
from rusty.services.prompt_service import PromptService
from rusty.services.prompt_definition_service import PromptDefinitionService
from rusty.services.context_service import ContextService
from rusty.services.creative_workflow_service import CreativeWorkflowService
from rusty.services.rewrite_workflow_service import RewriteWorkflowService
from rusty.services.resource_analysis_service import ResourceAnalysisService
from rusty.services.scene_service import SceneService
from rusty.services.scene_rewrite_orchestrator import SceneRewriteOrchestrator
from rusty.services.scene_boundary_ai_service import SceneBoundaryAIService
from rusty.services.branch_service import BranchService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator


logger = logging.getLogger(__name__)
from rusty.services.rewrite_version_map_service import RewriteVersionMapService
from rusty.services.style_extraction_service import StyleExtractionService
from rusty.services.style_service import StyleTemplate, StyleTemplateService

from .routes.workflows import WorkflowRouteServices, create_workflow_router
from .schemas import (
    ChapterAIOutputsOut,
    AnalysisPromptTemplateOut,
    AnalysisPromptTemplateWriteRequest,
    AnchorExtractRequest,
    AuthorStyleDimensionApplyRequest,
    AuthorStyleDimensionPreviewOut,
    AuthorStyleDimensionPreviewRequest,
    AISplitApplyRequest,
    AISplitPreviewRequest,
    CharacterAnalyzeRequest,
    CharacterAnalysisConfirmRequest,
    CharacterCategoryOut,
    CharacterCoverWriteRequest,
    CharacterCardOut,
    CharacterCardCopyRequest,
    CharacterCopyToProjectRequest,
    CharacterExtractionApplyItemOut,
    CharacterExtractionApplyOut,
    CharacterExtractionApplyRequest,
    CharacterExtractionCandidateOut,
    CharacterExtractionDraftOut,
    CharacterExtractionPreviewOut,
    CharacterExtractionPreviewRequest,
    CharacterExtractionSettingsOut,
    CharacterExtractionSettingsWriteRequest,
    CharacterCardsExtractOut,
    CharacterCardWriteRequest,
    CharacterPublishRequest,
    CharacterProjectSummaryOut,
    CharacterSourceSummaryOut,
    ChapterDetailOut,
    ChapterErrorOut,
    ChapterOut,
    CreateProjectRequest,
    LegacyAnalysisExportResponse,
    LegacyProjectCreateRequest,
    ErrorResponse,
    ExportPlanItemOut,
    ExportPlanUpdateRequest,
    ExportResponse,
    HealthResponse,
    LibraryDocumentImportRequest,
    LibraryDocumentImportResponse,
    LibraryDocumentUpdateRequest,
    LibraryDocumentCleanupRequest,
    LibraryDocumentAICleanupRequest,
    LibraryDocumentAICleanupResponse,
    LibraryDocumentCleanupChapterStatusOut,
    LibraryDocumentCleanupResponse,
    LibraryDocumentChapterOut,
    LibraryDocumentChapterReorderRequest,
    LibraryDocumentDirectoryOut,
    LibraryDocumentVolumeOut,
    LibraryDocumentVolumeRenameRequest,
    LibraryDocumentContentOut,
    LibraryDocumentDraftOut,
    LibraryDocumentDraftScopeRequest,
    LibraryDocumentDraftWriteRequest,
    LibraryDocumentSaveContentRequest,
    LibraryDocumentExportRequest,
    LibraryDocumentExportResponse,
    LibraryDocumentOut,
    LibraryDocumentRevisionOut,
    MaterialAnalyzeRequest,
    MaterialAISettingsOut,
    MaterialAISettingsImportRequest,
    MaterialAISettingsWriteRequest,
    MaterialAnalysisApplyRequest,
    MaterialCategoryCreateRequest,
    MaterialCategoryOut,
    MaterialExtractionApplyOut,
    MaterialExtractionApplyRequest,
    MaterialExtractionCandidateOut,
    MaterialExtractionPreviewOut,
    MaterialExtractionPreviewRequest,
    MaterialJsonImportRequest,
    MaterialCopyRequest,
    MaterialExtractOut,
    MaterialExtractRequest,
    MaterialOut,
    MaterialUpdateRequest,
    MaterialWriteRequest,
    DocumentProcessingTemplateCreateRequest,
    DocumentProcessingTemplateOut,
    DocumentLibraryMigrateRequest,
    DocumentLibrarySettingsOut,
    DocumentCreateChapterRequest,
    DocumentCreateChapterResponse,
    DocumentCursorSplitRequest,
    DocumentCategoryOut,
    DocumentMergeRequest,
    ModelTestResponse,
    ModelOut,
    ModelWriteRequest,
    PreviewChapterOut,
    PreviewRequest,
    PreviewResponse,
    ProjectDetailOut,
    ProjectMaterialFilterOut,
    ProjectMaterialFilterWriteRequest,
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
    SceneBoundaryWriteRequest,
    SceneContextCompileRequest,
    SceneFactLedgerWriteRequest,
    SceneRetrievalRequest,
    SceneRewriteVersionWriteRequest,
    SceneStageWriteRequest,
    SceneWorkflowExecuteRequest,
    SceneWorkflowPlanRequest,
    SceneWorkflowStartRequest,
    CharacterStoryStateWriteRequest,
    StorySkeletonRevisionRequest,
    StorySkeletonWriteRequest,
    RewritePlanWriteRequest,
    TargetedRepairWriteRequest,
    ConsistencyCheckWriteRequest,
    RegexSplitApplyRequest,
    RegexSplitPreviewRequest,
    ResourceTagAssignmentRequest,
    ResourceTagCreateRequest,
    ResourceTagOut,
    ResourceTagRenameRequest,
    SelectionResourceCreateRequest,
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
    SplitPreview,
    ManualChapterMarkRequest,
)

APP_NAME = "Rusty"
API_TOKEN_HEADER = "X-Rusty-Token"
PREVIEW_TTL_SECONDS = 15 * 60
SUPPORTED_IMPORT_SUFFIXES = {".txt", ".epub", ".docx"}
STYLE_EXTRACTION_MAX_FILE_BYTES = 5 * 1024 * 1024
DEFAULT_ALLOWED_ORIGINS = ("http://localhost:5173", "http://127.0.0.1:5173", "null")
_GENERATED_TOKEN = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class PreviewState:
    source_path: Path
    workspace_path: Path | None
    parsed_book: ParsedBook
    split_options: dict[str, Any]
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
    workflow_ai_client=None,
) -> FastAPI:
    db_path = Path(database_path) if database_path is not None else Path(
        os.environ.get("RUSTY_DATABASE_PATH", default_database_path())
    )
    initialize_database_file(db_path)
    project_service = ProjectService(db_path)
    chapter_split_service = ChapterSplitService()
    document_library_service = DocumentLibraryService(db_path)
    document_split_ai_service = DocumentSplitAIService(db_path)
    document_cleanup_ai_service = DocumentCleanupAIService(db_path)
    pipeline_service = PipelineService(db_path)
    model_service = ModelService(db_path)
    prompt_service = PromptService(db_path)
    prompt_definition_service = PromptDefinitionService(db_path)
    analysis_service = AnalysisService(db_path, ai_client=prompt_package_ai_client or style_ai_client)
    style_service = StyleTemplateService(db_path)
    style_extraction_service = StyleExtractionService(db_path, ai_client=style_ai_client)
    anchor_service = AnchorService(db_path)
    material_service = MaterialService(db_path)
    scene_service = SceneService(db_path)
    scene_boundary_ai_service = SceneBoundaryAIService(db_path)
    context_service = ContextService(db_path)
    creative_workflow_service = CreativeWorkflowService(db_path, ai_client=workflow_ai_client)
    rewrite_workflow_service = RewriteWorkflowService(db_path)
    resource_analysis_service = ResourceAnalysisService(db_path)
    scene_rewrite_orchestrator = SceneRewriteOrchestrator(db_path)
    branch_service = BranchService(db_path)
    plot_generation_orchestrator = PlotGenerationOrchestrator(
        db_path, ai_client=workflow_ai_client
    )
    prose_rewrite_orchestrator = ProseRewriteOrchestrator(
        db_path, ai_client=workflow_ai_client
    )
    chapter_version_service = ChapterVersionService(db_path)
    rewrite_version_map_service = RewriteVersionMapService(db_path)
    anchor_extraction_service = AnchorExtractionService(db_path, ai_client=anchor_ai_client or style_ai_client)

    app = FastAPI(
        title="Rusty Local API",
        version="0.1.0",
        responses={400: {"model": ErrorResponse}, 404: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_origins(),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
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

    @app.exception_handler(AIConnectTimeoutError)
    async def ai_connect_timeout_handler(_: Request, exc: AIConnectTimeoutError) -> JSONResponse:
        logger.warning("AI request failed during connection", exc_info=exc)
        return _error_response(504, "ai_connect_timeout", str(exc))

    @app.exception_handler(AIReadTimeoutError)
    async def ai_read_timeout_handler(_: Request, exc: AIReadTimeoutError) -> JSONResponse:
        logger.warning("AI provider response timed out", exc_info=exc)
        return _error_response(504, "ai_read_timeout", str(exc))

    @app.exception_handler(AIAuthenticationError)
    async def ai_authentication_handler(_: Request, exc: AIAuthenticationError) -> JSONResponse:
        logger.warning("AI provider rejected authentication", exc_info=exc)
        return _error_response(401, "ai_authentication_failed", str(exc))

    @app.exception_handler(AIProviderError)
    async def ai_provider_error_handler(_: Request, exc: AIProviderError) -> JSONResponse:
        logger.warning("AI provider request failed", exc_info=exc)
        return _error_response(502, "ai_provider_error", str(exc))

    @app.exception_handler(AIResponseParseError)
    async def ai_response_parse_handler(_: Request, exc: AIResponseParseError) -> JSONResponse:
        logger.warning("AI provider response could not be parsed", exc_info=exc)
        return _error_response(502, "ai_response_parse_error", str(exc))

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled API error", exc_info=exc)
        return _error_response(500, "internal_error", str(exc))

    app.include_router(
        create_workflow_router(
            WorkflowRouteServices(
                projects=project_service,
                branches=branch_service,
                plot=plot_generation_orchestrator,
                prose=prose_rewrite_orchestrator,
                chapters=chapter_version_service,
                rewrite_maps=rewrite_version_map_service,
                contexts=context_service,
            ),
            require_token=_require_token,
            require_project=_require_project,
            http_error=_http_error,
        )
    )

    @app.get("/api/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse(ok=True, app=APP_NAME)

    @app.get("/api/projects", response_model=list[ProjectOut])
    def list_projects() -> list[ProjectOut]:
        return [_project_out(project) for project in project_service.list_projects()]

    @app.get("/api/documents", response_model=list[LibraryDocumentOut])
    def list_library_documents() -> list[LibraryDocumentOut]:
        return [_library_document_out(document) for document in document_library_service.list_documents()]

    @app.post(
        "/api/documents/import",
        response_model=LibraryDocumentImportResponse,
        dependencies=[Depends(_require_token)],
    )
    def import_library_document(payload: LibraryDocumentImportRequest) -> LibraryDocumentImportResponse:
        result = document_library_service.import_document(payload.source_path)
        return LibraryDocumentImportResponse(
            document=_library_document_out(result.document),
            created=result.created,
            storage_format="txt",
        )

    @app.post(
        "/api/documents/{document_id}",
        response_model=LibraryDocumentOut,
        dependencies=[Depends(_require_token)],
    )
    def update_library_document(
        document_id: int,
        payload: LibraryDocumentUpdateRequest,
    ) -> LibraryDocumentOut:
        return _library_document_out(
            document_library_service.update_document_metadata(
                document_id,
                title=payload.title,
                author=payload.author,
            )
        )

    @app.get("/api/document-library/settings", response_model=DocumentLibrarySettingsOut)
    def get_document_library_settings() -> DocumentLibrarySettingsOut:
        return DocumentLibrarySettingsOut(storage_path=str(document_library_service.get_library_path()))

    @app.post(
        "/api/document-library/migrate",
        response_model=DocumentLibrarySettingsOut,
        dependencies=[Depends(_require_token)],
    )
    def migrate_document_library(payload: DocumentLibraryMigrateRequest) -> DocumentLibrarySettingsOut:
        migrated = document_library_service.migrate_library_path(payload.target_path)
        return DocumentLibrarySettingsOut(storage_path=str(migrated))

    @app.get("/api/document-tags", response_model=list[ResourceTagOut])
    def list_document_tags() -> list[ResourceTagOut]:
        return [_resource_tag_out(tag) for tag in document_library_service.list_tags()]

    @app.post("/api/document-tags", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def create_document_tag(payload: ResourceTagCreateRequest) -> ResourceTagOut:
        return _resource_tag_out(document_library_service.create_tag(payload.name))

    @app.post("/api/document-tags/{tag_id}", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def rename_document_tag(tag_id: int, payload: ResourceTagRenameRequest) -> ResourceTagOut:
        return _resource_tag_out(document_library_service.rename_tag(tag_id, payload.name))

    @app.post("/api/document-tags/{tag_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_document_tag(tag_id: int) -> dict[str, bool]:
        document_library_service.delete_tag(tag_id)
        return {"ok": True}

    @app.post(
        "/api/documents/{document_id}/tags/{tag_id}",
        response_model=LibraryDocumentOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_document_tag(document_id: int, tag_id: int, payload: ResourceTagAssignmentRequest) -> LibraryDocumentOut:
        return _library_document_out(document_library_service.set_document_tag(document_id, tag_id, payload.selected))

    @app.get("/api/document-categories", response_model=list[DocumentCategoryOut])
    def list_document_categories() -> list[DocumentCategoryOut]:
        return [
            DocumentCategoryOut(**category.__dict__)
            for category in document_library_service.list_categories()
        ]

    @app.post(
        "/api/document-categories",
        response_model=DocumentCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def create_document_category(payload: ResourceTagCreateRequest) -> DocumentCategoryOut:
        return DocumentCategoryOut(**document_library_service.create_category(payload.name).__dict__)

    @app.post(
        "/api/document-categories/{category_id}",
        response_model=DocumentCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def rename_document_category(
        category_id: int,
        payload: ResourceTagRenameRequest,
    ) -> DocumentCategoryOut:
        return DocumentCategoryOut(
            **document_library_service.rename_category(category_id, payload.name).__dict__
        )

    @app.post(
        "/api/document-categories/{category_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_document_category(category_id: int) -> dict[str, bool]:
        document_library_service.delete_category(category_id)
        return {"ok": True}

    @app.post(
        "/api/documents/{document_id}/categories/{category_id}",
        response_model=LibraryDocumentOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_document_category(
        document_id: int,
        category_id: int,
        payload: ResourceTagAssignmentRequest,
    ) -> LibraryDocumentOut:
        return _library_document_out(
            document_library_service.set_document_category(
                document_id,
                category_id,
                payload.selected,
            )
        )

    @app.get("/api/document-processing-templates", response_model=list[DocumentProcessingTemplateOut])
    def list_document_processing_templates() -> list[DocumentProcessingTemplateOut]:
        return [_processing_template_out(template) for template in document_library_service.list_processing_templates()]

    @app.post(
        "/api/document-processing-templates",
        response_model=DocumentProcessingTemplateOut,
        dependencies=[Depends(_require_token)],
    )
    def create_document_processing_template(
        payload: DocumentProcessingTemplateCreateRequest,
    ) -> DocumentProcessingTemplateOut:
        template = document_library_service.create_processing_template(
            payload.name,
            payload.settings.model_dump(),
        )
        return _processing_template_out(template)

    @app.get(
        "/api/documents/{document_id}/revisions",
        response_model=list[LibraryDocumentRevisionOut],
    )
    def list_library_document_revisions(document_id: int) -> list[LibraryDocumentRevisionOut]:
        return [_document_revision_out(revision) for revision in document_library_service.list_revisions(document_id)]

    @app.get(
        "/api/documents/{document_id}/chapters",
        response_model=list[LibraryDocumentChapterOut],
    )
    def list_library_document_chapters(document_id: int) -> list[LibraryDocumentChapterOut]:
        return [_library_chapter_out(chapter) for chapter in document_library_service.list_chapters(document_id)]

    @app.get(
        "/api/documents/{document_id}/directory",
        response_model=LibraryDocumentDirectoryOut,
    )
    def get_library_document_directory(document_id: int) -> LibraryDocumentDirectoryOut:
        directory = document_library_service.get_directory(document_id)
        return LibraryDocumentDirectoryOut(
            volumes=[
                LibraryDocumentVolumeOut(
                    **volume.__dict__,
                    chapters=[_library_chapter_out(chapter) for chapter in chapters],
                )
                for volume, chapters in directory.volumes
            ],
            unassigned_chapters=[
                _library_chapter_out(chapter)
                for chapter in directory.unassigned_chapters
            ],
        )

    @app.get(
        "/api/documents/{document_id}/content",
        response_model=LibraryDocumentContentOut,
    )
    def get_library_document_content(
        document_id: int,
        chapter_id: int | None = None,
    ) -> LibraryDocumentContentOut:
        return _library_document_content_out(
            document_library_service.get_content(document_id, chapter_id)
        )

    @app.get(
        "/api/documents/{document_id}/draft",
        response_model=LibraryDocumentDraftOut | None,
    )
    def get_library_document_draft(
        document_id: int,
        chapter_id: int | None = None,
    ) -> LibraryDocumentDraftOut | None:
        draft = document_library_service.get_draft(document_id, chapter_id)
        return _library_document_draft_out(draft) if draft is not None else None

    @app.put(
        "/api/documents/{document_id}/draft",
        response_model=LibraryDocumentDraftOut,
        dependencies=[Depends(_require_token)],
    )
    def save_library_document_draft(
        document_id: int,
        payload: LibraryDocumentDraftWriteRequest,
    ) -> LibraryDocumentDraftOut:
        try:
            draft = document_library_service.save_draft(
                document_id,
                base_revision_id=payload.base_revision_id,
                title=payload.title,
                text=payload.text,
                chapter_id=payload.chapter_id,
            )
        except DraftConflictError as exc:
            raise _http_error(409, "document_draft_conflict", str(exc)) from exc
        return _library_document_draft_out(draft)

    @app.post(
        "/api/documents/{document_id}/draft/commit",
        response_model=LibraryDocumentCleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def commit_library_document_draft(
        document_id: int,
        payload: LibraryDocumentDraftScopeRequest,
    ) -> LibraryDocumentCleanupResponse:
        try:
            result = document_library_service.commit_draft(document_id, payload.chapter_id)
        except DraftConflictError as exc:
            raise _http_error(409, "document_draft_conflict", str(exc)) from exc
        return LibraryDocumentCleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post(
        "/api/documents/{document_id}/draft/discard",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def discard_library_document_draft(
        document_id: int,
        payload: LibraryDocumentDraftScopeRequest,
    ) -> dict[str, bool]:
        document_library_service.discard_draft(document_id, payload.chapter_id)
        return {"ok": True}

    @app.post(
        "/api/documents/{document_id}/content",
        response_model=LibraryDocumentCleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def save_library_document_content(document_id: int, payload: LibraryDocumentSaveContentRequest) -> LibraryDocumentCleanupResponse:
        result = document_library_service.save_content(
            document_id,
            text=payload.text,
            title=payload.title,
            chapter_id=payload.chapter_id,
        )
        return LibraryDocumentCleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post("/api/documents/merge", response_model=LibraryDocumentOut, dependencies=[Depends(_require_token)])
    def merge_library_documents(payload: DocumentMergeRequest) -> LibraryDocumentOut:
        return _library_document_out(
            document_library_service.merge_documents(payload.document_ids, payload.title, payload.author)
        )

    @app.post(
        "/api/documents/{document_id}/chapters",
        response_model=DocumentCreateChapterResponse,
        dependencies=[Depends(_require_token)],
    )
    def create_library_document_chapter(document_id: int, payload: DocumentCreateChapterRequest) -> DocumentCreateChapterResponse:
        result = document_library_service.create_chapter(
            document_id,
            title=payload.title,
            text=payload.text,
            position=payload.position,
            anchor_chapter_id=payload.anchor_chapter_id,
        )
        if result.created_chapter_id is None:
            raise RuntimeError("Created chapter could not be resolved in the new revision.")
        return DocumentCreateChapterResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
            created_chapter_id=result.created_chapter_id,
        )

    @app.delete(
        "/api/documents/{document_id}/chapters/{chapter_id}",
        response_model=LibraryDocumentCleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def delete_library_document_chapter(
        document_id: int,
        chapter_id: int,
    ) -> LibraryDocumentCleanupResponse:
        result = document_library_service.delete_chapter(document_id, chapter_id)
        return LibraryDocumentCleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post("/api/documents/{document_id}/split/regex/preview", response_model=SplitPreview)
    def preview_regex_document_split(document_id: int, payload: RegexSplitPreviewRequest) -> SplitPreview:
        return SplitPreview(**document_library_service.preview_regex_split(document_id, payload.pattern).__dict__)

    @app.post(
        "/api/documents/{document_id}/split/ai/preview",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def preview_ai_document_split(document_id: int, payload: AISplitPreviewRequest) -> dict[str, Any]:
        return document_split_ai_service.preview(
            document_id,
            chapter_id=payload.chapter_id,
            prompt=payload.prompt,
            model_id=payload.model_id,
        )

    @app.post(
        "/api/documents/{document_id}/split/ai/apply",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def apply_ai_document_split(document_id: int, payload: AISplitApplyRequest) -> dict[str, Any]:
        result = document_split_ai_service.apply(payload.proposal_id, chapters=payload.chapters)
        if int(result.get("proposal_id", 0)) != payload.proposal_id or int(result.get("document_id", 0)) != document_id:
            raise _http_error(409, "split_proposal_mismatch", "AI split proposal mismatch.")
        return result

    @app.post(
        "/api/documents/{document_id}/split/cursor",
        response_model=DocumentCreateChapterResponse,
        dependencies=[Depends(_require_token)],
    )
    def split_document_chapter_at_cursor(
        document_id: int,
        payload: DocumentCursorSplitRequest,
    ) -> DocumentCreateChapterResponse:
        result = document_library_service.split_chapter_at_cursor(
            document_id,
            chapter_id=payload.chapter_id,
            cursor_offset=payload.cursor_offset,
            next_title=payload.next_title,
        )
        if result.created_chapter_id is None:
            raise RuntimeError("Created chapter could not be resolved in the new revision.")
        return DocumentCreateChapterResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
            created_chapter_id=result.created_chapter_id,
        )

    @app.post(
        "/api/documents/{document_id}/split/regex/apply",
        response_model=list[LibraryDocumentChapterOut],
        dependencies=[Depends(_require_token)],
    )
    def apply_regex_document_split(document_id: int, payload: RegexSplitApplyRequest) -> list[LibraryDocumentChapterOut]:
        return [
            _library_chapter_out(chapter)
            for chapter in document_library_service.apply_regex_split(
                document_id,
                payload.pattern,
                payload.preview_token,
                [chapter.model_dump() for chapter in payload.chapters] if payload.chapters is not None else None,
            )
        ]

    @app.post(
        "/api/documents/{document_id}/chapters/mark",
        response_model=list[LibraryDocumentChapterOut],
        dependencies=[Depends(_require_token)],
    )
    def mark_library_document_chapter(document_id: int, payload: ManualChapterMarkRequest) -> list[LibraryDocumentChapterOut]:
        return [
            _library_chapter_out(chapter)
            for chapter in document_library_service.mark_chapter(
                document_id,
                payload.revision_id,
                payload.title,
                payload.start_offset,
                payload.end_offset,
            )
        ]

    @app.post(
        "/api/documents/{document_id}/chapters/reorder",
        response_model=list[LibraryDocumentChapterOut],
        dependencies=[Depends(_require_token)],
    )
    def reorder_library_document_chapters(
        document_id: int,
        payload: LibraryDocumentChapterReorderRequest,
    ) -> list[LibraryDocumentChapterOut]:
        return [
            _library_chapter_out(chapter)
            for chapter in document_library_service.reorder_chapters(
                document_id,
                payload.ordered_chapter_ids,
                payload.volume_assignments,
            )
        ]

    @app.post(
        "/api/documents/{document_id}/volumes/{volume_id}",
        response_model=LibraryDocumentCleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def rename_library_document_volume(
        document_id: int,
        volume_id: int,
        payload: LibraryDocumentVolumeRenameRequest,
    ) -> LibraryDocumentCleanupResponse:
        result = document_library_service.rename_volume(
            document_id,
            volume_id,
            payload.title,
        )
        return LibraryDocumentCleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post(
        "/api/documents/{document_id}/delete",
        dependencies=[Depends(_require_token)],
    )
    def delete_library_document(document_id: int) -> dict[str, bool]:
        document_library_service.delete_document(document_id)
        return {"ok": True}

    @app.post(
        "/api/documents/{document_id}/cleanup",
        response_model=LibraryDocumentCleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def cleanup_library_document(
        document_id: int,
        payload: LibraryDocumentCleanupRequest,
    ) -> LibraryDocumentCleanupResponse:
        result = document_library_service.apply_cleanup(document_id, payload.template_id)
        return LibraryDocumentCleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post(
        "/api/documents/{document_id}/cleanup/ai",
        response_model=LibraryDocumentAICleanupResponse,
        dependencies=[Depends(_require_token)],
    )
    def cleanup_library_document_with_ai(
        document_id: int,
        payload: LibraryDocumentAICleanupRequest,
    ) -> LibraryDocumentAICleanupResponse:
        chapter_ids = payload.chapter_ids or ([payload.chapter_id] if payload.chapter_id is not None else [])
        if chapter_ids:
            batch = document_cleanup_ai_service.apply_many(
                document_id,
                chapter_ids=chapter_ids,
                prompt=payload.prompt,
                model_id=payload.model_id,
            )
            document = batch.result.document if batch.result else next(
                item for item in document_library_service.list_documents() if item.id == document_id
            )
            return LibraryDocumentAICleanupResponse(
                document=_library_document_out(document),
                revision=_document_revision_out(batch.result.revision) if batch.result else None,
                created=batch.result is not None,
                chapters=[LibraryDocumentCleanupChapterStatusOut(**item.__dict__) for item in batch.chapters],
            )
        result = document_cleanup_ai_service.apply(
            document_id,
            chapter_id=None,
            prompt=payload.prompt,
            model_id=payload.model_id,
        )
        return LibraryDocumentAICleanupResponse(
            document=_library_document_out(result.document),
            revision=_document_revision_out(result.revision),
            created=result.created,
        )

    @app.post(
        "/api/documents/{document_id}/revisions/{revision_id}/activate",
        response_model=LibraryDocumentOut,
        dependencies=[Depends(_require_token)],
    )
    def activate_library_document_revision(document_id: int, revision_id: int) -> LibraryDocumentOut:
        return _library_document_out(document_library_service.activate_revision(document_id, revision_id))

    @app.post(
        "/api/documents/{document_id}/export",
        response_model=LibraryDocumentExportResponse,
        dependencies=[Depends(_require_token)],
    )
    def export_library_document(
        document_id: int,
        payload: LibraryDocumentExportRequest,
    ) -> LibraryDocumentExportResponse:
        output = document_library_service.export_document(
            document_id,
            payload.format,
            payload.output_path,
        )
        return LibraryDocumentExportResponse(
            ok=True,
            format=payload.format,
            output_path=str(output),
        )

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
        split_options = payload.split.model_dump() if payload.split is not None else {"mode": "auto"}
        if source_path.suffix.lower() == ".txt":
            parsed = chapter_split_service.preview_txt(source_path, **split_options)
        else:
            parsed = project_service.preview_book(source_path)
            split_options = {"mode": "document"}
        token = secrets.token_urlsafe(24)
        _PREVIEWS[token] = PreviewState(
            source_path=source_path,
            workspace_path=workspace,
            parsed_book=parsed,
            split_options=split_options,
            fingerprint=_file_fingerprint(source_path),
            expires_at=time.time() + PREVIEW_TTL_SECONDS,
        )
        return _preview_out(parsed, token, split_mode=str(split_options["mode"]))

    @app.post("/api/projects", response_model=ProjectOut, dependencies=[Depends(_require_token)])
    def create_project(payload: CreateProjectRequest) -> ProjectOut:
        state = _consume_preview(payload.preview_token)
        if _file_fingerprint(state.source_path) != state.fingerprint:
            raise _http_error(400, "preview_mismatch", "源文件已变化，请重新预览后再创建工程。")
        workspace = _optional_workspace_path(payload.workspace_path) or state.workspace_path or state.source_path.parent
        parsed = state.parsed_book
        txt_split_rule_id = 1
        if parsed.source_format == "txt" and state.split_options.get("mode") != "auto":
            options = state.split_options
            txt_split_rule_id = project_service.create_txt_split_rule(
                name=f"{payload.project_name or parsed.title} import split",
                mode=str(options.get("mode") or "auto"),
                line_prefix=str(options.get("line_prefix") or "") or None,
                number_pattern=str(options.get("number_style") or "") or None,
                title_suffix="|".join(options.get("title_suffixes") or []) or None,
                custom_regex=options.get("custom_regex"),
                extra_rules={
                    "extra_title_regex": options.get("extra_title_regex"),
                },
            )
        project_id = project_service.create_project(
            parsed,
            workspace,
            payload.project_name,
            project_kind=payload.project_kind,
            processing_mode="manual",
            prompt_template_id=payload.prompt_template_id,
            analysis_prompt_template_id=payload.analysis_prompt_template_id,
            txt_split_rule_id=txt_split_rule_id,
            model_id=payload.model_id,
        )
        document_library_service.ensure_project_document(project_id, state.source_path)
        prompt_definition_service.initialize_project_master(
            project_id, payload.master_prompt_definition_id
        )
        return _project_out(_require_project(project_service, project_id))

    @app.get(
        "/api/projects/{project_id}/legacy-analysis/export",
        response_model=LegacyAnalysisExportResponse,
    )
    def export_legacy_analysis(project_id: int) -> dict[str, Any]:
        return project_service.export_legacy_analysis(project_id)

    @app.post(
        "/api/projects/{project_id}/legacy-analysis/create-project",
        response_model=ProjectOut,
        dependencies=[Depends(_require_token)],
    )
    def create_project_from_legacy(
        project_id: int, payload: LegacyProjectCreateRequest
    ) -> ProjectOut:
        target_id = project_service.create_from_legacy(
            project_id, **payload.model_dump()
        )
        return _project_out(_require_project(project_service, target_id))

    @app.post("/api/projects/{project_id}/delete", dependencies=[Depends(_require_token)])
    def delete_project(project_id: int) -> dict[str, bool]:
        _require_project(project_service, project_id)
        project_service.delete_project(project_id)
        return {"ok": True}

    @app.get("/api/projects/{project_id}/chapters", response_model=list[ChapterOut])
    def list_chapters(project_id: int) -> list[ChapterOut]:
        _require_project(project_service, project_id)
        return [_chapter_out(chapter) for chapter in project_service.list_chapters(project_id)]

    @app.get("/api/projects/{project_id}/creative-workflow", response_model=list[dict[str, Any]])
    def list_creative_workflow_states(project_id: int) -> list[dict[str, Any]]:
        project = _require_project(project_service, project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(409, "legacy_extract_workflow", "Legacy extract projects use their dedicated workflow.")
        return creative_workflow_service.list_chapter_states(project_id)

    @app.get("/api/chapters/{chapter_id}/creative-workflow", response_model=dict[str, Any])
    def get_creative_workflow_state(chapter_id: int) -> dict[str, Any]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        project = _require_project(project_service, chapter.project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(409, "legacy_extract_workflow", "Legacy extract projects use their dedicated workflow.")
        return creative_workflow_service.get_chapter_state(chapter_id)

    @app.get("/api/chapters/{chapter_id}/creative-scene-states", response_model=list[dict[str, Any]])
    def list_creative_scene_states(chapter_id: int) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        project = _require_project(project_service, chapter.project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(409, "legacy_extract_workflow", "Legacy extract projects use their dedicated workflow.")
        return creative_workflow_service.list_scene_states(chapter_id)

    @app.get("/api/scenes/{scene_id}/creative-workflow", response_model=dict[str, Any])
    def get_creative_scene_state(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_scene_state(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/creative-workflow/activate",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def activate_creative_scene(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.activate_scene(scene_id)

    @app.put(
        "/api/chapters/{chapter_id}/creative-workflow",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def update_creative_workflow_state(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        project = _require_project(project_service, chapter.project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(409, "legacy_extract_workflow", "Legacy extract projects use their dedicated workflow.")
        return creative_workflow_service.update_chapter_state(
            chapter_id,
            active_scene_id=(int(payload["active_scene_id"]) if payload.get("active_scene_id") is not None else None),
            current_stage=str(payload.get("current_stage") or "not_started"),
        )

    @app.get("/api/scenes/{scene_id}/preanalysis", response_model=dict[str, Any] | None)
    def get_scene_preanalysis(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_preanalysis(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/preanalysis/run",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def run_scene_preanalysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.run_preanalysis(
            scene_id, replace_existing=bool(payload.get("replace_existing", False))
        )

    @app.put(
        "/api/scenes/{scene_id}/preanalysis",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_preanalysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_preanalysis(scene_id, payload, user_edited=True)

    @app.post(
        "/api/scenes/{scene_id}/preanalysis/confirm",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def confirm_scene_preanalysis(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.confirm_preanalysis(scene_id)

    @app.get("/api/scenes/{scene_id}/creative-intent", response_model=dict[str, Any] | None)
    def get_scene_creative_intent(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_intent(scene_id)

    @app.put(
        "/api/scenes/{scene_id}/creative-intent",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_creative_intent(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_intent(scene_id, payload)

    @app.get(
        "/api/scenes/{scene_id}/character-modification-analysis",
        response_model=dict[str, Any] | None,
    )
    def get_character_modification_analysis(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_character_modification_analysis(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/character-modification-analysis/run",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def run_character_modification_analysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.run_character_modification_analysis(
            scene_id,
            source_character=str(payload.get("source_character") or ""),
            target_character_card_id=int(payload.get("target_character_card_id") or 0),
            replace_existing=bool(payload.get("replace_existing", False)),
        )

    @app.put(
        "/api/scenes/{scene_id}/character-modification-analysis",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_character_modification_analysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_character_modification_analysis(scene_id, payload)

    @app.post(
        "/api/scenes/{scene_id}/character-modification-analysis/confirm",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def confirm_character_modification_analysis(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.confirm_character_modification_analysis(scene_id)

    @app.get("/api/scenes/{scene_id}/strategy-analysis", response_model=dict[str, Any] | None)
    def get_strategy_analysis(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_strategy_analysis(scene_id)

    @app.post("/api/scenes/{scene_id}/strategy-analysis/run", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def run_strategy_analysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.run_strategy_analysis(scene_id, replace_existing=bool(payload.get("replace_existing", False)))

    @app.put("/api/scenes/{scene_id}/strategy-analysis", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def save_strategy_analysis(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_strategy_analysis(scene_id, payload)

    @app.post("/api/scenes/{scene_id}/strategy-analysis/confirm", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def confirm_strategy_analysis(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.confirm_strategy_analysis(scene_id)

    @app.get("/api/scenes/{scene_id}/target", response_model=dict[str, Any] | None)
    def get_scene_target(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_target(scene_id)

    @app.post("/api/scenes/{scene_id}/target/run", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def run_scene_target(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.run_target_design(scene_id, replace_existing=bool(payload.get("replace_existing", False)))

    @app.put("/api/scenes/{scene_id}/target", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def save_scene_target(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_target(scene_id, payload)

    @app.post("/api/scenes/{scene_id}/target/confirm", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def confirm_scene_target(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.confirm_target(scene_id)

    @app.get("/api/scenes/{scene_id}/writing-plan", response_model=dict[str, Any] | None)
    def get_writing_plan(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_writing_plan(scene_id)

    @app.post("/api/scenes/{scene_id}/writing-plan/run", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def run_writing_plan(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.run_writing_plan(scene_id, replace_existing=bool(payload.get("replace_existing", False)))

    @app.put("/api/scenes/{scene_id}/writing-plan", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def save_writing_plan(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_writing_plan(scene_id, payload)

    @app.get("/api/scenes/{scene_id}/current-draft", response_model=dict[str, Any] | None)
    def get_current_draft(scene_id: int) -> dict[str, Any] | None:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_current_draft(scene_id)

    @app.post("/api/scenes/{scene_id}/current-draft/generate", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def generate_current_draft(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.generate_current_draft(scene_id, replace_existing=bool(payload.get("replace_existing", False)))

    @app.put("/api/scenes/{scene_id}/current-draft", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def save_current_draft(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_current_draft(scene_id, payload)

    @app.post("/api/scenes/{scene_id}/current-draft/selected-edit", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def edit_selected_draft(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.edit_selected_draft_text(scene_id, start_offset=int(payload.get("start_offset") or 0), end_offset=int(payload.get("end_offset") or 0), user_instruction=str(payload.get("user_instruction") or ""))

    @app.post("/api/scenes/{scene_id}/writing-blocks/{block_id}/regenerate", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def regenerate_writing_block(scene_id: int, block_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.regenerate_writing_block(scene_id, block_id, current_start_offset=int(payload.get("current_start_offset") or 0), current_end_offset=int(payload.get("current_end_offset") or 0))

    @app.get("/api/scenes/{scene_id}/review-diff", response_model=dict[str, Any])
    def get_review_diff(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.get_review_diff(scene_id)

    @app.post("/api/scenes/{scene_id}/review/start", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def start_scene_review(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.start_review(scene_id)

    @app.get("/api/scenes/{scene_id}/review-marks", response_model=list[dict[str, Any]])
    def list_review_marks(scene_id: int) -> list[dict[str, Any]]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.list_review_marks(scene_id)

    @app.post("/api/scenes/{scene_id}/review-marks", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def save_review_mark(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.save_review_mark(scene_id, payload)

    @app.delete("/api/scenes/{scene_id}/review-marks/{mark_id}", dependencies=[Depends(_require_token)])
    def delete_review_mark(scene_id: int, mark_id: int) -> dict[str, bool]:
        _require_scene(scene_service, scene_id)
        creative_workflow_service.delete_review_mark(scene_id, mark_id)
        return {"ok": True}

    @app.post("/api/scenes/{scene_id}/review-marks/{mark_id}/restore", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def restore_review_source(scene_id: int, mark_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.restore_review_source(scene_id, mark_id)

    @app.post("/api/scenes/{scene_id}/review/rework", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def rework_review_range(scene_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.rework_review_range(scene_id, target_start_offset=int(payload.get("target_start_offset") or 0), target_end_offset=int(payload.get("target_end_offset") or 0), source_start_offset=payload.get("source_start_offset"), source_end_offset=payload.get("source_end_offset"), user_instruction=str(payload.get("user_instruction") or ""), mark_id=int(payload["mark_id"]) if payload.get("mark_id") is not None else None)

    @app.post("/api/scenes/{scene_id}/review/rework-all", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def rework_all_review_marks(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.rework_all_review_marks(scene_id)

    @app.post("/api/scenes/{scene_id}/review/adopt", response_model=list[dict[str, Any]], dependencies=[Depends(_require_token)])
    def adopt_review_rework(scene_id: int, payload: dict[str, Any]) -> list[dict[str, Any]]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.resolve_review_marks(scene_id, payload.get("mark_ids") or [])

    @app.post("/api/scenes/{scene_id}/confirm", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def confirm_creative_scene(scene_id: int) -> dict[str, Any]:
        _require_scene(scene_service, scene_id)
        return creative_workflow_service.confirm_scene(scene_id)

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
            rewrite_mode=payload.rewrite_mode,
            max_attempts=payload.max_attempts,
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
        project = _require_project(project_service, project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(
                409,
                "legacy_extract_read_only",
                "Legacy extract projects are read-only and cannot run the retired pipeline.",
            )
        result = pipeline_service.run_project(project_id)
        return PipelineRunResponse(
            ok=True,
            processed=result.processed,
            skipped=result.skipped,
            failed=result.failed,
            paused=result.paused,
        )

    @app.post("/api/projects/{project_id}/pipeline/summarize", response_model=PipelineRunResponse, dependencies=[Depends(_require_token)])
    def run_project_summary(project_id: int) -> PipelineRunResponse:
        project = _require_project(project_service, project_id)
        if project.project_kind == "legacy_extract":
            raise _http_error(
                409,
                "legacy_extract_read_only",
                "Legacy extract projects are read-only and cannot run the retired pipeline.",
            )
        result = pipeline_service.run_document_analysis(project_id)
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

    @app.get("/api/chapters/{chapter_id}/prompt-preview", response_model=dict[str, Any])
    def preview_chapter_prompt(chapter_id: int, stage: str = "rewrite") -> dict[str, Any]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return pipeline_service.preview_chapter_prompt(chapter_id, stage)

    @app.get("/api/chapters/{chapter_id}/generation-attempts", response_model=list[dict[str, Any]])
    def list_generation_attempts(chapter_id: int, stage: str | None = None) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return pipeline_service.list_generation_attempts(chapter_id, stage)

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
        document_library_service.sync_project_document(chapter.project_id)
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
        document_library_service.sync_project_document(chapter.project_id)
        return _chapter_detail(_require_existing_chapter(project_service, chapter_id), pipeline_service)

    @app.get("/api/chapters/{chapter_id}/scenes", response_model=list[dict[str, Any]])
    def list_chapter_scenes(chapter_id: int) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return [scene.__dict__ for scene in scene_service.list_scenes(chapter_id)]

    @app.post(
        "/api/chapters/{chapter_id}/scenes/analyze",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(_require_token)],
    )
    def analyze_chapter_scenes(chapter_id: int, payload: SceneBoundaryWriteRequest) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        if payload.source == "ai" and payload.boundaries is None:
            scenes = scene_boundary_ai_service.analyze(
                chapter_id,
                model_id=payload.model_id,
            )["scenes"]
        elif payload.source == "heuristic" and payload.boundaries is None:
            scenes = scene_service.split_chapter(chapter_id, source="heuristic")
        elif payload.boundaries is not None:
            scenes = scene_service.split_chapter(
                chapter_id,
                proposed_boundaries=[item.model_dump() for item in payload.boundaries],
                source=payload.source,
            )
        else:
            raise _http_error(
                400,
                "scene_boundary_source_invalid",
                "Scene analysis source must be ai or heuristic.",
            )
        if payload.confirm:
            scenes = scene_service.confirm_boundaries(chapter_id)
        creative_workflow_service.reconcile_chapter_scenes(chapter_id)
        return [scene.__dict__ for scene in scenes]

    @app.post(
        "/api/chapters/{chapter_id}/scenes/adjust",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(_require_token)],
    )
    def adjust_chapter_scenes(chapter_id: int, payload: SceneBoundaryWriteRequest) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        if payload.boundaries is None:
            raise _http_error(400, "scene_boundaries_required", "Manual scene adjustment requires boundaries.")
        scenes = scene_service.adjust_boundaries(
            chapter_id,
            [item.model_dump() for item in payload.boundaries],
        )
        creative_workflow_service.reconcile_chapter_scenes(chapter_id)
        return [scene.__dict__ for scene in scenes]

    @app.post(
        "/api/chapters/{chapter_id}/scenes/confirm",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(_require_token)],
    )
    def confirm_chapter_scenes(chapter_id: int) -> list[dict[str, Any]]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        scenes = scene_service.confirm_boundaries(chapter_id)
        creative_workflow_service.reconcile_chapter_scenes(chapter_id)
        return [scene.__dict__ for scene in scenes]

    @app.get("/api/scenes/{scene_id}/facts", response_model=dict[str, Any])
    def get_scene_facts(scene_id: int) -> dict[str, Any]:
        return scene_service.get_fact_ledger(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/facts",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_facts(scene_id: int, payload: SceneFactLedgerWriteRequest) -> dict[str, Any]:
        return scene_service.save_fact_ledger(
            scene_id,
            payload.facts,
            source_kind=payload.source_kind,
            model_id=payload.model_id,
            prompt_compilation_id=payload.prompt_compilation_id,
        )

    @app.get("/api/scenes/{scene_id}/character-states", response_model=list[dict[str, Any]])
    def list_scene_character_states(scene_id: int) -> list[dict[str, Any]]:
        return scene_service.list_character_states(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/character-states",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_character_state(scene_id: int, payload: CharacterStoryStateWriteRequest) -> dict[str, Any]:
        return scene_service.save_character_state(
            scene_id,
            payload.character_name,
            payload.state,
            character_card_id=payload.character_card_id,
        )

    @app.post(
        "/api/story-skeletons",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def create_story_skeleton(payload: StorySkeletonWriteRequest) -> dict[str, Any]:
        values = payload.model_dump()
        structured = values.pop("structured_skeleton")
        if structured is not None:
            values.pop("nodes")
            values["skeleton"] = structured
            value = rewrite_workflow_service.create_structured_skeleton(**values)
        else:
            value = rewrite_workflow_service.create_skeleton(**values)
        return value.__dict__

    @app.post(
        "/api/story-skeletons/{skeleton_id}/versions",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def revise_story_skeleton(skeleton_id: int, payload: StorySkeletonRevisionRequest) -> dict[str, Any]:
        if payload.structured_skeleton is not None:
            return rewrite_workflow_service.revise_structured_skeleton(
                skeleton_id,
                payload.structured_skeleton,
                change_note=payload.change_note,
            ).__dict__
        return rewrite_workflow_service.revise_skeleton(
            skeleton_id, payload.nodes, change_note=payload.change_note
        ).__dict__

    @app.get("/api/chapters/{chapter_id}/story-skeleton", response_model=dict[str, Any])
    def get_chapter_story_skeleton(chapter_id: int) -> dict[str, Any]:
        skeleton = rewrite_workflow_service.get_preferred_chapter_skeleton(chapter_id)
        if not skeleton:
            raise FileNotFoundError(f"Story skeleton not found for chapter: {chapter_id}")
        return skeleton

    @app.get(
        "/api/story-skeletons/{skeleton_id}/versions/{version}",
        response_model=dict[str, Any],
    )
    def get_story_skeleton_version(skeleton_id: int, version: int) -> dict[str, Any]:
        return rewrite_workflow_service.get_skeleton_version(skeleton_id, version).__dict__

    @app.post(
        "/api/story-skeletons/{skeleton_id}/confirm",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def confirm_story_skeleton(skeleton_id: int, version: int | None = None) -> dict[str, Any]:
        return rewrite_workflow_service.confirm_skeleton(skeleton_id, version).__dict__

    @app.post(
        "/api/rewrite-plans",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def create_rewrite_plan(payload: RewritePlanWriteRequest) -> dict[str, Any]:
        values = payload.model_dump()
        mode = values.pop("mode")
        material_mappings = values.pop("material_mappings")
        if mode == "skeleton_rewrite":
            plan_id = rewrite_workflow_service.create_skeleton_rewrite_plan(**values)
        else:
            plan_id = rewrite_workflow_service.create_expansion_plan(
                **values,
                material_mappings=material_mappings,
            )
        return rewrite_workflow_service.get_plan(plan_id)

    @app.get("/api/rewrite-plans/{plan_id}", response_model=dict[str, Any])
    def get_rewrite_plan(plan_id: int) -> dict[str, Any]:
        return rewrite_workflow_service.get_plan(plan_id)

    @app.post(
        "/api/rewrite-plans/{plan_id}/confirm",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def confirm_rewrite_plan(plan_id: int) -> dict[str, Any]:
        return rewrite_workflow_service.confirm_plan(plan_id)

    @app.post(
        "/api/scenes/{scene_id}/stages",
        response_model=dict[str, int],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_stage(scene_id: int, payload: SceneStageWriteRequest) -> dict[str, int]:
        stage_id = rewrite_workflow_service.save_stage_output(
            scene_id,
            payload.stage,
            payload.output,
            plan_id=payload.plan_id,
            prompt_compilation_id=payload.prompt_compilation_id,
            status=payload.status,
        )
        return {"id": stage_id}

    @app.post(
        "/api/scenes/{scene_id}/retrieval",
        response_model=list[dict[str, Any]],
        dependencies=[Depends(_require_token)],
    )
    def retrieve_scene_context(scene_id: int, payload: SceneRetrievalRequest) -> list[dict[str, Any]]:
        return context_service.retrieve(scene_id, **payload.model_dump())

    @app.post(
        "/api/scenes/{scene_id}/prompt-compile",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def compile_scene_prompt(scene_id: int, payload: SceneContextCompileRequest) -> dict[str, Any]:
        return context_service.compile_scene_context(scene_id, **payload.model_dump())

    @app.post(
        "/api/scenes/{scene_id}/rewrite-versions",
        response_model=dict[str, int],
        dependencies=[Depends(_require_token)],
    )
    def save_scene_rewrite_version(scene_id: int, payload: SceneRewriteVersionWriteRequest) -> dict[str, int]:
        version_id = rewrite_workflow_service.save_rewrite_version(
            scene_id,
            payload.rewritten_text,
            plan_id=payload.plan_id,
            skeleton_version_id=payload.skeleton_version_id,
            prompt_compilation_id=payload.prompt_compilation_id,
            facts_after=payload.facts_after,
        )
        return {"id": version_id}

    @app.post(
        "/api/scenes/{scene_id}/targeted-repairs",
        response_model=dict[str, int],
        dependencies=[Depends(_require_token)],
    )
    def save_targeted_repair(scene_id: int, payload: TargetedRepairWriteRequest) -> dict[str, int]:
        repair_id = rewrite_workflow_service.targeted_repair(scene_id=scene_id, **payload.model_dump())
        return {"id": repair_id}

    @app.post(
        "/api/consistency-checks",
        response_model=dict[str, int],
        dependencies=[Depends(_require_token)],
    )
    def save_consistency_check(payload: ConsistencyCheckWriteRequest) -> dict[str, int]:
        check_id = rewrite_workflow_service.save_consistency_check(**payload.model_dump())
        return {"id": check_id}

    @app.get("/api/chapters/{chapter_id}/continuity-check", response_model=dict[str, Any])
    def check_chapter_continuity(chapter_id: int) -> dict[str, Any]:
        chapter = _require_existing_chapter(project_service, chapter_id)
        _require_project(project_service, chapter.project_id)
        return rewrite_workflow_service.build_chapter_check(chapter_id)

    @app.get("/api/projects/{project_id}/book-consistency-check", response_model=dict[str, Any])
    def check_project_book_consistency(project_id: int) -> dict[str, Any]:
        _require_project(project_service, project_id)
        return rewrite_workflow_service.build_book_check(project_id)

    @app.post(
        "/api/scenes/{scene_id}/workflow/start",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def start_scene_workflow(scene_id: int, payload: SceneWorkflowStartRequest) -> dict[str, Any]:
        return scene_rewrite_orchestrator.start(scene_id, **payload.model_dump())

    @app.post(
        "/api/scene-workflows/{run_id}/plan",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def generate_scene_workflow_plan(run_id: int, payload: SceneWorkflowPlanRequest) -> dict[str, Any]:
        return scene_rewrite_orchestrator.generate_plan(run_id, **payload.model_dump())

    @app.post(
        "/api/scene-workflows/{run_id}/execute",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def execute_scene_workflow(run_id: int, payload: SceneWorkflowExecuteRequest) -> dict[str, Any]:
        return scene_rewrite_orchestrator.execute(run_id, **payload.model_dump())

    @app.get("/api/scene-workflows/{run_id}", response_model=dict[str, Any])
    def get_scene_workflow(run_id: int) -> dict[str, Any]:
        return scene_rewrite_orchestrator.get_run(run_id)

    @app.get("/api/scenes/{scene_id}/rewrite-history", response_model=list[dict[str, Any]])
    def get_scene_rewrite_history(scene_id: int) -> list[dict[str, Any]]:
        return scene_rewrite_orchestrator.list_scene_history(scene_id)

    @app.post(
        "/api/scenes/{scene_id}/rewrite-history/{version_id}/restore",
        response_model=dict[str, int],
        dependencies=[Depends(_require_token)],
    )
    def restore_scene_rewrite_version(scene_id: int, version_id: int) -> dict[str, int]:
        return {"id": scene_rewrite_orchestrator.restore_version(scene_id, version_id)}

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

    @app.get("/api/prompt-definitions", response_model=list[dict[str, Any]])
    def list_prompt_definitions() -> list[dict[str, Any]]:
        return [item.__dict__ for item in prompt_definition_service.list_definitions()]

    @app.post(
        "/api/prompt-definitions",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def create_prompt_definition(payload: dict[str, Any]) -> dict[str, Any]:
        return prompt_definition_service.create_definition(**payload).__dict__

    @app.put(
        "/api/prompt-definitions/{definition_id}",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def update_prompt_definition(definition_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        return prompt_definition_service.update_definition(definition_id, **payload).__dict__

    @app.post(
        "/api/prompt-definitions/{definition_id}/copy",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def copy_prompt_definition(definition_id: int) -> dict[str, Any]:
        return prompt_definition_service.duplicate_definition(definition_id).__dict__

    @app.post(
        "/api/prompt-definitions/{definition_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_prompt_definition(definition_id: int) -> dict[str, bool]:
        prompt_definition_service.delete_definition(definition_id)
        return {"ok": True}

    @app.post(
        "/api/prompt-definitions/{definition_id}/export",
        response_model=dict[str, str],
        dependencies=[Depends(_require_token)],
    )
    def export_prompt_definition(definition_id: int) -> dict[str, str]:
        return {"content": prompt_definition_service.export_definition(definition_id)}

    @app.post(
        "/api/prompt-definitions/import",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def import_prompt_definition(payload: dict[str, str]) -> dict[str, Any]:
        return prompt_definition_service.import_definition(payload.get("content", "")).__dict__

    @app.get("/api/projects/{project_id}/master-prompt", response_model=dict[str, Any])
    def get_project_master_prompt(project_id: int) -> dict[str, Any]:
        _require_project(project_service, project_id)
        return prompt_definition_service.get_project_master(project_id)

    @app.put(
        "/api/projects/{project_id}/master-prompt",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def save_project_master_prompt(project_id: int, payload: dict[str, str]) -> dict[str, Any]:
        _require_project(project_service, project_id)
        return prompt_definition_service.save_project_master(project_id, payload.get("content", ""))

    @app.post(
        "/api/projects/{project_id}/master-prompt/export",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def export_project_master_prompt(project_id: int, payload: dict[str, str]) -> dict[str, Any]:
        _require_project(project_service, project_id)
        return prompt_definition_service.export_project_master(
            project_id,
            name=payload.get("name", "").strip() or "工程总提示词",
            description=payload.get("description", ""),
        ).__dict__

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

    @app.get("/api/materials", response_model=list[MaterialOut])
    def list_materials(
        scope: str | None = None,
        project_id: int | None = None,
        material_type: str | None = None,
        tag_id: int | None = None,
        tag_group: str | None = None,
        category_id: int | None = None,
        analysis_status: str | None = None,
        pending_imports: bool = False,
        untagged: bool = False,
        query: str | None = None,
        limit: int | None = None,
        offset: int = 0,
    ) -> list[MaterialOut]:
        return [
            _material_out(item)
            for item in material_service.list_materials(
                scope=scope,
                project_id=project_id,
                material_type=material_type,
                tag_id=tag_id,
                tag_group=tag_group,
                category_id=category_id,
                analysis_status=analysis_status,
                pending_imports=pending_imports,
                untagged=untagged,
                query=query,
                limit=limit,
                offset=offset,
            )
        ]

    @app.get("/api/material-tags", response_model=list[ResourceTagOut])
    def list_material_tags(tag_group: str | None = None) -> list[ResourceTagOut]:
        return [_resource_tag_out(tag) for tag in material_service.list_tags(tag_group)]

    @app.post("/api/material-tags", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def create_material_tag(payload: ResourceTagCreateRequest) -> ResourceTagOut:
        return _resource_tag_out(
            material_service.create_tag(payload.name, tag_group=payload.tag_group)
        )

    @app.post("/api/material-tags/{tag_id}", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def rename_material_tag(tag_id: int, payload: ResourceTagRenameRequest) -> ResourceTagOut:
        return _resource_tag_out(material_service.rename_tag(tag_id, payload.name))

    @app.post("/api/material-tags/{tag_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_material_tag(tag_id: int) -> dict[str, bool]:
        material_service.delete_tag(tag_id)
        return {"ok": True}

    @app.post(
        "/api/materials/{material_id}/tags/{tag_id}",
        response_model=MaterialOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_material_tag(material_id: int, tag_id: int, payload: ResourceTagAssignmentRequest) -> MaterialOut:
        return _material_out(material_service.set_material_tag(material_id, tag_id, payload.selected))

    @app.get("/api/material-categories", response_model=list[MaterialCategoryOut])
    def list_material_categories(material_type: str | None = None) -> list[MaterialCategoryOut]:
        return [
            MaterialCategoryOut(**item.__dict__)
            for item in material_service.list_categories(material_type)
        ]

    @app.post(
        "/api/material-categories",
        response_model=MaterialCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def create_material_category(payload: MaterialCategoryCreateRequest) -> MaterialCategoryOut:
        return MaterialCategoryOut(
            **material_service.create_category(payload.material_type, payload.name).__dict__
        )

    @app.post(
        "/api/material-categories/{category_id}",
        response_model=MaterialCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def rename_material_category(
        category_id: int,
        payload: ResourceTagRenameRequest,
    ) -> MaterialCategoryOut:
        return MaterialCategoryOut(
            **material_service.rename_category(category_id, payload.name).__dict__
        )

    @app.post(
        "/api/material-categories/{category_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_material_category(category_id: int) -> dict[str, bool]:
        material_service.delete_category(category_id)
        return {"ok": True}

    @app.post(
        "/api/materials/{material_id}/categories/{category_id}",
        response_model=MaterialOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_material_category(
        material_id: int,
        category_id: int,
        payload: ResourceTagAssignmentRequest,
    ) -> MaterialOut:
        return _material_out(
            material_service.set_material_category(material_id, category_id, payload.selected)
        )

    @app.get(
        "/api/projects/{project_id}/material-filters",
        response_model=list[ProjectMaterialFilterOut],
    )
    def get_project_material_filters(project_id: int) -> list[ProjectMaterialFilterOut]:
        return [
            ProjectMaterialFilterOut(
                project_id=item.project_id,
                material_type=item.material_type,
                match_mode=item.match_mode,
                tag_ids=list(item.tag_ids),
                manual_material_ids=list(item.manual_material_ids),
                include_scene_keywords=item.include_scene_keywords,
                include_applicable_scene_tags=item.include_applicable_scene_tags,
            )
            for item in material_service.get_project_material_filters(project_id)
        ]

    @app.get("/api/projects/{project_id}/materials", response_model=list[MaterialOut])
    def list_project_materials(
        project_id: int,
        material_type: str | None = None,
    ) -> list[MaterialOut]:
        return [
            _material_out(item)
            for item in material_service.list_materials_for_project(
                project_id,
                material_type=material_type,
            )
        ]

    @app.post(
        "/api/projects/{project_id}/material-filters/{material_type}",
        response_model=ProjectMaterialFilterOut,
        dependencies=[Depends(_require_token)],
    )
    def set_project_material_filter(
        project_id: int,
        material_type: str,
        payload: ProjectMaterialFilterWriteRequest,
    ) -> ProjectMaterialFilterOut:
        item = material_service.set_project_material_filter(
            project_id,
            material_type,
            **payload.model_dump(),
        )
        return ProjectMaterialFilterOut(
            project_id=item.project_id,
            material_type=item.material_type,
            match_mode=item.match_mode,
            tag_ids=list(item.tag_ids),
            manual_material_ids=list(item.manual_material_ids),
            include_scene_keywords=item.include_scene_keywords,
            include_applicable_scene_tags=item.include_applicable_scene_tags,
        )

    @app.get("/api/material-ai-settings", response_model=list[MaterialAISettingsOut])
    def list_material_ai_settings() -> list[MaterialAISettingsOut]:
        return [_material_ai_settings_out(item) for item in material_service.list_ai_settings()]

    @app.get("/api/material-ai-settings/{task_type}", response_model=MaterialAISettingsOut)
    def get_material_ai_settings(task_type: str) -> MaterialAISettingsOut:
        return _material_ai_settings_out(material_service.get_ai_settings(task_type))

    @app.post(
        "/api/material-ai-settings/{task_type}",
        response_model=MaterialAISettingsOut,
        dependencies=[Depends(_require_token)],
    )
    def update_material_ai_settings(
        task_type: str,
        payload: MaterialAISettingsWriteRequest,
    ) -> MaterialAISettingsOut:
        return _material_ai_settings_out(
            material_service.update_ai_settings(task_type, **payload.model_dump())
        )

    @app.get("/api/author-style-settings/export")
    def export_author_style_settings() -> dict[str, Any]:
        return material_service.export_author_style_settings()

    @app.post(
        "/api/author-style-settings/import",
        response_model=MaterialAISettingsOut,
        dependencies=[Depends(_require_token)],
    )
    def import_author_style_settings(payload: MaterialAISettingsImportRequest) -> MaterialAISettingsOut:
        return _material_ai_settings_out(material_service.import_author_style_settings(payload.value))

    @app.post("/api/materials", response_model=MaterialOut, dependencies=[Depends(_require_token)])
    def create_material(payload: MaterialWriteRequest) -> MaterialOut:
        material_id = material_service.create_material(**payload.model_dump())
        material = material_service.get_material(material_id)
        if material is None:
            raise _http_error(500, "material_create_failed", "素材已创建但无法读取。")
        return _material_out(material)

    @app.post("/api/materials/import", response_model=MaterialOut, dependencies=[Depends(_require_token)])
    def import_material(payload: MaterialWriteRequest) -> MaterialOut:
        material_id = material_service.create_material(
            **{
                **payload.model_dump(),
                "import_metadata": {
                    **payload.import_metadata,
                    "created_by": "json_import",
                },
            }
        )
        material = material_service.get_material(material_id)
        if material is None:
            raise _http_error(500, "material_import_failed", "素材已导入但无法读取。")
        return _material_out(material)

    @app.post(
        "/api/materials/import-json",
        response_model=dict[str, list[dict[str, Any]]],
        dependencies=[Depends(_require_token)],
    )
    def import_material_json(payload: MaterialJsonImportRequest) -> dict[str, list[dict[str, Any]]]:
        return material_service.import_json_items(
            payload.value,
            default_scope=payload.default_scope,
            default_project_id=payload.default_project_id,
        )

    @app.get("/api/materials/{material_id}", response_model=MaterialOut)
    def get_material(material_id: int) -> MaterialOut:
        material = material_service.get_material(material_id)
        if material is None:
            raise _http_error(404, "material_not_found", f"找不到素材：{material_id}")
        return _material_out(material)

    @app.post("/api/materials/{material_id}", response_model=MaterialOut, dependencies=[Depends(_require_token)])
    def update_material(material_id: int, payload: MaterialUpdateRequest) -> MaterialOut:
        material_service.update_material(material_id, **payload.model_dump())
        material = material_service.get_material(material_id)
        if material is None:
            raise _http_error(404, "material_not_found", f"找不到素材：{material_id}")
        return _material_out(material)

    @app.post(
        "/api/materials/{material_id}/copy",
        response_model=MaterialOut,
        dependencies=[Depends(_require_token)],
    )
    def copy_material(material_id: int, payload: MaterialCopyRequest) -> MaterialOut:
        copied_id = material_service.copy_material(
            material_id,
            target_scope=payload.target_scope,
            target_project_id=payload.target_project_id,
            tag_ids=payload.tag_ids,
        )
        copied = material_service.get_material(copied_id)
        if copied is None:
            raise _http_error(500, "material_copy_failed", "素材副本已创建但无法读取。")
        return _material_out(copied)

    @app.post(
        "/api/materials/{material_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_material(material_id: int) -> dict[str, bool]:
        material_service.delete_material(material_id)
        return {"ok": True}

    @app.post("/api/materials/{material_id}/analyze", response_model=dict[str, Any], dependencies=[Depends(_require_token)])
    def analyze_material(material_id: int, payload: MaterialAnalyzeRequest) -> dict[str, Any]:
        proposal = resource_analysis_service.propose_material_analysis(material_id, model_id=payload.model_id)
        proposal.pop("_result", None)
        return proposal

    @app.post(
        "/api/materials/{material_id}/analysis/apply",
        response_model=MaterialOut,
        dependencies=[Depends(_require_token)],
    )
    def apply_material_analysis(material_id: int, payload: MaterialAnalysisApplyRequest) -> MaterialOut:
        return _material_out(
            resource_analysis_service.apply_material_analysis(
                material_id,
                content=payload.content,
                model_id=payload.model_id,
                invocation_id=payload.invocation_id,
            )
        )

    @app.post(
        "/api/material-extractions/preview",
        response_model=MaterialExtractionPreviewOut,
        dependencies=[Depends(_require_token)],
    )
    def preview_material_extraction(
        payload: MaterialExtractionPreviewRequest,
    ) -> MaterialExtractionPreviewOut:
        text, resolved_metadata = _resolve_anchor_source(
            payload,
            project_service=project_service,
            document_library_service=document_library_service,
        )
        preview = anchor_extraction_service.preview_materials_from_text(
            text,
            task_type=payload.task_type,
            name=payload.name,
            model_id=payload.model_id,
            source_metadata={**resolved_metadata, **payload.source_metadata},
        )
        return MaterialExtractionPreviewOut(
            preview_token=preview.preview_token,
            expires_at=preview.expires_at,
            task_type=preview.task_type,
            material_type=preview.material_type,
            source_summary=preview.source_summary,
            prompt_snapshot=preview.prompt_snapshot,
            candidates=[
                MaterialExtractionCandidateOut(**candidate.__dict__)
                for candidate in preview.candidates
            ],
        )

    @app.post(
        "/api/material-extractions/apply",
        response_model=MaterialExtractionApplyOut,
        dependencies=[Depends(_require_token)],
    )
    def apply_material_extraction(
        payload: MaterialExtractionApplyRequest,
    ) -> MaterialExtractionApplyOut:
        result = anchor_extraction_service.apply_material_extraction(
            **payload.model_dump()
        )
        return MaterialExtractionApplyOut(
            created=result["created"],
            errors=result["errors"],
        )

    @app.post(
        "/api/materials/{material_id}/author-style/dimensions/preview",
        response_model=AuthorStyleDimensionPreviewOut,
        dependencies=[Depends(_require_token)],
    )
    def preview_author_style_dimension(
        material_id: int,
        payload: AuthorStyleDimensionPreviewRequest,
    ) -> AuthorStyleDimensionPreviewOut:
        return AuthorStyleDimensionPreviewOut(
            **anchor_extraction_service.preview_author_style_dimension(
                material_id, **payload.model_dump()
            )
        )

    @app.post(
        "/api/materials/{material_id}/author-style/dimensions/apply",
        response_model=MaterialOut,
        dependencies=[Depends(_require_token)],
    )
    def apply_author_style_dimension(
        material_id: int,
        payload: AuthorStyleDimensionApplyRequest,
    ) -> MaterialOut:
        return _material_out(
            anchor_extraction_service.apply_author_style_dimension(
                material_id, preview_token=payload.preview_token
            )
        )

    @app.post("/api/material-extractions", response_model=MaterialExtractOut, dependencies=[Depends(_require_token)])
    def extract_materials(payload: MaterialExtractRequest) -> MaterialExtractOut:
        text, source_metadata = _resolve_anchor_source(
            payload,
            project_service=project_service,
            document_library_service=document_library_service,
        )
        material_ids = anchor_extraction_service.extract_materials_from_text(
            text,
            material_type=payload.material_type,
            scope=payload.scope,
            project_id=payload.project_id,
            name=payload.name,
            detail_level=payload.detail_level,
            model_id=payload.model_id,
            source_metadata=source_metadata,
        )
        materials = [material_service.get_material(material_id) for material_id in material_ids]
        return MaterialExtractOut(materials=[_material_out(item) for item in materials if item is not None])

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
    def list_character_cards(
        scope: str | None = None,
        project_id: int | None = None,
        tag_id: int | None = None,
        category_id: int | None = None,
        analysis_status: str | None = None,
        untagged: bool = False,
    ) -> list[CharacterCardOut]:
        return [
            _character_out(card)
            for card in anchor_service.list_character_cards(
                scope,
                project_id,
                tag_id=tag_id,
                category_id=category_id,
                analysis_status=analysis_status,
                untagged=untagged,
            )
        ]

    @app.get("/api/character-categories", response_model=list[CharacterCategoryOut])
    def list_character_categories() -> list[CharacterCategoryOut]:
        return [
            CharacterCategoryOut(
                id=category.id,
                name=category.name,
                normalized_name=category.normalized_name,
                sort_order=category.sort_order,
                resource_count=category.resource_count,
            )
            for category in anchor_service.list_character_categories()
        ]

    @app.post(
        "/api/character-categories",
        response_model=CharacterCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def create_character_category(payload: ResourceTagCreateRequest) -> CharacterCategoryOut:
        category = anchor_service.create_character_category(payload.name)
        return CharacterCategoryOut(
            id=category.id,
            name=category.name,
            normalized_name=category.normalized_name,
            sort_order=category.sort_order,
            resource_count=category.resource_count,
        )

    @app.post(
        "/api/character-categories/{category_id}",
        response_model=CharacterCategoryOut,
        dependencies=[Depends(_require_token)],
    )
    def rename_character_category(
        category_id: int,
        payload: ResourceTagRenameRequest,
    ) -> CharacterCategoryOut:
        category = anchor_service.rename_character_category(category_id, payload.name)
        return CharacterCategoryOut(
            id=category.id,
            name=category.name,
            normalized_name=category.normalized_name,
            sort_order=category.sort_order,
            resource_count=category.resource_count,
        )

    @app.post(
        "/api/character-categories/{category_id}/delete",
        response_model=dict[str, bool],
        dependencies=[Depends(_require_token)],
    )
    def delete_character_category(category_id: int) -> dict[str, bool]:
        anchor_service.delete_character_category(category_id)
        return {"ok": True}

    @app.post(
        "/api/characters/{card_id}/categories/{category_id}",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_character_category(
        card_id: int,
        category_id: int,
        payload: ResourceTagAssignmentRequest,
    ) -> CharacterCardOut:
        return _character_out(
            anchor_service.set_character_category(card_id, category_id, payload.selected)
        )

    @app.get(
        "/api/character-projects/summary",
        response_model=list[CharacterProjectSummaryOut],
    )
    def list_character_project_summaries() -> list[CharacterProjectSummaryOut]:
        return [
            CharacterProjectSummaryOut(
                project_id=project.project_id,
                project_name=project.project_name,
                character_count=project.character_count,
                updated_at=project.updated_at,
            )
            for project in anchor_service.list_character_project_summaries()
        ]

    @app.get("/api/character-tags", response_model=list[ResourceTagOut])
    def list_character_tags() -> list[ResourceTagOut]:
        return [ResourceTagOut(**tag) for tag in anchor_service.list_character_tags()]

    @app.post("/api/character-tags", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def create_character_tag(payload: ResourceTagCreateRequest) -> ResourceTagOut:
        return ResourceTagOut(**anchor_service.create_character_tag(payload.name))

    @app.post("/api/character-tags/{tag_id}", response_model=ResourceTagOut, dependencies=[Depends(_require_token)])
    def rename_character_tag(tag_id: int, payload: ResourceTagRenameRequest) -> ResourceTagOut:
        return ResourceTagOut(**anchor_service.rename_character_tag(tag_id, payload.name))

    @app.post("/api/character-tags/{tag_id}/delete", response_model=dict[str, bool], dependencies=[Depends(_require_token)])
    def delete_character_tag(tag_id: int) -> dict[str, bool]:
        anchor_service.delete_character_tag(tag_id)
        return {"ok": True}

    @app.post(
        "/api/characters/{card_id}/tags/{tag_id}",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def assign_character_tag(card_id: int, tag_id: int, payload: ResourceTagAssignmentRequest) -> CharacterCardOut:
        return _character_out(anchor_service.set_character_tag(card_id, tag_id, payload.selected))

    def _character_extraction_settings_out() -> CharacterExtractionSettingsOut:
        settings = anchor_extraction_service.get_character_extraction_settings()
        return CharacterExtractionSettingsOut(
            **{**settings.__dict__, "dimensions": list(settings.dimensions)},
            prompt_preview=(
                f"{settings.system_prompt}\n\n"
                f"Detail level: {settings.detail_level}\n"
                "Target character: {{TARGET_CHARACTER_NAME}}\n"
                f"Enabled dimensions: {json.dumps([item for item in settings.dimensions if item['enabled']], ensure_ascii=False)}\n"
                f"Additional requirements: {settings.custom_requirements or 'None'}\n"
                "JSON schema: {evidence_found,name,aliases,identity,age,description,stable_fields,suggested_tags}\n"
                "Source text: {{SOURCE_TEXT}}"
            ),
        )

    @app.get(
        "/api/character-extraction/settings",
        response_model=CharacterExtractionSettingsOut,
    )
    def get_character_extraction_settings() -> CharacterExtractionSettingsOut:
        return _character_extraction_settings_out()

    @app.post(
        "/api/character-extraction/settings",
        response_model=CharacterExtractionSettingsOut,
        dependencies=[Depends(_require_token)],
    )
    def update_character_extraction_settings(
        payload: CharacterExtractionSettingsWriteRequest,
    ) -> CharacterExtractionSettingsOut:
        anchor_extraction_service.update_character_extraction_settings(**payload.model_dump())
        return _character_extraction_settings_out()

    @app.post(
        "/api/character-extraction/settings/reset",
        response_model=CharacterExtractionSettingsOut,
        dependencies=[Depends(_require_token)],
    )
    def reset_character_extraction_settings() -> CharacterExtractionSettingsOut:
        anchor_extraction_service.reset_character_extraction_settings()
        return _character_extraction_settings_out()

    @app.post(
        "/api/characters/extract/preview",
        response_model=CharacterExtractionPreviewOut,
        dependencies=[Depends(_require_token)],
    )
    def preview_character_extraction(
        payload: CharacterExtractionPreviewRequest,
    ) -> CharacterExtractionPreviewOut:
        preview = anchor_extraction_service.preview_characters_from_text(
            payload.source_text,
            target_character_name=payload.target_character_name,
            detail_level=payload.detail_level,
            model_id=payload.model_id,
            source_metadata=payload.source_metadata,
        )
        return CharacterExtractionPreviewOut(
            preview_token=preview.preview_token,
            expires_at=preview.expires_at,
            character=CharacterExtractionDraftOut(**preview.character.__dict__),
        )

    @app.post(
        "/api/characters/extract/apply",
        response_model=CharacterExtractionApplyOut,
        dependencies=[Depends(_require_token)],
        deprecated=True,
    )
    def apply_character_extraction(
        payload: CharacterExtractionApplyRequest,
    ) -> CharacterExtractionApplyOut:
        result = anchor_extraction_service.apply_character_extraction(
            preview_token=payload.preview_token,
            candidates=[candidate.model_dump() for candidate in payload.candidates],
            selected_candidate_ids=payload.selected_candidate_ids,
            scope=payload.scope,
            project_id=payload.project_id,
            category_ids=payload.category_ids,
        )
        return CharacterExtractionApplyOut(
            created=[CharacterExtractionApplyItemOut(**item) for item in result["created"]],
            errors=[CharacterExtractionApplyItemOut(**item) for item in result["errors"]],
        )

    # Legacy compatibility endpoint. New clients must use preview then the normal character editor/save API.
    @app.post("/api/characters/extract", response_model=CharacterCardsExtractOut, dependencies=[Depends(_require_token)], deprecated=True)
    def extract_character_cards(payload: AnchorExtractRequest) -> CharacterCardsExtractOut:
        text, source_metadata = _resolve_anchor_source(
            payload,
            project_service=project_service,
            document_library_service=document_library_service,
        )
        card_ids = anchor_extraction_service.extract_characters_from_text(
            text,
            name=payload.name,
            detail_level=payload.detail_level,
            model_id=payload.model_id,
            source_metadata=source_metadata,
            scope=payload.scope,
            project_id=payload.project_id,
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

    @app.post("/api/characters/import", response_model=CharacterCardOut, dependencies=[Depends(_require_token)])
    def import_character_card(payload: CharacterCardWriteRequest) -> CharacterCardOut:
        values = payload.model_dump(exclude={"import_metadata"})
        card_id = anchor_service.create_character_card(
            **values,
            import_metadata={
                **payload.import_metadata,
                "created_by": "json_import",
            },
        )
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(500, "character_card_import_failed", "角色卡已导入但无法读取。")
        return _character_out(card)

    @app.post("/api/characters/{card_id}/copy", response_model=CharacterCardOut, dependencies=[Depends(_require_token)], deprecated=True)
    def copy_character_card(card_id: int, payload: CharacterCardCopyRequest) -> CharacterCardOut:
        copied_id = anchor_service.copy_character_card(
            card_id,
            target_scope=payload.target_scope,
            target_project_id=payload.target_project_id,
        )
        card = anchor_service.get_character_card(copied_id)
        if card is None:
            raise _http_error(500, "character_card_copy_failed", "角色卡副本已创建但无法读取。")
        return _character_out(card)

    @app.post(
        "/api/characters/{card_id}/copy-to-project",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
        deprecated=True,
    )
    def copy_public_character_to_project(
        card_id: int,
        payload: CharacterCopyToProjectRequest,
    ) -> CharacterCardOut:
        existing = anchor_service.find_active_project_copy(card_id, payload.target_project_id)
        if existing is not None and not payload.force:
            raise _http_error(
                409,
                "character_project_copy_exists",
                f"该公共角色已存在于目标工程（existing_card_id={existing.id}）",
            )
        copied_id = anchor_service.copy_public_character_to_project(
            card_id,
            payload.target_project_id,
        )
        card = anchor_service.get_character_card(copied_id)
        if card is None:
            raise _http_error(
                500,
                "character_card_copy_failed",
                "Character card copy was committed but could not be loaded.",
            )
        return _character_out(card)

    @app.get(
        "/api/characters/{card_id}/project-copy",
        response_model=CharacterCardOut | None,
        dependencies=[Depends(_require_token)],
        deprecated=True,
    )
    def get_existing_character_project_copy(
        card_id: int,
        target_project_id: int,
    ) -> CharacterCardOut | None:
        card = anchor_service.find_active_project_copy(card_id, target_project_id)
        return _character_out(card) if card is not None else None

    @app.post(
        "/api/characters/{card_id}/publish-to-public",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
        deprecated=True,
    )
    def publish_character_to_public(
        card_id: int,
        payload: CharacterPublishRequest,
    ) -> CharacterCardOut:
        published_id = anchor_service.publish_project_character_to_public(
            card_id,
            selected_fields=payload.selected_fields,
        )
        card = anchor_service.get_character_card(published_id)
        if card is None:
            raise _http_error(
                500,
                "character_publish_failed",
                "Character card was published but could not be loaded.",
            )
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

    @app.post(
        "/api/characters/{card_id}/analyze",
        response_model=dict[str, Any],
        dependencies=[Depends(_require_token)],
    )
    def analyze_character_card(card_id: int, payload: CharacterAnalyzeRequest) -> dict[str, Any]:
        return resource_analysis_service.propose_character_analysis(card_id, model_id=payload.model_id)

    @app.post(
        "/api/characters/{card_id}/analyze/confirm",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def confirm_character_analysis(card_id: int, payload: CharacterAnalysisConfirmRequest) -> CharacterCardOut:
        anchor_service.analyze_character_card(
            card_id,
            identity=payload.identity,
            age=payload.age,
            setting_text=payload.setting_text,
            custom_fields=payload.custom_fields,
            invocation_id=payload.invocation_id,
        )
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(404, "character_card_not_found", f"Character card not found: {card_id}")
        return _character_out(card)

    @app.post(
        "/api/characters/{card_id}/cover",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def save_character_cover(card_id: int, payload: CharacterCoverWriteRequest) -> CharacterCardOut:
        try:
            data = base64.b64decode(payload.data_base64, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise _http_error(400, "invalid_cover_data", "Cover data is not valid base64.") from exc
        return _character_out(anchor_service.save_character_cover(card_id, data))

    @app.post(
        "/api/characters/{card_id}/cover/delete",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def remove_character_cover(card_id: int) -> CharacterCardOut:
        return _character_out(anchor_service.remove_character_cover(card_id))

    @app.get("/api/characters/{card_id}/cover")
    def get_character_cover(card_id: int) -> FileResponse:
        path = anchor_service.character_cover_file(card_id)
        if path is None:
            raise _http_error(404, "character_cover_not_found", f"Character cover not found: {card_id}")
        media_type = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".webp": "image/webp",
        }.get(path.suffix.lower(), "application/octet-stream")
        return FileResponse(path, media_type=media_type)

    @app.post(
        "/api/selection/characters",
        response_model=CharacterCardOut,
        dependencies=[Depends(_require_token)],
    )
    def create_character_from_selection(payload: SelectionResourceCreateRequest) -> CharacterCardOut:
        selected_text = _normalize_selection_text(payload.selected_text)
        card_id = anchor_service.create_character_card(
            name=payload.name,
            scope="public",
            project_id=None,
            identity="",
            age="",
            setting_text="",
            custom_fields=[],
            raw_text=selected_text,
            analysis_status="unanalyzed",
            source_metadata=_selection_source_metadata(payload),
            import_metadata={"created_by": "selection_context_menu"},
        )
        card = anchor_service.get_character_card(card_id)
        if card is None:
            raise _http_error(500, "character_card_create_failed", "Character card was created but could not be loaded.")
        return _character_out(card)

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


def _require_scene(service: SceneService, scene_id: int):
    scene = service.get_scene(scene_id)
    if scene is None:
        raise _http_error(404, "scene_not_found", f"Scene not found: {scene_id}")
    return scene


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


def _preview_out(book: ParsedBook, token: str, split_mode: str = "auto") -> PreviewResponse:
    return PreviewResponse(
        preview_token=token,
        title=book.title,
        author=book.author,
        language=book.language,
        source_format=book.source_format,
        source_encoding=book.source_encoding,
        total_chapters=len(book.chapters),
        total_words=book.total_words,
        split_mode=split_mode,
        chapters=[
            PreviewChapterOut(
                index=chapter.index,
                title=chapter.title,
                word_count=chapter.word_count,
                start_line=chapter.start_line,
                end_line=chapter.end_line,
            )
            for chapter in book.chapters
        ],
    )


def _project_out(project: ProjectSummary) -> ProjectOut:
    progress = project.completed_chapters / project.total_chapters if project.total_chapters else 0
    return ProjectOut(
        id=project.id,
        name=project.name,
        project_kind=project.project_kind,
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


def _library_document_out(document: LibraryDocument) -> LibraryDocumentOut:
    return LibraryDocumentOut(**document.__dict__)


def _processing_template_out(template: ProcessingTemplate) -> DocumentProcessingTemplateOut:
    return DocumentProcessingTemplateOut(
        id=template.id,
        name=template.name,
        settings=template.settings,
        is_default=template.is_default,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


def _document_revision_out(revision: DocumentRevision) -> LibraryDocumentRevisionOut:
    return LibraryDocumentRevisionOut(**revision.__dict__)


def _resource_tag_out(tag: Any) -> ResourceTagOut:
    if isinstance(tag, dict):
        return ResourceTagOut(**tag)
    data = tag.__dict__.copy()
    if "document_count" in data and "resource_count" not in data:
        data["resource_count"] = data.pop("document_count")
    data.setdefault("normalized_name", data.get("name", "").casefold())
    return ResourceTagOut(**data)


def _library_chapter_out(chapter: LibraryChapter) -> LibraryDocumentChapterOut:
    return LibraryDocumentChapterOut(**chapter.__dict__)


def _library_document_content_out(content: LibraryDocumentContent) -> LibraryDocumentContentOut:
    return LibraryDocumentContentOut(**content.__dict__)


def _library_document_draft_out(draft: LibraryDocumentDraft) -> LibraryDocumentDraftOut:
    return LibraryDocumentDraftOut(**draft.__dict__)


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


def _material_ai_settings_out(settings) -> MaterialAISettingsOut:
    return MaterialAISettingsOut(
        **settings.__dict__,
        prompt_preview=compile_material_ai_prompt(settings),
    )


def _material_out(material: Material) -> MaterialOut:
    source_summary = material.source_summary
    if source_summary is None:
        raise RuntimeError("Material source summary was not generated.")
    return MaterialOut(
        id=material.id,
        material_type=material.material_type,
        scope=material.scope,
        project_id=material.project_id,
        project_name=material.project_name,
        name=material.name,
        description=material.description,
        detail_level=material.detail_level,
        raw_text=material.raw_text,
        content=_json_object(material.content_json),
        analysis_status=material.analysis_status,
        source_metadata=_json_object(material.source_metadata_json),
        import_metadata=_json_object(material.import_metadata_json),
        source_material_id=material.source_material_id,
        source_version=material.source_version,
        timeline_start_chapter=material.timeline_start_chapter,
        timeline_end_chapter=material.timeline_end_chapter,
        sort_order=material.sort_order,
        version=material.version,
        created_at=material.created_at,
        updated_at=material.updated_at,
        tags=list(material.tags),
        general_tags=list(material.general_tags),
        applicable_scene_tags=list(material.applicable_scene_tags),
        category_ids=list(material.category_ids),
        categories=list(material.categories),
        source_summary=source_summary.__dict__,
    )


def _character_out(card: CharacterCard) -> CharacterCardOut:
    source_summary = card.source_summary
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
        scope=card.scope,
        project_id=card.project_id,
        source_character_card_id=card.source_character_card_id,
        source_version=card.source_version,
        version=card.version,
        sort_order=card.sort_order,
        identity=card.identity,
        age=card.age,
        setting_text=card.setting_text,
        custom_fields=card.custom_fields,
        stable_fields=card.stable_fields,
        raw_text=card.raw_text,
        analysis_status=card.analysis_status,
        cover_path=card.cover_path,
        cover_updated_at=card.cover_updated_at,
        tags=list(card.tags),
        category_ids=list(card.category_ids),
        categories=list(card.categories),
        source_summary=CharacterSourceSummaryOut(
            kind=source_summary.kind if source_summary is not None else "manual",
            label=source_summary.label if source_summary is not None else "本地创建",
            document_id=source_summary.document_id if source_summary is not None else None,
            chapter_id=source_summary.chapter_id if source_summary is not None else None,
            project_id=source_summary.project_id if source_summary is not None else card.project_id,
            source_card_id=source_summary.source_card_id if source_summary is not None else card.source_character_card_id,
        ),
        created_at=card.created_at,
        updated_at=card.updated_at,
    )


def _normalize_selection_text(text: str) -> str:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not normalized:
        raise _http_error(400, "empty_selection", "Selected text is empty.")
    if len(normalized) > 50000:
        raise _http_error(400, "selection_too_large", "Selected text must be 50,000 characters or fewer.")
    return normalized


def _selection_source_metadata(payload: SelectionResourceCreateRequest) -> dict[str, Any]:
    return {
        "source_kind": payload.source_kind,
        "document_id": payload.document_id,
        "project_id": payload.project_id,
        "chapter_id": payload.chapter_id,
        "start_offset": payload.start_offset,
        "end_offset": payload.end_offset,
        "selection_snapshot": payload.selected_text,
        "source_version": payload.source_version,
        "captured_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
    }


def _resolve_anchor_source(
    payload: AnchorExtractRequest,
    *,
    project_service: ProjectService,
    document_library_service: DocumentLibraryService,
) -> tuple[str, dict[str, Any]]:
    sources = [
        bool(payload.sample_text and payload.sample_text.strip()),
        bool(payload.source_path),
        payload.source_project_id is not None,
        payload.source_document_id is not None,
    ]
    if sum(1 for present in sources if present) != 1:
        raise _http_error(
            400,
            "invalid_anchor_source",
            "请从粘贴文本、本地文件、工程或文档库中选择且只选择一种来源。",
        )
    if payload.sample_text and payload.sample_text.strip():
        return payload.sample_text, {"source_type": "paste"}
    if payload.source_path:
        source_path = _validate_source_path(payload.source_path)
        if source_path.stat().st_size > STYLE_EXTRACTION_MAX_FILE_BYTES:
            raise _http_error(400, "anchor_source_too_large", "AI 提取源文件过大。")
        book = project_service.preview_book(source_path)
        text = "\n\n".join(f"# {chapter.title}\n{chapter.text}" for chapter in book.chapters)
        return text, {
            "source_type": "file",
            "file_name": book.source_path.name,
            "source_file_name": book.source_path.name,
            "source_path": str(source_path),
            "source_format": book.source_format,
            "book_title": book.title,
        }
    if payload.source_project_id is not None:
        project = project_service.get_project(payload.source_project_id)
        if project is None:
            raise _http_error(404, "project_not_found", f"找不到工程：{payload.source_project_id}")
        chapters = project_service.list_chapters(payload.source_project_id)
        text = "\n\n".join(f"# {chapter.title}\n{chapter.original_text}" for chapter in chapters)
        return text, {
            "source_type": "project",
            "project_id": project.id,
            "project_name": project.name,
            "source_project_id": project.id,
            "source_project_name": project.name,
        }
    content = document_library_service.get_content(int(payload.source_document_id))
    return content.text, {
        "source_type": "document",
        "document_id": content.document_id,
        "document_title": content.title,
        "source_document_id": content.document_id,
        "source_document_title": content.title,
    }


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
