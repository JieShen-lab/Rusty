import { expect, test, type Page } from '@playwright/test';

const projects = [
  { id: 1, name: '示例工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-29 12:00:00' },
  { id: 2, name: '北境工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-28 12:00:00' },
  { id: 3, name: '旧城工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-27 12:00:00' },
  { id: 4, name: '海港工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-26 12:00:00' },
];
const tags = [{ id: 1, name: '主角', normalized_name: '主角', sort_order: 0, resource_count: 1 }];
const characterCategories = [
  { id: 31, name: '主要角色', normalized_name: '主要角色', sort_order: 0, resource_count: 1 },
  { id: 32, name: '历史人物', normalized_name: '历史人物', sort_order: 1, resource_count: 1 },
];
const publicCharacter = {
  id: 1, name: '林舟', aliases: [], description: '沉着的调查者', priority: 50, is_main: true, relationship_notes: '', personality: '', speech_style: '', action_constraints: '', anti_ooc_rules: '', profile: {}, source_metadata: {}, import_metadata: {}, scope: 'public' as const, project_id: null, source_character_card_id: null, source_version: null, version: 1, sort_order: 0, identity: '调查者', age: '', setting_text: '林舟习惯先观察再行动。他对旧城历史十分熟悉，并且不轻易表露情绪。', custom_fields: [], stable_fields: [{ id: 'personality', label: '性格', value: '冷静', sort_order: 0 }], raw_text: '林舟推门而入。', analysis_status: 'unanalyzed' as const, cover_path: null, cover_updated_at: null, tags: ['主角'], category_ids: [31, 32], categories: ['主要角色', '历史人物'], source_summary: { kind: 'document_selection' as const, label: '《示例长篇》 · 第一章', document_id: 1, chapter_id: 1 }, created_at: '', updated_at: '',
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
  { id: 1, material_type: 'author_style', scope: 'public', project_id: null, project_name: null, name: '雨夜文风', description: '雨夜动作写法', detail_level: 'standard', raw_text: '雨落在屋檐。', content: { schema_version: 1, summary: '短句推进', dimensions: [{ id: 'sentence-features', name: '句子特征', requirement: '分析句式', analysis: '短句推进动作', features: ['短句'], examples: ['雨落在屋檐。'] }] }, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [], general_tags: [], applicable_scene_tags: [], category_ids: [], categories: [], source_summary: { kind: 'manual', label: '本地创建' } },
  { id: 2, material_type: 'plot_skeleton', scope: 'public', project_id: null, project_name: null, name: '误会解除', description: '事件骨架', detail_level: 'standard', raw_text: '', content: { schema_version: 1, premise: '误会造成分离', stages: [{ id: 'stage-fixed', title: '误会发生', summary: '两人争执', causes: ['错误线索'], effects: ['暂时分离'], characters: ['林舟'], locations: ['旧城'], must_keep_details: ['钥匙'], forbidden_changes: ['不能提前和解'], unknown: 'keep' }], conflicts: [], turning_points: [], climax: { id: 'climax', title: '真相', summary: '发现真相' }, resolution: { id: 'resolution', title: '和解', summary: '解除误会' }, hooks: [], legacy_extra: { keep: true } }, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [] },
];
const baseDocumentItems = [
  { id: 1, title: '示例长篇', author: '作者', description: null, source_filename: 'novel.txt', source_format: 'txt', storage_path: 'D:/Rusty/novel-v2.txt', source_size_bytes: 100, stored_size_bytes: 100, chapter_count: 1, word_count: 16, status: 'ready', favorite: false, tags: ['长篇', '历史'], is_project_document: false, category_ids: [11, 12], categories: ['研究', '待整理'], project_ids: [], created_at: '2026-07-29 10:00:00', updated_at: '' },
  { id: 2, title: '工程原稿', author: '工程作者', description: null, source_filename: 'project.txt', source_format: 'txt', storage_path: 'D:/Rusty/project-v1.txt', source_size_bytes: 80, stored_size_bytes: 80, chapter_count: 1, word_count: 12, status: 'ready', favorite: false, tags: ['长篇'], is_project_document: true, category_ids: [11], categories: ['研究'], project_ids: [1], created_at: '2026-07-28 10:00:00', updated_at: '' },
  { id: 3, title: '普通资料', author: '资料作者', description: null, source_filename: 'reference.txt', source_format: 'txt', storage_path: 'D:/Rusty/reference-v1.txt', source_size_bytes: 60, stored_size_bytes: 60, chapter_count: 1, word_count: 10, status: 'ready', favorite: false, tags: [], is_project_document: false, category_ids: [11], categories: ['研究'], project_ids: [], created_at: '2026-07-27 10:00:00', updated_at: '' },
];
const documentTags = [{ id: 21, name: '长篇', normalized_name: '长篇', sort_order: 0, resource_count: 2 }, { id: 22, name: '历史', normalized_name: '历史', sort_order: 1, resource_count: 1 }];
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
  let materialSettings = [
    { task_type: 'plot_skeleton_extraction', model_id: 1, detail_level: 'standard', system_prompt: '只使用来源事实。', base_instruction: '提取可复用剧情结构。', dimensions: [{ id: 'structure', name: '整体剧情结构', requirement: '分析结构。' }], extra_requirements: '', prompt_preview: '提取可复用剧情结构', updated_at: '' },
    { task_type: 'author_style_extraction', model_id: 1, detail_level: 'standard', system_prompt: '分析作者风格。', base_instruction: '分析具体写法。', dimensions: [{ id: 'sentence-features', name: '句子特征', requirement: '分析句式' }], extra_requirements: '', prompt_preview: '分析作者风格', updated_at: '' },
  ];
  let characterItems = [structuredClone(publicCharacter)];
  let documentChapterTitle = '';
  let volumeTitle = '第七卷 雨夜';
  let extraChapter: { id: number; document_id: number; revision_id: number; index: number; title: string; start_line: number; end_line: number; start_offset: number; end_offset: number; word_count: number; volume_id: number } | null = null;
  let extraChapterBody = '新增正文';
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = [];
    if (path === '/api/projects') body = projects;
    else if (path === '/api/character-tags' || path === '/api/material-tags') body = tags;
    else if (path === '/api/character-categories') body = characterCategories;
    else if (path === '/api/character-projects/summary') body = projects.map((project, index) => ({ project_id: project.id, project_name: project.name, character_count: index === 0 ? 1 : 0, updated_at: project.updated_at }));
    else if (path === '/api/models') body = [{ id: 1, display_name: '测试模型', provider: 'openai_compatible', base_url: '', model_name: 'test', is_default: true, created_at: '', updated_at: '' }];
    else if (path === '/api/character-extraction/settings') body = { model_id: 1, detail_level: 'standard', generate_tags: true, custom_requirements: '', system_prompt: '不得补全无证据事实', dimensions: [{ id: 'personality', label: '性格', instruction: '只提取明确证据', sort_order: 0, enabled: true, is_default: true }], prompt_preview: '目标人物：{{TARGET_CHARACTER_NAME}}\n来源：{{SOURCE_TEXT}}' };
    else if (path === '/api/characters/extract/preview') {
      const request = route.request().postDataJSON() as { target_character_name: string; source_text: string; source_metadata?: Record<string, unknown> };
      const metadata = request.source_metadata ?? {};
      body = { preview_token: 'preview-test', expires_at: '2030-01-01T00:00:00Z', character: { name: request.target_character_name, aliases: [], description: '调查者', identity: '调查者', age: '', stable_fields: [{ id: 'personality', label: '性格', value: '冷静', sort_order: 0 }], suggested_tags: ['主角', '冷静'], source_metadata: metadata, import_metadata: { created_by: 'ai_character_extraction' }, raw_text: request.source_text } };
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
    else if (path === '/api/characters' && route.request().method() === 'POST') {
      const draft = route.request().postDataJSON();
      const created = { ...publicCharacter, ...draft, id: 8, tags: (draft.tag_ids ?? []).map((id: number) => tags.find((tag) => tag.id === id)?.name).filter(Boolean), category_ids: [], categories: [] };
      characterItems = [...characterItems, created]; body = created;
    }
    else if (path === '/api/characters') body = characterItems;
    else if (path === '/api/material-categories') body = [];
    else if (path === '/api/material-ai-settings') body = materialSettings;
    else if (/^\/api\/material-ai-settings\/(plot_skeleton_extraction|author_style_extraction)$/.test(path)) {
      const taskType = path.split('/').at(-1);
      const current = materialSettings.find((item) => item.task_type === taskType)!;
      if (route.request().method() === 'POST') {
        const request = route.request().postDataJSON();
        const updated = { ...current, ...request, prompt_preview: `${request.system_prompt}\n${request.base_instruction}\n${request.dimensions.map((item: { name: string }) => item.name).join('\n')}` };
        materialSettings = materialSettings.map((item) => item.task_type === taskType ? updated : item);
        body = updated;
      } else body = current;
    }
    else if (path === '/api/author-style-settings/export') {
      const current = materialSettings.find((item) => item.task_type === 'author_style_extraction')!;
      body = { schema_version: 1, config_type: 'author_style_extraction', detail_level: current.detail_level, system_prompt: current.system_prompt, base_instruction: current.base_instruction, dimensions: current.dimensions, extra_requirements: current.extra_requirements };
    }
    else if (path === '/api/author-style-settings/import') {
      const request = route.request().postDataJSON() as { value: Record<string, unknown> };
      const current = materialSettings.find((item) => item.task_type === 'author_style_extraction')!;
      const updated = { ...current, ...request.value, task_type: 'author_style_extraction', model_id: current.model_id, prompt_preview: String(request.value.system_prompt ?? '') };
      materialSettings = materialSettings.map((item) => item.task_type === 'author_style_extraction' ? updated : item);
      body = updated;
    }
    else if (path === '/api/material-extractions/preview') {
      const request = route.request().postDataJSON() as { source_metadata?: Record<string, unknown> };
      const metadata = request.source_metadata ?? {};
      body = {
      preview_token: 'material-preview',
      expires_at: '2030-01-01T00:00:00Z',
      task_type: 'author_style_extraction',
      material_type: 'author_style',
      source_summary: metadata.document_title ? { kind: 'document_selection', label: `《${metadata.document_title}》 · ${metadata.chapter_title}`, document_id: metadata.document_id, chapter_id: metadata.chapter_id } : { kind: 'pasted_text', label: '粘贴文本' },
      prompt_snapshot: { task_type: 'author_style_extraction' },
      candidates: [{
        candidate_id: 'style-1', material_type: 'author_style', selected: true, name: '雨夜文风', description: '雨夜动作写法',
        content: { schema_version: 1, summary: '雨夜追逐的动作与感官提示。', key_beats: [{ id: 'beat-1', title: '跃上屋顶', summary: '快速追逐', evidence_summary: '湿滑屋顶' }] },
        suggested_general_tags: ['动作'], suggested_applicable_scene_tags: ['雨夜'],
        evidence: [{ quote: '雨夜追逐' }], evidence_summary: '原文明确包含雨夜和追逐。',
        confidence: 0.9, warnings: [],
      }],
      };
    }
    else if (path === '/api/material-extractions/apply') body = { created: [{ candidate_id: 'scene-1', material_id: 1, error: null }], errors: [] };
    else if (/^\/api\/materials\/\d+\/author-style\/dimensions\/preview$/.test(path)) {
      const request = route.request().postDataJSON() as { dimension_id: string; dimension_name: string };
      body = { preview_token: 'dimension-preview', material_id: 1, dimension_id: request.dimension_id, dimension_name: request.dimension_name, analysis: '只分析新增维度', features: ['局部特征'], examples: ['雨落在屋檐。'], source_revision: 'source-hash' };
    }
    else if (/^\/api\/materials\/\d+\/author-style\/dimensions\/apply$/.test(path)) {
      const current = materialItems[0];
      const dimensions = Array.isArray(current.content.dimensions)
        ? current.content.dimensions.map((item: Record<string, unknown>) => item.analysis ? item : { ...item, analysis: '只分析新增维度', features: ['局部特征'], examples: ['雨落在屋檐。'] })
        : [];
      const updated = { ...current, content: { ...current.content, dimensions } };
      materialItems = materialItems.map((item) => item.id === current.id ? updated : item);
      body = updated;
    }
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
    else if (path === '/api/materials/import-json') body = { imported: [{ index: 0, id: 3, name: '导入风格', material_type: 'author_style' }], errors: [] };
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
      const tag = documentTags.find((item) => item.id === tagId);
      documentItems = documentItems.map((item) => item.id === documentId
        ? { ...item, tags: selected && tag ? [...new Set([...item.tags, tag.name])] : item.tags.filter((name) => name !== tag?.name) }
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
    else if (/^\/api\/documents\/\d+$/.test(path) && route.request().method() === 'POST') {
      const documentId = Number(path.split('/')[3]);
      const request = route.request().postDataJSON() as { title: string; author: string | null };
      documentItems = documentItems.map((item) => item.id === documentId
        ? { ...item, title: request.title, author: request.author, updated_at: '2026-07-30 09:00:00' }
        : item);
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
      extraChapterBody = request.text;
      documentItems = documentItems.map((item) => item.id === documentId ? { ...item, chapter_count: 2 } : item);
      body = { document: documentItems.find((item) => item.id === documentId), revision: { id: documentId * 10 + documentRevisionNumber, document_id: documentId, revision_number: documentRevisionNumber, revision_type: 'manual_edit', storage_path: `D:/Rusty/novel-v${documentRevisionNumber}.txt`, template_id: null, parent_revision_id: documentId * 10 + documentRevisionNumber - 1, created_at: '' }, created: true, created_chapter_id: 999 };
    }
    else if (/^\/api\/documents\/\d+\/split\/cursor$/.test(path)) {
      const documentId = Number(path.split('/')[3]);
      const request = route.request().postDataJSON() as { cursor_offset: number; next_title: string };
      extraChapterBody = documentBody.slice(request.cursor_offset);
      documentBody = documentBody.slice(0, request.cursor_offset);
      documentRevisionNumber += 1;
      extraChapter = { id: 999, document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, index: 2, title: request.next_title, start_line: 3, end_line: 4, start_offset: documentBody.length, end_offset: documentBody.length + request.next_title.length + extraChapterBody.length + 2, word_count: Array.from(request.next_title + extraChapterBody).filter((value) => !/\s/u.test(value)).length, volume_id: 701 };
      documentItems = documentItems.map((item) => item.id === documentId ? { ...item, chapter_count: 2 } : item);
      body = { document: documentItems.find((item) => item.id === documentId), revision: { id: documentId * 10 + documentRevisionNumber, document_id: documentId, revision_number: documentRevisionNumber, revision_type: 'split_cursor', storage_path: `D:/Rusty/novel-v${documentRevisionNumber}.txt`, template_id: null, parent_revision_id: documentId * 10 + documentRevisionNumber - 1, created_at: '' }, created: true, created_chapter_id: 999 };
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
        ? { document_id: documentId, revision_id: extraChapter.revision_id, chapter_id: 999, title: extraChapter.title, text: `${extraChapter.title}\n\n${extraChapterBody}`, body_text: extraChapterBody, section_start_offset: extraChapter.start_offset, body_start_offset: extraChapter.start_offset + extraChapter.title.length + 2, start_offset: extraChapter.start_offset, end_offset: extraChapter.end_offset }
        : { document_id: documentId, revision_id: documentId * 10 + documentRevisionNumber, chapter_id: documentId * 100 + documentRevisionNumber, title: documentChapterTitle, text: `${documentChapterTitle}\n\n${documentBody}`, body_text: documentBody, section_start_offset: 0, body_start_offset: documentChapterTitle.length + 2, start_offset: 0, end_offset: documentBody.length + documentChapterTitle.length + 2 };
    }
    else if (path === '/api/projects/1') body = { project: { id: 1, name: '示例工程', author: '', project_kind: 'rewrite', purpose: 'rewrite', status: 'ready', source_path: '', workspace_path: '', total_chapters: 1, total_words: 16, processed_chapters: 0, created_at: '', updated_at: '' }, metadata: {}, settings: { processing_mode: 'rewrite' }, exports: [] };
    else if (path === '/api/projects/1/chapters') body = [{ id: 1, project_id: 1, index: 1, title: '第一章', original_text: '林舟推门而入，看见桌上的钥匙。', rewritten_text: '', word_count: 16, status: 'pending', created_at: '', updated_at: '' }];
    else if (path === '/api/projects/1/creative-workflow') body = [{ chapter_id: 1, chapter_index: 1, title: '第一章', active_scene_id: 1, current_stage: 'preanalysis', updated_at: '' }];
    else if (path === '/api/chapters/1/creative-scene-states') body = [{ scene_id: 1, scene_index: 1, title: '发现钥匙', current_stage: 'preanalysis', updated_at: '' }];
    else if (path === '/api/projects/1/characters') body = { character_cards: [] };
    else if (path === '/api/projects/1/materials') body = [];
    else if (path === '/api/scenes/1/preanalysis' || path === '/api/scenes/1/creative-intent' || path === '/api/scenes/1/character-modification-analysis') body = null;
    else if (path === '/api/chapters/1') body = { chapter: { id: 1, project_id: 1, index: 1, title: '第一章', original_text: '林舟推门而入，看见桌上的钥匙。', rewritten_text: '', word_count: 16, status: 'pending', created_at: '', updated_at: '' }, ai_outputs: { plot_summary: '', expanded_plot: '', plot_characters: [], style_analysis: {}, reviewed_style_analysis: {}, style_analysis_status: '' } };
    else if (path.includes('/prompt-preview')) body = { ruleset_id: 'test', provenance: {}, expected_output: 'text', messages: [] };
    else if (path.includes('/generation-attempts')) body = [];
    else if (path === '/api/prompt-definitions') body = [
      { id: 101, name: '小说总规则', description: '工程通用创作要求', kind: 'master', workflow_key: null, task_key: null, content: '保持人物一致。', input_description: '工程级规则', is_default: true, created_at: '', updated_at: '' },
      { id: 102, name: '人物专项分析', description: '贴合原文人物修改', kind: 'workflow_task', workflow_key: 'faithful', task_key: 'character_modification_analysis', content: '识别人物关联。', input_description: '场景原文、人物卡、具体要求', is_default: true, created_at: '', updated_at: '' },
      { id: 103, name: '场景预分析', description: '轻量识别场景', kind: 'common_task', workflow_key: null, task_key: 'scene_preanalysis', content: '只提取基础事实。', input_description: '场景原文', is_default: true, created_at: '', updated_at: '' },
    ];
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

test('提示词管理使用总提示词、工作流和公共任务三类对象', async ({ page }) => {
  const analysisPromptRequests: string[] = [];
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('request', (request) => {
    if (new URL(request.url()).pathname === '/api/analysis-prompts') analysisPromptRequests.push(request.url());
  });
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/prompts');

  await expect(page.getByRole('heading', { name: '提示词', exact: true })).toBeVisible();
  await expect(page.getByText('总提示词', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('工作流', { exact: true })).toBeVisible();
  await expect(page.getByText('公共任务提示词', { exact: true }).first()).toBeVisible();
  await expect(page.getByRole('button', { name: /小说总规则/ }).first()).toBeVisible();
  await expect(page.getByLabel('名称')).toHaveValue('小说总规则');
  await page.getByRole('button', { name: '贴合原文', exact: true }).click();
  await expect(page.getByRole('button', { name: /人物专项分析/ })).toBeVisible();
  await expect(page.getByLabel('名称')).toHaveValue('人物专项分析');
  await expect(page.getByRole('button', { name: /小说总规则/ })).toHaveCount(0);
  await page.getByRole('button', { name: '公共任务提示词', exact: true }).click();
  await expect(page.getByRole('button', { name: /场景预分析/ })).toBeVisible();
  await expect(page.getByLabel('名称')).toHaveValue('场景预分析');
  await expect(page.getByText('版本历史')).toHaveCount(0);
  await expect(page.getByText('同步状态')).toHaveCount(0);
  expect(analysisPromptRequests).toHaveLength(0);
  expect(consoleErrors).toHaveLength(0);
  expect(pageErrors).toHaveLength(0);
});

test('素材库只显示两种类型且无时间线主视图', async ({ page }) => {
  await page.goto('/materials');
  await expect(page.getByText('剧情骨架', { exact: true }).first()).toBeVisible();
  await page.getByRole('button', { name: '切换素材类型（左）' }).click();
  await expect(page.getByText('作者风格', { exact: true }).first()).toBeVisible();
  await expect(page.getByText(['场景', '素材'].join(''), { exact: true })).toHaveCount(0);
  await expect(page.getByText('大纲', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('tab', { name: '时间线' })).toHaveCount(0);
});

test('素材库使用统一范围、结构化新建与 AI 候选确认流程', async ({ page }) => {
  await page.goto('/materials');
  const sidebar = page.locator('.material-library-sidebar');
  await expect(sidebar.getByText('公共素材', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('工程素材', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('我的标签', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('全部内容', { exact: true })).toHaveCount(1);
  await expect(sidebar.getByText('最近导入', { exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: /AI 分析/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新建剧情骨架', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '新建作者风格', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '切换素材类型（右）' }).click();
  await expect(page.getByRole('button', { name: '新建作者风格', exact: true })).toBeVisible();
  await page.getByRole('button', { name: '新建作者风格', exact: true }).click();
  await page.getByLabel('来源文本').fill('雨夜里，人物沿着湿滑屋顶快速追逐。');
  await page.getByRole('button', { name: /AI 提取/ }).click();
  await page.getByRole('button', { name: '确认保存' }).click();
});

test('AI 新建强制目标人物且 Preview 后进入统一编辑器', async ({ page }) => {
  let previewRequests = 0;
  let createRequests = 0;
  page.on('request', (request) => {
    if (request.url().endsWith('/api/characters/extract/preview')) previewRequests += 1;
    if (request.url().endsWith('/api/characters') && request.method() === 'POST') createRequests += 1;
  });
  await page.goto('/characters');
  await page.getByRole('button', { name: 'AI 新建' }).click();
  const dialog = page.getByRole('dialog', { name: 'AI 新建角色' });
  await dialog.getByLabel('来源文本').fill('林舟接过阿音递来的钥匙。');
  await expect(dialog.getByRole('button', { name: '开始提取' })).toBeDisabled();
  await dialog.getByLabel('角色名称 *').fill('林舟');
  await dialog.getByRole('button', { name: '开始提取' }).click();
  await expect(dialog).toHaveCount(0);
  const editor = page.getByRole('dialog', { name: '新建角色' });
  await expect(editor.getByLabel('角色名称')).toHaveValue('林舟');
  await expect(editor.getByLabel('性格内容')).toHaveValue('冷静');
  expect(previewRequests).toBe(1);
  expect(createRequests).toBe(0);
  await editor.getByRole('button', { name: '保存' }).click();
  await expect.poll(() => createRequests).toBe(1);
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
  await page.getByRole('button', { name: '切换素材类型（左）' }).click();
  await page.getByRole('button', { name: '新建作者风格', exact: true }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('来源文本').fill('雨夜里，人物沿着湿滑屋顶快速追逐。');
  await dialog.getByRole('button', { name: /AI 提取/ }).click();
  await dialog.getByRole('button', { name: '确认保存' }).click();
  await expect(dialog).toBeVisible();
  await expect(page.getByRole('alert')).toContainText('素材事务已回滚');
  await dialog.getByLabel('名称').fill('雨夜文风（修正）');
  await dialog.getByRole('button', { name: '确认保存' }).click();
  await expect(dialog).toHaveCount(0);
  expect(attempts).toBe(2);
});

test('剧情骨架详细字段可编辑保存并重新打开', async ({ page }) => {
  await page.goto('/materials');
  await page.locator('.document-book').filter({ hasText: '误会解除' }).dblclick();
  const editor = page.getByRole('dialog', { name: '剧情骨架编辑器' });
  await expect(editor.getByLabel('剧情骨架结构')).toBeVisible();
  await editor.getByRole('button', { name: '保存' }).click();
});

test('作者风格维度可编辑保存并重新打开', async ({ page }) => {
  await page.goto('/materials');
  await page.getByRole('button', { name: '切换素材类型（左）' }).click();
  await page.locator('.document-book').filter({ hasText: '雨夜文风' }).dblclick();
  const editor = page.getByRole('dialog', { name: '作者风格编辑器' });
  await editor.getByLabel('风格分析').fill('短句与动作交替');
  await editor.getByRole('button', { name: '保存' }).click();
  await expect(editor.getByLabel('风格分析')).toHaveValue('短句与动作交替');
});

test('作者风格可新增维度并只提取当前维度', async ({ page }) => {
  await page.goto('/materials');
  await page.getByRole('button', { name: '切换素材类型（左）' }).click();
  await page.locator('.document-book').filter({ hasText: '雨夜文风' }).dblclick();
  const editor = page.getByRole('dialog', { name: '作者风格编辑器' });
  await editor.getByRole('button', { name: '新增维度' }).click();
  const newDimension = editor.locator('details').last();
  await newDimension.locator('summary').click();
  await newDimension.getByLabel('维度名称').fill('女性描写风格');
  await newDimension.getByLabel('提取要求').fill('分析描写顺序并给出原文实例。');
  page.on('dialog', (dialog) => void dialog.accept());
  await newDimension.getByRole('button', { name: 'AI 提取此维度' }).click();
  await expect(newDimension.getByLabel('风格分析')).toHaveValue('只分析新增维度');
  await expect(editor.locator('details').first().getByLabel('风格分析')).toHaveValue('短句推进动作');
});

test('两类素材共用唯一设置方案且作者风格支持 JSON 导入导出', async ({ page }) => {
  await page.goto('/materials');
  await page.getByRole('button', { name: '剧情骨架提取设置' }).click();
  let dialog = page.getByRole('dialog', { name: '剧情骨架提取设置' });
  await expect(dialog.getByText('当前保存内容就是以后提取使用的唯一默认配置')).toBeVisible();
  await expect(dialog.getByText(/恢复默认|方案列表|另存为方案/)).toHaveCount(0);
  await dialog.getByRole('button', { name: '新增分析维度' }).click();
  await dialog.getByLabel('维度名称').last().fill('新结构维度');
  await expect(dialog.locator('.material-prompt-preview')).toContainText('新结构维度');
  await dialog.getByRole('button', { name: '关闭' }).last().click();

  await page.getByRole('button', { name: '切换素材类型（右）' }).click();
  await page.getByRole('button', { name: '作者风格提取设置' }).click();
  dialog = page.getByRole('dialog', { name: '作者风格提取设置' });
  const download = page.waitForEvent('download');
  await dialog.getByRole('button', { name: '导出 JSON' }).click();
  await download;
  let confirmed = false;
  page.on('dialog', (confirmation) => { confirmed = true; void confirmation.accept(); });
  await dialog.locator('input[type="file"]').setInputFiles({
    name: 'author-style.json', mimeType: 'application/json',
    buffer: Buffer.from(JSON.stringify({ schema_version: 1, config_type: 'author_style_extraction', detail_level: 'detailed', system_prompt: '导入后的系统提示词', base_instruction: '导入后的任务说明', dimensions: [{ id: 'imported', name: '导入维度', requirement: '导入要求' }], extra_requirements: '' })),
  });
  await expect.poll(() => confirmed).toBe(true);
  await expect(dialog.getByLabel('系统提示词')).toHaveValue('导入后的系统提示词');
  await expect(dialog.getByLabel('默认模型')).toHaveValue('1');
  await expect(dialog.getByText(/恢复默认|方案列表|另存为方案/)).toHaveCount(0);
});

test('素材库侧栏无重复标题且 1440 深色主题无横向溢出', async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto('/materials');
  await expect(page.locator('.material-library-sidebar').getByRole('heading', { name: '素材库' })).toHaveCount(0);
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
  await expect(page.getByRole('button', { name: '新建剧情骨架', exact: true })).toBeVisible();
});

test('角色与素材都使用文档书本卡片', async ({ page }) => {
  const consoleErrors: string[] = [];
  const pageErrors: string[] = [];
  page.on('console', (message) => {
    if (message.type() === 'error') consoleErrors.push(message.text());
  });
  page.on('pageerror', (error) => pageErrors.push(error.message));

  await page.goto('/materials');
  const materialCards = page.locator('.material-book-grid .document-book');
  await expect(materialCards).toHaveCount(1);
  const materialLayout = await page.locator('.material-book-grid').evaluate((list) => ({
    columns: getComputedStyle(list).gridTemplateColumns.split(' ').length,
    cardRadii: Array.from(list.children).map((card) => getComputedStyle(card).borderRadius),
    overflow: getComputedStyle(list.parentElement as HTMLElement).overflowY,
  }));
  expect(materialLayout.columns).toBeGreaterThanOrEqual(1);
  expect(materialLayout.cardRadii[0]).not.toBe('0px');
  expect(materialLayout.overflow).toBe('auto');
  const materialName = await materialCards.first().locator('.document-book-title').innerText();
  await materialCards.first().click();
  await expect(materialCards.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.material-detail-panel').getByRole('heading', { name: materialName })).toBeVisible();

  await page.goto('/characters');
  const characterCards = page.locator('.document-character-grid .document-book');
  await expect(characterCards).toHaveCount(1);
  await expect(characterCards.first().locator('.character-book-cover')).toBeVisible();
  await characterCards.first().click();
  await expect(characterCards.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.character-detail-panel').getByText('林舟', { exact: true })).toBeVisible();
  expect(consoleErrors).toHaveLength(0);
  expect(pageErrors).toHaveLength(0);
});

test('角色库统一资产、分类标签搜索取交集且响应式无溢出', async ({ page }) => {
  await page.goto('/characters');
  const sidebar = page.locator('.character-range-panel');
  const detail = page.locator('.character-detail-panel');
  await expect(page.getByRole('heading', { name: '角色卡', exact: true })).toBeVisible();
  await expect(sidebar.getByText('工程角色', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('公共角色', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('全部角色', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('我的分类', { exact: true })).toBeVisible();
  await expect(sidebar.getByText('我的标签', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('系统筛选', { exact: true })).toHaveCount(0);
  await expect(sidebar.getByText('收藏', { exact: true })).toHaveCount(0);
  await expect(sidebar.locator('select')).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '主要角色', exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: '历史人物', exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: '主角', exact: true })).toBeVisible();
  await detail.getByRole('button', { name: '主角', exact: true }).click();
  await expect(page.getByText('标签：主角', { exact: false })).toBeVisible();
  await expect(detail.getByRole('button', { name: '主角', exact: true })).toBeVisible();
  await expect(page.getByText('来源版本', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /复制到工程|保存为公共角色|添加到工程/ })).toHaveCount(0);
  await sidebar.getByRole('button', { name: /主要角色/ }).click();
  await page.getByPlaceholder('搜索角色名称、身份或简介').fill('不存在');
  await expect(page.getByText('没有匹配的角色')).toBeVisible();
  await page.getByPlaceholder('搜索角色名称、身份或简介').fill('林舟');
  await expect(page.locator('.document-character-grid .document-book')).toHaveCount(1);

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

test('文档角色素材自定义分类统一使用右键菜单且不会越出视口', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.route('http://127.0.0.1:8765/api/material-categories', async (route) => {
    await route.fulfill({
      contentType: 'application/json',
      status: 200,
      body: JSON.stringify([{ id: 41, name: '动作风格', normalized_name: '动作风格', material_type: 'author_style', sort_order: 0, resource_count: 1 }]),
    });
  });

  await page.goto('/characters');
  const characterCategory = page.locator('.character-range-panel .document-tag-item').filter({ hasText: '主要角色' });
  await expect(characterCategory.locator('svg.lucide-folder')).toHaveCount(1);
  await expect(page.locator('.character-browser-shelf > header').getByText('全部公共角色', { exact: true })).toHaveCount(0);
  await characterCategory.click();
  await expect(characterCategory).toHaveAttribute('aria-pressed', 'true');
  await characterCategory.click({ button: 'right' });
  let menu = page.getByRole('menu', { name: '主要角色 分类操作' });
  await expect(menu.getByRole('menuitem', { name: '重命名' })).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: '删除分类' })).toBeVisible();
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/characters-category-context-menu.png` });
  await page.keyboard.press('Escape');
  await expect(menu).toHaveCount(0);
  await page.locator('.character-range-panel').getByRole('button', { name: /全部角色/ }).click({ button: 'right' });
  await expect(page.getByRole('menu')).toHaveCount(0);

  await page.goto('/materials');
  await page.getByRole('button', { name: '切换素材类型（左）' }).click();
  const recent = page.locator('.material-library-sidebar').getByRole('button', { name: /最近导入/ }).first();
  await expect(recent.locator('svg.lucide-clock')).toHaveCount(1);
  const category = page.locator('.material-library-sidebar .document-tag-item').filter({ hasText: '动作风格' });
  await expect(category.locator('svg.lucide-folder')).toHaveCount(1);
  await expect(category.getByRole('button', { name: /管理分类|重命名分类|删除分类/ })).toHaveCount(0);
  await category.click();
  await expect(category).toHaveAttribute('aria-pressed', 'true');
  await category.click({ button: 'right' });
  menu = page.getByRole('menu', { name: '动作风格 分类操作' });
  await expect(menu).toBeVisible();
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/materials-category-context-menu.png` });
  await page.locator('.page-topbar').click();
  await category.evaluate((element) => element.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 1438, clientY: 898 })));
  menu = page.getByRole('menu', { name: '动作风格 分类操作' });
  await expect(menu).toBeVisible();
  const menuRect = await menu.boundingBox();
  expect(menuRect).not.toBeNull();
  expect(menuRect!.x).toBeGreaterThanOrEqual(8);
  expect(menuRect!.y).toBeGreaterThanOrEqual(8);
  expect(menuRect!.x + menuRect!.width).toBeLessThanOrEqual(1432);
  expect(menuRect!.y + menuRect!.height).toBeLessThanOrEqual(892);
  await page.locator('.page-topbar').click();
  await expect(menu).toHaveCount(0);
  await category.click({ button: 'right' });
  await page.locator('.material-library-sidebar nav').dispatchEvent('scroll');
  await expect(menu).toHaveCount(0);
  await recent.click({ button: 'right' });
  await expect(page.getByRole('menu')).toHaveCount(0);

  await page.goto('/documents');
  const documentCategory = page.locator('.document-tag-panel').getByRole('button', { name: /研究/ }).first();
  await documentCategory.click();
  await expect(documentCategory).toHaveAttribute('aria-current', 'page');
  await documentCategory.click({ button: 'right' });
  menu = page.getByRole('menu', { name: '研究 分类操作' });
  await expect(menu.getByRole('menuitem', { name: '重命名' })).toBeVisible();
  await expect(menu.getByRole('menuitem', { name: '删除分类' })).toBeVisible();
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/documents-category-context-menu.png` });
  await menu.getByRole('menuitem', { name: '重命名' }).click();
  const renameDialog = page.getByRole('dialog', { name: '重命名分类' });
  await expect(renameDialog.getByLabel('分类名称')).toHaveValue('研究');
  await renameDialog.getByRole('button', { name: '取消' }).click();
  await documentCategory.click({ button: 'right' });
  await page.keyboard.press('Escape');
  await page.locator('.document-tag-panel').getByRole('button', { name: /全部文档/ }).click({ button: 'right' });
  await expect(page.getByRole('menu')).toHaveCount(0);
});

test('资源库和提示词在深浅主题中保持同层 Workspace surface', async ({ page }) => {
  const cases = [
    { path: '/documents', workspace: '.document-library-layout', columns: ['.document-tag-panel', '.document-shelf-panel', '.document-detail-panel'] },
    { path: '/characters', workspace: '.character-browser-layout', columns: ['.character-range-panel', '.character-browser-shelf', '.character-detail-panel'] },
    { path: '/materials', workspace: '.material-browser-layout', columns: ['.material-library-sidebar', '.material-browser-shelf', '.material-detail-panel'] },
    { path: '/prompts', workspace: '.prompt-definition-layout', columns: ['.prompt-kind-tree', '.prompt-item-list', '.prompt-definition-editor'] },
  ];

  for (const item of cases) {
    await page.goto(item.path);
    const light = await page.locator(item.workspace).evaluate((workspace, columns) => ({
      workspace: getComputedStyle(workspace).backgroundColor,
      columns: columns.map((selector) => getComputedStyle(workspace.querySelector(selector)!).backgroundColor),
      radius: getComputedStyle(workspace).borderRadius,
    }), item.columns);
    expect(light.workspace).not.toBe('rgba(0, 0, 0, 0)');
    expect(new Set(light.columns)).toEqual(new Set(['rgba(0, 0, 0, 0)']));
    expect(light.radius).toBe('12px');

    await page.getByRole('button', { name: '切换到深色模式' }).click();
    const dark = await page.locator(item.workspace).evaluate((workspace, columns) => ({
      workspace: getComputedStyle(workspace).backgroundColor,
      columns: columns.map((selector) => getComputedStyle(workspace.querySelector(selector)!).backgroundColor),
    }), item.columns);
    expect(dark.workspace).not.toBe(light.workspace);
    expect(new Set(dark.columns)).toEqual(new Set(['rgba(0, 0, 0, 0)']));
    await page.getByRole('button', { name: '切换到浅色模式' }).click();
  }
});

test('文档角色素材使用同宽导航列和统一标题及导航行', async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  const cases = [
    { path: '/documents', sidebar: '.document-library-layout > .document-tag-panel', title: '.document-tag-panel > header h2' },
    { path: '/characters', sidebar: '.character-browser-layout > .character-range-panel', title: '.library-sidebar-section-title strong' },
    { path: '/materials', sidebar: '.material-browser-layout > .material-library-sidebar', title: '.library-sidebar-section-title strong' },
  ];
  const measurements = [];
  for (const item of cases) {
    await page.goto(item.path);
    measurements.push(await page.locator(item.sidebar).evaluate((sidebar, titleSelector) => {
      const title = sidebar.querySelector(titleSelector)!;
      const row = sidebar.querySelector('.document-tag-item')!;
      const rowStyle = getComputedStyle(row);
      const titleStyle = getComputedStyle(title);
      return {
        width: sidebar.getBoundingClientRect().width,
        titleAlign: titleStyle.textAlign,
        titleSize: titleStyle.fontSize,
        titleWeight: titleStyle.fontWeight,
        rowHeight: rowStyle.minHeight,
        rowRadius: rowStyle.borderRadius,
        rowColumns: rowStyle.gridTemplateColumns.split(' ').length,
      };
    }, item.title));
  }
  expect(new Set(measurements.map((item) => item.width))).toEqual(new Set([210]));
  expect(new Set(measurements.map((item) => item.titleSize))).toEqual(new Set(['15px']));
  expect(measurements.every((item) => Number(item.titleWeight) >= 700)).toBe(true);
  expect(measurements.every((item) => item.rowHeight === '42px' && item.rowRadius === '7px' && item.rowColumns === 3)).toBe(true);
});

test('提示词使用统一 Header、分隔列表并保留编辑保存、导入和新建', async ({ page }) => {
  let savedName = '';
  let imported = false;
  await page.route('http://127.0.0.1:8765/api/prompt-definitions/101', async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    savedName = String(payload.name ?? '');
    await route.fulfill({ contentType: 'application/json', status: 200, body: JSON.stringify({ id: 101, ...payload, created_at: '', updated_at: '' }) });
  });
  await page.route('http://127.0.0.1:8765/api/prompt-definitions/import', async (route) => {
    imported = true;
    await route.fulfill({ contentType: 'application/json', status: 200, body: JSON.stringify({ id: 104, name: '导入提示词', description: '', kind: 'master', workflow_key: null, task_key: null, content: '导入内容', input_description: '', is_default: false, created_at: '', updated_at: '' }) });
  });

  await page.goto('/prompts');
  await expect(page.locator('.prompt-definition-page > .page-topbar').getByRole('heading', { name: '提示词' })).toBeVisible();
  const primaryCategories = await page.locator('.prompt-kind-tree .primary-category, .prompt-kind-tree .prompt-primary-category').evaluateAll((items) => items.map((element) => ({
    fontSize: getComputedStyle(element).fontSize,
    fontWeight: getComputedStyle(element).fontWeight,
    height: getComputedStyle(element).minHeight,
    textAlign: getComputedStyle(element).textAlign,
  })));
  expect(primaryCategories).toHaveLength(3);
  expect(new Set(primaryCategories.map((item) => JSON.stringify(item))).size).toBe(1);
  const workflowChild = await page.locator('.prompt-kind-tree .category-button.nested').first().evaluate((element) => ({
    fontSize: getComputedStyle(element).fontSize,
    fontWeight: getComputedStyle(element).fontWeight,
    paddingLeft: getComputedStyle(element).paddingLeft,
    textAlign: getComputedStyle(element).textAlign,
  }));
  expect(workflowChild).toEqual({ fontSize: '13px', fontWeight: '400', paddingLeft: '28px', textAlign: 'left' });
  const activeItem = page.locator('.prompt-item-list > button.active');
  const activeStyle = await activeItem.evaluate((element) => ({
    shadow: getComputedStyle(element).boxShadow,
    divider: getComputedStyle(element).borderBottomWidth,
  }));
  expect(activeStyle.shadow).toBe('none');
  expect(activeStyle.divider).toBe('1px');
  await expect(page.getByRole('button', { name: '复制', exact: true })).toHaveClass(/secondary/);
  await expect(page.getByRole('button', { name: '导出', exact: true })).toHaveClass(/secondary/);
  await expect(page.getByRole('button', { name: '删除', exact: true })).toHaveClass(/danger/);
  await expect(page.getByRole('button', { name: '保存', exact: true })).toHaveClass(/primary/);

  await page.getByLabel('名称').fill('小说总规则（修订）');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByText('提示词已保存。')).toBeVisible();
  expect(savedName).toBe('小说总规则（修订）');

  await page.locator('input[type="file"]').setInputFiles({ name: 'prompt.json', mimeType: 'application/json', buffer: Buffer.from('{"name":"导入提示词"}') });
  await expect(page.getByText('提示词已导入。')).toBeVisible();
  expect(imported).toBe(true);
  await page.getByRole('button', { name: '新建', exact: true }).click();
  await expect(page.getByLabel('名称')).toHaveValue('');
});

test('工程首页保留独立 Dashboard 卡片布局并可进入 Creative Workflow', async ({ page }) => {
  await page.goto('/library');
  await expect(page.locator('.project-library-header').getByRole('heading', { name: '工程', exact: true })).toBeVisible();
  await expect(page.locator('.project-library-header')).toContainText('4 个工程');
  await expect(page.locator('.project-library-page > .page-topbar')).toHaveCount(0);
  await expect(page.locator('.project-list[aria-label="工程列表"]')).toBeVisible();

  const light = await page.locator('.project-library-layout').evaluate((layout) => {
    const detail = layout.querySelector('.project-detail-card')!;
    return {
      layoutBackground: getComputedStyle(layout).backgroundColor,
      layoutBorder: getComputedStyle(layout).borderTopWidth,
      layoutGap: getComputedStyle(layout).gap,
      layoutPaddingTop: getComputedStyle(layout).paddingTop,
      detailBackground: getComputedStyle(detail).backgroundColor,
      detailBorder: getComputedStyle(detail).borderTopWidth,
      detailRadius: getComputedStyle(detail).borderRadius,
      detailAlign: getComputedStyle(detail).alignSelf,
    };
  });
  expect(light).toMatchObject({
    layoutBackground: 'rgba(0, 0, 0, 0)',
    layoutBorder: '0px',
    layoutGap: '20px',
    layoutPaddingTop: '20px',
    detailBorder: '1px',
    detailRadius: '12px',
    detailAlign: 'start',
  });

  for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  }

  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  const darkDetailBackground = await page.locator('.project-detail-card').evaluate((element) => getComputedStyle(element).backgroundColor);
  expect(darkDetailBackground).not.toBe(light.detailBackground);

  const detailHeight = await page.locator('.project-detail-card').evaluate((element) => element.getBoundingClientRect().height);
  expect(detailHeight).toBeLessThanOrEqual(360);

  await page.getByRole('button', { name: '新建工程' }).click();
  await expect(page).toHaveURL(/(?:#)?\/new-project$/);
  await page.goto('/library');
  page.once('dialog', (dialog) => dialog.accept());
  const deleteRequest = page.waitForRequest((request) => request.method() === 'POST' && request.url().endsWith('/api/projects/1/delete'));
  await page.getByRole('button', { name: '删除', exact: true }).click();
  await deleteRequest;

  await page.getByRole('button', { name: '进入工程' }).click();
  await expect(page).toHaveURL(/(?:#)?\/workspace\/1$/);
  await expect(page.locator('.creative-topbar').getByRole('heading', { name: '示例工程' })).toBeVisible();
});

test('工程 Creative Workspace 使用统一 surface 并适配三种桌面尺寸', async ({ page }) => {
  await page.goto('/workspace/1');
  await expect(page.locator('.creative-topbar').getByRole('heading', { name: '示例工程' })).toBeVisible();
  await expect(page.locator('.creative-topbar').getByText('第一章', { exact: true })).toHaveCount(0);
  await expect(page.locator('.chapter-workspace-head')).toHaveCount(0);
  await expect(page.getByText('第1章 · 第一章', { exact: true })).toHaveCount(0);
  const progress = page.locator('.creative-workflow-progress');
  await expect(progress).toBeVisible();
  await expect(progress.getByRole('button')).toHaveCount(6);
  const surfaces = await page.locator('.creative-columns').evaluate((workspace) => ({
    workspace: getComputedStyle(workspace).backgroundColor,
    columns: ['.chapter-rail', '.chapter-workspace', '.creative-context-panel'].map((selector) => getComputedStyle(workspace.querySelector(selector)!).backgroundColor),
    radius: getComputedStyle(workspace).borderRadius,
    progressColumn: getComputedStyle(workspace.querySelector('.creative-workflow-progress')!).gridColumn,
    widths: ['.chapter-rail', '.chapter-workspace', '.creative-context-panel'].map((selector) => workspace.querySelector(selector)!.getBoundingClientRect().width),
  }));
  expect(surfaces.workspace).not.toBe('rgba(0, 0, 0, 0)');
  expect(new Set(surfaces.columns)).toEqual(new Set(['rgba(0, 0, 0, 0)']));
  expect(surfaces.radius).toBe('12px');
  expect(surfaces.progressColumn).toBe('1 / -1');
  expect(surfaces.widths[2]).toBeGreaterThan(300);
  expect(surfaces.widths[2]).toBeGreaterThan(surfaces.widths[0]);
  for (const viewport of [{ width: 1280, height: 720 }, { width: 1440, height: 900 }, { width: 1920, height: 1080 }]) {
    await page.setViewportSize(viewport);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
  }
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
  await expect(page.getByText('自动保存', { exact: false })).toBeVisible();
});

test('模型页保持原有双栏组件和主题交互', async ({ page }) => {
  await page.goto('/models');
  await expect(page.getByRole('heading', { name: '模型', exact: true })).toBeVisible();
  await expect(page.getByText('测试模型', { exact: true })).toBeVisible();
  await expect(page.locator('.model-list-panel')).toBeVisible();
  await expect(page.locator('.model-config-panel')).toBeVisible();
  const lightColumns = await page.locator('.models-layout').evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(lightColumns.split(' ')).toHaveLength(2);
  await page.getByRole('button', { name: '切换到深色模式' }).click();
  const darkColumns = await page.locator('.models-layout').evaluate((element) => getComputedStyle(element).gridTemplateColumns);
  expect(darkColumns).toBe(lightColumns);
  await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
});

test('全局操作按钮沿用模型页 Primary Secondary Danger 视觉基准', async ({ page }) => {
  const buttonStyle = (element: Element) => ({
    background: getComputedStyle(element).backgroundColor,
    border: getComputedStyle(element).borderColor,
    color: getComputedStyle(element).color,
    radius: getComputedStyle(element).borderRadius,
    fontWeight: getComputedStyle(element).fontWeight,
  });
  await page.goto('/models');
  const modelPrimary = await page.getByRole('button', { name: '保存', exact: true }).evaluate(buttonStyle);
  const modelSecondary = await page.getByRole('button', { name: '测试连接', exact: true }).evaluate(buttonStyle);
  const modelDanger = await page.getByRole('button', { name: '删除', exact: true }).evaluate(buttonStyle);

  await page.goto('/prompts');
  expect(await page.getByRole('button', { name: '保存', exact: true }).evaluate(buttonStyle)).toEqual(modelPrimary);
  expect(await page.getByRole('button', { name: '导入', exact: true }).evaluate(buttonStyle)).toEqual(modelSecondary);
  const promptDanger = await page.getByRole('button', { name: '删除', exact: true }).evaluate(buttonStyle);
  expect(promptDanger).toEqual(modelDanger);

  await page.goto('/characters');
  const settings = page.getByRole('button', { name: '角色 AI 提取设置' });
  const settingsSize = await settings.evaluate((element) => ({ width: getComputedStyle(element).width, height: getComputedStyle(element).minHeight }));
  expect(settingsSize).toEqual({ width: '40px', height: '40px' });
});

test('主要 Workspace 可生成深浅主题视觉验收截图', async ({ page }) => {
  const screenshotDirectory = process.env.RUSTY_E2E_SCREENSHOT_DIR;
  await page.setViewportSize({ width: 1440, height: 900 });
  const pages = [
    { key: 'project-home', path: '/library', heading: '工程' },
    { key: 'characters', path: '/characters', heading: '角色卡' },
    { key: 'materials', path: '/materials', heading: '素材库' },
    { key: 'documents', path: '/documents', heading: '文档库' },
    { key: 'prompts', path: '/prompts', heading: '提示词' },
    { key: 'workflow', path: '/workspace/1', heading: '示例工程' },
  ];

  for (const item of pages) {
    await page.goto(item.path);
    await expect(page.getByRole('heading', { name: item.heading, exact: true }).first()).toBeVisible();
    if (item.key === 'materials') await page.locator('.material-book-grid .document-book').first().click();
    if (await page.locator('html').getAttribute('data-theme') === 'dark') {
      await page.getByRole('button', { name: '切换到浅色模式' }).click();
    }
    await page.waitForTimeout(200);
    expect(await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth)).toBe(false);
    if (screenshotDirectory) await page.screenshot({ path: `${screenshotDirectory}/${item.key}-light-1440x900.png` });
    await page.getByRole('button', { name: '切换到深色模式' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.waitForTimeout(200);
    if (screenshotDirectory) await page.screenshot({ path: `${screenshotDirectory}/${item.key}-dark-1440x900.png` });
  }

  await page.goto('/documents');
  if (await page.locator('html').getAttribute('data-theme') === 'dark') {
    await page.getByRole('button', { name: '切换到浅色模式' }).click();
  }
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await expect(page.locator('.document-workspace-layout')).toBeVisible();
  if (screenshotDirectory) await page.screenshot({ path: `${screenshotDirectory}/document-editor-light-1440x900.png` });
});

test('AI 与手动入口分离、设置维度紧凑且编辑器使用标准化设定', async ({ page }) => {
  await page.goto('/characters');
  await expect(page.getByRole('button', { name: 'AI 新建' })).toBeVisible();
  await expect(page.getByRole('button', { name: '手动新建' })).toBeVisible();
  await page.getByRole('button', { name: '角色 AI 提取设置' }).click();
  const settingsDialog = page.getByRole('dialog', { name: '角色提取设置' });
  await expect(settingsDialog.getByLabel('默认模型')).toHaveValue('1');
  await expect(settingsDialog.getByText('查看 Prompt 预览')).toBeVisible();
  await expect(settingsDialog.getByText('最大候选角色数')).toHaveCount(0);
  await expect(settingsDialog.locator('.character-dimension-row')).toHaveCount(1);
  await settingsDialog.getByRole('button', { name: /添加维度/ }).click();
  const dimensionDialog = page.getByRole('dialog', { name: '添加生成维度' });
  await dimensionDialog.getByLabel('维度名称').fill('宗教信仰');
  await dimensionDialog.getByLabel('提取说明').fill('无证据时留空。');
  await dimensionDialog.getByRole('button', { name: '添加' }).click();
  await expect(settingsDialog.getByText('宗教信仰')).toBeVisible();
  await settingsDialog.getByRole('button', { name: '取消' }).click();
  let previewCalls = 0;
  page.on('request', (request) => { if (request.url().includes('/extract/preview')) previewCalls += 1; });
  await page.getByRole('button', { name: '手动新建' }).click();
  const editor = page.getByRole('dialog', { name: '新建角色' });
  await expect(editor.getByLabel('角色名称')).toBeVisible();
  await expect(editor.getByLabel('身份')).toBeVisible();
  await expect(editor.getByLabel('年龄')).toBeVisible();
  await expect(editor.getByLabel('简介')).toHaveAttribute('rows', '4');
  await expect(editor.getByLabel('性格内容')).toBeVisible();
  await expect(editor.locator('input[type="file"]')).toHaveCount(0);
  await expect(editor.getByText('当前封面')).toHaveCount(0);
  await expect(editor.getByRole('button', { name: /添加到工程|保存为公共角色/ })).toHaveCount(0);
  expect(previewCalls).toBe(0);
});

test('统一角色编辑器不显示 scope、封面和工程复制操作', async ({ page }) => {
  await page.goto('/characters');
  await page.locator('.document-character-grid .document-book').first().dblclick();
  const editor = page.getByRole('dialog', { name: '编辑角色' });
  await expect(editor.getByText(/公共角色|工程角色/)).toHaveCount(0);
  await expect(editor.getByRole('button', { name: /添加到工程|保存为公共角色|上传图片/ })).toHaveCount(0);
  await expect(editor.getByText('设定', { exact: true })).toBeVisible();
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

test('全部文档包含工程文档且系统筛选与分类可组合', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toBeVisible();
  const projectCard = page.getByRole('button', { name: '工程原稿，工程作者' });
  await expect(projectCard.locator('.default-book-cover .document-project-marker')).toHaveText('工程');
  await expect(projectCard.locator(':scope > .document-project-marker')).toHaveCount(0);
  await page.locator('.document-tag-panel').getByRole('button', { name: /研究/ }).click();
  await page.locator('.document-tag-panel').getByRole('button', { name: /工程文档/ }).click();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toHaveCount(0);
  await page.locator('.document-tag-panel').getByRole('button', { name: /全部文档/ }).click();
  await expect(page.getByRole('button', { name: /分类：研究/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toBeVisible();
  await page.getByRole('button', { name: '工程原稿，工程作者' }).dblclick();
  await expect(page.locator('textarea.manuscript-editor')).toBeVisible();
  await expect(page.getByText('工程原稿', { exact: true }).first()).toBeVisible();
  await expect(page.getByText('工程文档由工程保存结果同步，此处为只读工作区。')).toBeVisible();
  await expect(page.getByRole('button', { name: '保存', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '新增章节', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '导出文档', exact: true })).toHaveCount(1);
});

test('我的分类加号只打开轻量新建分类弹窗', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '新建文档分类' }).click();
  const dialog = page.getByRole('dialog', { name: '新建分类' });
  await expect(dialog.getByLabel('分类名称')).toBeVisible();
  await expect(dialog.getByRole('checkbox')).toHaveCount(0);
  await expect(dialog.getByText('管理分类')).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '保存关联' })).toHaveCount(0);
  await expect(dialog.getByRole('button', { name: '新建' })).toBeVisible();
});

test('文档详情只保留标签、导出和删除操作', async ({ page }) => {
  await page.goto('/documents');
  const detail = page.locator('.document-detail-panel');
  await expect(detail.getByText('分类', { exact: true })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '编辑', exact: true })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: 'AI 分析', exact: true })).toHaveCount(0);
  await expect(detail.getByRole('button', { name: '导出文档', exact: true })).toBeVisible();
  await expect(detail.getByRole('button', { name: '删除', exact: true })).toBeVisible();
  await expect(detail.locator('footer .button')).toHaveCount(2);
});

test('最近导入排除工程自动同步文档', async ({ page }) => {
  await page.goto('/documents');
  await page.locator('.document-tag-panel').getByRole('button', { name: /最近导入/ }).click();
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '工程原稿，工程作者' })).toHaveCount(0);
});

test('分类标签和搜索按交集筛选且标签胶囊不修改关联', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.locator('.document-detail-panel').getByText('分类', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '管理当前文档分类' })).toHaveCount(0);
  await page.locator('.document-tag-panel').getByRole('button', { name: /研究/ }).click();
  await page.locator('.document-detail-panel').getByRole('button', { name: '长篇', exact: true }).click();
  await page.locator('.document-detail-panel').getByRole('button', { name: '历史', exact: true }).click();
  await page.getByRole('searchbox', { name: '搜索文档' }).fill('示例');
  await expect(page.getByRole('button', { name: '示例长篇，作者' })).toBeVisible();
  await expect(page.getByRole('button', { name: '普通资料，资料作者' })).toHaveCount(0);
  expect(tagAssignmentRequests).toHaveLength(0);
  await expect(page.getByRole('button', { name: /分类：研究/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /标签：长篇/ })).toHaveCount(0);
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '长篇', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '历史', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await page.locator('.document-detail-panel').getByRole('button', { name: '历史', exact: true }).click();
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '历史', exact: true })).toHaveAttribute('aria-pressed', 'false');
});

test('标签管理弹窗显式移除关联并显示文档库存储目录', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByText('文档库存储目录', { exact: true })).toBeVisible();
  await expect(page.getByText('D:/Rusty', { exact: true })).toBeVisible();
  await expect(page.getByText('D:/Rusty/novel-v2.txt', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '管理当前文档标签' }).click();
  const dialog = page.getByRole('dialog', { name: '管理标签' });
  await dialog.getByRole('checkbox', { name: '长篇' }).uncheck();
  await expect(dialog.getByRole('button', { name: '保存关联' })).toHaveCount(0);
  expect(tagAssignmentRequests).toEqual([{ documentId: 1, tagId: 21, selected: false }]);
  await expect(page.locator('.document-detail-panel').getByRole('button', { name: '长篇', exact: true })).toHaveCount(0);
  await dialog.getByRole('button', { name: '关闭', exact: true }).click();
});

test('文档正文右键菜单、编辑命令与统一分章入口', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const chapterLayout = await page.locator('.chapter-row').first().evaluate((row) => {
    const ordinal = row.querySelector('.chapter-number')!;
    const title = row.querySelector('.chapter-name')!;
    const words = row.querySelector('.chapter-state')!;
    return {
      ordinal: ordinal.textContent,
      ordinalWhiteSpace: getComputedStyle(ordinal).whiteSpace,
      titleOverflow: getComputedStyle(title).textOverflow,
      wordsWhiteSpace: getComputedStyle(words).whiteSpace,
      rowColumns: getComputedStyle(row).gridTemplateColumns,
    };
  });
  expect(chapterLayout).toMatchObject({ ordinal: '第一章', ordinalWhiteSpace: 'nowrap', titleOverflow: 'ellipsis', wordsWhiteSpace: 'nowrap' });
  expect(chapterLayout.rowColumns.split(' ')).toHaveLength(3);
  const inspector = page.locator('.document-workspace-inspector');
  for (const removedHeading of ['文档处理', '选择操作', '编辑操作', '正文命令']) {
    await expect(inspector.getByText(removedHeading, { exact: true })).toHaveCount(0);
  }
  for (const action of ['合并文档', '新增章节', '分章', '文字整理', '版本记录', '导出文档']) {
    await expect(inspector.getByRole('button', { name: action, exact: true })).toBeVisible();
  }
  for (const removed of ['标记章节', '撤销', '重做']) await expect(inspector.getByRole('button', { name: removed, exact: true })).toHaveCount(0);
  const editor = page.locator('textarea.manuscript-editor');
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await expect(page.getByRole('button', { name: '添加为作者风格来源' })).toBeVisible();
  await expect(page.getByRole('button', { name: '添加为剧情骨架来源' })).toBeVisible();
  await expect(page.getByRole('button', { name: '提取角色卡' })).toBeVisible();
  await editor.click({ position: { x: 20, y: 20 } });
  await expect(page.getByRole('button', { name: '添加为作者风格来源' })).toHaveCount(0);
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await page.getByRole('button', { name: '添加为作者风格来源' }).click();
  await expect(page).toHaveURL(/\/materials$/);
  await expect(page.getByRole('dialog').filter({ hasText: '新建作者风格' })).toBeVisible();
  await expect(page.getByLabel('来源文本')).not.toHaveValue('');
  await page.getByRole('button', { name: /AI 提取/ }).click();
  await expect(page.getByLabel('概览')).toBeVisible();
  await page.getByRole('button', { name: '取消' }).last().click();
  await page.goBack();
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await expect(page.getByRole('button', { name: '标记章节', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '分章', exact: true })).toHaveCount(1);
  await expect(page.getByRole('button', { name: 'AI 分章', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '正则分章', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '引用范围', exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: '分章', exact: true }).click();
  await expect(page.getByRole('button', { name: '光标处分章' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI 分章' })).toBeVisible();
  await expect(page.getByRole('button', { name: '正则识别' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '手动标记' })).toHaveCount(0);
});

test('文档选区进入单人物 AI 新建并保留来源文本', async ({ page }) => {
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
  const dialog = page.getByRole('dialog', { name: 'AI 新建角色' });
  await expect(dialog.getByLabel('来源文本')).toHaveValue('林舟推门');
  await expect(dialog.getByRole('button', { name: '开始提取' })).toBeDisabled();
  await dialog.getByLabel('角色名称 *').fill('林舟');
  await expect(dialog.getByRole('button', { name: '开始提取' })).toBeEnabled();
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
  await page.getByRole('button', { name: '关闭', exact: true }).click();
  await page.getByRole('button', { name: '文字整理' }).click();
  const cleanupDialog = page.getByRole('dialog').filter({ hasText: '文字整理' });
  await expect(cleanupDialog).toBeVisible();
  await expect(cleanupDialog.getByText('版本记录')).toHaveCount(0);
  await expect(cleanupDialog.getByText('章节缩进')).toHaveCount(0);
  await expect(cleanupDialog.getByText('章节标题正则')).toHaveCount(0);
  await expect(cleanupDialog.getByLabel('整理提示词')).toBeVisible();
  await expect(cleanupDialog.getByLabel('具体要求')).toContainText('禁止改剧情');
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/document-cleanup-dialog.png` });
  }
});

test('章节标题、实时字数及原生输入撤销保持同步', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  const title = page.locator('.document-editor-title input');
  await editor.focus();
  const editorLayout = await editor.evaluate((node) => {
    const styles = getComputedStyle(node);
    const editorRect = node.getBoundingClientRect();
    const contentRect = node.closest('.document-workspace-content')!.getBoundingClientRect();
    return {
      boxShadow: styles.boxShadow,
      bottomGap: Math.round(contentRect.bottom - editorRect.bottom),
      outlineStyle: styles.outlineStyle,
    };
  });
  expect(editorLayout.outlineStyle).toBe('none');
  expect(editorLayout.boxShadow).toBe('none');
  expect(Math.abs(editorLayout.bottomGap)).toBeLessThanOrEqual(1);
  const headingLayout = await page.locator('.document-editor-heading').evaluate((node) => {
    const heading = node.getBoundingClientRect();
    const titleRect = node.querySelector('.document-editor-title')!.getBoundingClientRect();
    const saveRect = node.querySelector('.button')!.getBoundingClientRect();
    return {
      centerDelta: Math.abs((titleRect.left + titleRect.width / 2) - (heading.left + heading.width / 2)),
      saveRightGap: Math.abs(heading.right - saveRect.right - 18),
    };
  });
  expect(headingLayout.centerDelta).toBeLessThanOrEqual(1);
  expect(headingLayout.saveRightGap).toBeLessThanOrEqual(1);
  await expect(page.locator('.document-workspace-text').getByText('正文', { exact: true })).toHaveCount(0);
  await title.fill('即时新标题');
  await expect(page.locator('.chapter-list').getByText('即时新标题')).toBeVisible();
  await editor.fill('中文 A，🙂');
  await expect(page.locator('.document-workspace-stats').getByText('5', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '撤销', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '重做', exact: true })).toHaveCount(0);
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
  await expect(dialog.getByText('文档处理')).toHaveCount(0);
  await dialog.getByLabel('章节标题').fill('插入的新章');
  await dialog.getByLabel('插入位置').selectOption('after-index');
  await dialog.getByLabel('指定章节', { exact: true }).selectOption('1');
  await dialog.getByLabel('正文').fill('新增正文');
  await dialog.getByRole('button', { name: '保存为新版本' }).click();
  await expect(page.locator('.chapter-row[aria-current="page"]').getByText('插入的新章')).toBeVisible();
  await expect(page.locator('.chapter-row[aria-current="page"]').getByText('第二章')).toBeVisible();
  await expect(page.locator('.document-editor-title input')).toHaveValue('插入的新章');
});

test('光标处分章只要求下一章标题并自动选中新章节', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(4, 4);
    node.dispatchEvent(new Event('select', { bubbles: true }));
  });
  await page.getByRole('button', { name: '分章', exact: true }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: '光标处分章' });
  await expect(dialog.getByText('正则识别')).toHaveCount(0);
  await expect(dialog.getByText('手动标记')).toHaveCount(0);
  await dialog.getByLabel('下一章标题').fill('光标新章');
  await expect(dialog.getByText('第 4 字')).toBeVisible();
  await dialog.getByRole('button', { name: '分章', exact: true }).click();
  await expect(page.locator('.chapter-row[aria-current="page"]').getByText('光标新章')).toBeVisible();
  await expect(page.locator('.document-editor-title input')).toHaveValue('光标新章');
});

test('工作台右栏直接编辑书名和作者并同步统一元数据', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByLabel('书名').fill('统一书名');
  await page.getByLabel('书名').blur();
  await page.getByLabel('作者').fill('新作者');
  await page.getByLabel('作者').blur();
  await expect(page.getByText('书名和作者已同步保存。')).toBeVisible();
  await page.getByRole('button', { name: /返回文档库/ }).click();
  await expect(page.getByRole('button', { name: '统一书名，新作者' })).toBeVisible();
});

test('新增无标题章节仍按目录顺序显示章节序号', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '新增章节' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: '新增章节' });
  await dialog.getByLabel('插入位置').selectOption('after-index');
  await dialog.getByLabel('指定章节', { exact: true }).selectOption('1');
  await dialog.getByRole('button', { name: '保存为新版本' }).click();
  const selected = page.locator('.chapter-row[aria-current="page"]');
  await expect(selected.getByText('第二章')).toBeVisible();
  await expect(selected.getByText('未命名')).toBeVisible();
  await expect(page.locator('.document-editor-title input')).toHaveValue('');
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

test('合并弹窗直接选择文档且合并结果保留卷目录', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '合并文档' }).click();
  const dialog = page.getByRole('dialog').filter({ hasText: '合并文档' });
  await expect(dialog.getByRole('heading', { name: '研究' })).toHaveCount(0);
  await expect(dialog.getByText('工程原稿')).toBeVisible();
  await dialog.getByText('普通资料').locator('..').getByRole('button', { name: '添加' }).click();
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

test('普通工程不再通过旧场景改写 modal 开始工作', async ({ page }) => {
  await page.goto('/workspace/1');
  await expect(page.getByLabel('章节导航')).toBeVisible();
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
  await expect(page.getByRole('button', { name: '场景改写' })).toHaveCount(0);
  await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('普通工作台启动不发送旧场景规划或执行请求', async ({ page }) => {
  const legacyWorkflowRequests: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path.includes('/workflow/start') || path.includes('/scene-workflows/') || path.includes('/rewrite-plans/')) legacyWorkflowRequests.push(path);
  });
  await page.goto('/workspace/1');
  await expect(page.getByRole('button', { name: /发现钥匙/ })).toBeVisible();
  expect(legacyWorkflowRequests).toHaveLength(0);
  expect(workflowPlanRequests).toHaveLength(0);
});

test('预分析阶段不会提前解锁目标设计', async ({ page }) => {
  await page.goto('/workspace/1');
  await expect(page.getByRole('button', { name: /发现钥匙/ })).toContainText('进行中');
  await expect(page.getByRole('button', { name: '目标设计' })).toBeDisabled();
  await expect(page.getByRole('button', { name: '写作' })).toBeDisabled();
});
