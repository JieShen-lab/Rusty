import { expect, test, type Page } from '@playwright/test';

const projects = [
  { id: 1, name: '示例工程', author: '', status: 'ready', source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-29 12:00:00' },
  { id: 2, name: '北境工程', author: '', status: 'ready', source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-28 12:00:00' },
  { id: 3, name: '旧城工程', author: '', status: 'ready', source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-27 12:00:00' },
  { id: 4, name: '海港工程', author: '', status: 'ready', source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-26 12:00:00' },
];
const tags = [{ id: 1, name: '主角', normalized_name: '主角', sort_order: 0, resource_count: 1 }];
const characterCategories = [
  { id: 31, name: '主要角色', normalized_name: '主要角色', sort_order: 0, resource_count: 1 },
  { id: 32, name: '历史人物', normalized_name: '历史人物', sort_order: 1, resource_count: 1 },
];
const publicCharacter = {
  id: 1, name: '林舟', aliases: [], description: '沉着的调查者', priority: 50, is_main: true, relationship_notes: '', personality: '', speech_style: '', action_constraints: '', anti_ooc_rules: '', profile: {}, source_metadata: {}, import_metadata: {}, scope: 'public' as const, project_id: null, source_character_card_id: null, source_version: null, version: 1, sort_order: 0, identity: '调查者', age: '', setting_text: '林舟习惯先观察再行动。他对旧城历史十分熟悉，并且不轻易表露情绪。', custom_fields: [], raw_text: '林舟推门而入。', analysis_status: 'unanalyzed' as const, cover_path: null, cover_updated_at: null, tags: ['主角'], category_ids: [31, 32], categories: ['主要角色', '历史人物'], source_summary: { kind: 'document_selection' as const, label: '《示例长篇》 · 第一章', document_id: 1, chapter_id: 1 }, created_at: '', updated_at: '',
};
const projectCharacter = {
  ...publicCharacter,
  id: 2,
  name: '工程林舟',
  scope: 'project' as const,
  project_id: 1,
  source_character_card_id: 1,
  category_ids: [],
  categories: [],
  source_summary: { kind: 'public_copy' as const, label: '公共角色“林舟”', project_id: 1, source_card_id: 1 },
};
const materials = [
  { id: 1, material_type: 'scene_reference', scope: 'public', project_id: null, project_name: null, name: '雨夜追逐', description: '雨夜动作参考', detail_level: 'standard', raw_text: '', content: { schema_version: 1, summary: '雨夜追逐', key_beats: [{ id: 'beat-fixed', title: '跃上屋顶', summary: '快速追逐', evidence_summary: '屋顶湿滑', unknown: 'keep' }], actions: [], environment: [], sensory: [], writing_guidance: [], source_cues: [], avoidances: [], applicable_conditions: [], legacy_extra: { keep: true } }, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [] },
  { id: 2, material_type: 'plot_skeleton', scope: 'public', project_id: null, project_name: null, name: '误会解除', description: '事件骨架', detail_level: 'standard', raw_text: '', content: { schema_version: 1, premise: '误会造成分离', stages: [{ id: 'stage-fixed', title: '误会发生', summary: '两人争执', causes: ['错误线索'], effects: ['暂时分离'], characters: ['林舟'], locations: ['旧城'], must_keep_details: ['钥匙'], forbidden_changes: ['不能提前和解'], unknown: 'keep' }], conflicts: [], turning_points: [], climax: { id: 'climax', title: '真相', summary: '发现真相' }, resolution: { id: 'resolution', title: '和解', summary: '解除误会' }, hooks: [], legacy_extra: { keep: true } }, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [] },
];
const baseDocumentItems = [
  { id: 1, title: '示例长篇', author: '作者', description: null, source_filename: 'novel.txt', source_format: 'txt', storage_path: 'D:/Rusty/novel-v2.txt', source_size_bytes: 100, stored_size_bytes: 100, chapter_count: 1, word_count: 16, status: 'ready', favorite: false, tags: ['长篇'], is_project_document: false, category_ids: [11, 12], categories: ['研究', '待整理'], project_ids: [], created_at: '2026-07-29 10:00:00', updated_at: '' },
  { id: 2, title: '工程原稿', author: '工程作者', description: null, source_filename: 'project.txt', source_format: 'txt', storage_path: 'D:/Rusty/project-v1.txt', source_size_bytes: 80, stored_size_bytes: 80, chapter_count: 1, word_count: 12, status: 'ready', favorite: false, tags: ['长篇'], is_project_document: true, category_ids: [11], categories: ['研究'], project_ids: [1], created_at: '2026-07-28 10:00:00', updated_at: '' },
  { id: 3, title: '普通资料', author: '资料作者', description: null, source_filename: 'reference.txt', source_format: 'txt', storage_path: 'D:/Rusty/reference-v1.txt', source_size_bytes: 60, stored_size_bytes: 60, chapter_count: 1, word_count: 10, status: 'ready', favorite: false, tags: [], is_project_document: false, category_ids: [11], categories: ['研究'], project_ids: [], created_at: '2026-07-27 10:00:00', updated_at: '' },
];
const documentTags = [{ id: 21, name: '长篇', normalized_name: '长篇', sort_order: 0, resource_count: 2 }];
const documentCategories = [
  { id: 11, name: '研究', normalized_name: '研究', sort_order: 0, resource_count: 3 },
  { id: 12, name: '待整理', normalized_name: '待整理', sort_order: 1, resource_count: 1 },
];

const sceneHistory = [{ id: 8, version: 1, revision_kind: 'rewrite', parent_version_id: null as number | null, created_at: '2026-07-28', rewritten_text: '林舟推门而入。' }];
let workflowPlanRequests: Array<Record<string, unknown>> = [];
let tagAssignmentRequests: Array<{ documentId: number; tagId: number; selected: boolean }> = [];

async function mockApi(page: Page) {
  let skeletonNodes: Array<Record<string, unknown>> = [{ id: 'n1', event: '发现钥匙' }];
  let documentItems = baseDocumentItems.map((item) => ({ ...item, tags: [...item.tags], category_ids: [...item.category_ids], categories: [...item.categories] }));
  let documentDraft: { id: number; document_id: number; chapter_id: number | null; base_revision_id: number; title: string; text: string; updated_at: string } | null = null;
  let documentRevisionNumber = 1;
  let documentBody = '林舟推门而入，看见桌上的钥匙。';
  let materialItems = materials.map((item) => ({ ...item, content: structuredClone(item.content) }));
  let documentChapterTitle = '第一章';
  let volumeTitle = '第七卷 雨夜';
  let extraChapter: { id: number; document_id: number; revision_id: number; index: number; title: string; start_line: number; end_line: number; start_offset: number; end_offset: number; word_count: number; volume_id: number } | null = null;
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = [];
    if (path === '/api/projects') body = projects;
    else if (path === '/api/character-tags' || path === '/api/material-tags') body = tags;
    else if (path === '/api/character-categories') body = characterCategories;
    else if (path === '/api/character-projects/summary') body = projects.map((project, index) => ({ project_id: project.id, project_name: project.name, character_count: index === 0 ? 1 : 0, updated_at: project.updated_at }));
    else if (path === '/api/models') body = [{ id: 1, display_name: '测试模型', provider: 'openai_compatible', base_url: '', model_name: 'test', is_default: true, created_at: '', updated_at: '' }];
    else if (path === '/api/character-extraction/settings') body = { model_id: 1, detail_level: 'standard', max_candidates: 8, extract_all_characters: true, generate_tags: true, generate_appearance: true, generate_relationships: true, generate_personality: true, generate_speech_style: true, generate_action_constraints: true, generate_anti_ooc_rules: true, generate_abilities_background: true, custom_requirements: '', system_prompt: '不得补全无证据事实', prompt_preview: '不得补全无证据事实' };
    else if (path === '/api/characters/extract/preview') {
      const request = route.request().postDataJSON() as { source_metadata?: Record<string, unknown> };
      const metadata = request.source_metadata ?? {};
      body = { preview_token: 'preview-test', expires_at: '2030-01-01T00:00:00Z', source_summary: metadata.document_title ? { kind: 'document_selection', label: `《${metadata.document_title}》 · ${metadata.chapter_title}`, document_id: metadata.document_id, chapter_id: metadata.chapter_id } : { kind: 'ai_extraction', label: 'AI 文本提取' }, candidates: [{ candidate_id: 'alice', selected: true, name: '林舟', aliases: [], description: '调查者', identity: '调查者', age: '', setting_text: '', relationship_notes: '寻找阿音', personality: '冷静', speech_style: '', action_constraints: '', anti_ooc_rules: '', profile: {}, custom_fields: [], suggested_tags: ['主角', '冷静'], evidence_summary: '林舟主动调查钥匙。' }, { candidate_id: 'ayin', selected: true, name: '阿音', aliases: [], description: '线索提供者', identity: '', age: '', setting_text: '', relationship_notes: '', personality: '', speech_style: '', action_constraints: '', anti_ooc_rules: '', profile: {}, custom_fields: [], suggested_tags: [], evidence_summary: '阿音递出钥匙。' }] };
    }
    else if (path === '/api/characters/extract/apply') body = { created: [{ candidate_id: 'alice', card_id: 8, error: null }, { candidate_id: 'ayin', card_id: 9, error: null }], errors: [] };
    else if (path === '/api/projects/1/characters') body = { character_cards: [projectCharacter] };
    else if (path === '/api/projects/1/materials') body = materials.filter((item) => !url.searchParams.get('material_type') || item.material_type === url.searchParams.get('material_type')).map((item) => ({
      ...item,
      general_tags: item.tags,
      applicable_scene_tags: [],
      category_ids: [],
      categories: [],
      source_summary: { kind: 'manual', label: '本地创建' },
    }));
    else if (/^\/api\/projects\/\d+\/characters$/.test(path)) body = { character_cards: [] };
    else if (path === '/api/characters') body = url.searchParams.has('category_id') ? [publicCharacter] : [publicCharacter];
    else if (path === '/api/material-categories') body = [];
    else if (path === '/api/material-ai-settings') body = [
      { task_type: 'narrative_to_plot_skeleton', model_id: 1, detail_level: 'standard', max_candidates: 6, generate_general_tags: true, generate_applicable_scene_tags: false, analysis_dimensions: ['premise', 'stages'], user_prompt_template: '整理剧情', custom_requirements: '', system_prompt: '只使用来源证据。', updated_at: '' },
      { task_type: 'plot_text_to_normalized_skeleton', model_id: 1, detail_level: 'standard', max_candidates: 6, generate_general_tags: true, generate_applicable_scene_tags: false, analysis_dimensions: ['premise', 'stages'], user_prompt_template: '规范剧情', custom_requirements: '', system_prompt: '不添加新情节。', updated_at: '' },
      { task_type: 'source_text_to_scene_material', model_id: 1, detail_level: 'standard', max_candidates: 6, generate_general_tags: true, generate_applicable_scene_tags: true, analysis_dimensions: ['summary', 'key_beats'], user_prompt_template: '整理场景', custom_requirements: '', system_prompt: '只整理场景写法。', updated_at: '' },
    ];
    else if (path === '/api/material-extractions/preview') {
      const request = route.request().postDataJSON() as { source_metadata?: Record<string, unknown> };
      const metadata = request.source_metadata ?? {};
      body = {
      preview_token: 'material-preview',
      expires_at: '2030-01-01T00:00:00Z',
      task_type: 'source_text_to_scene_material',
      material_type: 'scene_reference',
      source_summary: metadata.document_title ? { kind: 'document_selection', label: `《${metadata.document_title}》 · ${metadata.chapter_title}`, document_id: metadata.document_id, chapter_id: metadata.chapter_id } : { kind: 'pasted_text', label: '粘贴文本' },
      prompt_snapshot: { task_type: 'source_text_to_scene_material' },
      candidates: [{
        candidate_id: 'scene-1', material_type: 'scene_reference', selected: true, name: '雨夜追逐', description: '雨夜动作参考',
        content: { schema_version: 1, summary: '雨夜追逐的动作与感官提示。', key_beats: [{ id: 'beat-1', title: '跃上屋顶', summary: '快速追逐', evidence_summary: '湿滑屋顶' }] },
        suggested_general_tags: ['动作'], suggested_applicable_scene_tags: ['雨夜'],
        evidence: [{ quote: '雨夜追逐' }], evidence_summary: '原文明确包含雨夜和追逐。',
        confidence: 0.9, warnings: [],
      }],
      };
    }
    else if (path === '/api/material-extractions/apply') body = { created: [{ candidate_id: 'scene-1', material_id: 1, error: null }], errors: [] };
    else if (path === '/api/materials') body = materialItems.map((item) => ({
      ...item,
      general_tags: item.tags,
      applicable_scene_tags: [],
      category_ids: [],
      categories: [],
      source_summary: { kind: 'manual', label: '本地创建' },
    }));
    else if (/^\/api\/materials\/1\/analyze$/.test(path)) body = { material_id: 1, model_id: 1, invocation_id: 9, existing: {}, proposal: { summary: '模型分析摘要' } };
    else if (/^\/api\/materials\/1\/analysis\/apply$/.test(path)) body = { ...materials[0], analysis_status: 'analyzed', content: { summary: '模型分析摘要' } };
    else if (path === '/api/materials/import-json') body = { imported: [{ index: 0, id: 3, name: '导入场景', material_type: 'scene_reference' }], errors: [] };
    else if (/^\/api\/materials\/\d+$/.test(path)) {
      const materialId = Number(path.split('/').at(-1));
      const current = materialItems.find((item) => item.id === materialId);
      if (route.request().method() === 'POST' && current) {
        const request = route.request().postDataJSON() as Record<string, unknown>;
        materialItems = materialItems.map((item) => item.id === materialId
          ? { ...item, ...request, version: item.version + 1 }
          : item);
      }
      const updated = materialItems.find((item) => item.id === materialId) ?? current;
      body = updated ? {
        ...updated,
        general_tags: updated.tags,
        applicable_scene_tags: [],
        category_ids: [],
        categories: [],
        source_summary: { kind: 'manual', label: '本地创建' },
      } : {};
    }
    else if (path === '/api/documents') body = documentItems;
    else if (path === '/api/document-tags') body = documentTags;
    else if (path === '/api/document-categories') body = documentCategories;
    else if (/^\/api\/documents\/\d+\/tags\/\d+$/.test(path)) {
      const [, , , documentIdText, , tagIdText] = path.split('/');
      const documentId = Number(documentIdText);
      const tagId = Number(tagIdText);
      const selected = Boolean((route.request().postDataJSON() as { selected: boolean }).selected);
      tagAssignmentRequests.push({ documentId, tagId, selected });
      documentItems = documentItems.map((item) => item.id === documentId
        ? { ...item, tags: selected ? ['长篇'] : [] }
        : item);
      body = documentItems.find((item) => item.id === documentId);
    }
    else if (/^\/api\/documents\/\d+\/categories\/\d+$/.test(path)) {
      const [, , , documentIdText, , categoryIdText] = path.split('/');
      const documentId = Number(documentIdText);
      const categoryId = Number(categoryIdText);
      const selected = Boolean((route.request().postDataJSON() as { selected: boolean }).selected);
      documentItems = documentItems.map((item) => {
        if (item.id !== documentId) return item;
        const category = documentCategories.find((candidate) => candidate.id === categoryId);
        return {
          ...item,
          category_ids: selected ? [...new Set([...item.category_ids, categoryId])] : item.category_ids.filter((id) => id !== categoryId),
          categories: selected && category ? [...new Set([...item.categories, category.name])] : item.categories.filter((name) => name !== category?.name),
        };
      });
      body = documentItems.find((item) => item.id === documentId);
    }
    else if (path === '/api/document-library/settings') body = { storage_path: 'D:/Rusty', exists: true };
    else if (path === '/api/document-processing-templates') body = [];
    else if (path === '/api/documents/merge' && route.request().method() === 'POST') {
      const request = route.request().postDataJSON() as { title: string };
      const merged = { ...documentItems[0], id: 4, title: request.title, source_filename: 'merged.txt', storage_path: 'D:/Rusty/merged.txt', category_ids: [], categories: [], tags: [], chapter_count: 2 };
      documentItems = [...documentItems, merged];
      body = merged;
    }
    else if (/^\/api\/documents\/\d+\/revisions$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      body = Array.from({ length: documentRevisionNumber }, (_, index) => ({ id: documentId * 10 + index + 1, document_id: documentId, revision_number: index + 1, revision_type: index ? 'manual_edit' : 'import', storage_path: index + 1 === documentRevisionNumber ? documentItems.find((item) => item.id === documentId)?.storage_path : `D:/Rusty/novel-v${index + 1}.txt`, word_count: 16, created_at: '' })).reverse();
    }
    else if (/^\/api\/documents\/\d+\/chapters$/.test(path) && route.request().method() === 'POST') {
      const documentId = Number(path.split('/')[3]);
      const request = route.request().postDataJSON() as { title: string; text: string };
      documentRevisionNumber += 1;
      extraChapter = { id: 999, document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, index: 2, title: request.title, start_line: 3, end_line: 4, start_offset: 30, end_offset: 30 + request.title.length + request.text.length + 2, word_count: Array.from(request.title + request.text).filter((value) => !/\s/u.test(value)).length, volume_id: 701 };
      documentItems = documentItems.map((item) => item.id === documentId ? { ...item, chapter_count: 2 } : item);
      body = { document: documentItems.find((item) => item.id === documentId), revision: { id: documentId * 10 + documentRevisionNumber, document_id: documentId, revision_number: documentRevisionNumber, revision_type: 'manual_edit', storage_path: `D:/Rusty/novel-v${documentRevisionNumber}.txt`, template_id: null, parent_revision_id: documentId * 10 + documentRevisionNumber - 1, created_at: '' }, created: true, created_chapter_id: 999 };
    }
    else if (/^\/api\/documents\/\d+\/chapters$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      body = [{ id: documentId * 100 + documentRevisionNumber, document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, index: 1, title: documentChapterTitle, start_line: 1, end_line: 2, start_offset: 0, end_offset: documentBody.length + documentChapterTitle.length + 2, word_count: Array.from(documentChapterTitle + documentBody).filter((value) => !/\s/u.test(value)).length, volume_id: 701 }, ...(extraChapter ? [extraChapter] : [])];
    }
    else if (/^\/api\/documents\/\d+\/directory$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      const chapter = { id: documentId * 100 + documentRevisionNumber, document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, index: 1, title: documentChapterTitle, start_line: 1, end_line: 2, start_offset: 0, end_offset: documentBody.length + documentChapterTitle.length + 2, word_count: Array.from(documentChapterTitle + documentBody).filter((value) => !/\s/u.test(value)).length, volume_id: 701 };
      body = {
        volumes: [{ id: 701, revision_id: documentId * 10 + documentRevisionNumber, index: 1, title: volumeTitle, start_offset: 0, end_offset: 100, word_count: 24, chapters: [chapter, ...(extraChapter ? [extraChapter] : [])] }],
        unassigned_chapters: [],
      };
    }
    else if (/^\/api\/documents\/\d+\/volumes\/701$/.test(path)) {
      const request = route.request().postDataJSON() as { title: string };
      volumeTitle = request.title;
      documentRevisionNumber += 1;
      body = { document: documentItems[0], revision: { id: 99, document_id: 1, revision_number: documentRevisionNumber, revision_type: 'manual_edit', storage_path: 'D:/Rusty/novel-volume.txt', template_id: null, parent_revision_id: 11, created_at: '' }, created: true };
    }
    else if (/^\/api\/documents\/\d+\/draft$/.test(path) && route.request().method() === 'GET') {
      const requestedChapterId = url.searchParams.has('chapter_id') ? Number(url.searchParams.get('chapter_id')) : null;
      body = documentDraft?.chapter_id === requestedChapterId ? documentDraft : null;
    }
    else if (/^\/api\/documents\/\d+\/draft$/.test(path) && route.request().method() === 'PUT') {
      const documentId = Number(path.split('/')[3]);
      const request = route.request().postDataJSON() as { chapter_id: number | null; base_revision_id: number; title: string; text: string };
      documentDraft = { id: 99, document_id: documentId, chapter_id: request.chapter_id, base_revision_id: request.base_revision_id, title: request.title, text: request.text, updated_at: '2026-07-29 12:00:00' };
      body = documentDraft;
    }
    else if (/^\/api\/documents\/\d+\/draft\/commit$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      if (documentDraft) {
        documentBody = documentDraft.text;
        documentChapterTitle = documentDraft.title;
      }
      documentDraft = null;
      documentRevisionNumber += 1;
      body = { document: { ...documentItems.find((item) => item.id === documentId), word_count: Array.from(documentBody).filter((value) => !/\s/u.test(value)).length }, revision: { id: documentId * 10 + documentRevisionNumber, document_id: documentId, revision_number: documentRevisionNumber, revision_type: 'manual_edit', storage_path: `D:/Rusty/novel-v${documentRevisionNumber}.txt`, template_id: null, parent_revision_id: documentId * 10 + documentRevisionNumber - 1, created_at: '' }, created: true };
    }
    else if (/^\/api\/documents\/\d+\/content$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      const requestedChapterId = Number(url.searchParams.get('chapter_id'));
      body = requestedChapterId === 999 && extraChapter
        ? { document_id: documentId, revision_id: extraChapter.revision_id, chapter_id: 999, title: extraChapter.title, text: `${extraChapter.title}\n\n新增正文`, body_text: '新增正文', section_start_offset: extraChapter.start_offset, body_start_offset: extraChapter.start_offset + extraChapter.title.length + 2, start_offset: extraChapter.start_offset, end_offset: extraChapter.end_offset }
        : { document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, chapter_id: documentId * 100 + documentRevisionNumber, title: documentChapterTitle, text: `${documentChapterTitle}\n\n${documentBody}`, body_text: documentBody, section_start_offset: 0, body_start_offset: documentChapterTitle.length + 2, start_offset: 0, end_offset: documentBody.length + documentChapterTitle.length + 2 };
    }
    else if (path === '/api/projects/1') body = { id: 1, name: '示例工程', author: '', purpose: 'rewrite', status: 'ready', source_path: '', workspace_path: '', total_chapters: 1, total_words: 16, processed_chapters: 0, settings: { processing_mode: 'rewrite' }, created_at: '', updated_at: '' };
    else if (path === '/api/projects/1/chapters') body = [{ id: 1, project_id: 1, index: 1, title: '第一章', original_text: '林舟推门而入，看见桌上的钥匙。', rewritten_text: '', word_count: 16, status: 'pending', created_at: '', updated_at: '' }];
    else if (path === '/api/chapters/1') body = { chapter: { id: 1, project_id: 1, index: 1, title: '第一章', original_text: '林舟推门而入，看见桌上的钥匙。', rewritten_text: '', word_count: 16, status: 'pending', created_at: '', updated_at: '' }, ai_outputs: { plot_summary: '', expanded_plot: '', plot_characters: [], style_analysis: {}, reviewed_style_analysis: {}, style_analysis_status: '' } };
    else if (path.includes('/prompt-preview')) body = { ruleset_id: 'test', provenance: {}, expected_output: 'text', messages: [] };
    else if (path.includes('/generation-attempts')) body = [];
    else if (path === '/api/prompts' || path === '/api/analysis-prompts' || path === '/api/projects/1/export-plan') body = [];
    else if (path === '/api/projects/1/style-synthesis') body = { prompt_template_id: null };
    else if (path === '/api/chapters/1/scenes') body = [{ id: 1, project_id: 1, chapter_id: 1, parent_scene_id: null, scene_index: 1, title: '发现钥匙', original_start_offset: 0, original_end_offset: 16, original_text: '林舟推门而入，看见桌上的钥匙。', source_version: 1, boundary_reasons: [], boundary_status: 'confirmed', scene_type: 'discovery', user_confirmed: true, confirmed_at: '' }];
    else if (path === '/api/scenes/1/workflow/start') {
      const request = route.request().postDataJSON() as Record<string, unknown>;
      body = { id: 10, project_id: 1, chapter_id: 1, scene_id: 1, mode: request.mode, status: 'awaiting_skeleton_confirmation', skeleton_id: 5, skeleton_version_id: 6, plan_id: null, current_stage: 'skeleton', error_message: null, skeleton_nodes: skeletonNodes };
    }
    else if (path === '/api/story-skeletons/5/versions') {
      const request = route.request().postDataJSON() as { nodes?: Array<Record<string, unknown>> };
      skeletonNodes = request.nodes ?? skeletonNodes;
      body = { skeleton_id: 5, version_id: 9, version: 2, status: 'draft', nodes: skeletonNodes };
    }
    else if (path === '/api/story-skeletons/5/confirm') body = { skeleton_id: 5, version_id: 9, version: 2, status: 'confirmed', nodes: skeletonNodes };
    else if (path === '/api/scene-workflows/10/plan') {
      const request = route.request().postDataJSON() as Record<string, unknown>;
      workflowPlanRequests.push(request);
      body = { id: 10, project_id: 1, chapter_id: 1, scene_id: 1, mode: 'expansion', status: 'awaiting_plan_confirmation', skeleton_id: 5, skeleton_version_id: 9, plan_id: 7, current_stage: 'plan', error_message: null, plan: { sequence: ['发现钥匙'] } };
    }
    else if (path === '/api/rewrite-plans/7/confirm') body = { id: 7, project_id: 1, chapter_id: 1, scene_id: 1, mode: 'skeleton_rewrite', skeleton_version_id: 6, status: 'confirmed', plan: {}, material_mappings: [], user_instruction: '' };
    else if (path === '/api/scene-workflows/10/execute') body = { id: 10, project_id: 1, chapter_id: 1, scene_id: 1, mode: 'skeleton_rewrite', status: 'completed', skeleton_id: 5, skeleton_version_id: 6, plan_id: 7, current_stage: 'completed', error_message: null, rewrite_version_id: 8, consistency: { revision_required: false } };
    else if (path === '/api/scenes/1/rewrite-history') body = sceneHistory;
    else if (path === '/api/scenes/1/rewrite-history/8/restore') {
      if (!sceneHistory.some((item) => item.id === 9)) sceneHistory.unshift({ id: 9, version: 2, revision_kind: 'restore', parent_version_id: 8, created_at: '2026-07-28', rewritten_text: '林舟推门而入。' });
      body = { id: 9 };
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test.beforeEach(async ({ page }) => {
  workflowPlanRequests = [];
  tagAssignmentRequests = [];
  page.on('pageerror', (error) => console.error(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') console.error(`console: ${message.text()}`);
  });
  await mockApi(page);
});

test('素材库只显示两种类型且无时间线主视图', async ({ page }) => {
  await page.goto('/materials');
  await expect(page.getByText('场景素材', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('剧情骨架', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('大纲', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: '时间线' })).toHaveCount(0);
});

test('素材库使用统一范围、结构化新建与 AI 候选确认流程', async ({ page }) => {
  await page.goto('/materials');
  const sidebar = page.locator('.material-library-sidebar');
  await expect(sidebar.getByText('公共素材', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('工程素材', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('我的标签', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('全部内容', { exact: true })).toHaveCount(2);
  await expect(sidebar.getByText('最近导入', { exact: true })).toHaveCount(2);
  await expect(page.getByRole('button', { name: /AI 分析/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新建剧情骨架', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '新建场景素材', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '新建场景素材', exact: true }).click();
  await page.getByRole('tab', { name: '从来源整理' }).click();
  await page.getByLabel('来源文本').fill('雨夜里，人物沿着湿滑屋顶快速追逐。');
  await page.getByRole('button', { name: /生成候选/ }).click();
  await expect(page.getByRole('heading', { name: '确认候选素材' })).toBeVisible();
  await expect(page.getByText('原文明确包含雨夜和追逐。')).toBeVisible();
  await expect(page.getByText('雨夜', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认创建' }).click();
  await expect(page.getByText(/已创建 1 条素材/)).toBeVisible();
});

test('角色候选 Apply 失败后保留弹窗并允许修改重试', async ({ page }) => {
  let attempts = 0;
  await page.route('http://127.0.0.1:8765/api/characters/extract/apply', async (route) => {
    attempts += 1;
    await route.fulfill({
      contentType: 'application/json',
      status: 200,
      body: JSON.stringify(attempts === 1
        ? { created: [], errors: [{ candidate_id: 'ayin', card_id: null, error: '候选写入失败' }] }
        : { created: [{ candidate_id: 'alice', card_id: 8, error: null }, { candidate_id: 'ayin', card_id: 9, error: null }], errors: [] }),
    });
  });
  await page.goto('/characters');
  await page.getByRole('button', { name: /新建角色/ }).first().click();
  const dialog = page.getByRole('dialog', { name: '新建角色' });
  await dialog.getByRole('tab', { name: '从文本提取' }).click();
  await dialog.getByLabel('来源文本').fill('林舟接过阿音递来的钥匙。');
  await dialog.getByRole('button', { name: '生成候选角色' }).click();
  await dialog.getByRole('button', { name: /确认创建/ }).click();
  await expect(dialog).toBeVisible();
  await expect(dialog.getByRole('alert')).toContainText('候选写入失败');
  await dialog.getByLabel('角色名称').nth(1).fill('阿音（修正）');
  await dialog.getByRole('button', { name: /确认创建/ }).click();
  await expect(dialog).toHaveCount(0);
  expect(attempts).toBe(2);
});

test('素材候选 Apply 失败后保留候选并允许修改重试', async ({ page }) => {
  let attempts = 0;
  await page.route('http://127.0.0.1:8765/api/material-extractions/apply', async (route) => {
    attempts += 1;
    await route.fulfill({
      contentType: 'application/json',
      status: 200,
      body: JSON.stringify(attempts === 1
        ? { created: [], errors: [{ candidate_id: 'scene-1', material_id: null, error: '素材事务已回滚' }] }
        : { created: [{ candidate_id: 'scene-1', material_id: 1, error: null }], errors: [] }),
    });
  });
  await page.goto('/materials');
  await page.getByRole('button', { name: '新建场景素材', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByRole('tab', { name: '从来源整理' }).click();
  await dialog.getByLabel('来源文本').fill('雨夜里，人物沿着湿滑屋顶快速追逐。');
  await dialog.getByRole('button', { name: /生成候选/ }).click();
  await dialog.getByRole('button', { name: '确认创建' }).click();
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('素材事务已回滚');
  await dialog.getByLabel('名称').fill('雨夜追逐（修正）');
  await dialog.getByRole('button', { name: '确认创建' }).click();
  await expect(dialog).toHaveCount(0);
  expect(attempts).toBe(2);
});

test('剧情骨架详细字段可编辑保存并重新打开', async ({ page }) => {
  await page.goto('/materials');
  const plotSection = page.locator('.material-sidebar-section').filter({ hasText: '剧情骨架' });
  await plotSection.getByRole('button', { name: /全部内容/ }).click();
  await page.locator('.material-compact-card').filter({ hasText: '误会解除' }).dblclick();
  let editor = page.getByRole('dialog', { name: '编辑素材' });
  await editor.getByLabel('阶段 1 标题').fill('误会升级');
  await editor.getByLabel('阶段 1 原因').fill('错误线索\n隐瞒事实');
  await editor.getByLabel('阶段 1 禁止改动').fill('不能提前和解');
  await editor.getByRole('button', { name: '保存' }).click();
  await page.locator('.material-compact-card').filter({ hasText: '误会解除' }).dblclick();
  editor = page.getByRole('dialog', { name: '编辑素材' });
  await expect(editor.getByLabel('阶段 1 标题')).toHaveValue('误会升级');
  await expect(editor.getByLabel('阶段 1 原因')).toHaveValue('错误线索\n隐瞒事实');
  await expect(editor.getByLabel('阶段 1 禁止改动')).toHaveValue('不能提前和解');
});

test('场景素材详细字段可编辑保存并重新打开', async ({ page }) => {
  await page.goto('/materials');
  const sceneSection = page.locator('.material-sidebar-section').filter({ hasText: '场景素材' });
  await sceneSection.getByRole('button', { name: /全部内容/ }).click();
  await page.locator('.material-compact-card').filter({ hasText: '雨夜追逐' }).dblclick();
  let editor = page.getByRole('dialog', { name: '编辑素材' });
  await editor.getByLabel('关键节拍 1 标题').fill('跨过屋脊');
  await editor.getByLabel('关键节拍 1', { exact: true }).fill('人物在湿滑屋脊保持平衡');
  await editor.getByLabel('关键节拍 1 证据').fill('原文提及湿滑屋顶');
  await editor.getByRole('button', { name: '保存' }).click();
  await page.locator('.material-compact-card').filter({ hasText: '雨夜追逐' }).dblclick();
  editor = page.getByRole('dialog', { name: '编辑素材' });
  await expect(editor.getByLabel('关键节拍 1 标题')).toHaveValue('跨过屋脊');
  await expect(editor.getByLabel('关键节拍 1', { exact: true })).toHaveValue('人物在湿滑屋脊保持平衡');
  await expect(editor.getByLabel('关键节拍 1 证据')).toHaveValue('原文提及湿滑屋顶');
});

test('素材库侧栏无重复标题且 1440 深色主题无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto('/materials');
  await expect(page.locator('.material-library-sidebar').getByRole('heading', { name: '素材库' })).toHaveCount(0);
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await expect(page.getByRole('button', { name: '新建剧情骨架', exact: true })).toBeVisible();
});

test('角色库按工程和公共分类导航，标签只在右侧筛选且摘要保持紧凑', async ({ page }) => {
  await page.goto('/characters');
  const sidebar = page.locator('.character-range-panel');
  const detail = page.locator('.character-detail-panel');
  await expect(sidebar.getByText('工程角色', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('公共角色', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('我的分类', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('我的标签', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('系统筛选', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('收藏', { exact: true })).toHaveCount(0);
  await expect(sidebar.locator('select')).toHaveCount(0);
  await expect(sidebar.getByRole('button', { name: /示例工程/ })).toBeVisible();
  await expect(sidebar.getByRole('button', { name: /北境工程/ })).toBeVisible();
  await expect(sidebar.getByRole('button', { name: /旧城工程/ })).toBeVisible();
  await expect(sidebar.getByRole('button', { name: /海港工程/ })).toHaveCount(0);
  await expect(sidebar.getByRole('button', { name: /展开更多工程/ })).toBeVisible();

  await expect(detail.getByRole('button', { name: '主要角色', exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: '历史人物', exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: '主角', exact: true })).toBeVisible();
  await detail.getByRole('button', { name: '主角', exact: true }).click();
  await expect(page.getByText('标签：主角')).toBeVisible();
  await expect(detail.getByRole('button', { name: '主角', exact: true })).toBeVisible();
  await expect(page.getByText('林舟习惯先观察再行动。他对旧城历史十分熟悉，并且不轻易表露情绪。')).toBeVisible();
  await expect(page.getByText('来源版本', { exact: true })).toHaveCount(0);
  await expect(page.getByText('更新时间', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /AI 分析/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /复制到工程/ })).toHaveCount(0);
  await expect(page.locator('.character-detail-footer').getByRole('button')).toHaveCount(2);

  await sidebar.getByRole('button', { name: /示例工程/ }).click();
  await expect(page.getByRole('heading', { name: '工程林舟' })).toBeVisible();
  await expect(detail.getByText('所属分类', { exact: true })).toHaveCount(0);
  await sidebar.getByRole('button', { name: /全部角色/ }).click();
  await expect(page.getByText('林舟', { exact: true }).first()).toBeVisible();

  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBe(false);
  }
});

test('统一新建入口先预览多个 AI 候选且手动编辑器使用紧凑资源布局', async ({ page }) => {
  await page.goto('/characters');
  await expect(page.getByRole('button', { name: /AI 分析/ })).toHaveCount(0);
  await page.getByRole('button', { name: '角色提取设置' }).click();
  const settingsDialog = page.getByRole('dialog', { name: '角色提取设置' });
  await expect(settingsDialog.getByLabel('默认模型')).toHaveValue('1');
  await expect(settingsDialog.getByText('查看 Prompt 预览')).toBeVisible();
  await settingsDialog.getByRole('button', { name: '取消' }).click();
  await page.getByRole('button', { name: /新建角色/ }).first().click();
  const createDialog = page.getByRole('dialog', { name: '新建角色' });
  await expect(createDialog.getByRole('tab', { name: '手动创建' })).toBeVisible();
  await expect(createDialog.getByRole('tab', { name: '从文本提取' })).toBeVisible();
  await createDialog.getByRole('tab', { name: '从文本提取' }).click();
  await createDialog.getByLabel('来源文本').fill('林舟接过阿音递来的钥匙。');
  const cardCountBefore = await page.locator('.character-compact-card').count();
  await createDialog.getByRole('button', { name: '生成候选角色' }).click();
  await expect(createDialog.getByLabel('角色名称').nth(0)).toHaveValue('林舟');
  await expect(createDialog.getByLabel('角色名称').nth(1)).toHaveValue('阿音');
  expect(await page.locator('.character-compact-card').count()).toBe(cardCountBefore);
  const suggestedTag = createDialog.locator('.character-candidate').first().getByRole('button', { name: '主角' });
  await expect(suggestedTag).toHaveAttribute('aria-pressed', 'false');
  await suggestedTag.click();
  await expect(suggestedTag).toHaveAttribute('aria-pressed', 'true');
  await createDialog.getByRole('button', { name: /确认创建/ }).click();
  await expect(createDialog).toHaveCount(0);

  await page.getByRole('button', { name: /新建角色/ }).first().click();
  await page.getByRole('dialog', { name: '新建角色' }).getByRole('button', { name: /进入手动编辑/ }).click();
  const editor = page.getByRole('dialog', { name: '新建角色' });
  await expect(editor.getByLabel('角色名称')).toBeVisible();
  await expect(editor.getByLabel('身份')).toBeVisible();
  await expect(editor.getByLabel('年龄')).toBeVisible();
  await expect(editor.getByLabel('设定')).toBeVisible();
  await expect(editor.locator('input[type="file"]')).toBeHidden();
  await expect(editor.getByText('PNG/JPEG/WebP，最大 5 MB')).toBeVisible();
  await editor.getByRole('button', { name: /添加字段/ }).click();
  await expect(editor.getByLabel('字段内容')).toHaveAttribute('rows', '2');
  await expect(editor.getByRole('button', { name: '上移' })).toBeDisabled();
  await expect(editor.getByRole('button', { name: '下移' })).toBeDisabled();
  await expect(editor.getByRole('button', { name: '添加到工程…' })).toHaveCount(0);
  await expect(editor.getByRole('button', { name: '保存为公共角色…' })).toHaveCount(0);
});

test('公共与工程角色编辑器只显示各自上下文操作', async ({ page }) => {
  await page.goto('/characters');
  await page.locator('.character-compact-card').first().dblclick();
  await expect(page.getByRole('dialog', { name: '编辑角色' }).getByRole('button', { name: '添加到工程…' })).toBeVisible();
  await page.getByRole('dialog', { name: '编辑角色' }).getByRole('button', { name: '取消' }).click();
  await page.locator('.character-range-panel').getByRole('button', { name: /示例工程/ }).click();
  await page.locator('.character-compact-card').first().dblclick();
  const projectEditor = page.getByRole('dialog', { name: '编辑角色' });
  await expect(projectEditor.getByRole('button', { name: '保存为公共角色…' })).toBeVisible();
  await expect(projectEditor.getByText('我的分类', { exact: true })).toHaveCount(0);
});

test('文档库在常用桌面窗口无横向溢出', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByText('文档库', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('收藏', { exact: true })).toHaveCount(0);
  for (const viewport of [
    { width: 1280, height: 720 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
  ]) {
    await page.setViewportSize(viewport);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
    expect(overflow).toBe(false);
  }
});

test('普通文档与工程文档严格分离并复用同一工作台', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toHaveCount(0);
  await page.locator('.document-tag-panel').getByRole('button', { name: /工程文档/ }).click();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toHaveCount(0);
  await page.getByRole('button', { name: '工程原稿，工程作者' }).dblclick();
  await expect(page.locator('textarea.manuscript-editor')).toBeVisible();
  await expect(page.getByText('工程原稿', { exact: true }).first()).toBeVisible();
});

test('分类标签和搜索按交集筛选且标签胶囊不修改关联', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '研究' })).toBeVisible();
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '待整理' })).toBeVisible();
  await page.locator('.document-tag-panel').getByRole('button', { name: /研究/ }).click();
  await page.locator('.document-detail-panel').getByRole('button', { name: '长篇', exact: true }).click();
  await page.getByRole('searchbox', { name: '搜索文档' }).fill('示例');
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toHaveCount(0);
  expect(tagAssignmentRequests).toHaveLength(0);
  await expect(page.getByRole('button', { name: /分类：研究/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /标签：长篇/ })).toBeVisible();
});

test('标签管理弹窗显式移除关联并显示当前版本文件', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByText('D:/Rusty/novel-v2.txt', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '管理当前文档标签' }).click();
  const dialog = page.getByRole('dialog', { name: '管理标签' });
  await dialog.getByRole('checkbox', { name: '长篇' }).uncheck();
  await dialog.getByRole('button', { name: '保存关联' }).click();
  await expect(dialog).toHaveCount(0);
  expect(tagAssignmentRequests).toEqual([{ documentId: 1, tagId: 21, selected: false }]);
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '长篇', exact: true })).toHaveCount(0);
});

test('文档正文右键菜单、编辑命令与统一分章入口', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await expect(page.getByRole('button', { name: '添加为场景素材来源' })).toBeVisible();
  await expect(page.getByRole('button', { name: '添加为剧情骨架来源' })).toBeVisible();
  await expect(page.getByRole('button', { name: '提取角色卡' })).toBeVisible();
  await editor.click({ position: { x: 20, y: 20 } });
  await expect(page.getByRole('button', { name: '添加为场景素材来源' })).toHaveCount(0);
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await page.getByRole('button', { name: '添加为场景素材来源' }).click();
  await expect(page).toHaveURL(/\/materials$/);
  await expect(page.getByRole('dialog').filter({ hasText: '新建场景素材' })).toBeVisible();
  await expect(page.getByRole('tab', { name: '从来源整理' })).toHaveAttribute('aria-selected', 'true');
  await expect(page.getByLabel('来源文本')).not.toHaveValue('');
  await page.getByRole('button', { name: /生成候选/ }).click();
  await expect(page.getByText('来源：《示例长篇》 · 第一章')).toBeVisible();
  await page.getByRole('button', { name: '返回来源' }).click();
  await page.getByRole('button', { name: '取消' }).last().click();
  await page.goBack();
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await expect(page.getByRole('button', { name: '标记章节', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '分章', exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'AI 分章', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '正则分章', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '引用范围', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '分章', exact: true }).click();
  await expect(page.getByRole('button', { name: 'AI 识别' })).toBeVisible();
  await expect(page.getByRole('button', { name: '正则识别' })).toBeVisible();
  await expect(page.getByRole('button', { name: '手动标记' })).toBeVisible();
});

test('文档选区通过 history state 进入角色候选流程而不直接创建', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await page.getByRole('button', { name: '提取角色卡' }).click();
  await expect(page).toHaveURL(/\/characters$/);
  const dialog = page.getByRole('dialog', { name: '新建角色' });
  await expect(dialog.getByRole('tab', { name: '从文本提取' })).toHaveAttribute('aria-selected', 'true');
  await expect(dialog.getByLabel('来源文本')).toHaveValue('林舟推门');
  await expect(dialog.getByRole('button', { name: '生成候选角色' })).toBeVisible();
  await dialog.getByRole('button', { name: '生成候选角色' }).click();
  await expect(dialog.getByText('来源：《示例长篇》 · 第一章')).toBeVisible();
});

test('正文自动保存草稿、手动保存单一版本并打开文字整理弹窗', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.fill('自动草稿-UNIQUE');
  await expect(page.getByText(/尚未保存草稿/)).toBeVisible();
  await expect(page.getByText(/草稿已保存/)).toBeVisible({ timeout: 3000 });
  await expect(page.getByText('版本 1 · 导入版')).toHaveCount(0);
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByText(/正文已保存为新版本/)).toBeVisible();
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/document-editor-saved.png` });
  }
  await page.getByRole('button', { name: '版本记录' }).click();
  await expect(page.getByText('版本 2 · 手动编辑')).toBeVisible();
  await page.getByRole('button', { name: '关闭' }).click();
  await page.getByRole('button', { name: '文字整理' }).click();
  await expect(page.getByRole('dialog').filter({ hasText: '文字整理' })).toBeVisible();
  await expect(page.getByRole('dialog').filter({ hasText: '文字整理' }).getByText('版本记录')).toHaveCount(0);
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/document-cleanup-dialog.png` });
  }
});

test('章节标题、实时字数及受控撤销重做保持同步', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  const title = page.locator('.document-editor-title input');
  await title.fill('即时新标题');
  await expect(page.locator('.chapter-list').getByText('即时新标题')).toBeVisible();
  await editor.fill('中文 A，🙂');
  await expect(page.locator('.document-workspace-stats').getByText('10', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '撤销', exact: true }).click();
  await expect(editor).toHaveValue('林舟推门而入，看见桌上的钥匙。');
  await page.getByRole('button', { name: '重做', exact: true }).click();
  await expect(editor).toHaveValue('中文 A，🙂');
  await editor.press('Control+z');
  await expect(editor).toHaveValue('林舟推门而入，看见桌上的钥匙。');
  await editor.press('Control+Shift+z');
  await expect(editor).toHaveValue('中文 A，🙂');
});

test('新增章节按目录序号解析锚点并自动选中新章节', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '新增章节' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: '新增章节' });
  await dialog.getByLabel('章节标题').fill('插入的新章');
  await dialog.getByLabel('插入位置').selectOption('after-index');
  await dialog.getByLabel('章节序号').fill('1');
  await expect(dialog.getByText('匹配：第一章')).toBeVisible();
  await dialog.getByLabel('正文').fill('新增正文');
  await dialog.getByRole('button', { name: '保存为新版本' }).click();
  await expect(page.locator('.chapter-row[aria-current="page"]').getByText('插入的新章')).toBeVisible();
  await expect(page.locator('.document-editor-title input')).toHaveValue('插入的新章');
});

test('卷目录可折叠、点击章节并独立修改卷标题', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const volumeTitle = page.getByLabel('卷标题：第七卷 雨夜');
  await expect(volumeTitle).toHaveValue('第七卷 雨夜');
  await expect(page.locator('.document-volume-row').getByText('24 字')).toBeVisible();
  const toggle = page.locator('.document-volume-toggle');
  await toggle.click();
  await expect(page.locator('.chapter-row')).toHaveCount(0);
  await toggle.click();
  await page.locator('.chapter-row').first().click();
  await expect(page.locator('textarea.manuscript-editor')).toHaveValue('林舟推门而入，看见桌上的钥匙。');
  await volumeTitle.fill('第七卷 新雨');
  await volumeTitle.blur();
  await expect(page.getByLabel('卷标题：第七卷 新雨')).toHaveValue('第七卷 新雨');
});

test('合并弹窗使用分类树且合并结果保留卷目录', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '合并文档' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: '合并文档' });
  await expect(dialog.getByRole('heading', { name: '研究' })).toBeVisible();
  await dialog.getByRole('checkbox', { name: '普通资料' }).check();
  await dialog.getByLabel('新文档标题').fill('层级合并本');
  await dialog.getByRole('button', { name: '创建新文档' }).click();
  await expect(page.getByRole('button', { name: '层级合并本，作者' })).toBeVisible();
  await page.getByRole('button', { name: '层级合并本，作者' }).dblclick();
  await expect(page.getByLabel('卷标题：第七卷 雨夜')).toBeVisible();
  await expect(page.getByRole('button', { name: '导出文档' })).toBeVisible();
});

test('卷目录在深色主题和桌面宽度下无横向溢出', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  }
});

test('场景改写完成三段确认流程', async ({ page }) => {
  page.on('dialog', (dialog) => dialog.accept());
  await page.goto('/workspace/1');
  await page.getByRole('button', { name: '场景改写' }).click();
  await page.getByRole('button', { name: /1\. 分析并提取骨架/ }).click();
  await expect(page.getByText(/等待确认骨架/)).toBeVisible();
  await page.getByRole('button', { name: /2\. 确认骨架并生成规划/ }).click();
  await expect(page.getByText(/等待确认/)).toBeVisible();
  await page.getByRole('button', { name: /3\. 确认规划并执行/ }).click();
  await expect(page.getByText(/一致性检查/)).toBeVisible();
  await expect(page.getByText('版本历史（原文不被覆盖）')).toBeVisible();
  await page.getByText(/版本 1/).click();
  await page.getByRole('button', { name: '恢复为新版本' }).click();
  await expect(page.getByText(/已从所选历史内容创建新的恢复版本/)).toBeVisible();
  await expect(page.getByText(/版本 2/)).toBeVisible();
});

test('编辑骨架后插入位置实时使用新节点 ID', async ({ page }) => {
  await page.goto('/workspace/1');
  await page.getByRole('button', { name: '场景改写' }).click();
  await page.locator('.scene-workflow-form label').filter({ hasText: '模式' }).locator('select').selectOption('expansion');
  await page.getByText('误会解除', { exact: true }).click();
  await page.getByRole('button', { name: /1\. 分析并提取骨架/ }).click();
  const editor = page.getByRole('heading', { name: '骨架编辑器' }).locator('..').locator('textarea');
  await editor.fill(JSON.stringify([{ id: 'NEW-NODE-ID', event: '新的事件节点' }], null, 2));
  const insertion = page.locator('.scene-workflow-form label').filter({ hasText: '插入位置' }).locator('select');
  await expect(insertion.locator('option[value="n1"]')).toHaveCount(0);
  await expect(insertion.locator('option[value="NEW-NODE-ID"]')).toHaveText(/新的事件节点/);
  await insertion.selectOption('NEW-NODE-ID');
  await page.getByRole('button', { name: /2\. 确认骨架并生成规划/ }).click();
  await expect.poll(() => workflowPlanRequests.length).toBe(1);
  const mappings = workflowPlanRequests[0].material_mappings as Array<Record<string, unknown>>;
  expect(mappings[0].insertion_after_node).toBe('NEW-NODE-ID');
});

test('非法骨架不会发送规划请求', async ({ page }) => {
  await page.goto('/workspace/1');
  await page.getByRole('button', { name: '场景改写' }).click();
  await page.locator('.scene-workflow-form label').filter({ hasText: '模式' }).locator('select').selectOption('expansion');
  await page.getByText('误会解除', { exact: true }).click();
  await page.getByRole('button', { name: /1\. 分析并提取骨架/ }).click();
  const editor = page.getByRole('heading', { name: '骨架编辑器' }).locator('..').locator('textarea');
  for (const [value, error] of [
    ['[{', '骨架 JSON 格式无效'],
    [JSON.stringify([{ id: 'DUP', event: 'A' }, { id: 'DUP', event: 'B' }]), '骨架节点 id 重复'],
    [JSON.stringify([{ id: 'NO-EVENT' }]), '缺少非空 event'],
  ]) {
    await editor.fill(value);
    await expect(page.getByRole('heading', { name: '骨架编辑器' }).locator('..').getByRole('alert')).toContainText(error);
    await page.getByRole('button', { name: /2\. 确认骨架并生成规划/ }).click();
    expect(workflowPlanRequests).toHaveLength(0);
  }
});
