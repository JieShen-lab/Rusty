import type {
  BranchChapterRecord,
  BranchCreateRequest,
  CanonChangeRun,
  CanonChangeScanRequest,
  CanonPatch,
  CanonPatchReviewRequest,
  ChapterRewriteVersion,
  ChapterSourceSelection,
  PlotGenerationExecuteRequest,
  PlotGenerationRun,
  PlotGenerationSeamConfirmRequest,
  PlotGenerationStartRequest,
  ProseRewriteExecuteRequest,
  ProseRewritePlanRequest,
  ProseRewriteRun,
  RewriteSemanticSegment,
  RewriteVersionSkeleton,
  StoryAnchor,
  StoryAnchorPreview,
  StoryBranch,
  StructuredSkeleton,
} from './types';
import { request } from './client';

export function getChapterRewriteVersions(chapterId: number) {
  return request<ChapterRewriteVersion[]>(`/api/chapters/${chapterId}/rewrite-versions`);
}

export function getChapterRewriteVersion(versionId: number) {
  return request<ChapterRewriteVersion>(`/api/chapter-rewrite-versions/${versionId}`);
}

export function getRewriteVersionAnchors(versionId: number) {
  return request<RewriteSemanticSegment[]>(`/api/chapter-rewrite-versions/${versionId}/anchors`);
}

export function getRewriteVersionSkeleton(versionId: number) {
  return request<RewriteVersionSkeleton>(`/api/chapter-rewrite-versions/${versionId}/skeleton`);
}

export function previewStoryAnchor(payload: {
  project_id: number;
  source: ChapterSourceSelection;
  anchor: StoryAnchor;
}) {
  return request<StoryAnchorPreview>('/api/story-anchors/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function restoreChapterRewriteVersion(versionId: number) {
  return request<ChapterRewriteVersion>(`/api/chapter-rewrite-versions/${versionId}/restore`, {
    method: 'POST',
  });
}

export function getStoryBranches(projectId: number) {
  return request<StoryBranch[]>(`/api/projects/${projectId}/branches`);
}

export function getBranchChapters(branchId: number) {
  return request<BranchChapterRecord[]>(`/api/branches/${branchId}/chapters`);
}

export function createStoryBranch(projectId: number, payload: BranchCreateRequest) {
  return request<StoryBranch>(`/api/projects/${projectId}/branches`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteStoryBranch(branchId: number) {
  return request<{ ok: boolean }>(`/api/branches/${branchId}/delete`, { method: 'POST' });
}

export function startPlotGeneration(payload: PlotGenerationStartRequest) {
  return request<PlotGenerationRun>('/api/plot-generation/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getPlotGenerationRun(runId: number) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}`);
}

export function getPlotGenerationRuns(projectId: number) {
  return request<PlotGenerationRun[]>(`/api/projects/${projectId}/plot-generation/runs`);
}

export function cancelPlotGeneration(runId: number) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/cancel`, {
    method: 'POST',
  });
}

export function confirmPlotGenerationSeams(runId: number, payload: PlotGenerationSeamConfirmRequest) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/seams`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function confirmPlotGenerationSkeleton(runId: number, targetSkeleton: StructuredSkeleton) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/skeleton`, {
    method: 'POST',
    body: JSON.stringify({ target_skeleton: targetSkeleton }),
  });
}

export function executePlotGeneration(runId: number, payload: PlotGenerationExecuteRequest) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateNextPlotScene(runId: number) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/generate-next`, {
    method: 'POST',
  });
}

export function retryPlotGeneration(runId: number) {
  return request<PlotGenerationRun>(`/api/plot-generation/runs/${runId}/retry`, {
    method: 'POST',
  });
}

export function planProseRewrite(payload: ProseRewritePlanRequest) {
  return request<ProseRewriteRun>('/api/prose-rewrite/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getProseRewriteRun(runId: number) {
  return request<ProseRewriteRun>(`/api/prose-rewrite/runs/${runId}`);
}

export function getProseRewriteRuns(projectId: number) {
  return request<ProseRewriteRun[]>(`/api/projects/${projectId}/prose-rewrite/runs`);
}

export function executeProseRewrite(runId: number, payload: ProseRewriteExecuteRequest) {
  return request<ProseRewriteRun>(`/api/prose-rewrite/runs/${runId}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function cancelProseRewrite(runId: number) {
  return request<ProseRewriteRun>(`/api/prose-rewrite/runs/${runId}/cancel`, {
    method: 'POST',
  });
}

export function retryProseRewrite(runId: number) {
  return request<ProseRewriteRun>(`/api/prose-rewrite/runs/${runId}/retry`, {
    method: 'POST',
  });
}

export function scanCanonChange(payload: CanonChangeScanRequest) {
  return request<CanonChangeRun>('/api/canon-change/runs', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getCanonChangeRun(runId: number) {
  return request<CanonChangeRun>(`/api/canon-change/runs/${runId}`);
}

export function getCanonChangeRuns(projectId: number) {
  return request<CanonChangeRun[]>(`/api/projects/${projectId}/canon-change/runs`);
}

export function reviewCanonPatch(patchId: number, payload: CanonPatchReviewRequest) {
  return request<CanonPatch>(`/api/canon-change/patches/${patchId}/review`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function applyCanonChange(runId: number) {
  return request<CanonChangeRun>(`/api/canon-change/runs/${runId}/apply`, { method: 'POST' });
}

export function cancelCanonChange(runId: number) {
  return request<CanonChangeRun>(`/api/canon-change/runs/${runId}/cancel`, {
    method: 'POST',
  });
}
