import { expect, test } from '@playwright/test';

// Ensure logo and its container are skipped by tabbing
test.describe('Logo focus behavior', () => {
  test.beforeEach(async ({ page }) => {
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
  });

  test('logo should not receive focus when tabbing through the page', async ({ page }) => {
    await page.goto('/customers');
    // Wait for customers list to be present
    await page.waitForSelector('input[name="search"]');

    // Ensure logo exists
    await page.waitForSelector('img[data-app-logo]');

    // Start from body focus
    await page.evaluate(() => (document.activeElement as HTMLElement | null)?.blur?.());

    // Sanity check: anchor and image should be non-tabbable
    const tabAttrs = await page.evaluate(() => {
      const img = document.querySelector('img[data-app-logo]') as HTMLElement | null;
      const parent = img?.parentElement as HTMLElement | null;
      return {
        imgTab: img?.getAttribute('tabindex') ?? null,
        parentTab: parent?.getAttribute('tabindex') ?? null,
      };
    });

    // If the attributes are not set to -1, fail fast to indicate change wasn't applied
    expect(tabAttrs.imgTab).toBe('-1');
    expect(tabAttrs.parentTab).toBe('-1');

    // Tab through the page up to N times and ensure logo never becomes activeElement
    const attempts = 40;
    let logoFocused = false;

    for (let i = 0; i < attempts; i++) {
      await page.keyboard.press('Tab');
      // small delay for focus transitions
      await page.waitForTimeout(30);
      const isFocused = await page.evaluate(() => {
        const logo = document.querySelector('img[data-app-logo]');
        const active = document.activeElement;
        return !!logo && (active === logo || active === logo?.parentElement);
      });
      if (isFocused) {
        // gather debugging info about the currently focused element
        const focusedInfo = await page.evaluate(() => {
          const a = document.activeElement as HTMLElement | null;
          if (!a) return null;
          return {
            tag: a.tagName,
            id: a.id || null,
            classes: a.className || null,
            role: a.getAttribute('role') || null,
            href: (a as HTMLAnchorElement).getAttribute('href') || null,
            outer: (a.outerHTML || '').slice(0, 300),
          };
        });
        // Fail with the debug info so we can see why it received focus
        throw new Error(
          'Logo received focus during tabbing; focused element: ' + JSON.stringify(focusedInfo),
        );
      }
    }

    expect(logoFocused).toBe(false);
  });
});
