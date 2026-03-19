import { describe, expect, it, vi } from 'vitest';
import { of, throwError } from 'rxjs';

import { initializeApplication } from './app.config';
import type { ThemePreferencePayload } from '@/core/services/theme.service';

describe('initializeApplication', () => {
  it('applies server theme preferences before initialization completes', async () => {
    const loadConfig = vi.fn().mockResolvedValue(undefined);
    const initMockAuth = vi.fn();
    const isAuthenticated = vi.fn().mockReturnValue(true);
    const loggerInit = vi.fn();
    const initializeTheme = vi.fn();
    const applyUserPreferences = vi.fn();
    const setTitle = vi.fn();
    const getMe = vi.fn().mockReturnValue(
      of({ theme: 'blue', darkMode: true } satisfies ThemePreferencePayload),
    );

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
      isBrowser: false,
    });

    expect(loadConfig).not.toHaveBeenCalled();
  });
});