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

async function advanceStrategyToTarget(page: Page, projectId: number, strategy: '调整剧情' | '增加剧情' | '重新构思') {
  await openProject(page, projectId);
  await page.getByRole('button', { name: '运行预分析' }).click();
  await page.getByRole('button', { name: '确认预分析' }).click();
  await page.getByRole('button', { name: strategy }).click();
  await page.getByPlaceholder(/把张三替换成李四/).fill(`${strategy}，保持已确认的场景边界。`);
  await page.getByRole('checkbox', { name: '李四' }).check();
  await page.getByRole('button', { name: '进入专项分析' }).click();
  await page.getByRole('button', { name: '运行专项分析' }).click();
  await page.getByRole('button', { name: '确认分析' }).click();
}

test('1. rewrite 与历史 branch 使用同一章节中心工作台并恢复活动场景', async ({ page, request }) => {
  await openProject(page, 1);
  await expect(page.getByRole('button', { name: /场景 1.*当前/ })).toBeVisible();
  await expect(page.getByLabel('章节导航')).not.toContainText('场景 1');
  await expect(page.getByRole('button', { name: '场景改写' })).toHaveCount(0);
  const rewriteState = await (await request.get(`${backend}/api/projects/1/creative-workflow`)).json();
  expect(rewriteState[0].active_scene_id).toBeTruthy();
  expect(rewriteState[0].current_stage).toBe('not_started');

  await openProject(page, 4);
  await expect(page.getByRole('button', { name: /场景 1.*当前/ })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toHaveCount(0);
});

test('2. 真后端完成 faithful Target、Plan、Draft、选区编辑与 Diff 审查纵向流程', async ({ page, request }) => {
  await openProject(page, 2);
  await expect(page.getByRole('button', { name: /场景 1.*当前/ })).toBeVisible();
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
  await page.getByRole('button', { name: '生成目标草案' }).click();
  await expect(page.locator('input[value="李四"]')).toBeVisible();
  await page.getByRole('button', { name: '确认目标' }).click();
  await expect(page.getByRole('heading', { name: '写作规划' })).toBeVisible();
  await page.getByRole('button', { name: '生成写作规划' }).click();
  await expect(page.getByLabel('区块 1 操作')).toHaveValue('preserve');
  await expect(page.getByLabel('区块 2 操作')).toHaveValue('transform');
  await page.getByRole('button', { name: '开始生成' }).click();
  const editor = page.getByLabel('当前正文');
  await expect(editor).toHaveValue(/李四谨慎地检查了院门/);
  const generated = await editor.inputValue();
  await editor.fill(`【人工修改】${generated}`);
  await editor.evaluate((node: HTMLTextAreaElement) => {
    const start = node.value.indexOf('李四谨慎地检查');
    node.setSelectionRange(start, start + '李四谨慎地检查'.length);
  });
  page.once('dialog', (dialog) => dialog.accept('动作更准确，不增加新事件'));
  await page.getByRole('button', { name: 'AI 修改选中内容' }).click();
  await expect(editor).toHaveValue(/【人工修改】/);
  await expect(editor).toHaveValue(/李四仔细检查/);
  await page.getByRole('button', { name: '进入审查' }).click();
  await expect(page.getByRole('heading', { name: 'Source ↔ Current Draft' })).toBeVisible();
  await expect(page.getByText('传统文本 Diff；进入本页不会调用 AI。')).toBeVisible();
  await page.getByText('选择原文与当前稿范围').click();
  await page.getByLabel('原文范围').evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(0, 6));
  await page.getByLabel('当前稿范围').evaluate((node: HTMLTextAreaElement) => node.setSelectionRange(0, 6));
  page.once('dialog', (dialog) => dialog.accept('这里要保留进入院子的动作。'));
  await page.getByRole('button', { name: '添加备注' }).click();
  await expect(page.getByText('这里要保留进入院子的动作。')).toBeVisible();
  page.once('dialog', (dialog) => dialog.accept('保留动作并适配李四'));
  await page.getByRole('button', { name: 'AI 重改此处' }).last().click();
  await expect(page.getByRole('button', { name: '采用新版' })).toBeVisible();
  await page.getByRole('button', { name: '采用新版' }).click();
  await page.getByRole('button', { name: '确认场景' }).click();
  await expect(page.getByText('场景已确认。')).toBeVisible();
  const finalState = await (await request.get(`${backend}/api/projects/2/creative-workflow`)).json();
  expect(finalState[0].current_stage).toBe('confirmed');
});

test('3. plot_adjust 专项分析、TargetSkeleton 编辑持久化并进入 Writing Plan', async ({ page }) => {
  await advanceStrategyToTarget(page, 4, '调整剧情');
  await page.getByRole('button', { name: 'AI 生成草案' }).click();
  const node = page.getByLabel('节点 2 摘要');
  await expect(node).toHaveValue('李四发现院门暗记');
  await node.fill('李四发现院门上的新暗记');
  await expect(page.getByRole('button', { name: '确认目标' })).toBeEnabled();
  await page.reload();
  await expect(page.getByLabel('节点 2 摘要')).toHaveValue('李四发现院门上的新暗记');
  await expect(page.getByLabel('source-2 映射')).toHaveValue('inspect');
  await page.getByRole('button', { name: '确认目标' }).click();
  await page.getByRole('button', { name: '生成写作规划' }).click();
  await expect(page.getByLabel('区块 1 操作')).toHaveValue('rewrite');
});

test('4. expansion 编辑退出约束并只在 Preserve Source 间生成插入正文', async ({ page }) => {
  await advanceStrategyToTarget(page, 5, '增加剧情');
  await page.getByRole('button', { name: 'AI 生成草案' }).click();
  const constraints = page.getByLabel('退出约束（必须可见、可编辑）');
  await expect(constraints).toHaveValue(/旧设定仍有效/);
  await constraints.fill('旧设定仍有效\n人物仍会检查院门\n人物不知道脚步声来源');
  await expect(page.getByRole('button', { name: '确认目标' })).toBeEnabled();
  await page.getByRole('button', { name: '确认目标' }).click();
  await page.getByRole('button', { name: '生成写作规划' }).click();
  await expect(page.getByLabel('区块 2 操作')).toHaveValue('insert');
  await page.getByRole('button', { name: '开始生成' }).click();
  const draft = page.getByLabel('当前正文');
  await expect(draft).toHaveValue(/人物进入院子/);
  await expect(draft).toHaveValue(/门外忽然传来一阵脚步声/);
  await expect(draft).toHaveValue(/他检查了院门/);
});

test('5. reimagine 以 Boundary Conditions 和 TargetSkeleton 完成完整场景生成', async ({ page }) => {
  await advanceStrategyToTarget(page, 6, '重新构思');
  await page.getByRole('button', { name: 'AI 生成草案' }).click();
  await expect(page.getByLabel('地点')).toHaveValue('院子');
  await expect(page.locator('.skeleton-node-list input').first()).toHaveValue('李四识破院中伏击');
  await page.getByRole('button', { name: '确认目标' }).click();
  await page.getByRole('button', { name: '生成写作规划' }).click();
  await expect(page.getByLabel('区块 1 操作')).toHaveValue('rewrite');
  await page.getByRole('button', { name: '开始生成' }).click();
  await expect(page.getByLabel('当前正文')).toHaveValue('李四进入院子，识破伏击并检查院门，随后仍返回客栈。');
});

test('6. Target 输入恢复原值后的 autosave 保持 confirmed 且不 stale 下游', async ({ page, request }) => {
  await openProject(page, 7);
  await page.getByRole('button', { name: '运行预分析' }).click();
  await page.getByRole('button', { name: '确认预分析' }).click();
  await page.getByRole('button', { name: /贴合原文/ }).click();
  await page.getByPlaceholder(/把张三替换成李四/).fill('把人物替换成李四，事件过程尽量保留。');
  await page.getByRole('checkbox', { name: '李四' }).check();
  await page.getByRole('button', { name: '进入专项分析' }).click();
  await page.getByRole('button', { name: '运行人物专项分析' }).click();
  await page.getByRole('button', { name: '确认分析' }).click();
  await page.getByRole('button', { name: '生成目标草案' }).click();
  await page.getByRole('button', { name: '确认目标' }).click();
  await page.getByRole('button', { name: '生成写作规划' }).click();
  await page.getByRole('button', { name: '开始生成' }).click();

  const workflow = await (await request.get(`${backend}/api/projects/7/creative-workflow`)).json();
  const sceneId = workflow[0].active_scene_id;
  await page.getByRole('button', { name: '目标设计' }).click();
  const label = page.getByLabel('目标项名称').first();
  const original = await label.inputValue();
  await label.fill(`${original}临`);
  await label.fill(original);
  await expect(page.locator('.target-editor').getByText('已确认', { exact: true })).toBeVisible();
  await expect.poll(async () => (await (await request.get(`${backend}/api/scenes/${sceneId}/target`)).json()).status).toBe('confirmed');
  expect((await (await request.get(`${backend}/api/scenes/${sceneId}/writing-plan`)).json()).status).toBe('ready');
  expect((await (await request.get(`${backend}/api/scenes/${sceneId}/current-draft`)).json()).status).toBe('draft');

  await page.reload();
  await page.getByRole('button', { name: '目标设计' }).click();
  await expect(page.locator('.target-editor').getByText('已确认', { exact: true })).toBeVisible();
  expect((await (await request.get(`${backend}/api/scenes/${sceneId}/writing-plan`)).json()).status).toBe('ready');
  expect((await (await request.get(`${backend}/api/scenes/${sceneId}/current-draft`)).json()).status).toBe('draft');
});

test('7. 工程总提示词是可独立编辑的当前文本', async ({ page, request }) => {
  await openProject(page, 3);
  await page.getByRole('button', { name: '工程设置' }).click();
  const editor = page.getByLabel('总提示词');
  await editor.fill('保持人物行为一致，不自动生成正文。');
  await page.getByRole('button', { name: '保存设置' }).click();
  await expect.poll(async () => (await (await request.get(`${backend}/api/projects/3/master-prompt`)).json()).content)
    .toBe('保持人物行为一致，不自动生成正文。');
});

test('8. 旧提取工程仍可导出分析并派生独立工程', async ({ page, request }) => {
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
