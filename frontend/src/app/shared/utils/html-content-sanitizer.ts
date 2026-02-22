import { SecurityContext } from '@angular/core';
import { DomSanitizer } from '@angular/platform-browser';

export function sanitizeUntrustedHtml(value: unknown, sanitizer: DomSanitizer): string {
  if (typeof value !== 'string' || value.length === 0) {
    return '';
  }

  return sanitizer.sanitize(SecurityContext.HTML, value) ?? '';
}
