import { CalendarService } from '@/core/api/api/calendar.service';
import { HolidaysService as HolidayService } from '@/core/api/api/holidays.service';
import { GoogleCalendarEvent } from '@/core/api/model/google-calendar-event';
import { Holiday } from '@/core/api/model/holiday';
import { AppConfig } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { DashboardWidgetComponent } from '@/shared/components/dashboard-widget/dashboard-widget.component';
import { ZardDialogService } from '@/shared/components/dialog';
import type { ZardDialogRef } from '@/shared/components/dialog/dialog-ref';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardSkeletonComponent } from '@/shared/components/skeleton/skeleton.component';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  ElementRef,
  HostListener,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';
import { finalize } from 'rxjs';

type CalendarEventWithColor = GoogleCalendarEvent & {
  colorId?: string;
  start?: { dateTime?: string; date?: string } | null;
  end?: { dateTime?: string; date?: string } | null;
};

type CalendarEventViewModel = CalendarEventWithColor & {
  startDate: Date;
  endDate: Date | null;
  isDone: boolean;
};

type MonthGridDay = {
  key: string;
  index: number;
  date: Date;
  inMonth: boolean;
  hasEvents: boolean;
  isHoliday: boolean;
  holidayName: string | null;
  isWeekend: boolean;
  weekendName: string | null;
  tooltip: string | null;
};

@Component({
  selector: 'app-calendar-integration',
  standalone: true,
  imports: [
    CommonModule,
    DashboardWidgetComponent,
    ZardButtonComponent,
    ZardIconComponent,
    ZardSkeletonComponent,
    AppDatePipe,
  ],
  templateUrl: './calendar-integration.component.html',
  styleUrl: './calendar-integration.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CalendarIntegrationComponent implements OnInit {
  private calendarService = inject(CalendarService);
  private configService = inject(ConfigService);
  private holidayService = inject(HolidayService);
  private platformId = inject(PLATFORM_ID);
  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);

  events = signal<GoogleCalendarEvent[]>([]);
  holidays = signal<Holiday[]>([]);
  loading = signal<boolean>(false);
  openDayEventsDate = signal<Date | null>(null);
  hoverInfoDay = signal<MonthGridDay | null>(null);
  hoverTooltipPosition = signal<{ left: number; top: number } | null>(null);
  selectedTodayEventId = signal<string | null>(null);
  isTodayEventDialogOpen = signal<boolean>(false);
  private eventUpdatingState = signal<Record<string, boolean>>({});
  private todayEventDialogRef = signal<ZardDialogRef | null>(null);
  // Timer used for delayed weekend/holiday tooltip (cancellable)
  private openDayTimer: ReturnType<typeof setTimeout> | null = null;

  readonly todayEventDetailsTemplate = viewChild.required<TemplateRef<unknown>>(
    'todayEventDetailsTemplate',
  );
  readonly monthWidgetContainerRef = viewChild<ElementRef<HTMLElement>>('monthWidgetContainerRef');

  readonly todoColorId = computed(() => this.getConfigColorId('calendarTodoColorId', '5'));
  readonly doneColorId = computed(() => this.getConfigColorId('calendarDoneColorId', '10'));

  readonly normalizedEvents = computed<CalendarEventViewModel[]>(() =>
    this.events().map((event) => {
      const typed = event as CalendarEventWithColor;
      return {
        ...typed,
        startDate: this.extractStartDate(typed),
        endDate: this.extractEndDate(typed),
        isDone: this.isDoneEvent(typed),
      };
    }),
  );

  readonly todayEvents = computed(() => {
    const today = new Date();
    return this.normalizedEvents().filter((event) => this.isSameDay(event.startDate, today));
  });

  readonly todayTodoEvents = computed(() => this.todayEvents().filter((event) => !event.isDone));

  readonly todayDoneEvents = computed(() => this.todayEvents().filter((event) => event.isDone));

  readonly selectedTodayEvent = computed(() => {
    const selectedId = this.selectedTodayEventId();
    if (!selectedId) return null;
    return this.todayEvents().find((event) => event.id === selectedId) ?? null;
  });

  readonly restOfWeekEvents = computed(() => {
    const today = new Date();
    const tomorrowStart = new Date(today);
    tomorrowStart.setDate(today.getDate() + 1);
    tomorrowStart.setHours(0, 0, 0, 0);

    const weekStart = new Date(today);
    weekStart.setDate(today.getDate() - today.getDay());
    weekStart.setHours(0, 0, 0, 0);

    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekStart.getDate() + 7);

    if (tomorrowStart >= weekEnd) {
      return [];
    }

    return this.normalizedEvents()
      .filter((event) => event.startDate >= tomorrowStart && event.startDate < weekEnd)
      .sort((left, right) => left.startDate.getTime() - right.startDate.getTime());
  });

  readonly overdueApplications = computed(() => {
    const todayStart = this.startOfDay(new Date());
    const oldestOverdueStart = new Date(todayStart);
    oldestOverdueStart.setDate(oldestOverdueStart.getDate() - 14);

    return this.normalizedEvents()
      .filter(
        (event) =>
          this.isApplicationEvent(event) &&
          !event.isDone &&
          event.startDate.getTime() < todayStart.getTime() &&
          event.startDate.getTime() >= oldestOverdueStart.getTime(),
      )
      .sort((left, right) => right.startDate.getTime() - left.startDate.getTime());
  });

  displayedMonth = signal<Date>(this.startOfMonth(new Date()));

  readonly activeMonthLabel = computed(() =>
    new Intl.DateTimeFormat('en-US', { month: 'long', year: 'numeric' }).format(
      this.displayedMonth(),
    ),
  );

  readonly monthGrid = computed<MonthGridDay[]>(() => {
    const month = this.displayedMonth();
    return this.buildMonthGrid(
      month,
      this.filterEventsByMonth(this.normalizedEvents(), month),
      this.filterHolidaysByMonth(this.holidays(), month),
    );
  });

  readonly selectedDayEvents = computed(() => {
    const day = this.openDayEventsDate();
    if (!day) return [];
    return this.normalizedEvents().filter((event) => this.isSameDay(event.startDate, day));
  });

  readonly selectedDayNationalHolidayNames = computed(() => {
    const day = this.openDayEventsDate();
    if (!day) return [];

    return this.holidays()
      .filter((holiday) => {
        const holidayDate = this.parseHolidayDate(holiday.date);
        return holidayDate
          ? this.isSameDay(holidayDate, day) && !this.isWeekendHoliday(holiday)
          : false;
      })
      .map((holiday) => holiday.name);
  });

  readonly selectedDayWeekendLabel = computed(() => {
    const day = this.openDayEventsDate();
    if (!day) return null;

    if (this.isWeekendDate(day)) {
      return this.weekendLabelForDate(day);
    }

    const weekendHoliday = this.holidays().find((holiday) => {
      const holidayDate = this.parseHolidayDate(holiday.date);
      return holidayDate
        ? this.isSameDay(holidayDate, day) && this.isWeekendHoliday(holiday)
        : false;
    });

    return weekendHoliday?.name ?? null;
  });

  readonly hoverInfoLabel = computed(() => {
    const day = this.hoverInfoDay();
    if (!day) return null;

    const labels: string[] = [];
    if (day.isWeekend && day.weekendName) {
      labels.push(day.weekendName);
    }
    if (day.isHoliday && day.holidayName) {
      labels.push(day.holidayName);
    }

    return labels.join(' • ') || day.tooltip || null;
  });

  constructor() {
    effect(() => {
      const open = this.isTodayEventDialogOpen();
      const current = this.todayEventDialogRef();
      const selected = this.selectedTodayEvent();

      if (open && !current) {
        const ref = this.dialogService.create({
          zTitle: selected?.summary || 'Calendar Event',
          zContent: this.todayEventDetailsTemplate(),
          zHideFooter: true,
          zClosable: true,
          zOnCancel: () => {
            this.isTodayEventDialogOpen.set(false);
          },
        });
        this.todayEventDialogRef.set(ref);
      }

      if (!open && current) {
        current.close();
        this.todayEventDialogRef.set(null);
      }
    });

    this.destroyRef.onDestroy(() => {
      const current = this.todayEventDialogRef();
      if (current) {
        current.close();
      }
      this.clearOpenDayTimer();
    });
  }

  ngOnInit() {
    if (isPlatformBrowser(this.platformId)) {
      this.loadEvents();
      this.loadHolidays();
    }
  }

  loadEvents() {
    this.loading.set(true);
    this.calendarService.calendarList().subscribe({
      next: (data) => {
        this.events.set(data);
        this.ensureSelectedTodayEvent();
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  loadHolidays(): void {
    this.holidayService.holidaysList('date').subscribe({
      next: (data) => {
        const indonesiaHolidays = (data ?? []).filter((holiday) =>
          this.isIndonesiaHolidayCountry(holiday.country),
        );
        this.holidays.set(indonesiaHolidays);
      },
      error: () => {
        this.holidays.set([]);
      },
    });
  }

  openDay(date: Date): void {
    if (this.hasEventsForDate(date)) {
      this.openDayEventsDate.set(date);
    } else {
      this.openDayEventsDate.set(null);
    }
  }

  showPreviousMonth(): void {
    this.shiftDisplayedMonth(-1);
  }

  showNextMonth(): void {
    this.shiftDisplayedMonth(1);
  }

  // Event day: open immediately. Weekend/holiday without events: show tooltip after 1s.
  scheduleOpenDay(day: MonthGridDay, event?: MouseEvent): void {
    if (!day.inMonth) {
      this.cancelScheduledOpenDay();
      return;
    }

    this.clearOpenDayTimer();
    this.hoverInfoDay.set(null);
    this.hoverTooltipPosition.set(null);

    if (day.hasEvents) {
      this.openDay(day.date);
      return;
    }

    this.openDayEventsDate.set(null);
    if (day.isWeekend || day.isHoliday) {
      const tooltipPosition = this.resolveTooltipPosition(event);
      this.openDayTimer = setTimeout(() => {
        this.hoverInfoDay.set(day);
        if (tooltipPosition) {
          this.hoverTooltipPosition.set(tooltipPosition);
        }
      }, 100);
    }
  }

  cancelScheduledOpenDay(): void {
    this.clearOpenDayTimer();
    this.openDayEventsDate.set(null);
    this.hoverInfoDay.set(null);
    this.hoverTooltipPosition.set(null);
  }

  onMonthDayMouseLeave(): void {
    this.clearOpenDayTimer();
    this.hoverInfoDay.set(null);
    this.hoverTooltipPosition.set(null);
  }

  private clearOpenDayTimer(): void {
    if (this.openDayTimer !== null) {
      clearTimeout(this.openDayTimer);
      this.openDayTimer = null;
    }
  }

  @HostListener('document:keydown.escape')
  closeDayDialogOnEscape(): void {
    if (this.openDayEventsDate()) {
      this.openDayEventsDate.set(null);
    }
    if (this.hoverInfoDay()) {
      this.hoverInfoDay.set(null);
    }
    this.hoverTooltipPosition.set(null);
    this.clearOpenDayTimer();
  }

  selectTodayEvent(eventId: string): void {
    this.selectedTodayEventId.set(eventId);
  }

  openTodayEventDialog(eventId: string): void {
    this.selectTodayEvent(eventId);
    this.isTodayEventDialogOpen.set(true);
  }

  toggleEventDone(event: CalendarEventViewModel, domEvent?: Event): void {
    domEvent?.stopPropagation();
    if (!event.id || event.isDone || this.isEventUpdating(event.id)) {
      return;
    }

    this.setEventUpdating(event.id, true);
    const targetColorId = this.doneColorId();

    this.calendarService
      .calendarPartialUpdate(event.id, { done: true } as unknown as GoogleCalendarEvent)
      .pipe(finalize(() => this.setEventUpdating(event.id, false)))
      .subscribe({
        next: (updatedEvent) => {
          this.events.update((items) =>
            items.map((item) =>
              item.id === event.id
                ? ({
                    ...item,
                    colorId: targetColorId,
                    ...(updatedEvent as CalendarEventWithColor),
                  } as GoogleCalendarEvent)
                : item,
            ),
          );
          this.ensureSelectedTodayEvent();
        },
      });
  }

  confirmOverdueApplicationDone(event: CalendarEventViewModel, domEvent?: Event): void {
    domEvent?.stopPropagation();
    if (!event.id || event.isDone || this.isEventUpdating(event.id)) {
      return;
    }

    this.dialogService.create({
      zTitle: 'Complete overdue application',
      zContent: `Mark "${event.summary}" as completed?`,
      zOkText: 'Complete',
      zCancelText: 'Cancel',
      zOkDestructive: false,
      zOnOk: () => {
        this.toggleEventDone(event);
      },
    });
  }

  isEventUpdating(eventId: string): boolean {
    return this.eventUpdatingState()[eventId] === true;
  }

  eventAlerts(event: CalendarEventViewModel): string[] {
    const reminders = (event as any)?.reminders;
    const overrides = Array.isArray(reminders?.overrides) ? reminders.overrides : [];

    return overrides
      .map((override: any) => {
        const minutes = Number(override?.minutes);
        const method = override?.method ? String(override.method) : 'Alert';

        if (!Number.isFinite(minutes)) {
          return `${method} reminder`;
        }
        if (minutes === 0) {
          return `${method} at event time`;
        }
        if (minutes < 60) {
          return `${method} ${minutes} minute${minutes === 1 ? '' : 's'} before`;
        }
        if (minutes < 1440) {
          const hours = Math.round(minutes / 60);
          return `${method} ${hours} hour${hours === 1 ? '' : 's'} before`;
        }

        const days = Math.round(minutes / 1440);
        return `${method} ${days} day${days === 1 ? '' : 's'} before`;
      })
      .filter((value: string) => value.trim().length > 0);
  }

  private ensureSelectedTodayEvent(): void {
    const today = this.todayEvents();
    if (today.length === 0) {
      this.selectedTodayEventId.set(null);
      this.isTodayEventDialogOpen.set(false);
      return;
    }

    const selected = this.selectedTodayEventId();
    if (selected && today.some((event) => event.id === selected)) {
      return;
    }

    this.selectedTodayEventId.set(today[0].id);
  }

  private setEventUpdating(eventId: string, isUpdating: boolean): void {
    this.eventUpdatingState.update((current) => {
      const next = { ...current };
      if (isUpdating) {
        next[eventId] = true;
      } else {
        delete next[eventId];
      }
      return next;
    });
  }

  private shiftDisplayedMonth(offset: number): void {
    this.displayedMonth.set(this.addMonths(this.displayedMonth(), offset));
    this.cancelScheduledOpenDay();
  }

  private buildMonthGrid(
    month: Date,
    monthEvents: CalendarEventViewModel[],
    monthHolidays: Holiday[],
  ): MonthGridDay[] {
    const first = this.startOfMonth(month);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    const endOfMonth = this.addMonths(first, 1);

    return Array.from({ length: 42 }).map((_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const isHighlightableDay = date >= first && date < endOfMonth;
      const hasEvents =
        isHighlightableDay && monthEvents.some((event) => this.isSameDay(event.startDate, date));
      const holidaysForDay = monthHolidays.filter((item) => {
        const holidayDate = this.parseHolidayDate(item.date);
        return holidayDate ? this.isSameDay(holidayDate, date) : false;
      });
      const nationalHoliday = holidaysForDay.find((item) => !this.isWeekendHoliday(item));
      const weekendHoliday = holidaysForDay.find((item) => this.isWeekendHoliday(item));

      const isWeekend = this.isWeekendDate(date) || Boolean(weekendHoliday);
      const weekendName = this.isWeekendDate(date)
        ? this.weekendLabelForDate(date)
        : (weekendHoliday?.name ?? null);
      const holidayName = nationalHoliday?.name ?? null;
      const tooltipParts = [isWeekend && weekendName ? weekendName : null, holidayName].filter(
        (value): value is string => Boolean(value),
      );

      return {
        key: `${this.monthKey(month)}-${index}`,
        index,
        date,
        inMonth: this.isDateInMonth(date, month),
        hasEvents,
        isHoliday: Boolean(nationalHoliday),
        holidayName,
        isWeekend,
        weekendName,
        tooltip: tooltipParts.join(' • ') || null,
      };
    });
  }

  private filterEventsByMonth(
    events: CalendarEventViewModel[],
    month: Date,
  ): CalendarEventViewModel[] {
    return events.filter((event) => this.isDateInMonth(event.startDate, month));
  }

  private filterHolidaysByMonth(holidays: Holiday[], month: Date): Holiday[] {
    return holidays.filter((holiday) => {
      const holidayDate = this.parseHolidayDate(holiday.date);
      return holidayDate ? this.isDateInMonth(holidayDate, month) : false;
    });
  }

  private monthKey(month: Date): string {
    return `${month.getFullYear()}-${String(month.getMonth() + 1).padStart(2, '0')}`;
  }

  private hasEventsForDate(date: Date): boolean {
    return this.normalizedEvents().some((event) => this.isSameDay(event.startDate, date));
  }

  private resolveTooltipPosition(event?: MouseEvent): { left: number; top: number } | null {
    if (!event) return null;

    const cellElement = event.currentTarget;
    if (!(cellElement instanceof HTMLElement)) return null;

    const containerElement = this.monthWidgetContainerRef()?.nativeElement;
    if (!containerElement) return null;

    const cellRect = cellElement.getBoundingClientRect();
    const containerRect = containerElement.getBoundingClientRect();

    return {
      left: cellRect.left - containerRect.left + cellRect.width / 2,
      top: cellRect.top - containerRect.top - 6,
    };
  }

  private extractStartDate(event: CalendarEventWithColor): Date {
    const start = event.start;
    const source = start?.dateTime || start?.date || event.startTime;
    return source ? new Date(source) : new Date();
  }

  private extractEndDate(event: CalendarEventWithColor): Date | null {
    const end = event.end;
    const source = end?.dateTime || end?.date || event.endTime;
    return source ? new Date(source) : null;
  }

  private isDoneEvent(event: CalendarEventWithColor): boolean {
    return event.colorId === this.doneColorId();
  }

  private isApplicationEvent(event: CalendarEventViewModel): boolean {
    return event.summary.trimStart().startsWith('[Application #');
  }

  private startOfDay(date: Date): Date {
    const normalized = new Date(date);
    normalized.setHours(0, 0, 0, 0);
    return normalized;
  }

  private startOfMonth(date: Date): Date {
    return new Date(date.getFullYear(), date.getMonth(), 1);
  }

  private addMonths(date: Date, offset: number): Date {
    return new Date(date.getFullYear(), date.getMonth() + offset, 1);
  }

  private getConfigColorId<K extends keyof AppConfig>(key: K, fallback: string): string {
    const value = this.configService.settings[key];
    if (typeof value === 'string' && value.trim().length > 0) {
      return value.trim();
    }
    return fallback;
  }

  private isSameDay(a: Date, b: Date): boolean {
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }

  private isDateInMonth(date: Date, month: Date): boolean {
    return date.getFullYear() === month.getFullYear() && date.getMonth() === month.getMonth();
  }

  private isWeekendDate(date: Date): boolean {
    const dayOfWeek = date.getDay();
    return dayOfWeek === 0 || dayOfWeek === 6;
  }

  private weekendLabelForDate(date: Date): string {
    return date.getDay() === 0 ? 'Sunday' : 'Saturday';
  }

  private isWeekendHoliday(holiday: Holiday): boolean {
    if (holiday.isWeekend) return true;
    const normalized = holiday.name.trim().toLowerCase();
    return normalized === 'saturday' || normalized === 'sunday';
  }

  private isIndonesiaHolidayCountry(country: string | null | undefined): boolean {
    const normalized = (country ?? '').trim().toUpperCase();
    return normalized === 'INDONESIA' || normalized === 'ID';
  }

  private parseHolidayDate(value: string | null | undefined): Date | null {
    const raw = (value ?? '').trim();
    if (!raw) return null;

    const isoMatch = raw.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      const year = Number(isoMatch[1]);
      const month = Number(isoMatch[2]);
      const day = Number(isoMatch[3]);
      const localDate = new Date(year, month - 1, day);
      if (
        localDate.getFullYear() === year &&
        localDate.getMonth() === month - 1 &&
        localDate.getDate() === day
      ) {
        return localDate;
      }
      return null;
    }

    const parsed = new Date(raw);
    if (Number.isNaN(parsed.getTime())) {
      return null;
    }
    return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
  }
}
