import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';

import { DocumentsService } from '@/core/services/documents.service';
import { ZardButtonComponent } from '@/shared/components/button';
import type {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';

@Component({
  selector: 'app-document-preview',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardIconComponent,
    ZardPopoverComponent,
    ZardPopoverDirective,
  ],
  template: `
    @if (fileLink()) {
      <button
        z-button
        [zType]="zType()"
        [zSize]="zSize()"
        type="button"
        zPopover
        [zContent]="previewContent"
        zTrigger="click"
        zPlacement="top"
        (zVisibleChange)="onPopoverToggle($event)"
      >
        {{ label() }}
      </button>

      <ng-template #previewContent>
        <z-popover class="p-2 w-72 sm:w-80">
          <div class="space-y-2">
            <div class="flex items-center justify-between">
              <span class="text-xs font-medium text-muted-foreground truncate">
                {{ fileName() }}
              </span>
            </div>
            <div
              class="overflow-hidden rounded border bg-muted/20 min-h-25 flex items-center justify-center"
            >
              @if (isLoading()) {
                <div class="text-xs text-muted-foreground animate-pulse">Loading preview...</div>
              } @else if (previewUrl()) {
                @if (isPdf()) {
                  <div class="flex flex-col items-center p-4 text-center">
                    <z-icon zType="file-text" class="h-10 w-10 text-red-500 mb-2" />
                    <span class="text-xs">PDF Preview (Click View Full)</span>
                  </div>
                } @else {
                  <img
                    [src]="previewUrl()"
                    alt="Document Preview"
                    class="max-h-60 w-full object-contain"
                  />
                }
              } @else {
                <div class="text-xs text-muted-foreground text-center p-4">
                  Preview not available.
                </div>
              }
            </div>
            <div class="flex justify-end">
              <button z-button zType="ghost" zSize="sm" class="h-7 text-xs" (click)="onViewFull()">
                View Full
              </button>
            </div>
          </div>
        </z-popover>
      </ng-template>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentPreviewComponent {
  private documentsService = inject(DocumentsService);
  private destroyRef = inject(DestroyRef);

  documentId = input.required<number>();
  fileLink = input<string | null | undefined>(null);
  label = input<string>('Preview');
  zType = input<ZardButtonTypeVariants>('outline');
  zSize = input<ZardButtonSizeVariants>('sm');

  viewFull = output<void>();

  isLoading = signal(false);
  previewUrl = signal<string | null>(null);

  protected readonly fileName = computed(() => this.fileLink()?.split('/').pop() || 'Document');
  protected readonly isPdf = computed(
    () => this.fileLink()?.toLowerCase().endsWith('.pdf') || false,
  );

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.cleanup();
    });
  }

  protected onPopoverToggle(visible: boolean): void {
    if (visible && !this.previewUrl() && !this.isLoading()) {
      this.loadPreview();
    }
    // We don't cleanup immediately on hide to avoid flickering if reopened,
    // but we could if memory is a concern. The destroyRef handles cleanup.
  }

  protected onViewFull(): void {
    this.viewFull.emit();
  }

  private loadPreview(): void {
    this.isLoading.set(true);
    this.documentsService.downloadDocumentFile(this.documentId()).subscribe({
      next: (blob) => {
        this.cleanup();
        const url = URL.createObjectURL(blob);
        this.previewUrl.set(url);
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.previewUrl.set(null);
      },
    });
  }

  private cleanup(): void {
    const url = this.previewUrl();
    if (url && url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
    this.previewUrl.set(null);
  }
}
