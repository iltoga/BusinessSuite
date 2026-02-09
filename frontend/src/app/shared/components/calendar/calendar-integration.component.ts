import { CalendarService } from '@/core/api/api/calendar.service';
import { GoogleCalendarEvent } from '@/core/api/model/google-calendar-event';
import { CommonModule } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

@Component({
  selector: 'app-calendar-integration',
  standalone: true,
  imports: [CommonModule, FormsModule],
  template: `
    <div class="p-6 space-y-6">
      <h2 class="text-2xl font-bold">Google Calendar (via Django)</h2>

      <!-- Create Event Form -->
      <div class="p-6 border rounded-xl bg-white shadow-sm border-gray-100">
        <h3 class="font-bold text-lg mb-4 text-gray-900">New Calendar Event</h3>
        <div class="grid gap-4">
          <div class="space-y-1">
            <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider"
              >Title</label
            >
            <input
              type="text"
              [(ngModel)]="newEventTitle"
              placeholder="What's happening?"
              class="w-full p-3 border rounded-lg bg-gray-50 text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all font-medium"
            />
          </div>
          <div class="space-y-1">
            <label class="text-xs font-semibold text-gray-500 uppercase tracking-wider"
              >Description</label
            >
            <textarea
              [(ngModel)]="newEventDesc"
              placeholder="Add more details..."
              rows="2"
              class="w-full p-3 border rounded-lg bg-gray-50 text-gray-900 focus:ring-2 focus:ring-blue-500 focus:border-transparent outline-none transition-all font-medium"
            ></textarea>
          </div>
          <button
            (click)="addEvent()"
            [disabled]="loading() || !newEventTitle"
            class="mt-2 px-6 py-3 bg-blue-600 text-white font-bold rounded-lg hover:bg-blue-700 active:scale-95 disabled:opacity-50 disabled:scale-100 transition-all shadow-lg shadow-blue-200"
          >
            {{ loading() ? 'Saving...' : '✨ Create Event' }}
          </button>
        </div>
      </div>

      <!-- Events List -->
      <div class="mt-8">
        <h3 class="font-bold text-lg mb-4 text-foreground">Upcoming Events</h3>
        <div *ngIf="loading()" class="flex items-center space-x-2 text-gray-500">
          <span class="animate-spin text-xl">◌</span>
          <span>Syncing with Google...</span>
        </div>

        <div
          *ngIf="events().length === 0 && !loading()"
          class="p-8 border-2 border-dashed rounded-lg text-center bg-gray-50/50"
        >
          <p class="text-gray-500 mb-2 font-medium">No upcoming events found.</p>
          <p class="text-sm text-gray-400 max-w-sm mx-auto">
            If you expected to see events here, ensure your calendar is shared with the service
            account email or check your settings.
          </p>
        </div>

        <ul class="space-y-3">
          <li
            *ngFor="let event of events()"
            class="flex justify-between items-center p-4 bg-white border rounded-lg shadow-sm hover:shadow-md transition-shadow"
          >
            <div class="flex-1 min-w-0 pr-4">
              <div class="font-bold text-gray-900 truncate">{{ event.summary }}</div>
              <div class="text-sm text-gray-600 flex items-center mt-1">
                <span class="mr-2">📅</span>
                {{
                  (event.start?.dateTime | date: 'medium') ||
                    (event.start?.date | date: 'mediumDate')
                }}
              </div>
              <div *ngIf="event.description" class="text-xs text-gray-400 mt-1 truncate">
                {{ event.description }}
              </div>
            </div>
            <button
              (click)="deleteEvent(event.id)"
              class="px-3 py-1 text-sm font-medium text-red-600 hover:bg-red-50 rounded transition-colors border border-red-100"
            >
              Delete
            </button>
          </li>
        </ul>
      </div>
    </div>
  `,
})
export class CalendarIntegrationComponent implements OnInit {
  private calendarService = inject(CalendarService);

  // Signals for state management
  events = signal<GoogleCalendarEvent[]>([]);
  loading = signal<boolean>(false);

  // Form inputs
  newEventTitle = '';
  newEventDesc = '';

  ngOnInit() {
    this.loadEvents();
  }

  loadEvents() {
    this.loading.set(true);
    this.calendarService.calendarList().subscribe({
      next: (data) => {
        this.events.set(data);
        this.loading.set(false);
      },
      error: (err) => {
        console.error('Failed to load events', err);
        this.loading.set(false);
      },
    });
  }

  addEvent() {
    if (!this.newEventTitle) return;

    this.loading.set(true);

    // Create an event for Tomorrow at 10 AM
    const startTime = new Date();
    startTime.setDate(startTime.getDate() + 1);
    startTime.setHours(10, 0, 0, 0);

    const endTime = new Date(startTime);
    endTime.setHours(11, 0, 0, 0);

    const googleEvent: any = {
      summary: this.newEventTitle,
      description: this.newEventDesc,
      startTime: startTime.toISOString(),
      endTime: endTime.toISOString(),
    };

    this.calendarService.calendarCreate(googleEvent).subscribe({
      next: () => {
        this.newEventTitle = '';
        this.newEventDesc = '';
        this.loadEvents(); // Refresh list
      },
      error: (err) => {
        console.error('Failed to create event', err);
        this.loading.set(false);
      },
    });
  }

  deleteEvent(id: string) {
    if (!confirm('Are you sure you want to delete this event?')) return;

    this.loading.set(true);
    this.calendarService.calendarDestroy(id).subscribe({
      next: () => this.loadEvents(),
      error: (err) => {
        console.error('Failed to delete', err);
        this.loading.set(false);
      },
    });
  }
}
