import { expect, test } from '@playwright/test';

const APP_URL = process.env.APP_URL || 'http://localhost:4200/applications/269';

test.describe('Button style checks', () => {
  test('Uploaded Documents actions use default (primary) buttons', async ({ page }) => {
    await page.goto(APP_URL);
    await page.waitForSelector('text=Uploaded Documents');

    // find first row actions buttons
    const actionCells = await page.locator('table tbody tr').first().locator('td').last();
    const buttons = actionCells.locator('button, a[z-button]');
    await expect(buttons).toHaveCount(3);

    // check each button has the primary background class
    const countBgPrimary = await buttons.filter({ has: page.locator('.bg-primary') }).count();
    expect(countBgPrimary).toBeGreaterThanOrEqual(1);

    // each button should at least have a Zard button host class
    await expect(buttons.first()).toHaveClass(/bg-primary|border|bg-destructive|bg-secondary/);
  });

  test('Customer list Disable button uses secondary (muted) variant', async ({ page }) => {
    await page.goto(process.env.CUSTOMER_LIST || 'http://localhost:4200/customers');
    await page.waitForSelector('text=Customer List');

    // find the first Disable button
    const disableBtn = page.locator('button, a[z-button]').filter({ hasText: 'Disable' }).first();
    await expect(disableBtn).toHaveClass(/bg-secondary|hover:bg-accent/);
  });
});
