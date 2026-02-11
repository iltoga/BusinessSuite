import { AsyncJob } from '@/core/api';
import { JobService } from '@/core/services/job.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { Z_MODAL_DATA, ZardDialogComponent, ZardDialogRef } from '@/shared/components/dialog';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardLoaderComponent } from '@/shared/components/loader/loader.component';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';

export interface JobProgressData {
  jobId: string;
  title?: string;
}

@Component({
  selector: 'app-job-progress-dialog',
  standalone: true,
  imports: [
    CommonModule,
    ZardDialogComponent,
    ZardLoaderComponent,
    ZardButtonComponent,
    ZardIconComponent,
  ],
  template: `
    <z-dialog [title]="data.title || 'Processing Task...'">
      <div class="flex flex-col items-center justify-center py-6 space-y-4">
        @if (!isFinished()) {
          <z-loader size="xl" variant="primary"></z-loader>
        } @else if (job()?.status === 'completed') {
          <div
            class="flex items-center justify-center w-16 h-16 rounded-full bg-green-100 text-green-600"
          >
            <z-icon zType="check" class="w-8 h-8"></z-icon>
          </div>
        } @else if (job()?.status === 'failed') {
          <div
            class="flex items-center justify-center w-16 h-16 rounded-full bg-red-100 text-red-600"
          >
            <z-icon zType="circle-alert" class="w-8 h-8"></z-icon>
          </div>
        }

        <div class="text-center">
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

        @if (job()?.status === 'failed') {
          <div
            class="w-full p-3 bg-red-50 border border-red-200 rounded text-red-700 text-sm overflow-auto max-h-32"
          >
            <strong>Error:</strong> {{ job()?.errorMessage || 'An unknown error occurred.' }}
          </div>
        }
      </div>

      <div class="flex justify-end pt-4 border-t">
        @if (isFinished()) {
          <z-button variant="primary" (click)="close()">Close</z-button>
        }
      </div>
    </z-dialog>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JobProgressDialogComponent implements OnInit {
  private jobService = inject(JobService);
  private dialogRef = inject(ZardDialogRef);
  readonly data = inject<JobProgressData>(Z_MODAL_DATA);

  readonly job = signal<AsyncJob | null>(null);
  readonly isFinished = signal(false);

  ngOnInit(): void {
    if (this.data.jobId) {
      this.jobService.watchJob(this.data.jobId).subscribe({
        next: (job) => {
          this.job.set(job);
          if (this.jobService.isFinished(job)) {
            this.isFinished.set(true);
            if (job.status === 'completed') {
              // Automatically close on success after a short delay
              setTimeout(() => this.dialogRef.close(job), 1500);
            }
          }
        },
        error: (err) => {
          this.isFinished.set(true);
          this.job.set({
            status: 'failed' as any,
            errorMessage: 'Lost connection to server.',
            message: 'Failed to track task',
            progress: 100,
          } as any);
        },
      });
    }
  }

  close(): void {
    this.dialogRef.close(this.job());
  }
}
