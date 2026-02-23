import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

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
  private readonly sseService = inject(SseService);

  connect(): Observable<RemindersStreamEvent> {
    return this.sseService.connect<RemindersStreamEvent>('/api/calendar-reminders/stream/');
  }
}
