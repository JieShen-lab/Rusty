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

test('Electron 完成预分析到人物专项分析的第一阶段闭环', async () => {
  await openSeedProject('真实 E2E 1');
  await expect(page.getByRole('button', { name: /场景 1.*当前/ })).toBeVisible();
  await page.getByRole('button', { name: '运行预分析' }).click();
  await expect(page.getByLabel('摘要')).toHaveValue('人物进入院子并检查院门。');
  await page.getByRole('button', { name: '确认预分析' }).click();
  await page.getByRole('button', { name: /贴合原文/ }).click();
  await page.getByPlaceholder(/把张三替换成李四/).fill('把人物替换成李四，保留事件顺序。');
  await page.getByRole('checkbox', { name: '李四' }).check();
  await page.getByRole('button', { name: '进入专项分析' }).click();
  await page.getByRole('button', { name: '运行人物专项分析' }).click();
  await expect(page.locator('input[value="人物进入院子"]')).toBeVisible();
  await expect(page.locator('input[value="“他”指人物"]')).toBeVisible();
  await expect(page.locator('input[value="存在差异"]')).toBeVisible();
  await page.getByRole('button', { name: '确认分析' }).click();
  await expect(page.getByRole('heading', { name: '目标设计' })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: '目标设计' })).toBeVisible();
});

test('Electron 历史 branch 工程进入统一章节工作台', async () => {
  await openSeedProject('真实 E2E 4');
  await expect(page.getByLabel('章节导航')).toContainText('第一章');
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
  await expect(page.getByRole('button', { name: '继续写' })).toHaveCount(0);
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
  await expect(page.getByLabel('章节导航')).toBeVisible();
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
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
  await page.getByRole('button', { name: '下一步' }).click();
  await page.getByRole('button', { name: '开始创建' }).click();
  await expect(page.getByLabel('章节导航')).toBeVisible();
  await expect(page.getByRole('heading', { name: '场景' })).toBeVisible();
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
  else await expect(page.getByLabel('章节导航')).toBeVisible();
}
