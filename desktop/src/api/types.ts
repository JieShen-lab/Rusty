export type Project = {
  id: number;
  name: string;
  status: string;
  current_stage: string;
  source_format: string | null;
  total_chapters: number;
  total_words: number;
  completed_chapters: number;
  book_title: string | null;
  author: string | null;
  created_at: string;
  updated_at: string;
  progress: number;
};

export type LibraryDocument = {
  id: number;
  title: string;
  author: string | null;
  description: string | null;
  source_filename: string;
  source_format: string;
  storage_path: string;
  source_size_bytes: number;
  stored_size_bytes: number;
  chapter_count: number;
  word_count: number;
  status: string;
  favorite: boolean;
  categories: string[];
  created_at: string;
  updated_at: string;
};

export type LibraryDocumentImportResult = {
  document: LibraryDocument;
  created: boolean;
  storage_format: 'txt';
};

export type DocumentProcessingSettings = {
  chapter_pattern: string;
  chapter_indent: number;
  paragraph_indent: number;
  blank_lines: number;
  trim_whitespace: boolean;
};

export type DocumentProcessingTemplate = {
  id: number;
  name: string;
  settings: DocumentProcessingSettings;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type LibraryDocumentRevision = {
  id: number;
  document_id: number;
  revision_number: number;
  revision_type: string;
  storage_path: string;
  template_id: number | null;
  parent_revision_id: number | null;
  created_at: string;
};

export type LibraryDocumentCleanupResult = {
  document: LibraryDocument;
  revision: LibraryDocumentRevision;
  created: boolean;
};

export type DocumentLibrarySettings = {
  storage_path: string;
};

export type DocumentCategory = {
  id: number;
  name: string;
  parent_id: number | null;
  sort_order: number;
  document_count: number;
};

export type LibraryDocumentChapter = {
  id: number;
  revision_id: number;
  index: number;
  title: string;
  start_line: number | null;
  end_line: number | null;
  word_count: number;
};

export type LibraryDocumentContent = {
  document_id: number;
  revision_id: number;
  chapter_id: number | null;
  title: string;
  text: string;
};

export type LibraryDocumentExportResult = {
  ok: boolean;
  format: 'txt' | 'epub';
  output_path: string;
};

export type Chapter = {
  id: number;
  project_id: number;
  index: number;
  title: string;
  original_text: string;
  rewritten_text: string | null;
  word_count: number;
  status: string;
  start_line: number | null;
  end_line: number | null;
};

export type ChapterAIOutputs = {
  plot_summary: string | null;
  plot_characters: Array<Record<string, unknown>> | null;
  needs_rewrite: boolean | null;
  scene_labels: string[] | null;
  scene_reasoning: string | null;
  scene_markers: Array<Record<string, unknown>> | null;
  plot_expansion_enabled: boolean | null;
  expanded_plot: string | null;
  rewrite_source: string | null;
  rewritten_word_count: number | null;
  expansion_ratio: number | null;
  rewrite_elapsed_ms: number | null;
  rewrite_mode: 'anchor_expand' | 'full_rewrite' | null;
  rewrite_anchor: string | null;
  rewrite_expanded: string | null;
  style_analysis: Record<string, unknown> | null;
  reviewed_style_analysis: Record<string, unknown> | null;
  style_analysis_status: string | null;
};

export type StageStatus = {
  stage: string;
  status: string;
  retry_count: number;
  elapsed_ms: number | null;
  started_at: string | null;
  finished_at: string | null;
};

export type ChapterError = {
  id: number;
  stage: string;
  error_type: string | null;
  message: string;
  created_at: string;
  resolved_at: string | null;
};

export type ChapterDetail = {
  chapter: Chapter;
  ai_outputs: ChapterAIOutputs;
  stage_statuses: StageStatus[];
  errors: ChapterError[];
};

export type CompiledPromptPreview = {
  stage: string;
  ruleset_id: string;
  expected_output: string;
  messages: Array<{ role: string; content: string }>;
  provenance: Record<string, unknown>;
  model?: Record<string, unknown>;
};

export type GenerationAttempt = {
  id: number;
  stage: string;
  attempt_number: number;
  request: CompiledPromptPreview;
  response_text: string;
  parsed: Record<string, unknown>;
  error_type: string | null;
  error_message: string | null;
  model_id: number | null;
  prompt_template_id: number | null;
  token_usage: Record<string, unknown>;
  elapsed_ms: number | null;
  created_at: string;
};

export type ProjectDetail = {
  project: Project;
  metadata: Record<string, unknown>;
  settings: Record<string, unknown> | null;
  exports: Array<Record<string, unknown>>;
};

export type ProjectPurpose = 'rewrite' | 'extract';

export type ChapterSplitOptions = {
  mode: 'auto' | 'simple' | 'regex';
  line_prefix?: string;
  number_style?: 'mixed' | 'arabic' | 'chinese';
  title_suffixes?: string[];
  extra_title_regex?: string | null;
  custom_regex?: string | null;
};

export type ExportSourceStatus = 'original' | 'manual_rewrite' | 'ai_rewrite' | 'kept_original';

export type ExportPlanItem = {
  chapter_id: number;
  export_order: number;
  export_title: string;
  include_in_export: boolean;
  source_status: ExportSourceStatus;
};

export type ExportPlanItemWrite = {
  chapter_id: number;
  export_order: number;
  export_title: string;
  include_in_export: boolean;
};

export type ExportPlanUpdate = {
  items: ExportPlanItemWrite[];
};

export type PreviewResponse = {
  preview_token: string;
  title: string;
  author: string | null;
  language: string | null;
  source_format: string;
  source_encoding: string | null;
  total_chapters: number;
  total_words: number;
  split_mode: string;
  chapters: Array<{
    index: number;
    title: string;
    word_count: number;
    start_line: number | null;
    end_line: number | null;
  }>;
};

export type ModelConfig = {
  id: number;
  display_name: string;
  provider: string;
  base_url: string;
  model_name: string;
  temperature: number;
  max_tokens: number | null;
  timeout_seconds: number;
  is_default: boolean;
  has_api_key: boolean;
};

export type ModelWrite = {
  display_name: string;
  provider: string;
  base_url: string;
  model_name: string;
  api_key?: string | null;
  temperature: number;
  max_tokens?: number | null;
  timeout_seconds: number;
  is_default: boolean;
};

export type ModelTestResult = {
  ok: boolean;
  message: string;
  elapsed_ms: number | null;
};

export type PromptTemplate = {
  id: number;
  name: string;
  version: number;
  is_default: boolean;
  global_rules: string;
  summary_rules: string;
  rewrite_rules: string;
  description: string;
  scene_rules: PromptSceneRule[];
  package_metadata: Record<string, unknown>;
  source_project_id: number | null;
};

export type PromptSceneRule = {
  scene_key: string;
  display_name: string;
  description: string;
  detection_prompt: string;
  rewrite_prompt: string;
  sort_order: number;
};

export type PromptTemplateWrite = {
  name: string;
  global_rules: string;
  summary_rules: string;
  rewrite_rules: string;
  description: string;
  scene_rules: PromptSceneRule[];
  package_metadata: Record<string, unknown>;
  source_project_id: number | null;
  is_default: boolean;
};

export type AnalysisPromptTemplate = {
  id: number;
  name: string;
  description: string;
  analysis_dimensions: string;
  evidence_rules: string;
  synthesis_rules: string;
  output_requirements: string;
  version: number;
  is_default: boolean;
};

export type AnalysisPromptTemplateWrite = Omit<AnalysisPromptTemplate, 'id' | 'version'>;

export type StyleAnalysis = {
  chapter_id: number;
  analysis: Record<string, unknown>;
  reviewed: Record<string, unknown>;
  status: string;
  analysis_prompt_template_id: number | null;
  model_id: number | null;
  elapsed_ms: number | null;
  updated_at: string | null;
  reviewed_at: string | null;
};

export type StyleDetailLevel = 'brief' | 'standard' | 'detailed';

export type StyleTemplate = {
  id: number;
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  global_prompt: string;
  rewrite_prompt: string;
  style_profile: Record<string, unknown>;
  generated_prompt: string;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  version: number;
};

export type StyleTemplateWrite = {
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  global_prompt: string;
  rewrite_prompt: string;
  style_profile: Record<string, unknown>;
  generated_prompt: string;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
};

export type StyleTemplateExtractWrite = {
  name: string;
  detail_level: StyleDetailLevel;
  sample_text?: string | null;
  source_path?: string | null;
  model_id?: number | null;
};

export type StyleTrialWrite = {
  sample_scene: string;
  target_chars: number;
  model_id?: number | null;
};

export type ProjectStyleBinding = {
  style_template: StyleTemplate | null;
};

export type OutlineTemplate = {
  id: number;
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  outline: Record<string, unknown>;
  anchor_prompt: string;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  version: number;
};

export type OutlineTemplateWrite = {
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  outline: Record<string, unknown>;
  anchor_prompt: string;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
};

export type CharacterCard = {
  id: number;
  name: string;
  aliases: string[];
  description: string;
  priority: number;
  is_main: boolean;
  relationship_notes: string;
  personality: string;
  speech_style: string;
  action_constraints: string;
  anti_ooc_rules: string;
  profile: Record<string, unknown>;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  scope: 'public' | 'project';
  project_id: number | null;
  source_character_card_id: number | null;
  source_version: number | null;
  version: number;
  sort_order: number;
};

export type CharacterCardWrite = {
  name: string;
  aliases: string[];
  description: string;
  priority: number;
  is_main: boolean;
  relationship_notes: string;
  personality: string;
  speech_style: string;
  action_constraints: string;
  anti_ooc_rules: string;
  profile: Record<string, unknown>;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  scope?: 'public' | 'project';
  project_id?: number | null;
};

export type AnchorExtractWrite = {
  name?: string | null;
  detail_level: StyleDetailLevel;
  sample_text?: string | null;
  source_path?: string | null;
  source_project_id?: number | null;
  source_document_id?: number | null;
  model_id?: number | null;
  scope?: 'public' | 'project';
  project_id?: number | null;
};

export type MaterialType = 'outline' | 'plot_skeleton' | 'snippet';
export type MaterialScope = 'public' | 'project';

export type Material = {
  id: number;
  material_type: MaterialType;
  scope: MaterialScope;
  project_id: number | null;
  project_name: string | null;
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  content: Record<string, unknown>;
  source_metadata: Record<string, unknown>;
  import_metadata: Record<string, unknown>;
  source_material_id: number | null;
  source_version: number | null;
  timeline_start_chapter: number | null;
  timeline_end_chapter: number | null;
  sort_order: number;
  version: number;
  created_at: string;
  updated_at: string;
  categories: string[];
};

export type MaterialWrite = {
  material_type: MaterialType;
  scope: MaterialScope;
  project_id?: number | null;
  name: string;
  description?: string;
  detail_level?: StyleDetailLevel;
  content: Record<string, unknown>;
  source_metadata?: Record<string, unknown>;
  import_metadata?: Record<string, unknown>;
  timeline_start_chapter?: number | null;
  timeline_end_chapter?: number | null;
  sort_order?: number;
  category_ids?: number[];
};

export type MaterialUpdate = Omit<MaterialWrite, 'material_type' | 'scope' | 'project_id' | 'source_metadata' | 'import_metadata'>;

export type MaterialCategory = {
  id: number;
  name: string;
  material_type: MaterialType;
  sort_order: number;
  material_count: number;
};

export type MaterialExtractWrite = AnchorExtractWrite & {
  material_type: MaterialType;
};

export type ProjectOutlineBinding = {
  outline_template: OutlineTemplate | null;
};

export type ProjectCharacterBindings = {
  character_cards: CharacterCard[];
};

export type ProjectSettingsWrite = {
  model_id?: number | null;
  prompt_template_id?: number | null;
  analysis_prompt_template_id?: number | null;
  processing_mode?: string;
  concurrency?: number;
  target_word_count?: number | null;
  min_expansion_ratio?: number | null;
  rewrite_mode?: 'anchor_expand' | 'full_rewrite';
  max_attempts?: number;
};

export type PipelineRunResult = {
  ok: boolean;
  processed: number;
  skipped: number;
  failed: number;
  paused: boolean;
};
