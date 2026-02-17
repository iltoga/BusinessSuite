import { CalendarService } from '@/core/api/api/calendar.service';
import { DEFAULT_APP_CONFIG } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';
import { CalendarIntegrationComponent } from '@/shared/components/calendar/calendar-integration.component';
import { ZardDialogService } from '@/shared/components/dialog';
import { Router } from '@angular/router';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

describe('CalendarIntegrationComponent', () => {
  const routerMock = { navigate: vi.fn().mockResolvedValue(true) };
  const today = new Date();
  const todayIsoDate = today.toISOString().slice(0, 10);
  const isoAtOffset = (daysOffset: number) => {
    const value = new Date(today);
    value.setDate(value.getDate() + daysOffset);
    return value.toISOString().slice(0, 10);
  };

  const makeEvent = (id: string, summary: string, colorId?: string, isoDate: string = todayIsoDate) => ({
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

  it('splits today events into todo and done buckets', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', 'Todo Event', '5'), makeEvent('2', 'Done Event', '10')])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', 'Todo Event', '10'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.todayTodoEvents().length).toBe(1);
    expect(component.todayDoneEvents().length).toBe(1);
  });

  it('marks a todo event as done via backend patch', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', 'Todo Event', '5')])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', 'Todo Event', '10'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    const todoEvent = component.todayTodoEvents()[0];

    component.toggleEventDone(todoEvent);

    expect(calendarServiceMock.calendarPartialUpdate).toHaveBeenCalledWith(
      '1',
      expect.objectContaining({ done: true }),
    );
    expect(component.todayDoneEvents().length).toBe(1);
    expect(component.todayTodoEvents().length).toBe(0);
  });

  it('does not allow moving a done event back to todo', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', 'Done Event', '10')])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', 'Done Event', '5'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    const doneEvent = component.todayDoneEvents()[0];

    component.toggleEventDone(doneEvent);

    expect(calendarServiceMock.calendarPartialUpdate).not.toHaveBeenCalled();
    expect(component.todayDoneEvents().length).toBe(1);
  });

  it('lists overdue application events from newest due date to oldest within last 14 days', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(
        of([
          makeEvent('too-old', '[Application #100] Too Old Overdue', '5', isoAtOffset(-15)),
          makeEvent('old', '[Application #101] Old Overdue', '5', isoAtOffset(-5)),
          makeEvent('new', '[Application #102] New Overdue', '5', isoAtOffset(-1)),
          makeEvent('done', '[Application #103] Done Overdue', '10', isoAtOffset(-2)),
          makeEvent('other', 'General Calendar Event', '5', isoAtOffset(-3)),
        ]),
      ),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('new', '[Application #102] New Overdue', '10'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.overdueApplications().map((event) => event.id)).toEqual(['new', 'old']);
  });

  it('opens a confirmation dialog before completing an overdue application', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', '[Application #101] Overdue', '5', isoAtOffset(-1))])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', '[Application #101] Overdue', '10'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const overdueEvent = component.overdueApplications()[0];

    component.confirmOverdueApplicationDone(overdueEvent);

    expect(dialogServiceMock.create).toHaveBeenCalled();
    const config = dialogServiceMock.create.mock.calls[0][0];
    config.zOnOk();
    expect(calendarServiceMock.calendarPartialUpdate).toHaveBeenCalledWith(
      '1',
      expect.objectContaining({ done: true }),
    );
  });

  it('shows day details on hover and closes on mouse leave when dialog is not pinned', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', '[Application #101] Todo Event', '5', isoAtOffset(0))])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', '[Application #101] Todo Event', '10', isoAtOffset(0)))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const dayWithEvent = component.monthGrid().find((day) => day.hasEvents);
    expect(dayWithEvent).toBeTruthy();

    component.scheduleOpenDay(dayWithEvent!);
    expect(component.openDayEventsDate()?.toDateString()).toBe(dayWithEvent!.date.toDateString());

    component.onMonthDayMouseLeave();
    expect(component.openDayEventsDate()).toBeNull();
  });

  it('pins day details on click and blocks hover popovers until closed', () => {
    const dialogServiceMock = { create: vi.fn() };
    const dayA = isoAtOffset(0);
    const dayB = isoAtOffset(1);
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(
        of([
          makeEvent('1', '[Application #101] Event A', '5', dayA),
          makeEvent('2', '[Application #102] Event B', '5', dayB),
        ]),
      ),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', '[Application #101] Event A', '10', dayA))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;
    const eventDays = component.monthGrid().filter((day) => day.hasEvents);
    expect(eventDays.length).toBeGreaterThanOrEqual(2);
    const firstDay = eventDays[0];
    const secondDay = eventDays[1];

    component.onMonthDayClick(firstDay);
    expect(component.dayEventsDialogPinned()).toBe(true);
    expect(component.openDayEventsDate()?.toDateString()).toBe(firstDay.date.toDateString());

    component.onMonthDayMouseLeave();
    expect(component.openDayEventsDate()?.toDateString()).toBe(firstDay.date.toDateString());

    component.scheduleOpenDay(secondDay);
    expect(component.openDayEventsDate()?.toDateString()).toBe(firstDay.date.toDateString());

    component.closeDayEventsDialog();
    expect(component.dayEventsDialogPinned()).toBe(false);
    expect(component.openDayEventsDate()).toBeNull();

    component.scheduleOpenDay(secondDay);
    expect(component.openDayEventsDate()?.toDateString()).toBe(secondDay.date.toDateString());
  });

  it('extracts application id from summary and routes to detail page', () => {
    const dialogServiceMock = { create: vi.fn() };
    const calendarServiceMock = {
      calendarList: vi.fn().mockReturnValue(of([makeEvent('1', '[Application #316] Test Event', '5')])),
      calendarPartialUpdate: vi.fn().mockReturnValue(of(makeEvent('1', '[Application #316] Test Event', '10'))),
    };

    const configServiceMock = {
      settings: { ...DEFAULT_APP_CONFIG, calendarTodoColorId: '5', calendarDoneColorId: '10' },
    };

    routerMock.navigate.mockClear();

    TestBed.configureTestingModule({
      imports: [CalendarIntegrationComponent],
      providers: [
        { provide: CalendarService, useValue: calendarServiceMock },
        { provide: ConfigService, useValue: configServiceMock },
        { provide: ZardDialogService, useValue: dialogServiceMock },
        { provide: Router, useValue: routerMock },
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();
    const component = fixture.componentInstance;

    expect(component.applicationIdFromSummary('[Application #316] Test Event')).toBe(316);
    component.openApplicationDetail(316);
    expect(routerMock.navigate).toHaveBeenCalledWith(['/applications', 316], {
      state: { from: 'dashboard' },
    });
  });
});
