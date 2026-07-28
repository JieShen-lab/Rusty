import { expect, test, type Page } from '@playwright/test';

const projects = [{ id: 1, name: '示例工程', author: '', status: 'ready', source_format: 'txt', total_chapters: 1, total_words: 100, processed_chapters: 0, progress_percent: 0, created_at: '', updated_at: '' }];
const tags = [{ id: 1, name: '主角', normalized_name: '主角', sort_order: 0, resource_count: 1 }];
const materials = [
  { id: 1, material_type: 'scene_reference', scope: 'public', project_id: null, project_name: null, name: '雨夜追逐', description: '雨夜动作参考', detail_level: 'standard', raw_text: '', content: {}, analysis_status: 'unanalyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [] },
  { id: 2, material_type: 'plot_skeleton', scope: 'public', project_id: null, project_name: null, name: '误会解除', description: '事件骨架', detail_level: 'standard', raw_text: '', content: {}, analysis_status: 'analyzed', source_metadata: {}, import_metadata: {}, source_material_id: null, source_version: null, timeline_start_chapter: null, timeline_end_chapter: null, sort_order: 0, version: 1, created_at: '', updated_at: '', tags: [] },
];
const documentItem = { id: 1, title: '示例长篇', author: '作者', description: null, source_filename: 'novel.txt', source_format: 'txt', storage_path: 'novel.txt', source_size_bytes: 100, stored_size_bytes: 100, chapter_count: 1, word_count: 16, status: 'ready', favorite: false, tags: [], created_at: '', updated_at: '' };

const sceneHistory = [{ id: 8, version: 1, revision_kind: 'rewrite', parent_version_id: null as number | null, created_at: '2026-07-28', rewritten_text: '林舟推门而入。' }];
let workflowPlanRequests: Array<Record<string, unknown>> = [];

async function mockApi(page: Page) {
  let skeletonNodes: Array<Record<string, unknown>> = [{ id: 'n1', event: '发现钥匙' }];
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const url = new URL(route.request().url());
    const path = url.pathname;
    let body: unknown = [];
    if (path === '/api/projects') body = projects;
    else if (path === '/api/character-tags' || path === '/api/material-tags') body = tags;
    else if (path === '/api/characters') body = [{
      id: 1, name: '林舟', aliases: [], description: '', priority: 50, is_main: true, relationship_notes: '', personality: '', speech_style: '', action_constraints: '', anti_ooc_rules: '', profile: {}, source_metadata: {}, import_metadata: {}, scope: 'public', project_id: null, source_character_card_id: null, source_version: null, version: 1, sort_order: 0, identity: '', age: '', setting_text: '', custom_fields: [], raw_text: '林舟推门而入。', analysis_status: 'unanalyzed', cover_path: null, cover_updated_at: null, tags: ['主角'], created_at: '', updated_at: '',
    }];
    else if (path === '/api/materials') body = materials;
    else if (/^\/api\/materials\/1\/analyze$/.test(path)) body = { material_id: 1, model_id: 1, invocation_id: 9, existing: {}, proposal: { summary: '模型分析摘要' } };
    else if (/^\/api\/materials\/1\/analysis\/apply$/.test(path)) body = { ...materials[0], analysis_status: 'analyzed', content: { summary: '模型分析摘要' } };
    else if (path === '/api/materials/import-json') body = { imported: [{ index: 0, id: 3, name: '导入场景', material_type: 'scene_reference' }], errors: [] };
    else if (path === '/api/documents') body = [documentItem];
    else if (path === '/api/document-tags') body = [];
    else if (path === '/api/document-library/settings') body = { storage_path: 'D:/Rusty', exists: true };
    else if (path === '/api/document-processing-templates') body = [];
    else if (path === '/api/documents/1/revisions') body = [{ id: 1, document_id: 1, revision_number: 1, revision_type: 'import', storage_path: 'novel.txt', word_count: 16, created_at: '' }];
    else if (path === '/api/documents/1/chapters') body = [{ id: 1, document_id: 1, revision_id: 1, index: 1, title: '第一章', start_line: 1, end_line: 2, start_offset: 0, end_offset: 16, word_count: 16 }];
    else if (path === '/api/documents/1/content') body = { document_id: 1, revision_id: 1, chapter_id: 1, title: '第一章', text: '林舟推门而入，看见桌上的钥匙。', start_offset: 0, end_offset: 16 };
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

test('素材 JSON 导入预览与真实 AI 分析 mock 流程', async ({ page }) => {
  await page.goto('/materials');
  await page.getByRole('button', { name: '导入', exact: true }).click();
  await page.locator('textarea').fill('[{"material_type":"scene_reference","name":"导入场景","tags":["雨夜"]}]');
  await expect(page.getByText('导入场景', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '确认批量导入' }).click();
  await expect(page.getByText(/已导入 1 条素材/)).toBeVisible();
  await page.getByText('雨夜追逐', { exact: true }).first().click();
  await page.getByRole('button', { name: /AI 分析/ }).last().click();
  await expect(page.getByText(/模型分析建议已生成/)).toBeVisible();
  await page.getByRole('button', { name: '确认应用' }).click();
  await expect(page.getByText(/结构化分析建议已确认并保存/)).toBeVisible();
});

test('角色空字段提醒、自定义字段排序和封面入口', async ({ page }) => {
  await page.goto('/characters');
  await page.getByRole('button', { name: '编辑' }).click();
  await expect(page.getByText('自定义封面')).toBeVisible();
  await page.getByRole('button', { name: '新增字段' }).click();
  await page.getByPlaceholder('字段名').fill('习惯');
  await page.getByRole('button', { name: '保存', exact: true }).click();
  await expect(page.getByRole('dialog', { name: '空字段保存提醒' })).toBeVisible();
});

test('文档库在常用桌面窗口无横向溢出', async ({ page }) => {
  await page.goto('/documents');
  await expect(page.getByText('文档库', { exact: true }).first()).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth);
  expect(overflow).toBe(false);
});

test('文档正文右键菜单、手动章节标记与 AI 分章入口', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.evaluate((node: HTMLTextAreaElement) => {
    node.focus();
    node.setSelectionRange(0, 4);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: 500, clientY: 300 }));
  });
  await expect(page.getByRole('button', { name: '添加为场景素材' })).toBeVisible();
  await expect(page.getByRole('button', { name: '添加为剧情骨架' })).toBeVisible();
  await expect(page.getByRole('button', { name: '添加到公共角色卡' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: '标记章节开始' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'AI 分章' })).toBeVisible();
});

test('未保存正文取消切换后仍保留编辑内容', async ({ page }) => {
  await page.goto('/documents');
  await page.getByRole('button', { name: '示例长篇，作者' }).dblclick();
  const editor = page.locator('textarea.manuscript-editor');
  await editor.fill('未保存内容-UNIQUE');
  page.once('dialog', (dialog) => dialog.dismiss());
  await page.getByRole('button', { name: '文字整理' }).click();
  await expect(editor).toHaveValue('未保存内容-UNIQUE');
  await expect(page.getByText(/未保存/).first()).toBeVisible();
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
