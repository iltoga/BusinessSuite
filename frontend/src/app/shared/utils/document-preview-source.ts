export type DocumentPreviewType = 'image' | 'pdf' | 'unknown';

export interface ExistingDocumentPreviewInput {
  thumbnailLink?: string | null;
  fileLink?: string | null;
}

export interface ExistingDocumentPreviewOptions {
  preferOriginalForPdf?: boolean;
}

export interface DocumentPreviewResult {
  url: string | null;
  type: DocumentPreviewType;
}

interface ObjectUrlFactory {
  createObjectUrl: (file: File) => string;
}

const IMAGE_EXTENSIONS = ['png', 'jpg', 'jpeg', 'webp', 'gif', 'bmp', 'avif', 'svg'];
const URL_FILENAME_QUERY_KEYS = ['filename', 'file_name', 'file', 'name', 'download'];

function stripUrlDecorators(url: string): string {
  return (url || '').toLowerCase().split('?')[0]?.split('#')[0] ?? '';
}

function decodeSafely(value: string): string {
  try {
    return decodeURIComponent(value);
  } catch {
    return value;
  }
}

function inferTypeFromCandidate(value: string): DocumentPreviewType {
  const normalized = (value || '').toLowerCase();
  if (normalized.endsWith('.pdf')) {
    return 'pdf';
  }
  const imagePattern = new RegExp(`\\.(${IMAGE_EXTENSIONS.join('|')})$`, 'i');
  if (imagePattern.test(normalized)) {
    return 'image';
  }
  return 'unknown';
}

export function inferPreviewTypeFromUrl(url?: string | null): DocumentPreviewType {
  if (!url) {
    return 'unknown';
  }

  const trimmed = url.trim();
  const lowerRaw = trimmed.toLowerCase();
  if (lowerRaw.startsWith('data:application/pdf')) {
    return 'pdf';
  }
  if (lowerRaw.startsWith('data:image/')) {
    return 'image';
  }

  const fromDecorated = inferTypeFromCandidate(stripUrlDecorators(trimmed));
  if (fromDecorated !== 'unknown') {
    return fromDecorated;
  }

  try {
    const parsed = new URL(trimmed);
    const pathSegment = decodeSafely(parsed.pathname.split('/').filter(Boolean).pop() ?? '');
    const fromPath = inferTypeFromCandidate(pathSegment);
    if (fromPath !== 'unknown') {
      return fromPath;
    }

    for (const key of URL_FILENAME_QUERY_KEYS) {
      const value = parsed.searchParams.get(key);
      if (!value) {
        continue;
      }
      const fromParam = inferTypeFromCandidate(decodeSafely(value));
      if (fromParam !== 'unknown') {
        return fromParam;
      }
    }
  } catch {
    // Non-standard URL; keep unknown.
  }

  return 'unknown';
}

export function buildExistingDocumentPreview(
  input: ExistingDocumentPreviewInput,
  options: ExistingDocumentPreviewOptions = {},
): DocumentPreviewResult {
  const preferOriginalForPdf = options.preferOriginalForPdf ?? true;
  const originalUrl = input.fileLink ?? null;
  const originalType = inferPreviewTypeFromUrl(originalUrl);
  if (originalUrl && originalType === 'pdf' && preferOriginalForPdf) {
    return { url: originalUrl, type: 'pdf' };
  }

  const thumbnailUrl = input.thumbnailLink ?? null;
  const thumbnailType = inferPreviewTypeFromUrl(thumbnailUrl);
  if (thumbnailUrl && thumbnailType === 'image') {
    return { url: thumbnailUrl, type: 'image' };
  }

  if (originalUrl && originalType !== 'unknown') {
    return { url: originalUrl, type: originalType };
  }

  return { url: null, type: 'unknown' };
}

export function buildLocalFilePreview(
  file: File,
  factory: ObjectUrlFactory = { createObjectUrl: (value) => URL.createObjectURL(value) },
): DocumentPreviewResult {
  const mime = (file.type || '').toLowerCase();
  const lowerName = (file.name || '').toLowerCase();

  if (mime.startsWith('image/') || IMAGE_EXTENSIONS.some((ext) => lowerName.endsWith(`.${ext}`))) {
    return { url: factory.createObjectUrl(file), type: 'image' };
  }

  if (mime === 'application/pdf' || lowerName.endsWith('.pdf')) {
    return { url: factory.createObjectUrl(file), type: 'pdf' };
  }

  return { url: null, type: 'unknown' };
}
