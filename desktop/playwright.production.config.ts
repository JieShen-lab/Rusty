import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e-production',
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 60_000,
  reporter: 'list',
  use: {
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  webServer: {
    command: 'python e2e/electron_backend_server.py',
    url: 'http://127.0.0.1:8767/api/health',
    reuseExistingServer: false,
    timeout: 120_000,
  },
});
