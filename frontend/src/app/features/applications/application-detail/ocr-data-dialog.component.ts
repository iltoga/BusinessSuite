import { ChangeDetectionStrategy, Component, inject, input, output } from '@angular/core';

import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-ocr-data-dialog',
  standalone: true,
  imports: [ZardButtonComponent, ZardIconComponent, ZardInputDirective],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (isOpen()) {
      <div class="app-modal-overlay fixed inset-0 z-1200 flex justify-center bg-black/50 p-4">
        <div class="w-full max-w-2xl rounded-lg bg-card p-6 shadow-lg">
          <div class="flex items-start justify-between gap-3">
            <div>
              <h3 class="text-lg font-semibold">OCR Extracted Data</h3>
              <p class="text-sm text-muted-foreground">
                This document does not have a details field. Copy the extracted data for manual use.
              </p>
            </div>
            <button
              z-button
              zType="ghost"
              zSize="sm"
              class="h-8 w-8 rounded-full p-0"
              (click)="closed.emit()"
              aria-label="Close OCR extracted data dialog"
            >
              <z-icon zType="circle-x" class="h-5 w-5" />
            </button>
          </div>

          <div class="mt-4">
            <textarea
              z-input
              readonly
              rows="14"
              class="w-full min-h-64 font-mono text-xs leading-5"
              [value]="text()"
            ></textarea>
          </div>

          <div class="mt-6 flex justify-end gap-2">
            <button z-button zType="outline" (click)="copyText()">Copy</button>
            <button z-button zType="default" (click)="closed.emit()">
              <z-icon zType="circle-x" class="h-4 w-4" />
              Close
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [
    `
      .app-modal-overlay {
        align-items: flex-start;
        overflow-y: auto;
        padding-top: 1rem;
        padding-bottom: 1rem;
      }
    `,
  ],
})
export class OcrDataDialogComponent {
  private readonly toast = inject(GlobalToastService);

  readonly isOpen = input.required<boolean>();
  readonly text = input.required<string>();

  readonly closed = output<void>();

  copyText(): void {
    const value = this.text();
    if (!value) return;
    navigator.clipboard.writeText(value).then(
      () => this.toast.success('Copied to clipboard'),
      () => this.toast.error('Failed to copy'),
    );
  }
}
