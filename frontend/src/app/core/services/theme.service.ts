import { Injectable, signal } from '@angular/core';
import { getTheme, ThemeColors, ThemeName, THEMES } from '../theme.config';

export interface ThemePreferencePayload {
  theme?: ThemeName | string | null;
  dark_mode?: boolean | null;
  darkMode?: boolean | null;
}

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
 *   this.themeService.currentTheme();
 * }
 * ```
 */
@Injectable({
  providedIn: 'root',
})
export class ThemeService {
  // Avoid capturing platform at construction time; check runtime environment when needed.
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
   * Apply theme + dark mode together from a server/local preference payload.
   * This avoids transient double-applies during bootstrap.
   */
  applyUserPreferences(
    settings: ThemePreferencePayload | null | undefined,
    defaultTheme: ThemeName = 'neutral',
    persistToLocalStorage = true,
  ): void {
    const resolvedTheme = this.normalizeThemeName(settings?.theme, defaultTheme);
    const resolvedDarkMode = this.resolveDarkModePreference(settings);
    this.applyThemeState(resolvedTheme, resolvedDarkMode, persistToLocalStorage);
  }

  /**
   * Apply a theme by name
   */
  setTheme(themeName: ThemeName, persistToLocalStorage = true): void {
    const resolvedTheme = this.normalizeThemeName(themeName, 'neutral');
    this.applyThemeState(resolvedTheme, this._isDarkMode(), persistToLocalStorage);
  }

  /**
   * Toggle between light and dark mode
   */
  toggleDarkMode(): void {
    this.applyThemeState(this._currentTheme(), !this._isDarkMode(), true);
  }

  /**
   * Set dark mode state explicitly
   */
  setDarkMode(isDark: boolean): void {
    this.applyThemeState(this._currentTheme(), isDark, true);
  }

  /**
   * Initialize theme from localStorage or default
   */
  initializeTheme(defaultTheme: ThemeName = 'neutral'): void {
    // If not running in a browser, apply the default theme without attempting to
    // read/write localStorage.
    if (typeof window === 'undefined') {
      this.setTheme(defaultTheme, false);
      return;
    }

    const storage = this.getStorage();

    // Load theme from localStorage or use default
    const savedTheme = storage?.getItem('theme') as ThemeName | null;
    const themeName = this.normalizeThemeName(savedTheme, defaultTheme);

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

    this.applyThemeState(themeName, this._isDarkMode(), false);

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
    if (typeof document === 'undefined') {
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

    // Ensure semantic foreground fallbacks are applied (some palettes omit them)
    this.setCssVar(
      root,
      '--destructive-foreground',
      (theme as any).destructiveForeground ?? theme.foreground,
    );
    this.setCssVar(
      root,
      '--warning-foreground',
      (theme as any).warningForeground ?? theme.foreground,
    );
    this.setCssVar(
      root,
      '--success-foreground',
      (theme as any).successForeground ?? theme.foreground,
    );

    // Sidebar variables (optional in theme)
    if ((theme as any).sidebar) this.setCssVar(root, '--sidebar', (theme as any).sidebar);
    if ((theme as any).sidebarForeground)
      this.setCssVar(root, '--sidebar-foreground', (theme as any).sidebarForeground);
    if ((theme as any).sidebarPrimary)
      this.setCssVar(root, '--sidebar-primary', (theme as any).sidebarPrimary);
    if ((theme as any).sidebarPrimaryForeground)
      this.setCssVar(root, '--sidebar-primary-foreground', (theme as any).sidebarPrimaryForeground);

    // Toggle .dark class on html element for TailwindCSS
    if (this._isDarkMode()) {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }

  private applyThemeState(
    themeName: ThemeName,
    isDarkMode: boolean,
    persistToLocalStorage: boolean,
  ): void {
    this._currentTheme.set(themeName);
    this._isDarkMode.set(isDarkMode);

    if (persistToLocalStorage) {
      this.persistPreferences(themeName, isDarkMode);
    }

    this.applyThemeColors();
  }

  private persistPreferences(themeName: ThemeName, isDarkMode: boolean): void {
    const storage = this.getStorage();
    if (!storage) {
      return;
    }

    try {
      storage.setItem('theme', themeName);
      storage.setItem('darkMode', String(isDarkMode));
    } catch (err) {
      console.warn('[ThemeService] Failed to persist theme preferences to localStorage.', err);
    }
  }

  private normalizeThemeName(
    themeName: ThemeName | string | null | undefined,
    fallback: ThemeName,
  ): ThemeName {
    if (themeName && THEMES[themeName as ThemeName]) {
      return themeName as ThemeName;
    }

    if (themeName) {
      console.warn(`Theme "${themeName}" not found. Falling back to "${fallback}".`);
    }

    return THEMES[fallback] ? fallback : 'neutral';
  }

  private resolveDarkModePreference(settings: ThemePreferencePayload | null | undefined): boolean {
    const requestedDarkMode = settings?.dark_mode ?? settings?.darkMode;
    return typeof requestedDarkMode === 'boolean' ? requestedDarkMode : this._isDarkMode();
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
    // Determine browser availability dynamically so the service works even when
    // instantiated during SSR and later reused in the browser (hydration).
    if (typeof window === 'undefined' || typeof window.localStorage === 'undefined') {
      return null;
    }

    try {
      const storage = window.localStorage as Storage | undefined;
      if (!storage || typeof storage.getItem !== 'function') {
        return null;
      }
      return storage;
    } catch (err) {
      console.warn('[ThemeService] localStorage is not accessible.', err);
      return null;
    }
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
