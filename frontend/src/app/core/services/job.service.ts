import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { AsyncJob } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';
import { ZardDialogService } from '@/shared/components/dialog';

@Injectable({
  providedIn: 'root',
})
export class JobService {
  private dialogService = inject(ZardDialogService);

  constructor(
    private sseService: SseService,
    private authService: AuthService,
  ) {}

  /**
   * Connects to the SSE endpoint for a specific job and returns an observable of job updates.
   *
   * @param jobId The UUID of the job to track
   * @returns Observable of AsyncJob updates
   */
  watchJob(jobId: string): Observable<AsyncJob> {
    const token = this.authService.getToken();
    // Use the explicit SSE endpoint path
    const url = `/api/async-jobs/status/${jobId}/?token=${token}`;
    return this.sseService.connect<AsyncJob>(url);
  }

  /**
   * Opens a progress dialog for a specific job.
   *
   * @param jobId The UUID of the job
   * @param title Optional title for the dialog
   * @returns Observable that emits the final job state when closed
   */
  openProgressDialog(jobId: string, title?: string): Observable<AsyncJob> {
    const {
      JobProgressDialogComponent,
    } = require('@/shared/components/job-progress-dialog/job-progress-dialog.component');

    const dialogRef = this.dialogService.create({
      zContent: JobProgressDialogComponent,
      zData: { jobId, title },
      zWidth: '450px',
      zClosable: false,
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
