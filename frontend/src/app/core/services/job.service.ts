import { inject, Injectable } from '@angular/core';
import { catchError, map, Observable, takeWhile, timeout } from 'rxjs';

import { type AsyncJob } from '@/core/api';
import { RealtimeNotificationService } from '@/core/services/realtime-notification.service';
import { SseService } from '@/core/services/sse.service';
import { isTerminalAsyncJob, normalizeAsyncJobUpdate } from '@/core/utils/async-job-contract';
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
    // Prefer the per-job SSE stream because it returns the canonical job payload
    // immediately and closes cleanly on completion.
    return this.watchJobDirect(jobId).pipe(catchError(() => this.realtimeService.watchJob(jobId)));
  }

  private watchJobDirect(jobId: string): Observable<AsyncJob> {
    return this.sseService
      .connect<unknown>(`/api/async-jobs/status/${jobId}/`)
      .pipe(
        map((payload) => normalizeAsyncJobUpdate(payload)),
        takeWhile((job) => !isTerminalAsyncJob(job), true),
      );
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
    return isTerminalAsyncJob(job);
  }
}
