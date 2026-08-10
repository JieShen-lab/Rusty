import { expect, test, type Page } from '@playwright/test';
import fs from 'node:fs';

const backend = 'http://127.0.0.1:8766';
const query = `apiBase=${encodeURIComponent(backend)}&apiToken=real-e2e-token`;

async function openProject(page: Page, id: number) {
  await page.goto(`/workspace/${id}?${query}`);
  if (id <= 3) await expect(page.getByRole('button', { name: '增加剧情' })).toBeVisible();
  else if (id <= 7) await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
  else await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
  if (id <= 3) await expect(page.locator('.chapter-row.selected')).toBeVisible();
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
  const [executeResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/execute') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '生成全部剩余场景' }).click(),
  ]);
  await expect(page.locator('pre').filter({ hasText: /"rewritten_text"|"chapters"/ })).toBeVisible();
  return executeResponse.json();
}

test('1. 改写工程增加剧情并应用双接缝', async ({ page, request }) => {
  await openProject(page, 1);
  const scenes = await (await request.get(`${backend}/api/chapters/1/scenes`)).json();
  await page.getByLabel('插入点节点类型').selectOption('scene_end');
  await page.getByLabel('插入点场景').selectOption(String(scenes[0].id));
  await page.getByLabel('新增剧情目标').fill('增加一场伏击战');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/1`)).json();
  expect(chapter.chapter.original_text).toBe('人物进入院子。\n\n他检查了院门。\n\n旧设定仍有效。\n\n人物返回客栈。');
  expect(chapter.chapter.rewritten_text).toContain('人物进入院子。\n\n他检查了院门。');
  expect(chapter.chapter.rewritten_text).toContain('旧设定仍有效。\n\n人物返回客栈。');
  expect(chapter.chapter.rewritten_text).toContain('人物遭遇伏击');
  expect(chapter.chapter.rewritten_text).toContain('【进入新剧情】');
  expect(chapter.chapter.rewritten_text).toContain('【返回原路线】');

  await page.getByRole('button', { name: '开始新的运行' }).click();
  await page.getByLabel('新增剧情目标').fill('再增加一场雨夜追逐');
  await page.getByRole('button', { name: '启动分析' }).click();
  await finishPlot(page);
  const histories = await (await request.get(`${backend}/api/projects/1/plot-generation/runs`)).json();
  expect(histories).toHaveLength(2);
  expect(histories.map((run: { status: string }) => run.status)).toEqual(['completed', 'completed']);
  const afterSecondRun = await (await request.get(`${backend}/api/chapters/1`)).json();
  expect(afterSecondRun.chapter.original_text).toBe(chapter.chapter.original_text);
  expect(afterSecondRun.chapter.rewritten_text).toContain('人物进入院子。');
  expect(afterSecondRun.chapter.rewritten_text).toContain('人物返回客栈。');
  expect(afterSecondRun.chapter.rewritten_text).toContain('增加一场伏击战');
  expect(afterSecondRun.chapter.rewritten_text).toContain('再增加一场雨夜追逐');
  const versions = await (await request.get(`${backend}/api/chapters/1/rewrite-versions`)).json();
  expect(versions).toHaveLength(2);
  expect(versions[0].parent_version_id).toBe(versions[1].id);
  expect(versions[0].is_current).toBe(true);
});

test('2. 根据细纲重写正文并自动结构检查', async ({ page, request }) => {
  await openProject(page, 2);
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  const editor = page.getByLabel('模块化细纲编辑器');
  await expect(editor).toBeVisible();
  await editor.getByRole('button', { name: '新增人物状态变化' }).click();
  await editor.getByLabel('人物状态变化 1 人物').fill('人物');
  await editor.getByLabel('人物状态变化 1 属性').fill('警觉');
  await editor.getByLabel('人物状态变化 1 变化后').fill('提高');
  const endState = editor.getByLabel('结束状态 / 回接条件编辑器');
  await endState.getByRole('button', { name: '增加字段' }).click();
  await endState.getByLabel('结束状态 / 回接条件 字段1', { exact: true }).fill('安全');
  await page.getByRole('button', { name: '保存并确认细纲版本' }).click();
  await expect(editor.getByLabel('细纲版本信息')).toContainText('已确认');
  await page.reload();
  await expect(page.getByRole('button', { name: '重写正文' })).toBeVisible();
  await expect(page.locator('.chapter-row.selected')).toBeVisible();
  await page.getByRole('button', { name: '重写正文' }).click();
  await page.getByLabel('源细纲').click();
  await expect(page.getByLabel('人物状态变化 1 变化后')).toHaveValue('提高');
  await expect(page.getByLabel('结束状态 / 回接条件 字段1', { exact: true })).toHaveValue('安全');
  await page.getByRole('button', { name: '生成重写计划' }).click();
  await page.getByRole('button', { name: '生成正文并自动检查' }).click();
  await expect(page.getByRole('status')).toContainText('completed');
  const chapter = await (await request.get(`${backend}/api/chapters/2`)).json();
  expect(chapter.chapter.rewritten_text).toContain('警觉地观察');
  expect(chapter.chapter.original_text).toContain('旧设定仍有效');
  const persisted = await (await request.get(`${backend}/api/chapters/2/story-skeleton`)).json();
  expect(persisted.structured.character_state_changes[0].after).toBe('提高');
  expect(persisted.structured.required_end_state['字段1']).toBe('安全');
});

test('3. 修改设定、审查补丁并原子应用', async ({ page, request }) => {
  await openProject(page, 3);
  await page.getByRole('button', { name: '修改设定' }).click();
  await page.getByLabel('旧设定').fill('旧设定仍有效');
  await page.getByLabel('新设定').fill('新设定已经生效');
  const scanButton = page.getByRole('button', { name: '扫描下游影响' });
  await expect(scanButton).toBeEnabled();
  await scanButton.click();
  try {
    await expect(page.getByLabel('设定变更影响列表')).toBeVisible({ timeout: 5_000 });
  } catch {
    await scanButton.click();
    await expect(page.getByLabel('设定变更影响列表')).toBeVisible();
  }
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

  await page.getByRole('button', { name: '开始新的运行' }).click();
  await page.getByRole('button', { name: '从原文创建新分支' }).click();
  await page.getByLabel('剧情目标').fill('从原文再创建另一条顶级路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await finishPlot(page);
  const roots = await (await request.get(`${backend}/api/projects/4/branches`)).json();
  expect(roots).toHaveLength(2);
  expect(roots.every((branch: { parent_branch_id: number | null }) => branch.parent_branch_id === null)).toBe(true);
});

test('5. 从中途建立分支且保留原路线', async ({ page, request }) => {
  await openProject(page, 5);
  const scenes = await (await request.get(`${backend}/api/chapters/5/scenes`)).json();
  await page.getByRole('button', { name: '从指定节点建立分支' }).click();
  await page.getByLabel('起点节点类型').selectOption('scene_end');
  await page.getByLabel('起点场景').selectOption(String(scenes[0].id));
  await page.getByLabel('剧情目标').fill('从第一章末尾改变路线');
  const [startResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/plot-generation/runs') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '启动分析并创建分支' }).click(),
  ]);
  const started = await startResponse.json();
  const completed = await finishPlot(page);
  const chapter = await (await request.get(`${backend}/api/chapters/5`)).json();
  expect(chapter.chapter.rewritten_text).toBeNull();
  const branches = await (await request.get(`${backend}/api/projects/5/branches`)).json();
  expect(branches[0].branch_mode).toBe('fork');
  expect(branches[0].start_anchor.anchor_type).toBe('scene_end');
  expect(branches[0].start_anchor.scene_id).toBe(scenes[0].id);
  expect(started.start_state.gate_checked).toBe(true);
  expect(started.start_state.original_future_event).toBeUndefined();
  expect(completed.fact_ledger.gate_checked).toBe(true);
  expect(completed.fact_ledger.original_future_event).toBeUndefined();
});

test('6. 分支满足回接状态后生成回接接缝', async ({ page, request }) => {
  await openProject(page, 6);
  const scenes = await (await request.get(`${backend}/api/chapters/6/scenes`)).json();
  await page.getByRole('button', { name: '建立分支并接回原文' }).click();
  await page.getByLabel('起点节点类型').selectOption('scene_end');
  await page.getByLabel('起点场景').selectOption(String(scenes[0].id));
  await page.getByLabel('回接点节点类型').selectOption('scene_start');
  await page.getByLabel('回接点场景').selectOption(String(scenes[1].id));
  await page.getByLabel('剧情目标').fill('绕行后返回原路线');
  const [startResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/plot-generation/runs') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '启动分析并创建分支' }).click(),
  ]);
  const started = await startResponse.json();
  const completed = await finishPlot(page);
  const branches = await (await request.get(`${backend}/api/projects/6/branches`)).json();
  expect(branches[0].branch_mode).toBe('fork_and_rejoin');
  const branch = await (await request.get(`${backend}/api/branches/${branches[0].id}`)).json();
  expect(branch.return_anchor).not.toBeNull();
  expect(started.seams).toEqual([]);
  expect(completed.seams).toHaveLength(2);
  expect(completed.seams[0].source_anchor.scene_id).toBe(scenes[0].id);
  expect(completed.seams[1].source_anchor.scene_id).toBe(scenes[1].id);
  expect(completed.seams[0].source_hash).not.toBe(completed.seams[1].source_hash);
  expect(completed.required_return_state).toEqual({ location: '客栈', gate_checked: true });
  expect(completed.fact_ledger.location).toBe('客栈');
  const content = await (await request.get(`${backend}/api/branches/${branches[0].id}/chapters`)).json();
  expect(content.at(-1).scenes.at(-1).generated_text).toContain('【返回原路线】');
});

test('7. 从已有分支建立子分支', async ({ page, request }) => {
  await openProject(page, 7);
  await page.getByLabel('分支树').getByRole('button', { name: /父分支/ }).click();
  await page.getByRole('button', { name: '从此分支继续派生' }).click();
  await page.getByRole('button', { name: '从指定节点建立分支' }).click();
  await expect(page.getByLabel('起点父分支节点').locator('option:checked')).toContainText('场景：');
  await page.getByLabel('剧情目标').fill('从父分支派生子路线');
  const [startResponse] = await Promise.all([
    page.waitForResponse((response) => response.url().endsWith('/api/plot-generation/runs') && response.request().method() === 'POST'),
    page.getByRole('button', { name: '启动分析并创建分支' }).click(),
  ]);
  const started = await startResponse.json();
  await finishPlot(page);
  await expect(page.getByLabel('分支树')).toContainText('分支 2');
  const branches = await (await request.get(`${backend}/api/projects/7/branches`)).json();
  expect(branches).toHaveLength(2);
  expect(branches[1].parent_branch_id).toBe(branches[0].id);
  expect(branches[1].start_anchor.anchor_type).toBe('branch_scene');
  expect(branches[1].start_anchor.source_version_id).toBeTruthy();
  expect(started.start_state).toMatchObject({ parent_secret_known: true, location: '地下室' });
  const childContent = await (await request.get(`${backend}/api/branches/${branches[1].id}/chapters`)).json();
  expect(childContent[0].scenes[0].facts_after).toMatchObject({ parent_secret_known: true, location: '地下室' });
  expect(childContent[0].scenes[0].facts_after.original_future_event).toBeUndefined();
});

test('8. 旧提取工程导出分析并创建独立扩写工程', async ({ page, request }) => {
  await openProject(page, 8);
  const before = await (await request.get(`${backend}/api/projects/8`)).json();
  const beforeChapter = await (await request.get(`${backend}/api/chapters/8`)).json();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出已有分析' }).click();
  const downloaded = await download;
  expect(downloaded.suggestedFilename()).toContain('analysis.json');
  const exportPath = await downloaded.path();
  const exported = JSON.parse(fs.readFileSync(exportPath!, 'utf8'));
  expect(exported.chapter_analyses[0].plot_summary).toBe('旧分析结果');
  await page.getByRole('button', { name: '基于此项目创建新工程' }).click();
  await page.getByLabel('工程类型').selectOption('branch');
  await page.getByRole('button', { name: '创建并打开' }).click();
  await expect(page).toHaveURL(/\/workspace\/9/);
  const original = await (await request.get(`${backend}/api/projects/8`)).json();
  const derived = await (await request.get(`${backend}/api/projects/9`)).json();
  expect(original.project.project_kind).toBe('legacy_extract');
  expect(derived.project.project_kind).toBe('branch');
  const derivedChapters = await (await request.get(`${backend}/api/projects/9/chapters`)).json();
  expect(derivedChapters[0].original_text).toBe(beforeChapter.chapter.original_text);
  const derivedAnalysis = await (await request.get(`${backend}/api/chapters/${derivedChapters[0].id}/story-skeleton`)).json();
  expect(derivedAnalysis.plot_summary).toBe('旧分析结果');
  const after = await (await request.get(`${backend}/api/projects/8`)).json();
  expect(after.project.project_kind).toBe(before.project.project_kind);
  expect(after.project.id).toBe(before.project.id);
});
