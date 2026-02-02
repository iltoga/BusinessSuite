import { test } from '@playwright/test';
import { checkA11y, injectAxe } from 'axe-playwright';

// Simple accessibility sanity checks for key pages. These aim to catch regressions early.
const paths = ['/', '/customers', '/invoices'];

for (const p of paths) {
  test(`a11y: ${p}`, async ({ page }) => {
    await page.goto(p);
    // Wait for main content to load - tune when necessary
    await page.locator('body').waitFor();
    await injectAxe(page);
    // Default rules, fail if any serious violations
    await checkA11y(page, undefined, {
      detailedReport: true,
      detailedReportOptions: { html: true },
    });
  });
}
