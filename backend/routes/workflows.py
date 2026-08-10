from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import APIRouter, Depends, HTTPException

from rusty.models import ProjectSummary
from rusty.services.branch_service import BranchService
from rusty.services.canon_change_orchestrator import CanonChangeOrchestrator
from rusty.services.chapter_version_service import ChapterVersionService
from rusty.services.context_service import ContextService
from rusty.services.plot_generation_orchestrator import PlotGenerationOrchestrator
from rusty.services.project_service import ProjectService
from rusty.services.prose_rewrite_orchestrator import ProseRewriteOrchestrator
from rusty.services.rewrite_version_map_service import RewriteVersionMapService

from backend.schemas import (
    BranchCreateRequest,
    CanonChangeRunResponse,
    CanonChangeScanRequest,
    CanonPatchResponse,
    CanonPatchReviewRequest,
    ChapterRewriteVersionResponse,
    PlotGenerationExecuteRequest,
    PlotGenerationRunResponse,
    PlotGenerationSeamConfirmRequest,
    PlotGenerationSkeletonConfirmRequest,
    PlotGenerationStartRequest,
    ProseRewriteExecuteRequest,
    ProseRewritePlanRequest,
    ProseRewriteRunResponse,
    RewriteVersionSkeletonResponse,
    StoryAnchorPreviewRequest,
    StoryAnchorPreviewResponse,
    StoryBranchResponse,
)


@dataclass(frozen=True)
class WorkflowRouteServices:
    projects: ProjectService
    branches: BranchService
    plot: PlotGenerationOrchestrator
    prose: ProseRewriteOrchestrator
    canon: CanonChangeOrchestrator
    chapters: ChapterVersionService
    rewrite_maps: RewriteVersionMapService
    contexts: ContextService


def create_workflow_router(
    services: WorkflowRouteServices,
    *,
    require_token: Callable[..., None],
    require_project: Callable[[ProjectService, int], ProjectSummary],
    http_error: Callable[[int, str, str], HTTPException],
) -> APIRouter:
    router = APIRouter()
    write_dependencies = [Depends(require_token)]

    @router.get(
        "/api/projects/{project_id}/branches",
        response_model=list[StoryBranchResponse],
    )
    def list_story_branches(project_id: int) -> list[dict[str, Any]]:
        require_project(services.projects, project_id)
        return services.branches.list_branches(project_id)

    @router.get("/api/branches/{branch_id}", response_model=StoryBranchResponse)
    def get_story_branch(branch_id: int) -> dict[str, Any]:
        return services.branches.get_branch(branch_id)

    @router.get("/api/branches/{branch_id}/chapters", response_model=list[dict[str, Any]])
    def list_story_branch_chapters(branch_id: int) -> list[dict[str, Any]]:
        return services.branches.list_chapters(branch_id)

    @router.post(
        "/api/projects/{project_id}/branches",
        response_model=StoryBranchResponse,
        dependencies=write_dependencies,
    )
    def create_story_branch(
        project_id: int, payload: BranchCreateRequest
    ) -> dict[str, Any]:
        project = require_project(services.projects, project_id)
        if project.project_kind != "branch":
            raise http_error(
                409, "branch_project_required", "Branches require a branch project."
            )
        values = payload.model_dump()
        return services.branches.create_branch(
            project_id=project_id,
            name=values["name"],
            branch_mode=values["branch_mode"],
            start_anchor=values["start_anchor"],
            return_anchor=values["return_anchor"],
            parent_branch_id=values.get("parent_branch_id"),
            base_source_version_id=values.get("base_source_version_id"),
            downstream_strategy=values.get("downstream_strategy"),
        )

    @router.post("/api/branches/{branch_id}/delete", dependencies=write_dependencies)
    def delete_story_branch(branch_id: int) -> dict[str, bool]:
        services.branches.delete_branch(branch_id)
        return {"ok": True}

    @router.post(
        "/api/plot-generation/runs",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def start_plot_generation(payload: PlotGenerationStartRequest) -> dict[str, Any]:
        return services.plot.start(**payload.model_dump())

    @router.post(
        "/api/story-anchors/preview",
        response_model=StoryAnchorPreviewResponse,
        dependencies=write_dependencies,
    )
    def preview_story_anchor(payload: StoryAnchorPreviewRequest) -> dict[str, Any]:
        values = payload.model_dump()
        return services.contexts.preview_story_anchor(
            project_id=values["project_id"],
            source=values["source"],
            anchor=values["anchor"],
        )

    @router.get(
        "/api/plot-generation/runs/{run_id}",
        response_model=PlotGenerationRunResponse,
    )
    def get_plot_generation_run(run_id: int) -> dict[str, Any]:
        return services.plot.get_run(run_id)

    @router.get(
        "/api/projects/{project_id}/plot-generation/runs",
        response_model=list[PlotGenerationRunResponse],
    )
    def list_plot_generation_runs(project_id: int) -> list[dict[str, Any]]:
        require_project(services.projects, project_id)
        return services.plot.list_runs(project_id)

    @router.post(
        "/api/plot-generation/runs/{run_id}/cancel",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def cancel_plot_generation(run_id: int) -> dict[str, Any]:
        return services.plot.cancel(run_id)

    @router.post(
        "/api/plot-generation/runs/{run_id}/seams",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def confirm_plot_generation_seams(
        run_id: int, payload: PlotGenerationSeamConfirmRequest
    ) -> dict[str, Any]:
        return services.plot.confirm_seams(
            run_id, [review.model_dump() for review in payload.reviews]
        )

    @router.post(
        "/api/plot-generation/runs/{run_id}/skeleton",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def confirm_plot_generation_skeleton(
        run_id: int, payload: PlotGenerationSkeletonConfirmRequest
    ) -> dict[str, Any]:
        return services.plot.confirm_target_skeleton(run_id, payload.target_skeleton)

    @router.post(
        "/api/plot-generation/runs/{run_id}/execute",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def execute_plot_generation(
        run_id: int, payload: PlotGenerationExecuteRequest
    ) -> dict[str, Any]:
        return services.plot.execute(run_id, max_scenes=payload.max_scenes)

    @router.post(
        "/api/plot-generation/runs/{run_id}/generate-next",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def generate_next_plot_scene(run_id: int) -> dict[str, Any]:
        return services.plot.generate_next(run_id)

    @router.post(
        "/api/plot-generation/runs/{run_id}/retry",
        response_model=PlotGenerationRunResponse,
        dependencies=write_dependencies,
    )
    def retry_plot_generation(run_id: int) -> dict[str, Any]:
        return services.plot.retry(run_id)

    @router.post(
        "/api/prose-rewrite/runs",
        response_model=ProseRewriteRunResponse,
        dependencies=write_dependencies,
    )
    def plan_prose_rewrite(payload: ProseRewritePlanRequest) -> dict[str, Any]:
        values = payload.model_dump()
        values["source_selection"] = values.pop("source")
        return services.prose.plan(**values)

    @router.get(
        "/api/prose-rewrite/runs/{run_id}",
        response_model=ProseRewriteRunResponse,
    )
    def get_prose_rewrite_run(run_id: int) -> dict[str, Any]:
        return services.prose.get_run(run_id)

    @router.get(
        "/api/projects/{project_id}/prose-rewrite/runs",
        response_model=list[ProseRewriteRunResponse],
    )
    def list_prose_rewrite_runs(project_id: int) -> list[dict[str, Any]]:
        require_project(services.projects, project_id)
        return services.prose.list_runs(project_id)

    @router.post(
        "/api/prose-rewrite/runs/{run_id}/execute",
        response_model=ProseRewriteRunResponse,
        dependencies=write_dependencies,
    )
    def execute_prose_rewrite(
        run_id: int, payload: ProseRewriteExecuteRequest
    ) -> dict[str, Any]:
        return services.prose.execute(run_id, **payload.model_dump())

    @router.post(
        "/api/prose-rewrite/runs/{run_id}/cancel",
        response_model=ProseRewriteRunResponse,
        dependencies=write_dependencies,
    )
    def cancel_prose_rewrite(run_id: int) -> dict[str, Any]:
        return services.prose.cancel(run_id)

    @router.post(
        "/api/prose-rewrite/runs/{run_id}/retry",
        response_model=ProseRewriteRunResponse,
        dependencies=write_dependencies,
    )
    def retry_prose_rewrite(run_id: int) -> dict[str, Any]:
        return services.prose.retry(run_id)

    @router.post(
        "/api/canon-change/runs",
        response_model=CanonChangeRunResponse,
        dependencies=write_dependencies,
    )
    def scan_canon_change(payload: CanonChangeScanRequest) -> dict[str, Any]:
        return services.canon.scan(**payload.model_dump())

    @router.get(
        "/api/canon-change/runs/{run_id}",
        response_model=CanonChangeRunResponse,
    )
    def get_canon_change_run(run_id: int) -> dict[str, Any]:
        return services.canon.get_run(run_id)

    @router.get(
        "/api/projects/{project_id}/canon-change/runs",
        response_model=list[CanonChangeRunResponse],
    )
    def list_canon_change_runs(project_id: int) -> list[dict[str, Any]]:
        require_project(services.projects, project_id)
        return services.canon.list_runs(project_id)

    @router.post(
        "/api/canon-change/patches/{patch_id}/review",
        response_model=CanonPatchResponse,
        dependencies=write_dependencies,
    )
    def review_canon_patch(
        patch_id: int, payload: CanonPatchReviewRequest
    ) -> dict[str, Any]:
        return services.canon.review_patch(patch_id, **payload.model_dump())

    @router.post(
        "/api/canon-change/runs/{run_id}/apply",
        response_model=CanonChangeRunResponse,
        dependencies=write_dependencies,
    )
    def apply_canon_change(run_id: int) -> dict[str, Any]:
        return services.canon.apply(run_id)

    @router.post(
        "/api/canon-change/runs/{run_id}/cancel",
        response_model=CanonChangeRunResponse,
        dependencies=write_dependencies,
    )
    def cancel_canon_change(run_id: int) -> dict[str, Any]:
        return services.canon.cancel(run_id)

    @router.get(
        "/api/chapters/{chapter_id}/rewrite-versions",
        response_model=list[ChapterRewriteVersionResponse],
    )
    def list_chapter_rewrite_versions(chapter_id: int) -> list[dict[str, Any]]:
        if services.projects.get_chapter(chapter_id) is None:
            raise http_error(404, "chapter_not_found", "Chapter not found.")
        return services.chapters.list_versions(chapter_id)

    @router.get(
        "/api/chapter-rewrite-versions/{version_id}",
        response_model=ChapterRewriteVersionResponse,
    )
    def get_chapter_rewrite_version(version_id: int) -> dict[str, Any]:
        return services.chapters.get_version(version_id)

    @router.get("/api/chapter-rewrite-versions/{version_id}/anchors")
    def list_rewrite_version_anchors(version_id: int) -> list[dict[str, Any]]:
        services.chapters.get_version(version_id)
        return services.rewrite_maps.list_segments(version_id)

    @router.get(
        "/api/chapter-rewrite-versions/{version_id}/skeleton",
        response_model=RewriteVersionSkeletonResponse,
    )
    def get_rewrite_version_skeleton(version_id: int) -> dict[str, Any]:
        services.chapters.get_version(version_id)
        try:
            structure = services.rewrite_maps.get_rewrite_structure(version_id)
        except ValueError as exc:
            raise http_error(404, "rewrite_structure_unavailable", str(exc)) from exc
        assert structure is not None
        return structure

    @router.post(
        "/api/chapter-rewrite-versions/{version_id}/restore",
        response_model=ChapterRewriteVersionResponse,
        dependencies=write_dependencies,
    )
    def restore_chapter_rewrite_version(version_id: int) -> dict[str, Any]:
        return services.chapters.restore_version(version_id)

    return router
