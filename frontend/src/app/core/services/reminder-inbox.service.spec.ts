import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { CalendarRemindersService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { PushNotificationsService } from '@/core/services/push-notifications.service';
import { ReminderInboxService } from '@/core/services/reminder-inbox.service';
import {
  type RemindersStreamEvent,
  RemindersStreamService,
} from '@/features/utils/reminders/reminders-stream.service';

describe('ReminderInboxService', () => {
  let service: ReminderInboxService;
  let stream$: Subject<RemindersStreamEvent>;
  let push$: Subject<any>;
  let pendingInboxRequests: Subject<any>[];
  let mockCalendarRemindersApi: {
    calendarRemindersInboxRetrieve: ReturnType<typeof vi.fn>;
  };
  let mockDesktopBridge: { publishUnreadCount: ReturnType<typeof vi.fn> };
  let mockRemindersStreamService: {
    connect: ReturnType<typeof vi.fn>;
    classifyInboxSignal: ReturnType<typeof vi.fn>;
  };

  const takePendingInboxRequest = () => {
    const request = pendingInboxRequests.shift();
    expect(request).toBeDefined();
    return request!;
  };

  beforeEach(() => {
    vi.useFakeTimers();
    stream$ = new Subject<RemindersStreamEvent>();
    push$ = new Subject();
    pendingInboxRequests = [];
    mockCalendarRemindersApi = {
      calendarRemindersInboxRetrieve: vi.fn(() => {
        const request$ = new Subject<any>();
        pendingInboxRequests.push(request$);
        return request$.asObservable();
      }),
    };
    mockDesktopBridge = {
      publishUnreadCount: vi.fn(),
    };
    mockRemindersStreamService = {
      connect: vi.fn(() => stream$.asObservable()),
      classifyInboxSignal: vi.fn(
        (event: RemindersStreamEvent, options?: { refreshOnSnapshot?: boolean }) => {
          if (event.event === 'calendar_reminders_error') {
            return 'reconnect';
          }
          if (event.event === 'calendar_reminders_changed') {
            return 'refresh';
          }
          if (event.event === 'calendar_reminders_snapshot' && options?.refreshOnSnapshot) {
            return 'refresh';
          }
          return 'ignore';
        },
      ),
    };

    TestBed.configureTestingModule({
      providers: [
        ReminderInboxService,
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: CalendarRemindersService, useValue: mockCalendarRemindersApi },
        {
          provide: AuthService,
          useValue: {
            isAuthenticated: vi.fn(() => true),
            getToken: vi.fn(() => 'jwt-token'),
          },
        },
        { provide: DesktopBridgeService, useValue: mockDesktopBridge },
        { provide: PushNotificationsService, useValue: { incoming$: push$.asObservable() } },
        { provide: RemindersStreamService, useValue: mockRemindersStreamService },
      ],
    });

    service = TestBed.inject(ReminderInboxService);
  });

  afterEach(() => {
    try {
      service.stop();
    } finally {
      TestBed.resetTestingModule();
      vi.useRealTimers();
    }
  });

  it('refreshes immediately on SSE changes and updates unread count', () => {
    service.start();

    const initialRequest = takePendingInboxRequest();
    initialRequest.next({
      unreadCount: 2,
      today: [{ id: 11, content: 'Morning', reminderDate: '2026-03-07', reminderTime: '09:00' }],
    });
    initialRequest.complete();

    stream$.next({
      event: 'calendar_reminders_changed',
      cursor: 2,
      lastReminderId: 11,
      lastUpdatedAt: '2026-03-07T09:00:00Z',
      reason: 'signal',
    });

    const refreshRequest = takePendingInboxRequest();
    refreshRequest.next({
      unreadCount: 1,
      today: [{ id: 11, content: 'Morning', reminderDate: '2026-03-07', reminderTime: '09:00' }],
    });
    refreshRequest.complete();

    expect(service.unreadCount()).toBe(1);
    expect(service.todayReminders()).toHaveLength(1);
    expect(mockDesktopBridge.publishUnreadCount).toHaveBeenLastCalledWith(1);
  });

  it('refreshes immediately on reminder push notifications', () => {
    service.start();

    const initialRequest = takePendingInboxRequest();
    initialRequest.next({ unreadCount: 0, today: [] });
    initialRequest.complete();

    push$.next({
      data: {
        type: 'calendar_reminder',
        reminderId: '42',
      },
    });

    const refreshRequest = takePendingInboxRequest();
    refreshRequest.next({
      unreadCount: 3,
      today: [
        { id: 42, content: 'Call customer', reminderDate: '2026-03-07', reminderTime: '10:30' },
      ],
    });
    refreshRequest.complete();

    expect(service.unreadCount()).toBe(3);
    expect(mockDesktopBridge.publishUnreadCount).toHaveBeenLastCalledWith(3);
  });

  it('uses a five-minute fallback poll instead of refreshing every minute', () => {
    service.start();

    const initialRequest = takePendingInboxRequest();
    initialRequest.next({ unreadCount: 1, today: [] });
    initialRequest.complete();

    vi.advanceTimersByTime(60_000);
    expect(mockCalendarRemindersApi.calendarRemindersInboxRetrieve).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(4 * 60_000);
    const pollRequest = takePendingInboxRequest();
    pollRequest.next({ unreadCount: 1, today: [] });
    pollRequest.complete();
  });

  it('coalesces simultaneous push and SSE invalidations into one follow-up refresh', async () => {
    service.start();

    const initialRequest = takePendingInboxRequest();

    push$.next({ data: { type: 'calendar_reminder', reminderId: '7' } });
    stream$.next({
      event: 'calendar_reminders_changed',
      cursor: 7,
      lastReminderId: 7,
      lastUpdatedAt: '2026-03-07T09:15:00Z',
      reason: 'signal',
    });

    initialRequest.next({ unreadCount: 2, today: [] });
    initialRequest.complete();
    await Promise.resolve();

    expect(pendingInboxRequests).toHaveLength(1);
    const followUpRequest = takePendingInboxRequest();
    followUpRequest.next({ unreadCount: 4, today: [] });
    followUpRequest.complete();

    expect(service.unreadCount()).toBe(4);
  });

  it('keeps fallback polling active for recovery after the live stream disconnects', () => {
    const recoveryStream$ = new Subject<RemindersStreamEvent>();
    mockRemindersStreamService.connect
      .mockImplementationOnce(() => stream$.asObservable())
      .mockImplementationOnce(() => recoveryStream$.asObservable());

    service.start();
    const initialRequest = takePendingInboxRequest();
    initialRequest.next({ unreadCount: 1, today: [] });
    initialRequest.complete();

    stream$.error(new Error('stream dropped'));

    vi.advanceTimersByTime(2_000);
    expect(mockRemindersStreamService.connect).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(60_000);
    expect(mockCalendarRemindersApi.calendarRemindersInboxRetrieve).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(4 * 60_000);
    const recoveryPollRequest = takePendingInboxRequest();
    recoveryPollRequest.next({ unreadCount: 2, today: [] });
    recoveryPollRequest.complete();

    expect(service.unreadCount()).toBe(2);
  });
});
