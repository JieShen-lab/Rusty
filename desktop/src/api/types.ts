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
  tags: string[];
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

export type ResourceTag = {
  id: number;
  name: string;
  normalized_name: string;
  sort_order: number;
  resource_count: number;
  tag_group?: 'general' | 'applicable_scene';
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

export type SourceRange = {
  start: number;
  end: number;
};

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

export type BranchCreateRequest = {
  name: string;
  branch_mode: 'open_continuation' | 'fork' | 'fork_and_rejoin';
  parent_branch_id?: number | null;
  start_anchor: StoryAnchor;
  return_anchor?: StoryAnchor | null;
  base_source_version_id?: number | null;
  downstream_strategy?: 'replace' | 'reference' | 'rejoin' | null;
};

export type SeamProposal = {
  id?: number | null;
  seam_kind: 'entry' | 'return';
  operation: 'keep' | 'insert_before' | 'insert_after' | 'replace_range';
  original_text: string;
  proposed_text: string;
  source_range: SourceRange;
  source_hash: string;
  reason: string;
  status: 'draft' | 'confirmed' | 'rejected';
  source_anchor?: StoryAnchor | null;
  source_version_id?: number | null;
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

export type PlotGenerationStartRequest = {
  project_id: number;
  generation_mode: 'bounded_insert' | 'open_continuation' | 'fork' | 'fork_and_rejoin';
  start_anchor: StoryAnchor;
  return_anchor?: StoryAnchor | null;
  user_direction: string;
  selected_character_ids?: number[];
  selected_material_ids?: number[];
  style_profile_id?: number | null;
  parent_branch_id?: number | null;
  branch_name?: string;
  range_operation?: 'insert_between' | 'replace_range';
};

export type PlotGenerationSeamConfirmRequest = {
  reviews: Array<{
    seam_id: number;
    decision: 'confirmed' | 'rejected';
    proposed_text?: string | null;
  }>;
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
  seams: SeamProposal[] | WorkflowObject;
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
};

export type ProseRewritePlanRequest = {
  project_id: number;
  chapter_id: number;
  source_skeleton: StructuredSkeleton;
  preservation_policy: WorkflowObject;
  style_profile_id?: number | null;
  user_direction?: string;
};

export type ProseRewriteExecuteRequest = {
  auto_repair?: boolean;
};

export type ProseRewriteRun = {
  id: number;
  project_id: number;
  chapter_id: number;
  status: string;
  source_skeleton: StructuredSkeleton;
  preservation_policy: WorkflowObject;
  target_skeleton: StructuredSkeleton;
  rewrite_plan: WorkflowObject;
  rewritten_text: string | null;
  issues: WorkflowObject[];
  operation_type: 'prose_rewrite';
  created_at: string;
  updated_at: string;
};

export type CanonChangeScanRequest = {
  project_id: number;
  old_fact: WorkflowObject;
  new_fact: WorkflowObject;
  effective_order: number;
  branch_id?: number | null;
};

export type CanonPatchReviewRequest = {
  decision: 'accepted' | 'rejected' | 'edited' | 'skipped';
  replacement_text?: string | null;
};

export type CanonPatch = {
  id: number;
  run_id: number;
  route_kind: string;
  target_id: number;
  source_range: SourceRange;
  source_hash: string;
  original_text: string;
  replacement_text: string;
  impact_type: string;
  reason: string;
  confidence: number;
  evidence: unknown[];
  requires_confirmation: boolean;
  status: string;
};

export type CanonChangeRun = {
  id: number;
  project_id: number;
  branch_id: number | null;
  effective_order: number;
  status: string;
  old_fact: WorkflowObject;
  new_fact: WorkflowObject;
  fact_ledger: WorkflowObject;
  consistency_issues: WorkflowObject[];
  patches: CanonPatch[];
  operation_type: 'canon_change';
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
  identity: string;
  age: string;
  setting_text: string;
  custom_fields: CharacterCustomField[];
  raw_text: string;
  analysis_status: AnalysisStatus;
  cover_path: string | null;
  cover_updated_at: string | null;
  tags: string[];
  category_ids: number[];
  categories: string[];
  source_summary: CharacterSourceSummary;
  created_at: string;
  updated_at: string;
};

export type CharacterSourceSummary = {
  kind:
    | 'manual'
    | 'document_selection'
    | 'project_selection'
    | 'file_import'
    | 'ai_extraction'
    | 'public_copy'
    | 'project_copy';
  label: string;
  document_id?: number | null;
  chapter_id?: number | null;
  project_id?: number | null;
  source_card_id?: number | null;
};

export type CharacterCategory = {
  id: number;
  name: string;
  normalized_name: string;
  sort_order: number;
  resource_count: number;
};

export type CharacterProjectSummary = {
  project_id: number;
  project_name: string;
  character_count: number;
  updated_at: string;
};

export type CharacterLibrarySelection =
  | { kind: 'project'; projectId: number }
  | { kind: 'public-all' }
  | { kind: 'public-category'; categoryId: number };

export type CharacterQueryState = {
  query: string;
  activeTagId: number | null;
  analysisStatus: 'all' | 'unanalyzed' | 'analyzed';
  untaggedOnly: boolean;
};

export type CharacterCustomField = {
  id: string;
  label: string;
  value: string;
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
  identity?: string;
  age?: string;
  setting_text?: string;
  custom_fields?: CharacterCustomField[];
  raw_text?: string;
  analysis_status?: AnalysisStatus;
  tag_ids?: number[];
};

export type CharacterExtractionSettings = {
  model_id: number | null;
  detail_level: StyleDetailLevel;
  max_candidates: number;
  extract_all_characters: boolean;
  generate_tags: boolean;
  generate_appearance: boolean;
  generate_relationships: boolean;
  generate_personality: boolean;
  generate_speech_style: boolean;
  generate_action_constraints: boolean;
  generate_anti_ooc_rules: boolean;
  generate_abilities_background: boolean;
  custom_requirements: string;
  system_prompt: string;
  prompt_preview: string;
};

export type CharacterExtractionCandidate = {
  candidate_id: string;
  selected: boolean;
  name: string;
  aliases: string[];
  description: string;
  identity: string;
  age: string;
  setting_text: string;
  relationship_notes: string;
  personality: string;
  speech_style: string;
  action_constraints: string;
  anti_ooc_rules: string;
  profile: Record<string, unknown>;
  custom_fields: CharacterCustomField[];
  suggested_tags: string[];
  confirmed_tags?: string[];
  evidence_summary: string;
};

export type CharacterExtractionPreview = {
  preview_token: string;
  expires_at: string;
  source_summary: CharacterSourceSummary;
  candidates: CharacterExtractionCandidate[];
};

export type CharacterExtractionApplyResult = {
  created: Array<{ candidate_id: string; card_id: number | null; error: string | null }>;
  errors: Array<{ candidate_id: string; card_id: number | null; error: string | null }>;
};

export type AnalysisStatus = 'unanalyzed' | 'analyzed';
export type MaterialType = 'scene_reference' | 'plot_skeleton';
export type MaterialScope = 'public' | 'project';
export type MaterialTagGroup = 'general' | 'applicable_scene';
export type MaterialAITask =
  | 'narrative_to_plot_skeleton'
  | 'plot_text_to_normalized_skeleton'
  | 'source_text_to_scene_material';

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
  content: Record<string, unknown>;
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
  tags: string[];
  general_tags: string[];
  applicable_scene_tags: string[];
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
  content: Record<string, unknown>;
  analysis_status?: AnalysisStatus;
  source_metadata?: Record<string, unknown>;
  import_metadata?: Record<string, unknown>;
  timeline_start_chapter?: number | null;
  timeline_end_chapter?: number | null;
  sort_order?: number;
  tag_ids?: number[];
  category_ids?: number[];
};

export type MaterialUpdate = Omit<MaterialWrite, 'material_type' | 'scope' | 'project_id' | 'source_metadata' | 'import_metadata'>;

export type ProjectMaterialFilter = {
  project_id: number;
  material_type: MaterialType;
  match_mode: 'any' | 'all';
  tag_ids: number[];
  manual_material_ids: number[];
  include_scene_keywords: boolean;
  include_applicable_scene_tags: boolean;
};

export type MaterialAISettings = {
  task_type: MaterialAITask;
  model_id: number | null;
  detail_level: StyleDetailLevel;
  max_candidates: number;
  system_prompt: string;
  user_prompt_template: string;
  analysis_dimensions: string[];
  generate_general_tags: boolean;
  generate_applicable_scene_tags: boolean;
  custom_requirements: string;
  updated_at: string;
};

export type MaterialExtractionCandidate = {
  candidate_id: string;
  material_type: MaterialType;
  selected: boolean;
  name: string;
  description: string;
  content: Record<string, unknown>;
  suggested_general_tags: string[];
  suggested_applicable_scene_tags: string[];
  confirmed_general_tags?: string[];
  confirmed_applicable_scene_tags?: string[];
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
  tag_ids?: number[];
};

export type AISplitProposal = {
  proposal_id: number;
  document_id: number;
  source_revision_id: number;
  chapters: Array<{ title: string; start_offset: number; end_offset: number; reason: string }>;
  model_invocation_id: number;
};

export type SceneWorkflowRun = {
  id: number;
  project_id: number;
  chapter_id: number;
  scene_id: number;
  mode: RewriteMode;
  status: string;
  skeleton_id: number | null;
  skeleton_version_id: number | null;
  plan_id: number | null;
  current_stage: string;
  error_message: string | null;
  skeleton_nodes?: Record<string, unknown>[];
  plan?: Record<string, unknown> | null;
  material_mappings?: Record<string, unknown>[];
};

export type SceneWorkflowExecutePayload = {
  user_instruction?: string;
  model_id?: number | null;
  character_ids?: number[];
  plot_skeleton_material_ids?: number[];
  scene_reference_ids?: number[];
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
  character_card_id: number | null;
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
