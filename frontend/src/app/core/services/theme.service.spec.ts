import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ThemeService } from './theme.service';

const originalLocalStorage = window.localStorage;

const createLocalStorageMock = (seed: Record<string, string> = {}): Storage => {
  const store = new Map(Object.entries(seed));
  return {
    clear: vi.fn(() => {
      store.clear();
    }),
    getItem: vi.fn((key: string) => (store.has(key) ? store.get(key)! : null)),
    key: vi.fn((index: number) => Array.from(store.keys())[index] ?? null),
    length: 0,
    removeItem: vi.fn((key: string) => {
      store.delete(key);
    }),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, String(value));
    }),
  } as unknown as Storage;
};

const installLocalStorageMock = (mock: Storage) => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: mock,
  });
};

const restoreLocalStorage = () => {
  installLocalStorageMock(originalLocalStorage);
};

describe('ThemeService', () => {
  let service: ThemeService;
  let localStorageMock: Storage;

  beforeEach(() => {
    localStorageMock = createLocalStorageMock();
    installLocalStorageMock(localStorageMock);
    document.documentElement.className = '';
    document.documentElement.style.cssText = '';
    service = new ThemeService();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    restoreLocalStorage();
    document.documentElement.className = '';
    document.documentElement.style.cssText = '';
    TestBed.resetTestingModule();
  });

  it('applies user preferences and persists them to localStorage', () => {
    service.applyUserPreferences({ theme: 'gundam', dark_mode: true });

    expect(service.currentTheme()).toBe('gundam');
    expect(service.isDarkMode()).toBe(true);
    expect(localStorageMock.getItem('theme')).toBe('gundam');
    expect(localStorageMock.getItem('darkMode')).toBe('true');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--background')).toContain('oklch');
  });

  it('setTheme preserves the current dark mode while updating CSS variables', () => {
    service.applyUserPreferences({ theme: 'neutral', dark_mode: true }, 'neutral', false);
    service.setTheme('revis');

    expect(service.currentTheme()).toBe('revis');
    expect(service.isDarkMode()).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);
    expect(document.documentElement.style.getPropertyValue('--primary')).toContain('oklch');
  });

  it('toggleDarkMode flips the mode and persists the new value', () => {
    service.applyUserPreferences({ theme: 'neutral', dark_mode: false });

    service.toggleDarkMode();

    expect(service.isDarkMode()).toBe(true);
    expect(localStorageMock.getItem('darkMode')).toBe('true');
    expect(document.documentElement.classList.contains('dark')).toBe(true);
  });

  it('initializeTheme prefers saved localStorage values over system preference', () => {
    localStorageMock.setItem('theme', 'teal');
    localStorageMock.setItem('darkMode', 'false');
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });

    service.initializeTheme('neutral');

    expect(service.currentTheme()).toBe('teal');
    expect(service.isDarkMode()).toBe(false);
    expect(document.documentElement.classList.contains('dark')).toBe(false);

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: originalMatchMedia,
    });
  });

  it('initializeTheme follows the system preference when no saved dark mode exists', () => {
    localStorageMock.setItem('theme', 'silver');
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({
        matches: true,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });

    service.initializeTheme('neutral');

    expect(service.currentTheme()).toBe('silver');
    expect(service.isDarkMode()).toBe(true);
    expect(document.documentElement.classList.contains('dark')).toBe(true);

    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: originalMatchMedia,
    });
  });

  it('falls back to the default theme when theme normalization fails', () => {
    service.setTheme('neutral');
    service.applyUserPreferences({ theme: 'not-a-theme' }, 'revis', false);

    expect(service.currentTheme()).toBe('revis');
  });

  it('uses the default theme when storage is unavailable', () => {
    const getStorageSpy = vi.spyOn(service as any, 'getStorage').mockReturnValue(null);
    const originalMatchMedia = window.matchMedia;
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: vi.fn(() => ({
        matches: false,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
      })),
    });

    service.initializeTheme('legacy');

    expect(service.currentTheme()).toBe('legacy');
    expect(service.isDarkMode()).toBe(false);
    expect(localStorageMock.getItem('theme')).toBeNull();

    getStorageSpy.mockRestore();
    Object.defineProperty(window, 'matchMedia', {
      configurable: true,
      value: originalMatchMedia,
    });
  });
});
