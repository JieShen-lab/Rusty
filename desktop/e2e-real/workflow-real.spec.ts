import { expect, test, type Page } from '@playwright/test';

const backend = 'http://127.0.0.1:8766';
const token = 'real-e2e-token';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=${token}`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  await expect(page.locator('.creative-project-title h1')).toBeVisible();
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
  await page.getByRole('button', { name: '保存并完成审查' }).click();
  await expect(page.getByText('本章审查稿已保存。')).toBeVisible();

  const state = await (await request.get(`${backend}/api/chapters/1/workflow`)).json();
  expect(state.current_stage).toBe('review');
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
