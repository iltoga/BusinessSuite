import { expect, test } from '@playwright/test';

test.describe('Theme UI interaction', () => {
  test('theme switcher is visible and toggles theme/dark mode', async ({ page }) => {
    await page.goto('/');

    // Ensure header and theme switcher are visible
    await expect(page.locator('app-theme-switcher')).toBeVisible();

    const getPrimary = () =>
      page.evaluate(() =>
        getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
      );

    const initialPrimary = await getPrimary();

    // Select purple theme via UI
    await page.locator('app-theme-switcher select').selectOption('purple');

    // Click dark mode toggle (button shows 'Light' or 'Dark')
    // Use JS click to avoid any overlay or z-button nuances
    await page.evaluate(() => document.querySelector('app-theme-switcher button')?.click());

    // Wait for localStorage to be set and for html.dark class to be toggled
    await page.waitForFunction(() => localStorage.getItem('darkMode') === 'true', null, {
      timeout: 3000,
    });
    await page.waitForFunction(() => document.documentElement.classList.contains('dark'), null, {
      timeout: 3000,
    });

    // Wait a moment for CSS vars to update
    await page.waitForTimeout(100);

    const appliedPrimary = await getPrimary();

    // Assertions
    await expect(appliedPrimary).not.toBe(initialPrimary);
    expect(appliedPrimary).toContain('303.9'); // purple hue present
  });
});
