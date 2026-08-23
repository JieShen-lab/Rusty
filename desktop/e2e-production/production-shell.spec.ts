import { expect, test, _electron as electron } from '@playwright/test';
import fs from 'node:fs';
import path from 'node:path';

const desktopRoot = process.cwd();
const repositoryRoot = path.resolve(desktopRoot, '..');
const runtimeRoot = path.join(repositoryRoot, 'installer', 'work', 'package-e2e');
const packagedExecutable = process.env.RUSTY_PACKAGED_EXECUTABLE
  || path.join(desktopRoot, 'release', 'win-unpacked', 'Rusty.exe');

test('packaged Rusty starts its bundled backend and renders local assets', async () => {
  expect(fs.existsSync(packagedExecutable)).toBe(true);
  fs.mkdirSync(runtimeRoot, { recursive: true });

  const electronApp = await electron.launch({
    executablePath: packagedExecutable,
    args: [
      '--no-sandbox',
      `--user-data-dir=${path.join(runtimeRoot, `user-data-${process.pid}`)}`,
    ],
    env: {
      ...process.env,
      RUSTY_DATABASE_PATH: path.join(runtimeRoot, 'rusty.db'),
      RUSTY_API_HOST: '127.0.0.1',
      RUSTY_API_PORT: '0',
      RUSTY_API_TOKEN: 'package-e2e-token',
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
    await expect(page).toHaveURL(/^file:\/\/.+\/dist\/index\.html\?.+#\/library$/);

    const backend = await page.evaluate(async () => {
      const config = await window.rustyDesktop?.getBackendConfig?.();
      const health = await window.rustyDesktop?.requestBackend?.({ path: '/api/health' });
      return { config, health };
    });
    expect(backend.config?.apiBase).toMatch(/^http:\/\/127\.0\.0\.1:\d+$/);
    expect(backend.config?.apiBase?.endsWith(':0')).toBe(false);
    expect(backend.health?.status).toBe(200);
    expect(JSON.parse(backend.health?.body ?? '{}')).toEqual({ ok: true, app: 'Rusty' });

    const keyring = await page.evaluate(async () => {
      const createdResponse = await window.rustyDesktop?.requestBackend?.({
        path: '/api/models',
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          display_name: 'Package E2E Model',
          provider: 'openai_compatible',
          base_url: 'https://example.invalid/v1',
          model_name: 'package-e2e',
          api_key: 'package-e2e-secret',
        }),
      });
      const created = JSON.parse(createdResponse?.body ?? '{}');
      const deletedResponse = created.id ? await window.rustyDesktop?.requestBackend?.({
        path: `/api/models/${created.id}/delete`,
        method: 'POST',
      }) : undefined;
      return { createdResponse, created, deletedResponse };
    });
    expect(keyring.createdResponse?.status).toBe(200);
    expect(keyring.created.has_api_key).toBe(true);
    expect(keyring.created.api_key).toBeUndefined();
    expect(keyring.deletedResponse?.status).toBe(200);

    for (const [button, heading] of [
      ['文档库', '文档库'],
      ['作者', '作者'],
      ['提示词', '提示词'],
      ['模型', '模型'],
    ] as const) {
      await page.getByRole('button', { name: button, exact: true }).click();
      await expect(page.getByRole('heading', { name: heading, exact: true })).toBeVisible();
    }

    await page.getByRole('button', { name: /深色/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.getByRole('button', { name: /浅色/ }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');

    expect(failedLocalResources).toEqual([]);
    expect(rendererErrors).toEqual([]);
  } finally {
    await electronApp.close();
  }
});
