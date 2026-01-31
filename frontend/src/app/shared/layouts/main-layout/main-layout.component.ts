import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '@/core/services/auth.service';
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
        class="fixed md:relative inset-y-0 left-0 z-40 w-64 transform flex-col border-r bg-card transition-all duration-200 ease-in-out overflow-hidden"
      >
        <!-- Top Row: Logo Header -->
        <div class="h-32 border-b bg-accent/5 dark:bg-accent/10">
          <a
            routerLink="/dashboard"
            class="flex h-full w-full items-center justify-center rounded-md bg-card transition-transform hover:scale-[1.02] dark:bg-accent/20 overflow-hidden"
          >
            <img [src]="logoSrc()" alt="BusinessSuite Logo" class="h-full w-full object-contain" />
          </a>
        </div>

        <!-- Bottom Row: Navigation menu -->
        <div class="flex-1 overflow-y-auto p-4">
          <nav class="space-y-1 text-sm">
            <a
              routerLink="/dashboard"
              routerLinkActive="bg-accent"
              [routerLinkActiveOptions]="{ exact: true }"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
            >
              <z-icon zType="layout-dashboard" class="h-4 w-4" />
              Dashboard
            </a>
            <a
              routerLink="/customers"
              routerLinkActive="bg-accent"
              [routerLinkActiveOptions]="{ exact: true }"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
            >
              <z-icon zType="users" class="h-4 w-4" />
              Customers
            </a>
            <a
              routerLink="/applications"
              routerLinkActive="bg-accent"
              [routerLinkActiveOptions]="{ exact: true }"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
            >
              <z-icon zType="folder" class="h-4 w-4" />
              Applications
            </a>
            <a
              routerLink="/products"
              routerLinkActive="bg-accent"
              [routerLinkActiveOptions]="{ exact: true }"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
            >
              <z-icon zType="archive" class="h-4 w-4" />
              Products
            </a>
            <a
              routerLink="/invoices"
              routerLinkActive="bg-accent"
              [routerLinkActiveOptions]="{ exact: true }"
              class="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
            >
              <z-icon zType="file-text" class="h-4 w-4" />
              Invoices
            </a>

            <div class="pt-4 pb-1">
              <button
                (click)="toggleLetters()"
                class="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
              >
                <div class="flex items-center gap-3">
                  <z-icon zType="file-text" class="h-4 w-4" />
                  <span>Letters</span>
                </div>
                <z-icon
                  [zType]="lettersExpanded() ? 'chevron-down' : 'chevron-right'"
                  class="h-3 w-3"
                />
              </button>

              <div *ngIf="lettersExpanded()" class="mt-1 space-y-1 pl-7">
                <a
                  routerLink="/letters/surat-permohonan"
                  routerLinkActive="bg-accent text-foreground"
                  [routerLinkActiveOptions]="{ exact: true }"
                  class="block rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
                >
                  Surat Permohonan
                </a>
              </div>
            </div>

            <!-- Admin Section - Only visible for superusers -->
            <div *ngIf="isAdminUser()" class="pt-4 pb-1">
              <button
                (click)="toggleAdmin()"
                class="flex w-full items-center justify-between gap-3 rounded-md px-3 py-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground transition-colors hover:bg-accent/50 hover:text-foreground"
              >
                <div class="flex items-center gap-3">
                  <z-icon zType="settings" class="h-4 w-4" />
                  <span>Admin</span>
                </div>
                <z-icon
                  [zType]="adminExpanded() ? 'chevron-down' : 'chevron-right'"
                  class="h-3 w-3"
                />
              </button>

              <div *ngIf="adminExpanded()" class="mt-1 space-y-1 pl-7">
                <a
                  routerLink="/admin/document-types"
                  routerLinkActive="bg-accent text-foreground"
                  class="block rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
                >
                  Document Types
                </a>
                <a
                  routerLink="/admin/backups"
                  routerLinkActive="bg-accent text-foreground"
                  class="block rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
                >
                  Backups
                </a>
                <a
                  routerLink="/admin/server"
                  routerLinkActive="bg-accent text-foreground"
                  class="block rounded-md px-3 py-1.5 text-muted-foreground transition-colors hover:text-foreground hover:bg-accent/50"
                >
                  Server Management
                </a>
              </div>
            </div>
          </nav>
        </div>
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
  lettersExpanded = signal(true);
  adminExpanded = signal(false);

  private themeService = inject(ThemeService);
  private authService = inject(AuthService);

  logoSrc = computed(() =>
    // Use assets path to ensure the dev-server and production builds serve the images reliably
    this.themeService.isDarkMode()
      ? '/assets/logo_inverted_transparent.png'
      : '/assets/logo_transparent.png',
  );

  isAdminUser = computed(() => this.authService.isSuperuser());

  toggleSidebar() {
    this.sidebarOpen = !this.sidebarOpen;
  }

  toggleLetters() {
    this.lettersExpanded.update((v) => !v);
  }

  toggleAdmin() {
    this.adminExpanded.update((v) => !v);
  }
}
