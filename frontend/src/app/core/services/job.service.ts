import { HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, Observable, switchMap, takeWhile, timer } from 'rxjs';

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
    private http: HttpClient,
  ) {}

  /**
   * Connects to the SSE endpoint for a specific job and returns an observable of job updates.
   *
   * @param jobId The UUID of the job to track
   * @returns Observable of AsyncJob updates
   */
  watchJob(jobId: string): Observable<AsyncJob> {
    const token = this.authService.getToken();
    const params = new URLSearchParams();

    if (token) {
      params.set('token', token);
    } else if (this.authService.isMockEnabled()) {
      params.set('token', 'mock-token');
    }

    const query = params.toString();
    const url = `/api/async-jobs/status/${jobId}/${query ? `?${query}` : ''}`;

    return this.sseService.connect<AsyncJob>(url).pipe(catchError(() => this.pollJob(jobId)));
  }

  private pollJob(jobId: string): Observable<AsyncJob> {
    return timer(0, 1000).pipe(
      switchMap(() => this.http.get<AsyncJob>(`/api/async-jobs/${jobId}/`)),
      takeWhile((job) => !this.isFinished(job), true),
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
    const {
      JobProgressDialogComponent,
    } = require('@/shared/components/job-progress-dialog/job-progress-dialog.component');

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
