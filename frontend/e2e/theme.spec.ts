import { expect, test } from '@playwright/test';

// Basic e2e test that verifies theme initialization applies CSS variables
// by writing to localStorage (as the app reads theme/darkMode on startup) and
// reloading the page to let the AppInitializer call ThemeService.initializeTheme().

test.describe('Theme initialization', () => {
  test('applies theme and dark mode from localStorage', async ({ page }) => {
    // Visit root to ensure app bootstraps
    await page.goto('/');

    // Capture initial primary color
    const initialPrimary = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
    );

    // Set theme to 'purple' and enable dark mode via localStorage
    await page.evaluate(() => {
      localStorage.setItem('theme', 'purple');
      localStorage.setItem('darkMode', 'true');
    });

    // Reload so the app reads the stored values during initialization
    await page.reload();

    // Read applied CSS variable and html.dark class
    const appliedPrimary = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
    );

    const hasDarkClass = await page.evaluate(() =>
      document.documentElement.classList.contains('dark'),
    );

    // The primary color should have changed from the initial value
    await expect(appliedPrimary).not.toBe(initialPrimary);

    // Purple dark primary value (from theme config) should be applied (partial match)
    expect(appliedPrimary).toContain('303.9');

    // Dark class should be present
    expect(hasDarkClass).toBe(true);
  });

  test('applies legacy theme in light mode from localStorage', async ({ page }) => {
    await page.goto('/');

    // Set theme to 'legacy' and ensure light mode
    await page.evaluate(() => {
      localStorage.setItem('theme', 'legacy');
      localStorage.setItem('darkMode', 'false');
    });

    await page.reload();

    const appliedPrimary = await page.evaluate(() =>
      getComputedStyle(document.documentElement).getPropertyValue('--primary').trim(),
    );

    // Should apply legacy navy (OKLCH hue ~260)
    expect(appliedPrimary).toContain('260');
  });
});
