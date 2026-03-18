import { ChangeDetectionStrategy, Component, input, output } from '@angular/core';

import type { OcrStatusResponse } from '@/core/services/applications.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardIconComponent } from '@/shared/components/icon';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

@Component({
  selector: 'app-ocr-review-dialog',
  standalone: true,
  imports: [ZardButtonComponent, ZardIconComponent, AppDatePipe],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (isOpen() && reviewData()) {
      <div class="app-modal-overlay fixed inset-0 z-1200 flex justify-center bg-black/50 p-4">
        <div class="w-full max-w-lg rounded-lg bg-card p-6 shadow-lg">
          <div class="flex items-start justify-between">
            <div>
              <h3 class="text-lg font-semibold">OCR Review</h3>
              <p class="text-sm text-muted-foreground">
                Review extracted data before applying to the document.
              </p>
            </div>
            <button
              z-button
              zType="ghost"
              zSize="sm"
              class="h-8 w-8 rounded-full p-0"
              (click)="dismiss.emit()"
              aria-label="Close OCR review dialog"
            >
              <z-icon zType="circle-x" class="h-5 w-5" />
            </button>
          </div>

          <div class="mt-4 space-y-3 text-sm">
            @if (reviewData()!.mrzData?.number) {
              <div class="flex justify-between">
                <span class="text-muted-foreground">Document Number</span>
                <span>{{ reviewData()!.mrzData?.number }}</span>
              </div>
            }
            @if (reviewData()!.mrzData?.expirationDateYyyyMmDd) {
              <div class="flex justify-between">
                <span class="text-muted-foreground">Expiration Date</span>
                <span>{{ reviewData()!.mrzData?.expirationDateYyyyMmDd | appDate }}</span>
              </div>
            }
            @if (reviewData()!.aiWarning) {
              <div class="rounded-md bg-warning/10 p-2 text-warning">
                {{ reviewData()!.aiWarning }}
              </div>
            }
          </div>

          <div class="mt-6 flex justify-end gap-2">
            <button z-button zType="outline" (click)="dismiss.emit()">Dismiss</button>
            <button z-button zType="default" (click)="apply.emit()">Apply Data</button>
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
export class OcrReviewDialogComponent {
  readonly isOpen = input.required<boolean>();
  readonly reviewData = input.required<OcrStatusResponse | null>();

  readonly apply = output<void>();
  readonly dismiss = output<void>();
}
