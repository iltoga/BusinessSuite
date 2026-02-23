import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  OnDestroy,
  PLATFORM_ID,
  QueryList,
  signal,
  ViewChild,
  ViewChildren,
} from '@angular/core';
import { Router, RouterLink, RouterLinkActive, RouterOutlet } from '@angular/router';

import { AuthService } from '@/core/services/auth.service';
import { ReminderDialogService } from '@/core/services/reminder-dialog.service';
import {
  ReminderInboxService,
  type ReminderInboxItem,
} from '@/core/services/reminder-inbox.service';
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
export class MainLayoutComponent implements AfterViewInit, OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  sidebarOpen = signal(true);
  utilitiesExpanded = signal(false);
  lettersExpanded = signal(false);
  reportsExpanded = signal(false);
  adminExpanded = signal(false);

  @ViewChildren('sidebarItem', { read: ElementRef })
  private sidebarItems!: QueryList<ElementRef<HTMLElement>>;
  @ViewChild('lettersToggle', { read: ElementRef })
  private lettersToggle?: ElementRef<HTMLElement>;

  private themeService = inject(ThemeService);
  private authService = inject(AuthService);
  private reminderDialogService = inject(ReminderDialogService);
  private reminderInboxService = inject(ReminderInboxService);
  private router = inject(Router);

  logoSrc = computed(() => {
    // Hardcoded static paths — dynamic loading from config has been removed.
    const normal = '/assets/logo_transparent.png';
    const inverted = '/assets/logo_inverted_transparent.png';
    return this.themeService.isDarkMode() ? inverted : normal;
  });

  isStaff = computed(() => this.authService.isStaff());
  isSuperuser = computed(() => this.authService.isSuperuser());
  isInAdminGroup = computed(() => this.authService.isInAdminGroup());
  canAccessProducts = computed(() => this.authService.isAdminOrManager());
  canAccessReports = computed(() => this.authService.isAdminOrManager());
  canAccessStaffAdminItems = computed(() => this.isStaff() || this.isInAdminGroup());
  canAccessBackups = computed(() => this.isSuperuser() || this.isInAdminGroup());
  canAccessAdminSection = computed(
    () => this.canAccessStaffAdminItems() || this.canAccessBackups() || this.isInAdminGroup(),
  );
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
  reminderUnreadCount = this.reminderInboxService.unreadCount;
  reminderInboxItems = this.reminderInboxService.todayReminders;
  unreadReminderItems = computed(() =>
    this.reminderInboxItems().filter((item) => !item.readAt && Number(item.id) > 0),
  );
  hasUnreadReminderItems = computed(() => this.unreadReminderItems().length > 0);
  reminderInboxLoading = this.reminderInboxService.isLoading;
  reminderUnreadCountLabel = computed(() => {
    const count = this.reminderUnreadCount();
    if (count > 99) {
      return '99+';
    }
    return String(Math.max(0, count));
  });

  private _capturingKeydown = (event: KeyboardEvent) => {
    if (!this.isBrowser) return;

    if (event.key === 'Tab') {
      const active = document.activeElement as HTMLElement | null;
      const items = this.sidebarItems?.toArray() ?? [];
      const isSidebarFocused = items.some((el) => el.nativeElement.contains(active as Node));

      if (isSidebarFocused) {
        event.preventDefault();
        event.stopPropagation();

        if (event.shiftKey) {
          // Shift+Tab from Sidebar -> Focus Table
          const table = document.querySelector('.data-table-focus-trap') as HTMLElement;
          table?.focus();
        } else {
          // Tab from Sidebar -> Focus Search
          const search = document.querySelector('app-search-toolbar input') as HTMLElement;
          search?.focus();
        }
        return;
      }
    }

    // Global navigation shortcuts (Shift + letter)
    if (event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const active = document.activeElement as HTMLElement | null;
      const tag = active?.tagName ?? '';
      const isEditable =
        tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable);
      if (isEditable) return;

      const key = event.key.toUpperCase();

      // Shift+M for Menu
      if (key === 'M') {
        event.preventDefault();
        event.stopPropagation();

        if (!this.sidebarOpen()) {
          this.sidebarOpen.set(true);
        }

        // Focus first sidebar item on next tick to ensure visibility
        setTimeout(() => {
          const first = this.sidebarItems?.first?.nativeElement;
          if (first) {
            first.focus();
          }
        }, 0);
        return;
      }

      if (key === 'L') {
        event.preventDefault();
        event.stopPropagation();
        if (!this.sidebarOpen()) {
          this.sidebarOpen.set(true);
        }
        this.lettersExpanded.set(true);
        setTimeout(() => {
          this.lettersToggle?.nativeElement?.focus();
        }, 0);
        return;
      }

      if (key === 'R') {
        if (!this.canAccessReports()) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        if (!this.sidebarOpen()) {
          this.sidebarOpen.set(true);
        }
        this.reportsExpanded.set(true);
        this.router.navigate(['/reports']);
        return;
      }
      // Shift+T -> Focus table view if present
      if (key === 'T') {
        event.preventDefault();
        event.stopPropagation();
        setTimeout(() => {
          // Prefer a focus trap element if present
          const tableTrap = document.querySelector('.data-table-focus-trap') as HTMLElement | null;
          if (tableTrap) {
            tableTrap.focus();
            return;
          }

          // Fallback: focus first focusable element inside a table container
          const table = document.querySelector('.data-table') as HTMLElement | null;
          if (table) {
            const focusable = table.querySelector<HTMLElement>(
              'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
            );
            (focusable ?? table).focus();
          }
        }, 0);
        return;
      }

      const routeMap: Record<string, string> = {
        D: '/dashboard',
        C: '/customers',
        A: '/applications',
        P: '/products',
        I: '/invoices',
        U: '/reminders',
        R: '/reports',
      };
      const target = routeMap[key];
      if (target) {
        if (target === '/reports' && !this.canAccessReports()) {
          return;
        }
        if (target === '/products' && !this.canAccessProducts()) {
          return;
        }
        event.preventDefault();
        event.stopPropagation();
        this.router.navigate([target]);
        return;
      }

      // Shift+N -> Create new entity in list views (customers, applications, invoices, products)
      if (key === 'N') {
        try {
          const path = window.location.pathname || '';
          const mapping = ['/customers', '/applications', '/invoices'];
          if (this.canAccessProducts()) {
            mapping.push('/products');
          }
          for (const base of mapping) {
            if (path.startsWith(base)) {
              event.preventDefault();
              event.stopPropagation();
              const searchInput = document.querySelector(
                'app-search-toolbar input',
              ) as HTMLInputElement | null;
              const searchQuery = searchInput?.value?.trim();
              const from = base.replace(/^\//, '');
              // Use router to navigate to the new entity route
              this.router.navigate([base.slice(1), 'new'], {
                state: { from, searchQuery },
              });
              return;
            }
          }
        } catch {}
      }
    }

    // Arrow navigation when sidebar item is focused
    const active = document.activeElement as HTMLElement | null;
    if (!active) return;

    const items = this.sidebarItems?.toArray() ?? [];
    const currentIndex = items.findIndex((el) => el.nativeElement === active);

    if (currentIndex !== -1) {
      if (event.key === 'ArrowDown' || event.key === 'Down') {
        event.preventDefault();
        const next = (currentIndex + 1) % items.length;
        items[next].nativeElement.focus();
      } else if (event.key === 'ArrowUp' || event.key === 'Up') {
        event.preventDefault();
        const prev = (currentIndex - 1 + items.length) % items.length;
        items[prev].nativeElement.focus();
      }
    }
  };

  ngAfterViewInit(): void {
    if (this.isBrowser) {
      window.addEventListener('keydown', this._capturingKeydown, true);
      this.reminderInboxService.start();
    }
  }

  ngOnDestroy(): void {
    if (this.isBrowser) {
      window.removeEventListener('keydown', this._capturingKeydown, true);
      this.reminderInboxService.stop();
    }
  }

  toggleSidebar() {
    this.sidebarOpen.update((v) => !v);
  }

  onSidebarNavigationClick(event: Event): void {
    if (!this.isBrowser || !this.sidebarOpen() || !this.isMobileViewport()) {
      return;
    }

    const target = event.target as HTMLElement | null;
    const link = target?.closest('a[routerLink]');
    if (!link) {
      return;
    }

    this.sidebarOpen.set(false);
  }

  private isMobileViewport(): boolean {
    if (!this.isBrowser) {
      return false;
    }

    return window.matchMedia('(max-width: 767px)').matches;
  }

  toggleLetters() {
    this.lettersExpanded.update((v) => !v);
  }

  toggleUtilities() {
    this.utilitiesExpanded.update((v) => !v);
  }

  toggleReports() {
    this.reportsExpanded.update((v) => !v);
  }

  toggleAdmin() {
    this.adminExpanded.update((v) => !v);
  }

  openReminderInbox() {
    const today = this.toIsoDate(new Date());
    this.router.navigate(['/reminders'], {
      queryParams: {
        statuses: 'pending,sent,failed',
        createdFrom: today,
        createdTo: today,
      },
    });
  }

  openReminder(reminder: ReminderInboxItem) {
    this.reminderDialogService.enqueueFromInboxReminder(reminder);
    if (reminder.id > 0 && !reminder.readAt) {
      this.reminderInboxService.markSingleRead(reminder.id);
    }
  }

  markAllMenuRemindersRead() {
    const ids = this.unreadReminderItems()
      .map((item) => Number(item.id))
      .filter((id) => Number.isFinite(id) && id > 0);

    if (!ids.length) {
      return;
    }

    this.reminderInboxService.markRead(ids);
  }

  logout() {
    this.reminderInboxService.stop();
    this.authService.logout();
  }

  private toIsoDate(date: Date): string {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
      return '';
    }

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
