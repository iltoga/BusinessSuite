import { inject, Injectable } from '@angular/core';
import { filter, map, Observable, shareReplay, takeWhile } from 'rxjs';

import { type AsyncJob } from '@/core/api';
import { isTerminalAsyncJob, normalizeAsyncJobUpdate } from '@/core/utils/async-job-contract';
import { SseMessage, SseService } from '@/core/services/sse.service';

export interface RealtimeJobUpdate {
  status?: string; // 'queued' | 'processing' | 'completed' | 'failed'
  progress?: number;
  id?: string;
  jobId?: string;
  taskName?: string;
  message?: string | null;
  result?: unknown;
  errorMessage?: string | null;
  createdAt?: string;
  updatedAt?: string;
  createdBy?: number | null;
  payload?: unknown;
}

export function mapJobUpdateToAsyncJob(update: RealtimeJobUpdate): AsyncJob {
  return normalizeAsyncJobUpdate(update);
}

@Injectable({
  providedIn: 'root',
})
export class RealtimeNotificationService {
  private _events$: Observable<SseMessage<unknown>> | null = null;
  private sseService = inject(SseService);

  private get events$(): Observable<SseMessage<unknown>> {
    if (!this._events$) {
      // Connect to the single global multiplexed stream
      this._events$ = this.sseService
        .connectMessages<unknown>('/api/core/realtime/stream/')
        .pipe(shareReplay({ bufferSize: 50, refCount: true }));
    }
    return this._events$;
  }

  /**
   * Subscribe to the raw global event stream.
   */
  watchAll(): Observable<SseMessage<unknown>> {
    return this.events$;
  }

  /**
   * Watch a specific background job via the multiplexed stream.
   * Maps generic backend payloads back into AsyncJob-compatible objects
   * so existing UI components continue working without major rewrites.
   */
  watchJob(jobId: string): Observable<AsyncJob> {
    return this.events$.pipe(
      map((msg) => normalizeAsyncJobUpdate(msg.data)),
      filter((job) => job.jobId === jobId),
      takeWhile((job) => !isTerminalAsyncJob(job), true),
    );
  }
}
