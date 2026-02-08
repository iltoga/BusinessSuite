import { expect, test } from '@playwright/test';

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
    await page.route('**/api/customers*', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(customersResponse),
      }),
    );
  });

  test('space opens menu; arrows move highlight; hover highlights', async ({ page }) => {
    await page.goto('/customers');

    const row = page.locator('tbody tr').first();
    await row.waitFor();

    await row.click();
    await expect(row).toHaveAttribute('aria-selected', 'true');

    await row.focus();
    await page.keyboard.press('Space');

    const menu = page.locator('[role="menu"]');
    await expect(menu).toBeVisible();

    const firstItem = menu.locator('z-dropdown-menu-item, [z-dropdown-menu-item]').first();
    await expect(firstItem).toBeFocused();
    await expect(firstItem).toHaveAttribute('data-highlighted', 'true');

    await page.keyboard.press('ArrowDown');
    const editItem = menu.locator(
      'z-dropdown-menu-item:has-text("Edit"), [z-dropdown-menu-item]:has-text("Edit")',
    );
    await expect(editItem).toBeFocused();
    await expect(editItem).toHaveAttribute('data-highlighted', 'true');

    const editBg = await editItem.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(editBg).not.toBe('rgba(0, 0, 0, 0)');
    expect(editBg).not.toBe('transparent');

    const toggleItem = menu
      .locator('z-dropdown-menu-item:has-text("Toggle"), [z-dropdown-menu-item]:has-text("Toggle")')
      .first();
    await toggleItem.hover();
    await expect(toggleItem).toHaveAttribute('data-highlighted', 'true');
    await expect(toggleItem).toBeFocused();

    const toggleBg = await toggleItem.evaluate((el) => getComputedStyle(el).backgroundColor);
    expect(toggleBg).not.toBe('rgba(0, 0, 0, 0)');
    expect(toggleBg).not.toBe('transparent');
  });
});
