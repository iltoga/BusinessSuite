import { test } from '@playwright/test';
import { checkA11y, injectAxe } from 'axe-playwright';

// Simple accessibility sanity checks for key pages. These aim to catch regressions early.
const paths = ['/', '/customers', '/invoices'];

for (const p of paths) {
  test(`a11y: ${p}`, async ({ page }) => {
    // If the app relies on mock auth being enabled, ensure a mock token is present prior to app load
    await page.addInitScript(() => {
      try {
        localStorage.setItem('auth_token', 'mock-token');
        localStorage.setItem('auth_refresh_token', 'mock-refresh');
      } catch (e) {}
    });

    // Ensure the frontend receives a config that enables mock auth
    await page.route('**/app-config/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ MOCK_AUTH_ENABLED: 'True' }),
      }),
    );

    // Mock data endpoints to avoid "Failed to load" toasts which trigger a11y violations
    await page.route('**/api/customers*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
      }),
    );
    await page.route('**/api/invoices*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ count: 0, next: null, previous: null, results: [] }),
      }),
    );
    await page.route('**/api/dashboard-stats/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          total_customers: 0,
          pending_applications: 0,
          active_invoices: 0,
          total_revenue: 0,
        }),
      }),
    );

    await page.goto(p);
    // Wait for main content to load - tune when necessary
    await page.locator('body').waitFor();
    await injectAxe(page);
    // Default rules, fail if any serious violations.
    // Exclude the toast container (ngx-sonner) which has some known a11y quirks.
    await checkA11y(
      page,
      { exclude: [['[data-sonner-toaster]']] },
      {
        detailedReport: true,
        detailedReportOptions: { html: true },
      },
    );
  });
}
