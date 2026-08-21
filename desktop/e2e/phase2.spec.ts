import { expect, test, type Page } from '@playwright/test';

const projects = [
  { id: 1, name: '示例工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-29 12:00:00' },
  { id: 2, name: '北境工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-28 12:00:00' },
  { id: 3, name: '旧城工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-27 12:00:00' },
  { id: 4, name: '海港工程', author: '', status: 'ready', current_stage: 'imported', progress: 0, source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '2026-07-26 12:00:00' },
];
const tags = [{ id: 1, name: '动作', normalized_name: '动作', sort_order: 0, resource_count: 1 }];
const materials = [
  { id: 1, material_type: 'author_style', scope: 'public', project_id: null, project_name: null, name: '沈砚', description: '擅长都市悬疑叙事。', detail_level: 'standard', raw_text: '雨落在屋檐。', content: { schema_version: 2, author_name: '沈砚', introduction: '擅长都市悬疑叙事。', source_works: ['雨夜旧城'], overall_style: '冷静短句推进，重视环境细节。', summary: '冷静短句推进，重视环境细节。', dimensions: [{ id: 'sentence-features', name: '句子特征', requirement: '分析句式', analysis: '短句推进动作', features: ['短句'], examples: ['雨落在屋檐。'] }] }, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [], general_tags: [], applicable_scene_tags: [], category_ids: [], categories: [], source_summary: { kind: 'manual', label: '本地创建' } },
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

let tagAssignmentRequests: Array<{ documentId: number; tagId: number; selected: boolean }> = [];

async function mockApi(page: Page) {
  let documentItems = baseDocumentItems.map((item) => ({ ...item, tags: [...item.tags], category_ids: [...item.category_ids], categories: [...item.categories] }));
  let documentDraft: { id: number; document_id: number; chapter_id: number | null; base_revision_id: number; title: string; text: string; updated_at: string } | null = null;
  let documentRevisionNumber = 1;
  let documentBody = '林舟推门而入，看见桌上的钥匙。';
  let materialItems = materials.map((item) => ({ ...item, content: structuredClone(item.content) }));
  let materialSettings = [
    { task_type: 'author_style_extraction', model_id: 1, detail_level: 'standard', system_prompt: '分析作者风格。', base_instruction: '分析具体写法。', dimensions: [{ id: 'sentence-features', name: '句子特征', requirement: '分析句式' }], extra_requirements: '', prompt_preview: '分析作者风格', updated_at: '' },
  ];
  let documentChapterTitle = '';
  let volumeTitle = '第七卷 雨夜';
  let extraChapter: { id: number; document_id: number; revision_id: number; index: number; title: string; start_line: number; end_line: number; start_offset: number; end_offset: number; word_count: number; volume_id: number } | null = null;
  let extraChapterBody = '新增正文';
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = [];
    if (path === '/api/projects') body = projects;
    else if (path === '/api/material-tags') body = tags;
    else if (path === '/api/models') body = [{ id: 1, display_name: '测试模型', provider: 'openai_compatible', base_url: '', model_name: 'test', is_default: true, created_at: '', updated_at: '' }];
    else if (path === '/api/projects/1/materials') body = materials.filter((item) => !url.searchParams.get('material_type') || item.material_type === url.searchParams.get('material_type')).map((item) => ({
      ...item,
      general_tags: item.tags,
      applicable_scene_tags: [],
      category_ids: [],
      categories: [],
      source_summary: { kind: 'manual', label: '本地创建' },
    }));
    else if (path === '/api/material-categories') body = [];
    else if (path === '/api/material-ai-settings') body = materialSettings;
    else if (path === '/api/material-ai-settings/author_style_extraction') {
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
    else if (/^\/api\/documents\/\d+\/chapters\/\d+$/.test(path) && route.request().method() === 'DELETE') {
      const documentId = Number(path.split('/')[3]);
      const chapterId = Number(path.split('/')[5]);
      if (chapterId === 999) extraChapter = null;
      documentRevisionNumber += 1;
      documentItems = documentItems.map((item) => item.id === documentId ? { ...item, chapter_count: 1 } : item);
      body = { document: documentItems.find((item) => item.id === documentId), revision: { id: documentId * 10 + documentRevisionNumber, document_id: documentId, revision_number: documentRevisionNumber, revision_type: 'manual_edit', storage_path: `D:/Rusty/novel-v${documentRevisionNumber}.txt`, template_id: null, parent_revision_id: documentId * 10 + documentRevisionNumber - 1, created_at: '' }, created: true };
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
    else if (path === '/api/projects/1/materials') body = [];
    else if (path === '/api/chapters/1') body = { chapter: { id: 1, project_id: 1, index: 1, title: '第一章', original_text: '林舟推门而入，看见桌上的钥匙。', rewritten_text: '', word_count: 16, status: 'pending', created_at: '', updated_at: '' }, ai_outputs: { plot_summary: '林舟进入房间并发现钥匙。', expanded_plot: '', plot_characters: [{ name: '林舟', role_in_chapter: '发现线索' }], key_events: ['进入房间', '发现钥匙'], style_analysis: {}, reviewed_style_analysis: {}, style_analysis_status: '' } };
    else if (path === '/api/chapters/1/workflow') body = { chapter_id: 1, strategy: null, current_stage: 'not_started', source_base_kind: 'original', source_base_version_id: null, source_hash: null, source_changed: false, updated_at: '' };
    else if (path.includes('/prompt-preview')) body = { ruleset_id: 'test', provenance: {}, expected_output: 'text', messages: [] };
    else if (path.includes('/generation-attempts')) body = [];
    else if (path === '/api/prompt-definitions') body = [
      { id: 101, name: '系统提示词', description: '所有任务最高优先级携带', kind: 'master', workflow_key: null, task_key: null, content: '保持上下文一致。', input_description: '所有章节任务', is_default: true, created_at: '', updated_at: '' },
      { id: 102, name: '内容总结', description: '进入工程后的第一步', kind: 'common_task', workflow_key: null, task_key: 'chapter_summary', content: '提取章节事实。', input_description: '章节原文', is_default: true, created_at: '', updated_at: '' },
      { id: 103, name: '调整剧情', description: '生成原始与目标大纲', kind: 'workflow_task', workflow_key: 'plot_adjust', task_key: 'special_analysis', content: '识别需调整的章节片段。', input_description: '章节原文、具体要求', is_default: true, created_at: '', updated_at: '' },
      { id: 104, name: '增加剧情', description: '设计新的下一章', kind: 'workflow_task', workflow_key: 'expansion', task_key: 'special_analysis', content: '设计承接章节。', input_description: '整本小说原文、具体要求', is_default: true, created_at: '', updated_at: '' },
      { id: 105, name: '重写剧情', description: '生成重写后的剧情大纲', kind: 'workflow_task', workflow_key: 'plot_rewrite', task_key: 'special_analysis', content: '重写章节事件链。', input_description: '章节原文、具体要求', is_default: true, created_at: '', updated_at: '' },
      { id: 106, name: '写作', description: '三个方向共用的正文规则', kind: 'common_task', workflow_key: null, task_key: 'writing', content: '按目标大纲写作。', input_description: '程序按方向组合原文、新大纲和作者风格', is_default: true, created_at: '', updated_at: '' },
    ];
    else if (path === '/api/prompts' || path === '/api/analysis-prompts' || path === '/api/projects/1/export-plan') body = [];
    else if (path === '/api/projects/1/style-synthesis') body = { prompt_template_id: null };
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
}

test.beforeEach(async ({ page }) => {
  tagAssignmentRequests = [];
  page.on('pageerror', (error) => console.error(`pageerror: ${error.message}`));
  page.on('console', (message) => {
    if (message.type() === 'error') console.error(`console: ${message.text()}`);
  });
  await mockApi(page);
});

test('提示词菜单严格对应六个工程流程槽位并可保存', async ({ page }) => {
  let savedContent = '';
  await page.route('http://127.0.0.1:8765/api/prompt-definitions/101', async (route) => {
    const payload = route.request().postDataJSON() as Record<string, unknown>;
    savedContent = String(payload.content ?? '');
    await route.fulfill({ contentType: 'application/json', status: 200, body: JSON.stringify({ id: 101, ...payload, created_at: '', updated_at: '' }) });
  });

  await page.goto('/prompts');
  await expect(page.locator('.prompt-definition-page > .page-topbar').getByRole('heading', { name: '提示词' })).toBeVisible();
  const menu = page.locator('.fixed-prompt-menu > button');
  await expect(menu).toHaveCount(6);
  await expect(menu).toHaveText([/系统提示词/, /内容总结/, /调整剧情/, /增加剧情/, /重写剧情/, /写作/]);
  await expect(page.getByText('最高优先级', { exact: true })).toBeVisible();
  await expect(page.getByText('作者风格提取继续使用作者页面中的提取设置')).toBeVisible();
  await page.getByLabel('提示词正文').fill('始终先遵守系统规则。');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByText('提示词已保存。')).toBeVisible();
  expect(savedContent).toBe('始终先遵守系统规则。');
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

test('作者页以一位作者一份档案展示完整信息', async ({ page }) => {
  await mockApi(page);
  await page.goto('/authors');
  await expect(page.getByRole('heading', { name: '作者档案' })).toBeVisible();
  await page.getByText('沈砚', { exact: true }).first().click();
  await expect(page.locator('.material-detail-panel').getByText('擅长都市悬疑叙事。')).toBeVisible();
  await expect(page.locator('.author-work-list').getByText('雨夜旧城', { exact: true })).toBeVisible();
  await expect(page.locator('.material-detail-panel').getByText('冷静短句推进，重视环境细节。')).toBeVisible();
  await expect(page.getByText('句子特征')).toBeVisible();
  await expect(page.getByText('素材库', { exact: true })).toHaveCount(0);
  await expect(page.locator('.material-library-sidebar')).toHaveCount(0);
  await expect(page.locator('.material-library-unified')).toHaveCSS('grid-template-columns', /\S+px \S+px/);
  await expect(page.locator('.author-cover img')).toHaveCount(0);
  await expect(page.locator('.author-cover').first()).toBeVisible();
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/author-library.png` });
  }
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

test('文档工作区章节序号与标题分两行并提供分卷按钮', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await expect(page.getByRole('button', { name: '新建分卷' })).toBeVisible();
  const row = page.locator('.chapter-row').first();
  const layout = await row.evaluate((node) => {
    const number = node.querySelector('.chapter-number')!.getBoundingClientRect();
    const name = node.querySelector('.chapter-name')!.getBoundingClientRect();
    return { numberBottom: number.bottom, nameTop: name.top };
  });
  expect(layout.nameTop).toBeGreaterThanOrEqual(layout.numberBottom - 1);
  await expect(row.locator('.chapter-number')).toHaveText('第一章');
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/document-volume-workspace.png` });
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
  await expect(cleanupDialog.getByText('整理范围', { exact: true })).toBeVisible();
  await expect(cleanupDialog.getByRole('checkbox')).toHaveCount(1);
  await expect(cleanupDialog.getByRole('checkbox')).toBeChecked();
  await expect(cleanupDialog.getByText('待处理', { exact: true })).toBeVisible();
  await expect(cleanupDialog.getByLabel('具体要求')).toContainText('禁止改剧情');
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/document-cleanup-dialog.png` });
  }
});

test('本章搜索只计算当前正文并支持循环前后跳转', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '本章搜索' }).click();
  const search = page.locator('.chapter-search-bar input');
  await search.fill('林舟');
  await expect(page.getByText('1 / 1', { exact: true })).toBeVisible();
  await search.press('Enter');
  const selection = await page.locator('textarea.manuscript-editor').evaluate((node: HTMLTextAreaElement) => ({
    text: node.value.slice(node.selectionStart, node.selectionEnd),
    start: node.selectionStart,
  }));
  expect(selection.text).toBe('林舟');
  await search.press('Shift+Enter');
  await expect(page.getByText('1 / 1', { exact: true })).toBeVisible();
  await search.press('Escape');
  await expect(search).toHaveCount(0);
});

test('章节右键删除需确认并在删除当前章后选择相邻章节', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '新增章节' }).click();
  const addDialog = page.getByRole('dialog').filter({ hasText: '新增章节' });
  await addDialog.getByLabel('章节标题').fill('待删除章节');
  await addDialog.getByLabel('正文').fill('临时正文');
  await addDialog.getByRole('button', { name: '保存为新版本' }).click();
  const deleting = page.locator('.chapter-row').filter({ hasText: '待删除章节' });
  await deleting.click({ button: 'right' });
  await expect(page.getByRole('menuitem', { name: '删除章节' })).toBeVisible();
  page.once('dialog', async (dialog) => {
    expect(dialog.message()).toContain('待删除章节');
    await dialog.accept();
  });
  await page.getByRole('menuitem', { name: '删除章节' }).click();
  await expect(page.locator('.chapter-row').filter({ hasText: '待删除章节' })).toHaveCount(0);
  await expect(page.locator('.chapter-row').first()).toHaveAttribute('aria-current', 'page');
});

test('文字整理范围默认当前章并可同时选择任意多章', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  await page.getByRole('button', { name: '新增章节' }).click();
  const addDialog = page.getByRole('dialog').filter({ hasText: '新增章节' });
  await addDialog.getByLabel('章节标题').fill('第二章');
  await addDialog.getByLabel('正文').fill('第二章正文');
  await addDialog.getByRole('button', { name: '保存为新版本' }).click();
  await page.getByRole('button', { name: '文字整理' }).click();
  const dialog = page.getByRole('dialog', { name: '文字整理' });
  const checks = dialog.getByRole('checkbox');
  await expect(checks).toHaveCount(2);
  await expect(checks.nth(0)).not.toBeChecked();
  await expect(checks.nth(1)).toBeChecked();
  await checks.nth(0).check();
  await expect(checks.nth(0)).toBeChecked();
  await expect(checks.nth(1)).toBeChecked();
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
    const titleInput = node.querySelector('.document-editor-title input')!.getBoundingClientRect();
    const saveRect = node.querySelector('.document-save-button')!.getBoundingClientRect();
    return {
      titleLeftGap: Math.abs(titleRect.left - heading.left - 18),
      titleInputWidth: titleInput.width,
      titleInputHeight: titleInput.height,
      saveRightGap: Math.abs(heading.right - saveRect.right - 18),
    };
  });
  expect(headingLayout.titleLeftGap).toBeLessThanOrEqual(1);
  expect(headingLayout.titleInputWidth).toBeGreaterThan(300);
  expect(headingLayout.titleInputHeight).toBeLessThanOrEqual(36);
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
  await page.getByRole('textbox', { name: '作者' }).fill('新作者');
  await page.getByRole('textbox', { name: '作者' }).blur();
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

test('普通工作台启动不发送旧场景规划或执行请求', async ({ page }) => {
  const legacyWorkflowRequests: string[] = [];
  page.on('request', (request) => {
    const path = new URL(request.url()).pathname;
    if (path.includes('/workflow/start') || path.includes('/scene-workflows/') || path.includes('/rewrite-plans/')) legacyWorkflowRequests.push(path);
  });
  await page.goto('/workspace/1');
  await expect(page.getByRole('button', { name: /第一章/ })).toBeVisible();
  await expect(page.getByRole('button', { name: /发现钥匙/ })).toHaveCount(0);
  expect(legacyWorkflowRequests).toHaveLength(0);
});
