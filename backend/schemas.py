from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    ok: bool
    app: str


class ProjectOut(BaseModel):
    id: int
    name: str
    status: str
    current_stage: str
    source_format: str | None
    total_chapters: int
    total_words: int
    completed_chapters: int
    book_title: str | None
    author: str | None
    created_at: str
    updated_at: str
    progress: float


class ChapterOut(BaseModel):
    id: int
    project_id: int
    index: int
    title: str
    original_text: str
    rewritten_text: str | None
    word_count: int
    status: str
    start_line: int | None
    end_line: int | None


class StageStatusOut(BaseModel):
    stage: str
    status: str
    retry_count: int
    elapsed_ms: int | None
    started_at: str | None
    finished_at: str | None


class ChapterErrorOut(BaseModel):
    id: int
    stage: str
    error_type: str | None
    message: str
    created_at: str
    resolved_at: str | None


class ChapterAIOutputsOut(BaseModel):
    plot_summary: str | None = None
    needs_rewrite: bool | None = None
    scene_labels: list[str] | None = None
    scene_reasoning: str | None = None
    rewrite_source: str | None = None
    rewritten_word_count: int | None = None
    expansion_ratio: float | None = None
    rewrite_elapsed_ms: int | None = None


class ChapterDetailOut(BaseModel):
    chapter: ChapterOut
    ai_outputs: ChapterAIOutputsOut
    stage_statuses: list[StageStatusOut]
    errors: list[ChapterErrorOut]


class ProjectDetailOut(BaseModel):
    project: ProjectOut
    metadata: dict[str, Any]
    settings: dict[str, Any] | None = None
    exports: list[dict[str, Any]]


class PreviewRequest(BaseModel):
    source_path: str = Field(min_length=1)
    workspace_path: str | None = None


class PreviewChapterOut(BaseModel):
    index: int
    title: str
    word_count: int
    start_line: int | None = None
    end_line: int | None = None


class PreviewResponse(BaseModel):
    preview_token: str
    title: str
    author: str | None
    language: str | None
    source_format: str
    source_encoding: str | None
    total_chapters: int
    total_words: int
    chapters: list[PreviewChapterOut]


class CreateProjectRequest(BaseModel):
    preview_token: str = Field(min_length=1)
    project_name: str | None = None
    workspace_path: str | None = None


class ExportResponse(BaseModel):
    ok: bool
    format: Literal["txt", "epub"]
    output_path: str


class TextResultResponse(BaseModel):
    ok: bool
    text: str


class PipelineRunResponse(BaseModel):
    ok: bool
    processed: int
    skipped: int
    failed: int
    paused: bool


class RetryStageRequest(BaseModel):
    stage: Literal["summary", "scene_detection", "rewrite"]


class RewriteTextRequest(BaseModel):
    rewritten_text: str = ""


class ProjectSettingsUpdateRequest(BaseModel):
    model_id: int | None = None
    prompt_template_id: int | None = None
    processing_mode: str = "auto"
    concurrency: int = 1
    target_word_count: int | None = None
    min_expansion_ratio: float | None = None


class ModelOut(BaseModel):
    id: int
    display_name: str
    provider: str
    base_url: str
    model_name: str
    temperature: float
    max_tokens: int | None
    timeout_seconds: int
    is_default: bool
    has_api_key: bool


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


class ModelTestResponse(BaseModel):
    ok: bool
    message: str
    elapsed_ms: int | None = None


class PromptTemplateOut(BaseModel):
    id: int
    name: str
    version: int
    is_default: bool
    global_rules: str
    summary_rules: str
    scene_detection_rules: str
    rewrite_rules: str


class PromptTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    global_rules: str = ""
    summary_rules: str = ""
    scene_detection_rules: str = ""
    rewrite_rules: str = ""
    is_default: bool = False


class ProjectPromptWriteRequest(BaseModel):
    prompt_key: str = Field(min_length=1)
    prompt_text: str = ""


class StyleTemplateOut(BaseModel):
    id: int
    name: str
    description: str
    detail_level: Literal["brief", "standard", "detailed"]
    global_prompt: str
    rewrite_prompt: str
    style_profile: dict[str, Any]
    generated_prompt: str
    source_metadata: dict[str, Any]
    import_metadata: dict[str, Any]
    version: int


class StyleTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    global_prompt: str = ""
    rewrite_prompt: str = ""
    style_profile: dict[str, Any] = Field(default_factory=dict)
    generated_prompt: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_metadata: dict[str, Any] = Field(default_factory=dict)


class StyleTemplateImportRequest(BaseModel):
    content: str = Field(min_length=1)


class StyleTemplateExportResponse(BaseModel):
    content: str


class ProjectStyleBindingRequest(BaseModel):
    style_template_id: int | None = None


class ProjectStyleBindingOut(BaseModel):
    style_template: StyleTemplateOut | None = None
