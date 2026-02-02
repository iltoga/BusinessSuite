import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { ZardDialogService } from '@/shared/components/dialog';
import type { ZardDialogRef } from '@/shared/components/dialog/dialog-ref';

import {
  BulkDeleteDialogContentComponent,
  type BulkDeleteDialogData,
  type BulkDeleteDialogResult,
} from './bulk-delete-dialog-content.component';

export type { BulkDeleteDialogData, BulkDeleteDialogResult };

@Component({
  selector: 'app-bulk-delete-dialog',
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BulkDeleteDialogComponent {
  isOpen = input<boolean>(false);
  data = input<BulkDeleteDialogData | null>(null);

  confirmed = output<BulkDeleteDialogResult>();
  cancelled = output<void>();

  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);
  private dialogRef = signal<ZardDialogRef | null>(null);

  constructor() {
    effect(() => {
      const open = this.isOpen();
      const dialogData = this.data();
      const current = this.dialogRef();

      if (open && dialogData && !current) {
        const title = `Delete ${dialogData.mode === 'selected' ? 'Selected' : 'All'} ${dialogData.entityLabel}`;
        const confirmText = `Yes, Delete ${dialogData.mode === 'selected' ? 'Selected' : 'All'} ${dialogData.entityLabel}`;

        const ref = this.dialogService.create({
          zTitle: title,
          zContent: BulkDeleteDialogContentComponent,
          zOkText: confirmText,
          zCancelText: 'Cancel',
          zOkDestructive: true,
          zOkDisabled: dialogData.totalCount <= 0,
          zData: dialogData,
          zOnOk: (content) => {
            const result = content.getResult();
            this.confirmed.emit(result);
          },
          zOnCancel: () => {
            this.cancelled.emit();
          },
        });

        this.dialogRef.set(ref);
      }

      if ((!open || !dialogData) && current) {
        current.close();
        this.dialogRef.set(null);
      }
    });

    this.destroyRef.onDestroy(() => {
      const current = this.dialogRef();
      if (current) {
        current.close();
      }
    });
  }
}
