from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class LibraryDocumentImportRequest(BaseModel):
    source_path: str = Field(min_length=1)


class LibraryDocumentUpdateRequest(BaseModel):
    title: str = Field(min_length=1)
    author: str | None = None


class LibraryDocumentAICleanupRequest(BaseModel):
    chapter_id: int | None = None
    chapter_ids: list[int] | None = None
    prompt: str = Field(min_length=1)
    model_id: int | None = None


class DocumentLibraryMigrateRequest(BaseModel):
    target_path: str = Field(min_length=1)


class ResourceNameCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class ResourceNameRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class LibraryDocumentVolumeRenameRequest(BaseModel):
    title: str = Field(min_length=1)


class LibraryDocumentVolumeCreateRequest(BaseModel):
    chapter_id: int
    title: str = Field(min_length=1)


class LibraryDocumentDraftWriteRequest(BaseModel):
    base_revision_id: int
    title: str
    text: str
    chapter_id: int | None = None


class LibraryDocumentDraftScopeRequest(BaseModel):
    chapter_id: int | None = None


class DocumentMergeRequest(BaseModel):
    document_ids: list[int] = Field(min_length=2)
    title: str = Field(min_length=1)
    author: str | None = None


class DocumentCreateChapterRequest(BaseModel):
    title: str = Field(min_length=1)
    text: str = ""
    position: Literal["before", "after"] = "after"
    anchor_chapter_id: int | None = None


class DocumentCursorSplitRequest(BaseModel):
    chapter_id: int
    cursor_offset: int = Field(ge=0)
    next_title: str = Field(min_length=1)


class AISplitPreviewRequest(BaseModel):
    chapter_id: int
    prompt: str = Field(min_length=1)
    model_id: int | None = None


class AISplitApplyRequest(BaseModel):
    proposal_id: int
    chapters: list[dict[str, Any]] | None = None


class LibraryDocumentChapterReorderRequest(BaseModel):
    ordered_chapter_ids: list[int] = Field(min_length=1)
    volume_assignments: dict[int, int | None] = Field(default_factory=dict)


class LibraryDocumentExportRequest(BaseModel):
    format: Literal["txt", "epub"]
    output_path: str = Field(min_length=1)


class ChapterSplitRequest(BaseModel):
    mode: Literal["auto", "simple", "regex"] = "auto"
    line_prefix: str = "第"
    number_style: Literal["mixed", "arabic", "chinese"] = "mixed"
    title_suffixes: list[str] = Field(default_factory=lambda: ["章", "回", "节", "卷", "集", "部", "篇"])
    extra_title_regex: str | None = None
    custom_regex: str | None = None


class PreviewRequest(BaseModel):
    source_path: str = Field(min_length=1)
    workspace_path: str | None = None
    split: ChapterSplitRequest | None = None


class CreateProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preview_token: str = Field(min_length=1)
    project_name: str | None = None
    workspace_path: str | None = None
    model_id: int | None = None


class ModelWriteRequest(BaseModel):
    display_name: str = Field(min_length=1)
    provider: str = "openai_compatible"
    base_url: str = Field(min_length=1)
    model_name: str = Field(min_length=1)
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int | None = None
    timeout_seconds: int = 60
    is_default: bool = False


class MaterialUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    content: dict[str, Any] = Field(default_factory=dict)
    sort_order: int = 0


class MaterialAIDimension(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=100)
    requirement: str = Field(default="", max_length=4000)


class MaterialAISettingsImportRequest(BaseModel):
    value: Any


class MaterialAISettingsWriteRequest(BaseModel):
    model_id: int | None = None
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    extraction_rules: str = Field(default="", max_length=12000)
    base_instruction: str = Field(default="", max_length=12000)
    dimensions: list[MaterialAIDimension] = Field(default_factory=list, max_length=50)
    extra_requirements: str = Field(default="", max_length=12000)


class MaterialExtractionPreviewRequest(BaseModel):
    name: str = Field(min_length=1)
    source_path: str = Field(min_length=1)
    model_id: int | None = None


class MaterialExtractionApplyRequest(BaseModel):
    preview_token: str
    candidates: list[dict[str, Any]] = Field(default_factory=list)
    selected_candidate_ids: list[str] = Field(default_factory=list)
