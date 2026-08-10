from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictWorkflowModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class StoryAnchorRequest(StrictWorkflowModel):
    anchor_type: Literal[
        "document_end",
        "chapter_start",
        "chapter_end",
        "scene_start",
        "scene_end",
        "skeleton_node",
        "text_offset",
        "branch_chapter",
        "branch_scene",
    ]
    chapter_id: int | None = Field(default=None, ge=1)
    scene_id: int | None = Field(default=None, ge=1)
    skeleton_version_id: int | None = Field(default=None, ge=1)
    node_id: str | None = Field(default=None, min_length=1)
    branch_chapter_id: int | None = Field(default=None, ge=1)
    branch_scene_id: int | None = Field(default=None, ge=1)
    text_offset: int | None = Field(default=None, ge=0)
    side: Literal["before", "after", "at"] | None = None
    source_version_id: int | None = Field(default=None, ge=1)
    source_hash: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_target(self) -> "StoryAnchorRequest":
        requirements = {
            "chapter_start": ("chapter_id",),
            "chapter_end": ("chapter_id",),
            "scene_start": ("scene_id",),
            "scene_end": ("scene_id",),
            "skeleton_node": ("skeleton_version_id", "node_id"),
            "text_offset": ("text_offset", "side"),
            "branch_chapter": ("branch_chapter_id",),
            "branch_scene": ("branch_scene_id",),
        }
        missing = [
            field_name
            for field_name in requirements.get(self.anchor_type, ())
            if getattr(self, field_name) is None
        ]
        if missing:
            raise ValueError(f"{self.anchor_type} anchor requires: {', '.join(missing)}")
        return self


class BranchCreateRequest(StrictWorkflowModel):
    name: str = Field(min_length=1)
    branch_mode: Literal["open_continuation", "fork"]
    start_anchor: StoryAnchorRequest


class StoryBranchResponse(BaseModel):
    id: int
    project_id: int
    parent_branch_id: int | None
    base_source_kind: str
    base_source_version_id: int | None
    name: str
    branch_mode: str
    downstream_strategy: str
    status: str
    start_anchor: dict[str, Any] | None = None
    return_anchor: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class CurrentChapterSource(StrictWorkflowModel):
    kind: Literal["current"] = "current"


class OriginalChapterSource(StrictWorkflowModel):
    kind: Literal["original"] = "original"


class RewriteVersionChapterSource(StrictWorkflowModel):
    kind: Literal["rewrite_version"]
    version_id: int = Field(ge=1)


ChapterSourceSelection = (
    CurrentChapterSource | OriginalChapterSource | RewriteVersionChapterSource
)


class StoryAnchorPreviewRequest(StrictWorkflowModel):
    project_id: int = Field(ge=1)
    source: ChapterSourceSelection = Field(default_factory=CurrentChapterSource)
    anchor: StoryAnchorRequest


class StoryAnchorPreviewResponse(BaseModel):
    resolved_version_id: int | None
    resolved_start: int
    resolved_end: int
    text_excerpt: str
    state_before: dict[str, Any]
    state_after: dict[str, Any]
    mapping_method: Literal["identity", "shifted", "structural", "semantic"]
    state_method: str
    confidence: float
    semantic_map_hash: str | None = None


class PlotGenerationStartRequest(StrictWorkflowModel):
    project_id: int = Field(ge=1)
    generation_mode: Literal[
        "bounded_insert", "open_continuation", "fork"
    ]
    start_anchor: StoryAnchorRequest
    return_anchor: StoryAnchorRequest | None = None
    user_direction: str = Field(min_length=1)
    selected_character_ids: list[int] = Field(default_factory=list)
    selected_material_ids: list[int] = Field(default_factory=list)
    style_profile_id: int | None = Field(default=None, ge=1)
    branch_id: int | None = Field(default=None, ge=1)
    branch_name: str = Field(default="Generated branch", min_length=1)
    range_operation: Literal["insert_between", "replace_range"] = "insert_between"
    source: ChapterSourceSelection = Field(default_factory=CurrentChapterSource)

    @model_validator(mode="after")
    def validate_return_anchor(self) -> "PlotGenerationStartRequest":
        requires_return = self.generation_mode == "bounded_insert"
        if requires_return and self.return_anchor is None:
            raise ValueError(f"{self.generation_mode} requires return_anchor")
        if not requires_return and self.return_anchor is not None:
            raise ValueError(f"{self.generation_mode} does not accept return_anchor")
        return self


class PlotGenerationSkeletonConfirmRequest(StrictWorkflowModel):
    target_skeleton: dict[str, Any]


class GeneratedSceneRequest(StrictWorkflowModel):
    title: str = ""
    text: str = Field(min_length=1)
    facts_after: dict[str, Any] = Field(default_factory=dict)


class PlotGenerationExecuteRequest(StrictWorkflowModel):
    max_scenes: int | None = Field(default=None, ge=1)


PlotGenerationStatus = Literal[
    "awaiting_skeleton",
    "planning_blocked",
    "awaiting_seams",
    "ready",
    "generating",
    "repair_required",
    "completed",
    "failed",
    "cancelled",
]


class PlotGenerationRunResponse(BaseModel):
    id: int
    project_id: int
    branch_id: int | None
    generation_mode: str
    range_operation: str = "insert_between"
    output_topology: str
    status: PlotGenerationStatus
    stage: str
    start_anchor: dict[str, Any]
    return_anchor: dict[str, Any] | None
    start_state: dict[str, Any]
    required_return_state: dict[str, Any]
    target_skeleton: dict[str, Any]
    context: dict[str, Any]
    seams: list[dict[str, Any]] | dict[str, Any]
    issues: list[dict[str, Any]] | dict[str, Any]
    result: dict[str, Any]
    scene_plan: dict[str, Any]
    fact_ledger: dict[str, Any]
    generated_progress: dict[str, Any]
    next_scene_cursor: int
    generation_attempt: int
    source_chapter_id: int | None = None
    source_base_kind: Literal["original", "rewrite_version"] | None = None
    source_base_version_id: int | None = None
    source_hash: str | None = None
    expected_source_head_version_id: int | None = None
    source_map_hash: str | None = None
    resolved_start_anchor: dict[str, Any] = Field(default_factory=dict)
    resolved_return_anchor: dict[str, Any] | None = None
    result_version_id: int | None = None
    operation_type: Literal["plot_generation"] = "plot_generation"
    user_direction: str
    created_at: str
    updated_at: str


class ProseRewritePlanRequest(StrictWorkflowModel):
    project_id: int = Field(ge=1)
    chapter_id: int = Field(ge=1)
    source_skeleton: dict[str, Any]
    source_skeleton_version_id: int = Field(ge=1)
    preservation_policy: dict[str, Any]
    style_profile_id: int | None = Field(default=None, ge=1)
    user_direction: str = ""
    source: ChapterSourceSelection = Field(default_factory=CurrentChapterSource)


class ProseRewriteExecuteRequest(StrictWorkflowModel):
    pass


class ProseRewriteRunResponse(BaseModel):
    id: int
    project_id: int
    chapter_id: int
    status: Literal["planned", "generating", "blocked", "completed", "failed", "cancelled"]
    source_skeleton: dict[str, Any]
    source_skeleton_version_id: int | None = None
    preservation_policy: dict[str, Any]
    target_skeleton: dict[str, Any]
    rewrite_plan: dict[str, Any]
    rewritten_text: str | None
    issues: list[dict[str, Any]]
    source_base_kind: Literal["original", "rewrite_version"] | None = None
    source_base_version_id: int | None = None
    source_hash: str | None = None
    expected_source_head_version_id: int | None = None
    source_map_hash: str | None = None
    result_version_id: int | None = None
    generation_attempt: int = 0
    operation_type: Literal["prose_rewrite"] = "prose_rewrite"
    created_at: str
    updated_at: str


class ChapterRewriteVersionResponse(BaseModel):
    id: int
    project_id: int
    chapter_id: int
    version: int
    parent_version_id: int | None
    source_kind: str
    source_operation: Literal[
        "plot_generation", "prose_rewrite", "canon_change",
        "manual", "migration", "restore"
    ]
    source_run_id: int | None
    source_base_kind: Literal["original", "rewrite_version"]
    source_base_version_id: int | None
    source_hash: str
    rewritten_text: str
    content_hash: str
    facts_before: dict[str, Any]
    facts_after: dict[str, Any]
    fact_chain_status: Literal["consistent", "needs_recompute"] = "needs_recompute"
    is_current: bool
    created_at: str


class RewriteVersionSkeletonResponse(BaseModel):
    rewrite_version_id: int
    skeleton_id: int
    skeleton_version_id: int
    structured: dict[str, Any]
    source_kind: Literal["rewrite_version"]
    status: str
