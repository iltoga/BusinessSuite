import { inject, Injectable } from '@angular/core';
import { filter, map, Observable, shareReplay } from 'rxjs';

import { AsyncJob } from '@/core/api';
import { SseMessage, SseService } from '@/core/services/sse.service';

export interface RealtimeJobUpdate {
  job_id: string;
  status: string; // 'queued' | 'processing' | 'completed' | 'failed'
  progress: number;
  payload?: any;
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
      this._events$ = this.sseService.connectMessages<any>('/api/core/realtime/stream/').pipe(
        shareReplay({ bufferSize: 50, refCount: true })
      );
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
      filter(msg => !!msg.data && msg.data.job_id === jobId),
      map(msg => {
        const update = msg.data as RealtimeJobUpdate;
        const job: any = {
          id: update.job_id,
          status: update.status as AsyncJob.StatusEnum,
          progress: update.progress,
        };
        
        if (update.status === 'failed' && update.payload?.error) {
          job.errorMessage = update.payload.error;
        }
        if (update.status === 'completed' && update.payload?.result) {
          job.result = update.payload.result;
        }
        
        return job as AsyncJob;
      })
    );
  }
}
