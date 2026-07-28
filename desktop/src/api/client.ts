import type {
  AnalysisPromptTemplate,
  AnalysisPromptTemplateWrite,
  AnchorExtractWrite,
  Chapter,
  ChapterSplitOptions,
  ChapterDetail,
  CompiledPromptPreview,
  CharacterCard,
  CharacterCardWrite,
  ExportPlanItem,
  ExportPlanUpdate,
  GenerationAttempt,
  ModelConfig,
  ModelTestResult,
  Material,
  MaterialExtractWrite,
  MaterialScope,
  MaterialType,
  MaterialUpdate,
  MaterialWrite,
  ResourceTag,
  SelectionResourceCreate,
  SplitPreview,
  OutlineTemplate,
  OutlineTemplateWrite,
  ModelWrite,
  LibraryDocument,
  LibraryDocumentCleanupResult,
  LibraryDocumentChapter,
  LibraryDocumentContent,
  LibraryDocumentExportResult,
  LibraryDocumentImportResult,
  LibraryDocumentRevision,
  DocumentProcessingSettings,
  DocumentProcessingTemplate,
  DocumentLibrarySettings,
  PreviewResponse,
  Project,
  ProjectCharacterBindings,
  ProjectDetail,
  ProjectOutlineBinding,
  ProjectPurpose,
  ProjectSettingsWrite,
  ProjectStyleBinding,
  PromptTemplate,
  PromptTemplateWrite,
  PipelineRunResult,
  StyleTemplateExtractWrite,
  StyleTemplate,
  StyleTrialWrite,
  StyleAnalysis,
  StyleTemplateWrite,
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

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
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

export function getDocumentTags() {
  return request<ResourceTag[]>('/api/document-tags');
}

export function createDocumentTag(name: string) {
  return request<ResourceTag>('/api/document-tags', { method: 'POST', body: JSON.stringify({ name }) });
}

export function renameDocumentTag(tagId: number, name: string) {
  return request<ResourceTag>(`/api/document-tags/${tagId}`, { method: 'POST', body: JSON.stringify({ name }) });
}

export function deleteDocumentTag(tagId: number) {
  return request<{ ok: boolean }>(`/api/document-tags/${tagId}/delete`, { method: 'POST' });
}

export function assignDocumentTag(documentId: number, tagId: number, selected: boolean) {
  return request<LibraryDocument>(`/api/documents/${documentId}/tags/${tagId}`, {
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

export function getLibraryDocumentContent(documentId: number, chapterId?: number | null) {
  const query = chapterId == null ? '' : `?chapter_id=${chapterId}`;
  return request<LibraryDocumentContent>(`/api/documents/${documentId}/content${query}`);
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
  position: 'before' | 'after' | 'end',
  currentChapterId?: number | null,
) {
  return request<LibraryDocumentCleanupResult>(`/api/documents/${documentId}/chapters`, {
    method: 'POST',
    body: JSON.stringify({ title, text, position, current_chapter_id: currentChapterId ?? null }),
  });
}

export function previewRegexSplit(documentId: number, pattern: string) {
  return request<SplitPreview>(`/api/documents/${documentId}/split/regex/preview`, {
    method: 'POST',
    body: JSON.stringify({ pattern }),
  });
}

export function applyRegexSplit(documentId: number, pattern: string, previewToken: string) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/split/regex/apply`, {
    method: 'POST',
    body: JSON.stringify({ pattern, preview_token: previewToken }),
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

export function reorderLibraryDocumentChapters(documentId: number, orderedChapterIds: number[]) {
  return request<LibraryDocumentChapter[]>(`/api/documents/${documentId}/chapters/reorder`, {
    method: 'POST',
    body: JSON.stringify({ ordered_chapter_ids: orderedChapterIds }),
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

export function getChapters(projectId: number) {
  return request<Chapter[]>(`/api/projects/${projectId}/chapters`);
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
  purpose: ProjectPurpose = 'rewrite',
  promptTemplateId?: number | null,
  analysisPromptTemplateId?: number | null,
  modelId?: number | null,
) {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({
      preview_token: previewToken,
      project_name: projectName || null,
      workspace_path: workspacePath || null,
      purpose,
      model_id: modelId ?? null,
      prompt_template_id: promptTemplateId ?? null,
      analysis_prompt_template_id: analysisPromptTemplateId ?? null,
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

export function getStyleTemplates() {
  return request<StyleTemplate[]>('/api/styles');
}

export function getStyleTemplate(templateId: number) {
  return request<StyleTemplate>(`/api/styles/${templateId}`);
}

export function createStyleTemplate(payload: StyleTemplateWrite) {
  return request<StyleTemplate>('/api/styles', { method: 'POST', body: JSON.stringify(payload) });
}

export function importStyleTemplate(content: string) {
  return request<StyleTemplate>('/api/styles/import', { method: 'POST', body: JSON.stringify({ content }) });
}

export function extractStyleTemplate(payload: StyleTemplateExtractWrite) {
  return request<StyleTemplate>('/api/styles/extract', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateStyleTemplate(templateId: number, payload: StyleTemplateWrite) {
  return request<StyleTemplate>(`/api/styles/${templateId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteStyleTemplate(templateId: number) {
  return request<{ ok: boolean }>(`/api/styles/${templateId}/delete`, { method: 'POST' });
}

export function exportStyleTemplate(templateId: number) {
  return request<{ content: string }>(`/api/styles/${templateId}/export`, { method: 'POST' });
}

export function trialWriteStyleTemplate(templateId: number, payload: StyleTrialWrite) {
  return request<{ ok: boolean; text: string }>(`/api/styles/${templateId}/trial-write`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getProjectStyle(projectId: number) {
  return request<ProjectStyleBinding>(`/api/projects/${projectId}/style`);
}

export function bindProjectStyle(projectId: number, styleTemplateId: number | null) {
  return request<ProjectStyleBinding>(`/api/projects/${projectId}/style`, {
    method: 'POST',
    body: JSON.stringify({ style_template_id: styleTemplateId }),
  });
}

export function getOutlineTemplates() {
  return request<OutlineTemplate[]>('/api/outlines');
}

export function getMaterials(filters: {
  scope?: MaterialScope;
  project_id?: number;
  material_type?: MaterialType;
  tag_id?: number;
  analysis_status?: 'unanalyzed' | 'analyzed';
  untagged?: boolean;
  query?: string;
} = {}) {
  const params = new URLSearchParams();
  if (filters.scope) params.set('scope', filters.scope);
  if (filters.project_id !== undefined) params.set('project_id', String(filters.project_id));
  if (filters.material_type) params.set('material_type', filters.material_type);
  if (filters.tag_id !== undefined) params.set('tag_id', String(filters.tag_id));
  if (filters.analysis_status) params.set('analysis_status', filters.analysis_status);
  if (filters.untagged) params.set('untagged', 'true');
  if (filters.query) params.set('query', filters.query);
  const query = params.size ? `?${params.toString()}` : '';
  return request<Material[]>(`/api/materials${query}`);
}

export function getMaterialTags() {
  return request<ResourceTag[]>('/api/material-tags');
}

export function createMaterialTag(name: string) {
  return request<ResourceTag>('/api/material-tags', { method: 'POST', body: JSON.stringify({ name }) });
}

export function renameMaterialTag(tagId: number, name: string) {
  return request<ResourceTag>(`/api/material-tags/${tagId}`, { method: 'POST', body: JSON.stringify({ name }) });
}

export function deleteMaterialTag(tagId: number) {
  return request<{ ok: boolean }>(`/api/material-tags/${tagId}/delete`, { method: 'POST' });
}

export function assignMaterialTag(materialId: number, tagId: number, selected: boolean) {
  return request<Material>(`/api/materials/${materialId}/tags/${tagId}`, {
    method: 'POST',
    body: JSON.stringify({ selected }),
  });
}

export function analyzeMaterial(materialId: number, modelId?: number | null) {
  return request<import('./types').MaterialAnalysisProposal>(`/api/materials/${materialId}/analyze`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  });
}

export function createMaterial(payload: MaterialWrite) {
  return request<Material>('/api/materials', { method: 'POST', body: JSON.stringify(payload) });
}

export function importMaterial(payload: MaterialWrite) {
  return request<Material>('/api/materials/import', { method: 'POST', body: JSON.stringify(payload) });
}

export function applyMaterialAnalysis(materialId: number, proposal: import('./types').MaterialAnalysisProposal) {
  return request<Material>(`/api/materials/${materialId}/analysis/apply`, {
    method: 'POST',
    body: JSON.stringify({
      content: proposal.proposal,
      model_id: proposal.model_id,
      invocation_id: proposal.invocation_id,
    }),
  });
}

export function importMaterialJson(value: unknown, defaultScope: MaterialScope, defaultProjectId?: number | null) {
  return request<import('./types').MaterialJsonImportResult>('/api/materials/import-json', {
    method: 'POST',
    body: JSON.stringify({
      value,
      default_scope: defaultScope,
      default_project_id: defaultProjectId ?? null,
    }),
  });
}

export function updateMaterial(materialId: number, payload: MaterialUpdate) {
  return request<Material>(`/api/materials/${materialId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteMaterial(materialId: number) {
  return request<{ ok: boolean }>(`/api/materials/${materialId}/delete`, { method: 'POST' });
}

export function copyMaterial(
  materialId: number,
  targetScope: MaterialScope,
  targetProjectId?: number | null,
  tagIds: number[] = [],
) {
  return request<Material>(`/api/materials/${materialId}/copy`, {
    method: 'POST',
    body: JSON.stringify({
      target_scope: targetScope,
      target_project_id: targetProjectId ?? null,
      tag_ids: tagIds,
    }),
  });
}

export function extractMaterials(payload: MaterialExtractWrite) {
  return request<{ materials: Material[] }>('/api/material-extractions', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function createOutlineTemplate(payload: OutlineTemplateWrite) {
  return request<OutlineTemplate>('/api/outlines', { method: 'POST', body: JSON.stringify(payload) });
}

export function updateOutlineTemplate(templateId: number, payload: OutlineTemplateWrite) {
  return request<OutlineTemplate>(`/api/outlines/${templateId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteOutlineTemplate(templateId: number) {
  return request<{ ok: boolean }>(`/api/outlines/${templateId}/delete`, { method: 'POST' });
}

export function extractOutlineTemplate(payload: AnchorExtractWrite) {
  return request<OutlineTemplate>('/api/outlines/extract', { method: 'POST', body: JSON.stringify(payload) });
}

export function getCharacterCards(scope?: 'public' | 'project', projectId?: number | null) {
  const params = new URLSearchParams();
  if (scope) params.set('scope', scope);
  if (projectId !== undefined && projectId !== null) params.set('project_id', String(projectId));
  const query = params.size ? `?${params.toString()}` : '';
  return request<CharacterCard[]>(`/api/characters${query}`);
}

export function getCharacterTags() {
  return request<ResourceTag[]>('/api/character-tags');
}

export function createCharacterTag(name: string) {
  return request<ResourceTag>('/api/character-tags', { method: 'POST', body: JSON.stringify({ name }) });
}

export function renameCharacterTag(tagId: number, name: string) {
  return request<ResourceTag>(`/api/character-tags/${tagId}`, { method: 'POST', body: JSON.stringify({ name }) });
}

export function deleteCharacterTag(tagId: number) {
  return request<{ ok: boolean }>(`/api/character-tags/${tagId}/delete`, { method: 'POST' });
}

export function assignCharacterTag(cardId: number, tagId: number, selected: boolean) {
  return request<CharacterCard>(`/api/characters/${cardId}/tags/${tagId}`, {
    method: 'POST',
    body: JSON.stringify({ selected }),
  });
}

export function analyzeCharacterCard(
  cardId: number,
  modelId?: number | null,
) {
  return request<import('./types').CharacterAnalysisProposal>(`/api/characters/${cardId}/analyze`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
  });
}

export function confirmCharacterAnalysis(
  cardId: number,
  payload: {
    identity: string;
    age: string;
    setting_text: string;
    custom_fields: import('./types').CharacterCustomField[];
    invocation_id: number;
  },
) {
  return request<CharacterCard>(`/api/characters/${cardId}/analyze/confirm`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function saveCharacterCover(cardId: number, dataBase64: string) {
  return request<CharacterCard>(`/api/characters/${cardId}/cover`, {
    method: 'POST',
    body: JSON.stringify({ data_base64: dataBase64 }),
  });
}

export function removeCharacterCover(cardId: number) {
  return request<CharacterCard>(`/api/characters/${cardId}/cover/delete`, { method: 'POST' });
}

export function characterCoverUrl(cardId: number) {
  return `${apiBase()}/api/characters/${cardId}/cover`;
}

export function createSceneMaterialFromSelection(payload: SelectionResourceCreate) {
  return request<Material>('/api/selection/materials/scene-reference', { method: 'POST', body: JSON.stringify(payload) });
}

export function createPlotSkeletonFromSelection(payload: SelectionResourceCreate) {
  return request<Material>('/api/selection/materials/plot-skeleton', { method: 'POST', body: JSON.stringify(payload) });
}

export function createCharacterFromSelection(payload: SelectionResourceCreate) {
  return request<CharacterCard>('/api/selection/characters', { method: 'POST', body: JSON.stringify(payload) });
}

export function createCharacterCard(payload: CharacterCardWrite) {
  return request<CharacterCard>('/api/characters', { method: 'POST', body: JSON.stringify(payload) });
}

export function importCharacterCard(payload: CharacterCardWrite) {
  return request<CharacterCard>('/api/characters/import', { method: 'POST', body: JSON.stringify(payload) });
}

export function copyCharacterCard(
  cardId: number,
  targetScope: 'public' | 'project',
  targetProjectId?: number | null,
) {
  return request<CharacterCard>(`/api/characters/${cardId}/copy`, {
    method: 'POST',
    body: JSON.stringify({
      target_scope: targetScope,
      target_project_id: targetProjectId ?? null,
    }),
  });
}

export function updateCharacterCard(cardId: number, payload: CharacterCardWrite) {
  return request<CharacterCard>(`/api/characters/${cardId}`, { method: 'POST', body: JSON.stringify(payload) });
}

export function deleteCharacterCard(cardId: number) {
  return request<{ ok: boolean }>(`/api/characters/${cardId}/delete`, { method: 'POST' });
}

export function extractCharacterCards(payload: AnchorExtractWrite) {
  return request<ProjectCharacterBindings>('/api/characters/extract', { method: 'POST', body: JSON.stringify(payload) });
}

export function getProjectOutline(projectId: number) {
  return request<ProjectOutlineBinding>(`/api/projects/${projectId}/outline`);
}

export function bindProjectOutline(projectId: number, outlineTemplateId: number | null) {
  return request<ProjectOutlineBinding>(`/api/projects/${projectId}/outline`, {
    method: 'POST',
    body: JSON.stringify({ outline_template_id: outlineTemplateId }),
  });
}

export function getProjectCharacters(projectId: number) {
  return request<ProjectCharacterBindings>(`/api/projects/${projectId}/characters`);
}

export function bindProjectCharacter(projectId: number, characterCardId: number, sortOrder = 0) {
  return request<ProjectCharacterBindings>(`/api/projects/${projectId}/characters`, {
    method: 'POST',
    body: JSON.stringify({ character_card_id: characterCardId, sort_order: sortOrder }),
  });
}

export function unbindProjectCharacter(projectId: number, characterCardId: number) {
  return request<ProjectCharacterBindings>(`/api/projects/${projectId}/characters/${characterCardId}/unbind`, {
    method: 'POST',
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
  payload: { character_name: string; character_card_id?: number | null; state: Record<string, unknown> },
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
  nodes: Record<string, unknown>[];
}) {
  return request<import('./types').StorySkeletonVersion>('/api/story-skeletons', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function reviseStorySkeleton(
  skeletonId: number,
  nodes: Record<string, unknown>[],
  changeNote = '',
) {
  return request<import('./types').StorySkeletonVersion>(`/api/story-skeletons/${skeletonId}/versions`, {
    method: 'POST',
    body: JSON.stringify({ nodes, change_note: changeNote }),
  });
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

export function previewAIDocumentSplit(documentId: number, modelId?: number | null) {
  return request<import('./types').AISplitProposal>(`/api/documents/${documentId}/split/ai/preview`, {
    method: 'POST',
    body: JSON.stringify({ model_id: modelId ?? null }),
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

export function startSceneWorkflow(
  sceneId: number,
  payload: {
    mode: import('./types').RewriteMode;
    user_instruction?: string;
    model_id?: number | null;
    character_ids?: number[];
    material_ids?: number[];
  },
) {
  return request<import('./types').SceneWorkflowRun>(`/api/scenes/${sceneId}/workflow/start`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function generateSceneWorkflowPlan(runId: number, payload: Record<string, unknown>) {
  return request<import('./types').SceneWorkflowRun>(`/api/scene-workflows/${runId}/plan`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function executeSceneWorkflow(runId: number, payload: import('./types').SceneWorkflowExecutePayload) {
  return request<import('./types').SceneWorkflowRun & {
    rewrite_version_id: number;
    consistency: Record<string, unknown>;
  }>(`/api/scene-workflows/${runId}/execute`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function getSceneRewriteHistory(sceneId: number) {
  return request<Array<Record<string, unknown>>>(`/api/scenes/${sceneId}/rewrite-history`);
}

export function restoreSceneRewriteVersion(sceneId: number, versionId: number) {
  return request<{ id: number }>(`/api/scenes/${sceneId}/rewrite-history/${versionId}/restore`, {
    method: 'POST',
  });
}
