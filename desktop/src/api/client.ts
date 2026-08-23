import type {
  AISplitProposal,
  Chapter,
  ChapterSplitOptions,
  ChapterWorkflowState,
  CreativeStrategy,
  DocumentCategory,
  DocumentLibrarySettings,
  LibraryDocument,
  LibraryDocumentAICleanupResult,
  LibraryDocumentChapter,
  LibraryDocumentCleanupResult,
  LibraryDocumentCreateChapterResult,
  LibraryDocumentDirectory,
  LibraryDocumentDraft,
  LibraryDocumentExportResult,
  LibraryDocumentImportResult,
  LibraryDocumentRevision,
  Material,
  MaterialAISettings,
  MaterialAITask,
  MaterialExtractionApplyResult,
  MaterialExtractionCandidate,
  ModelConfig,
  ModelTestResult,
  ModelWrite,
  PreviewResponse,
  Project,
  PromptSlot,
  PromptSlotKey,
} from './types';
import { trackAITask } from './aiTaskStatus';

function queryValue(name: string): string {
  return new URLSearchParams(window.location.search).get(name) ?? '';
}

function apiBase(): string {
  return queryValue('apiBase') || window.rustyDesktop?.backend?.apiBase || import.meta.env.VITE_RUSTY_API_URL || 'http://127.0.0.1:8765';
}

function apiToken(): string {
  return queryValue('apiToken') || window.rustyDesktop?.backend?.apiToken || import.meta.env.VITE_RUSTY_API_TOKEN || '';
}

export class ApiError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message); this.name = 'ApiError';
  }
}

let backendRecovery: Promise<boolean> | null = null;
async function recoverBackend(): Promise<boolean> {
  const restart = window.rustyDesktop?.restartBackend;
  if (!restart) return false;
  if (!backendRecovery) backendRecovery = restart().then((result) => result.ok).catch(() => false).finally(() => { backendRecovery = null; });
  return backendRecovery;
}

async function sendRequest(path: string, options: RequestInit, headers: Headers): Promise<Response> {
  const desktopRequest = window.rustyDesktop?.requestBackend;
  if (!desktopRequest) return fetch(`${apiBase()}${path}`, { ...options, headers });
  const result = await desktopRequest({ path, method: options.method || 'GET', headers: Object.fromEntries(headers.entries()), body: typeof options.body === 'string' ? options.body : null });
  return new Response(result.body, { status: result.status, statusText: result.statusText, headers: result.headers });
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers); headers.set('Accept', 'application/json');
  if (options.body) headers.set('Content-Type', 'application/json');
  const token = apiToken(); if (token) headers.set('X-Rusty-Token', token);
  let response: Response;
  try { response = await sendRequest(path, options, headers); }
  catch (error) {
    if (!(error instanceof TypeError) && !/ECONNREFUSED|ECONNRESET|EPIPE|socket hang up|ETIMEDOUT/i.test(String(error))) throw new ApiError(0, `请求未完成：${String(error)}`);
    if (!await recoverBackend()) throw new ApiError(0, `Rusty 后端已停止且自动重启失败：${String(error)}`);
    response = await sendRequest(path, options, headers);
  }
  const text = await response.text(); const data = text ? JSON.parse(text) : null;
  if (!response.ok) throw new ApiError(response.status, data?.message ?? response.statusText, data?.details);
  return data as T;
}

const body = (value: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(value) });
const put = (value: unknown): RequestInit => ({ method: 'PUT', body: JSON.stringify(value) });

export const getProjects = () => request<Project[]>('/api/projects');
export const getProject = (id: number) => request<Project>(`/api/projects/${id}`);
export const deleteProject = (id: number) => request<{ ok: boolean }>(`/api/projects/${id}/delete`, { method: 'POST' });
export const getChapters = (projectId: number) => request<Chapter[]>(`/api/projects/${projectId}/chapters`);
export const getChapter = (chapterId: number) => request<Chapter>(`/api/chapters/${chapterId}`);
export const getChapterWorkflow = (chapterId: number) => request<ChapterWorkflowState>(`/api/chapters/${chapterId}/workflow`);
export const runChapterSummary = (id: number) => trackAITask('生成内容总结', () => request<import('./types').ChapterSummary>(`/api/chapters/${id}/workflow/summary/run`, { method: 'POST' }));
export const saveChapterSummary = (id: number, value: import('./types').ChapterSummary) => request<import('./types').ChapterSummary>(`/api/chapters/${id}/workflow/summary`, put(value));
export const saveChapterDirection = (id: number, strategy: CreativeStrategy, userInstruction: string) => request<import('./types').ChapterCreativeIntent>(`/api/chapters/${id}/workflow/direction`, put({ strategy, user_instruction: userInstruction }));
export const runChapterSpecialAnalysis = (id: number) => trackAITask('生成专项分析', () => request<import('./types').ChapterSpecialAnalysis>(`/api/chapters/${id}/workflow/special-analysis/run`, body({})));
export const saveChapterSpecialAnalysis = (id: number, value: import('./types').ChapterSpecialAnalysis) => request<import('./types').ChapterSpecialAnalysis>(`/api/chapters/${id}/workflow/special-analysis`, put(value));
export const resolveChapterStyle = (id: number, value: { author_style_material_id?: number | null }) => trackAITask('确定写作风格', () => request<import('./types').ChapterStyleContext>(`/api/chapters/${id}/workflow/style/resolve`, body(value)));
export const generateChapterWriting = (id: number, replaceExisting = false) => trackAITask('生成章节草稿', () => request<import('./types').ChapterWriting>(`/api/chapters/${id}/workflow/writing/generate`, body({ replace_existing: replaceExisting })));
export const saveChapterWriting = (id: number, resultText: string) => request<import('./types').ChapterWriting>(`/api/chapters/${id}/workflow/writing`, put({ result_text: resultText }));
export const confirmChapterWorkflow = (id: number) => request<ChapterWorkflowState>(`/api/chapters/${id}/workflow/confirm`, { method: 'POST' });

export function previewProject(sourcePath: string, workspacePath = '', split?: ChapterSplitOptions) {
  return request<PreviewResponse>('/api/projects/preview', body({ source_path: sourcePath, workspace_path: workspacePath, split: split ?? { mode: 'auto' } }));
}
export function createProject(previewToken: string, projectName: string, workspacePath: string, modelId: number) {
  return request<Project>('/api/projects', body({ preview_token: previewToken, project_name: projectName, workspace_path: workspacePath, model_id: modelId }));
}

export const getModels = () => request<ModelConfig[]>('/api/models');
export const createModel = (value: ModelWrite) => request<ModelConfig>('/api/models', body(value));
export const updateModel = (id: number, value: ModelWrite) => request<ModelConfig>(`/api/models/${id}`, body(value));
export const deleteModel = (id: number) => request<{ ok: boolean }>(`/api/models/${id}/delete`, { method: 'POST' });
export const testModel = (id: number) => trackAITask('测试模型连接', () => request<ModelTestResult>(`/api/models/${id}/test`, { method: 'POST' }));

export const getPromptSlots = () => request<PromptSlot[]>('/api/prompt-slots');
export const updatePromptSlot = (key: PromptSlotKey, content: string) => request<PromptSlot>(`/api/prompt-slots/${key}`, put({ content }));

export function getMaterials(filters: { query?: string } = {}) {
  const params = new URLSearchParams();
  if (filters.query) params.set('query', filters.query);
  return request<Material[]>(`/api/materials${params.size ? `?${params}` : ''}`);
}
export const updateMaterial = (id: number, value: import('./types').MaterialUpdate) => request<Material>(`/api/materials/${id}`, body(value));
export const deleteMaterial = (id: number) => request<{ ok: boolean }>(`/api/materials/${id}/delete`, { method: 'POST' });
export const getMaterialAISettings = (task: MaterialAITask) => request<MaterialAISettings>(`/api/material-ai-settings/${task}`);
export const updateMaterialAISettings = (task: MaterialAITask, value: Omit<MaterialAISettings, 'task_type' | 'updated_at' | 'prompt_preview'>) => request<MaterialAISettings>(`/api/material-ai-settings/${task}`, body(value));
export const exportAuthorStyleSettings = () => request<Record<string, unknown>>('/api/author-style-settings/export');
export const importAuthorStyleSettings = (value: unknown) => request<MaterialAISettings>('/api/author-style-settings/import', body({ value }));
export const previewMaterialExtraction = (value: { name: string; source_path: string; model_id?: number | null }) => trackAITask('提取作者风格', () => request<import('./types').MaterialExtractionPreview>('/api/material-extractions/preview', body(value)));
export const applyMaterialExtraction = (value: { preview_token: string; candidates: MaterialExtractionCandidate[]; selected_candidate_ids: string[] }) => request<MaterialExtractionApplyResult>('/api/material-extractions/apply', body(value));

export const getLibraryDocuments = () => request<LibraryDocument[]>('/api/documents');
export const importLibraryDocument = (sourcePath: string) => request<LibraryDocumentImportResult>('/api/documents/import', body({ source_path: sourcePath }));
export const updateLibraryDocument = (id: number, title: string, author: string | null) => request<LibraryDocument>(`/api/documents/${id}`, body({ title, author }));
export const getDocumentLibrarySettings = () => request<DocumentLibrarySettings>('/api/document-library/settings');
export const migrateDocumentLibrary = (targetPath: string) => request<DocumentLibrarySettings>('/api/document-library/migrate', body({ target_path: targetPath }));
export const getDocumentCategories = () => request<DocumentCategory[]>('/api/document-categories');
export const createDocumentCategory = (name: string) => request<DocumentCategory>('/api/document-categories', body({ name }));
export const renameDocumentCategory = (id: number, name: string) => request<DocumentCategory>(`/api/document-categories/${id}`, body({ name }));
export const deleteDocumentCategory = (id: number) => request<{ ok: boolean }>(`/api/document-categories/${id}/delete`, { method: 'POST' });
export const getLibraryDocumentRevisions = (id: number) => request<LibraryDocumentRevision[]>(`/api/documents/${id}/revisions`);
export const getLibraryDocumentDirectory = (id: number) => request<LibraryDocumentDirectory>(`/api/documents/${id}/directory`);
export const getLibraryDocumentContent = (id: number, chapterId?: number | null) => request<import('./types').LibraryDocumentContent>(`/api/documents/${id}/content${chapterId == null ? '' : `?chapter_id=${chapterId}`}`);
export const getLibraryDocumentDraft = (id: number, chapterId?: number | null) => request<LibraryDocumentDraft | null>(`/api/documents/${id}/draft${chapterId == null ? '' : `?chapter_id=${chapterId}`}`);
export const saveLibraryDocumentDraft = (id: number, baseRevisionId: number, title: string, text: string, chapterId?: number | null) => request<LibraryDocumentDraft>(`/api/documents/${id}/draft`, put({ base_revision_id: baseRevisionId, title, text, chapter_id: chapterId ?? null }));
export const commitLibraryDocumentDraft = (id: number, chapterId?: number | null) => request<LibraryDocumentCleanupResult>(`/api/documents/${id}/draft/commit`, body({ chapter_id: chapterId ?? null }));
export const mergeLibraryDocuments = (ids: number[], title: string, author?: string | null) => request<LibraryDocument>('/api/documents/merge', body({ document_ids: ids, title, author: author ?? null }));
export const createLibraryDocumentChapter = (id: number, title: string, text: string, position: 'before' | 'after', anchorChapterId?: number | null) => request<LibraryDocumentCreateChapterResult>(`/api/documents/${id}/chapters`, body({ title, text, position, anchor_chapter_id: anchorChapterId ?? null }));
export const deleteLibraryDocumentChapter = (id: number, chapterId: number) => request<LibraryDocumentCleanupResult>(`/api/documents/${id}/chapters/${chapterId}`, { method: 'DELETE' });
export const splitLibraryDocumentChapterAtCursor = (id: number, chapterId: number, cursorOffset: number, nextTitle: string) => request<LibraryDocumentCreateChapterResult>(`/api/documents/${id}/split/cursor`, body({ chapter_id: chapterId, cursor_offset: cursorOffset, next_title: nextTitle }));
export const reorderLibraryDocumentChapters = (id: number, orderedChapterIds: number[], volumeAssignments: Record<number, number | null> = {}) => request<LibraryDocumentChapter[]>(`/api/documents/${id}/chapters/reorder`, body({ ordered_chapter_ids: orderedChapterIds, volume_assignments: volumeAssignments }));
export const createLibraryDocumentVolume = (id: number, chapterId: number, title: string) => request<LibraryDocumentCleanupResult>(`/api/documents/${id}/volumes`, body({ chapter_id: chapterId, title }));
export const renameLibraryDocumentVolume = (id: number, volumeId: number, title: string) => request<LibraryDocumentCleanupResult>(`/api/documents/${id}/volumes/${volumeId}`, body({ title }));
export const deleteLibraryDocument = (id: number) => request<{ ok: boolean }>(`/api/documents/${id}/delete`, { method: 'POST' });
export const cleanupLibraryDocumentWithAI = (id: number, chapterIds: number[], prompt: string, modelId?: number | null) => trackAITask('AI 整理文档', () => request<LibraryDocumentAICleanupResult>(`/api/documents/${id}/cleanup/ai`, body({ chapter_ids: chapterIds, prompt, model_id: modelId ?? null })));
export const activateLibraryDocumentRevision = (id: number, revisionId: number) => request<LibraryDocument>(`/api/documents/${id}/revisions/${revisionId}/activate`, { method: 'POST' });
export const exportLibraryDocument = (id: number, format: 'txt' | 'epub', outputPath: string) => request<LibraryDocumentExportResult>(`/api/documents/${id}/export`, body({ format, output_path: outputPath }));
export const previewAIDocumentSplit = (id: number, chapterId: number, prompt: string, modelId?: number | null) => trackAITask('AI 拆分文档', () => request<AISplitProposal>(`/api/documents/${id}/split/ai/preview`, body({ chapter_id: chapterId, prompt, model_id: modelId ?? null })));
export const applyAIDocumentSplit = (id: number, proposalId: number, chapters: AISplitProposal['chapters']) => request<{ document_id: number; revision_id: number; chapters: LibraryDocumentChapter[] }>(`/api/documents/${id}/split/ai/apply`, body({ proposal_id: proposalId, chapters }));
