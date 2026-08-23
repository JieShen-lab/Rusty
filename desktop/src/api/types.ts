export type Project = {
  id: number;
  name: string;
  project_kind: 'rewrite' | 'branch' | 'legacy_extract';
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
  is_project_document: boolean;
  category_ids: number[];
  categories: string[];
  project_ids: number[];
  created_at: string;
  updated_at: string;
};

export type DocumentCategory = {
  id: number;
  name: string;
  normalized_name: string;
  sort_order: number;
  resource_count: number;
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

export type LibraryDocumentAICleanupResult = {
  document: LibraryDocument;
  revision: LibraryDocumentRevision | null;
  created: boolean;
  chapters: Array<{
    chapter_id: number;
    title: string;
    status: 'success' | 'failed';
    error: string | null;
  }>;
};

export type DocumentLibrarySettings = {
  storage_path: string;
};

export type LibraryDocumentChapter = {
  id: number;
  revision_id: number;
  index: number;
  title: string;
  start_line: number | null;
  end_line: number | null;
  start_offset: number | null;
  end_offset: number | null;
  word_count: number;
  volume_id: number | null;
};

export type LibraryDocumentVolume = {
  id: number;
  revision_id: number;
  index: number;
  title: string;
  start_offset: number;
  end_offset: number;
  word_count: number;
  chapters: LibraryDocumentChapter[];
};

export type LibraryDocumentDirectory = {
  volumes: LibraryDocumentVolume[];
  unassigned_chapters: LibraryDocumentChapter[];
};

export type LibraryDocumentContent = {
  document_id: number;
  revision_id: number;
  chapter_id: number | null;
  title: string;
  text: string;
  body_text: string;
  section_start_offset: number;
  body_start_offset: number;
  end_offset: number;
  start_offset: number;
};

export type LibraryDocumentDraft = {
  id: number;
  document_id: number;
  chapter_id: number | null;
  base_revision_id: number;
  title: string;
  text: string;
  updated_at: string;
};

export type LibraryDocumentCreateChapterResult = LibraryDocumentCleanupResult & {
  created_chapter_id: number;
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

export type CreativeWorkflowStage =
  | 'not_started'
  | 'summary'
  | 'direction'
  | 'special_analysis'
  | 'style'
  | 'writing'
  | 'review'
  | 'confirmed';

export type ChapterWorkflowState = {
  chapter_id: number;
  current_stage: CreativeWorkflowStage;
  source_base_kind: 'original' | 'rewrite_version' | null;
  source_base_version_id: number | null;
  source_hash: string;
  source_changed: boolean;
  summary: ChapterSummary | null;
  direction: ChapterCreativeIntent | null;
  special_analysis: ChapterSpecialAnalysis | null;
  style: ChapterStyleContext | null;
  writing: ChapterWriting | null;
  updated_at: string;
};

export type ChapterAIOutputs = {
  plot_summary: string | null;
  plot_characters: Array<Record<string, unknown>> | null;
  key_events: string[] | null;
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

export type ProjectKind = 'rewrite' | 'branch';

export type StoryBranch = {
  id: number;
  project_id: number;
  parent_branch_id: number | null;
  base_source_kind: 'original' | 'branch';
  base_source_version_id: number | null;
  name: string;
  branch_mode: 'open_continuation' | 'fork' | 'fork_and_rejoin';
  downstream_strategy: 'replace' | 'reference' | 'rejoin';
  status: string;
  start_anchor?: StoryAnchor | null;
  return_anchor?: StoryAnchor | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowObject = { [key: string]: unknown };

export type StoryAnchor = {
  anchor_type:
    | 'document_end'
    | 'chapter_start'
    | 'chapter_end'
    | 'scene_start'
    | 'scene_end'
    | 'skeleton_node'
    | 'text_offset'
    | 'branch_chapter'
    | 'branch_scene';
  chapter_id?: number | null;
  scene_id?: number | null;
  skeleton_version_id?: number | null;
  node_id?: string | null;
  branch_chapter_id?: number | null;
  branch_scene_id?: number | null;
  text_offset?: number | null;
  side?: 'before' | 'after' | 'at' | null;
  source_version_id?: number | null;
  source_hash?: string | null;
};

export type RewriteSemanticSegment = {
  id: number;
  rewrite_version_id: number;
  segment_kind: 'scene' | 'event_node' | 'generated_event';
  source_scene_id: number | null;
  skeleton_version_id: number | null;
  node_id: string | null;
  segment_index: number;
  start_offset: number;
  end_offset: number;
  mapping_method: 'identity' | 'shifted' | 'structural' | 'semantic';
  confidence: number;
  needs_remap: boolean;
  state_method: string;
  state_before: WorkflowObject;
  state_after: WorkflowObject;
};

export type StoryAnchorPreview = {
  resolved_version_id: number | null;
  resolved_start: number;
  resolved_end: number;
  text_excerpt: string;
  state_before: WorkflowObject;
  state_after: WorkflowObject;
  mapping_method: 'identity' | 'shifted' | 'structural' | 'semantic';
  state_method: string;
  confidence: number;
  semantic_map_hash: string | null;
};

export type BranchCreateRequest = {
  name: string;
  branch_mode: 'open_continuation' | 'fork';
  start_anchor: StoryAnchor;
};

export type StructuredEventNode = {
  id: string;
  order: number;
  event_type: string;
  summary: string;
  participants: string[];
  location: string;
  time_state: WorkflowObject;
  causes: string[];
  effects: string[];
  motivation?: string;
  knowledge_changes?: string[];
  locked: boolean;
  source_span: WorkflowObject | null;
  confidence: number;
};

export type StructuredSkeleton = {
  metadata: WorkflowObject;
  event_nodes: StructuredEventNode[];
  causal_links: WorkflowObject[];
  character_state_changes: WorkflowObject[];
  location_changes: WorkflowObject[];
  time_changes: WorkflowObject[];
  object_changes: WorkflowObject[];
  knowledge_changes: WorkflowObject[];
  relationship_changes: WorkflowObject[];
  foreshadowing: WorkflowObject[];
  open_threads: WorkflowObject[];
  resolved_threads: WorkflowObject[];
  required_start_state: WorkflowObject;
  required_end_state: WorkflowObject;
  editable_points: WorkflowObject[];
  source_references: WorkflowObject[];
};

export type ChapterSourceSelection =
  | { kind: 'current' }
  | { kind: 'original' }
  | { kind: 'rewrite_version'; version_id: number };

export type ChapterRewriteVersion = {
  id: number;
  project_id: number;
  chapter_id: number;
  version: number;
  parent_version_id: number | null;
  source_kind: string;
  source_operation: 'plot_generation' | 'prose_rewrite' | 'canon_change' | 'manual' | 'migration' | 'restore';
  source_run_id: number | null;
  source_base_kind: 'original' | 'rewrite_version';
  source_base_version_id: number | null;
  source_hash: string;
  rewritten_text: string;
  content_hash: string;
  facts_before: WorkflowObject;
  facts_after: WorkflowObject;
  fact_chain_status: 'consistent' | 'needs_recompute';
  created_at: string;
  is_current: boolean;
};

export type RewriteVersionSkeleton = {
  rewrite_version_id: number;
  skeleton_id: number;
  skeleton_version_id: number;
  structured: StructuredSkeleton;
  source_kind: 'rewrite_version';
  status: string;
};

export type PlotGenerationStartRequest = {
  project_id: number;
  generation_mode: 'bounded_insert' | 'open_continuation' | 'fork';
  start_anchor: StoryAnchor;
  return_anchor?: StoryAnchor | null;
  user_direction: string;
  selected_material_ids?: number[];
  style_profile_id?: number | null;
  branch_id?: number | null;
  branch_name?: string;
  range_operation?: 'insert_between' | 'replace_range';
  source?: ChapterSourceSelection;
};

export type GeneratedSceneRequest = {
  title?: string;
  text: string;
  facts_after?: WorkflowObject;
};

export type PlotGenerationExecuteRequest = {
  max_scenes?: number | null;
};

export type PlotGenerationStatus =
  | 'awaiting_skeleton'
  | 'planning_blocked'
  | 'awaiting_seams'
  | 'ready'
  | 'generating'
  | 'repair_required'
  | 'completed'
  | 'failed'
  | 'cancelled';

export type PlotGenerationRun = {
  id: number;
  project_id: number;
  branch_id: number | null;
  generation_mode: PlotGenerationStartRequest['generation_mode'];
  range_operation: 'insert_between' | 'replace_range';
  output_topology: 'in_place' | 'branch';
  status: PlotGenerationStatus;
  stage: string;
  start_anchor: StoryAnchor;
  return_anchor: StoryAnchor | null;
  start_state: WorkflowObject;
  required_return_state: WorkflowObject;
  target_skeleton: StructuredSkeleton;
  context: WorkflowObject;
  seams: WorkflowObject[] | WorkflowObject;
  issues: WorkflowObject[] | WorkflowObject;
  result: WorkflowObject;
  scene_plan: WorkflowObject;
  fact_ledger: WorkflowObject;
  generated_progress: {
    chapters: Array<WorkflowObject & { scenes?: WorkflowObject[] }>;
    scenes: WorkflowObject[];
  };
  next_scene_cursor: number;
  generation_attempt: number;
  operation_type: 'plot_generation';
  user_direction: string;
  created_at: string;
  updated_at: string;
  source_chapter_id: number | null;
  source_base_kind: 'original' | 'rewrite_version' | null;
  source_base_version_id: number | null;
  source_hash: string | null;
  source_map_hash: string | null;
  resolved_start_anchor: WorkflowObject;
  resolved_return_anchor: WorkflowObject | null;
  expected_source_head_version_id: number | null;
  result_version_id: number | null;
};

export type ProseRewritePlanRequest = {
  project_id: number;
  chapter_id: number;
  source_skeleton: StructuredSkeleton;
  source_skeleton_version_id: number;
  preservation_policy: WorkflowObject;
  style_profile_id?: number | null;
  user_direction?: string;
  source?: ChapterSourceSelection;
};

export type ProseRewriteExecuteRequest = Record<string, never>;

export type ProseRewriteRun = {
  id: number;
  project_id: number;
  chapter_id: number;
  status: 'planned' | 'generating' | 'blocked' | 'completed' | 'failed' | 'cancelled';
  source_skeleton: StructuredSkeleton;
  source_skeleton_version_id: number | null;
  preservation_policy: WorkflowObject;
  target_skeleton: StructuredSkeleton;
  rewrite_plan: WorkflowObject;
  rewritten_text: string | null;
  issues: WorkflowObject[];
  operation_type: 'prose_rewrite';
  source_base_kind: 'original' | 'rewrite_version' | null;
  source_base_version_id: number | null;
  source_hash: string | null;
  source_map_hash: string | null;
  expected_source_head_version_id: number | null;
  result_version_id: number | null;
  generation_attempt: number;
  created_at: string;
  updated_at: string;
};

export type LegacyAnalysisExport = {
  schema: 'rusty.legacy_analysis_export.v1';
  project: WorkflowObject;
  metadata: WorkflowObject;
  chapter_analyses: WorkflowObject[];
  character_analyses: WorkflowObject[];
  style_analysis: WorkflowObject;
  generated_prompts: WorkflowObject[];
  structured_skeletons: WorkflowObject[];
};

export type LegacyProjectCreateRequest = {
  target_project_kind: 'rewrite' | 'branch';
  copy_source_text: true;
  copy_analysis_results: boolean;
  project_name?: string | null;
};

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

export type AnalysisStatus = 'unanalyzed' | 'analyzed';
export type MaterialType = 'author_style';
export type MaterialScope = 'public' | 'project';
export type MaterialAITask = 'author_style_extraction';

export type MaterialAIDimension = {
  id: string;
  name: string;
  requirement: string;
};

export type AuthorStyleContent = Record<string, unknown> & {
  schema_version?: number;
  work?: string;
  overall_style?: string;
  dimensions?: Array<{
    id: string;
    name: string;
    analysis: string;
    features: string[];
    examples: string[];
  }>;
};

export type MaterialSourceSummary = {
  kind:
    | 'manual'
    | 'document_selection'
    | 'project_selection'
    | 'file_import'
    | 'pasted_text'
    | 'ai_extraction'
    | 'legacy_copy'
    | 'legacy_project_material';
  label: string;
  document_id?: number | null;
  chapter_id?: number | null;
  project_id?: number | null;
};

export type MaterialCategory = {
  id: number;
  material_type: MaterialType;
  name: string;
  normalized_name: string;
  sort_order: number;
  resource_count: number;
};

export type Material = {
  id: number;
  material_type: MaterialType;
  scope: MaterialScope;
  project_id: number | null;
  project_name: string | null;
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  raw_text: string;
  content: AuthorStyleContent;
  analysis_status: AnalysisStatus;
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
  category_ids: number[];
  categories: string[];
  source_summary: MaterialSourceSummary;
};

export type MaterialWrite = {
  material_type: MaterialType;
  scope: MaterialScope;
  project_id?: number | null;
  name: string;
  description?: string;
  detail_level?: StyleDetailLevel;
  raw_text?: string;
  content: AuthorStyleContent;
  analysis_status?: AnalysisStatus;
  source_metadata?: Record<string, unknown>;
  import_metadata?: Record<string, unknown>;
  timeline_start_chapter?: number | null;
  timeline_end_chapter?: number | null;
  sort_order?: number;
  category_ids?: number[];
};

export type MaterialUpdate = Omit<MaterialWrite, 'material_type' | 'scope' | 'project_id' | 'source_metadata' | 'import_metadata'>;

export type ProjectMaterialFilter = {
  project_id: number;
  material_type: MaterialType;
  manual_material_ids: number[];
  include_scene_keywords: boolean;
};

export type MaterialAISettings = {
  task_type: MaterialAITask;
  model_id: number | null;
  detail_level: StyleDetailLevel;
  system_prompt: string;
  base_instruction: string;
  dimensions: MaterialAIDimension[];
  extra_requirements: string;
  prompt_preview: string;
  updated_at: string;
};

export type MaterialExtractionCandidate = {
  candidate_id: string;
  material_type: MaterialType;
  selected: boolean;
  name: string;
  description: string;
  content: AuthorStyleContent;
  category_ids?: number[];
  evidence: Array<Record<string, unknown>>;
  evidence_summary: string;
  confidence: number;
  warnings: string[];
};

export type MaterialExtractionPreview = {
  preview_token: string;
  expires_at: string;
  task_type: MaterialAITask;
  material_type: MaterialType;
  source_summary: MaterialSourceSummary;
  prompt_snapshot: Record<string, unknown>;
  candidates: MaterialExtractionCandidate[];
};

export type MaterialExtractionApplyResult = {
  created: Array<{ candidate_id: string; material_id: number | null; error: string | null }>;
  errors: Array<{ candidate_id: string; material_id: number | null; error: string | null }>;
};

export type SelectionResourceCreate = {
  source_kind: 'document' | 'project';
  selected_text: string;
  name: string;
  document_id?: number | null;
  project_id?: number | null;
  chapter_id?: number | null;
  start_offset?: number | null;
  end_offset?: number | null;
  source_version?: number | null;
  save_to_public?: boolean;
};

export type AISplitProposal = {
  proposal_id: number;
  document_id: number;
  source_revision_id: number;
  chapter_id: number;
  chapters: Array<{ title: string; start_offset: number; end_offset: number; reason?: string }>;
  model_invocation_id: number;
};

export type SplitChapterCandidate = {
  index: number;
  title: string;
  start_line: number;
  end_line: number;
  start_offset: number;
  end_offset: number;
  word_count: number;
};

export type SplitPreview = {
  preview_token: string;
  revision_id: number;
  chapter_count: number;
  chapters: SplitChapterCandidate[];
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

export type SceneRecord = {
  id: number;
  project_id: number;
  chapter_id: number;
  parent_scene_id: number | null;
  scene_index: number;
  title: string;
  original_start_offset: number;
  original_end_offset: number;
  original_text: string;
  source_version: number;
  boundary_reasons: string[];
  boundary_status: 'proposed' | 'confirmed' | 'adjusted';
  scene_type: string;
  user_confirmed: boolean;
  confirmed_at: string | null;
};

export type PromptDefinitionKind = 'master' | 'workflow_task' | 'common_task';

export type PromptDefinition = {
  id: number;
  name: string;
  description: string;
  kind: PromptDefinitionKind;
  workflow_key: CreativeStrategy | null;
  task_key: string | null;
  content: string;
  input_description: string;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

export type PromptDefinitionWrite = Omit<PromptDefinition, 'id' | 'created_at' | 'updated_at'>;

export type ProjectMasterPrompt = {
  project_id: number;
  content: string;
  source_prompt_definition_id: number | null;
  updated_at: string;
};

export type CreativeStrategy = 'plot_adjust' | 'expansion' | 'plot_rewrite';
export type ChapterSummary = { chapter_id: number; plot_summary: string; main_characters: string; key_events: string; source_hash: string; updated_at: string };
export type ChapterCreativeIntent = { chapter_id: number; strategy: CreativeStrategy; user_instruction: string; updated_at: string };
export type ChapterSpecialAnalysis = { chapter_id: number; strategy: CreativeStrategy; source_outline: string; target_outline: string; source_hash: string; updated_at: string };
export type ChapterStyleContext = { chapter_id: number; strategy: CreativeStrategy; style_mode: 'source_auto' | 'selected_author_style'; source_scope: 'document' | 'chapter'; author_style_material_id: number | null; author_style_material_version: number | null; style_snapshot: Record<string, unknown>; extraction_settings_snapshot: Record<string, unknown>; generated_guidance: string; source_hash: string; created_at: string };
export type ChapterWriting = { id: number; chapter_id: number; strategy: CreativeStrategy; writing_plan: Array<Record<string, unknown>>; result_text: string; created_chapter_id: number | null; source_hash: string; status: 'draft' | 'reviewed' | 'confirmed'; updated_at: string };
export type SceneBoundaryItem = {
  start_offset: number;
  end_offset: number;
  title: string;
  reasons: string[];
};

export type SceneFactLedger = {
  scene_id: number;
  events: unknown[];
  characters_present: string[];
  character_changes: Record<string, unknown>;
  location: string;
  time_state: Record<string, unknown>;
  objects: Record<string, unknown>;
  knowledge_states: Record<string, unknown>;
  relationship_changes: unknown[];
  open_threads: unknown[];
  resolved_threads: unknown[];
  foreshadowing: unknown[];
  required_start_state: Record<string, unknown>;
  required_end_state: Record<string, unknown>;
  [key: string]: unknown;
};

export type CharacterStoryState = {
  id: number;
  scene_id: number;
  character_name: string;
  state: Record<string, unknown>;
};

export type PromptContextBlock = {
  key: string;
  content: string;
  priority: number;
  required: boolean;
  token_count: number;
  source_type: string;
  source_id: string;
  included: boolean;
  decision: string;
};

export type PromptCompilation = {
  id: number;
  stage: string;
  max_input_tokens: number;
  reserved_output_tokens: number;
  used_input_tokens: number;
  blocks: PromptContextBlock[];
  context: Record<string, unknown>;
};

export type StorySkeletonVersion = {
  skeleton_id: number;
  version_id: number;
  version: number;
  status: 'draft' | 'confirmed';
  nodes: Record<string, unknown>[];
  structured?: StructuredSkeleton | null;
};

export type PreferredStorySkeleton = {
  format: 'structured' | 'legacy_summary' | 'missing';
  skeleton_id?: number;
  version?: number;
  version_id?: number;
  status?: 'draft' | 'confirmed';
  structured?: StructuredSkeleton;
  legacy_summary?: string;
};

export type BranchSceneRecord = {
  id: number;
  branch_id: number;
  branch_chapter_id: number;
  sequence_index: number;
  scene_index: number;
  title: string;
  current_version: number;
  version_id: number;
  generated_text: string;
  facts_after: WorkflowObject;
};

export type BranchChapterRecord = {
  id: number;
  branch_id: number;
  sequence_index: number;
  title: string;
  current_version: number;
  version_id: number;
  version: number;
  summary: string;
  facts_before: WorkflowObject;
  facts_after: WorkflowObject;
  scenes: BranchSceneRecord[];
};

export type RewriteMode = 'skeleton_rewrite' | 'expansion';

export type RewritePlan = {
  id: number;
  project_id: number;
  chapter_id: number;
  scene_id: number;
  mode: RewriteMode;
  skeleton_version_id: number;
  status: 'draft' | 'confirmed' | 'executed';
  plan: Record<string, unknown>;
  material_mappings: Record<string, unknown>[];
  user_instruction: string;
  created_at: string;
  updated_at: string;
};

export type RetrievalResult = {
  retrieval_run_id: number;
  retrieval_type: 'manual' | 'structure' | 'keyword' | 'relationship' | 'vector';
  source_type: string;
  source_id: string;
  source_location: string;
  relevance_reason: string;
  confidence: number;
  included_in_prompt: boolean;
  token_count: number;
  content: string;
  rank_order: number;
};
