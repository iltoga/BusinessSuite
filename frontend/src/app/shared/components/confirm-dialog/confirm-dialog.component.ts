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

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ConfirmDialogComponent {
  isOpen = input<boolean>(false);
  title = input<string>('Confirm Action');
  message = input<string>('Are you sure?');
  confirmText = input<string>('Confirm');
  cancelText = input<string>('Cancel');
  destructive = input<boolean>(false);

  confirmed = output<void>();
  cancelled = output<void>();

  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);
  private dialogRef = signal<ZardDialogRef | null>(null);

  constructor() {
    effect(() => {
      const open = this.isOpen();
      const current = this.dialogRef();

      if (open && !current) {
        const ref = this.dialogService.create({
          zTitle: this.title(),
          zContent: this.message(),
          zOkText: this.confirmText(),
          zCancelText: this.cancelText(),
          zOkDestructive: this.destructive(),
          zOnOk: () => {
            this.confirmed.emit();
          },
          zOnCancel: () => {
            this.cancelled.emit();
          },
        });

        this.dialogRef.set(ref);
      }

      if (!open && current) {
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
