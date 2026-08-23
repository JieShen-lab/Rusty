from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from rusty.db import default_database_path, initialize_database_file
from rusty.models import ParsedBook
from rusty.services.ai_client import (
    AIAuthenticationError,
    AIConnectTimeoutError,
    AIProviderError,
    AIReadTimeoutError,
    AIResponseParseError,
)
from rusty.services.ai_request_executor import AIRequestExecutor
from rusty.services.author_style_extraction_service import AuthorStyleExtractionService
from rusty.services.chapter_split_service import ChapterSplitService
from rusty.services.creative_workflow_service import CreativeWorkflowService, WorkflowSourceConflict
from rusty.services.document_cleanup_ai_service import DocumentCleanupAIService
from rusty.services.document_library_service import DocumentLibraryService, DraftConflictError
from rusty.services.document_split_ai_service import DocumentSplitAIService
from rusty.services.material_service import MaterialService
from rusty.services.model_service import ModelService
from rusty.services.project_service import ProjectService
from rusty.services.prompt_slot_service import PromptSlotService
from rusty.services.structured_model_service import StructuredModelService

from .schemas import (
    AISplitApplyRequest,
    AISplitPreviewRequest,
    CreateProjectRequest,
    DocumentCreateChapterRequest,
    DocumentCategoryAssignmentRequest,
    DocumentCursorSplitRequest,
    DocumentLibraryMigrateRequest,
    DocumentMergeRequest,
    LibraryDocumentAICleanupRequest,
    LibraryDocumentChapterReorderRequest,
    LibraryDocumentDraftScopeRequest,
    LibraryDocumentDraftWriteRequest,
    LibraryDocumentExportRequest,
    LibraryDocumentImportRequest,
    LibraryDocumentUpdateRequest,
    LibraryDocumentVolumeCreateRequest,
    LibraryDocumentVolumeRenameRequest,
    MaterialAISettingsImportRequest,
    MaterialAISettingsWriteRequest,
    MaterialExtractionApplyRequest,
    MaterialExtractionPreviewRequest,
    MaterialUpdateRequest,
    ModelWriteRequest,
    PreviewRequest,
    ResourceNameCreateRequest,
    ResourceNameRenameRequest,
)


APP_NAME = "Rusty"
API_TOKEN_HEADER = "X-Rusty-Token"
PREVIEW_TTL_SECONDS = 15 * 60
SUPPORTED_IMPORT_SUFFIXES = {".txt", ".epub", ".docx"}
_GENERATED_TOKEN = secrets.token_urlsafe(32)


@dataclass(frozen=True)
class PreviewState:
    source_path: Path
    workspace_path: Path | None
    parsed_book: ParsedBook
    fingerprint: str
    expires_at: float


_PREVIEWS: dict[str, PreviewState] = {}


def current_api_token() -> str:
    return os.environ.get("RUSTY_API_TOKEN") or _GENERATED_TOKEN


def create_app(
    database_path: str | Path | None = None,
    ai_client=None,
) -> FastAPI:
    db_path = Path(database_path) if database_path is not None else Path(
        os.environ.get("RUSTY_DATABASE_PATH", default_database_path())
    )
    initialize_database_file(db_path)
    executor = AIRequestExecutor(db_path, ai_client=ai_client)
    projects = ProjectService(db_path)
    chapter_split = ChapterSplitService()
    documents = DocumentLibraryService(db_path)
    structured = StructuredModelService(db_path, executor=executor)
    structured_cleanup = DocumentCleanupAIService(db_path, structured_model_service=structured)
    document_split = DocumentSplitAIService(
        db_path, structured_model_service=structured,
    )
    models = ModelService(db_path)
    prompts = PromptSlotService(db_path)
    materials = MaterialService(db_path)
    author_styles = AuthorStyleExtractionService(db_path, executor=executor)
    creative = CreativeWorkflowService(db_path, executor=executor)

    app = FastAPI(title="Rusty Local API", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "null"],
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", API_TOKEN_HEADER],
    )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
        detail = exc.detail if isinstance(exc.detail, dict) else {"message": str(exc.detail)}
        return JSONResponse(exc.status_code, {"error": detail.get("error", "http_error"), "message": detail.get("message", str(exc.detail)), "details": detail.get("details")})

    @app.exception_handler(WorkflowSourceConflict)
    async def workflow_conflict(_: Request, exc: WorkflowSourceConflict) -> JSONResponse:
        return JSONResponse(409, {"code": "workflow_source_changed", "message": str(exc)})

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError) -> JSONResponse:
        return _error_response(400, "validation_error", str(exc))

    @app.exception_handler(FileNotFoundError)
    async def missing_error(_: Request, exc: FileNotFoundError) -> JSONResponse:
        return _error_response(404, "file_not_found", str(exc))

    for exception_type, status, code in (
        (AIConnectTimeoutError, 504, "ai_connect_timeout"),
        (AIReadTimeoutError, 504, "ai_read_timeout"),
        (AIAuthenticationError, 401, "ai_authentication_failed"),
        (AIProviderError, 502, "ai_provider_error"),
        (AIResponseParseError, 502, "ai_response_parse_error"),
    ):
        app.add_exception_handler(
            exception_type,
            lambda _request, exc, status=status, code=code: _error_response(status, code, str(exc)),
        )

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "app": APP_NAME}

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        return [_project_out(item) for item in projects.list_projects()]

    @app.get("/api/projects/{project_id}")
    def get_project(project_id: int) -> dict[str, Any]:
        return _project_out(_require_project(projects, project_id))

    @app.post("/api/projects/preview", dependencies=[Depends(_require_token)])
    def preview_project(payload: PreviewRequest) -> dict[str, Any]:
        source_path = _validate_source_path(payload.source_path)
        workspace = _optional_workspace_path(payload.workspace_path)
        split_options = payload.split.model_dump() if payload.split is not None else {"mode": "auto"}
        if source_path.suffix.lower() == ".txt":
            parsed = chapter_split.preview_txt(source_path, **split_options)
        else:
            parsed = projects.preview_book(source_path)
            split_options = {"mode": "document"}
        token = secrets.token_urlsafe(24)
        _PREVIEWS[token] = PreviewState(source_path, workspace, parsed, _file_fingerprint(source_path), time.time() + PREVIEW_TTL_SECONDS)
        return _preview_out(parsed, token, str(split_options["mode"]))

    @app.post("/api/projects", dependencies=[Depends(_require_token)])
    def create_project(payload: CreateProjectRequest) -> dict[str, Any]:
        state = _consume_preview(payload.preview_token)
        if _file_fingerprint(state.source_path) != state.fingerprint:
            raise _http_error(400, "preview_mismatch", "源文件已变化，请重新预览后再创建工程。")
        workspace = _optional_workspace_path(payload.workspace_path) or state.workspace_path or state.source_path.parent
        project_id = projects.create_project(
            state.parsed_book,
            workspace,
            payload.project_name,
            model_id=payload.model_id,
        )
        return _project_out(_require_project(projects, project_id))

    @app.post("/api/projects/{project_id}/delete", dependencies=[Depends(_require_token)])
    def delete_project(project_id: int) -> dict[str, bool]:
        _require_project(projects, project_id)
        projects.delete_project(project_id)
        return {"ok": True}

    @app.post("/api/projects/{project_id}/export", dependencies=[Depends(_require_token)])
    def export_project(project_id: int, payload: LibraryDocumentExportRequest) -> dict[str, Any]:
        _require_project(projects, project_id)
        output = projects.export_project(project_id, payload.format, payload.output_path)
        return {"ok": True, "format": payload.format, "output_path": str(output)}

    @app.get("/api/projects/{project_id}/chapters")
    def list_chapters(project_id: int) -> list[dict[str, Any]]:
        _require_project(projects, project_id)
        return [asdict(item) for item in projects.list_chapters(project_id)]

    @app.get("/api/chapters/{chapter_id}")
    def get_chapter(chapter_id: int) -> dict[str, Any]:
        chapter = projects.get_chapter(chapter_id)
        if chapter is None:
            raise FileNotFoundError(f"Chapter not found: {chapter_id}")
        return asdict(chapter)

    @app.get("/api/chapters/{chapter_id}/workflow")
    def get_chapter_workflow(chapter_id: int) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.get_chapter_workflow(chapter_id)

    @app.post("/api/chapters/{chapter_id}/workflow/summary/run", dependencies=[Depends(_require_token)])
    def run_summary(chapter_id: int) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.run_chapter_summary(chapter_id)

    @app.put("/api/chapters/{chapter_id}/workflow/summary", dependencies=[Depends(_require_token)])
    def save_summary(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.save_chapter_summary(chapter_id, payload)

    @app.put("/api/chapters/{chapter_id}/workflow/direction", dependencies=[Depends(_require_token)])
    def save_direction(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.save_chapter_direction(chapter_id, strategy=str(payload.get("strategy") or ""), user_instruction=str(payload.get("user_instruction") or ""))

    @app.post("/api/chapters/{chapter_id}/workflow/special-analysis/run", dependencies=[Depends(_require_token)])
    def run_analysis(chapter_id: int) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.run_special_analysis(chapter_id)

    @app.put("/api/chapters/{chapter_id}/workflow/special-analysis", dependencies=[Depends(_require_token)])
    def save_analysis(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.save_special_analysis(chapter_id, payload)

    @app.post("/api/chapters/{chapter_id}/workflow/style/resolve", dependencies=[Depends(_require_token)])
    def resolve_style(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        material_id = payload.get("author_style_material_id")
        return creative.resolve_style(chapter_id, author_style_material_id=int(material_id) if material_id is not None else None)

    @app.post("/api/chapters/{chapter_id}/workflow/writing/generate", dependencies=[Depends(_require_token)])
    def generate_writing(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.generate_chapter(chapter_id, replace_existing=bool(payload.get("replace_existing", False)))

    @app.put("/api/chapters/{chapter_id}/workflow/writing", dependencies=[Depends(_require_token)])
    def save_writing(chapter_id: int, payload: dict[str, Any]) -> dict[str, Any]:
        _require_chapter(projects, chapter_id)
        return creative.save_writing(chapter_id, str(payload.get("result_text") or ""))

    @app.get("/api/models")
    def list_models() -> list[dict[str, Any]]:
        return [asdict(item) for item in models.list_models()]

    @app.post("/api/models", dependencies=[Depends(_require_token)])
    def create_model(payload: ModelWriteRequest) -> dict[str, Any]:
        model_id = models.create_model(**payload.model_dump())
        model = models.get_model(model_id)
        if model is None:
            raise FileNotFoundError(f"Model not found: {model_id}")
        return asdict(model)

    @app.post("/api/models/{model_id}", dependencies=[Depends(_require_token)])
    def update_model(model_id: int, payload: ModelWriteRequest) -> dict[str, Any]:
        models.update_model(model_id=model_id, **payload.model_dump())
        model = models.get_model(model_id)
        if model is None:
            raise FileNotFoundError(f"Model not found: {model_id}")
        return asdict(model)

    @app.post("/api/models/{model_id}/delete", dependencies=[Depends(_require_token)])
    def delete_model(model_id: int) -> dict[str, bool]:
        models.delete_model(model_id)
        return {"ok": True}

    @app.post("/api/models/{model_id}/test", dependencies=[Depends(_require_token)])
    def test_model(model_id: int) -> dict[str, Any]:
        return asdict(executor.test_connection(model_id))

    @app.get("/api/prompt-slots")
    def list_prompt_slots() -> list[dict[str, Any]]:
        return [asdict(item) for item in prompts.list_slots()]

    @app.put("/api/prompt-slots/{slot_key}", dependencies=[Depends(_require_token)])
    def update_prompt_slot(slot_key: str, payload: dict[str, str]) -> dict[str, Any]:
        return asdict(prompts.update_slot(slot_key, payload.get("content", "")))

    @app.get("/api/materials")
    def list_materials(query: str | None = None) -> list[dict[str, Any]]:
        return [_material_out(item) for item in materials.list_materials(query=query)]

    @app.post("/api/materials/{material_id}", dependencies=[Depends(_require_token)])
    def update_material(material_id: int, payload: MaterialUpdateRequest) -> dict[str, Any]:
        materials.update_material(material_id, **payload.model_dump())
        material = materials.get_material(material_id)
        if material is None:
            raise FileNotFoundError(f"Author style not found: {material_id}")
        return _material_out(material)

    @app.post("/api/materials/{material_id}/delete", dependencies=[Depends(_require_token)])
    def delete_material(material_id: int) -> dict[str, bool]:
        materials.delete_material(material_id)
        return {"ok": True}

    @app.get("/api/material-ai-settings/{task_type}")
    def get_material_settings(task_type: str) -> dict[str, Any]:
        return _settings_out(materials.get_ai_settings(task_type))

    @app.post("/api/material-ai-settings/{task_type}", dependencies=[Depends(_require_token)])
    def update_material_settings(task_type: str, payload: MaterialAISettingsWriteRequest) -> dict[str, Any]:
        return _settings_out(materials.update_ai_settings(task_type, **payload.model_dump()))

    @app.get("/api/author-style-settings/export")
    def export_author_style_settings() -> dict[str, Any]:
        return materials.export_author_style_settings()

    @app.post("/api/author-style-settings/import", dependencies=[Depends(_require_token)])
    def import_author_style_settings(payload: MaterialAISettingsImportRequest) -> dict[str, Any]:
        return _settings_out(materials.import_author_style_settings(payload.value))

    @app.post("/api/material-extractions/preview", dependencies=[Depends(_require_token)])
    def preview_author_style(payload: MaterialExtractionPreviewRequest) -> dict[str, Any]:
        preview = author_styles.preview_from_file(payload.source_path, name=payload.name or "", model_id=payload.model_id)
        return {
            **asdict(preview),
            "candidates": [asdict(item) for item in preview.candidates],
        }

    @app.post("/api/material-extractions/apply", dependencies=[Depends(_require_token)])
    def apply_author_style(payload: MaterialExtractionApplyRequest) -> dict[str, Any]:
        return author_styles.apply_preview(**payload.model_dump())

    _register_document_routes(app, documents, structured_cleanup, document_split)
    return app


def _register_document_routes(app: FastAPI, documents: DocumentLibraryService, cleanup: DocumentCleanupAIService, split_ai: DocumentSplitAIService) -> None:
    write = [Depends(_require_token)]

    @app.get("/api/documents")
    def list_documents() -> list[dict[str, Any]]:
        return [asdict(item) for item in documents.list_documents()]

    @app.post("/api/documents/import", dependencies=write)
    def import_document(payload: LibraryDocumentImportRequest) -> dict[str, Any]:
        result = documents.import_document(payload.source_path)
        return {"document": asdict(result.document), "created": result.created, "storage_format": "txt"}

    @app.post("/api/documents/{document_id}", dependencies=write)
    def update_document(document_id: int, payload: LibraryDocumentUpdateRequest) -> dict[str, Any]:
        return asdict(documents.update_document_metadata(document_id, title=payload.title, author=payload.author))

    @app.get("/api/document-library/settings")
    def library_settings() -> dict[str, str]:
        return {"storage_path": str(documents.get_library_path())}

    @app.post("/api/document-library/migrate", dependencies=write)
    def migrate_library(payload: DocumentLibraryMigrateRequest) -> dict[str, str]:
        return {"storage_path": str(documents.migrate_library_path(payload.target_path))}

    @app.get("/api/document-categories")
    def list_categories() -> list[dict[str, Any]]:
        return [asdict(item) for item in documents.list_categories()]

    @app.post("/api/document-categories", dependencies=write)
    def create_category(payload: ResourceNameCreateRequest) -> dict[str, Any]:
        return asdict(documents.create_category(payload.name))

    @app.post("/api/document-categories/{category_id}", dependencies=write)
    def rename_category(category_id: int, payload: ResourceNameRenameRequest) -> dict[str, Any]:
        return asdict(documents.rename_category(category_id, payload.name))

    @app.post("/api/document-categories/{category_id}/delete", dependencies=write)
    def delete_category(category_id: int) -> dict[str, bool]:
        documents.delete_category(category_id)
        return {"ok": True}

    @app.put("/api/documents/{document_id}/categories", dependencies=write)
    def set_document_categories(document_id: int, payload: DocumentCategoryAssignmentRequest) -> dict[str, Any]:
        return asdict(documents.set_document_categories(document_id, payload.category_ids))

    @app.get("/api/documents/{document_id}/revisions")
    def list_revisions(document_id: int) -> list[dict[str, Any]]:
        return [asdict(item) for item in documents.list_revisions(document_id)]

    @app.get("/api/documents/{document_id}/directory")
    def directory(document_id: int) -> dict[str, Any]:
        value = documents.get_directory(document_id)
        return {
            "volumes": [{**asdict(volume), "chapters": [asdict(chapter) for chapter in chapters]} for volume, chapters in value.volumes],
            "unassigned_chapters": [asdict(item) for item in value.unassigned_chapters],
        }

    @app.get("/api/documents/{document_id}/content")
    def content(document_id: int, chapter_id: int | None = None) -> dict[str, Any]:
        return asdict(documents.get_content(document_id, chapter_id))

    @app.get("/api/documents/{document_id}/draft")
    def get_draft(document_id: int, chapter_id: int | None = None) -> dict[str, Any] | None:
        value = documents.get_draft(document_id, chapter_id)
        return asdict(value) if value else None

    @app.put("/api/documents/{document_id}/draft", dependencies=write)
    def save_draft(document_id: int, payload: LibraryDocumentDraftWriteRequest) -> dict[str, Any]:
        try:
            return asdict(documents.save_draft(document_id, base_revision_id=payload.base_revision_id, title=payload.title, text=payload.text, chapter_id=payload.chapter_id))
        except DraftConflictError as exc:
            raise _http_error(409, "document_draft_conflict", str(exc)) from exc

    @app.post("/api/documents/{document_id}/draft/commit", dependencies=write)
    def commit_draft(document_id: int, payload: LibraryDocumentDraftScopeRequest) -> dict[str, Any]:
        result = documents.commit_draft(document_id, payload.chapter_id)
        return _cleanup_out(result)

    @app.post("/api/documents/merge", dependencies=write)
    def merge_documents(payload: DocumentMergeRequest) -> dict[str, Any]:
        return asdict(documents.merge_documents(payload.document_ids, payload.title, payload.author))

    @app.post("/api/documents/{document_id}/chapters", dependencies=write)
    def create_chapter(document_id: int, payload: DocumentCreateChapterRequest) -> dict[str, Any]:
        return _cleanup_out(documents.create_chapter(document_id, title=payload.title, text=payload.text, position=payload.position, anchor_chapter_id=payload.anchor_chapter_id))

    @app.delete("/api/documents/{document_id}/chapters/{chapter_id}", dependencies=write)
    def delete_chapter(document_id: int, chapter_id: int) -> dict[str, Any]:
        return _cleanup_out(documents.delete_chapter(document_id, chapter_id))

    @app.post("/api/documents/{document_id}/split/cursor", dependencies=write)
    def split_cursor(document_id: int, payload: DocumentCursorSplitRequest) -> dict[str, Any]:
        return _cleanup_out(documents.split_chapter_at_cursor(document_id, chapter_id=payload.chapter_id, cursor_offset=payload.cursor_offset, next_title=payload.next_title))

    @app.post("/api/documents/{document_id}/split/ai/preview", dependencies=write)
    def preview_ai(document_id: int, payload: AISplitPreviewRequest) -> dict[str, Any]:
        return split_ai.preview(document_id, chapter_id=payload.chapter_id, prompt=payload.prompt, model_id=payload.model_id)

    @app.post("/api/documents/{document_id}/split/ai/apply", dependencies=write)
    def apply_ai(document_id: int, payload: AISplitApplyRequest) -> dict[str, Any]:
        result = split_ai.apply(payload.proposal_id, chapters=payload.chapters)
        if int(result["document_id"]) != document_id:
            raise _http_error(409, "split_proposal_mismatch", "AI split proposal mismatch.")
        return result

    @app.post("/api/documents/{document_id}/chapters/reorder", dependencies=write)
    def reorder_chapters(document_id: int, payload: LibraryDocumentChapterReorderRequest) -> list[dict[str, Any]]:
        return [asdict(item) for item in documents.reorder_chapters(document_id, payload.ordered_chapter_ids, payload.volume_assignments)]

    @app.post("/api/documents/{document_id}/volumes", dependencies=write)
    def create_volume(document_id: int, payload: LibraryDocumentVolumeCreateRequest) -> dict[str, Any]:
        return _cleanup_out(documents.create_volume(document_id, payload.chapter_id, payload.title))

    @app.post("/api/documents/{document_id}/volumes/{volume_id}", dependencies=write)
    def rename_volume(document_id: int, volume_id: int, payload: LibraryDocumentVolumeRenameRequest) -> dict[str, Any]:
        return _cleanup_out(documents.rename_volume(document_id, volume_id, payload.title))

    @app.post("/api/documents/{document_id}/delete", dependencies=write)
    def delete_document(document_id: int) -> dict[str, bool]:
        documents.delete_document(document_id)
        return {"ok": True}

    @app.post("/api/documents/{document_id}/cleanup/ai", dependencies=write)
    def cleanup_ai(document_id: int, payload: LibraryDocumentAICleanupRequest) -> dict[str, Any]:
        chapter_ids = payload.chapter_ids or ([payload.chapter_id] if payload.chapter_id is not None else [])
        if chapter_ids:
            batch = cleanup.apply_many(document_id, chapter_ids=chapter_ids, prompt=payload.prompt, model_id=payload.model_id)
            document = batch.result.document if batch.result else next(item for item in documents.list_documents() if item.id == document_id)
            return {"document": asdict(document), "revision": asdict(batch.result.revision) if batch.result else None, "created": batch.result is not None, "chapters": [asdict(item) for item in batch.chapters]}
        return _cleanup_out(cleanup.apply(document_id, chapter_id=None, prompt=payload.prompt, model_id=payload.model_id))

    @app.post("/api/documents/{document_id}/revisions/{revision_id}/activate", dependencies=write)
    def activate_revision(document_id: int, revision_id: int) -> dict[str, Any]:
        return asdict(documents.activate_revision(document_id, revision_id))

    @app.post("/api/documents/{document_id}/export", dependencies=write)
    def export_document(document_id: int, payload: LibraryDocumentExportRequest) -> dict[str, Any]:
        output = documents.export_document(document_id, payload.format, payload.output_path)
        return {"ok": True, "format": payload.format, "output_path": str(output)}


def _cleanup_out(result: Any) -> dict[str, Any]:
    value = {"document": asdict(result.document), "revision": asdict(result.revision), "created": result.created}
    if result.created_chapter_id is not None:
        value["created_chapter_id"] = result.created_chapter_id
    return value


def _material_out(material: Any) -> dict[str, Any]:
    return {
        "id": material.id,
        "name": material.name,
        "raw_text": material.raw_text,
        "content": json.loads(material.content_json),
        "created_at": material.created_at,
        "updated_at": material.updated_at,
    }


def _settings_out(settings: Any) -> dict[str, Any]:
    value = asdict(settings)
    value["dimensions"] = [dict(item) for item in settings.dimensions]
    value["prompt_preview"] = (
        f"{settings.extraction_rules}\n\n任务：\n{settings.base_instruction}\n\n"
        + "\n\n".join(f"{index}. {item['name']}\nID: {item['id']}\n提取要求：{item['requirement']}" for index, item in enumerate(settings.dimensions, 1))
    )
    return value


def _project_out(project: Any) -> dict[str, Any]:
    value = asdict(project)
    value["progress"] = project.completed_chapters / project.total_chapters if project.total_chapters else 0
    return value


def _preview_out(book: ParsedBook, token: str, split_mode: str) -> dict[str, Any]:
    return {
        "preview_token": token,
        "title": book.title,
        "author": book.author,
        "language": book.language,
        "source_format": book.source_format,
        "source_encoding": book.source_encoding,
        "total_chapters": len(book.chapters),
        "total_words": book.total_words,
        "split_mode": split_mode,
        "chapters": [
            {
                "index": item.index,
                "title": item.title,
                "word_count": item.word_count,
                "start_line": item.start_line,
                "end_line": item.end_line,
            }
            for item in book.chapters
        ],
    }


def _consume_preview(token: str) -> PreviewState:
    state = _PREVIEWS.pop(token, None)
    if state is None or state.expires_at < time.time():
        raise _http_error(400, "preview_expired", "预览已失效，请重新选择文件。")
    return state


def _validate_source_path(value: str) -> Path:
    path = Path(value).expanduser().resolve()
    if not path.is_file() or path.suffix.lower() not in SUPPORTED_IMPORT_SUFFIXES:
        raise _http_error(400, "invalid_source", "请选择存在的 TXT、EPUB 或 DOCX 文件。")
    return path


def _optional_workspace_path(value: str | None) -> Path | None:
    if not value or not value.strip():
        return None
    path = Path(value).expanduser().resolve()
    if not path.is_dir():
        raise _http_error(400, "invalid_workspace", "工作目录不存在。")
    return path


def _file_fingerprint(path: Path) -> str:
    stat = path.stat()
    return hashlib.sha256(f"{path}:{stat.st_size}:{stat.st_mtime_ns}".encode()).hexdigest()


def _require_project(service: ProjectService, project_id: int) -> Any:
    project = service.get_project(project_id)
    if project is None:
        raise FileNotFoundError(f"Project not found: {project_id}")
    return project


def _require_chapter(service: ProjectService, chapter_id: int) -> Any:
    chapter = service.get_chapter(chapter_id)
    if chapter is None:
        raise FileNotFoundError(f"Chapter not found: {chapter_id}")
    return chapter


def _http_error(status: int, code: str, message: str, details: Any = None) -> HTTPException:
    return HTTPException(status, {"error": code, "message": message, "details": details})


def _error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status, {"error": code, "message": message, "details": None})


def _require_token(x_rusty_token: str | None = Header(default=None)) -> None:
    if not secrets.compare_digest(x_rusty_token or "", current_api_token()):
        raise _http_error(401, "invalid_token", "Rusty API token is missing or invalid.")


app = create_app()
