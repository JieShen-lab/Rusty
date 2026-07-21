import type {
  AnalysisPromptTemplate,
  AnalysisPromptTemplateWrite,
  AnchorExtractWrite,
  Chapter,
  ChapterDetail,
  CompiledPromptPreview,
  CharacterCard,
  CharacterCardWrite,
  ExportPlanItem,
  ExportPlanUpdate,
  GenerationAttempt,
  ModelConfig,
  ModelTestResult,
  OutlineTemplate,
  OutlineTemplateWrite,
  ModelWrite,
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

  let response: Response;
  try {
    response = await fetch(`${apiBase()}${path}`, { ...options, headers });
  } catch (error) {
    const recovered = await recoverBackend();
    if (!recovered) {
      throw new ApiError(0, `Rusty 后端已停止且自动重启失败：${String(error)}`);
    }
    try {
      response = await fetch(`${apiBase()}${path}`, { ...options, headers });
    } catch (retryError) {
      throw new ApiError(0, `Rusty 后端重启后仍无法连接：${String(retryError)}`);
    }
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

export function previewProject(sourcePath: string, workspacePath?: string) {
  return request<PreviewResponse>('/api/projects/preview', {
    method: 'POST',
    body: JSON.stringify({ source_path: sourcePath, workspace_path: workspacePath || null }),
  });
}

export function createProject(
  previewToken: string,
  projectName?: string,
  workspacePath?: string,
  purpose: ProjectPurpose = 'rewrite',
  promptTemplateId?: number | null,
  analysisPromptTemplateId?: number | null,
) {
  return request<Project>('/api/projects', {
    method: 'POST',
    body: JSON.stringify({
      preview_token: previewToken,
      project_name: projectName || null,
      workspace_path: workspacePath || null,
      purpose,
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

export function getCharacterCards() {
  return request<CharacterCard[]>('/api/characters');
}

export function createCharacterCard(payload: CharacterCardWrite) {
  return request<CharacterCard>('/api/characters', { method: 'POST', body: JSON.stringify(payload) });
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
