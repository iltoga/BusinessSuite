import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { ThemeService } from '@/core/services/theme.service';
import { ZardAvatarComponent } from '@/shared/components/avatar';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardDropdownImports } from '@/shared/components/dropdown';
import { ZardIconComponent } from '@/shared/components/icon';
import { ThemeSwitcherComponent } from '@/shared/components/theme-switcher/theme-switcher.component';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    RouterLinkActive,
    ZardAvatarComponent,
    ZardButtonComponent,
    ZardIconComponent,
    ZardDropdownImports,
    // Expose theme switcher in header
    ThemeSwitcherComponent,
  ],
  templateUrl: './main-layout.component.html',
  styleUrls: ['./main-layout.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MainLayoutComponent {
  sidebarOpen = true;
  lettersExpanded = signal(true);
  adminExpanded = signal(false);

  private themeService = inject(ThemeService);
  private authService = inject(AuthService);
  private configService = inject(ConfigService);

  logoSrc = computed(() => {
    // Use assets path to ensure the dev-server and production builds serve the images reliably
    const cfg = this.configService.settings;
    const normal = `/assets/${cfg.logoFilename || 'logo_transparent.png'}`;
    const inverted = `/assets/${cfg.logoInvertedFilename || 'logo_inverted_transparent.png'}`;
    return this.themeService.isDarkMode() ? inverted : normal;
  });

  isAdminUser = computed(() => this.authService.isSuperuser());
  userFullName = computed(() => this.authService.claims()?.fullName || 'User');
  userEmail = computed(() => this.authService.claims()?.email || '');
  userAvatar = computed(() => this.authService.claims()?.avatar || undefined);
  userInitials = computed(() => {
    const fullName = this.userFullName();
    if (!fullName) return 'U';
    return fullName
      .split(' ')
      .map((n) => n[0])
      .join('')
      .toUpperCase()
      .substring(0, 2);
  });

  toggleSidebar() {
    this.sidebarOpen = !this.sidebarOpen;
  }

  toggleLetters() {
    this.lettersExpanded.update((v) => !v);
  }

  toggleAdmin() {
    this.adminExpanded.update((v) => !v);
  }

  logout() {
    this.authService.logout();
  }
}
