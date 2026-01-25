import { ThemeService } from '@/core/services/theme.service';
import { ThemeName } from '@/core/theme.config';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';
import { Component, inject } from '@angular/core';

/**
 * Theme Switcher Component
 *
 * A standalone component that provides UI controls for switching themes
 * and toggling dark mode.
 *
 * Usage:
 * ```html
 * <app-theme-switcher />
 * ```
 *
 * You can add this to your header, settings page, or anywhere in your app.
 */
@Component({
  selector: 'app-theme-switcher',
  standalone: true,
  imports: [ZardButtonComponent, ZardIconComponent],
  template: `
    <div class="flex gap-4 items-center">
      <!-- Theme Selector -->
      <label class="flex items-center gap-2">
        <span class="text-sm font-medium">Theme:</span>
        <select
          [value]="currentTheme()"
          (change)="onThemeChange($event)"
          class="border border-input rounded-md px-3 py-1.5 text-sm bg-background focus:outline-none focus:ring-2 focus:ring-ring"
        >
          @for (theme of availableThemes; track theme) {
            <option [value]="theme">
              {{ formatThemeName(theme) }}
            </option>
          }
        </select>
      </label>

      <!-- Dark Mode Toggle -->
      <button
        z-button
        zVariant="outline"
        zSize="sm"
        (click)="toggleDarkMode()"
        class="flex items-center gap-2"
      >
        <span>{{ isDarkMode() ? '🌙' : '☀️' }}</span>
        <span>{{ isDarkMode() ? 'Dark' : 'Light' }}</span>
      </button>
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
      }
    `,
  ],
})
export class ThemeSwitcherComponent {
  private themeService = inject(ThemeService);

  // Reactive signals from theme service
  currentTheme = this.themeService.currentTheme;
  isDarkMode = this.themeService.isDarkMode;

  // Get all available themes
  availableThemes = this.themeService.getAvailableThemes();

  /**
   * Handle theme selection change
   */
  onThemeChange(event: Event): void {
    const select = event.target as HTMLSelectElement;
    const theme = select.value as ThemeName;
    this.themeService.setTheme(theme);
  }

  /**
   * Toggle between light and dark mode
   */
  toggleDarkMode(): void {
    this.themeService.toggleDarkMode();
  }

  /**
   * Format theme name for display (capitalize first letter)
   */
  formatThemeName(theme: string): string {
    return theme.charAt(0).toUpperCase() + theme.slice(1);
  }
}
