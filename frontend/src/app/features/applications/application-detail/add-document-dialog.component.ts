import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardIconComponent } from '@/shared/components/icon';

@Component({
  selector: 'app-add-document-dialog',
  standalone: true,
  imports: [ZardButtonComponent, ZardComboboxComponent, ZardIconComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (isOpen()) {
      <div class="app-modal-overlay fixed inset-0 z-1200 flex justify-center bg-black/50 p-4">
        <div class="w-full max-w-lg rounded-lg bg-card p-6 shadow-lg">
          <div class="flex items-start justify-between">
            <div>
              <h3 class="text-lg font-semibold">Add Document</h3>
              <p class="text-sm text-muted-foreground">Select the document type you want to add.</p>
            </div>
            <button
              z-button
              zType="ghost"
              zSize="sm"
              class="h-8 w-8 rounded-full p-0"
              (click)="closed.emit()"
              aria-label="Close add document dialog"
            >
              <z-icon zType="circle-x" class="h-5 w-5" />
            </button>
          </div>

          <div class="mt-6 space-y-4">
            <z-combobox
              [options]="options()"
              [value]="selectedType()"
              [searchable]="true"
              placeholder="Select doc type"
              [zWidth]="'full'"
              (zValueChange)="selectedType.set($event)"
            />
          </div>

          <div class="mt-6 flex justify-end gap-2">
            <button z-button zType="outline" (click)="closed.emit()">Cancel</button>
            <button z-button zType="default" (click)="onAdd()" [disabled]="!selectedType()">
              Add Document
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
export class AddDocumentDialogComponent {
  readonly isOpen = input.required<boolean>();
  readonly options = input.required<ZardComboboxOption[]>();

  readonly closed = output<void>();
  readonly addDocument = output<string>();

  readonly selectedType = signal<string | null>(null);

  onAdd(): void {
    const type = this.selectedType();
    if (type) {
      this.addDocument.emit(type);
      this.selectedType.set(null);
    }
  }
}
