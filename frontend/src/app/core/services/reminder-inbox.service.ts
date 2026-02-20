import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Inject, Injectable, NgZone, PLATFORM_ID, computed, inject, signal } from '@angular/core';
import { Subscription, catchError, finalize, interval, of } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { PushNotificationsService } from '@/core/services/push-notifications.service';

export interface ReminderInboxItem {
  id: number;
  content: string;
  reminderDate: string;
  reminderTime: string;
  timezone: string;
  sentAt: string | null;
  readAt: string | null;
}

@Injectable({
  providedIn: 'root',
})
export class ReminderInboxService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly desktopBridge = inject(DesktopBridgeService);
  private readonly pushNotifications = inject(PushNotificationsService);
  private readonly ngZone = inject(NgZone);

  readonly unreadCount = signal(0);
  readonly todayReminders = signal<ReminderInboxItem[]>([]);
  readonly isLoading = signal(false);
  readonly hasUnread = computed(() => this.unreadCount() > 0);

  private started = false;
  private refreshTimerSubscription: Subscription | null = null;
  private pushSubscription: Subscription | null = null;

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {}

  start(): void {
    if (!isPlatformBrowser(this.platformId) || this.started) {
      return;
    }

    this.started = true;
    this.refresh(false);

    // Run the interval OUTSIDE the Angular zone so zone.js doesn't track the
    // recurring setInterval.  If the interval ran inside the zone, Angular's
    // stability check would never resolve, delaying service-worker registration
    // until the 30-second timeout (see Angular error NG0506).
    this.ngZone.runOutsideAngular(() => {
      this.refreshTimerSubscription = interval(60_000).subscribe(() => {
        // Re-enter the zone for the actual work so signals and HTTP calls
        // trigger change detection correctly.
        this.ngZone.run(() => this.refresh(false));
      });
    });

    this.pushSubscription = this.pushNotifications.incoming$.subscribe((payload) => {
      const type = String(payload?.data?.['type'] || '').toLowerCase();
      if (type === 'calendar_reminder') {
        this.refresh(false);
      }
    });
  }

  stop(): void {
    this.started = false;
    this.refreshTimerSubscription?.unsubscribe();
    this.refreshTimerSubscription = null;
    this.pushSubscription?.unsubscribe();
    this.pushSubscription = null;
  }

  refresh(showError = false): void {
    if (!this.authService.isAuthenticated()) {
      this.setUnreadCount(0);
      this.todayReminders.set([]);
      return;
    }

    this.isLoading.set(true);

    const params = new HttpParams().set('limit', 100);
    this.http
      .get<any>('/api/calendar-reminders/inbox/', {
        params,
        headers: this.buildHeaders(),
      })
      .pipe(
        catchError((error) => {
          if (showError) {
            console.error('[ReminderInboxService] Failed to load reminder inbox', error);
          }
          return of({ unreadCount: 0, today: [] as any[] });
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response) => {
        this.setUnreadCount(Number(response?.unreadCount ?? response?.unread_count ?? 0));
        this.todayReminders.set(
          Array.isArray(response?.today)
            ? response.today.map((item: any) => this.mapReminder(item))
            : [],
        );
      });
  }

  markRead(ids: number[] = []): void {
    this.http
      .post<any>(
        '/api/calendar-reminders/inbox/mark-read/',
        { ids, deviceLabel: this.deviceLabel() },
        {
          headers: this.buildHeaders(),
        },
      )
      .pipe(
        catchError((error) => {
          console.error('[ReminderInboxService] Failed to mark reminders as read', error);
          return of(null);
        }),
      )
      .subscribe((response) => {
        if (!response) return;

        const unreadCount = Number(response?.unreadCount ?? response?.unread_count ?? 0);
        this.setUnreadCount(unreadCount);

        if (!ids.length) {
          this.todayReminders.update((items) =>
            items.map((item) => ({ ...item, readAt: item.readAt || new Date().toISOString() })),
          );
          return;
        }

        const idSet = new Set(ids);
        this.todayReminders.update((items) =>
          items.map((item) =>
            idSet.has(item.id)
              ? { ...item, readAt: item.readAt || new Date().toISOString() }
              : item,
          ),
        );
      });
  }

  markAllRead(): void {
    this.markRead([]);
  }

  markSingleRead(id: number): void {
    if (!Number.isFinite(id) || id <= 0) {
      return;
    }
    this.markRead([id]);
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  private mapReminder(item: any): ReminderInboxItem {
    return {
      id: Number(item?.id ?? 0),
      content: String(item?.content ?? ''),
      reminderDate: String(item?.reminderDate ?? item?.reminder_date ?? ''),
      reminderTime: String(item?.reminderTime ?? item?.reminder_time ?? ''),
      timezone: String(item?.timezone ?? 'Asia/Makassar'),
      sentAt: item?.sentAt ?? item?.sent_at ?? null,
      readAt: item?.readAt ?? item?.read_at ?? null,
    };
  }

  private deviceLabel(): string {
    if (!isPlatformBrowser(this.platformId)) {
      return '';
    }
    const platform = navigator.platform || 'unknown-platform';
    const lang = navigator.language || 'unknown-lang';
    return `${platform} (${lang})`;
  }

  private setUnreadCount(value: number): void {
    const parsed = Number(value);
    const normalized = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;
    this.unreadCount.set(normalized);
    this.desktopBridge.publishUnreadCount(normalized);
  }
}
