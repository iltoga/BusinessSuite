import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';

import { sanitizeUntrustedHtml } from './html-content-sanitizer';

describe('sanitizeUntrustedHtml', () => {
  let sanitizer: DomSanitizer;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    sanitizer = TestBed.inject(DomSanitizer);
  });

  it('strips unsafe html attributes and scripts', () => {
    const value = sanitizeUntrustedHtml('<img src=x onerror=alert(1)><script>alert(1)</script><b>ok</b>', sanitizer);

    expect(value).toContain('<img');
    expect(value).toContain('<b>ok</b>');
    expect(value).not.toContain('onerror=');
    expect(value).not.toContain('<script>');
  });

  it('returns empty string for non-string values', () => {
    expect(sanitizeUntrustedHtml(null, sanitizer)).toBe('');
    expect(sanitizeUntrustedHtml({ value: 'x' }, sanitizer)).toBe('');
  });
});
