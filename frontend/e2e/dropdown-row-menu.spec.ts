import { test } from '@playwright/test';

const customersResponse = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      full_name_with_company: 'Kristina Barannikova',
      email: 'kristina@example.com',
      telephone: '+79145384020',
      passport_number: '667407742',
      passport_expiration_date: '2028-04-14',
      passport_expired: false,
      passport_expiring_soon: false,
      active: true,
      nationality: 'Rusia',
      nationality_code: 'RUS',
      added: '2025-12-18T13:37:27',
      updated: '2025-12-18T13:37:27',
    },
  ],
};

test.describe('Row actions dropdown keyboard flow', () => {
  test.beforeEach(async ({ page }) => {
    // If the app relies on mock auth being enabled, ensure a mock token is present prior to app load
    await page.addInitScript(() => {
      try {
        localStorage.setItem('auth_token', 'mock-token');
        localStorage.setItem('auth_refresh_token', 'mock-refresh');
      } catch (e) {}
    });

    // Ensure the frontend receives a config that enables mock auth
    await page.route('**/api/app-config/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ MOCK_AUTH_ENABLED: 'True' }),
      }),
    );

    await page.route('**/api/customers*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(customersResponse),
      }),
    );
  });
});
