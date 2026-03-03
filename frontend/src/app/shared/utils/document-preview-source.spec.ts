import { describe, expect, it } from 'vitest';

import {
  buildExistingDocumentPreview,
  buildLocalFilePreview,
  inferPreviewTypeFromUrl,
} from './document-preview-source';

describe('document-preview-source', () => {
  it('prefers original pdf when available for existing documents', () => {
    const preview = buildExistingDocumentPreview({
      thumbnailLink: 'https://cdn.example.com/docs/thumbnails/document_1.jpg',
      fileLink: 'https://cdn.example.com/docs/passport.pdf',
    });

    expect(preview).toEqual({
      url: 'https://cdn.example.com/docs/passport.pdf',
      type: 'pdf',
    });
  });

  it('can prefer thumbnail even when original is pdf', () => {
    const preview = buildExistingDocumentPreview(
      {
        thumbnailLink: 'https://cdn.example.com/docs/thumbnails/document_1.jpg',
        fileLink: 'https://cdn.example.com/docs/passport.pdf',
      },
      { preferOriginalForPdf: false },
    );

    expect(preview).toEqual({
      url: 'https://cdn.example.com/docs/thumbnails/document_1.jpg',
      type: 'image',
    });
  });

  it('falls back to original file when thumbnail is missing', () => {
    const preview = buildExistingDocumentPreview({
      thumbnailLink: null,
      fileLink: 'https://cdn.example.com/docs/passport.pdf?token=abc123',
    });

    expect(preview).toEqual({
      url: 'https://cdn.example.com/docs/passport.pdf?token=abc123',
      type: 'pdf',
    });
  });

  it('infers local image file preview', () => {
    const file = new File([new Uint8Array([1, 2, 3])], 'avatar.png', {
      type: 'image/png',
    });
    const preview = buildLocalFilePreview(file, {
      createObjectUrl: () => 'blob:image-preview',
    });

    expect(preview).toEqual({
      url: 'blob:image-preview',
      type: 'image',
    });
  });

  it('infers local pdf file preview', () => {
    const file = new File([new Uint8Array([1, 2, 3])], 'passport.pdf', {
      type: 'application/pdf',
    });
    const preview = buildLocalFilePreview(file, {
      createObjectUrl: () => 'blob:pdf-preview',
    });

    expect(preview).toEqual({
      url: 'blob:pdf-preview',
      type: 'pdf',
    });
  });

  it('returns unknown for unsupported urls', () => {
    expect(inferPreviewTypeFromUrl('https://cdn.example.com/file.bin')).toBe('unknown');
  });

  it('infers file type from encoded path segments', () => {
    expect(
      inferPreviewTypeFromUrl('https://cdn.example.com/documents/passport%2Epdf?token=abc123'),
    ).toBe('pdf');
  });

  it('infers file type from query filename hints', () => {
    expect(
      inferPreviewTypeFromUrl('https://cdn.example.com/signed-url?filename=ktp_sponsor.jpeg'),
    ).toBe('image');
  });

  it('infers file type from data urls', () => {
    expect(inferPreviewTypeFromUrl('data:application/pdf;base64,AAAA')).toBe('pdf');
    expect(inferPreviewTypeFromUrl('data:image/png;base64,BBBB')).toBe('image');
  });
});
