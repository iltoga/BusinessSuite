import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { FormBuilder } from '@angular/forms';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { of, Subject } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { BackendReadinessService } from '@/core/services/backend-readiness.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardDialogService } from '@/shared/components/dialog';

import { RemindersStreamService } from './reminders-stream.service';
import { RemindersComponent } from './reminders.component';
import {
  type ReminderItem,
  type ReminderListResponse,
  RemindersService,
} from './reminders.service';

function buildReminder(id: number, content: string): ReminderItem {
  return {
    id,
    user: id,
    userFullName: `User ${id}`,
    userEmail: `user${id}@example.com`,
    createdBy: id,
    createdByFullName: `Creator ${id}`,
    createdByEmail: `creator${id}@example.com`,
    calendarEvent: null,
    reminderDate: '2026-02-20',
    reminderTime: '09:00',
    timezone: 'Asia/Makassar',
    scheduledFor: '2026-02-20T09:00:00+08:00',
    content,
    status: 'pending',
    sentAt: null,
    readAt: null,
    readDeviceLabel: '',
    errorMessage: '',
    deliveryChannel: '',
    deliveryDeviceLabel: '',
    createdAt: '2026-02-20T01:00:00Z',
    updatedAt: '2026-02-20T01:00:00Z',
  };
}

describe('RemindersComponent search requests', () => {
  let component: RemindersComponent;
  let remindersServiceMock: {
    list: ReturnType<typeof vi.fn>;
    listUsers: ReturnType<typeof vi.fn>;
    listTimezones: ReturnType<typeof vi.fn>;
    create: ReturnType<typeof vi.fn>;
    update: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
    bulkCreate: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    remindersServiceMock = {
      list: vi.fn(),
      listUsers: vi.fn(() => of([])),
      listTimezones: vi.fn(() => of([])),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      bulkCreate: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        FormBuilder,
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: ActivatedRoute,
          useValue: { queryParamMap: of(convertToParamMap({})) },
        },
        { provide: RemindersService, useValue: remindersServiceMock },
        { provide: RemindersStreamService, useValue: { connect: vi.fn(() => of()) } },
        {
          provide: BackendReadinessService,
          useValue: { isBackendReady: vi.fn(() => Promise.resolve(false)) },
        },
        { provide: AuthService, useValue: { claims: vi.fn(() => null) } },
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
        { provide: ZardDialogService, useValue: { create: vi.fn() } },
      ],
    });

    component = TestBed.runInInjectionContext(() => new RemindersComponent());
  });

  afterEach(() => {
    component.ngOnDestroy();
  });

  it('keeps the latest search results when an earlier request resolves later', () => {
    const firstResponse$ = new Subject<ReminderListResponse>();
    const secondResponse$ = new Subject<ReminderListResponse>();

    remindersServiceMock.list
      .mockReturnValueOnce(firstResponse$.asObservable())
      .mockReturnValueOnce(secondResponse$.asObservable());

    component.onQueryChange('first term');
    component.onQueryChange('latest term');

    expect(component.query()).toBe('latest term');
    expect(component.isLoading()).toBe(true);

    firstResponse$.next({
      count: 1,
      next: null,
      previous: null,
      results: [buildReminder(1, 'first term result')],
    });
    firstResponse$.complete();

    expect(component.reminders()).toEqual([]);
    expect(component.isLoading()).toBe(true);

    secondResponse$.next({
      count: 1,
      next: null,
      previous: null,
      results: [buildReminder(2, 'latest term result')],
    });
    secondResponse$.complete();

    expect(component.reminders().map((item) => item.id)).toEqual([2]);
    expect(component.isLoading()).toBe(false);
  });
});
