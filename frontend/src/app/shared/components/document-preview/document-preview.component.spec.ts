import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';
import { of } from 'rxjs';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { DocumentsService } from '@/core/services/documents.service';
import { DocumentPreviewComponent } from './document-preview.component';

describe('DocumentPreviewComponent', () => {
  let component: DocumentPreviewComponent;
  let documentsServiceMock: { downloadDocumentFile: ReturnType<typeof vi.fn> };
  let sanitizerMock: { bypassSecurityTrustResourceUrl: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    documentsServiceMock = {
      downloadDocumentFile: vi.fn(),
    };
    sanitizerMock = {
      bypassSecurityTrustResourceUrl: vi.fn((value: string) => `safe:${value}` as any),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: DocumentsService, useValue: documentsServiceMock },
        { provide: DomSanitizer, useValue: sanitizerMock },
      ],
    });
    component = TestBed.runInInjectionContext(() => new DocumentPreviewComponent());

    Object.assign(component as any, {
      documentId: () => 42,
      fileLink: () => 'https://example.com/document.pdf',
      thumbnailLink: () => null,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('extracts readable names and detects expiring storage URLs', () => {
    expect((component as any).extractFileName('https://example.com/path/My%20File.pdf?x=1')).toBe(
      'My File.pdf',
    );
    expect((component as any).extractFileName('')).toBe('Document');
    expect((component as any).isLikelyExpiringStorageUrl('https://example.com/file?token=abc')).toBe(
      true,
    );
  });

  it('uses a safe thumbnail image without downloading the original file', () => {
    Object.assign(component as any, {
      fileLink: () => 'https://example.com/document.docx',
      thumbnailLink: () => 'https://example.com/thumbnail.png',
    });

    (component as any).onPopoverToggle(true);

    expect(documentsServiceMock.downloadDocumentFile).not.toHaveBeenCalled();
    expect(component.previewUrl()).toBe('https://example.com/thumbnail.png');
    expect(component.previewMime()).toBe('image/png');
    expect(sanitizerMock.bypassSecurityTrustResourceUrl).toHaveBeenCalled();
  });

  it('downloads the document when no thumbnail is available', () => {
    const blob = new Blob(['img'], { type: 'image/png' });
    documentsServiceMock.downloadDocumentFile.mockReturnValue(of(blob));
    const createObjectUrlSpy = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:preview');

    (component as any).onPopoverToggle(true);

    expect(documentsServiceMock.downloadDocumentFile).toHaveBeenCalledWith(42);
    expect(createObjectUrlSpy).toHaveBeenCalledWith(blob);
    expect(component.previewUrl()).toBe('blob:preview');
    expect(component.previewBlob()).toBe(blob);
    expect(component.previewMime()).toBe('image/png');
  });

  it('emits viewFull for non-pdf documents and opens the viewer for pdfs', async () => {
    const viewFullSpy = vi.spyOn((component as any).viewFull, 'emit');
    const openViewerSpy = vi.spyOn(component as any, 'openViewer').mockResolvedValue(undefined);

    Object.assign(component as any, {
      fileLink: () => 'https://example.com/document.docx',
      previewMime: component.previewMime,
    });

    (component as any).onViewFull();
    expect(viewFullSpy).toHaveBeenCalled();

    viewFullSpy.mockClear();
    Object.assign(component as any, {
      fileLink: () => 'https://example.com/document.pdf',
    });
    component.previewBlob.set(new Blob(['pdf'], { type: 'application/pdf' }));
    component.previewMime.set('application/pdf');

    (component as any).onViewFull();
    expect(openViewerSpy).toHaveBeenCalled();
    expect(viewFullSpy).not.toHaveBeenCalled();
  });

  it('cleans up blob URLs when destroyed', () => {
    const revokeSpy = vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);
    component.previewUrl.set('blob:preview');
    component.sanitizedPreview.set('safe:preview' as any);
    component.previewMime.set('application/pdf');

    (component as any).cleanup();

    expect(revokeSpy).toHaveBeenCalledWith('blob:preview');
    expect(component.previewUrl()).toBeNull();
    expect(component.sanitizedPreview()).toBeNull();
    expect(component.previewMime()).toBeNull();
  });
});
