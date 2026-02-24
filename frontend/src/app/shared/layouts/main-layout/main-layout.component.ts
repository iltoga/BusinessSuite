import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { Router, RouterLink, RouterOutlet } from '@angular/router';

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
import { MenuContainerComponent } from '@/shared/components/menu/menu-container.component';
import { ThemeSwitcherComponent } from '@/shared/components/theme-switcher/theme-switcher.component';
import { PwaOverlayService } from '@/shared/services/pwa-overlay.service';

@Component({
  selector: 'app-main-layout',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterLink,
    ZardAvatarComponent,
    ZardButtonComponent,
    ZardIconComponent,
    ZardDropdownImports,
    ThemeSwitcherComponent,
    MenuContainerComponent,
  ],
  templateUrl: './main-layout.component.html',
  styleUrls: ['./main-layout.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MainLayoutComponent implements AfterViewInit, OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  sidebarOpen = signal(true);

  private themeService = inject(ThemeService);
  private authService = inject(AuthService);
  private reminderDialogService = inject(ReminderDialogService);
  private reminderInboxService = inject(ReminderInboxService);
  private router = inject(Router);
  private overlayService = inject(PwaOverlayService);

  isOverlayMode = toSignal(this.overlayService.isOverlayMode$, { initialValue: false });

  logoSrc = computed(() => {
    const normal = '/assets/logo_transparent.png';
    const inverted = '/assets/logo_inverted_transparent.png';
    return this.themeService.isDarkMode() ? inverted : normal;
  });

  canAccessProducts = computed(() => this.authService.isAdminOrManager());
  canAccessReports = computed(() => this.authService.isAdminOrManager());
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
    return count > 99 ? '99+' : String(Math.max(0, count));
  });

  private _capturingKeydown = (event: KeyboardEvent) => {
    if (!this.isBrowser) return;
    if (event.shiftKey && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const active = document.activeElement as HTMLElement | null;
      const tag = active?.tagName ?? '';
      const isEditable =
        tag === 'INPUT' || tag === 'TEXTAREA' || (active && active.isContentEditable);
      if (isEditable) return;

      const key = event.key.toUpperCase();
      const routeMap: Record<string, string> = {
        D: '/dashboard',
        C: '/customers',
        A: '/applications',
        P: '/products',
        I: '/invoices',
        U: '/utils/reminders',
        R: '/reports',
      };
      const target = routeMap[key];
      if (target) {
        if (target === '/reports' && !this.canAccessReports()) return;
        if (target === '/products' && !this.canAccessProducts()) return;
        event.preventDefault();
        event.stopPropagation();
        this.router.navigate([target]);
        return;
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
    if (this.isOverlayMode()) return;
    this.sidebarOpen.update((v) => !v);
  }

  onSidebarNavigationClick(event: Event): void {
    if (!this.isBrowser || !this.sidebarOpen() || !this.isMobileViewport()) return;
    const target = event.target as HTMLElement | null;
    if (target?.closest('a[routerLink]')) {
      this.sidebarOpen.set(false);
    }
  }

  private isMobileViewport(): boolean {
    return this.isBrowser && window.matchMedia('(max-width: 767px)').matches;
  }

  openReminderInbox() {
    const today = this.toIsoDate(new Date());
    this.router.navigate(['/utils/reminders'], {
      queryParams: {
        statuses: 'pending,sent,failed',
        createdFrom: today,
        createdTo: today,
      },
    });
  }

  openReminder(reminder: ReminderInboxItem) {
    this.reminderDialogService.enqueueFromInboxReminder(reminder);
    if (reminder.id > 0 && !reminder.readAt) this.reminderInboxService.markSingleRead(reminder.id);
  }

  markAllMenuRemindersRead() {
    const ids = this.unreadReminderItems()
      .map((item) => Number(item.id))
      .filter((id) => Number.isFinite(id) && id > 0);
    if (ids.length) this.reminderInboxService.markRead(ids);
  }

  logout() {
    this.reminderInboxService.stop();
    this.authService.logout();
  }

  private toIsoDate(date: Date): string {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) return '';
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }
}
