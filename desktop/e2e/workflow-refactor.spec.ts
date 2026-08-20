import { expect, test, type Page } from '@playwright/test';

const chapter = {
  id: 901, project_id: 99, index: 1, title: '第一章',
  original_text: '雨落在旧城的屋檐上。', rewritten_text: null,
  word_count: 11, status: 'imported', start_line: 1, end_line: 1,
};

function projectDetail() {
  return {
    project: {
      id: 99, name: '章节工作流测试工程', project_kind: 'rewrite', status: 'ready',
      current_stage: 'imported', source_format: 'txt', total_chapters: 1, total_words: 11,
      completed_chapters: 0, book_title: '测试小说', author: null, created_at: '',
      updated_at: '', progress: 0,
    },
    metadata: {}, settings: { processing_mode: 'manual' }, exports: [],
  };
}

async function mockCurrentWorkspace(page: Page, sourceChanged = false) {
  const requests: string[] = [];
  await page.route('http://127.0.0.1:8765/api/**', async (route) => {
    const path = new URL(route.request().url()).pathname;
    requests.push(path);
    let body: unknown;
    if (path === '/api/projects/99') body = projectDetail();
    else if (path === '/api/projects/99/chapters') body = [chapter];
    else if (path === '/api/materials') body = [];
    else if (path === '/api/chapters/901') {
      body = { chapter, ai_outputs: {}, stage_statuses: [], errors: [] };
    } else if (path === '/api/chapters/901/workflow') {
      body = {
        chapter_id: 901, strategy: 'plot_adjust', current_stage: 'direction',
        source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash',
        source_changed: sourceChanged, summary: { chapter_id: 901, plot_summary: '旧城雨夜里，主人公发现了线索。', main_characters: ['主人公'], key_events: ['发现线索'], relationships: [], start_state: {}, end_state: {}, important_facts: ['雨夜发生'], open_threads: ['线索来源'], source_hash: 'source-hash', updated_at: '' },
        direction: { chapter_id: 901, strategy: 'plot_adjust', user_instruction: '', updated_at: '' }, special_analysis: null, style: null, writing: null, updated_at: '2026-08-19T00:00:00',
      };
    } else {
      await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({ detail: `unexpected API: ${path}` }) });
      return;
    }
    await route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  });
  return requests;
}

test('章节工作台只读取章节与 chapter workflow API', async ({ page }) => {
  const runtimeErrors: string[] = [];
  page.on('pageerror', (error) => runtimeErrors.push(error.message));
  const requests = await mockCurrentWorkspace(page);

  await page.goto('/workspace/99');
  await expect(page.getByRole('button', { name: /第 1 章.*第一章/ })).toBeVisible();
  await expect(page.getByText('章节创作工作台')).toBeVisible();
  await expect(page.getByRole('button', { name: '调整剧情' })).toBeVisible();

  expect(requests).toContain('/api/chapters/901/workflow');
  expect(requests.some((path) => path.includes('/scenes') || path.includes('creative-scene'))).toBe(false);
  expect(runtimeErrors).toEqual([]);
});

test('当前界面不再暴露角色卡、剧情骨架和贴合原文策略', async ({ page }) => {
  await mockCurrentWorkspace(page);
  await page.goto('/workspace/99');
  await expect(page.getByRole('button', { name: /第 1 章.*第一章/ })).toBeVisible();
  await expect(page.getByText('角色卡', { exact: true })).toHaveCount(0);
  await expect(page.getByText('剧情骨架', { exact: true })).toHaveCount(0);
  await expect(page.getByText('贴合原文', { exact: true })).toHaveCount(0);
});

test('章节正文变化时显示重新分析提示', async ({ page }) => {
  await mockCurrentWorkspace(page, true);
  await page.goto('/workspace/99');
  await expect(page.getByText('章节原文已经变化，请从内容总结重新开始，避免沿用过期分析。')).toBeVisible();
});

test('专项分析逐条对照原始大纲与可编辑目标大纲', async ({ page }) => {
  await mockCurrentWorkspace(page);
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    chapter_id: 901, strategy: 'plot_adjust', current_stage: 'special_analysis', source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash', source_changed: false,
    summary: { chapter_id: 901, plot_summary: '发现线索。', main_characters: [], key_events: [], relationships: [], start_state: {}, end_state: {}, important_facts: [], open_threads: [], source_hash: 'source-hash', updated_at: '' },
    direction: { chapter_id: 901, strategy: 'plot_adjust', user_instruction: '让冲突更早发生', updated_at: '' },
    special_analysis: { chapter_id: 901, strategy: 'plot_adjust', outline_detail_level: null, source_outline: [{ id: 's1', summary: '主人公进入旧城', source_span: '第 1 段', operation: 'preserve' }, { id: 's2', summary: '在雨夜发现线索', source_span: '第 2 段', operation: 'preserve' }], target_outline: [{ id: 't1', summary: '主人公被追赶后进入旧城', operation: 'modify', source_ids: ['s1'] }, { id: 't2', summary: '提前发现关键线索', operation: 'modify', source_ids: ['s2'] }], constraints: {}, analysis_notes: ['强化开场冲突'], source_hash: 'source-hash', updated_at: '' },
    style: null, writing: null, updated_at: '',
  }) }));
  await page.goto('/workspace/99');
  await expect(page.getByRole('heading', { name: '原始大纲' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '目标大纲' })).toBeVisible();
  await expect(page.getByLabel('第 1 条操作')).toHaveValue('modify');
  await page.getByRole('button', { name: '新增大纲' }).click();
  await expect(page.getByLabel('第 3 条操作')).toHaveValue('insert');
});

test('审查由人工对照编辑并保存确认，不请求模型审查', async ({ page }) => {
  await mockCurrentWorkspace(page);
  let savedText = '';
  let confirmed = false;
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    chapter_id: 901, strategy: 'plot_adjust', current_stage: 'review', source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash', source_changed: false,
    summary: { chapter_id: 901, plot_summary: '发现线索。', main_characters: [], key_events: [], relationships: [], start_state: {}, end_state: {}, important_facts: [], open_threads: [], source_hash: 'source-hash', updated_at: '' },
    direction: { chapter_id: 901, strategy: 'plot_adjust', user_instruction: '', updated_at: '' }, special_analysis: { chapter_id: 901, strategy: 'plot_adjust', outline_detail_level: null, source_outline: [], target_outline: [], constraints: {}, analysis_notes: [], source_hash: 'source-hash', updated_at: '' },
    style: { chapter_id: 901, strategy: 'plot_adjust', style_mode: 'source_auto', source_scope: 'document', author_style_material_id: null, author_style_material_version: null, style_snapshot: {}, extraction_settings_snapshot: {}, generated_guidance: '', source_hash: 'source-hash', created_at: '' },
    writing: { id: 1, chapter_id: 901, strategy: 'plot_adjust', writing_plan: [], result_text: '修改后的雨夜正文。', created_chapter_id: null, source_hash: 'source-hash', status: 'draft', updated_at: '' }, updated_at: '',
  }) }));
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow/writing', async (route) => { savedText = String(route.request().postDataJSON().result_text); await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); });
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow/confirm', async (route) => { confirmed = true; await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); });
  await page.goto('/workspace/99');
  await expect(page.getByText('原始正文', { exact: true })).toBeVisible();
  const edited = page.getByLabel('修改后正文');
  await edited.fill('人工调整后的正文。');
  await page.getByRole('button', { name: '保存修改' }).click();
  await expect.poll(() => savedText).toBe('人工调整后的正文。');
  await page.getByRole('button', { name: '保存并人工确认' }).click();
  await expect.poll(() => confirmed).toBe(true);
});
