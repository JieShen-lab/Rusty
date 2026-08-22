import type {
  AnalysisPromptTemplate,
  AuthorStyleDimensionPreview,
  AnalysisPromptTemplateWrite,
  Chapter,
  ChapterSplitOptions,
  ChapterDetail,
  ChapterWorkflowState,
  CreativeStrategy,
  CompiledPromptPreview,
  ExportPlanItem,
  ExportPlanUpdate,
  GenerationAttempt,
  ModelConfig,
  ModelTestResult,
  Material,
  MaterialAISettings,
  MaterialAITask,
  MaterialCategory,
  MaterialExtractionApplyResult,
  MaterialExtractionCandidate,
  MaterialExtractionPreview,
  MaterialScope,
  MaterialType,
  MaterialUpdate,
  MaterialWrite,
  SplitPreview,
  ModelWrite,
  LibraryDocument,
  LibraryDocumentCleanupResult,
  LibraryDocumentChapter,
  LibraryDocumentCreateChapterResult,
  LibraryDocumentContent,
  LibraryDocumentDirectory,
  LibraryDocumentDraft,
  LibraryDocumentExportResult,
  LibraryDocumentImportResult,
  LibraryDocumentRevision,
  LegacyAnalysisExport,
  LegacyProjectCreateRequest,
  DocumentProcessingSettings,
  DocumentProcessingTemplate,
  DocumentLibrarySettings,
  PreviewResponse,
  Project,
  ProjectDetail,
  ProjectMaterialFilter,
  ProjectKind,
  ProjectSettingsWrite,
  PromptTemplate,
  PromptTemplateWrite,
  PromptDefinition,
  PromptDefinitionWrite,
  ProjectMasterPrompt,
  PipelineRunResult,
  StructuredSkeleton,
  StyleAnalysis,
} from './types';

function queryValue(name: string): string {
  return new URLSearchParams(window.location.search).get(name) ?? '';
}

function apiBase(): string {
  return (
    queryValue('apiBase') ||
    window.rustyDesktop?.backend?.apiBase ||
    import.meta.env.VITE_RUSTY_API_URL ||
    'http://127.0.0.1:8765'
  );
}

function apiToken(): string {
  return queryValue('apiToken') || window.rustyDesktop?.backend?.apiToken || import.meta.env.VITE_RUSTY_API_TOKEN || '';
}

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

let backendRecovery: Promise<boolean> | null = null;

async function recoverBackend(): Promise<boolean> {
  const restart = window.rustyDesktop?.restartBackend;
  if (!restart) return false;
  if (!backendRecovery) {
    backendRecovery = restart()
      .then((result) => result.ok)
      .catch(() => false)
      .finally(() => {
        backendRecovery = null;
      });
  }
  return backendRecovery;
}

async function sendRequest(path: string, options: RequestInit, headers: Headers): Promise<Response> {
  const desktopRequest = window.rustyDesktop?.requestBackend;
  if (!desktopRequest) {
    return fetch(`${apiBase()}${path}`, { ...options, headers });
  }
  const body = typeof options.body === 'string' ? options.body : null;
  const result = await desktopRequest({
    path,
    method: options.method || 'GET',
    headers: Object.fromEntries(headers.entries()),
    body,
  });
  return new Response(result.body, {
    status: result.status,
    statusText: result.statusText,
    headers: result.headers,
  });
}

function shouldRecoverBackend(error: unknown): boolean {
  if (!window.rustyDesktop?.requestBackend) {
    return error instanceof TypeError;
  }
  return /ECONNREFUSED|ECONNRESET|EPIPE|socket hang up|connect\s+ETIMEDOUT/i.test(String(error));
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  headers.set('Accept', 'application/json');
  if (options.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }
  const token = apiToken();
  if (token) {
    headers.set('X-Rusty-Token', token);
  }

  let response: Response | null = null;
  try {
    response = await sendRequest(path, options, headers);
  } catch (error) {
    if (!shouldRecoverBackend(error)) {
      throw new ApiError(0, `请求未完成：${String(error)}`);
    }
    const recovered = await recoverBackend();
    if (!recovered) {
      throw new ApiError(0, `Rusty 后端已停止且自动重启失败：${String(error)}`);
    }
    let retryError: unknown = error;
    for (let attempt = 0; attempt < 3; attempt += 1) {
      try {
        response = await sendRequest(path, options, headers);
        retryError = null;
        break;
      } catch (reason) {
        retryError = reason;
        await new Promise((resolve) => window.setTimeout(resolve, 200 * (attempt + 1)));
      }
    }
    if (retryError) {
      throw new ApiError(0, `Rusty 后端重启后仍无法连接：${String(retryError)}`);
    }
  }

  if (!response) {
    throw new ApiError(0, 'Rusty 后端未返回响应。');
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

export function getLibraryDocuments() {
  return request<LibraryDocument[]>('/api/documents');
}

export function importLibraryDocument(sourcePath: string) {
  return request<LibraryDocumentImportResult>('/api/documents/import', {
    method: 'POST',
    body: JSON.stringify({ source_path: sourcePath }),
  });
}

export function updateLibraryDocument(documentId: number, title: string, author: string | null) {
  return request<LibraryDocument>(`/api/documents/${documentId}`, {
    method: 'POST',
    body: JSON.stringify({ title, author }),
  });
}

export function getDocumentLibrarySettings() {
  return request<DocumentLibrarySettings>('/api/document-library/settings');
}

export function migrateDocumentLibrary(targetPath: string) {
  return request<DocumentLibrarySettings>('/api/document-library/migrate', {
    method: 'POST',
    body: JSON.stringify({ target_path: targetPath }),
  });
}

export function getDocumentCategories() {
  return request<import('./types').DocumentCategory[]>('/api/document-categories');
}

export function createDocumentCategory(name: string) {
  return request<import('./types').DocumentCategory>('/api/document-categories', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function renameDocumentCategory(categoryId: number, name: string) {
  return request<import('./types').DocumentCategory>(`/api/document-categories/${categoryId}`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteDocumentCategory(categoryId: number) {
  return request<{ ok: boolean }>(`/api/document-categories/${categoryId}/delete`, {
    method: 'POST',
  });
}

export function assignDocumentCategory(documentId: number, categoryId: number, selected: boolean) {
  return request<LibraryDocument>(`/api/documents/${documentId}/categories/${categoryId}`, {
    method: 'POST',
    body: JSON.stringify({ selected }),
  });
}

export function getDocumentProcessingTemplates() {
  return request<DocumentProcessingTemplate[]>('/api/document-processing-templates');
}

export function createDocumentProcessingTemplate(name: string, settings: DocumentProcessingSettings) {
  return request<DocumentProcessingTemplate>('/api/document-processing-templates', {
    method: 'POST',
    body: JSON.stringify({ name, settings }),
  });
}

export function getLibraryDocumentRevisions(documentId: number) {
  return request<LibraryDocumentRevision[]>(`/api/documents/${documentId}/revisions`);
}

export function getLibraryDocumentChapters(documentId: number) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/chapters`);
}

export function getLibraryDocumentDirectory(documentId: number) {
  return request<LibraryDocumentDirectory>(`/api/documents/${documentId}/directory`);
}

export function getLibraryDocumentContent(documentId: number, chapterId?: number | null) {
  const query = chapterId == null ? '' : `?chapter_id=${chapterId}`;
  return request<LibraryDocumentContent>(`/api/documents/${documentId}/content${query}`);
}

export function getLibraryDocumentDraft(documentId: number, chapterId?: number | null) {
  const query = chapterId == null ? '' : `?chapter_id=${chapterId}`;
  return request<LibraryDocumentDraft | null>(`/api/documents/${documentId}/draft${query}`);
}

export function saveLibraryDocumentDraft(
  documentId: number,
  baseRevisionId: number,
  title: string,
  text: string,
  chapterId?: number | null,
) {
  return request<LibraryDocumentDraft>(`/api/documents/${documentId}/draft`, {
    method: 'PUT',
    body: JSON.stringify({
      base_revision_id: baseRevisionId,
      title,
      text,
      chapter_id: chapterId ?? null,
    }),
  });
}

export function commitLibraryDocumentDraft(documentId: number, chapterId?: number | null) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/draft/commit`, {
    method: 'POST',
    body: JSON.stringify({ chapter_id: chapterId ?? null }),
  });
}

export function discardLibraryDocumentDraft(documentId: number, chapterId?: number | null) {
  return request<{ ok: boolean }>(`/api/documents/${documentId}/draft/discard`, {
    method: 'POST',
    body: JSON.stringify({ chapter_id: chapterId ?? null }),
  });
}

export function saveLibraryDocumentContent(documentId: number, text: string, title?: string | null, chapterId?: number | null) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/content`, {
    method: 'POST',
    body: JSON.stringify({ text, title: title ?? null, chapter_id: chapterId ?? null }),
  });
}

export function mergeLibraryDocuments(documentIds: number[], title: string, author?: string | null) {
  return request<LibraryDocument>('/api/documents/merge', {
    method: 'POST',
    body: JSON.stringify({ document_ids: documentIds, title, author: author ?? null }),
  });
}

export function createLibraryDocumentChapter(
  documentId: number,
  title: string,
  text: string,
  position: 'before' | 'after',
  anchorChapterId?: number | null,
) {
  return request<LibraryDocumentCreateChapterResult>(`/api/documents/${documentId}/chapters`, {
    method: 'POST',
    body: JSON.stringify({ title, text, position, anchor_chapter_id: anchorChapterId ?? null }),
  });
}

export function deleteLibraryDocumentChapter(documentId: number, chapterId: number) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/chapters/${chapterId}`, {
    method: 'DELETE',
  });
}

export function splitLibraryDocumentChapterAtCursor(
  documentId: number,
  chapterId: number,
  cursorOffset: number,
  nextTitle: string,
) {
  return request<LibraryDocumentCreateChapterResult>(`/api/documents/${documentId}/split/cursor`, {
    method: 'POST',
    body: JSON.stringify({ chapter_id: chapterId, cursor_offset: cursorOffset, next_title: nextTitle }),
  });
}

export function previewRegexSplit(documentId: number, pattern: string) {
  return request<SplitPreview>(`/api/documents/${documentId}/split/regex/preview`, {
    method: 'POST',
    body: JSON.stringify({ pattern }),
  });
}

export function applyRegexSplit(
  documentId: number,
  pattern: string,
  previewToken: string,
  chapters?: SplitPreview['chapters'],
) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/split/regex/apply`, {
    method: 'POST',
    body: JSON.stringify({ pattern, preview_token: previewToken, chapters: chapters ?? null }),
  });
}

export function markLibraryDocumentChapter(
  documentId: number,
  revisionId: number,
  title: string,
  startOffset: number,
  endOffset: number,
) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/chapters/mark`, {
    method: 'POST',
    body: JSON.stringify({ revision_id: revisionId, title, start_offset: startOffset, end_offset: endOffset }),
  });
}

export function reorderLibraryDocumentChapters(
  documentId: number,
  orderedChapterIds: number[],
  volumeAssignments: Record<number, number | null> = {},
) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/chapters/reorder`, {
    method: 'POST',
    body: JSON.stringify({
      ordered_chapter_ids: orderedChapterIds,
      volume_assignments: volumeAssignments,
    }),
  });
}

export function renameLibraryDocumentVolume(documentId: number, volumeId: number, title: string) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/volumes/${volumeId}`, {
    method: 'POST',
    body: JSON.stringify({ title }),
  });
}

export function createLibraryDocumentVolume(documentId: number, chapterId: number, title: string) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/volumes`, {
    method: 'POST',
    body: JSON.stringify({ chapter_id: chapterId, title }),
  });
}

export function deleteLibraryDocument(documentId: number) {
  return request<{ ok: boolean }>(`/api/documents/${documentId}/delete`, { method: 'POST' });
}

export function cleanupLibraryDocument(documentId: number, templateId: number) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/cleanup`, {
    method: 'POST',
    body: JSON.stringify({ template_id: templateId }),
  });
}

export function cleanupLibraryDocumentWithAI(
  documentId: number,
  chapterIds: number[],
  prompt: string,
  modelId?: number | null,
) {
  return request<import('./types').LibraryDocumentAICleanupResult>(`/api/documents/${documentId}/cleanup/ai`, {
    method: 'POST',
    body: JSON.stringify({ chapter_ids: chapterIds, prompt, model_id: modelId ?? null }),
  });
}

export function activateLibraryDocumentRevision(documentId: number, revisionId: number) {
  return request<LibraryDocument>(`/api/documents/${documentId}/revisions/${revisionId}/activate`, {
    method: 'POST',
  });
}

export function exportLibraryDocument(documentId: number, format: 'txt' | 'epub', outputPath: string) {
  return request<LibraryDocumentExportResult>(`/api/documents/${documentId}/export`, {
    method: 'POST',
    body: JSON.stringify({ format, output_path: outputPath }),
  });
}

export function getProject(projectId: number) {
  return request<ProjectDetail>(`/api/projects/${projectId}`);
}

export function getLegacyAnalysisExport(projectId: number) {
  return request<LegacyAnalysisExport>(
    `/api/projects/${projectId}/legacy-analysis/export`,
  );
}

export function createProjectFromLegacy(
  projectId: number,
  payload: LegacyProjectCreateRequest,
) {
  return request<Project>(
    `/api/projects/${projectId}/legacy-analysis/create-project`,
    { method: 'POST', body: JSON.stringify(payload) },
  );
}

export function getChapters(projectId: number) {
  return request<Chapter[]>(`/api/projects/${projectId}/chapters`);
}

export function getCreativeWorkflowStates(projectId: number) {
  return request<ChapterWorkflowState[]>(`/api/projects/${projectId}/creative-workflow`);
}

export function getChapterWorkflow(chapterId: number) {
  return request<ChapterWorkflowState>(`/api/chapters/${chapterId}/workflow`);
}

export function runChapterSummary(chapterId: number) {
  return request<import('./types').ChapterSummary>(`/api/chapters/${chapterId}/workflow/summary/run`, { method: 'POST' });
}

export function saveChapterSummary(chapterId: number, value: import('./types').ChapterSummary) {
  return request<import('./types').ChapterSummary>(`/api/chapters/${chapterId}/workflow/summary`, {
    method: 'PUT', body: JSON.stringify(value),
  });
}

export function saveChapterDirection(chapterId: number, strategy: CreativeStrategy, userInstruction: string) {
  return request<import('./types').ChapterCreativeIntent>(`/api/chapters/${chapterId}/workflow/direction`, {
    method: 'PUT', body: JSON.stringify({ strategy, user_instruction: userInstruction }),
  });
}

export function runChapterSpecialAnalysis(chapterId: number) {
  return request<import('./types').ChapterSpecialAnalysis>(`/api/chapters/${chapterId}/workflow/special-analysis/run`, {
    method: 'POST', body: JSON.stringify({}),
  });
}

export function saveChapterSpecialAnalysis(chapterId: number, value: import('./types').ChapterSpecialAnalysis) {
  return request<import('./types').ChapterSpecialAnalysis>(`/api/chapters/${chapterId}/workflow/special-analysis`, {
    method: 'PUT', body: JSON.stringify(value),
  });
}

export function resolveChapterStyle(chapterId: number, value: { source_scope?: 'document' | 'chapter'; author_style_material_id?: number | null }) {
  return request<import('./types').ChapterStyleContext>(`/api/chapters/${chapterId}/workflow/style/resolve`, {
    method: 'POST', body: JSON.stringify(value),
  });
}

export function generateChapterWriting(chapterId: number, replaceExisting = false) {
  return request<import('./types').ChapterWriting>(`/api/chapters/${chapterId}/workflow/writing/generate`, {
    method: 'POST', body: JSON.stringify({ replace_existing: replaceExisting }),
  });
}

export function saveChapterWriting(chapterId: number, resultText: string) {
  return request<import('./types').ChapterWriting>(`/api/chapters/${chapterId}/workflow/writing`, {
    method: 'PUT', body: JSON.stringify({ result_text: resultText }),
  });
}

export function confirmChapterWorkflow(chapterId: number) {
  return request<ChapterWorkflowState>(`/api/chapters/${chapterId}/workflow/confirm`, { method: 'POST' });
}

export function getChapter(chapterId: number) {
  return request<ChapterDetail>(`/api/chapters/${chapterId}`);
}

export function getProjectChapter(projectId: number, chapterId: number) {
  return request<ChapterDetail>(`/api/projects/${projectId}/chapters/${chapterId}`);
}

export function getProjectExportPlan(projectId: number) {
  return request<ExportPlanItem[]>(`/api/projects/${projectId}/export-plan`);
}

export function saveProjectExportPlan(projectId: number, payload: ExportPlanUpdate) {
  return request<ExportPlanItem[]>(`/api/projects/${projectId}/export-plan`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
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

export function previewProject(sourcePath: string, workspacePath?: string, split?: ChapterSplitOptions) {
  return request<PreviewResponse>('/api/projects/preview', {
    method: 'POST',
    body: JSON.stringify({ source_path: sourcePath, workspace_path: workspacePath || null, split: split ?? null }),
  });
}

export function createProject(
  previewToken: string,
  projectName?: string,
  workspacePath?: string,
  projectKind: ProjectKind = 'rewrite',
  promptTemplateId?: number | null,
  analysisPromptTemplateId?: number | null,
  modelId?: number | null,
  masterPromptDefinitionId?: number | null,
) {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({
      preview_token: previewToken,
      project_name: projectName || null,
      workspace_path: workspacePath || null,
      project_kind: projectKind,
      model_id: modelId ?? null,
      prompt_template_id: promptTemplateId ?? null,
      analysis_prompt_template_id: analysisPromptTemplateId ?? null,
      master_prompt_definition_id: masterPromptDefinitionId ?? null,
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

export function importPromptPackage(content: string) {
  return request<PromptTemplate>('/api/prompts/import', { method: 'POST', body: JSON.stringify({ content }) });
}

export function exportPromptPackage(templateId: number) {
  return request<{ content: string }>(`/api/prompts/${templateId}/export`, { method: 'POST' });
}

export function getAnalysisPrompts() {
  return request<AnalysisPromptTemplate[]>('/api/analysis-prompts');
}

export function createAnalysisPrompt(payload: AnalysisPromptTemplateWrite) {
  return request<AnalysisPromptTemplate>('/api/analysis-prompts', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateAnalysisPrompt(templateId: number, payload: AnalysisPromptTemplateWrite) {
  return request<AnalysisPromptTemplate>(`/api/analysis-prompts/${templateId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteAnalysisPrompt(templateId: number) {
  return request<{ ok: boolean }>(`/api/analysis-prompts/${templateId}/delete`, { method: 'POST' });
}

export function extractProjectPromptPackage(projectId: number, modelId?: number | null) {
  return request<PromptTemplate>(`/api/projects/${projectId}/prompt-package/extract`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  });
}

export function getMaterials(filters: {
  scope?: MaterialScope;
  project_id?: number;
  material_type?: MaterialType;
  category_id?: number;
  analysis_status?: 'unanalyzed' | 'analyzed';
  pending_imports?: boolean;
  query?: string;
  limit?: number;
  offset?: number;
} = {}) {
  const params = new URLSearchParams();
  if (filters.scope) params.set('scope', filters.scope);
  if (filters.project_id !== undefined) params.set('project_id', String(filters.project_id));
  if (filters.material_type) params.set('material_type', filters.material_type);
  if (filters.category_id !== undefined) params.set('category_id', String(filters.category_id));
  if (filters.analysis_status) params.set('analysis_status', filters.analysis_status);
  if (filters.pending_imports) params.set('pending_imports', 'true');
  if (filters.query) params.set('query', filters.query);
  if (filters.limit !== undefined) params.set('limit', String(filters.limit));
  if (filters.offset !== undefined) params.set('offset', String(filters.offset));
  const query = params.size ? `?${params.toString()}` : '';
  return request<Material[]>(`/api/materials${query}`);
}

export function createMaterial(payload: MaterialWrite) {
  return request<Material>('/api/materials', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateMaterial(materialId: number, payload: MaterialUpdate) {
  return request<Material>(`/api/materials/${materialId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteMaterial(materialId: number) {
  return request<{ ok: boolean }>(`/api/materials/${materialId}/delete`, { method: 'POST' });
}

export function getMaterialCategories(materialType?: MaterialType) {
  const query = materialType ? `?material_type=${materialType}` : '';
  return request<MaterialCategory[]>(`/api/material-categories${query}`);
}

export function createMaterialCategory(materialType: MaterialType, name: string) {
  return request<MaterialCategory>('/api/material-categories', {
    method: 'POST',
    body: JSON.stringify({ material_type: materialType, name }),
  });
}

export function renameMaterialCategory(categoryId: number, name: string) {
  return request<MaterialCategory>(`/api/material-categories/${categoryId}`, {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function deleteMaterialCategory(categoryId: number) {
  return request<{ ok: boolean }>(`/api/material-categories/${categoryId}/delete`, { method: 'POST' });
}

export function assignMaterialCategory(materialId: number, categoryId: number, selected: boolean) {
  return request<Material>(`/api/materials/${materialId}/categories/${categoryId}`, {
    method: 'POST',
    body: JSON.stringify({ selected }),
  });
}

export function getProjectMaterialFilters(projectId: number) {
  return request<ProjectMaterialFilter[]>(`/api/projects/${projectId}/material-filters`);
}

export function getProjectMaterials(projectId: number, materialType?: MaterialType) {
  const query = materialType ? `?material_type=${materialType}` : '';
  return request<Material[]>(`/api/projects/${projectId}/materials${query}`);
}

export function setProjectMaterialFilter(
  projectId: number,
  materialType: MaterialType,
  payload: Omit<ProjectMaterialFilter, 'project_id' | 'material_type'>,
) {
  return request<ProjectMaterialFilter>(`/api/projects/${projectId}/material-filters/${materialType}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getMaterialAISettings(taskType?: MaterialAITask) {
  return taskType
    ? request<MaterialAISettings>(`/api/material-ai-settings/${taskType}`)
    : request<MaterialAISettings[]>('/api/material-ai-settings');
}

export function updateMaterialAISettings(
  taskType: MaterialAITask,
  payload: Omit<MaterialAISettings, 'task_type' | 'updated_at' | 'prompt_preview'>,
) {
  return request<MaterialAISettings>(`/api/material-ai-settings/${taskType}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function exportAuthorStyleSettings() {
  return request<Record<string, unknown>>('/api/author-style-settings/export');
}

export function importAuthorStyleSettings(value: unknown) {
  return request<MaterialAISettings>('/api/author-style-settings/import', {
    method: 'POST',
    body: JSON.stringify({ value }),
  });
}

export function previewAuthorStyleDimension(materialId: number, payload: {
  dimension_id: string;
  dimension_name: string;
  dimension_requirement: string;
  model_id?: number | null;
}) {
  return request<AuthorStyleDimensionPreview>(`/api/materials/${materialId}/author-style/dimensions/preview`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function applyAuthorStyleDimension(materialId: number, previewToken: string) {
  return request<Material>(`/api/materials/${materialId}/author-style/dimensions/apply`, {
    method: 'POST',
    body: JSON.stringify({ preview_token: previewToken }),
  });
}

export function previewMaterialExtraction(payload: {
  task_type: MaterialAITask;
  name?: string | null;
  sample_text?: string | null;
  source_path?: string | null;
  source_project_id?: number | null;
  source_document_id?: number | null;
  model_id?: number | null;
  source_metadata?: Record<string, unknown>;
}) {
  return request<MaterialExtractionPreview>('/api/material-extractions/preview', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function applyMaterialExtraction(payload: {
  preview_token: string;
  candidates: MaterialExtractionCandidate[];
  selected_candidate_ids: string[];
}) {
  return request<MaterialExtractionApplyResult>('/api/material-extractions/apply', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateProjectSettings(projectId: number, payload: ProjectSettingsWrite) {
  return request<ProjectDetail>(`/api/projects/${projectId}/settings`, { method: 'POST', body: JSON.stringify(payload) });
}

export function runProjectPipeline(projectId: number) {
  return request<PipelineRunResult>(`/api/projects/${projectId}/pipeline/run`, { method: 'POST' });
}

export function runProjectSummary(projectId: number) {
  return request<PipelineRunResult>(`/api/projects/${projectId}/pipeline/summarize`, { method: 'POST' });
}

export function pauseProjectPipeline(projectId: number) {
  return request<{ ok: boolean }>(`/api/projects/${projectId}/pipeline/pause`, { method: 'POST' });
}

export function summarizeChapter(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/summarize`, { method: 'POST' });
}

export function analyzeChapterStyle(chapterId: number, modelId?: number | null) {
  return request<StyleAnalysis>(`/api/chapters/${chapterId}/style-analysis`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  });
}

export function reviewChapterStyle(chapterId: number, reviewed: Record<string, unknown>) {
  return request<StyleAnalysis>(`/api/chapters/${chapterId}/style-analysis/review`, {
    method: 'POST',
    body: JSON.stringify({ reviewed }),
  });
}

export function synthesizeProjectStyle(projectId: number, modelId?: number | null) {
  return request<PromptTemplate>(`/api/projects/${projectId}/style-analysis/synthesize`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  });
}

export function getProjectStyleSynthesis(projectId: number) {
  return request<{ prompt_template_id?: number | null }>(`/api/projects/${projectId}/style-analysis/synthesis`);
}

export function detectScene(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/detect-scene`, { method: 'POST' });
}

export function rewriteChapter(chapterId: number) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/rewrite`, { method: 'POST' });
}

export function getChapterPromptPreview(
  chapterId: number,
  stage: 'summary' | 'scene_detection' | 'plot_expansion' | 'rewrite' = 'rewrite',
) {
  return request<CompiledPromptPreview>(`/api/chapters/${chapterId}/prompt-preview?stage=${stage}`);
}

export function getChapterGenerationAttempts(chapterId: number, stage?: string) {
  const query = stage ? `?stage=${encodeURIComponent(stage)}` : '';
  return request<GenerationAttempt[]>(`/api/chapters/${chapterId}/generation-attempts${query}`);
}

export function expandChapterPlot(chapterId: number, enabled: boolean) {
  return request<{ ok: boolean; text: string }>(`/api/chapters/${chapterId}/expand-plot`, {
    method: 'POST',
    body: JSON.stringify({ enabled }),
  });
}

export function saveTargetSkeleton(chapterId: number, text: string, enabled = true) {
  return request<import('./types').ChapterDetail>(`/api/chapters/${chapterId}/target-skeleton`, {
    method: 'POST',
    body: JSON.stringify({ text, enabled }),
  });
}

export function retryChapterStage(chapterId: number, stage: 'summary' | 'scene_detection' | 'plot_expansion' | 'rewrite') {
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

export function confirmChapterRewrite(chapterId: number) {
  return request<import('./types').ChapterDetail>(`/api/chapters/${chapterId}/confirm-rewrite`, { method: 'POST' });
}

export function getChapterScenes(chapterId: number) {
  return request<import('./types').SceneRecord[]>(`/api/chapters/${chapterId}/scenes`);
}

export function getPromptDefinitions() {
  return request<PromptDefinition[]>('/api/prompt-definitions');
}

export function createPromptDefinition(value: PromptDefinitionWrite) {
  return request<PromptDefinition>('/api/prompt-definitions', { method: 'POST', body: JSON.stringify(value) });
}

export function updatePromptDefinition(id: number, value: PromptDefinitionWrite) {
  return request<PromptDefinition>(`/api/prompt-definitions/${id}`, { method: 'PUT', body: JSON.stringify(value) });
}

export function copyPromptDefinition(id: number) {
  return request<PromptDefinition>(`/api/prompt-definitions/${id}/copy`, { method: 'POST' });
}

export function deletePromptDefinition(id: number) {
  return request<{ ok: boolean }>(`/api/prompt-definitions/${id}/delete`, { method: 'POST' });
}

export function exportPromptDefinition(id: number) {
  return request<{ content: string }>(`/api/prompt-definitions/${id}/export`, { method: 'POST' });
}

export function importPromptDefinition(content: string) {
  return request<PromptDefinition>('/api/prompt-definitions/import', { method: 'POST', body: JSON.stringify({ content }) });
}

export function getProjectMasterPrompt(projectId: number) {
  return request<ProjectMasterPrompt>(`/api/projects/${projectId}/master-prompt`);
}

export function saveProjectMasterPrompt(projectId: number, content: string) {
  return request<ProjectMasterPrompt>(`/api/projects/${projectId}/master-prompt`, { method: 'PUT', body: JSON.stringify({ content }) });
}

export function exportProjectMasterPrompt(projectId: number, name: string, description = '') {
  return request<PromptDefinition>(`/api/projects/${projectId}/master-prompt/export`, { method: 'POST', body: JSON.stringify({ name, description }) });
}

export function analyzeChapterScenes(
  chapterId: number,
  payload: {
    boundaries?: import('./types').SceneBoundaryItem[] | null;
    source?: 'ai' | 'heuristic' | 'user';
    confirm?: boolean;
    model_id?: number | null;
  },
) {
  return request<import('./types').SceneRecord[]>(`/api/chapters/${chapterId}/scenes/analyze`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function adjustChapterScenes(chapterId: number, boundaries: import('./types').SceneBoundaryItem[]) {
  return request<import('./types').SceneRecord[]>(`/api/chapters/${chapterId}/scenes/adjust`, {
    method: 'POST',
    body: JSON.stringify({ boundaries, source: 'user', confirm: true }),
  });
}

export function confirmChapterScenes(chapterId: number) {
  return request<import('./types').SceneRecord[]>(`/api/chapters/${chapterId}/scenes/confirm`, { method: 'POST' });
}

export function getSceneFacts(sceneId: number) {
  return request<import('./types').SceneFactLedger>(`/api/scenes/${sceneId}/facts`);
}

export function saveSceneFacts(sceneId: number, facts: Record<string, unknown>, sourceKind = 'user') {
  return request<import('./types').SceneFactLedger>(`/api/scenes/${sceneId}/facts`, {
    method: 'POST',
    body: JSON.stringify({ facts, source_kind: sourceKind }),
  });
}

export function getSceneCharacterStates(sceneId: number) {
  return request<import('./types').CharacterStoryState[]>(`/api/scenes/${sceneId}/character-states`);
}

export function saveSceneCharacterState(
  sceneId: number,
  payload: { character_name: string; state: Record<string, unknown> },
) {
  return request<import('./types').CharacterStoryState>(`/api/scenes/${sceneId}/character-states`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createStorySkeleton(payload: {
  project_id: number;
  chapter_id: number;
  scene_id?: number | null;
  scope?: string;
  source_kind?: string;
  nodes?: Record<string, unknown>[];
  structured_skeleton?: StructuredSkeleton;
}) {
  return request<import('./types').StorySkeletonVersion>('/api/story-skeletons', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function reviseStorySkeleton(
  skeletonId: number,
  nodes: Record<string, unknown>[] | undefined,
  changeNote = '',
  structuredSkeleton?: StructuredSkeleton,
) {
  return request<import('./types').StorySkeletonVersion>(`/api/story-skeletons/${skeletonId}/versions`, {
    method: 'POST',
    body: JSON.stringify({ nodes: nodes ?? [], structured_skeleton: structuredSkeleton ?? null, change_note: changeNote }),
  });
}

export function getChapterStorySkeleton(chapterId: number) {
  return request<import('./types').PreferredStorySkeleton>(`/api/chapters/${chapterId}/story-skeleton`);
}

export function getStorySkeletonVersion(skeletonId: number, version: number) {
  return request<import('./types').StorySkeletonVersion>(`/api/story-skeletons/${skeletonId}/versions/${version}`);
}

export function confirmStorySkeleton(skeletonId: number, version?: number) {
  const query = version === undefined ? '' : `?version=${version}`;
  return request<import('./types').StorySkeletonVersion>(`/api/story-skeletons/${skeletonId}/confirm${query}`, {
    method: 'POST',
  });
}

export function createRewritePlan(payload: Record<string, unknown>) {
  return request<import('./types').RewritePlan>('/api/rewrite-plans', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getRewritePlan(planId: number) {
  return request<import('./types').RewritePlan>(`/api/rewrite-plans/${planId}`);
}

export function confirmRewritePlan(planId: number) {
  return request<import('./types').RewritePlan>(`/api/rewrite-plans/${planId}/confirm`, { method: 'POST' });
}

export function retrieveSceneContext(sceneId: number, payload: Record<string, unknown>) {
  return request<import('./types').RetrievalResult[]>(`/api/scenes/${sceneId}/retrieval`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function compileScenePrompt(sceneId: number, payload: Record<string, unknown>) {
  return request<import('./types').PromptCompilation>(`/api/scenes/${sceneId}/prompt-compile`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveSceneStage(sceneId: number, payload: Record<string, unknown>) {
  return request<{ id: number }>(`/api/scenes/${sceneId}/stages`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveSceneRewriteVersion(sceneId: number, payload: Record<string, unknown>) {
  return request<{ id: number }>(`/api/scenes/${sceneId}/rewrite-versions`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveTargetedRepair(sceneId: number, payload: Record<string, unknown>) {
  return request<{ id: number }>(`/api/scenes/${sceneId}/targeted-repairs`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveConsistencyCheck(payload: Record<string, unknown>) {
  return request<{ id: number }>('/api/consistency-checks', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function checkChapterContinuity(chapterId: number) {
  return request<Record<string, unknown>>(`/api/chapters/${chapterId}/continuity-check`);
}

export function checkBookConsistency(projectId: number) {
  return request<Record<string, unknown>>(`/api/projects/${projectId}/book-consistency-check`);
}

export function previewAIDocumentSplit(
  documentId: number,
  chapterId: number,
  prompt: string,
  modelId?: number | null,
) {
  return request<import('./types').AISplitProposal>(`/api/documents/${documentId}/split/ai/preview`, {
    method: 'POST',
    body: JSON.stringify({ chapter_id: chapterId, prompt, model_id: modelId ?? null }),
  });
}

export function applyAIDocumentSplit(
  documentId: number,
  proposalId: number,
  chapters: import('./types').AISplitProposal['chapters'],
) {
  return request<{ document_id: number; revision_id: number; chapters: import('./types').LibraryDocumentChapter[] }>(
    `/api/documents/${documentId}/split/ai/apply`,
    { method: 'POST', body: JSON.stringify({ proposal_id: proposalId, chapters }) },
  );
}

export function getSceneRewriteHistory(sceneId: number) {
  return request<Array<Record<string, unknown>>>(`/api/scenes/${sceneId}/rewrite-history`);
}

export function restoreSceneRewriteVersion(sceneId: number, versionId: number) {
  return request<{ id: number }>(`/api/scenes/${sceneId}/rewrite-history/${versionId}/restore`, {
    method: 'POST',
  });
}
