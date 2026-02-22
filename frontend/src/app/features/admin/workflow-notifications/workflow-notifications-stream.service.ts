import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { SseService } from '@/core/services/sse.service';

export interface WorkflowNotificationsStreamEvent {
  event: 'workflow_notifications_snapshot' | 'workflow_notifications_changed' | 'workflow_notifications_error';
  cursor: number;
  windowHours: number;
  lastNotificationId: number | null;
  lastUpdatedAt: string | null;
  reason: 'initial' | 'signal' | 'db_state_change' | string;
  operation?: 'created' | 'updated' | 'deleted' | string;
  changedNotificationId?: number | null;
  error?: string;
}

@Injectable({
  providedIn: 'root',
})
export class WorkflowNotificationsStreamService {
  private readonly sseService = inject(SseService);

  connect(): Observable<WorkflowNotificationsStreamEvent> {
    return this.sseService.connect<WorkflowNotificationsStreamEvent>('/api/workflow-notifications/stream/');
  }
}
