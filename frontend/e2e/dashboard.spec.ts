import { expect, test } from '@playwright/test';

test.describe('Dashboard (mock)', () => {
  test.beforeEach(async ({ page }) => {
    // If the app relies on mock auth being enabled, ensure a mock token is present prior to app load
    // AuthService expects token under `auth_token` key
    await page.addInitScript(() => {
      try {
        localStorage.setItem('auth_token', 'mock-token');
        localStorage.setItem('auth_refresh_token', 'mock-refresh');
      } catch (e) {
        // ignore if storage is unavailable
      }
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

  test('loads dashboard and shows stats', async ({ page }) => {
    await page.goto('/dashboard');

    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();
    await expect(page.getByText('Total Customers')).toBeVisible();
    await expect(page.getByText(/\d+/).first()).toBeVisible();
  });
});
