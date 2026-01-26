import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';
import { mergeClasses } from '@/shared/utils/merge-classes';

@Component({
  selector: 'app-file-upload',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent],
  templateUrl: './file-upload.component.html',
  styleUrls: ['./file-upload.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FileUploadComponent {
  label = input<string>('Upload file');
  accept = input<string>('*/*');
  disabled = input<boolean>(false);
  progress = input<number | null>(null);
  fileName = input<string | null>(null);
  helperText = input<string | null>(null);

  fileSelected = output<File>();
  cleared = output<void>();

  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');
  readonly isDragging = signal(false);

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
