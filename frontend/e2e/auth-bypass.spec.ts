import { expect, test } from '@playwright/test';

test.describe('Auth mock bypass', () => {
  test.beforeEach(async ({ page }) => {
    // Ensure we start with a known mocked authenticated state
    await page.addInitScript(() => {
      try {
        // Seed an auth token so the app initialises as authenticated under mock mode
        localStorage.setItem('auth_token', 'mock-token');
        localStorage.setItem('auth_refresh_token', 'mock-refresh');
      } catch (e) {
        // ignore in non-browser env
      }
    });

    // Intercept /app-config/ to ensure MOCK_AUTH_ENABLED is true for the test run
    await page.route('**/app-config/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ MOCK_AUTH_ENABLED: 'True', title: 'RevisBali CRM' }),
      }),
    );
  });

  // Increase default timeouts for navigation/interaction in these tests
  test.setTimeout(60_000);

  test('visiting / redirects to /dashboard when MOCK_AUTH_ENABLED is true', async ({ page }) => {
    await page.goto('/');

    // The app loads the runtime config and should init mock auth, which navigates to the dashboard
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible({ timeout: 10000 });
    await expect(page).toHaveURL(/\/dashboard$/);

    // Login form should not be visible
    await expect(page.getByRole('heading', { name: 'Login' })).toHaveCount(0);
  });

  test('logout takes user to login form', async ({ page }) => {
    await page.goto('/dashboard');

    // Ensure we are on dashboard
    await expect(page.getByRole('heading', { name: 'Dashboard' })).toBeVisible();

    // Click the Logout button in the banner to log out
    await page.getByRole('button', { name: 'Logout' }).click();

    // Should be navigated to the login page
    await expect(page).toHaveURL(/\/login$/);
    await expect(page.getByRole('heading', { name: 'Login' })).toBeVisible();

    // The login form should be visible. The login button starts disabled when the form is empty.
    await expect(page.getByRole('button', { name: 'Login' })).toBeDisabled();
    await expect(page.getByLabel('Username')).toBeVisible();
    await expect(page.getByLabel('Password')).toBeVisible();
  });
});
