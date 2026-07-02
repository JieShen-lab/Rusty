import type {
  Chapter,
  ChapterDetail,
  ModelConfig,
  ModelTestResult,
  ModelWrite,
  PreviewResponse,
  Project,
  ProjectDetail,
  ProjectSettingsWrite,
  PromptTemplate,
  PromptTemplateWrite,
  PipelineRunResult,
} from './types';

const API_BASE = import.meta.env.VITE_RUSTY_API_URL ?? 'http://127.0.0.1:8765';
const API_TOKEN = import.meta.env.VITE_RUSTY_API_TOKEN ?? '';

export class ApiError extends Error {
  status: number;
  details: unknown;

  constructor(status: number, message: string, details?: unknown) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  if (API_TOKEN) {
    headers.set('X-Rusty-Token', API_TOKEN);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  } catch (error) {
    throw new ApiError(0, `无法连接 Rusty 后端：${String(error)}`);
  }

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;
  if (!response.ok) {
    throw new ApiError(response.status, data?.message ?? response.statusText, data?.details);
  }
  return data as T;
}

export function getHealth() {
  return request<{ ok: boolean; app: string }>('/api/health');
}

export function getProjects() {
  return request<Project[]>('/api/projects');
}

export function getProject(projectId: number) {
  return request<ProjectDetail>(`/api/projects/${projectId}`);
}

export function getChapters(projectId: number) {
  return request<Chapter[]>(`/api/projects/${projectId}/chapters`);
}

export function getChapter(chapterId: number) {
  return request<ChapterDetail>(`/api/chapters/${chapterId}`);
}

export function getProjectChapter(projectId: number, chapterId: number) {
  return request<ChapterDetail>(`/api/projects/${projectId}/chapters/${chapterId}`);
}

export function deleteProject(projectId: number) {
  return request<{ ok: boolean }>(`/api/projects/${projectId}/delete`, { method: 'POST' });
}

export function exportTxt(projectId: number) {
  return request<{ ok: boolean; format: 'txt'; output_path: string }>(`/api/projects/${projectId}/export/txt`, {
    method: 'POST',
  });
}

export function exportEpub(projectId: number) {
  return request<{ ok: boolean; format: 'epub'; output_path: string }>(`/api/projects/${projectId}/export/epub`, {
    method: 'POST',
  });
}

export function previewProject(sourcePath: string, workspacePath?: string) {
  return request<PreviewResponse>('/api/projects/preview', {
    method: 'POST',
    body: JSON.stringify({ source_path: sourcePath, workspace_path: workspacePath || null }),
  });
}

export function createProject(previewToken: string, projectName?: string, workspacePath?: string) {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({
      preview_token: previewToken,
      project_name: projectName || null,
      workspace_path: workspacePath || null,
    }),
  });
}

export function getModels() {
  return request<ModelConfig[]>('/api/models');
}

export function createModel(payload: ModelWrite) {
  return request<ModelConfig>('/api/models', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateModel(modelId: number, payload: ModelWrite) {
  return request<ModelConfig>(`/api/models/${modelId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteModel(modelId: number) {
  return request<{ ok: boolean }>(`/api/models/${modelId}/delete`, { method: 'POST' });
}

export function testModel(modelId: number) {
  return request<ModelTestResult>(`/api/models/${modelId}/test`, { method: 'POST' });
}

export function getPrompts() {
  return request<PromptTemplate[]>('/api/prompts');
}

export function createPrompt(payload: PromptTemplateWrite) {
  return request<PromptTemplate>('/api/prompts', { method: 'POST', body: JSON.stringify(payload) });
}

export function updatePrompt(templateId: number, payload: PromptTemplateWrite) {
  return request<PromptTemplate>(`/api/prompts/${templateId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deletePrompt(templateId: number) {
  return request<{ ok: boolean }>(`/api/prompts/${templateId}/delete`, { method: 'POST' });
}

export function updateProjectSettings(projectId: number, payload: ProjectSettingsWrite) {
  return request<ProjectDetail>(`/api/projects/${projectId}/settings`, { method: 'POST', body: JSON.stringify(payload) });
}

export function runProjectPipeline(projectId: number) {
  return request<PipelineRunResult>(`/api/projects/${projectId}/pipeline/run`, { method: 'POST' });
}

export function pauseProjectPipeline(projectId: number) {
  return request<{ ok: boolean }>(`/api/projects/${projectId}/pipeline/pause`, { method: 'POST' });
}

export function summarizeChapter(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/summarize`, { method: 'POST' });
}

export function detectScene(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/detect-scene`, { method: 'POST' });
}

export function rewriteChapter(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/rewrite`, { method: 'POST' });
}

export function retryChapterStage(chapterId: number, stage: 'summary' | 'scene_detection' | 'rewrite') {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/retry`, {
    method: 'POST',
    body: JSON.stringify({ stage }),
  });
}

export function saveChapterRewrite(chapterId: number, rewrittenText: string) {
  return request<import('./types').ChapterDetail>(`/api/chapters/${chapterId}/rewrite-text`, {
    method: 'POST',
    body: JSON.stringify({ rewritten_text: rewrittenText }),
  });
}
