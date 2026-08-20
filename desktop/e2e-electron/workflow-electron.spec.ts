import { expect, test, type ElectronApplication, type Page, _electron as electron } from '@playwright/test';
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

test('Electron 新建统一普通小说工程且没有改写扩写选择', async () => {
  await createProject();
});

test('Electron 完成内容总结到目标大纲保存的章节流程', async () => {
  await openSeedProject('真实 E2E 1');
  await page.getByRole('button', { name: '生成内容总结' }).click();
  await page.getByRole('button', { name: '调整剧情' }).click();
  await page.getByPlaceholder(/保留人物相遇/).fill('让院门暗记成为明确线索。');
  await page.getByRole('button', { name: '保存并开始分析' }).click();
  await page.getByRole('button', { name: '开始分析' }).click();
  await expect(page.getByRole('heading', { name: '原始大纲' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '目标大纲' })).toBeVisible();
  await expect(page.getByLabel('第 2 条操作')).toHaveValue('modify');
  await page.getByRole('button', { name: '保存目标大纲' }).click();
  await expect(page.getByRole('heading', { name: '确定写作风格' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '专项分析' })).toBeVisible();
  await page.getByRole('button', { name: '风格', exact: true }).click();
  await expect(page.getByRole('heading', { name: '确定写作风格' })).toBeVisible();
});

test('Electron 历史扩写工程仍保持独立扩写工作台', async () => {
  await openSeedProject('真实 E2E 4');
  await expect(page.getByRole('heading', { name: '真实 E2E 4' })).toBeVisible();
  await expect(page.getByText('每条路线独立保存；可以从原文创建新路线，也可以在当前路线中继续写。')).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toBeVisible();
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
  await expect(page.getByText('扩写工程', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toBeVisible();
});

async function createProject() {
  await page.evaluate(() => localStorage.clear());
  await goToProjectLibrary();
  await page.getByRole('button', { name: '新建工程' }).first().click();
  await expect(page.getByRole('heading', { name: '导入文件' })).toBeVisible();
  await expect(page.getByRole('button', { name: /改写工程/ })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /扩写工程/ })).toHaveCount(0);
  await page.getByRole('button', { name: '选择文件' }).click();
  await page.getByRole('button', { name: '选择目录' }).click();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '拆分并预览' }).click();
  await expect(page.getByText('章节预览')).toBeVisible();
  await page.getByRole('button', { name: '下一步' }).click();
  await expect(page.getByRole('button', { name: /Fake E2E Model/ })).toBeVisible();
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '开始创建' }).click();
  await expect(page.getByText('章节创作工作台')).toBeVisible();
  await expect(page.getByRole('button', { name: /第 1 章/ })).toBeVisible();
}

async function goToProjectLibrary() {
  await page.locator('.rail-item[aria-label="工程"]').click();
  await expect(page.getByRole('heading', { name: '工程' })).toBeVisible();
}

async function openSeedProject(name: string) {
  await page.evaluate(() => localStorage.clear());
  await goToProjectLibrary();
  await page.getByRole('button', { name: new RegExp(name) }).first().click();
  await page.getByRole('button', { name: '进入工程' }).click();
  if (name.endsWith('8')) await expect(page.getByText('此项目属于旧版分析工程。')).toBeVisible();
  else if (name === '真实 E2E 4') await expect(page.getByText('扩写工程', { exact: true })).toBeVisible();
  else await expect(page.getByText('章节创作工作台')).toBeVisible();
}
