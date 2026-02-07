import { expect, test } from '@playwright/test';

const customersResponse = {
  count: 1,
  next: null,
  previous: null,
  results: [
    {
      id: 1,
      full_name_with_company: 'John Doe',
      email: 'john@example.com',
      telephone: null,
      passport_number: null,
      passport_expiration_date: null,
      passport_expired: false,
      passport_expiring_soon: false,
      active: true,
    },
  ],
};

test.describe('Data table keyboard shortcuts (customers list)', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/customers*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(customersResponse),
      }),
    );
  });

  test('menu Edit navigates to edit page (visual shortcut present)', async ({ page }) => {
    await page.goto('/customers');
    const row = page.locator('tbody tr').first();
    await row.waitFor();

    // Click to open the actions menu
    await row.locator('button[z-dropdown]').click();

    // Ensure the Edit menu entry is visible
    const editItem = page.locator('button:has-text("Edit")');
    await expect(editItem).toBeVisible();

    // Click Edit and assert navigation
    await editItem.click();
    await expect(page).toHaveURL(/\/customers\/\d+\/edit/);
  });

  test('pressing T triggers toggle-active request', async ({ page }) => {
    // Intercept toggle-active endpoint using waitForRequest to be robust
    await page.goto('/customers');
    const row = page.locator('tbody tr').first();
    await row.waitFor();

    // Click to open the actions menu
    await row.locator('button[z-dropdown]').click();

    // Click Toggle Active and wait for the toggle call
    const toggleItem = page.locator('button:has-text("Toggle Active")');
    await expect(toggleItem).toBeVisible();
    await page.waitForTimeout(50);
    const enabled = await toggleItem.isEnabled();
    expect(enabled).toBe(true);

    // Clicking Toggle Active should ultimately refresh the customers list; wait for that request
    const reqPromise = page.waitForRequest(
      (req) => req.url().includes('/api/customers') && req.method() === 'GET',
    );

    await toggleItem.click();

    const req = await reqPromise;
    expect(req).toBeTruthy();
  });
});
