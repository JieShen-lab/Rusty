import { expect, test, type ElectronApplication, type Page, _electron as electron } from '@playwright/test';
import path from 'node:path';

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
});

test.afterAll(async () => {
  await electronApp?.close();
});

test('Electron 启动、preload 桥接和后端连接正常', async () => {
  const bridge = await page.evaluate(async () => ({
    backend: await window.rustyDesktop?.getBackendConfig?.(),
    selectedBook: await window.rustyDesktop?.selectBookFile?.(),
    exportPath: await window.rustyDesktop?.selectDocumentExportPath?.('txt', 'electron'),
  }));
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
  await page.getByRole('button', { name: '保存并选择方向' }).click();
  await page.getByRole('button', { name: '调整剧情' }).click();
  await page.getByPlaceholder(/保留人物相遇/).fill('让院门暗记成为明确线索。');
  await page.getByRole('button', { name: '保存并开始分析' }).click();
  await page.getByRole('button', { name: '开始分析' }).click();
  await expect(page.getByRole('heading', { name: '旧大纲' })).toBeVisible();
  await expect(page.getByRole('heading', { name: '新大纲及细节' })).toBeVisible();
  await expect(page.getByLabel('新大纲及细节')).toHaveValue('1. 人物进入院子\n2. 李四发现院门暗记\n3. 人物返回客栈');
  await page.getByRole('button', { name: '保存新大纲' }).click();
  await expect(page.getByRole('heading', { name: '确定写作风格' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '专项分析' })).toBeVisible();
  await page.getByRole('button', { name: '风格', exact: true }).click();
  await expect(page.getByRole('heading', { name: '确定写作风格' })).toBeVisible();
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
  await expect(page.locator('.creative-project-title h1')).toBeVisible();
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
  await expect(page.locator('.creative-project-title h1')).toBeVisible();
}
