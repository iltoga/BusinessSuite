import { inject, Injectable } from '@angular/core';
import { filter, map, Observable, shareReplay } from 'rxjs';

import { AsyncJob } from '@/core/api';
import { SseMessage, SseService } from '@/core/services/sse.service';

export interface RealtimeJobUpdate {
  job_id: string;
  status: string; // 'queued' | 'processing' | 'completed' | 'failed'
  progress: number;
  id?: string;
  jobId?: string;
  message?: string | null;
  result?: unknown;
  error?: string | null;
  errorMessage?: string | null;
  error_message?: string | null;
  payload?: any;
}

function firstDefined<T>(...values: (T | null | undefined)[]): T | undefined {
  return values.find((value) => value !== undefined && value !== null);
}

export function mapJobUpdateToAsyncJob(update: RealtimeJobUpdate): AsyncJob {
  const nestedPayload =
    update.payload && typeof update.payload === 'object'
      ? (update.payload as Record<string, unknown>)
      : null;
  const job: any = {
    id: String(firstDefined(update.id, update.job_id, update.jobId) ?? ''),
    status: update.status as AsyncJob.StatusEnum,
    progress: Number(update.progress ?? 0),
  };

  const message = firstDefined(
    update.message,
    nestedPayload?.['message'] as string | null | undefined,
  );
  if (message !== undefined) {
    job.message = message;
  }

  const result = firstDefined(update.result, nestedPayload?.['result']);
  if (result !== undefined) {
    job.result = result;
  }

  const errorMessage = firstDefined(
    update.errorMessage,
    update.error_message,
    update.error,
    nestedPayload?.['errorMessage'] as string | null | undefined,
    nestedPayload?.['error_message'] as string | null | undefined,
    nestedPayload?.['error'] as string | null | undefined,
  );
  if (errorMessage !== undefined) {
    job.errorMessage = errorMessage;
    job.error_message = errorMessage;
    job.error = errorMessage;
  }

  return job as AsyncJob;
}

@Injectable({
  providedIn: 'root',
})
export class RealtimeNotificationService {
  private _events$: Observable<SseMessage<any>> | null = null;
  private sseService = inject(SseService);

  private get events$(): Observable<SseMessage<any>> {
    if (!this._events$) {
      // Connect to the single global multiplexed stream
      this._events$ = this.sseService
        .connectMessages<any>('/api/core/realtime/stream/')
        .pipe(shareReplay({ bufferSize: 50, refCount: true }));
    }
    return this._events$;
  }

  /**
   * Subscribe to the raw global event stream.
   */
  watchAll(): Observable<SseMessage<any>> {
    return this.events$;
  }

  /**
   * Watch a specific background job via the multiplexed stream.
   * Maps generic backend payloads back into AsyncJob-compatible objects
   * so existing UI components continue working without major rewrites.
   */
  watchJob(jobId: string): Observable<AsyncJob> {
    return this.events$.pipe(
      filter((msg) => !!msg.data && msg.data.job_id === jobId),
      map((msg) => mapJobUpdateToAsyncJob(msg.data as RealtimeJobUpdate)),
    );
  }
}
