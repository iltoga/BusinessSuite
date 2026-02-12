import { CalendarService } from '@/core/api/api/calendar.service';
import { DEFAULT_APP_CONFIG } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';
import { CalendarIntegrationComponent } from '@/shared/components/calendar/calendar-integration.component';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

describe('CalendarIntegrationComponent', () => {
  const today = new Date();
  const todayIsoDate = today.toISOString().slice(0, 10);

  const makeEvent = (id: string, summary: string, colorId?: string) => ({
    id,
    summary,
    description: '',
    startTime: `${todayIsoDate}T08:00:00+08:00`,
    endTime: `${todayIsoDate}T09:00:00+08:00`,
    start: { date: todayIsoDate },
    end: { date: todayIsoDate },
    htmlLink: 'https://calendar.google.com',
    ...(colorId ? { colorId } : {}),
  });

  it('splits today events into todo and done buckets', () => {
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
      ],
    });

    const fixture = TestBed.createComponent(CalendarIntegrationComponent);
    fixture.detectChanges();

    const component = fixture.componentInstance;
    expect(component.todayTodoEvents().length).toBe(1);
    expect(component.todayDoneEvents().length).toBe(1);
  });

  it('marks a todo event as done via backend patch', () => {
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
});
