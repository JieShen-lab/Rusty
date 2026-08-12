import { expect, test, _electron as electron } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const desktopRoot = process.cwd();
const repositoryRoot = path.resolve(desktopRoot, '..');
const runtimeRoot = path.join(repositoryRoot, 'tmp', 'electron-production-e2e');

test('production loadFile renders Rusty with local assets and file-safe navigation', async () => {
  const indexHtml = fs.readFileSync(path.join(desktopRoot, 'dist', 'index.html'), 'utf8');
  expect(indexHtml).not.toMatch(/(?:src|href)="\/assets\//);
  expect(indexHtml).toMatch(/src="\.\/assets\//);
  expect(indexHtml).toMatch(/href="\.\/assets\//);

  const electronApp = await electron.launch({
    args: [
      '--no-sandbox',
      `--user-data-dir=${path.join(runtimeRoot, `user-data-${process.pid}`)}`,
      desktopRoot,
    ],
    env: {
      ...process.env,
      NODE_ENV: 'production',
      RUSTY_API_HOST: '127.0.0.1',
      RUSTY_API_PORT: '8767',
      RUSTY_API_TOKEN: 'electron-e2e-token',
    },
  });

  try {
    const page = await electronApp.firstWindow();
    const rendererErrors: string[] = [];
    const failedLocalResources: string[] = [];
    page.on('console', (message) => {
      if (message.type() === 'error') rendererErrors.push(message.text());
    });
    page.on('pageerror', (error) => rendererErrors.push(error.message));
    page.on('requestfailed', (request) => {
      if (request.url().startsWith('file:')) {
        failedLocalResources.push(`${request.url()} ${request.failure()?.errorText ?? ''}`);
      }
    });

    await expect(page.getByRole('heading', { name: '工程', exact: true })).toBeVisible();
    await expect(page).toHaveURL(/^file:\/\/\/.+\/dist\/index\.html\?.+#\/library$/);
    const rendererState = await page.evaluate(() => ({
      rootChildren: document.querySelector('#root')?.childElementCount ?? 0,
      styleSheets: document.styleSheets.length,
      shellDisplay: getComputedStyle(document.querySelector('.app-shell')!).display,
    }));
    expect(rendererState.rootChildren).toBe(1);
    expect(rendererState.styleSheets).toBeGreaterThan(0);
    expect(rendererState.shellDisplay).toBe('grid');

    for (const [button, route, heading] of [
      ['文档库', 'documents', '文档库'],
      ['素材', 'materials', '素材库'],
      ['角色卡', 'characters', '角色卡库'],
      ['提示词', 'prompts', '提示词'],
      ['模型', 'models', '模型'],
    ] as const) {
      await page.getByRole('button', { name: button, exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`#/${route}$`));
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    }

    await page.getByRole('button', { name: /深色/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByRole('button', { name: /浅色/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');

    await page.getByRole('button', { name: '工程', exact: true }).click();
    await expect(page).toHaveURL(/#\/library$/);
    await expect(page.getByRole('heading', { name: '工程', exact: true })).toBeVisible();
    await page.getByRole('button', { name: /真实 E2E 1/ }).first().click();
    await page.getByRole('button', { name: '进入工程', exact: true }).click();
    await expect(page).toHaveURL(/#\/workspace\/\d+$/);
    await expect(page.locator('.creative-workspace')).toBeVisible();
    await expect(page.getByRole('button', { name: '运行预分析' })).toBeVisible();

    expect(failedLocalResources).toEqual([]);
    expect(rendererErrors).toEqual([]);
  } finally {
    await electronApp.close();
  }
});
