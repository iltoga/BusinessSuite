import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Subject } from 'rxjs';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

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
  let httpMock: HttpTestingController;
  let stream$: Subject<RemindersStreamEvent>;
  let push$: Subject<any>;
  let mockDesktopBridge: { publishUnreadCount: ReturnType<typeof vi.fn> };
  let mockRemindersStreamService: {
    connect: ReturnType<typeof vi.fn>;
    classifyInboxSignal: ReturnType<typeof vi.fn>;
  };

  const expectInboxRequest = () =>
    httpMock.expectOne((req) => req.url === '/api/calendar-reminders/inbox/' && req.params.get('limit') === '100');

  beforeEach(() => {
    vi.useFakeTimers();
    stream$ = new Subject<RemindersStreamEvent>();
    push$ = new Subject();
    mockDesktopBridge = {
      publishUnreadCount: vi.fn(),
    };
    mockRemindersStreamService = {
      connect: vi.fn(() => stream$.asObservable()),
      classifyInboxSignal: vi.fn((event: RemindersStreamEvent, options?: { refreshOnSnapshot?: boolean }) => {
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
      }),
    };

    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        ReminderInboxService,
        { provide: PLATFORM_ID, useValue: 'browser' },
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
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    try {
      service.stop();
      httpMock.verify();
    } finally {
      TestBed.resetTestingModule();
      vi.useRealTimers();
    }
  });

  it('refreshes immediately on SSE changes and updates unread count', () => {
    service.start();

    const initialReq = expectInboxRequest();
    initialReq.flush({
      unreadCount: 2,
      today: [{ id: 11, content: 'Morning', reminderDate: '2026-03-07', reminderTime: '09:00' }],
    });

    stream$.next({
      event: 'calendar_reminders_changed',
      cursor: 2,
      lastReminderId: 11,
      lastUpdatedAt: '2026-03-07T09:00:00Z',
      reason: 'signal',
    });

    const refreshReq = expectInboxRequest();
    refreshReq.flush({
      unreadCount: 1,
      today: [{ id: 11, content: 'Morning', reminderDate: '2026-03-07', reminderTime: '09:00' }],
    });

    expect(service.unreadCount()).toBe(1);
    expect(service.todayReminders()).toHaveLength(1);
    expect(mockDesktopBridge.publishUnreadCount).toHaveBeenLastCalledWith(1);
  });

  it('refreshes immediately on reminder push notifications', () => {
    service.start();

    expectInboxRequest().flush({ unreadCount: 0, today: [] });

    push$.next({
      data: {
        type: 'calendar_reminder',
        reminderId: '42',
      },
    });

    const refreshReq = expectInboxRequest();
    refreshReq.flush({
      unreadCount: 3,
      today: [{ id: 42, content: 'Call customer', reminderDate: '2026-03-07', reminderTime: '10:30' }],
    });

    expect(service.unreadCount()).toBe(3);
    expect(mockDesktopBridge.publishUnreadCount).toHaveBeenLastCalledWith(3);
  });

  it('uses a five-minute fallback poll instead of refreshing every minute', () => {
    service.start();

    expectInboxRequest().flush({ unreadCount: 1, today: [] });

    vi.advanceTimersByTime(60_000);
    httpMock.expectNone('/api/calendar-reminders/inbox/');

    vi.advanceTimersByTime(4 * 60_000);
    expectInboxRequest().flush({ unreadCount: 1, today: [] });
  });

  it('coalesces simultaneous push and SSE invalidations into one follow-up refresh', async () => {
    service.start();

    const initialReq = expectInboxRequest();

    push$.next({ data: { type: 'calendar_reminder', reminderId: '7' } });
    stream$.next({
      event: 'calendar_reminders_changed',
      cursor: 7,
      lastReminderId: 7,
      lastUpdatedAt: '2026-03-07T09:15:00Z',
      reason: 'signal',
    });

    initialReq.flush({ unreadCount: 2, today: [] });
    await Promise.resolve();

    const followUps = httpMock.match(
      (req) => req.url === '/api/calendar-reminders/inbox/' && req.params.get('limit') === '100',
    );
    expect(followUps).toHaveLength(1);
    followUps[0].flush({ unreadCount: 4, today: [] });

    expect(service.unreadCount()).toBe(4);
  });

  it('keeps fallback polling active for recovery after the live stream disconnects', () => {
    const recoveryStream$ = new Subject<RemindersStreamEvent>();
    mockRemindersStreamService.connect
      .mockImplementationOnce(() => stream$.asObservable())
      .mockImplementationOnce(() => recoveryStream$.asObservable());

    service.start();
    expectInboxRequest().flush({ unreadCount: 1, today: [] });

    stream$.error(new Error('stream dropped'));

    vi.advanceTimersByTime(2_000);
    expect(mockRemindersStreamService.connect).toHaveBeenCalledTimes(2);

    vi.advanceTimersByTime(60_000);
    httpMock.expectNone('/api/calendar-reminders/inbox/');

    vi.advanceTimersByTime(4 * 60_000);
    expectInboxRequest().flush({ unreadCount: 2, today: [] });

    expect(service.unreadCount()).toBe(2);
  });
});
