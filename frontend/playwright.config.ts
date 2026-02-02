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

  // Start the dev server automatically when running tests locally or in CI.
  // Playwright will run `npm start` and wait for the URL to respond.
  webServer: {
    command: 'npm start',
    url: 'http://localhost:4200',
    timeout: 120_000,
    reuseExistingServer: !process.env.CI,
  },

  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
    // add firefox and webkit if desired
  ],
});
