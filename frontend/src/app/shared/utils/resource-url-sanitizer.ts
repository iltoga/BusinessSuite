import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';

const SAFE_DATA_MIME_PREFIXES = ['image/', 'application/pdf'];

function isAllowedDataUrl(raw: string): boolean {
  if (!raw.startsWith('data:')) {
    return false;
  }
  const commaIndex = raw.indexOf(',');
  if (commaIndex <= 5) {
    return false;
  }
  const metadata = raw.slice(5, commaIndex).toLowerCase();
  const mimeType = metadata.split(';', 1)[0]?.trim() ?? '';
  if (!mimeType) {
    return false;
  }
  return SAFE_DATA_MIME_PREFIXES.some((prefix) => mimeType.startsWith(prefix));
}

function isAllowedHttpUrl(raw: string): boolean {
  try {
    const parsed = new URL(raw, window.location.origin);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function sanitizeResourceUrl(
  value: string | null | undefined,
  sanitizer: DomSanitizer,
): SafeResourceUrl | null {
  const raw = value?.trim();
  if (!raw) {
    return null;
  }

  if (raw.startsWith('blob:') || isAllowedDataUrl(raw) || isAllowedHttpUrl(raw)) {
    return sanitizer.bypassSecurityTrustResourceUrl(raw);
  }

  return null;
}
