import { inject, Injectable } from '@angular/core';
import { catchError, map, Observable, timeout } from 'rxjs';

import { AsyncJob } from '@/core/api';
import {
  mapJobUpdateToAsyncJob,
  RealtimeNotificationService,
} from '@/core/services/realtime-notification.service';
import { SseService } from '@/core/services/sse.service';
import { ZardDialogService } from '@/shared/components/dialog';
import { JobProgressDialogComponent } from '@/shared/components/job-progress-dialog/job-progress-dialog.component';

@Injectable({
  providedIn: 'root',
})
export class JobService {
  private dialogService = inject(ZardDialogService);

  constructor(
    private sseService: SseService,
    private realtimeService: RealtimeNotificationService,
  ) {}

  /**
   * Connects to the SSE endpoint for a specific job and returns an observable of job updates.
   *
   * @param jobId The UUID of the job to track
   * @returns Observable of AsyncJob updates
   */
  watchJob(jobId: string): Observable<AsyncJob> {
    // Prefer the global multiplexed stream, but fall back to the per-job SSE endpoint
    // when no first update arrives promptly.
    return this.realtimeService.watchJob(jobId).pipe(
      timeout({
        first: 1500,
        with: () => this.watchJobDirect(jobId),
      }),
      catchError(() => this.watchJobDirect(jobId)),
    );
  }

  private watchJobDirect(jobId: string): Observable<AsyncJob> {
    return this.sseService
      .connect<any>(`/api/async-jobs/status/${jobId}/`)
      .pipe(map((payload) => mapJobUpdateToAsyncJob(payload)));
  }

  /**
   * Opens a progress dialog for a specific job.
   *
   * @param jobId The UUID of the job
   * @param title Optional title for the dialog
   * @returns Observable that emits the final job state when closed
   */
  openProgressDialog(jobId: string, title?: string): Observable<AsyncJob> {
    const dialogRef = this.dialogService.create({
      zContent: JobProgressDialogComponent,
      zData: { jobId, title },
      zTitle: title || 'Processing Task...',
      zWidth: '450px',
      zClosable: false,
      zHideFooter: true,
    });

    return dialogRef.afterClosed();
  }

  /**
   * Helper to check if a job is finished.
   */
  isFinished(job: AsyncJob): boolean {
    return (
      job.status === AsyncJob.StatusEnum.Completed || job.status === AsyncJob.StatusEnum.Failed
    );
  }
}
