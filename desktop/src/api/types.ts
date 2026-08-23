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

export type Chapter = {
  id: number;
  project_id: number;
  index: number;
  title: string;
  original_text: string;
  rewritten_text: string | null;
  word_count: number;
  status: string;
  workflow_stage: CreativeWorkflowStage;
};

export type CreativeWorkflowStage = 'not_started' | 'summary' | 'direction' | 'special_analysis' | 'style' | 'writing' | 'review' | 'confirmed';
export type CreativeStrategy = 'plot_adjust' | 'expansion' | 'plot_rewrite';
export type ChapterSummary = { chapter_id: number; plot_summary: string; main_characters: string; key_events: string; source_hash: string; updated_at: string };
export type ChapterCreativeIntent = { chapter_id: number; strategy: CreativeStrategy; user_instruction: string; updated_at: string };
export type ChapterSpecialAnalysis = { chapter_id: number; strategy: CreativeStrategy; source_outline: string; target_outline: string; source_hash: string; updated_at: string };
export type ChapterStyleContext = { chapter_id: number; strategy: CreativeStrategy; style_mode: 'source_auto' | 'selected_author_style'; source_scope: 'document' | 'chapter'; author_style_material_id: number | null; author_style_material_version: number | null; style_snapshot: Record<string, unknown>; extraction_settings_snapshot: Record<string, unknown>; generated_guidance: string; source_hash: string; created_at: string };
export type ChapterWriting = { id: number; chapter_id: number; strategy: CreativeStrategy; writing_plan: Array<Record<string, unknown>>; result_text: string; created_chapter_id: number | null; source_hash: string; status: 'draft' | 'reviewed' | 'confirmed'; updated_at: string };
export type ChapterWorkflowState = { chapter_id: number; current_stage: CreativeWorkflowStage; source_base_kind: 'original' | 'rewrite_version'; source_base_version_id: number | null; source_hash: string; source_changed: boolean; summary: ChapterSummary | null; direction: ChapterCreativeIntent | null; special_analysis: ChapterSpecialAnalysis | null; style: ChapterStyleContext | null; writing: ChapterWriting | null; updated_at: string };

export type ChapterSplitOptions = {
  mode: 'auto' | 'simple' | 'regex';
  line_prefix?: string;
  number_style?: 'mixed' | 'arabic' | 'chinese';
  title_suffixes?: string[];
  extra_title_regex?: string | null;
  custom_regex?: string;
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
  chapters: Array<{ index: number; title: string; word_count: number; start_line: number | null; end_line: number | null }>;
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
export type ModelWrite = Omit<ModelConfig, 'id' | 'has_api_key'> & { api_key?: string | null };
export type ModelTestResult = { ok: boolean; message: string; elapsed_ms: number | null };

export type PromptSlotKey = 'global_system' | 'chapter_summary' | 'plot_adjust' | 'expansion' | 'plot_rewrite' | 'writing';
export type PromptSlot = { slot_key: PromptSlotKey; content: string; updated_at: string };

export type StyleDetailLevel = 'brief' | 'standard' | 'detailed';
export type MaterialAITask = 'author_style_extraction';
export type MaterialAIDimension = { id: string; name: string; requirement: string };
export type AuthorStyleContent = Record<string, unknown> & { schema_version?: number; work?: string; overall_style?: string; dimensions?: Array<{ id: string; name: string; analysis: string; features: string[]; examples: string[] }> };
export type Material = {
  id: number;
  name: string;
  description: string;
  detail_level: StyleDetailLevel;
  raw_text: string;
  content: AuthorStyleContent;
  sort_order: number;
  version: number;
  created_at: string;
  updated_at: string;
  category_ids: number[];
  categories: string[];
};
export type MaterialUpdate = { name: string; description: string; detail_level: StyleDetailLevel; content: AuthorStyleContent; sort_order: number };
export type MaterialAISettings = { task_type: MaterialAITask; model_id: number | null; detail_level: StyleDetailLevel; extraction_rules: string; base_instruction: string; dimensions: MaterialAIDimension[]; extra_requirements: string; prompt_preview: string; updated_at: string };
export type MaterialExtractionCandidate = { candidate_id: string; name: string; description: string; content: AuthorStyleContent };
export type MaterialExtractionPreview = { preview_token: string; candidates: MaterialExtractionCandidate[] };
export type MaterialExtractionApplyResult = { created: Array<{ candidate_id: string; material_id: number | null; error?: string | null }>; errors: Array<{ candidate_id: string; material_id?: number | null; error: string | null }> };

export type DocumentCategory = { id: number; name: string; normalized_name: string; sort_order: number; resource_count: number };
export type LibraryDocument = { id: number; title: string; author: string | null; description: string | null; source_filename: string; source_format: string; storage_path: string; source_size_bytes: number; stored_size_bytes: number; chapter_count: number; word_count: number; status: string; favorite: boolean; is_project_document: boolean; category_ids: number[]; categories: string[]; project_ids: number[]; created_at: string; updated_at: string };
export type LibraryDocumentImportResult = { document: LibraryDocument; created: boolean; storage_format: string };
export type DocumentLibrarySettings = { storage_path: string };
export type LibraryDocumentRevision = { id: number; document_id: number; revision_number: number; revision_type: string; storage_path: string; template_id: number | null; parent_revision_id: number | null; created_at: string };
export type LibraryDocumentChapter = { id: number; revision_id: number; index: number; title: string; start_line: number | null; end_line: number | null; start_offset: number | null; end_offset: number | null; word_count: number; volume_id: number | null };
export type LibraryDocumentVolume = { id: number; revision_id: number; index: number; title: string; start_offset: number; end_offset: number; word_count: number; chapters: LibraryDocumentChapter[] };
export type LibraryDocumentDirectory = { volumes: LibraryDocumentVolume[]; unassigned_chapters: LibraryDocumentChapter[] };
export type LibraryDocumentContent = { document_id: number; revision_id: number; chapter_id: number | null; title: string; text: string; body_text: string; section_start_offset: number; body_start_offset: number; end_offset: number; start_offset: number };
export type LibraryDocumentDraft = { id: number; document_id: number; chapter_id: number | null; base_revision_id: number; title: string; text: string; updated_at: string };
export type LibraryDocumentCleanupResult = { document: LibraryDocument; revision: LibraryDocumentRevision; created: boolean };
export type LibraryDocumentCreateChapterResult = LibraryDocumentCleanupResult & { created_chapter_id: number };
export type LibraryDocumentExportResult = { ok: boolean; format: string; output_path: string };
export type LibraryDocumentAICleanupResult = { document: LibraryDocument; revision: LibraryDocumentRevision | null; created: boolean; chapters: Array<{ chapter_id: number; title: string; status: 'success' | 'failed'; error: string | null }> };
export type AISplitProposal = { proposal_id: number; document_id: number; source_revision_id: number; chapter_id: number; chapters: Array<{ title: string; start_offset: number; end_offset: number; reason: string }> };
