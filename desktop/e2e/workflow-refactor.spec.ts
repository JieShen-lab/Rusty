import { expect, test, type Page } from '@playwright/test';

const chapter = {
  id: 901, project_id: 99, index: 1, title: '第一章',
  original_text: '雨落在旧城的屋檐上。', rewritten_text: null,
  word_count: 11, baseline_word_count: 11, current_word_count: 11, word_delta: 0,
  is_added_chapter: false, status: 'imported', workflow_stage: 'direction',
};

function projectDetail() {
  return {
    id: 99, name: '章节工作流测试工程', status: 'ready', current_stage: 'imported',
    source_format: 'txt', total_chapters: 1, total_words: 11, completed_chapters: 0,
    book_title: '测试小说', author: null, created_at: '', updated_at: '', progress: 0,
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
      body = chapter;
    } else if (path === '/api/chapters/901/workflow') {
      body = {
        chapter_id: 901, strategy: 'plot_adjust', current_stage: 'direction',
        source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash',
        source_changed: sourceChanged, summary: { chapter_id: 901, plot_summary: '旧城雨夜里，主人公发现了线索。', main_characters: '主人公：本章视角人物。', key_events: '1. 发现线索', source_hash: 'source-hash', updated_at: '' },
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
  await expect(page.getByRole('heading', { name: '章节工作流测试工程', exact: true })).toBeVisible();
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
  await page.getByRole('button', { name: '内容总结' }).click();
  await expect(page.getByText('主要人物及设定', { exact: true })).toBeVisible();
  await expect(page.getByText('关键事件', { exact: true })).toBeVisible();
  await expect(page.getByText('重要事实', { exact: true })).toHaveCount(0);
  await expect(page.getByText('未解决线索', { exact: true })).toHaveCount(0);
});

test('章节正文变化时显示重新分析提示', async ({ page }) => {
  await mockCurrentWorkspace(page, true);
  await page.goto('/workspace/99');
  await expect(page.getByText('章节原文已经变化，请从内容总结重新开始，避免沿用过期分析。')).toBeVisible();
});

test('调整剧情对照旧大纲与可编辑的新大纲及细节', async ({ page }) => {
  await mockCurrentWorkspace(page);
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    chapter_id: 901, strategy: 'plot_adjust', current_stage: 'special_analysis', source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash', source_changed: false,
    summary: { chapter_id: 901, plot_summary: '发现线索。', main_characters: '', key_events: '', source_hash: 'source-hash', updated_at: '' },
    direction: { chapter_id: 901, strategy: 'plot_adjust', user_instruction: '让冲突更早发生', updated_at: '' },
    special_analysis: { chapter_id: 901, strategy: 'plot_adjust', source_outline: '1. 主人公进入旧城\n2. 在雨夜发现线索', target_outline: '1. 主人公被追赶后进入旧城\n2. 提前发现关键线索', source_hash: 'source-hash', updated_at: '' },
    style: null, writing: null, updated_at: '',
  }) }));
  await page.goto('/workspace/99');
  await expect(page.getByRole('heading', { name: '旧大纲' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '新大纲及细节' })).toBeVisible();
  const targetOutline = page.getByLabel('新大纲及细节');
  await expect(targetOutline).toHaveValue('1. 主人公被追赶后进入旧城\n2. 提前发现关键线索');
  await targetOutline.fill('1. 主人公在追赶中进入旧城\n2. 提前发现关键线索');
  await expect(page.getByText('来源正文', { exact: true })).toHaveCount(0);
  if (process.env.RUSTY_E2E_SCREENSHOT_DIR) {
    await page.screenshot({ path: `${process.env.RUSTY_E2E_SCREENSHOT_DIR}/workflow-outline.png` });
  }
});

test('审查由人工对照编辑并保存修改，不请求模型审查', async ({ page }) => {
  await mockCurrentWorkspace(page);
  let savedText = '';
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow', async (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({
    chapter_id: 901, strategy: 'plot_adjust', current_stage: 'review', source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash', source_changed: false,
    summary: { chapter_id: 901, plot_summary: '发现线索。', main_characters: '', key_events: '', source_hash: 'source-hash', updated_at: '' },
    direction: { chapter_id: 901, strategy: 'plot_adjust', user_instruction: '', updated_at: '' }, special_analysis: { chapter_id: 901, strategy: 'plot_adjust', source_outline: '', target_outline: '', source_hash: 'source-hash', updated_at: '' },
    style: { chapter_id: 901, strategy: 'plot_adjust', style_mode: 'source_auto', author_style_material_id: null, style_snapshot: {}, extraction_settings_snapshot: {}, generated_guidance: '', source_hash: 'source-hash', created_at: '' },
    writing: { id: 1, chapter_id: 901, strategy: 'plot_adjust', result_text: '修改后的雨夜正文。', created_chapter_id: null, source_hash: 'source-hash', status: 'draft', updated_at: '' }, updated_at: '',
  }) }));
  await page.route('http://127.0.0.1:8765/api/chapters/901/workflow/writing', async (route) => { savedText = String(route.request().postDataJSON().result_text); await route.fulfill({ status: 200, contentType: 'application/json', body: '{}' }); });
  await page.goto('/workspace/99');
  await expect(page.getByText('原始正文', { exact: true })).toBeVisible();
  const edited = page.getByLabel('修改后正文');
  await edited.fill('人工调整后的正文。');
  await page.getByRole('button', { name: '保存并完成审查' }).click();
  await expect.poll(() => savedText).toBe('人工调整后的正文。');
});
