import { TestBed } from '@angular/core/testing';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { MultiFileUploadComponent } from './multi-file-upload.component';

describe('MultiFileUploadComponent', () => {
  let component: MultiFileUploadComponent;
  let fileInput: HTMLInputElement;

  beforeEach(() => {
    TestBed.configureTestingModule({});

    component = TestBed.runInInjectionContext(() => new MultiFileUploadComponent());
    fileInput = document.createElement('input');
    fileInput.click = vi.fn();
    Object.defineProperty(component as any, 'fileInput', {
      value: () => ({ nativeElement: fileInput }),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('opens the file picker when browsing is allowed', () => {
    component.onBrowseClick();

    expect(fileInput.click).toHaveBeenCalled();
  });

  it('adds files from change events and tracks totals', () => {
    const fileA = new File(['a'], 'a.txt', { type: 'text/plain' });
    const fileB = new File(['bb'], 'b.pdf', { type: 'application/pdf' });

    component.onFileChange({
      target: {
        files: [fileA, fileB],
        value: 'selected',
      },
    } as unknown as Event);

    expect(component.hasFiles()).toBe(true);
    expect(component.fileCount()).toBe(2);
    expect(component.totalSize()).toBe('3 B');
    expect(component.selectedFiles().map((item) => item.name)).toEqual(['a.txt', 'b.pdf']);
  });

  it('removes files and clears the list', () => {
    const fileA = new File(['a'], 'a.txt', { type: 'text/plain' });
    const fileB = new File(['bb'], 'b.pdf', { type: 'application/pdf' });

    component.onFileChange({
      target: {
        files: [fileA, fileB],
        value: 'selected',
      },
    } as unknown as Event);

    component.removeFile(0);
    expect(component.selectedFiles().map((item) => item.name)).toEqual(['b.pdf']);

    component.clearAll();
    expect(component.selectedFiles()).toEqual([]);
    expect(component.hasFiles()).toBe(false);
  });

  it('formats sizes and file icons consistently', () => {
    expect(component.getFileIcon('image/png')).toBe('🖼️');
    expect(component.getFileIcon('application/pdf')).toBe('📄');
    expect(component.getFileIcon('text/plain')).toBe('📎');
    expect(component.formatSize(1024)).toBe('1.0 KB');
    expect(component.formatSize(1024 * 1024)).toBe('1.0 MB');
  });
});
