import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { ThemeService } from '@/core/services/theme.service';
import { ZardAvatarComponent } from '@/shared/components/avatar';
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
    ZardIconComponent,
    // Expose theme switcher in header
    ThemeSwitcherComponent,
  ],
  template: `
    <div class="flex h-screen bg-background text-foreground overflow-hidden">
      <aside
        [class.-translate-x-full]="!sidebarOpen"
        [ngClass]="
          sidebarOpen ? 'md:w-64 md:visible md:opacity-100' : 'md:w-0 md:invisible md:opacity-0'
        "
        class="fixed md:relative inset-y-0 left-0 z-40 w-64 transform flex-col border-r bg-card p-4 transition-all duration-200 ease-in-out overflow-hidden"
      >
        <img
          [src]="logoSrc()"
          alt="BusinessSuite Logo"
          class="block w-full max-w-full h-auto mb-6 object-contain"
        />
        <nav class="space-y-2 text-sm">
          <a
            routerLink="/dashboard"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="block rounded px-3 py-2 hover:bg-accent"
            >Dashboard</a
          >
          <a
            routerLink="/customers"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="block rounded px-3 py-2 hover:bg-accent"
            >Customers</a
          >
          <a
            routerLink="/applications"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="block rounded px-3 py-2 hover:bg-accent"
            >Applications</a
          >
          <a
            routerLink="/products"
            routerLinkActive="active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="block rounded px-3 py-2 hover:bg-accent"
            >Products</a
          >
        </nav>
      </aside>

      <!-- backdrop for mobile when sidebar is open -->
      <div
        *ngIf="sidebarOpen"
        class="fixed inset-0 bg-black/40 z-30 md:hidden"
        (click)="sidebarOpen = false"
      ></div>

      <div class="flex flex-1 flex-col md:pl-0">
        <header class="flex h-16 items-center justify-between border-b bg-card px-6">
          <div class="flex items-center gap-3">
            <button
              type="button"
              class="p-2 mr-2 rounded hover:bg-accent"
              (click)="toggleSidebar()"
            >
              <z-icon [zType]="sidebarOpen ? 'chevron-left' : 'panel-left'" />
            </button>
            <div class="text-sm font-medium">Welcome back</div>
          </div>

          <div class="flex items-center gap-3">
            <!-- Theme switcher visible in header -->
            <app-theme-switcher />

            <span class="text-sm text-muted-foreground">revisadmin</span>
            <z-avatar class="h-8 w-8" zFallback="RA" />
          </div>
        </header>

        <main class="flex-1 p-6 overflow-y-auto">
          <router-outlet />
        </main>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MainLayoutComponent {
  sidebarOpen = true;

  private themeService = inject(ThemeService);
  logoSrc = computed(() =>
    // Use assets path to ensure the dev-server and production builds serve the images reliably
    this.themeService.isDarkMode()
      ? '/assets/logo_inverted_transparent.png'
      : '/assets/logo_transparent.png',
  );

  toggleSidebar() {
    this.sidebarOpen = !this.sidebarOpen;
  }
}
