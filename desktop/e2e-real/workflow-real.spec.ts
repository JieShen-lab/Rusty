import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

const backend = 'http://127.0.0.1:8766';
const token = 'real-e2e-token';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=${token}`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  if (id === 8) await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
  else {
    await expect(page.getByLabel('章节导航')).toBeVisible();
    await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
  }
}

test('1. rewrite 与历史 branch 使用同一章节中心工作台并恢复活动场景', async ({ page, request }) => {
  await openProject(page, 1);
  await expect(page.getByRole('button', { name: /场景 1 当前/ })).toBeVisible();
  await expect(page.getByLabel('章节导航')).not.toContainText('场景 1');
  await expect(page.getByRole('button', { name: '场景改写' })).toHaveCount(0);
  const rewriteState = await (await request.get(`${backend}/api/projects/1/creative-workflow`)).json();
  expect(rewriteState[0].active_scene_id).toBeTruthy();
  expect(rewriteState[0].current_stage).toBe('preanalysis');

  await openProject(page, 4);
  await expect(page.getByRole('button', { name: /场景 1 当前/ })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toHaveCount(0);
});

test('2. 真后端完成预分析、方向和贴合原文人物专项分析', async ({ page, request }) => {
  await openProject(page, 2);
  await expect(page.getByRole('button', { name: /场景 1 当前/ })).toBeVisible();
  await page.getByRole('button', { name: '运行预分析' }).click();
  await expect(page.getByLabel('摘要')).toHaveValue('人物进入院子并检查院门。');
  await page.getByRole('button', { name: '确认预分析' }).click();
  await page.getByRole('button', { name: /贴合原文/ }).click();
  await page.getByPlaceholder(/把张三替换成李四/).fill('把人物替换成李四，事件过程尽量保留。');
  await page.getByRole('checkbox', { name: '李四' }).check();
  await page.getByRole('button', { name: '进入专项分析' }).click();
  await page.getByRole('button', { name: '运行人物专项分析' }).click();
  await expect(page.locator('input[value="人物进入院子"]')).toBeVisible();
  await expect(page.locator('input[value="“他”指人物"]')).toBeVisible();
  await expect(page.locator('input[value="存在差异"]')).toBeVisible();
  await page.getByRole('button', { name: '确认分析' }).click();
  await expect(page.getByRole('heading', { name: '目标设计' })).toBeVisible();

  const state = await (await request.get(`${backend}/api/projects/2/creative-workflow`)).json();
  expect(state[0].current_stage).toBe('target_design');
  const chapter = await (await request.get(`${backend}/api/chapters/2`)).json();
  expect(chapter.chapter.rewritten_text).toBeNull();
  await page.reload();
  await expect(page.getByRole('heading', { name: '目标设计' })).toBeVisible();
});

test('3. 工程总提示词是可独立编辑的当前文本', async ({ page, request }) => {
  await openProject(page, 3);
  await page.getByRole('button', { name: '工程设置' }).click();
  const editor = page.getByLabel('总提示词');
  await editor.fill('保持人物行为一致，不自动生成正文。');
  await page.getByRole('button', { name: '保存设置' }).click();
  const stored = await (await request.get(`${backend}/api/projects/3/master-prompt`)).json();
  expect(stored.content).toBe('保持人物行为一致，不自动生成正文。');
});

test('4. 旧提取工程仍可导出分析并派生独立工程', async ({ page, request }) => {
  await openProject(page, 8);
  const before = await (await request.get(`${backend}/api/projects/8`)).json();
  const beforeChapter = await (await request.get(`${backend}/api/chapters/8`)).json();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出已有分析' }).click();
  const downloaded = await download;
  const exported = JSON.parse(fs.readFileSync((await downloaded.path())!, 'utf8'));
  expect(exported.chapter_analyses[0].plot_summary).toBe('旧分析结果');
  await page.getByRole('button', { name: '基于此项目创建新工程' }).click();
  await page.getByLabel('工程类型').selectOption('branch');
  await page.getByRole('button', { name: '创建并打开' }).click();
  await expect.poll(() => Number(page.url().match(/\/workspace\/(\d+)/)?.[1])).toBeGreaterThan(8);
  const derivedId = Number(page.url().match(/\/workspace\/(\d+)/)?.[1]);
  const derived = await (await request.get(`${backend}/api/projects/${derivedId}`)).json();
  expect(derived.project.project_kind).toBe('branch');
  const derivedChapters = await (await request.get(`${backend}/api/projects/${derivedId}/chapters`)).json();
  expect(derivedChapters[0].original_text).toBe(beforeChapter.chapter.original_text);
  const after = await (await request.get(`${backend}/api/projects/8`)).json();
  expect(after.project.project_kind).toBe(before.project.project_kind);
});
