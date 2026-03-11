import { isPlatformBrowser } from '@angular/common';
import { Inject, Injectable, NgZone, PLATFORM_ID, computed, inject, signal } from '@angular/core';
import { Subscription, catchError, finalize, interval, of } from 'rxjs';

import { CalendarRemindersService } from '@/core/api/api/calendar-reminders.service';
import { AuthService } from '@/core/services/auth.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { PushNotificationsService } from '@/core/services/push-notifications.service';
import {
  RemindersStreamService,
  type RemindersStreamEvent,
} from '@/features/utils/reminders/reminders-stream.service';

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
  private readonly fallbackRefreshMs = 5 * 60_000;
  private readonly reconnectBaseDelayMs = 2_000;
  private readonly reconnectMaxDelayMs = 30_000;

  private readonly authService = inject(AuthService);
  private readonly calendarRemindersApi = inject(CalendarRemindersService);
  private readonly desktopBridge = inject(DesktopBridgeService);
  private readonly pushNotifications = inject(PushNotificationsService);
  private readonly remindersStreamService = inject(RemindersStreamService);
  private readonly ngZone = inject(NgZone);

  readonly unreadCount = signal(0);
  readonly todayReminders = signal<ReminderInboxItem[]>([]);
  readonly isLoading = signal(false);
  readonly hasUnread = computed(() => this.unreadCount() > 0);

  private started = false;
  private hasHydratedInbox = false;
  private refreshQueued = false;
  private refreshQueuedShowError = false;
  private awaitingRecoverySnapshot = false;
  private reconnectAttempt = 0;
  private refreshTimerSubscription: Subscription | null = null;
  private pushSubscription: Subscription | null = null;
  private streamSubscription: Subscription | null = null;
  private activeRefreshSubscription: Subscription | null = null;
  private streamReconnectTimeoutId: number | null = null;

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {}

  start(): void {
    if (!isPlatformBrowser(this.platformId) || this.started) {
      return;
    }

    this.started = true;
    this.subscribeToReminderStream();
    this.refresh(false);

    // Run the interval OUTSIDE the Angular zone so zone.js doesn't track the
    // recurring setInterval.  If the interval ran inside the zone, Angular's
    // stability check would never resolve, delaying service-worker registration
    // until the 30-second timeout (see Angular error NG0506).
    this.ngZone.runOutsideAngular(() => {
      this.refreshTimerSubscription = interval(this.fallbackRefreshMs).subscribe(() => {
        // Re-enter the zone for the actual work so signals and HTTP calls
        // trigger change detection correctly.
        this.ngZone.run(() => this.handleFreshnessSignal('fallback'));
      });
    });

    this.pushSubscription = this.pushNotifications.incoming$.subscribe((payload) => {
      if (this.isReminderPush(payload)) {
        this.handleFreshnessSignal('push');
      }
    });
  }

  stop(): void {
    this.started = false;
    this.refreshTimerSubscription?.unsubscribe();
    this.refreshTimerSubscription = null;
    this.pushSubscription?.unsubscribe();
    this.pushSubscription = null;
    this.streamSubscription?.unsubscribe();
    this.streamSubscription = null;
    this.activeRefreshSubscription?.unsubscribe();
    this.activeRefreshSubscription = null;
    this.clearReconnectTimeout();
  }

  refresh(showError = false): void {
    if (!this.authService.isAuthenticated()) {
      this.hasHydratedInbox = false;
      this.refreshQueued = false;
      this.refreshQueuedShowError = false;
      this.setUnreadCount(0);
      this.todayReminders.set([]);
      return;
    }

    if (this.activeRefreshSubscription) {
      this.refreshQueued = true;
      this.refreshQueuedShowError = this.refreshQueuedShowError || showError;
      return;
    }

    this.isLoading.set(true);

    this.activeRefreshSubscription = this.calendarRemindersApi
      .calendarRemindersInboxRetrieve()
      .pipe(
        catchError((error) => {
          if (showError) {
            console.error('[ReminderInboxService] Failed to load reminder inbox', error);
          }
          return of(null);
        }),
        finalize(() => {
          this.isLoading.set(false);
          this.activeRefreshSubscription = null;

          if (this.refreshQueued) {
            const nextShowError = this.refreshQueuedShowError;
            this.refreshQueued = false;
            this.refreshQueuedShowError = false;
            this.refresh(nextShowError);
          }
        }),
      )
      .subscribe((response) => {
        if (!response) {
          return;
        }

        const inbox = response as unknown as Record<string, unknown>;

        this.hasHydratedInbox = true;
        this.setUnreadCount(Number(inbox['unreadCount'] ?? inbox['unread_count'] ?? 0));
        this.todayReminders.set(
          Array.isArray(inbox['today'])
            ? (inbox['today'] as any[]).map((item: any) => this.mapReminder(item))
            : [],
        );
      });
  }

  markRead(ids: number[] = []): void {
    this.calendarRemindersApi
      .calendarRemindersInboxMarkReadCreate({ ids, deviceLabel: this.deviceLabel() })
      .pipe(
        catchError((error) => {
          console.error('[ReminderInboxService] Failed to mark reminders as read', error);
          return of(null);
        }),
      )
      .subscribe((response) => {
        if (!response) return;

        const payload = response as unknown as Record<string, unknown>;

        const unreadCount = Number(payload['unreadCount'] ?? payload['unread_count'] ?? 0);
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

  private subscribeToReminderStream(): void {
    this.clearReconnectTimeout();
    this.streamSubscription?.unsubscribe();
    this.streamSubscription = this.remindersStreamService.connect().subscribe({
      next: (event) => this.handleReminderStreamEvent(event),
      error: () => this.handleReminderStreamDisconnect(),
      complete: () => this.handleReminderStreamDisconnect(),
    });
  }

  private handleReminderStreamEvent(event: RemindersStreamEvent): void {
    this.reconnectAttempt = 0;
    const signal = this.remindersStreamService.classifyInboxSignal(event, {
      refreshOnSnapshot: this.awaitingRecoverySnapshot || !this.hasHydratedInbox,
    });

    if (signal === 'refresh') {
      this.awaitingRecoverySnapshot = false;
      this.handleFreshnessSignal('stream');
      return;
    }

    if (signal === 'reconnect') {
      this.handleReminderStreamDisconnect();
      return;
    }
  }

  private handleReminderStreamDisconnect(): void {
    if (!this.started || !isPlatformBrowser(this.platformId)) {
      return;
    }

    this.awaitingRecoverySnapshot = true;
    this.scheduleReconnect();
  }

  private scheduleReconnect(): void {
    this.clearReconnectTimeout();
    const delay = Math.min(
      this.reconnectMaxDelayMs,
      this.reconnectBaseDelayMs * 2 ** this.reconnectAttempt,
    );
    this.reconnectAttempt += 1;
    this.streamReconnectTimeoutId = window.setTimeout(
      () => this.subscribeToReminderStream(),
      delay,
    );
  }

  private clearReconnectTimeout(): void {
    if (this.streamReconnectTimeoutId === null) {
      return;
    }

    window.clearTimeout(this.streamReconnectTimeoutId);
    this.streamReconnectTimeoutId = null;
  }

  private handleFreshnessSignal(source: 'push' | 'stream' | 'fallback'): void {
    if (!this.started) {
      return;
    }

    this.refresh(false);
  }

  private isReminderPush(payload: { data?: Record<string, string> } | null | undefined): boolean {
    const type = String(payload?.data?.['type'] || '').toLowerCase();
    return type === 'calendar_reminder';
  }
}
