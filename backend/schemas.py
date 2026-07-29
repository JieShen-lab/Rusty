from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: dict[str, Any] | None = None


class HealthResponse(BaseModel):
    ok: bool
    app: str


class LibraryDocumentOut(BaseModel):
    id: int
    title: str
    author: str | None
    description: str | None
    source_filename: str
    source_format: str
    storage_path: str
    source_size_bytes: int
    stored_size_bytes: int
    chapter_count: int
    word_count: int
    status: str
    favorite: bool
    tags: list[str] = Field(default_factory=list)
    is_project_document: bool = False
    category_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    project_ids: list[int] = Field(default_factory=list)
    created_at: str
    updated_at: str


class LibraryDocumentImportRequest(BaseModel):
    source_path: str = Field(min_length=1)


class LibraryDocumentUpdateRequest(BaseModel):
    title: str = Field(min_length=1)
    author: str | None = None


class LibraryDocumentImportResponse(BaseModel):
    document: LibraryDocumentOut
    created: bool
    storage_format: Literal["txt"] = "txt"


class DocumentProcessingSettings(BaseModel):
    chapter_pattern: str = Field(min_length=1)
    chapter_indent: int = Field(default=0, ge=0, le=8)
    paragraph_indent: int = Field(default=2, ge=0, le=8)
    blank_lines: int = Field(default=1, ge=0, le=3)
    trim_whitespace: bool = True


class DocumentProcessingTemplateOut(BaseModel):
    id: int
    name: str
    settings: DocumentProcessingSettings
    is_default: bool
    created_at: str
    updated_at: str


class DocumentProcessingTemplateCreateRequest(BaseModel):
    name: str = Field(min_length=1)
    settings: DocumentProcessingSettings


class LibraryDocumentRevisionOut(BaseModel):
    id: int
    document_id: int
    revision_number: int
    revision_type: str
    storage_path: str
    template_id: int | None
    parent_revision_id: int | None
    created_at: str


class LibraryDocumentCleanupRequest(BaseModel):
    template_id: int


class LibraryDocumentCleanupResponse(BaseModel):
    document: LibraryDocumentOut
    revision: LibraryDocumentRevisionOut
    created: bool


class DocumentLibrarySettingsOut(BaseModel):
    storage_path: str


class DocumentLibraryMigrateRequest(BaseModel):
    target_path: str = Field(min_length=1)


class ResourceTagOut(BaseModel):
    id: int
    name: str
    normalized_name: str = ""
    sort_order: int = 0
    resource_count: int = 0


class DocumentCategoryOut(BaseModel):
    id: int
    name: str
    normalized_name: str
    sort_order: int = 0
    resource_count: int = 0


class ResourceTagCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class ResourceTagRenameRequest(BaseModel):
    name: str = Field(min_length=1, max_length=40)


class ResourceTagAssignmentRequest(BaseModel):
    selected: bool


class LibraryDocumentChapterOut(BaseModel):
    id: int
    revision_id: int
    index: int
    title: str
    start_line: int | None
    end_line: int | None
    start_offset: int | None = None
    end_offset: int | None = None
    word_count: int
    volume_id: int | None = None


class LibraryDocumentVolumeOut(BaseModel):
    id: int
    revision_id: int
    index: int
    title: str
    start_offset: int
    end_offset: int
    word_count: int
    chapters: list[LibraryDocumentChapterOut] = Field(default_factory=list)


class LibraryDocumentDirectoryOut(BaseModel):
    volumes: list[LibraryDocumentVolumeOut] = Field(default_factory=list)
    unassigned_chapters: list[LibraryDocumentChapterOut] = Field(default_factory=list)


class LibraryDocumentVolumeRenameRequest(BaseModel):
    title: str = Field(min_length=1)


class LibraryDocumentContentOut(BaseModel):
    document_id: int
    revision_id: int
    chapter_id: int | None
    title: str
    text: str
    body_text: str
    section_start_offset: int
    body_start_offset: int
    end_offset: int
    start_offset: int


class LibraryDocumentDraftOut(BaseModel):
    id: int
    document_id: int
    chapter_id: int | None
    base_revision_id: int
    title: str
    text: str
    updated_at: str


class LibraryDocumentDraftWriteRequest(BaseModel):
    base_revision_id: int
    title: str
    text: str
    chapter_id: int | None = None


class LibraryDocumentDraftScopeRequest(BaseModel):
    chapter_id: int | None = None


class LibraryDocumentSaveContentRequest(BaseModel):
    title: str | None = None
    text: str
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


class DocumentCreateChapterResponse(LibraryDocumentCleanupResponse):
    created_chapter_id: int


class SplitChapterCandidate(BaseModel):
    index: int
    title: str
    start_line: int
    end_line: int
    start_offset: int
    end_offset: int
    word_count: int


class SplitPreview(BaseModel):
    preview_token: str
    revision_id: int
    chapter_count: int
    chapters: list[SplitChapterCandidate]


class RegexSplitPreviewRequest(BaseModel):
    pattern: str = Field(min_length=1)


class RegexSplitApplyRequest(BaseModel):
    pattern: str = Field(min_length=1)
    preview_token: str = Field(min_length=1)
    chapters: list[SplitChapterCandidate] | None = None


class ManualChapterMarkRequest(BaseModel):
    revision_id: int
    title: str = Field(min_length=1)
    start_offset: int = Field(ge=0)
    end_offset: int = Field(ge=0)


class AISplitPreviewRequest(BaseModel):
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


class LibraryDocumentExportResponse(BaseModel):
    ok: bool = True
    format: Literal["txt", "epub"]
    output_path: str


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
    plot_characters: list[dict[str, Any]] | None = None
    needs_rewrite: bool | None = None
    scene_labels: list[str] | None = None
    scene_reasoning: str | None = None
    scene_markers: list[dict[str, Any]] | None = None
    plot_expansion_enabled: bool | None = None
    expanded_plot: str | None = None
    rewrite_source: str | None = None
    rewritten_word_count: int | None = None
    expansion_ratio: float | None = None
    rewrite_elapsed_ms: int | None = None
    rewrite_mode: str | None = None
    rewrite_anchor: str | None = None
    rewrite_expanded: str | None = None
    style_analysis: dict[str, Any] | None = None
    reviewed_style_analysis: dict[str, Any] | None = None
    style_analysis_status: str | None = None


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
    split_mode: str = "auto"
    chapters: list[PreviewChapterOut]


class CreateProjectRequest(BaseModel):
    preview_token: str = Field(min_length=1)
    project_name: str | None = None
    workspace_path: str | None = None
    purpose: Literal["rewrite", "extract", "summary"] = "rewrite"
    model_id: int | None = None
    prompt_template_id: int | None = None
    analysis_prompt_template_id: int | None = None


class ExportResponse(BaseModel):
    ok: bool
    format: Literal["txt", "epub"]
    output_path: str


class ExportPlanItemOut(BaseModel):
    chapter_id: int
    export_order: int
    export_title: str
    include_in_export: bool
    source_status: Literal["original", "manual_rewrite", "ai_rewrite", "kept_original"] = "original"


class ExportPlanItemWrite(BaseModel):
    chapter_id: int
    export_order: int
    export_title: str = ""
    include_in_export: bool = True


class ExportPlanUpdateRequest(BaseModel):
    items: list[ExportPlanItemWrite] = Field(min_length=1)


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


class SceneBoundaryItem(BaseModel):
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    title: str = ""
    reasons: list[str] = Field(default_factory=list)


class SceneBoundaryWriteRequest(BaseModel):
    boundaries: list[SceneBoundaryItem] | None = None
    source: str = "ai"
    confirm: bool = False
    model_id: int | None = None


class SceneFactLedgerWriteRequest(BaseModel):
    facts: dict[str, Any] = Field(default_factory=dict)
    source_kind: str = "analysis"
    model_id: int | None = None
    prompt_compilation_id: int | None = None


class CharacterStoryStateWriteRequest(BaseModel):
    character_name: str = Field(min_length=1)
    character_card_id: int | None = None
    state: dict[str, Any] = Field(default_factory=dict)


class StorySkeletonWriteRequest(BaseModel):
    project_id: int
    chapter_id: int
    scene_id: int | None = None
    scope: Literal["scene", "chapter", "volume", "book"] = "scene"
    source_kind: str = "original_analysis"
    nodes: list[dict[str, Any]] = Field(min_length=1)


class StorySkeletonRevisionRequest(BaseModel):
    nodes: list[dict[str, Any]] = Field(min_length=1)
    change_note: str = ""


class RewritePlanWriteRequest(BaseModel):
    project_id: int
    chapter_id: int
    scene_id: int
    mode: Literal["skeleton_rewrite", "expansion"]
    skeleton_version_id: int
    plan: dict[str, Any]
    material_mappings: list[dict[str, Any]] = Field(default_factory=list)


class SceneStageWriteRequest(BaseModel):
    stage: Literal["analysis", "planning", "rewrite", "consistency_check", "targeted_repair"]
    output: dict[str, Any]
    plan_id: int | None = None
    prompt_compilation_id: int | None = None
    status: Literal["pending", "running", "completed", "failed", "needs_confirmation"] = "completed"


class SceneRewriteVersionWriteRequest(BaseModel):
    rewritten_text: str = Field(min_length=1)
    plan_id: int
    skeleton_version_id: int
    prompt_compilation_id: int | None = None
    facts_after: dict[str, Any] = Field(default_factory=dict)


class TargetedRepairWriteRequest(BaseModel):
    source_version_id: int
    paragraph_start: int = Field(ge=0)
    paragraph_end: int = Field(ge=0)
    issues: list[Any] = Field(default_factory=list)
    replacement_text: str = Field(min_length=1)
    affected_facts: dict[str, Any] = Field(default_factory=dict)


class SceneContextCompileRequest(BaseModel):
    stage: str
    system_rules: str
    user_instruction: str = ""
    task: dict[str, Any] = Field(default_factory=dict)
    model_context_tokens: int = Field(default=32768, ge=1024)
    reserved_output_tokens: int = Field(default=4096, ge=1)
    retrieval_results: list[dict[str, Any]] = Field(default_factory=list)
    style_context: dict[str, Any] = Field(default_factory=dict)
    model_id: int | None = None


class SceneRetrievalRequest(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    character_names: list[str] = Field(default_factory=list)
    location: str = ""
    time_hint: str = ""
    manual_material_ids: list[int] = Field(default_factory=list)
    manual_character_ids: list[int] = Field(default_factory=list)
    limit: int = Field(default=24, ge=1, le=100)


class ConsistencyCheckWriteRequest(BaseModel):
    project_id: int
    check_scope: Literal["scene", "chapter", "volume", "book"]
    result: dict[str, Any]


class SceneWorkflowStartRequest(BaseModel):
    mode: Literal["skeleton_rewrite", "expansion"]
    user_instruction: str = ""
    model_id: int | None = None
    character_ids: list[int] = Field(default_factory=list)
    material_ids: list[int] = Field(default_factory=list)


class SceneWorkflowPlanRequest(BaseModel):
    skeleton_version_id: int
    user_instruction: str = ""
    model_id: int | None = None
    character_ids: list[int] = Field(default_factory=list)
    material_mappings: list[dict[str, Any]] = Field(default_factory=list)
    scene_reference_ids: list[int] = Field(default_factory=list)


class SceneWorkflowExecuteRequest(BaseModel):
    user_instruction: str = ""
    model_id: int | None = None
    character_ids: list[int] = Field(default_factory=list)
    plot_skeleton_material_ids: list[int] = Field(default_factory=list)
    scene_reference_ids: list[int] = Field(default_factory=list)
    material_ids: list[int] = Field(default_factory=list)
    chapter_id: int | None = None
    scene_id: int | None = None


class ProjectSettingsUpdateRequest(BaseModel):
    model_id: int | None = None
    prompt_template_id: int | None = None
    analysis_prompt_template_id: int | None = None
    processing_mode: str = "auto"
    concurrency: int = 1
    target_word_count: int | None = None
    min_expansion_ratio: float | None = None
    rewrite_mode: Literal["anchor_expand", "full_rewrite"] = "anchor_expand"
    max_attempts: int = Field(default=2, ge=1, le=10)


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


class PromptSceneRule(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    scene_key: str
    display_name: str
    description: str = ""
    detection_prompt: str = ""
    rewrite_prompt: str = ""
    sort_order: int = 0


class PromptTemplateOut(BaseModel):
    id: int
    name: str
    version: int
    is_default: bool
    global_rules: str
    summary_rules: str
    rewrite_rules: str
    description: str = ""
    scene_rules: list[PromptSceneRule] = Field(default_factory=list)
    package_metadata: dict[str, Any] = Field(default_factory=dict)
    source_project_id: int | None = None


class PromptTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    global_rules: str = ""
    summary_rules: str = ""
    rewrite_rules: str = ""
    description: str = ""
    scene_rules: list[PromptSceneRule] = Field(default_factory=list)
    package_metadata: dict[str, Any] = Field(default_factory=dict)
    source_project_id: int | None = None
    is_default: bool = False


class PromptPackageImportRequest(BaseModel):
    content: str = Field(min_length=1)


class PromptPackageExtractRequest(BaseModel):
    model_id: int | None = None


class PlotExpansionRequest(BaseModel):
    enabled: bool = True


class TargetSkeletonWriteRequest(BaseModel):
    text: str = ""
    enabled: bool = True


class AnalysisPromptTemplateOut(BaseModel):
    id: int
    name: str
    description: str
    analysis_dimensions: str
    evidence_rules: str
    synthesis_rules: str
    output_requirements: str
    version: int
    is_default: bool


class AnalysisPromptTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    analysis_dimensions: str = ""
    evidence_rules: str = ""
    synthesis_rules: str = ""
    output_requirements: str = ""
    is_default: bool = False


class StyleAnalysisOut(BaseModel):
    chapter_id: int
    analysis: dict[str, Any] = Field(default_factory=dict)
    reviewed: dict[str, Any] = Field(default_factory=dict)
    status: str
    analysis_prompt_template_id: int | None = None
    model_id: int | None = None
    elapsed_ms: int | None = None
    updated_at: str | None = None
    reviewed_at: str | None = None


class StyleAnalysisReviewRequest(BaseModel):
    reviewed: dict[str, Any] = Field(default_factory=dict)


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


class StyleTemplateExtractRequest(BaseModel):
    name: str = Field(min_length=1)
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    sample_text: str | None = None
    source_path: str | None = None
    model_id: int | None = None


class StyleTrialWriteRequest(BaseModel):
    sample_scene: str = Field(min_length=1)
    target_chars: int = Field(default=300, ge=80, le=2000)
    model_id: int | None = None


class StyleTemplateExportResponse(BaseModel):
    content: str


class ProjectStyleBindingRequest(BaseModel):
    style_template_id: int | None = None


class ProjectStyleBindingOut(BaseModel):
    style_template: StyleTemplateOut | None = None


class OutlineTemplateOut(BaseModel):
    id: int
    name: str
    description: str
    detail_level: Literal["brief", "standard", "detailed"]
    outline: dict[str, Any]
    anchor_prompt: str
    source_metadata: dict[str, Any]
    import_metadata: dict[str, Any]
    version: int


class OutlineTemplateWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = ""
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    outline: dict[str, Any] = Field(default_factory=dict)
    anchor_prompt: str = ""
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_metadata: dict[str, Any] = Field(default_factory=dict)


class AnchorExtractRequest(BaseModel):
    name: str | None = None
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    sample_text: str | None = None
    source_path: str | None = None
    source_project_id: int | None = None
    source_document_id: int | None = None
    model_id: int | None = None
    scope: Literal["public", "project"] = "public"
    project_id: int | None = None


class MaterialOut(BaseModel):
    id: int
    material_type: Literal["scene_reference", "plot_skeleton"]
    scope: Literal["public", "project"]
    project_id: int | None = None
    project_name: str | None = None
    name: str
    description: str
    detail_level: Literal["brief", "standard", "detailed"]
    raw_text: str = ""
    content: dict[str, Any]
    analysis_status: Literal["unanalyzed", "analyzed"] = "analyzed"
    source_metadata: dict[str, Any]
    import_metadata: dict[str, Any]
    source_material_id: int | None = None
    source_version: int | None = None
    timeline_start_chapter: int | None = None
    timeline_end_chapter: int | None = None
    sort_order: int = 0
    version: int
    created_at: str
    updated_at: str
    tags: list[str] = Field(default_factory=list)


class MaterialWriteRequest(BaseModel):
    material_type: Literal["scene_reference", "plot_skeleton"]
    scope: Literal["public", "project"] = "public"
    project_id: int | None = None
    name: str = Field(min_length=1)
    description: str = ""
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    raw_text: str = ""
    content: dict[str, Any] = Field(default_factory=dict)
    analysis_status: Literal["unanalyzed", "analyzed"] = "analyzed"
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_metadata: dict[str, Any] = Field(default_factory=dict)
    timeline_start_chapter: int | None = Field(default=None, ge=1)
    timeline_end_chapter: int | None = Field(default=None, ge=1)
    sort_order: int = 0
    tag_ids: list[int] = Field(default_factory=list)


class MaterialUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1)
    description: str = ""
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    raw_text: str | None = None
    content: dict[str, Any] = Field(default_factory=dict)
    analysis_status: Literal["unanalyzed", "analyzed"] | None = None
    timeline_start_chapter: int | None = Field(default=None, ge=1)
    timeline_end_chapter: int | None = Field(default=None, ge=1)
    sort_order: int = 0
    tag_ids: list[int] | None = None


class MaterialCopyRequest(BaseModel):
    target_scope: Literal["public", "project"]
    target_project_id: int | None = None
    tag_ids: list[int] = Field(default_factory=list)


class MaterialAnalyzeRequest(BaseModel):
    model_id: int | None = None


class MaterialAnalysisApplyRequest(BaseModel):
    content: dict[str, Any]
    model_id: int
    invocation_id: int


class MaterialJsonImportRequest(BaseModel):
    value: Any
    default_scope: Literal["public", "project"] = "public"
    default_project_id: int | None = None


class MaterialExtractRequest(AnchorExtractRequest):
    material_type: Literal["scene_reference", "plot_skeleton"]


class MaterialExtractOut(BaseModel):
    materials: list[MaterialOut]


class CharacterSourceSummaryOut(BaseModel):
    kind: Literal[
        "manual",
        "document_selection",
        "project_selection",
        "file_import",
        "ai_extraction",
        "public_copy",
        "project_copy",
    ]
    label: str
    document_id: int | None = None
    chapter_id: int | None = None
    project_id: int | None = None
    source_card_id: int | None = None


class CharacterCardOut(BaseModel):
    id: int
    name: str
    aliases: list[str]
    description: str
    priority: int
    is_main: bool
    relationship_notes: str
    personality: str
    speech_style: str
    action_constraints: str
    anti_ooc_rules: str
    profile: dict[str, Any]
    source_metadata: dict[str, Any]
    import_metadata: dict[str, Any]
    scope: Literal["public", "project"] = "public"
    project_id: int | None = None
    source_character_card_id: int | None = None
    source_version: int | None = None
    version: int
    sort_order: int = 0
    identity: str = ""
    age: str = ""
    setting_text: str = ""
    custom_fields: list[dict[str, Any]] = Field(default_factory=list)
    raw_text: str = ""
    analysis_status: Literal["unanalyzed", "analyzed"] = "analyzed"
    cover_path: str | None = None
    cover_updated_at: str | None = None
    tags: list[str] = Field(default_factory=list)
    category_ids: list[int] = Field(default_factory=list)
    categories: list[str] = Field(default_factory=list)
    source_summary: CharacterSourceSummaryOut
    created_at: str = ""
    updated_at: str = ""


class CharacterCategoryOut(BaseModel):
    id: int
    name: str
    normalized_name: str
    sort_order: int
    resource_count: int


class CharacterProjectSummaryOut(BaseModel):
    project_id: int
    project_name: str
    character_count: int
    updated_at: str


class CharacterCardWriteRequest(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    priority: int = Field(default=50, ge=0, le=100)
    is_main: bool = False
    relationship_notes: str = ""
    personality: str = ""
    speech_style: str = ""
    action_constraints: str = ""
    anti_ooc_rules: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    source_metadata: dict[str, Any] = Field(default_factory=dict)
    import_metadata: dict[str, Any] = Field(default_factory=dict)
    scope: Literal["public", "project"] = "public"
    project_id: int | None = None
    identity: str = ""
    age: str = ""
    setting_text: str = ""
    custom_fields: list[dict[str, Any]] = Field(default_factory=list)
    raw_text: str = ""
    analysis_status: Literal["unanalyzed", "analyzed"] = "analyzed"
    tag_ids: list[int] = Field(default_factory=list)


class CharacterCardCopyRequest(BaseModel):
    target_scope: Literal["public", "project"]
    target_project_id: int | None = None


class CharacterCopyToProjectRequest(BaseModel):
    target_project_id: int
    force: bool = False


class CharacterPublishRequest(BaseModel):
    selected_fields: list[str]


class CharacterExtractionSettingsOut(BaseModel):
    model_id: int | None = None
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    max_candidates: int = Field(default=8, ge=1, le=20)
    extract_all_characters: bool = True
    generate_tags: bool = True
    generate_appearance: bool = True
    generate_relationships: bool = True
    generate_personality: bool = True
    generate_speech_style: bool = True
    generate_action_constraints: bool = True
    generate_anti_ooc_rules: bool = True
    generate_abilities_background: bool = True
    custom_requirements: str = ""
    system_prompt: str = ""
    prompt_preview: str = ""


class CharacterExtractionSettingsWriteRequest(BaseModel):
    model_id: int | None = None
    detail_level: Literal["brief", "standard", "detailed"] = "standard"
    max_candidates: int = Field(default=8, ge=1, le=20)
    extract_all_characters: bool = True
    generate_tags: bool = True
    generate_appearance: bool = True
    generate_relationships: bool = True
    generate_personality: bool = True
    generate_speech_style: bool = True
    generate_action_constraints: bool = True
    generate_anti_ooc_rules: bool = True
    generate_abilities_background: bool = True
    custom_requirements: str = ""
    system_prompt: str = ""


class CharacterExtractionPreviewRequest(BaseModel):
    sample_text: str = Field(min_length=1, max_length=50000)
    name: str | None = None
    detail_level: Literal["brief", "standard", "detailed"] | None = None
    model_id: int | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)


class CharacterExtractionCandidateOut(BaseModel):
    candidate_id: str
    selected: bool = True
    name: str
    aliases: list[str] = Field(default_factory=list)
    description: str = ""
    identity: str = ""
    age: str = ""
    setting_text: str = ""
    relationship_notes: str = ""
    personality: str = ""
    speech_style: str = ""
    action_constraints: str = ""
    anti_ooc_rules: str = ""
    profile: dict[str, Any] = Field(default_factory=dict)
    custom_fields: list[dict[str, Any]] = Field(default_factory=list)
    suggested_tags: list[str] = Field(default_factory=list)
    evidence_summary: str = ""


class CharacterExtractionPreviewOut(BaseModel):
    preview_token: str
    source_summary: CharacterSourceSummaryOut
    candidates: list[CharacterExtractionCandidateOut]


class CharacterExtractionCandidateApply(CharacterExtractionCandidateOut):
    confirmed_tags: list[str] = Field(default_factory=list)


class CharacterExtractionApplyRequest(BaseModel):
    preview_token: str
    candidates: list[CharacterExtractionCandidateApply]
    selected_candidate_ids: list[str]
    scope: Literal["public", "project"] = "public"
    project_id: int | None = None
    category_ids: list[int] = Field(default_factory=list)


class CharacterExtractionApplyItemOut(BaseModel):
    candidate_id: str
    card_id: int | None = None
    error: str | None = None


class CharacterExtractionApplyOut(BaseModel):
    created: list[CharacterExtractionApplyItemOut]
    errors: list[CharacterExtractionApplyItemOut]


class CharacterAnalyzeRequest(BaseModel):
    model_id: int | None = None


class CharacterAnalysisConfirmRequest(BaseModel):
    identity: str = ""
    age: str = ""
    setting_text: str = ""
    custom_fields: list[dict[str, Any]] = Field(default_factory=list)
    invocation_id: int | None = None


class CharacterCoverWriteRequest(BaseModel):
    data_base64: str = Field(min_length=1)


class SelectionResourceCreateRequest(BaseModel):
    source_kind: Literal["document", "project"]
    selected_text: str = Field(min_length=1, max_length=50000)
    name: str = Field(min_length=1)
    document_id: int | None = None
    project_id: int | None = None
    chapter_id: int | None = None
    start_offset: int | None = None
    end_offset: int | None = None
    source_version: int | None = None
    save_to_public: bool = False
    tag_ids: list[int] = Field(default_factory=list)


class ProjectOutlineBindingRequest(BaseModel):
    outline_template_id: int | None = None


class ProjectOutlineBindingOut(BaseModel):
    outline_template: OutlineTemplateOut | None = None


class ProjectCharacterBindingRequest(BaseModel):
    character_card_id: int
    sort_order: int = 0


class ProjectCharacterBindingsOut(BaseModel):
    character_cards: list[CharacterCardOut]


class CharacterCardsExtractOut(BaseModel):
    character_cards: list[CharacterCardOut]
