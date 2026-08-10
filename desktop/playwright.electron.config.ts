import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-electron',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: [['list'], ['html', { open: 'never', outputFolder: 'playwright-report-electron' }]],
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: [
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: 'python e2e/electron_backend_server.py',
      url: 'http://127.0.0.1:8767/api/health',
      reuseExistingServer: false,
      timeout: 120_000,
    },
  ],
});
