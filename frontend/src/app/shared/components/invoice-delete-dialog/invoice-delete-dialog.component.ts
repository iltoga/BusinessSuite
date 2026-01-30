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
  InvoiceDeleteDialogContentComponent,
  type InvoiceDeleteDialogResult,
  type InvoiceDeletePreviewData,
} from './invoice-delete-dialog-content.component';

export type { InvoiceDeleteDialogResult, InvoiceDeletePreviewData };

@Component({
  selector: 'app-invoice-delete-dialog',
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDeleteDialogComponent {
  isOpen = input<boolean>(false);
  data = input<InvoiceDeletePreviewData | null>(null);

  confirmed = output<InvoiceDeleteDialogResult>();
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
        const ref = this.dialogService.create({
          zTitle: 'Delete Invoice',
          zContent: InvoiceDeleteDialogContentComponent,
          zOkText: 'Force Delete Invoice',
          zCancelText: 'Cancel',
          zOkDestructive: true,
          zData: dialogData,
          zOnOk: (content) => {
            if (!content.validate()) {
              return false;
            }
            this.confirmed.emit(content.getResult());
            return;
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
