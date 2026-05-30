import { signal } from '@angular/core';
import { of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import type { ThemePreferencePayload } from '@/core/services/theme.service';
import { initializeApplication } from './app.config';

describe('initializeApplication', () => {
  it('applies dynamic ui scaling during initialization and resize', async () => {
    const loggerInit = vi.fn();
    const originalZoom = document.documentElement.style.zoom;
    const originalScaledDvh = document.documentElement.style.getPropertyValue('--app-scaled-dvh');
    const originalInnerWidth = window.innerWidth;
    const originalInnerHeight = window.innerHeight;
    const resizeViewport = (width: number, height = originalInnerHeight) => {
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        writable: true,
        value: width,
      });
      Object.defineProperty(window, 'innerHeight', {
        configurable: true,
        writable: true,
        value: height,
      });
    };

    try {
      resizeViewport(1800, 1000);

      await initializeApplication({
        configService: {
          loadConfig: vi.fn().mockResolvedValue(undefined),
          settings: {
            theme: 'neutral',
            skeletonDebounceDurationMs: 250,
            title: 'BusinessSuite',
            uiScalePercent: 90,
            uiAutoScaleEnabled: true,
            uiAutoScaleReferenceWidth: 1440,
            uiAutoScaleMinPercent: 95,
            uiAutoScaleMaxPercent: 105,
            uiAutoScaleDesktopOnly: true,
          },
        } as any,
        themeService: {
          initializeTheme: vi.fn(),
          applyUserPreferences: vi.fn(),
        } as any,
        authService: {
          initMockAuth: vi.fn(),
          isAuthenticated: vi.fn().mockReturnValue(false),
        } as any,
        loggerService: {
          init: loggerInit,
        } as any,
        userSettingsApi: {
          getMe: vi.fn(),
        } as any,
        titleService: {
          setTitle: vi.fn(),
        } as any,
        rbacService: {
          rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
        } as any,
        rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
        isBrowser: true,
      });

      expect(loggerInit).toHaveBeenCalledOnce();
      expect(document.documentElement.style.zoom).toBe('0.945');
      expect(
        Number.parseFloat(document.documentElement.style.getPropertyValue('--app-scaled-dvh')),
      ).toBeCloseTo(1000 / 0.945, 3);

      resizeViewport(1400, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(document.documentElement.style.zoom).toBe('0.875');
      expect(
        Number.parseFloat(document.documentElement.style.getPropertyValue('--app-scaled-dvh')),
      ).toBeCloseTo(1000 / 0.875, 3);

      resizeViewport(1200, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(document.documentElement.style.zoom).toBe('0.855');
      expect(
        Number.parseFloat(document.documentElement.style.getPropertyValue('--app-scaled-dvh')),
      ).toBeCloseTo(1000 / 0.855, 3);
    } finally {
      document.documentElement.style.zoom = originalZoom;
      document.documentElement.style.setProperty('--app-scaled-dvh', originalScaledDvh);
      resizeViewport(originalInnerWidth, originalInnerHeight);
    }
  });

  it('continues shrinking below the old 80 percent auto-scale floor when desktop-only mode is disabled', async () => {
    const originalZoom = document.documentElement.style.zoom;
    const originalScaledDvh = document.documentElement.style.getPropertyValue('--app-scaled-dvh');
    const originalInnerWidth = window.innerWidth;
    const originalInnerHeight = window.innerHeight;
    const resizeViewport = (width: number, height = originalInnerHeight) => {
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        writable: true,
        value: width,
      });
      Object.defineProperty(window, 'innerHeight', {
        configurable: true,
        writable: true,
        value: height,
      });
    };

    try {
      resizeViewport(1200, 1000);

      await initializeApplication({
        configService: {
          loadConfig: vi.fn().mockResolvedValue(undefined),
          settings: {
            theme: 'neutral',
            skeletonDebounceDurationMs: 250,
            title: 'BusinessSuite',
            uiScalePercent: 98,
            uiAutoScaleEnabled: true,
            uiAutoScaleReferenceWidth: 1440,
            uiAutoScaleMinPercent: 60,
            uiAutoScaleMaxPercent: 120,
            uiAutoScaleDesktopOnly: false,
          },
        } as any,
        themeService: {
          initializeTheme: vi.fn(),
          applyUserPreferences: vi.fn(),
        } as any,
        authService: {
          initMockAuth: vi.fn(),
          isAuthenticated: vi.fn().mockReturnValue(false),
        } as any,
        loggerService: {
          init: vi.fn(),
        } as any,
        userSettingsApi: {
          getMe: vi.fn(),
        } as any,
        titleService: {
          setTitle: vi.fn(),
        } as any,
        rbacService: {
          rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
        } as any,
        rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
        isBrowser: true,
      });

      expect(Number.parseFloat(document.documentElement.style.zoom)).toBeCloseTo(0.8166666667, 6);

      resizeViewport(1000, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(Number.parseFloat(document.documentElement.style.zoom)).toBeCloseTo(0.6805555556, 6);

      resizeViewport(800, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(Number.parseFloat(document.documentElement.style.zoom)).toBeCloseTo(0.588, 6);
      expect(
        Number.parseFloat(document.documentElement.style.getPropertyValue('--app-scaled-dvh')),
      ).toBeCloseTo(1000 / 0.588, 3);
    } finally {
      document.documentElement.style.zoom = originalZoom;
      document.documentElement.style.setProperty('--app-scaled-dvh', originalScaledDvh);
      resizeViewport(originalInnerWidth, originalInnerHeight);
    }
  });

  it('keeps desktop-only scaling active until overlay menu reaches the mobile breakpoint', async () => {
    const originalZoom = document.documentElement.style.zoom;
    const originalScaledDvh = document.documentElement.style.getPropertyValue('--app-scaled-dvh');
    const originalInnerWidth = window.innerWidth;
    const originalInnerHeight = window.innerHeight;
    const resizeViewport = (width: number, height = originalInnerHeight) => {
      Object.defineProperty(window, 'innerWidth', {
        configurable: true,
        writable: true,
        value: width,
      });
      Object.defineProperty(window, 'innerHeight', {
        configurable: true,
        writable: true,
        value: height,
      });
    };

    try {
      resizeViewport(900, 1000);

      await initializeApplication({
        configService: {
          loadConfig: vi.fn().mockResolvedValue(undefined),
          settings: {
            theme: 'neutral',
            skeletonDebounceDurationMs: 250,
            title: 'BusinessSuite',
            useOverlayMenu: true,
            uiScalePercent: 100,
            uiAutoScaleEnabled: true,
            uiAutoScaleReferenceWidth: 1600,
            uiAutoScaleMinPercent: 25,
            uiAutoScaleMaxPercent: 120,
            uiAutoScaleDesktopOnly: true,
          },
        } as any,
        themeService: {
          initializeTheme: vi.fn(),
          applyUserPreferences: vi.fn(),
        } as any,
        authService: {
          initMockAuth: vi.fn(),
          isAuthenticated: vi.fn().mockReturnValue(false),
        } as any,
        loggerService: {
          init: vi.fn(),
        } as any,
        userSettingsApi: {
          getMe: vi.fn(),
        } as any,
        titleService: {
          setTitle: vi.fn(),
        } as any,
        rbacService: {
          rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
        } as any,
        rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
        isBrowser: true,
      });

      expect(document.documentElement.style.zoom).toBe('0.5625');

      resizeViewport(800, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(document.documentElement.style.zoom).toBe('0.5');

      resizeViewport(767, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(document.documentElement.style.zoom).toBe('0.48');

      resizeViewport(700, 1000);
      window.dispatchEvent(new Event('resize'));
      await new Promise((resolve) => window.requestAnimationFrame(() => resolve(undefined)));

      expect(document.documentElement.style.zoom).toBe('0.48');
      expect(
        Number.parseFloat(document.documentElement.style.getPropertyValue('--app-scaled-dvh')),
      ).toBeCloseTo(1000 / 0.48, 3);
    } finally {
      document.documentElement.style.zoom = originalZoom;
      document.documentElement.style.setProperty('--app-scaled-dvh', originalScaledDvh);
      resizeViewport(originalInnerWidth, originalInnerHeight);
    }
  });

  it('applies server theme preferences before initialization completes', async () => {
    const loadConfig = vi.fn().mockResolvedValue(undefined);
    const initMockAuth = vi.fn();
    const isAuthenticated = vi.fn().mockReturnValue(true);
    const loggerInit = vi.fn();
    const initializeTheme = vi.fn();
    const applyUserPreferences = vi.fn();
    const setTitle = vi.fn();
    const getMe = vi
      .fn()
      .mockReturnValue(of({ theme: 'blue', darkMode: true } satisfies ThemePreferencePayload));

    await initializeApplication({
      configService: {
        loadConfig,
        settings: { theme: 'neutral', skeletonDebounceDurationMs: 250, title: 'BusinessSuite' },
      } as any,
      themeService: {
        initializeTheme,
        applyUserPreferences,
      } as any,
      authService: {
        initMockAuth,
        isAuthenticated,
      } as any,
      loggerService: {
        init: loggerInit,
      } as any,
      userSettingsApi: {
        getMe,
      } as any,
      titleService: {
        setTitle,
      } as any,
      rbacService: {
        rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
      } as any,
      rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
      isBrowser: true,
    });

    expect(loggerInit).toHaveBeenCalledOnce();
    expect(loadConfig).toHaveBeenCalledOnce();
    expect(initMockAuth).toHaveBeenCalledOnce();
    expect(initializeTheme).toHaveBeenCalledWith('neutral');
    expect(getMe).toHaveBeenCalledOnce();
    expect(applyUserPreferences).toHaveBeenCalledWith({ theme: 'blue', darkMode: true }, 'neutral');
    expect(setTitle).toHaveBeenCalledWith('BusinessSuite');
  });

  it('keeps the baseline theme when server theme fetch fails', async () => {
    const initializeTheme = vi.fn();
    const applyUserPreferences = vi.fn();

    await initializeApplication({
      configService: {
        loadConfig: vi.fn().mockResolvedValue(undefined),
        settings: { theme: 'slate', skeletonDebounceDurationMs: 500, title: null },
      } as any,
      themeService: {
        initializeTheme,
        applyUserPreferences,
      } as any,
      authService: {
        initMockAuth: vi.fn(),
        isAuthenticated: vi.fn().mockReturnValue(true),
      } as any,
      loggerService: {
        init: vi.fn(),
      } as any,
      userSettingsApi: {
        getMe: vi.fn().mockReturnValue(throwError(() => new Error('nope'))),
      } as any,
      titleService: {
        setTitle: vi.fn(),
      } as any,
      rbacService: {
        rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
      } as any,
      rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
      isBrowser: true,
    });

    expect(initializeTheme).toHaveBeenCalledWith('slate');
    expect(applyUserPreferences).not.toHaveBeenCalled();
  });

  it('skips browser-only work during non-browser initialization', async () => {
    const loadConfig = vi.fn();

    await initializeApplication({
      configService: {
        loadConfig,
        settings: { theme: 'neutral' },
      } as any,
      themeService: {
        initializeTheme: vi.fn(),
        applyUserPreferences: vi.fn(),
      } as any,
      authService: {
        initMockAuth: vi.fn(),
        isAuthenticated: vi.fn(),
      } as any,
      loggerService: {
        init: vi.fn(),
      } as any,
      userSettingsApi: {
        getMe: vi.fn(),
      } as any,
      titleService: {
        setTitle: vi.fn(),
      } as any,
      rbacService: {
        rbacMyPermissionsRetrieve: vi.fn().mockReturnValue(of({ menus: {}, fields: {} })),
      } as any,
      rbacRulesSignal: signal({ menus: {}, fields: {} } as any),
      isBrowser: false,
    });

    expect(loadConfig).not.toHaveBeenCalled();
  });
});
