import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';

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

@Injectable({
  providedIn: 'root',
})
export class RemindersStreamService {
  private readonly authService = inject(AuthService);
  private readonly sseService = inject(SseService);

  connect(): Observable<RemindersStreamEvent> {
    const params = new URLSearchParams();
    const token = this.authService.getToken();
    if (token) {
      params.set('token', token);
    } else if (this.authService.isMockEnabled()) {
      params.set('token', 'mock-token');
    }

    const query = params.toString();
    const url = `/api/calendar-reminders/stream/${query ? `?${query}` : ''}`;
    return this.sseService.connect<RemindersStreamEvent>(url);
  }
}
