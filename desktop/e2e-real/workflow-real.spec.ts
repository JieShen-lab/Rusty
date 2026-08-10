import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

const backend = 'http://127.0.0.1:8766';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=real-e2e-token`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  if (id <= 3) await expect(page.getByRole('button', { name: '增加剧情' })).toBeVisible();
  else if (id <= 7) await expect(page.getByRole('button', { name: '继续写' })).toBeVisible();
  else await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
}

async function finishPlot(page: Page) {
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '确认目标细纲' }).click();
  const [response] = await Promise.all([
    page.waitForResponse((item) => item.url().endsWith('/execute') && item.request().method() === 'POST'),
    page.getByRole('button', { name: '生成全部剩余场景' }).click(),
  ]);
  expect(response.ok()).toBe(true);
  return response.json();
}

test('1. bounded insert 保留原文并连续产生版本', async ({ page, request }) => {
  await openProject(page, 1);
  const scenes = await (await request.get(`${backend}/api/chapters/1/scenes`)).json();
  await page.getByLabel('插入点节点类型').selectOption('scene_end');
  await page.getByLabel('插入点场景').selectOption(String(scenes[0].id));
  await page.getByLabel('新增剧情目标').fill('增加一场伏击战');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const first = await (await request.get(`${backend}/api/chapters/1`)).json();
  expect(first.chapter.original_text).toBe('人物进入院子。\n\n他检查了院门。\n\n旧设定仍有效。\n\n人物返回客栈。');
  expect(first.chapter.rewritten_text).toContain('人物遭遇伏击');
  expect(first.chapter.rewritten_text).toContain('人物进入院子。');
  expect(first.chapter.rewritten_text).toContain('人物返回客栈。');

  await page.getByRole('button', { name: '开始新的创作' }).click();
  await page.getByLabel('新增剧情目标').fill('再增加一场雨夜追逐');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const second = await (await request.get(`${backend}/api/chapters/1`)).json();
  expect(second.chapter.original_text).toBe(first.chapter.original_text);
  expect(second.chapter.rewritten_text).toContain('增加一场伏击战');
  expect(second.chapter.rewritten_text).toContain('再增加一场雨夜追逐');
  const versions = await (await request.get(`${backend}/api/chapters/1/rewrite-versions`)).json();
  expect(versions).toHaveLength(2);
  expect(versions[0].parent_version_id).toBe(versions[1].id);
});

test('2. Prose 使用当前版本并保留语义锚点和恢复能力', async ({ page, request }) => {
  await openProject(page, 2);
  const scenes = await (await request.get(`${backend}/api/chapters/2/scenes`)).json();
  await page.getByLabel('插入点节点类型').selectOption('scene_end');
  await page.getByLabel('插入点场景').selectOption(String(scenes[0].id));
  await page.getByLabel('新增剧情目标').fill('语义链事件 A');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  await page.getByRole('button', { name: '开始新的创作' }).click();
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  await page.getByRole('button', { name: '生成重写计划' }).click();
  await page.getByRole('button', { name: '生成正文并检查' }).click();
  await expect(page.getByRole('status')).toContainText('本次创作已完成');
  const versionsAfterProse = await (await request.get(`${backend}/api/chapters/2/rewrite-versions`)).json();
  const proseVersion = versionsAfterProse[0];
  expect(proseVersion.source_operation).toBe('prose_rewrite');
  expect(proseVersion.rewritten_text).toContain('语义链事件 A');

  await page.getByRole('button', { name: '开始新的运行' }).click();
  await page.getByRole('button', { name: '增加剧情' }).click();
  await page.getByLabel('插入点节点类型').selectOption('scene_end');
  await page.getByLabel('插入点场景').selectOption(String(scenes[0].id));
  await page.getByRole('button', { name: '预览位置' }).first().click();
  await expect(page.getByLabel('插入点锚点预览')).toContainText('人物');
  await page.getByLabel('新增剧情目标').fill('语义链事件 B');
  const [startResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().endsWith('/api/plot-generation/runs') && item.request().method() === 'POST'),
    page.getByRole('button', { name: '启动分析' }).click(),
  ]);
  expect((await startResponse.json()).source_base_version_id).toBe(proseVersion.id);
  await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/2`)).json();
  expect(chapter.chapter.rewritten_text).toContain('语义链事件 A');
  expect(chapter.chapter.rewritten_text).toContain('语义链事件 B');

  const restore = await request.post(
    `${backend}/api/chapter-rewrite-versions/${proseVersion.id}/restore`,
    { headers: { 'X-Rusty-Token': 'real-e2e-token' } },
  );
  expect(restore.ok()).toBe(true);
  const restored = await restore.json();
  expect(restored.rewritten_text).toBe(proseVersion.rewritten_text);
  const structure = await request.get(`${backend}/api/chapter-rewrite-versions/${restored.id}/skeleton`);
  expect(structure.ok()).toBe(true);
});

test('3. 替换范围只替换明确选择的场景且原文基线不变', async ({ page, request }) => {
  await openProject(page, 3);
  const scenes = await (await request.get(`${backend}/api/chapters/3/scenes`)).json();
  await page.getByLabel('插入方式').selectOption('replace_range');
  await page.getByLabel('插入点节点类型').selectOption('scene_start');
  await page.getByLabel('插入点场景').selectOption(String(scenes[1].id));
  await page.getByLabel('范围终点节点类型').selectOption('scene_end');
  await page.getByLabel('范围终点场景').selectOption(String(scenes[1].id));
  await page.getByLabel('新增剧情目标').fill('替换旧设定段落');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/3`)).json();
  expect(chapter.chapter.original_text).toContain('旧设定仍有效');
  expect(chapter.chapter.rewritten_text).toContain('人物进入院子。');
  expect(chapter.chapter.rewritten_text).not.toContain('旧设定仍有效');
  expect(chapter.chapter.rewritten_text).toContain('替换旧设定段落');
});

test('4. 续写路线可以在同一 Branch 中连续追加', async ({ page, request }) => {
  await openProject(page, 4);
  await page.getByLabel('剧情目标').fill('从末尾继续新的旅程');
  await page.getByRole('button', { name: '开始规划' }).click();
  await finishPlot(page);
  let branches = await (await request.get(`${backend}/api/projects/4/branches`)).json();
  expect(branches).toHaveLength(1);
  const branchId = branches[0].id;
  let chapters = await (await request.get(`${backend}/api/branches/${branchId}/chapters`)).json();
  expect(chapters).toHaveLength(1);

  await page.getByRole('button', { name: '继续创作' }).click();
  await page.getByLabel('剧情目标').fill('沿同一路线继续第二章');
  await page.getByRole('button', { name: '开始规划' }).click();
  await finishPlot(page);
  branches = await (await request.get(`${backend}/api/projects/4/branches`)).json();
  expect(branches).toHaveLength(1);
  chapters = await (await request.get(`${backend}/api/branches/${branchId}/chapters`)).json();
  expect(chapters).toHaveLength(2);
  expect(chapters[1].scenes[0].generated_text).toContain('沿同一路线继续第二章');
});

test('5. 从原文场景创建独立 IF 路线', async ({ page, request }) => {
  await openProject(page, 5);
  const scenes = await (await request.get(`${backend}/api/chapters/5/scenes`)).json();
  await page.getByRole('button', { name: '写另一种发展' }).click();
  await page.getByLabel('从这里开始节点类型').selectOption('scene_end');
  await page.getByLabel('从这里开始场景').selectOption(String(scenes[0].id));
  await page.getByLabel('剧情目标').fill('从院门开始另一种发展');
  const [startResponse] = await Promise.all([
    page.waitForResponse((item) => item.url().endsWith('/api/plot-generation/runs') && item.request().method() === 'POST'),
    page.getByRole('button', { name: '开始规划' }).click(),
  ]);
  const started = await startResponse.json();
  await finishPlot(page);
  const original = await (await request.get(`${backend}/api/chapters/5`)).json();
  expect(original.chapter.rewritten_text).toBeNull();
  const branches = await (await request.get(`${backend}/api/projects/5/branches`)).json();
  expect(branches).toHaveLength(1);
  expect(branches[0].branch_mode).toBe('fork');
  expect(branches[0].start_anchor.scene_id).toBe(scenes[0].id);
  expect(started.start_state.gate_checked).toBe(true);
  expect(started.start_state.original_future_event).toBeUndefined();
});

test('6. 旧提取工程仍可导出分析并派生独立工程', async ({ page, request }) => {
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
  expect(derivedId).toBeGreaterThan(8);
  const derived = await (await request.get(`${backend}/api/projects/${derivedId}`)).json();
  expect(derived.project.project_kind).toBe('branch');
  const derivedChapters = await (await request.get(`${backend}/api/projects/${derivedId}/chapters`)).json();
  expect(derivedChapters[0].original_text).toBe(beforeChapter.chapter.original_text);
  const after = await (await request.get(`${backend}/api/projects/8`)).json();
  expect(after.project.project_kind).toBe(before.project.project_kind);
});
