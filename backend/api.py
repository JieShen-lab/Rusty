from __future__ import annotations

import hashlib
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
from rusty.models import ChapterRecord, ParsedBook, ProjectSummary
from rusty.services.model_service import ModelService
from rusty.services.pipeline_service import PipelineService
from rusty.services.project_service import ProjectService, default_database_path
from rusty.services.prompt_service import PromptService

from .schemas import (
    ChapterAIOutputsOut,
    ChapterDetailOut,
    ChapterErrorOut,
    ChapterOut,
    CreateProjectRequest,
    ErrorResponse,
    ExportResponse,
    HealthResponse,
    ModelOut,
    PreviewChapterOut,
    PreviewRequest,
    PreviewResponse,
    ProjectDetailOut,
    ProjectOut,
    PromptTemplateOut,
    StageStatusOut,
)

APP_NAME = "Rusty"
API_TOKEN_HEADER = "X-Rusty-Token"
PREVIEW_TTL_SECONDS = 15 * 60
SUPPORTED_IMPORT_SUFFIXES = {".txt", ".epub", ".docx"}
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


def create_app(database_path: str | Path | None = None) -> FastAPI:
    db_path = Path(os.environ.get("RUSTY_DATABASE_PATH", database_path or default_database_path()))
    project_service = ProjectService(db_path)
    pipeline_service = PipelineService(db_path)
    model_service = ModelService(db_path)
    prompt_service = PromptService(db_path)

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
        project_id = project_service.create_project(parsed, workspace, payload.project_name)
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

    @app.post("/api/chapters/{chapter_id}/summarize", dependencies=[Depends(_require_token)])
    def summarize_chapter(chapter_id: int) -> None:
        raise _http_error(501, "not_implemented", f"Chapter summarize API is reserved for UI-R3: {chapter_id}")

    @app.post("/api/chapters/{chapter_id}/detect-scene", dependencies=[Depends(_require_token)])
    def detect_scene(chapter_id: int) -> None:
        raise _http_error(501, "not_implemented", f"Chapter scene detection API is reserved for UI-R3: {chapter_id}")

    @app.post("/api/chapters/{chapter_id}/rewrite", dependencies=[Depends(_require_token)])
    def rewrite_chapter(chapter_id: int) -> None:
        raise _http_error(501, "not_implemented", f"Chapter rewrite API is reserved for UI-R3: {chapter_id}")

    @app.get("/api/models", response_model=list[ModelOut])
    def list_models() -> list[ModelOut]:
        return [ModelOut(**model.__dict__) for model in model_service.list_models()]

    @app.get("/api/prompts", response_model=list[PromptTemplateOut])
    def list_prompts() -> list[PromptTemplateOut]:
        return [PromptTemplateOut(**template.__dict__) for template in prompt_service.list_templates()]

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


def _http_error(status_code: int, error: str, message: str, details: dict[str, Any] | None = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"error": error, "message": message, "details": details})


def _error_response(status_code: int, error: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status_code, content={"error": error, "message": message, "details": None})


app = create_app()
