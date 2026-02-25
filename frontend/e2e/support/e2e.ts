import { expect, test as base } from '@playwright/test';

const DEFAULT_APP_CONFIG = {
  MOCK_AUTH_ENABLED: 'True',
  title: 'RevisBali CRM',
};

const DEFAULT_MOCK_AUTH_CONFIG = {
  sub: 'mock-user',
  username: 'mock-user',
  email: 'mock@example.com',
  roles: ['admin'],
  groups: ['admin'],
  isSuperuser: true,
  isStaff: true,
};

const DEFAULT_USER_SETTINGS = {
  theme: 'zinc',
  dark_mode: true,
};

export const test = base.extend<{
  mockAuthSession: void;
}>({
  mockAuthSession: [
    async ({ page }, use) => {
      await page.addInitScript(() => {
        try {
          localStorage.setItem('auth_token', 'mock-token');
          localStorage.setItem('auth_refresh_token', 'mock-refresh');
          (window as any).APP_CONFIG = { MOCK_AUTH_ENABLED: 'True' };
        } catch {
          // Ignore storage errors in non-browser contexts.
        }
      });

      await page.route(/\/api\/app-config\/?(\?.*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_APP_CONFIG),
        });
      });

      await page.route(/\/api\/mock-auth-config\/?(\?.*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_MOCK_AUTH_CONFIG),
        });
      });

      await page.route(/\/api\/user-settings\/me\/?(\?.*)?$/, async (route) => {
        await route.fulfill({
          status: 200,
          contentType: 'application/json',
          body: JSON.stringify(DEFAULT_USER_SETTINGS),
        });
      });

      await use();
    },
    { auto: true },
  ],
});

export { expect };
export type { Page } from '@playwright/test';
