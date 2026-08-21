import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

const backend = 'http://127.0.0.1:8766';
const token = 'real-e2e-token';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=${token}`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  if (id === 8) {
    await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
    return;
  }
  await expect(page.getByText('章节创作工作台')).toBeVisible();
  await expect(page.getByRole('button', { name: /第 1 章/ })).toBeVisible();
}

test('真实后端完成章节总结、大纲对照、写作和人工审查', async ({ page, request }) => {
  await openProject(page, 1);

  await page.getByRole('button', { name: '生成内容总结' }).click();
  await expect(page.getByText('主要人物及设定', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '保存并选择方向' }).click();
  await expect(page.getByRole('button', { name: '调整剧情' })).toBeVisible();
  await page.getByRole('button', { name: '调整剧情' }).click();
  await page.getByPlaceholder(/保留人物相遇/).fill('保留事件主干，让院门暗记成为明确线索。');
  await page.getByRole('button', { name: '保存并开始分析' }).click();

  await page.getByRole('button', { name: '开始分析' }).click();
  await expect(page.getByRole('heading', { name: '旧大纲' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '新大纲及细节' })).toBeVisible();
  const targetItem = page.getByLabel('新大纲及细节');
  await expect(targetItem).toHaveValue('1. 人物进入院子\n2. 李四发现院门暗记\n3. 人物返回客栈');
  await targetItem.fill('1. 人物进入院子\n2. 李四在院门上发现新的暗记\n3. 人物返回客栈');
  await page.getByRole('button', { name: '保存新大纲' }).click();

  await expect(page.getByRole('heading', { name: '确定写作风格' })).toBeVisible();
  await page.getByRole('button', { name: '提取并使用本文风格' }).click();
  await expect(page.getByRole('button', { name: '开始写作' })).toBeVisible();
  await page.getByRole('button', { name: '开始写作' }).click();

  await expect(page.getByRole('heading', { name: '原文与修改后对照' })).toBeVisible();
  await expect(page.getByText('原始正文', { exact: true })).toBeVisible();
  const edited = page.getByLabel('修改后正文');
  await expect(edited).toHaveValue(/李四在院门上发现了一枚暗记/);
  await edited.fill('【人工修订】李四在院门上发现新的暗记，随后返回客栈。');
  await page.getByRole('button', { name: '保存修改' }).click();
  await expect(page.getByText('修改稿已保存。')).toBeVisible();
  await page.getByRole('button', { name: '保存并人工确认' }).click();
  await expect(page.getByText('本章已由人工确认，可进入下一章。')).toBeVisible();

  const state = await (await request.get(`${backend}/api/chapters/1/workflow`)).json();
  expect(state.current_stage).toBe('confirmed');
  expect(state.writing.result_text).toContain('【人工修订】');
  expect(state.special_analysis.target_outline).toContain('2. 李四在院门上发现新的暗记');
});

test('真实后端的章节工作台不再暴露旧角色卡和场景工作流', async ({ page }) => {
  await openProject(page, 2);
  await expect(page.getByText('角色卡', { exact: true })).toHaveCount(0);
  await expect(page.getByText('剧情骨架', { exact: true })).toHaveCount(0);
  await expect(page.getByText('场景', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '调整剧情' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: '生成内容总结' })).toBeVisible();
});

test('旧提取工程仍可导出分析并派生独立工程', async ({ page, request }) => {
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
