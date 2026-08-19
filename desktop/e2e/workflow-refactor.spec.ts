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
    else if (path === '/api/chapters/901') {
      body = { chapter, ai_outputs: {}, stage_statuses: [], errors: [] };
    } else if (path === '/api/chapters/901/workflow') {
      body = {
        chapter_id: 901, strategy: 'plot_adjust', current_stage: 'direction',
        source_base_kind: 'original', source_base_version_id: null, source_hash: 'source-hash',
        source_changed: sourceChanged, updated_at: '2026-08-19T00:00:00',
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
  await expect(page.getByRole('heading', { name: '第一章' })).toBeVisible();
  await expect(page.getByText('章节 Workflow：方向选择')).toBeVisible();
  await expect(page.locator('textarea')).toHaveValue('雨落在旧城的屋檐上。');

  expect(requests).toContain('/api/chapters/901/workflow');
  expect(requests.some((path) => path.includes('/scenes') || path.includes('creative-scene'))).toBe(false);
  expect(runtimeErrors).toEqual([]);
});

test('当前界面不再暴露角色卡、剧情骨架和贴合原文策略', async ({ page }) => {
  await mockCurrentWorkspace(page);
  await page.goto('/workspace/99');
  await expect(page.getByRole('heading', { name: '第一章' })).toBeVisible();
  await expect(page.getByText('角色卡', { exact: true })).toHaveCount(0);
  await expect(page.getByText('剧情骨架', { exact: true })).toHaveCount(0);
  await expect(page.getByText('贴合原文', { exact: true })).toHaveCount(0);
});

test('章节正文变化时显示重新分析提示', async ({ page }) => {
  await mockCurrentWorkspace(page, true);
  await page.goto('/workspace/99');
  await expect(page.getByText('当前章节已变化，需要重新分析。')).toBeVisible();
});
