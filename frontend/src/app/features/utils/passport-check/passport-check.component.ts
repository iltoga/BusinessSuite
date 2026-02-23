import { ZardButtonComponent } from '@/shared/components/button';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, OnDestroy, OnInit, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom, Subscription } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CustomersService } from '../../../core/api/api/customers.service';
import { JobService } from '../../../core/services/job.service';
import { GlobalToastService } from '../../../core/services/toast.service';
import { ConfirmDialogComponent } from '../../../shared/components/confirm-dialog/confirm-dialog.component';
import { ContextHelpDirective } from '../../../shared/directives/context-help.directive';
import { HelpService } from '../../../shared/services/help.service';
import { extractServerErrorMessage } from '../../../shared/utils/form-errors';

@Component({
  selector: 'app-passport-check',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ZardButtonComponent,
    ContextHelpDirective,
    ConfirmDialogComponent,
    FileUploadComponent,
  ],
  templateUrl: './passport-check.component.html',
  styleUrls: ['./passport-check.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PassportCheckComponent implements OnInit, OnDestroy {
  private readonly customersApi = inject(CustomersService);
  private readonly http = inject(HttpClient);
  private readonly jobService = inject(JobService);
  private readonly toast = inject(GlobalToastService);
  private readonly helpService = inject(HelpService);
  private readonly router = inject(Router);
  private jobProgressSubscription: Subscription | null = null;

  readonly selectedFile = signal<File | null>(null);
  readonly previewUrl = signal<string | null>(null);
  readonly method = signal<'ai' | 'hybrid'>('hybrid');

  readonly isChecking = signal(false);
  readonly progress = signal(0);
  readonly progressMessage = signal('');
  readonly processSteps = signal<string[]>([]);

  readonly result = signal<any>(null);
  readonly existingCustomer = signal<any>(null);

  readonly showUpdateDialog = signal(false);
  readonly showCreateDialog = signal(false);

  ngOnInit() {
    this.helpService.register('/utils/passport-check', {
      id: '/utils/passport-check',
      briefExplanation:
        'This tool allows you to verify if a passport image meets the requirements for uploading to the Indonesian immigration website.',
      details:
        'AI: Uses deterministic OpenCV quality checks plus Google Gemini analysis. Hybrid: Runs deterministic checks, then AI with additional decision context for stricter validation.',
    });
    this.helpService.setContextForPath('/utils/passport-check');
  }

  ngOnDestroy(): void {
    this.stopProgressStream();
  }

  onFileSelected(file: File) {
    this.selectedFile.set(file);

    // Create preview
    const reader = new FileReader();
    reader.onload = (e) => {
      this.previewUrl.set(e.target?.result as string);
    };
    reader.readAsDataURL(file);

    // Reset state
    this.result.set(null);
    this.existingCustomer.set(null);
    this.processSteps.set([]);
  }

  onFileCleared() {
    this.stopProgressStream();
    this.selectedFile.set(null);
    this.previewUrl.set(null);
    this.result.set(null);
    this.existingCustomer.set(null);
    this.processSteps.set([]);
  }

  async checkPassport() {
    const file = this.selectedFile();
    if (!file) return;

    this.stopProgressStream();
    this.isChecking.set(true);
    this.progress.set(0);
    this.progressMessage.set('Starting verification...');
    this.result.set(null);
    this.existingCustomer.set(null);

    try {
      const formData = new FormData();
      formData.append('file', file, file.name);
      formData.append('method', this.method());

      const response = await firstValueFrom(
        this.http.post<{ job_id?: string; jobId?: string }>(
          `${environment.apiUrl}/api/customers/check-passport/`,
          formData,
          {
            withCredentials: true,
          },
        ),
      );

      const jobId = response?.job_id ?? response?.jobId;
      if (jobId) {
        this.listenToJobProgress(jobId);
      } else {
        this.toast.error('Passport check started but no job id was returned');
        this.isChecking.set(false);
      }
    } catch (error) {
      const message = extractServerErrorMessage(error) || 'Failed to start passport check';
      this.toast.error(message);
      this.isChecking.set(false);
    }
  }

  private listenToJobProgress(jobId: string) {
    this.stopProgressStream();
    this.jobProgressSubscription = this.jobService.watchJob(jobId).subscribe({
      next: async (job: any) => {
        if (job?.error) {
          this.isChecking.set(false);
          this.toast.error(String(job.error));
          this.stopProgressStream();
          return;
        }

        this.progress.set(Number(job?.progress ?? 0));
        const message = String(job?.message ?? 'Processing...');
        this.progressMessage.set(message);
        this.appendProcessStep(message);

        if (job?.status === 'completed') {
          this.isChecking.set(false);
          const result = job?.result ?? null;
          this.result.set(result);
          this.stopProgressStream();

          if (result?.is_valid) {
            await this.checkExistingCustomer(result.passport_data);
          }
        } else if (job?.status === 'failed') {
          this.isChecking.set(false);
          this.toast.error(job?.errorMessage || job?.error_message || 'Verification failed');
          this.stopProgressStream();
        }
      },
      error: () => {
        this.isChecking.set(false);
        this.toast.error('Connection to server lost');
        this.stopProgressStream();
      },
    });
  }

  private stopProgressStream() {
    this.jobProgressSubscription?.unsubscribe();
    this.jobProgressSubscription = null;
  }

  private appendProcessStep(message: string) {
    if (!message) return;
    const trimmed = message.trim();
    if (!trimmed) return;

    this.processSteps.update((steps) => {
      if (steps[steps.length - 1] === trimmed) {
        return steps;
      }
      return [...steps, trimmed];
    });
  }

  private async checkExistingCustomer(passportData: any) {
    if (!passportData.first_name || !passportData.last_name) return;

    try {
      // Search for customer by name
      const query = `${passportData.first_name} ${passportData.last_name}`;
      const response = await this.customersApi
        .customersList(undefined, undefined, undefined, query)
        .toPromise();

      if (response && response.results && response.results.length > 0) {
        // Find exact match (simplified for now)
        const customer = response.results[0];
        this.existingCustomer.set(customer);

        if (customer.passportNumber !== passportData.passport_number) {
          this.showUpdateDialog.set(true);
        }
      } else {
        this.showCreateDialog.set(true);
      }
    } catch (error) {
      console.error('Error checking existing customer', error);
    }
  }

  async updateCustomer() {
    const customer = this.existingCustomer();
    const file = this.selectedFile();
    const data = this.result()?.passport_data;

    if (!customer || !file || !data) return;

    try {
      await this.customersApi
        .customersPartialUpdate(customer.id, {
          passportNumber: data.passport_number,
          passportIssueDate: data.issue_date,
          passportExpirationDate: data.expiration_date,
          passportFile: file as any, // The API client might need adjustment for file uploads in PATCH
        } as any)
        .toPromise();

      this.toast.success('Customer updated successfully');
      this.showUpdateDialog.set(false);
    } catch (error) {
      this.toast.error('Failed to update customer');
    }
  }

  createNewCustomer() {
    const data = this.result()?.passport_data;
    if (!data) return;

    // Navigate to new customer form with query params
    this.router.navigate(['/customers/new'], {
      queryParams: {
        firstName: data.first_name,
        lastName: data.last_name,
        passportNumber: data.passport_number,
        nationality: data.nationality,
        // We can't easily pass the file via query params, so the user will have to upload it again
        // Or we could store it in a shared service temporarily
      },
    });
  }

  getDisplayRejectionReason(): string {
    const result = this.result();
    if (!result) {
      return '';
    }

    if (result.rejection_code === 'page_cropped') {
      return 'Passport page is cropped/partial. Please upload a full passport biodata page with all 4 corners visible.';
    }

    if (result.rejection_code === 'image_blurry') {
      return 'Passport image is blurry. Please upload a sharp image where all text and MRZ are clearly readable.';
    }

    if (result.rejection_code === 'mrz_incomplete') {
      return 'MRZ is incomplete (only part of the bottom zone is visible/readable). Please upload the full passport page with both full MRZ lines.';
    }

    if (result.rejection_code === 'mrz_cropped') {
      return 'The last MRZ line is cut/cropped at the bottom edge. Please upload a full passport image where both MRZ lines are entirely visible.';
    }

    if (result.rejection_code === 'invalid_name') {
      return 'Extracted first/last name looks invalid. Please upload a clearer image of the complete passport biodata page.';
    }

    if (result.rejection_code === 'invalid_passport_number') {
      return result.rejection_reason || 'Extracted passport number is invalid.';
    }

    if (result.rejection_code === 'invalid_nationality') {
      return 'Extracted nationality code is invalid. Please use a clearer full-page passport image.';
    }

    if (result.rejection_code === 'missing_essential_fields') {
      return 'Essential fields are missing (name, passport number, nationality). The image quality/completeness is insufficient.';
    }

    return result.rejection_reason || 'Verification failed.';
  }
}
