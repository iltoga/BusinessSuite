import { CalendarService } from '@/core/api/api/calendar.service';
import { GoogleCalendarEvent } from '@/core/api/model/google-calendar-event';
import { ZardButtonComponent } from '@/shared/components/button';
import { DashboardWidgetComponent } from '@/shared/components/dashboard-widget/dashboard-widget.component';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';

@Component({
  selector: 'app-calendar-integration',
  standalone: true,
  imports: [CommonModule, DashboardWidgetComponent, ZardButtonComponent],
  template: `
    <div class="space-y-4">
      <h2 class="text-2xl font-bold">Calendar Overview</h2>

      <div class="grid gap-4 lg:grid-cols-3">
        <app-dashboard-widget title="Today" subtitle="Upcoming today">
          @if (todayEvents().length === 0) {
            <div class="text-sm text-muted-foreground">No events today.</div>
          } @else {
            <ul class="space-y-2 text-sm">
              @for (event of todayEvents(); track event.id) {
                <li class="rounded border border-border/50 px-3 py-2">{{ event.summary }}</li>
              }
            </ul>
          }
        </app-dashboard-widget>

        <app-dashboard-widget title="This Week" subtitle="Current week">
          @if (weekEvents().length === 0) {
            <div class="text-sm text-muted-foreground">No events this week.</div>
          } @else {
            <ul class="space-y-2 text-sm">
              @for (event of weekEvents(); track event.id) {
                <li class="rounded border border-border/50 px-3 py-2">
                  <div class="font-medium">{{ event.summary }}</div>
                  <div class="text-xs text-muted-foreground">
                    {{ event.start | date: 'EEE, d MMM' }}
                  </div>
                </li>
              }
            </ul>
          }
        </app-dashboard-widget>

        <app-dashboard-widget title="Month" subtitle="Click day for details">
          <div class="grid grid-cols-7 gap-1 text-center text-xs mb-2 text-muted-foreground">
            @for (day of ['S', 'M', 'T', 'W', 'T', 'F', 'S']; track day + $index) {
              <div>{{ day }}</div>
            }
          </div>
          <div class="grid grid-cols-7 gap-1">
            @for (day of monthGrid(); track day.key) {
              <button
                class="h-8 rounded text-xs border transition"
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

    @if (openDayEventsDate()) {
      <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
        <div class="w-full max-w-xl rounded-lg bg-card p-4 border-4 border-primary/50">
          <div class="mb-3 flex items-center justify-between">
            <h3 class="text-lg font-semibold">{{ openDayEventsDate() | date: 'fullDate' }}</h3>
            <button z-button zType="ghost" zSize="sm" (click)="openDayEventsDate.set(null)">
              Close
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
  private platformId = inject(PLATFORM_ID);

  events = signal<GoogleCalendarEvent[]>([]);
  loading = signal<boolean>(false);
  openDayEventsDate = signal<Date | null>(null);

  readonly normalizedEvents = computed(() =>
    this.events().map((event) => ({
      ...event,
      start: this.extractDate(event),
    })),
  );

  readonly todayEvents = computed(() => {
    const today = new Date();
    return this.normalizedEvents().filter((e) => this.isSameDay(e.start, today));
  });

  readonly weekEvents = computed(() => {
    const today = new Date();
    const start = new Date(today);
    start.setDate(today.getDate() - today.getDay());
    start.setHours(0, 0, 0, 0);
    const end = new Date(start);
    end.setDate(start.getDate() + 7);
    return this.normalizedEvents().filter((e) => e.start >= start && e.start < end);
  });

  readonly monthGrid = computed(() => {
    const now = new Date();
    const first = new Date(now.getFullYear(), now.getMonth(), 1);
    const start = new Date(first);
    start.setDate(first.getDate() - first.getDay());
    return Array.from({ length: 42 }).map((_, index) => {
      const date = new Date(start);
      date.setDate(start.getDate() + index);
      const hasEvents = this.normalizedEvents().some((event) => this.isSameDay(event.start, date));
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
    return this.normalizedEvents().filter((event) => this.isSameDay(event.start, day));
  });

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
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  openDay(date: Date): void {
    this.openDayEventsDate.set(date);
  }

  private extractDate(event: GoogleCalendarEvent): Date {
    const startAny: any = event.start;
    const source = startAny?.dateTime || startAny?.date || event.startTime;
    return source ? new Date(source) : new Date();
  }

  private isSameDay(a: Date, b: Date): boolean {
    return (
      a.getFullYear() === b.getFullYear() &&
      a.getMonth() === b.getMonth() &&
      a.getDate() === b.getDate()
    );
  }
}
