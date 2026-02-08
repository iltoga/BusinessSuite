import { expect, test } from '@playwright/test';

test.describe('Passport Auto-Import', () => {
  const mockCustomer = {
    id: 123,
    fullName: 'Test Customer',
    fullNameWithCompany: 'Test Customer',
    passportNumber: 'P123456',
    passportFile: '/media/passports/test.pdf',
    active: true,
  };

  const mockProduct = {
    id: 456,
    name: 'Test Product',
    required_documents: [
      { id: 1, name: 'Passport' },
      { id: 2, name: 'Photos' },
    ],
    optional_documents: [],
  };

  const mockDocumentTypes = [
    { id: 1, name: 'Passport' },
    { id: 2, name: 'Photos' },
  ];

  test.beforeEach(async ({ page }) => {
    // Mock Config
    await page.route('**/app-config/', (route) =>
      route.fulfill({ body: JSON.stringify({ MOCK_AUTH_ENABLED: 'true' }) }),
    );
    await page.route('**/api/mock-auth-config/', (route) =>
      route.fulfill({ body: JSON.stringify({ sub: 'test-user', isSuperuser: true }) }),
    );

    // Mock APIs
    await page.route('**/api/customers/123/', (route) =>
      route.fulfill({ body: JSON.stringify(mockCustomer) }),
    );
    await page.route('**/api/customers/**', (route) =>
      route.fulfill({ body: JSON.stringify({ results: [mockCustomer], count: 1 }) }),
    );
    await page.route('**/api/products/get_product_by_id/456/', (route) =>
      route.fulfill({ body: JSON.stringify(mockProduct) }),
    );
    await page.route('**/api/products/**', (route) =>
      route.fulfill({
        body: JSON.stringify({
          results: [{ id: 456, name: 'Test Product', code: 'TP' }],
          count: 1,
        }),
      }),
    );
    await page.route('**/api/document-types/', (route) =>
      route.fulfill({ body: JSON.stringify(mockDocumentTypes) }),
    );

    // Set mock token
    await page.addInitScript(() => {
      window.localStorage.setItem('auth_token', 'mock-token');
    });
  });

  test('passport is imported silently and message is not shown', async ({ page }) => {
    await page.goto('/applications/new');

    // Wait for the page to load by checking the heading
    await expect(page.locator('h1')).toHaveText('New Application');

    // 1. Select Customer
    // Use a more generic selector for the combobox button if the text is problematic
    const customerCombobox = page.locator('app-customer-select button[role="combobox"]');
    await customerCombobox.click();
    await page.locator('z-command-option:has-text("Test Customer")').click();

    // 2. Select Product
    // The product select might have a different placeholder or internal structure
    await page.locator('app-product-select button[role="combobox"]').click();
    await page.locator('z-command-option:has-text("Test Product")').click();

    // Verify documents panel is visible (contains "Application Documents")
    await expect(page.locator('h2:has-text("Application Documents")')).toBeVisible();

    // The 'Passport' row should NOT be present because it's auto-imported
    // Only 'Photos' should be present
    // We check for the combobox displaying "Passport" which should NOT be found
    await expect(page.locator('z-combobox').filter({ hasText: 'Passport' })).toBeHidden();

    // 'Photos' should be visible
    await expect(page.locator('z-combobox').filter({ hasText: 'Photos' })).toBeVisible();

    // Verify Toast is NOT there
    const toastMessage = 'Passport file automatically imported from Customer profile';
    const toast = page.getByText(toastMessage);
    await expect(toast).toBeHidden();
  });
});
