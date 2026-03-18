import { signal } from '@angular/core';

import {
  ApplicationCategorizationHandler,
  buildStageMessage,
  formatCategorizationFilenames,
  truncateFilename,
} from './categorization-handler.service';

describe('ApplicationCategorizationHandler progress messaging', () => {
  const createHandler = (): ApplicationCategorizationHandler => {
    const handler = Object.create(
      ApplicationCategorizationHandler.prototype,
    ) as ApplicationCategorizationHandler;

    // Initialize signals that the handler uses internally
    (handler as any).isActive = signal(false);
    (handler as any).jobId = signal<string | null>(null);
    (handler as any).totalFiles = signal(3);
    (handler as any).processedFiles = signal(0);
    (handler as any).results = signal<any[]>([]);
    (handler as any).isComplete = signal(false);
    (handler as any).statusMessage = signal('');
    (handler as any).progressPercentOverride = signal<number | null>(null);
    (handler as any).isApplying = signal(false);
    (handler as any).files = signal<File[]>([]);
    (handler as any).lastActivitySummary = signal('');

    return handler;
  };

  it('keeps showing the active validating filename even if a generic progress event arrives', () => {
    const handler = createHandler();

    handler.handleEvent({
      type: 'file_start',
      data: { filename: 'passport-super-long-filename-image.jpg', index: 0 },
    });
    handler.handleEvent({
      type: 'file_validating',
      data: { filename: 'passport-super-long-filename-image.jpg', aiValidationEnabled: true },
    });
    handler.handleEvent({
      type: 'progress',
      data: {
        totalFiles: 3,
        processedFiles: 0,
        overallPercent: 40,
        phase: 'processing',
        message: 'Upload complete. Starting AI processing...',
      },
    });

    expect(handler.statusMessage()).toContain('Validating:');
    expect(handler.statusMessage()).toContain('passport-super-long-f');
    expect(handler.statusMessage()).toContain('.jpg');
    expect(handler.statusMessage()).not.toContain('Upload complete. Starting AI processing...');
  });

  it('aggregates multiple queued files into one informative status line', () => {
    const handler = createHandler();

    handler.handleEvent({
      type: 'file_upload_start',
      data: { filename: 'passport.jpg', index: 0 },
    });
    handler.handleEvent({
      type: 'file_upload_start',
      data: { filename: 'itk.pdf', index: 1 },
    });
    handler.handleEvent({
      type: 'file_uploaded',
      data: { filename: 'passport.jpg', index: 0 },
    });
    handler.handleEvent({
      type: 'file_uploaded',
      data: { filename: 'itk.pdf', index: 1 },
    });

    expect(handler.statusMessage()).toBe(
      'Queued 2 files: "passport.jpg", "itk.pdf" — waiting to process',
    );
  });

  it('shows file_start status with filename', () => {
    const handler = createHandler();

    handler.handleEvent({
      type: 'file_start',
      data: { filename: 'my-document.pdf', index: 1 },
    });

    // refreshStatusMessage aggregates from pipeline state; it shows "Categorizing: ..."
    expect(handler.statusMessage()).toContain('Categorizing');
    expect(handler.statusMessage()).toContain('my-document.pdf');
  });

  it('prefers lastActivitySummary over fallback when no files are in active pipeline stage', () => {
    const handler = createHandler();

    handler.handleEvent({
      type: 'file_start',
      data: { filename: 'passport.jpg', index: 0 },
    });
    handler.handleEvent({
      type: 'file_categorized',
      data: {
        filename: 'passport.jpg',
        itemId: 'item-1',
        documentType: 'Passport',
        documentTypeId: 1,
        documentId: 10,
        confidence: 0.95,
        reasoning: 'Looks like a passport',
      },
    });

    // At this point passport is in terminal state (categorized).
    // A generic progress event should NOT overwrite the meaningful activity.
    handler.handleEvent({
      type: 'progress',
      data: {
        totalFiles: 3,
        processedFiles: 1,
        overallPercent: 33,
        phase: 'processing',
      },
    });

    expect(handler.statusMessage()).toContain('Categorized:');
    expect(handler.statusMessage()).toContain('passport.jpg');
    expect(handler.statusMessage()).toContain('Passport');
  });
});

describe('truncateFilename', () => {
  it('returns short filenames unchanged', () => {
    expect(truncateFilename('short.pdf')).toBe('short.pdf');
  });

  it('truncates long filenames preserving extension', () => {
    const long = 'this-is-a-very-long-filename-that-should-be-truncated.jpg';
    const result = truncateFilename(long, 28);
    expect(result.length).toBeLessThanOrEqual(28);
    expect(result).toContain('.jpg');
    expect(result).toContain('...');
  });
});

describe('formatCategorizationFilenames', () => {
  it('deduplicates and truncates filenames', () => {
    const result = formatCategorizationFilenames(['a.pdf', 'a.pdf', 'b.pdf']);
    expect(result).toBe('"a.pdf", "b.pdf"');
  });
});

describe('buildStageMessage', () => {
  it('formats single file stage message', () => {
    const result = buildStageMessage('Uploading', ['file.pdf']);
    expect(result).toBe('Uploading: "file.pdf"...');
  });

  it('formats multiple files with count', () => {
    const result = buildStageMessage('Queued', ['a.pdf', 'b.pdf'], ' — waiting to process');
    expect(result).toBe('Queued 2 files: "a.pdf", "b.pdf" — waiting to process');
  });
});
