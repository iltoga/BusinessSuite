import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  inject,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';

import { ZardButtonComponent } from '@/shared/components/button';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { mergeClasses } from '@/shared/utils/merge-classes';
import { sanitizeResourceUrl } from '@/shared/utils/resource-url-sanitizer';

@Component({
  selector: 'app-file-upload',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ImageMagnifierComponent],
  templateUrl: './file-upload.component.html',
  styleUrls: ['./file-upload.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FileUploadComponent {
  label = input<string>('Upload file');
  accept = input<string>('*/*');
  disabled = input<boolean>(false);
  progress = input<number | null | undefined>(null);
  fileName = input<string | null | undefined>(null);
  helperText = input<string | null | undefined>(null);
  previewUrl = input<string | null | undefined>(null);
  previewType = input<'image' | 'pdf' | 'unknown'>('unknown');
  previewLoading = input<boolean>(false);
  previewHeight = input<string>('40rem');
  previewWidth = input<string | null>(null);
  magnifierEnabledByDefault = input<boolean>(false);
  showMagnifierToggle = input<boolean>(true);

  fileSelected = output<File>();
  cleared = output<void>();

  private readonly sanitizer = inject(DomSanitizer);
  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');
  readonly isDragging = signal(false);

  readonly hasImagePreview = computed(
    () =>
      this.previewType() === 'image' &&
      Boolean(this.previewUrl()) &&
      Boolean(this.sanitizedPreview()),
  );
  readonly hasPdfPreview = computed(
    () => this.previewType() === 'pdf' && Boolean(this.sanitizedPreview()),
  );
  readonly showPreview = computed(() => this.hasImagePreview() || this.hasPdfPreview());
  readonly hasPreviewCandidate = computed(() => Boolean(this.fileName()) || Boolean(this.previewUrl()));
  readonly showPreviewContainer = computed(
    () => this.previewLoading() || this.showPreview() || this.hasPreviewCandidate(),
  );
  readonly showPreviewSkeleton = computed(() => this.previewLoading());

  readonly sanitizedPreview = computed<SafeResourceUrl | null>(() => {
    const url = this.previewUrl();
    if (!url) {
      return null;
    }
    return sanitizeResourceUrl(url, this.sanitizer);
  });

  onBrowseClick(): void {
    if (this.disabled()) {
      return;
    }
    this.fileInput().nativeElement.click();
  }

  onFileChange(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    const file = target?.files?.[0];
    if (!file) {
      return;
    }
    this.fileSelected.emit(file);
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    if (this.disabled()) {
      return;
    }
    const file = event.dataTransfer?.files?.[0];
    if (file) {
      this.fileSelected.emit(file);
    }
    this.isDragging.set(false);
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    if (!this.disabled()) {
      this.isDragging.set(true);
    }
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    this.isDragging.set(false);
  }

  clearSelection(): void {
    this.fileInput().nativeElement.value = '';
    this.cleared.emit();
  }

  getDropzoneClasses(): string {
    return mergeClasses(
      'flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-6 text-center transition',
      this.isDragging() && !this.disabled() ? 'border-primary bg-primary/5' : 'border-muted',
      this.disabled() ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
    );
  }
}
