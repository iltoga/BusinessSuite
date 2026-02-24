import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  computed,
  input,
  output,
  signal,
  viewChild,
} from '@angular/core';

import { ZardButtonComponent } from '@/shared/components/button';

export interface SelectedFile {
  file: File;
  name: string;
  size: number;
  type: string;
}

@Component({
  selector: 'app-multi-file-upload',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent],
  templateUrl: './multi-file-upload.component.html',
  styleUrls: ['./multi-file-upload.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MultiFileUploadComponent {
  accept = input<string>('image/*,.pdf');
  disabled = input<boolean>(false);
  maxFiles = input<number>(20);
  label = input<string>('Upload Documents');
  helperText = input<string>(
    'Drag and drop files here, or click to browse. Multiple files supported.',
  );

  filesSelected = output<File[]>();
  cleared = output<void>();

  private readonly fileInput = viewChild.required<ElementRef<HTMLInputElement>>('fileInput');
  readonly isDragging = signal(false);
  readonly selectedFiles = signal<SelectedFile[]>([]);

  readonly hasFiles = computed(() => this.selectedFiles().length > 0);
  readonly fileCount = computed(() => this.selectedFiles().length);
  readonly totalSize = computed(() => {
    const bytes = this.selectedFiles().reduce((sum, f) => sum + f.size, 0);
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  });

  onBrowseClick(): void {
    if (!this.disabled()) {
      this.fileInput().nativeElement.click();
    }
  }

  onFileChange(event: Event): void {
    const input = event.target as HTMLInputElement;
    if (input.files && input.files.length > 0) {
      this.addFiles(Array.from(input.files));
      input.value = '';
    }
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging.set(false);

    if (this.disabled()) return;

    const files = event.dataTransfer?.files;
    if (files && files.length > 0) {
      this.addFiles(Array.from(files));
    }
  }

  onDragOver(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    if (!this.disabled()) {
      this.isDragging.set(true);
    }
  }

  onDragLeave(event: DragEvent): void {
    event.preventDefault();
    event.stopPropagation();
    this.isDragging.set(false);
  }

  removeFile(index: number): void {
    const files = [...this.selectedFiles()];
    files.splice(index, 1);
    this.selectedFiles.set(files);
    this.emitFiles();
  }

  clearAll(): void {
    this.selectedFiles.set([]);
    this.cleared.emit();
  }

  private addFiles(files: File[]): void {
    const current = this.selectedFiles();
    const remaining = this.maxFiles() - current.length;
    const toAdd = files.slice(0, Math.max(0, remaining));

    const newSelected: SelectedFile[] = toAdd.map((file) => ({
      file,
      name: file.name,
      size: file.size,
      type: file.type,
    }));

    this.selectedFiles.set([...current, ...newSelected]);
    this.emitFiles();
  }

  private emitFiles(): void {
    const files = this.selectedFiles().map((sf) => sf.file);
    if (files.length > 0) {
      this.filesSelected.emit(files);
    }
  }

  getFileIcon(type: string): string {
    if (type.startsWith('image/')) return '🖼️';
    if (type === 'application/pdf') return '📄';
    return '📎';
  }

  formatSize(bytes: number): string {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  }
}
