import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';

import { Z_MODAL_DATA } from '@/shared/components/dialog';

export type BulkDeleteMode = 'all' | 'selected';

export interface BulkDeleteDialogData {
  entityLabel: string;
  totalCount: number;
  query?: string | null;
  mode: BulkDeleteMode;
  detailsText: string;
  extraCheckboxLabel?: string;
}

export interface BulkDeleteDialogResult {
  extraChecked: boolean;
}

@Component({
  selector: 'app-bulk-delete-dialog-content',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './bulk-delete-dialog-content.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BulkDeleteDialogContentComponent {
  readonly data = inject<BulkDeleteDialogData>(Z_MODAL_DATA);
  readonly extraChecked = signal(false);

  getResult(): BulkDeleteDialogResult {
    return { extraChecked: this.extraChecked() };
  }
}
