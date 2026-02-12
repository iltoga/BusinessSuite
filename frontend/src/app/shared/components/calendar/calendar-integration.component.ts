import { CalendarService } from '@/core/api/api/calendar.service';
import { GoogleCalendarEvent } from '@/core/api/model/google-calendar-event';
import { AppConfig } from '@/core/config/app.config';
import { ConfigService } from '@/core/services/config.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { DashboardWidgetComponent } from '@/shared/components/dashboard-widget/dashboard-widget.component';
import { ZardDialogService } from '@/shared/components/dialog';
import type { ZardDialogRef } from '@/shared/components/dialog/dialog-ref';
import { ZardIconComponent } from '@/shared/components/icon';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
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

@Component({
  selector: 'app-calendar-integration',
  standalone: true,
  imports: [
    CommonModule,
    DashboardWidgetComponent,
    ZardButtonComponent,
    ZardIconComponent,
    AppDatePipe,
  ],
  template: `
    <div class="space-y-4">
      <h2 class="text-2xl font-bold">Calendar Overview</h2>

      <div class="grid gap-4 lg:grid-cols-3">
        <app-dashboard-widget title="Today" subtitle="Todo and done">
          @if (todayEvents().length === 0) {
            <div class="text-sm text-muted-foreground">No applications deadlines today.</div>
          } @else {
            <div class="space-y-3">
              <section class="space-y-2">
                <div
                  class="flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground"
                >
                  <span>Todo</span>
                  <span>{{ todayTodoEvents().length }}</span>
                </div>
                @if (todayTodoEvents().length === 0) {
                  <div
                    class="rounded border border-dashed border-border/60 p-3 text-xs text-muted-foreground"
                  >
                    No todo events.
                  </div>
                } @else {
                  <ul class="space-y-2 text-sm">
                    @for (event of todayTodoEvents(); track event.id) {
                      <li class="rounded border border-border/50 bg-background/40 px-2 py-2">
                        <div class="flex items-start gap-2">
                          <button
                            type="button"
                            class="mt-0.5 rounded-full text-muted-foreground transition hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                            [disabled]="isEventUpdating(event.id)"
                            [attr.aria-label]="'Mark ' + event.summary + ' done'"
                            (click)="toggleEventDone(event, $event)"
                          >
                            <z-icon zType="circle" class="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            class="min-w-0 flex-1 text-left"
                            (click)="openTodayEventDialog(event.id)"
                          >
                            <div class="font-medium">{{ event.summary }}</div>
                          </button>
                        </div>
                      </li>
                    }
                  </ul>
                }
              </section>

              <div class="h-px w-full bg-border/70"></div>

              <section class="space-y-2">
                <div
                  class="flex items-center justify-between text-xs uppercase tracking-wide text-muted-foreground"
                >
                  <span>Done</span>
                  <span>{{ todayDoneEvents().length }}</span>
                </div>
                @if (todayDoneEvents().length === 0) {
                  <div
                    class="rounded border border-dashed border-border/60 p-3 text-xs text-muted-foreground"
                  >
                    No completed events.
                  </div>
                } @else {
                  <ul class="space-y-2 text-sm">
                    @for (event of todayDoneEvents(); track event.id) {
                      <li class="rounded border border-border/60 bg-muted/40 px-2 py-2">
                        <div class="flex items-start gap-2">
                          <button
                            type="button"
                            class="mt-0.5 rounded-full text-primary transition hover:text-foreground disabled:cursor-not-allowed disabled:opacity-50"
                            [disabled]="isEventUpdating(event.id)"
                            [attr.aria-label]="'Mark ' + event.summary + ' todo'"
                            (click)="toggleEventDone(event, $event)"
                          >
                            <z-icon zType="circle-check" class="h-4 w-4" />
                          </button>
                          <button
                            type="button"
                            class="min-w-0 flex-1 text-left"
                            (click)="openTodayEventDialog(event.id)"
                          >
                            <div class="font-medium text-foreground">{{ event.summary }}</div>
                          </button>
                        </div>
                      </li>
                    }
                  </ul>
                }
              </section>
            </div>
          }
        </app-dashboard-widget>

        <app-dashboard-widget title="Rest of the Week" subtitle="Tomorrow to week end">
          @if (restOfWeekEvents().length === 0) {
            <div class="text-sm text-muted-foreground">Nothing yet for the rest of the week.</div>
          } @else {
            <ul class="space-y-2 text-sm">
              @for (event of restOfWeekEvents(); track event.id) {
                <li class="rounded border border-border/50 px-3 py-2">
                  <div class="font-medium">{{ event.summary }}</div>
                  <div class="text-xs text-muted-foreground">
                    {{ event.startDate | appDate }}
                  </div>
                </li>
              }
            </ul>
          }
        </app-dashboard-widget>

        <app-dashboard-widget title="Month" subtitle="Click day for details">
          <div class="mb-2 grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
            @for (day of ['S', 'M', 'T', 'W', 'T', 'F', 'S']; track day + $index) {
              <div>{{ day }}</div>
            }
          </div>
          <div class="grid grid-cols-7 gap-1">
            @for (day of monthGrid(); track day.key) {
              <button
                class="h-8 rounded border text-xs transition"
                [class.bg-primary/15]="day.hasEvents"
                [class.border-primary/40]="day.hasEvents"
                [class.border-border/50]="!day.hasEvents"
                [class.text-muted-foreground]="!day.inMonth"
                (click)="openDay(day.date)"
              >
                {{ day.date.getDate() }}
              </button>
            }
          </div>
        </app-dashboard-widget>
      </div>
    </div>

    <ng-template #todayEventDetailsTemplate>
      @if (selectedTodayEvent(); as selected) {
        <div class="space-y-3 text-sm">
          <div>
            <p class="text-xs text-muted-foreground">
              {{ selected.startDate | appDate: 'datetime' }}
            </p>
            @if (selected.endDate) {
              <p class="text-xs text-muted-foreground">
                Ends {{ selected.endDate | appDate: 'datetime' }}
              </p>
            }
          </div>

          @if (selected.description) {
            <div>
              <p class="text-xs uppercase tracking-wide text-muted-foreground">Details</p>
              <p class="whitespace-pre-wrap text-sm">{{ selected.description }}</p>
            </div>
          }

          @if (eventAlerts(selected).length > 0) {
            <div>
              <p class="text-xs uppercase tracking-wide text-muted-foreground">Alerts</p>
              <ul class="list-disc space-y-1 pl-5">
                @for (alert of eventAlerts(selected); track alert + $index) {
                  <li>{{ alert }}</li>
                }
              </ul>
            </div>
          }

          @if (selected.htmlLink) {
            <a
              class="inline-block text-xs text-primary underline-offset-4 hover:underline"
              [href]="selected.htmlLink"
              target="_blank"
              rel="noopener noreferrer"
            >
              Open in Google Calendar
            </a>
          }
        </div>
      }
    </ng-template>

    @if (openDayEventsDate()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div class="w-full max-w-xl rounded-lg border border-border bg-card p-4">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-lg font-semibold">{{ openDayEventsDate() | appDate }}</h3>
            <button
              z-button
              zType="ghost"
              zSize="sm"
              aria-label="Close dialog"
              (click)="openDayEventsDate.set(null)"
            >
              <z-icon zType="x" />
            </button>
          </div>
          @if (selectedDayEvents().length === 0) {
            <div class="text-sm text-muted-foreground">No events for this day.</div>
          } @else {
            <ul class="space-y-2 text-sm">
              @for (event of selectedDayEvents(); track event.id) {
                <li class="rounded border border-border/50 px-3 py-2">{{ event.summary }}</li>
              }
            </ul>
          }
        </div>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CalendarIntegrationComponent implements OnInit {
  private calendarService = inject(CalendarService);
  private configService = inject(ConfigService);
  private platformId = inject(PLATFORM_ID);
  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);

  events = signal<GoogleCalendarEvent[]>([]);
  loading = signal<boolean>(false);
  openDayEventsDate = signal<Date | null>(null);
  selectedTodayEventId = signal<string | null>(null);
  isTodayEventDialogOpen = signal<boolean>(false);
  private eventUpdatingState = signal<Record<string, boolean>>({});
  private todayEventDialogRef = signal<ZardDialogRef | null>(null);

  readonly todayEventDetailsTemplate = viewChild.required<TemplateRef<unknown>>(
    'todayEventDetailsTemplate',
  );

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

    return this.normalizedEvents().filter(
      (event) => event.startDate >= tomorrowStart && event.startDate < weekEnd,
    );
  });

  readonly monthGrid = computed(() => {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    const todayStart = new Date();
    todayStart.setHours(0, 0, 0, 0);
    const endOfMonth = new Date(now.getFullYear(), now.getMonth() + 1, 1);

    return Array.from({ length: 42 }).map((_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const isHighlightableDay = date >= todayStart && date < endOfMonth;
      const hasEvents =
        isHighlightableDay &&
        this.normalizedEvents().some((event) => this.isSameDay(event.startDate, date));

      return {
        key: `${date.toISOString()}-${index}`,
        date,
        inMonth: date.getMonth() === now.getMonth(),
        hasEvents,
      };
    });
  });

  readonly selectedDayEvents = computed(() => {
    const day = this.openDayEventsDate();
    if (!day) return [];
    return this.normalizedEvents().filter((event) => this.isSameDay(event.startDate, day));
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
    });
  }

  ngOnInit() {
    if (isPlatformBrowser(this.platformId)) {
      this.loadEvents();
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

  openDay(date: Date): void {
    this.openDayEventsDate.set(date);
  }

  @HostListener('document:keydown.escape')
  closeDayDialogOnEscape(): void {
    if (this.openDayEventsDate()) {
      this.openDayEventsDate.set(null);
    }
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
    if (!event.id || this.isEventUpdating(event.id)) {
      return;
    }

    this.setEventUpdating(event.id, true);
    const targetColorId = event.isDone ? this.todoColorId() : this.doneColorId();

    this.calendarService
      .calendarPartialUpdate(event.id, { done: !event.isDone } as unknown as GoogleCalendarEvent)
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
}
