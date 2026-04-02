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
  });

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

  it('splits today events into todo and done buckets', () => {
    const { component } = setup([
      makeEvent('1', 'Todo Event', '5'),
      makeEvent('2', 'Done Event', '10'),
    ]);

    expect(component.todayTodoEvents().length).toBe(1);
    expect(component.todayDoneEvents().length).toBe(1);
  });

  it('marks a todo event as done via backend patch', () => {
    const { component, calendarServiceMock } = setup([makeEvent('1', 'Todo Event', '5')]);
    const todoEvent = component.todayTodoEvents()[0];

    component.toggleEventDone(todoEvent);

    expect(calendarServiceMock.calendarPartialUpdate).toHaveBeenCalledWith({
      id: '1',
      googleCalendarEventRequest: expect.objectContaining({ done: true }),
    });
  });

  it('does not allow moving a done event back to todo', () => {
    const { component, calendarServiceMock } = setup([makeEvent('1', 'Done Event', '10')]);
    const doneEvent = component.todayDoneEvents()[0];

    component.toggleEventDone(doneEvent);

    expect(calendarServiceMock.calendarPartialUpdate).not.toHaveBeenCalled();
  });

  it('lists overdue application events from newest due date to oldest within last 14 days', () => {
    const { component } = setup([
      makeEvent('too-old', '[Application #100] Too Old Overdue', '5', isoAtOffset(-15)),
      makeEvent('old', '[Application #101] Old Overdue', '5', isoAtOffset(-5)),
      makeEvent('new', '[Application #102] New Overdue', '5', isoAtOffset(-1)),
      makeEvent('done', '[Application #103] Done Overdue', '10', isoAtOffset(-2)),
      makeEvent('other', 'General Calendar Event', '5', isoAtOffset(-3)),
    ]);

    expect(component.overdueApplications().map((event) => event.id)).toEqual(['new', 'old']);
  });
});
