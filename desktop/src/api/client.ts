import type {
  Chapter,
  ChapterDetail,
  ModelConfig,
  PreviewResponse,
  Project,
  ProjectDetail,
  PromptTemplate,
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

export function getPrompts() {
  return request<PromptTemplate[]>('/api/prompts');
}
