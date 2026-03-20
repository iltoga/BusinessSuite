import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { ConfigService } from '@/core/services/config.service';
import { FileUploadComponent } from './file-upload.component';

describe('FileUploadComponent', () => {
  let component: FileUploadComponent;
  let fileInput: HTMLInputElement;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        { provide: ConfigService, useValue: { settings: { DEBUG: true } } },
        {
          provide: DomSanitizer,
          useValue: { bypassSecurityTrustResourceUrl: vi.fn((value: string) => value) },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new FileUploadComponent());
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

  it('does not open the file picker when disabled', () => {
    Object.assign(component as any, { disabled: () => true });

    component.onBrowseClick();

    expect(fileInput.click).not.toHaveBeenCalled();
  });

  it('emits the first selected file from a change event', () => {
    const emitSpy = vi.spyOn((component as any).fileSelected, 'emit');
    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });

    component.onFileChange({
      target: {
        files: [file],
      },
    } as unknown as Event);

    expect(emitSpy).toHaveBeenCalledWith(file);
  });

  it('emits dropped files and resets drag state', () => {
    const emitSpy = vi.spyOn((component as any).fileSelected, 'emit');
    const file = new File(['hello'], 'hello.txt', { type: 'text/plain' });

    component.isDragging.set(true);
    component.onDrop({
      preventDefault: vi.fn(),
      dataTransfer: { files: [file] },
    } as unknown as DragEvent);

    expect(emitSpy).toHaveBeenCalledWith(file);
    expect(component.isDragging()).toBe(false);
  });

  it('clears the selection and emits cleared', () => {
    const emitSpy = vi.spyOn((component as any).cleared, 'emit');
    fileInput.value = 'selected.txt';

    component.clearSelection();

    expect(fileInput.value).toBe('');
    expect(emitSpy).toHaveBeenCalled();
  });

  it('detects previews and debug controls', () => {
    Object.assign(component as any, {
      previewUrl: () => 'data:image/png;base64,abc',
      previewType: () => 'image',
      disablePreview: () => false,
      fileName: () => 'image.png',
    });

    expect(component.showDebugControls()).toBe(true);
    expect(component.sanitizedPreview()).toBeTruthy();
    expect(component.hasImagePreview()).toBe(true);
    expect(component.showPreviewContainer()).toBe(true);
  });
});
