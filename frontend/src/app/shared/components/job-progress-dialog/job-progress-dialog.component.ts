import { AsyncJobStatusEnum, type AsyncJob } from '@/core/api';
import { JobService } from '@/core/services/job.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { Z_MODAL_DATA, ZardDialogRef } from '@/shared/components/dialog';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardLoaderComponent } from '@/shared/components/loader/loader.component';

import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

export interface JobProgressData {
  jobId: string;
  title?: string;
}

@Component({
  selector: 'app-job-progress-dialog',
  standalone: true,
  imports: [ZardLoaderComponent, ZardButtonComponent, ZardIconComponent],
  template: `
    <div class="flex flex-col items-center justify-center py-6 space-y-4">
      @if (!isFinished()) {
        <z-loader size="xl" variant="primary"></z-loader>
      } @else if (job()?.status === jobStatusEnum.Completed) {
        <div
          class="flex items-center justify-center w-16 h-16 rounded-full bg-green-100 text-green-600"
        >
          <z-icon zType="check" class="w-8 h-8"></z-icon>
        </div>
      } @else if (job()?.status === jobStatusEnum.Failed) {
        <div
          class="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 text-red-600"
        >
          <z-icon zType="circle-alert" class="w-8 h-8"></z-icon>
        </div>
      }

      <div class="text-center w-full">
        <p class="text-lg font-medium text-gray-900">
          {{ job()?.message || 'Please wait while we process your request...' }}
        </p>
        @if (job()?.progress !== undefined) {
          <div class="w-full bg-gray-200 rounded-full h-2.5 mt-4 overflow-hidden">
            <div
              class="bg-primary h-2.5 rounded-full transition-all duration-300"
              [style.width.%]="job()?.progress"
            ></div>
          </div>
          <p class="text-xs text-gray-500 mt-1">{{ job()?.progress }}%</p>
        }
      </div>

      @if (job()?.status === jobStatusEnum.Failed) {
        <div
          class="w-full p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm overflow-auto max-h-32"
        >
          <strong>Error:</strong> {{ job()?.errorMessage || 'An unknown error occurred.' }}
        </div>
      }
    </div>

    <div class="flex justify-end pt-4 border-t -mx-6 px-6">
      @if (isFinished()) {
        <z-button variant="primary" (click)="close()">
          <z-icon zType="circle-x" class="h-4 w-4"></z-icon>
          Close
        </z-button>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JobProgressDialogComponent implements OnInit {
  readonly jobStatusEnum = AsyncJobStatusEnum;
  private jobService = inject(JobService);
  private dialogRef = inject(ZardDialogRef);
  private destroyRef = inject(DestroyRef);
  readonly data = inject<JobProgressData>(Z_MODAL_DATA);

  readonly job = signal<AsyncJob | null>(null);
  readonly isFinished = signal(false);

  ngOnInit(): void {
    if (this.data.jobId) {
      this.jobService
        .watchJob(this.data.jobId)
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe({
          next: (job) => {
            this.job.set(job);
            if (this.jobService.isFinished(job)) {
              this.isFinished.set(true);
              if (job.status === AsyncJobStatusEnum.Completed) {
                // Automatically close on success after a short delay
                setTimeout(() => this.dialogRef.close(job), 1500);
              }
            }
          },
          error: (err) => {
            this.isFinished.set(true);
            this.job.set({
              id: this.data.jobId,
              jobId: this.data.jobId,
              taskName: 'Task',
              status: AsyncJobStatusEnum.Failed,
              progress: 100,
              message: 'Failed to track task',
              result: {},
              errorMessage: 'Lost connection to server.',
              createdAt: '',
              updatedAt: '',
              createdBy: null,
            });
          },
        });
    }
  }

  close(): void {
    this.dialogRef.close(this.job());
  }
}
