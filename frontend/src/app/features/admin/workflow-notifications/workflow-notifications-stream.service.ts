import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
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
  private readonly authService = inject(AuthService);
  private readonly sseService = inject(SseService);

  connect(): Observable<WorkflowNotificationsStreamEvent> {
    const params = new URLSearchParams();
    const token = this.authService.getToken();
    if (token) {
      params.set('token', token);
    } else if (this.authService.isMockEnabled()) {
      params.set('token', 'mock-token');
    }
    const query = params.toString();
    const url = `/api/workflow-notifications/stream/${query ? `?${query}` : ''}`;
    return this.sseService.connect<WorkflowNotificationsStreamEvent>(url);
  }
}

