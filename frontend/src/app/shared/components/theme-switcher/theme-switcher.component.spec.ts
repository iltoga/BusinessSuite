import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { UserSettingsApiService } from '@/core/api/user-settings.service';
import { AuthService } from '@/core/services/auth.service';
import { ThemeService } from '@/core/services/theme.service';
import { ThemeSwitcherComponent } from './theme-switcher.component';

describe('ThemeSwitcherComponent', () => {
  let themeService: ThemeService;
  let authServiceMock: { isAuthenticated: ReturnType<typeof vi.fn> };
  let userSettingsApiMock: { patchMe: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    TestBed.resetTestingModule();
    authServiceMock = { isAuthenticated: vi.fn(() => false) };
    userSettingsApiMock = { patchMe: vi.fn(() => of({})) };

    TestBed.configureTestingModule({
      providers: [
        ThemeService,
        { provide: AuthService, useValue: authServiceMock },
        { provide: UserSettingsApiService, useValue: userSettingsApiMock },
      ],
    });

    themeService = TestBed.inject(ThemeService);
    themeService.applyUserPreferences({ theme: 'neutral', dark_mode: false }, 'neutral', false);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    window.localStorage?.clear?.();
    document.documentElement.className = '';
    document.documentElement.style.cssText = '';
    TestBed.resetTestingModule();
  });

  it('toggles dark mode locally and persists it when authenticated', () => {
    authServiceMock.isAuthenticated.mockReturnValue(true);
    const setDarkModeSpy = vi.spyOn(themeService, 'setDarkMode');
    const component = TestBed.runInInjectionContext(() => new ThemeSwitcherComponent());

    component.toggleDarkMode();

    expect(setDarkModeSpy).toHaveBeenCalledWith(true);
    expect(userSettingsApiMock.patchMe).toHaveBeenCalledWith({ dark_mode: true });
  });

  it('toggles dark mode locally without server persistence when anonymous', () => {
    const setDarkModeSpy = vi.spyOn(themeService, 'setDarkMode');
    const component = TestBed.runInInjectionContext(() => new ThemeSwitcherComponent());

    component.toggleDarkMode();

    expect(setDarkModeSpy).toHaveBeenCalledWith(true);
    expect(userSettingsApiMock.patchMe).not.toHaveBeenCalled();
  });

  it('formats theme names for display', () => {
    const component = TestBed.runInInjectionContext(() => new ThemeSwitcherComponent());

    expect(component.formatThemeName('revis')).toBe('Revis');
    expect(component.formatThemeName('')).toBe('');
  });
});
