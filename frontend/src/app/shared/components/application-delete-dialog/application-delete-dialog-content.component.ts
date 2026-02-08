import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Z_MODAL_DATA } from '@/shared/components/dialog';

export interface ApplicationDeleteDialogData {
  applicationId: number;
  invoiceId?: number | null;
}

export interface ApplicationDeleteDialogResult {
  confirmed: boolean;
}

@Component({
  selector: 'app-application-delete-dialog-content',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './application-delete-dialog-content.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationDeleteDialogContentComponent {
  readonly data = inject<ApplicationDeleteDialogData>(Z_MODAL_DATA);
  readonly confirmChecked = signal(false);
  readonly showValidation = signal(false);

  validate(): boolean {
    const valid = this.confirmChecked();
    this.showValidation.set(!valid);
    return valid;
  }

  getResult(): ApplicationDeleteDialogResult {
    return { confirmed: true };
  }
}
