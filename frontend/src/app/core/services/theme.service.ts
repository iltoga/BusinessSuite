import { isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { getTheme, ThemeColors, ThemeName, THEMES } from '../theme.config';

/**
 * Theme Service
 *
 * Manages application theming by dynamically applying CSS variables
 * based on selected theme and dark mode state.
 *
 * Usage:
 * ```typescript
 * constructor(private themeService: ThemeService) {}
 *
 * ngOnInit() {
 *   // Apply a theme
 *   this.themeService.setTheme('blue');
 *
 *   // Or get current theme
 *   console.log(this.themeService.currentTheme());
 * }
 * ```
 */
@Injectable({
  providedIn: 'root',
})
export class ThemeService {
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  private readonly _currentTheme = signal<ThemeName>('neutral');
  private readonly _isDarkMode = signal<boolean>(false);

  /**
   * Current theme name (reactive signal)
   */
  readonly currentTheme = this._currentTheme.asReadonly();

  /**
   * Whether dark mode is active (reactive signal)
   */
  readonly isDarkMode = this._isDarkMode.asReadonly();

  /**
   * Apply a theme by name
   */
  setTheme(themeName: ThemeName, persistToLocalStorage = true): void {
    if (!THEMES[themeName]) {
      console.warn(`Theme "${themeName}" not found. Falling back to "neutral".`);
      themeName = 'neutral';
    }

    this._currentTheme.set(themeName);

    // Persist to localStorage
    const storage = this.getStorage();
    if (persistToLocalStorage && storage) {
      storage.setItem('theme', themeName);
    }

    // Apply theme colors
    this.applyThemeColors();

    console.log(`✅ Theme applied: ${themeName}`);
  }

  /**
   * Toggle between light and dark mode
   */
  toggleDarkMode(): void {
    this._isDarkMode.set(!this._isDarkMode());
    this.applyThemeColors();

    // Persist to localStorage
    const storage = this.getStorage();
    if (storage) {
      storage.setItem('darkMode', String(this._isDarkMode()));
    }
  }

  /**
   * Set dark mode state explicitly
   */
  setDarkMode(isDark: boolean): void {
    this._isDarkMode.set(isDark);
    this.applyThemeColors();

    // Persist to localStorage
    const storage = this.getStorage();
    if (storage) {
      storage.setItem('darkMode', String(isDark));
    }
  }

  /**
   * Initialize theme from localStorage or default
   */
  initializeTheme(defaultTheme: ThemeName = 'neutral'): void {
    if (!this.isBrowser) {
      // Server-side rendering or non-browser environment
      this.setTheme(defaultTheme, false);
      return;
    }

    const storage = this.getStorage();

    // Load theme from localStorage or use default
    const savedTheme = storage?.getItem('theme') as ThemeName | null;
    const themeName = savedTheme && THEMES[savedTheme] ? savedTheme : defaultTheme;

    // Load dark mode preference from localStorage
    const savedDarkMode = storage?.getItem('darkMode');
    if (savedDarkMode !== null && savedDarkMode !== undefined) {
      this._isDarkMode.set(savedDarkMode === 'true');
    } else {
      // Check system preference
      const prefersDark =
        typeof window !== 'undefined' &&
        typeof window.matchMedia === 'function' &&
        window.matchMedia('(prefers-color-scheme: dark)').matches;
      this._isDarkMode.set(Boolean(prefersDark));
    }

    this.setTheme(themeName, false);

    // Listen for system dark mode changes
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', (e) => {
        if (storage?.getItem('darkMode') === null) {
          this.setDarkMode(e.matches);
        }
      });
    }
  }

  /**
   * Apply theme colors to CSS variables
   */
  private applyThemeColors(): void {
    if (!this.isBrowser || typeof document === 'undefined') {
      return;
    }

    const mode = this._isDarkMode() ? 'dark' : 'light';
    const theme = getTheme(this._currentTheme(), mode);
    const root = document.documentElement;

    // Apply all theme colors as CSS variables
    this.setCssVar(root, '--background', theme.background);
    this.setCssVar(root, '--foreground', theme.foreground);
    this.setCssVar(root, '--card', theme.card);
    this.setCssVar(root, '--card-foreground', theme.cardForeground);
    this.setCssVar(root, '--popover', theme.popover);
    this.setCssVar(root, '--popover-foreground', theme.popoverForeground);
    this.setCssVar(root, '--primary', theme.primary);
    this.setCssVar(root, '--primary-foreground', theme.primaryForeground);
    this.setCssVar(root, '--secondary', theme.secondary);
    this.setCssVar(root, '--secondary-foreground', theme.secondaryForeground);
    this.setCssVar(root, '--muted', theme.muted);
    this.setCssVar(root, '--muted-foreground', theme.mutedForeground);
    this.setCssVar(root, '--accent', theme.accent);
    this.setCssVar(root, '--accent-foreground', theme.accentForeground);
    this.setCssVar(root, '--destructive', theme.destructive);
    this.setCssVar(root, '--warning', theme.warning);
    this.setCssVar(root, '--success', theme.success);
    this.setCssVar(root, '--border', theme.border);
    this.setCssVar(root, '--input', theme.input);
    this.setCssVar(root, '--ring', theme.ring);

    // Optional: Apply chart colors if defined
    if (theme.chart1) this.setCssVar(root, '--chart-1', theme.chart1);
    if (theme.chart2) this.setCssVar(root, '--chart-2', theme.chart2);
    if (theme.chart3) this.setCssVar(root, '--chart-3', theme.chart3);
    if (theme.chart4) this.setCssVar(root, '--chart-4', theme.chart4);
    if (theme.chart5) this.setCssVar(root, '--chart-5', theme.chart5);

    // Toggle .dark class on html element for TailwindCSS
    if (this._isDarkMode()) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }

  /**
   * Helper to set CSS variable
   */
  private setCssVar(element: HTMLElement, varName: string, value: string): void {
    element.style.setProperty(varName, value);
  }

  /**
   * Safe access to localStorage (browser only)
   */
  private getStorage(): Storage | null {
    if (!this.isBrowser) {
      return null;
    }

    const storage = globalThis?.localStorage as Storage | undefined;
    if (!storage || typeof storage.getItem !== 'function') {
      return null;
    }

    return storage;
  }

  /**
   * Get all available theme names
   */
  getAvailableThemes(): ThemeName[] {
    return Object.keys(THEMES) as ThemeName[];
  }

  /**
   * Get theme colors for a specific theme and mode
   */
  getThemeColors(themeName: ThemeName, mode: 'light' | 'dark' = 'light'): ThemeColors {
    return getTheme(themeName, mode);
  }
}
