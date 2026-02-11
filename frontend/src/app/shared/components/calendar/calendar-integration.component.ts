import { CalendarService } from '@/core/api/api/calendar.service';
import { GoogleCalendarEvent } from '@/core/api/model/google-calendar-event';
import { CommonModule, isPlatformBrowser } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, OnInit, PLATFORM_ID, signal } from '@angular/core';
import { ZardButtonComponent } from '@/shared/components/button';
import { DashboardWidgetComponent } from '@/shared/components/dashboard-widget/dashboard-widget.component';

@Component({
  selector: 'app-calendar-integration',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, DashboardWidgetComponent],
  templateUrl: './calendar-integration.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CalendarIntegrationComponent implements OnInit {
  private calendarService = inject(CalendarService);
  private platformId = inject(PLATFORM_ID);

  readonly events = signal<GoogleCalendarEvent[]>([]);
  readonly loading = signal(false);
  readonly selectedDay = signal<string | null>(null);

  readonly todayEvents = computed(() => {
    const today = new Date().toISOString().slice(0, 10);
    return this.events().filter((event) => this.eventDate(event) === today);
  });

  readonly weekEvents = computed(() => {
    const now = new Date();
    const start = new Date(now);
    start.setDate(now.getDate() - now.getDay());
    const end = new Date(start);
    end.setDate(start.getDate() + 6);
    return this.events().filter((event) => {
      const date = this.eventDate(event);
      if (!date) return false;
      return date >= start.toISOString().slice(0, 10) && date <= end.toISOString().slice(0, 10);
    });
  });

  readonly monthGrid = computed(() => {
    const now = new Date();
    const year = now.getFullYear();
    const month = now.getMonth();
    const first = new Date(year, month, 1);
    const last = new Date(year, month + 1, 0);
    const days = [] as Array<{ date: string; day: number; hasEvents: boolean }>;
    for (let day = 1; day <= last.getDate(); day++) {
      const d = new Date(year, month, day);
      const dateIso = d.toISOString().slice(0, 10);
      days.push({ date: dateIso, day, hasEvents: this.events().some((e) => this.eventDate(e) === dateIso) });
    }
    return { firstWeekday: first.getDay(), days };
  });

  readonly selectedDayEvents = computed(() => {
    const day = this.selectedDay();
    if (!day) return [];
    return this.events().filter((event) => this.eventDate(event) === day);
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
        this.events.set(data || []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  openDay(date: string): void {
    this.selectedDay.set(date);
  }

  closeDayDialog(): void {
    this.selectedDay.set(null);
  }

  private eventDate(event: GoogleCalendarEvent): string | null {
    const startDate = event.start?.date;
    if (startDate) return startDate;
    const dt = event.start?.dateTime;
    if (!dt) return null;
    return dt.slice(0, 10);
  }
}
