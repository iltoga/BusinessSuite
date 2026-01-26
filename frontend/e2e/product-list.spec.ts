import { expect, test } from '@playwright/test';

test.describe('Product list and detail', () => {
  test('list shows type and base price and detail opens', async ({ page }) => {
    await page.goto('/products');

    // Wait for page heading to be visible to confirm page load
    await expect(page.getByRole('heading', { name: 'Products' })).toBeVisible();
    // Check first product row contains Type and Base Price
    const firstRow = page.locator('table tbody tr').first();
    await expect(firstRow).toContainText('Visa');
    // Base price should render and include currency symbol or digits
    await expect(firstRow).toContainText('Rp');
    // Description column should display the product description
    await expect(firstRow).toContainText('Airport grab');

    // Click view on first row and check detail
    await firstRow.getByRole('link', { name: 'View' }).click();

    await expect(page).toHaveURL(/\/products\/[0-9]+/);
    await expect(page.getByText('Product Detail')).toBeVisible();
    // Base price should appear in details
    await expect(page.locator('text=Base price')).toBeVisible();
  });
});
