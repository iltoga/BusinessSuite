import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';

import { ZardCardComponent } from '@/shared/components/card';
import { Z_MODAL_DATA } from '@/shared/components/dialog';
import { ZardIconComponent } from '@/shared/components/icon';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

export interface ProductDeleteTaskRecord {
  id: number;
  step: number;
  name: string;
}

export interface ProductDeleteApplicationRecord {
  id: number;
  customerName: string;
  status: string;
  statusDisplay: string;
  docDate?: string | null;
  dueDate?: string | null;
  workflowCount: number;
  documentCount: number;
  invoiceLineCount: number;
}

export interface ProductDeleteInvoiceApplicationRecord {
  id: number;
  invoiceId: number;
  invoiceNoDisplay: string;
  invoiceStatus: string;
  customerApplicationId?: number | null;
  customerName: string;
  amount: string | number;
  status: string;
  statusDisplay: string;
  paymentCount: number;
}

export interface ProductDeleteRelatedCounts {
  tasks: number;
  applications: number;
  workflows: number;
  documents: number;
  invoiceApplications: number;
  invoices: number;
  payments: number;
}

export interface ProductDeleteRelatedRecords {
  tasks: ProductDeleteTaskRecord[];
  applications: ProductDeleteApplicationRecord[];
  invoiceApplications: ProductDeleteInvoiceApplicationRecord[];
}

export interface ProductDeletePreviewData {
  productId: number;
  productCode: string;
  productName: string;
  canDelete: boolean;
  requiresForceDelete: boolean;
  message?: string | null;
  relatedCounts: ProductDeleteRelatedCounts;
  relatedRecords: ProductDeleteRelatedRecords;
  relatedRecordsTruncated?: {
    tasks?: boolean;
    applications?: boolean;
    invoiceApplications?: boolean;
  };
  recordLimit?: number;
}

export interface ProductDeleteDialogResult {
  forceDelete: boolean;
}

@Component({
  selector: 'app-product-delete-dialog-content',
  standalone: true,
  imports: [CommonModule, ZardCardComponent, ZardIconComponent, AppDatePipe],
  templateUrl: './product-delete-dialog-content.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductDeleteDialogContentComponent {
  readonly data = inject<ProductDeletePreviewData>(Z_MODAL_DATA);
  readonly confirmChecked = signal(false);
  readonly forceDelete = signal(false);
  readonly showRelated = signal(false);
  readonly showValidation = signal(false);
  readonly showForceValidation = signal(false);

  readonly hasAnyRelatedRecords = computed(() => {
    const counts = this.data.relatedCounts;
    return (
      counts.tasks +
        counts.applications +
        counts.workflows +
        counts.documents +
        counts.invoiceApplications +
        counts.invoices +
        counts.payments >
      0
    );
  });

  validate(): boolean {
    const confirmed = this.confirmChecked();
    const forceChoiceValid = this.data.canDelete || this.forceDelete();

    this.showValidation.set(!confirmed);
    this.showForceValidation.set(!forceChoiceValid);

    return confirmed && forceChoiceValid;
  }

  getResult(): ProductDeleteDialogResult {
    return { forceDelete: this.forceDelete() };
  }
}
