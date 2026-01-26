import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 30_000,
  expect: { timeout: 5000 },
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  use: {
    headless: true,
    viewport: { width: 1280, height: 720 },
    actionTimeout: 0,
    baseURL: 'http://localhost:4200',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // add firefox and webkit if desired
  ],
});
