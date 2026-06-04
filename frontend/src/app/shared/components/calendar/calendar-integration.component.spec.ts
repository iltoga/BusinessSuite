import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of } from 'rxjs';

import { CalendarService } from '@/core/api/api/calendar.service';
import { HolidaysService } from '@/core/api/api/holidays.service';
import { DEFAULT_APP_CONFIG } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';
import { ZardDialogService } from '@/shared/components/dialog';

import { CalendarIntegrationComponent } from './calendar-integration.component';

describe('CalendarIntegrationComponent', () => {
  const routerMock = { navigate: vi.fn().mockResolvedValue(true) };

  const formatLocalIsoDate = (value: Date) => {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  };

  const today = new Date();
  const todayIsoDate = formatLocalIsoDate(today);
  const isoAtOffset = (daysOffset: number) => {
    const value = new Date(today);
    value.setDate(value.getDate() + daysOffset);
    return formatLocalIsoDate(value);
  };

  const makeEvent = (
    id: string,
    summary: string,
    colorId?: string,
    isoDate: string = todayIsoDate,
    extra: Record<string, unknown> = {},
  ) => ({
    id,
    summary,
    description: '',
    startTime: `${isoDate}T08:00:00+08:00`,
    endTime: `${isoDate}T09:00:00+08:00`,
    start: { date: isoDate },
    end: { date: isoDate },
    htmlLink: 'https://calendar.google.com',
    ...(colorId ? { colorId } : {}),
    ...extra,
  });

  const taskDeadlineExtra = {
    extendedProperties: {
      private: {
        revisbali_event_kind: 'task_deadline',
      },
    },
  };

  const submissionExtra = {
    extendedProperties: {
      private: {
        revisbali_event_kind: 'application_submission',
      },
    },
  };

  const visaWindowExtra = {
    extendedProperties: {
      private: {
        revisbali_event_kind: 'visa_submission_window',
      },
    },
  };

  const setup = (events: any[]) => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of(events)),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', 'Updated Event', '10'))),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: HolidaysService, useValue: { holidaysList: vi.fn().mockReturnValue(of([])) } },
        {
          provide: ConfigService,
          useValue: {
            settings: {
              ...DEFAULT_APP_CONFIG,
              calendarTodoColorId: '5',
              calendarDoneColorId: '10',
            },
          },
        },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const component = TestBed.runInInjectionContext(() => new CalendarIntegrationComponent());
    component.loadEvents();
    return { component, calendarServiceMock, dialogServiceMock };
  };

  afterEach(() => {
    vi.useRealTimers();
  });

  it('splits today events into todo and done buckets', () => {
    const { component } = setup([
      makeEvent('1', '[Application #1] Todo Event', '5', todayIsoDate, taskDeadlineExtra),
      makeEvent('2', '[Application #2] Done Event', '10', todayIsoDate, taskDeadlineExtra),
    ]);

    expect(component.todayTodoEvents().length).toBe(1);
    expect(component.todayDoneEvents().length).toBe(1);
  });

  it('uses the Bali business date for timestamped calendar events', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-06-01T17:30:00.000Z'));

    const { component } = setup([
      {
        ...makeEvent(
          'bali-today',
          '[Application #325] Maria Puig Ramon - biometrics',
          '5',
          '2026-06-02',
          taskDeadlineExtra,
        ),
        start: { dateTime: '2026-06-02T00:30:00+08:00' },
        end: { dateTime: '2026-06-02T01:30:00+08:00' },
      },
    ]);

    expect(component.todayTodoEvents().map((event) => event.id)).toEqual(['bali-today']);
    expect(component.overdueApplications()).toEqual([]);
  });

  it('marks a todo event as done via backend patch', () => {
    const { component, calendarServiceMock } = setup([
      makeEvent('1', '[Application #1] Todo Event', '5', todayIsoDate, taskDeadlineExtra),
    ]);
    const todoEvent = component.todayTodoEvents()[0];

    component.toggleEventDone(todoEvent);

    expect(calendarServiceMock.calendarPartialUpdate).toHaveBeenCalledWith({
      id: '1',
      googleCalendarEventRequest: expect.objectContaining({ done: true }),
    });

    // Backend rejects requests with both `done` and `colorId`; verify colorId is excluded.
    const actualRequest =
      calendarServiceMock.calendarPartialUpdate.mock.calls[0][0].googleCalendarEventRequest;
    expect(actualRequest).not.toHaveProperty('colorId');
  });

  it('does not allow moving a done event back to todo', () => {
    const { component, calendarServiceMock } = setup([
      makeEvent('1', '[Application #1] Done Event', '10', todayIsoDate, taskDeadlineExtra),
    ]);
    const doneEvent = component.todayDoneEvents()[0];

    component.toggleEventDone(doneEvent);

    expect(calendarServiceMock.calendarPartialUpdate).not.toHaveBeenCalled();
  });

  it('lists overdue application events from newest due date to oldest within last 14 days', () => {
    const { component } = setup([
      makeEvent(
        'too-old',
        '[Application #100] Too Old Overdue',
        '5',
        isoAtOffset(-15),
        taskDeadlineExtra,
      ),
      makeEvent('old', '[Application #101] Old Overdue', '5', isoAtOffset(-5), taskDeadlineExtra),
      makeEvent('new', '[Application #102] New Overdue', '5', isoAtOffset(-1), taskDeadlineExtra),
      makeEvent(
        'done',
        '[Application #103] Done Overdue',
        '10',
        isoAtOffset(-2),
        taskDeadlineExtra,
      ),
      makeEvent(
        'submission',
        '[Application #104] Local Event - Application submission',
        '9',
        isoAtOffset(-1),
        submissionExtra,
      ),
      makeEvent(
        'visa-window',
        '[Application #105] Local Event - Visa submission window',
        '6',
        isoAtOffset(-3),
        visaWindowExtra,
      ),
      makeEvent('other', 'General Calendar Event', '5', isoAtOffset(-3)),
    ]);

    expect(component.overdueApplications().map((event) => event.id)).toEqual(['new', 'old']);
  });

  it('keeps submission and visa-window milestones out of today and upcoming task widgets', () => {
    const { component } = setup([
      makeEvent(
        'submission-today',
        '[Application #201] Customer - Application submission',
        '9',
        todayIsoDate,
        submissionExtra,
      ),
      makeEvent(
        'todo-today',
        '[Application #202] Customer - Biometrics',
        '5',
        todayIsoDate,
        taskDeadlineExtra,
      ),
      makeEvent(
        'done-today',
        '[Application #203] Customer - Interview',
        '10',
        todayIsoDate,
        taskDeadlineExtra,
      ),
      makeEvent(
        'visa-future',
        '[Application #204] Customer - Visa submission window',
        '6',
        isoAtOffset(1),
        visaWindowExtra,
      ),
    ]);

    expect(component.todayEvents().map((event) => event.id)).toEqual(['todo-today', 'done-today']);
    expect(component.todayTodoEvents().map((event) => event.id)).toEqual(['todo-today']);
    expect(component.todayDoneEvents().map((event) => event.id)).toEqual(['done-today']);
    expect(component.restOfWeekEvents()).toEqual([]);
  });
});
