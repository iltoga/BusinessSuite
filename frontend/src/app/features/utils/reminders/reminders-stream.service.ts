import { Injectable, inject } from '@angular/core';
import { NEVER, Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';

const STREAM_ROTATION_MS = 55_000;

export interface RemindersStreamEvent {
  event: 'calendar_reminders_snapshot' | 'calendar_reminders_changed' | 'calendar_reminders_error';
  cursor: number;
  lastReminderId: number | null;
  lastUpdatedAt: string | null;
  reason: 'initial' | 'signal' | 'db_state_change' | string;
  operation?: 'created' | 'updated' | 'deleted' | string;
  changedReminderId?: number | null;
  error?: string;
}

export type ReminderInboxStreamSignal = 'refresh' | 'reconnect' | 'ignore';

@Injectable({
  providedIn: 'root',
})
export class RemindersStreamService {
  private readonly authService = inject(AuthService);
  private readonly sseService = inject(SseService);

  connect(): Observable<RemindersStreamEvent> {
    if (!this.authService.isAuthenticated()) {
      return NEVER;
    }

    return this.sseService.connect<RemindersStreamEvent>('/api/calendar-reminders/stream/', {
      maxConnectionDurationMs: STREAM_ROTATION_MS,
    });
  }

  classifyInboxSignal(
    event: RemindersStreamEvent,
    options: { refreshOnSnapshot?: boolean } = {},
  ): ReminderInboxStreamSignal {
    if (event.event === 'calendar_reminders_error') {
      return 'reconnect';
    }

    if (event.event === 'calendar_reminders_changed') {
      return 'refresh';
    }

    if (event.event === 'calendar_reminders_snapshot' && options.refreshOnSnapshot) {
      return 'refresh';
    }

    return 'ignore';
  }
}
