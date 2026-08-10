import { expect, test, type ElectronApplication, type Locator, type Page, _electron as electron } from '@playwright/test';
import path from 'node:path';
import fs from 'node:fs';

let electronApp: ElectronApplication;
let page: Page;
const desktopRoot = process.cwd();
const repositoryRoot = path.resolve(desktopRoot, '..');
const runtimeRoot = path.join(repositoryRoot, 'tmp', 'electron-e2e');

test.beforeAll(async () => {
  electronApp = await electron.launch({
    args: ['--no-sandbox', `--user-data-dir=${path.join(runtimeRoot, `user-data-${process.pid}`)}`, desktopRoot],
    env: {
      ...process.env,
      NODE_ENV: 'test',
      RUSTY_API_HOST: '127.0.0.1',
      RUSTY_API_PORT: '8767',
      RUSTY_API_TOKEN: 'electron-e2e-token',
      RUSTY_E2E_BOOK_FILE: path.join(runtimeRoot, 'source-1.txt'),
      RUSTY_E2E_WORKSPACE: runtimeRoot,
      RUSTY_E2E_EXPORT_PATH: path.join(runtimeRoot, 'electron-export.txt'),
    },
  });
  page = await electronApp.firstWindow();
  await page.waitForLoadState('domcontentloaded');
  await page.evaluate(() => localStorage.clear());
  await page.reload();
  await electronApp.evaluate(({ session }, outputPath) => {
    session.defaultSession.on('will-download', (_event, item) => item.setSavePath(outputPath));
  }, path.join(runtimeRoot, 'legacy-analysis.json'));
});

test.afterAll(async () => {
  await electronApp?.close();
});

test('Electron 启动、preload 桥接和后端连接正常', async () => {
  const bridge = await page.evaluate(async () => ({
    version: window.rustyDesktop?.bridgeVersion,
    platform: window.rustyDesktop?.platform,
    backend: await window.rustyDesktop?.getBackendConfig?.(),
    selectedBook: await window.rustyDesktop?.selectBookFile?.(),
    exportPath: await window.rustyDesktop?.selectDocumentExportPath?.('txt', 'electron'),
  }));
  expect(bridge.version).toBe(2);
  expect(bridge.platform).toBeTruthy();
  expect(bridge.backend?.apiBase).toBe('http://127.0.0.1:8767');
  expect(bridge.selectedBook).toBe(path.join(runtimeRoot, 'source-1.txt'));
  expect(bridge.exportPath).toBe(path.join(runtimeRoot, 'electron-export.txt'));
  await expect(page.getByRole('heading', { name: '工程' })).toBeVisible();
});

test('Electron 新建改写和扩写工程且没有提取入口', async () => {
  await createProject('rewrite');
  await createProject('branch');
});

test('Electron 改写工作流完成增加剧情最小闭环', async () => {
  await openSeedProject('真实 E2E 1');
  await page.getByLabel('新增剧情目标').fill('增加一场伏击战');
  await page.getByRole('button', { name: '启动分析' }).click();
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '确认目标细纲' }).click();
  const seams = page.getByLabel('接缝审查');
  await confirmAllSeams(seams);
  await seams.getByRole('button', { name: '提交接缝审查' }).click();
  await page.getByRole('button', { name: '生成全部剩余场景' }).click();
  await expect(page.locator('pre').filter({ hasText: '人物遭遇伏击' })).toBeVisible();

  await page.getByRole('button', { name: '开始新的运行' }).click();
  await page.getByLabel('新增剧情目标').fill('再增加一场雨夜追逐');
  await page.getByRole('button', { name: '启动分析' }).click();
  await expect(page.getByLabel('模块化细纲编辑器')).toBeVisible();
  await page.getByRole('button', { name: '确认目标细纲' }).click();
  const secondSeams = page.getByLabel('接缝审查');
  await confirmAllSeams(secondSeams);
  await secondSeams.getByRole('button', { name: '提交接缝审查' }).click();
  await page.getByRole('button', { name: '生成全部剩余场景' }).click();
  await expect(page.getByText('本次运行已完成')).toBeVisible();
  await expect(page.getByLabel('剧情生成历史').locator('button')).toHaveCount(2);
});

test('Electron 扩写工作流生成分支章节和场景', async () => {
  await openSeedProject('真实 E2E 4');
  await page.getByLabel('剧情目标').fill('继续新的路线');
  await page.getByRole('button', { name: '启动分析并创建分支' }).click();
  await page.getByRole('button', { name: '确认目标细纲' }).click();
  const seams = page.getByLabel('接缝审查');
  await confirmAllSeams(seams);
  await seams.getByRole('button', { name: '提交接缝审查' }).click();
  await page.getByRole('button', { name: '生成全部剩余场景' }).click();
  await expect(page.locator('pre').filter({ hasText: '新章节' })).toBeVisible();
});

test('Electron 旧提取工程可下载分析并创建派生工程', async () => {
  await openSeedProject('真实 E2E 8');
  const exportFile = path.join(runtimeRoot, 'legacy-analysis.json');
  await page.getByRole('button', { name: '导出已有分析' }).click();
  await expect(page.getByRole('status')).toContainText('分析结果已导出');
  await expect.poll(() => fs.existsSync(exportFile)).toBe(true);
  await page.getByRole('button', { name: '基于此项目创建新工程' }).click();
  await page.getByLabel('工程类型').selectOption('branch');
  await page.getByRole('button', { name: '创建并打开' }).click();
  await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
});

async function createProject(kind: 'rewrite' | 'branch') {
  await page.evaluate(() => localStorage.clear());
  await goToProjectLibrary();
  await page.getByRole('button', { name: '新建工程' }).first().click();
  await expect(page.getByRole('button', { name: /改写工程/ })).toBeVisible();
  await expect(page.getByText('提取工程')).toHaveCount(0);
  await page.getByRole('button', { name: kind === 'rewrite' ? /改写工程/ : /扩写工程/ }).click();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '选择文件' }).click();
  await page.getByRole('button', { name: '选择目录' }).click();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '拆分并预览' }).click();
  await expect(page.getByText('章节预览')).toBeVisible();
  await page.getByRole('button', { name: '下一步' }).click();
  await expect(page.getByRole('button', { name: /Fake E2E Model/ })).toBeVisible();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '开始创建' }).click();
  await expect(page.getByRole('button', { name: kind === 'rewrite' ? '增加剧情' : '从原文末尾续写' })).toBeVisible();
}

async function goToProjectLibrary() {
  await page.getByRole('button', { name: '工程', exact: true }).click();
  await expect(page.getByRole('heading', { name: '工程' })).toBeVisible();
}

async function openSeedProject(name: string) {
  await page.evaluate(() => localStorage.clear());
  await goToProjectLibrary();
  await page.getByRole('button', { name: new RegExp(name) }).first().click();
  await page.getByRole('button', { name: '进入工程' }).click();
  if (name.endsWith('8')) await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
  else if (name.endsWith('4')) {
    await expect(page.getByRole('button', { name: '从原文末尾续写' })).toBeVisible();
    await expect(page.getByLabel('起点节点类型')).toBeVisible();
  } else {
    await expect(page.getByRole('button', { name: '增加剧情' })).toBeVisible();
    await expect(page.locator('.chapter-row.selected')).toBeVisible();
  }
}

async function confirmAllSeams(seams: Locator) {
  await expect(seams).toBeVisible();
  for (const article of await seams.locator('article').all()) {
    await article.getByRole('button', { name: '确认', exact: true }).click();
  }
}
