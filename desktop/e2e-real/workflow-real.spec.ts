import { expect, test, type Page } from '@playwright/test';

const backend = 'http://127.0.0.1:8766';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=real-e2e-token`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  if (id <= 3) await expect(page.getByRole('button', { name: '增加剧情' })).toBeVisible();
  else if (id <= 7) await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
  else await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
}

async function finishPlot(page: Page) {
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '确认目标细纲' }).click();
  const seams = page.getByLabel('接缝审查');
  await expect(seams).toBeVisible();
  for (const button of await seams.getByRole('button', { name: '确认', exact: true }).all()) {
    await button.click();
  }
  await seams.getByRole('button', { name: '提交接缝审查' }).click();
  await page.getByRole('button', { name: '逐场景生成并检查' }).click();
  await expect(page.locator('pre').filter({ hasText: /"rewritten_text"|"chapters"/ })).toBeVisible();
}

test('1. 改写工程增加剧情并应用双接缝', async ({ page, request }) => {
  await openProject(page, 1);
  await page.getByLabel('新增剧情目标').fill('增加一场伏击战');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/1`)).json();
  expect(chapter.chapter.original_text).toContain('人物进入院子');
  expect(chapter.chapter.rewritten_text).toContain('人物遭遇伏击');
  expect(chapter.chapter.rewritten_text).toContain('【进入新剧情】');
  expect(chapter.chapter.rewritten_text).toContain('【返回原路线】');
});

test('2. 根据细纲重写正文并自动结构检查', async ({ page, request }) => {
  await openProject(page, 2);
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '生成重写计划' }).click();
  await page.getByRole('button', { name: '生成正文并自动检查' }).click();
  await expect(page.getByRole('status')).toContainText('completed');
  const chapter = await (await request.get(`${backend}/api/chapters/2`)).json();
  expect(chapter.chapter.rewritten_text).toContain('警觉地观察');
  expect(chapter.chapter.original_text).toContain('旧设定仍有效');
});

test('3. 修改设定、审查补丁并原子应用', async ({ page, request }) => {
  await openProject(page, 3);
  await page.getByRole('button', { name: '修改设定' }).click();
  await page.getByLabel('旧设定').fill('旧设定仍有效');
  await page.getByLabel('新设定').fill('新设定已经生效');
  const [scanResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/canon-change/runs') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '扫描下游影响' }).click(),
  ]);
  expect(scanResponse.ok()).toBe(true);
  await expect(page.getByLabel('设定变更影响列表')).toBeVisible();
  await page.getByLabel('设定变更影响列表').getByRole('button', { name: '接受' }).click();
  await page.getByRole('button', { name: '原子应用已接受补丁' }).click();
  await expect(page.getByLabel('设定变更影响列表')).toContainText('applied');
  const chapter = await (await request.get(`${backend}/api/chapters/3`)).json();
  expect(chapter.chapter.rewritten_text).toContain('新设定已经生效');
  expect(chapter.chapter.original_text).toContain('旧设定仍有效');
});

test('4. 从原文末尾续写并生成分支章节场景', async ({ page, request }) => {
  await openProject(page, 4);
  await page.getByLabel('剧情目标').fill('从末尾继续新的旅程');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await finishPlot(page);
  const branches = await (await request.get(`${backend}/api/projects/4/branches`)).json();
  expect(branches).toHaveLength(1);
  const content = await (await request.get(`${backend}/api/branches/${branches[0].id}/chapters`)).json();
  expect(content[0].scenes[0].facts_after.ambush_resolved).toBe(true);
});

test('5. 从中途建立分支且保留原路线', async ({ page, request }) => {
  await openProject(page, 5);
  await page.getByRole('button', { name: '从指定节点建立分支' }).click();
  await page.getByLabel('剧情目标').fill('从第一章末尾改变路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/5`)).json();
  expect(chapter.chapter.rewritten_text).toBeNull();
  const branches = await (await request.get(`${backend}/api/projects/5/branches`)).json();
  expect(branches[0].branch_mode).toBe('fork');
});

test('6. 分支满足回接状态后生成回接接缝', async ({ page, request }) => {
  await openProject(page, 6);
  await page.getByRole('button', { name: '建立分支并接回原文' }).click();
  await page.getByLabel('剧情目标').fill('绕行后返回原路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await finishPlot(page);
  const branches = await (await request.get(`${backend}/api/projects/6/branches`)).json();
  expect(branches[0].branch_mode).toBe('fork_and_rejoin');
  const branch = await (await request.get(`${backend}/api/branches/${branches[0].id}`)).json();
  expect(branch.return_anchor).not.toBeNull();
});

test('7. 从已有分支建立子分支', async ({ page, request }) => {
  await openProject(page, 7);
  await page.getByLabel('分支树').getByRole('button', { name: /父分支/ }).click();
  await page.getByRole('button', { name: '从指定节点建立分支' }).click();
  await page.getByLabel('剧情目标').fill('从父分支派生子路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await expect(page.getByLabel('分支树')).toContainText('分支 2');
  const branches = await (await request.get(`${backend}/api/projects/7/branches`)).json();
  expect(branches).toHaveLength(2);
  expect(branches[1].parent_branch_id).toBe(branches[0].id);
});

test('8. 旧提取工程导出分析并创建独立扩写工程', async ({ page, request }) => {
  await openProject(page, 8);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出已有分析' }).click();
  expect((await download).suggestedFilename()).toContain('analysis.json');
  await page.getByRole('button', { name: '基于此项目创建新工程' }).click();
  await page.getByLabel('工程类型').selectOption('branch');
  await page.getByRole('button', { name: '创建并打开' }).click();
  await expect(page).toHaveURL(/\/workspace\/9/);
  const original = await (await request.get(`${backend}/api/projects/8`)).json();
  const derived = await (await request.get(`${backend}/api/projects/9`)).json();
  expect(original.project.project_kind).toBe('legacy_extract');
  expect(derived.project.project_kind).toBe('branch');
});
