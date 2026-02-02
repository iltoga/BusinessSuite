import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Z_MODAL_DATA } from '@/shared/components/dialog';

export interface InvoiceDeletePreviewData {
  invoiceNoDisplay: string;
  customerName: string;
  totalAmount: string | number;
  statusDisplay: string;
  invoiceApplicationsCount: number;
  customerApplicationsCount: number;
  paymentsCount: number;
}

export interface InvoiceDeleteDialogResult {
  deleteCustomerApplications: boolean;
}

@Component({
  selector: 'app-invoice-delete-dialog-content',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './invoice-delete-dialog-content.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDeleteDialogContentComponent {
  readonly data = inject<InvoiceDeletePreviewData>(Z_MODAL_DATA);
  readonly confirmChecked = signal(false);
  readonly deleteCustomerApps = signal(false);
  readonly showValidation = signal(false);

  validate(): boolean {
    const valid = this.confirmChecked();
    this.showValidation.set(!valid);
    return valid;
  }

  getResult(): InvoiceDeleteDialogResult {
    return { deleteCustomerApplications: this.deleteCustomerApps() };
  }
}
