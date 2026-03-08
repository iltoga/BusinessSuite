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
import type { DeleteDialogData, DeleteDialogResult } from './delete-dialog.models';

@Component({
  selector: 'app-delete-dialog',
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DeleteDialogComponent {
  open = input<boolean>(false);
  data = input<DeleteDialogData | null>(null);
  
  confirmed = output<DeleteDialogResult>();
  cancelled = output<void>();

  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);
  private dialogRef = signal<ZardDialogRef | null>(null);
  private extraChecked = signal(false);

  constructor() {
    effect(() => {
      const open = this.open();
      const current = this.dialogRef();
      const data = this.data();

      if (open && data && !current) {
        const title = this.buildTitle(data);
        const message = this.buildMessage(data);
        
        const ref = this.dialogService.create({
          zTitle: title,
          zContent: message,
          zOkText: 'Delete',
          zCancelText: 'Cancel',
          zOkDestructive: true,
          zOnOk: () => {
            this.confirmed.emit({ extraChecked: this.extraChecked() });
            this.extraChecked.set(false);
          },
          zOnCancel: () => {
            this.extraChecked.set(false);
            this.cancelled.emit();
          },
        });

        this.dialogRef.set(ref);
      }

      if (!open && current) {
        current.close();
        this.dialogRef.set(null);
        this.extraChecked.set(false);
      }
    });

    this.destroyRef.onDestroy(() => {
      const current = this.dialogRef();
      if (current) {
        current.close();
        this.extraChecked.set(false);
      }
    });
  }

  private buildTitle(data: DeleteDialogData): string {
    const mode = data.mode ?? 'all';
    const count = data.totalCount ?? 0;
    
    if (mode === 'selected' && data.entityLabel.endsWith('s')) {
      return `Delete Selected ${data.entityLabel}`;
    }
    
    if (mode === 'all') {
      return `Delete All ${data.entityLabel}${count > 0 ? ` (${count})` : ''}`;
    }
    
    return `Delete ${data.entityLabel}?`;
  }

  private buildMessage(data: DeleteDialogData): string {
    let message = data.detailsText ?? 'This action cannot be undone.';
    
    if (data.extraCheckboxLabel) {
      message += '\n\n☐ ' + data.extraCheckboxLabel;
      if (data.extraCheckboxTooltip) {
        message += ' — ' + data.extraCheckboxTooltip;
      }
    }
    
    return message;
  }
}
