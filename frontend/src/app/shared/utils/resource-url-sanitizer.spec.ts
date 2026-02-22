import { TestBed } from '@angular/core/testing';
import { DomSanitizer } from '@angular/platform-browser';

import { sanitizeResourceUrl } from './resource-url-sanitizer';

describe('sanitizeResourceUrl', () => {
  let sanitizer: DomSanitizer;

  beforeEach(() => {
    TestBed.configureTestingModule({});
    sanitizer = TestBed.inject(DomSanitizer);
  });

  it('accepts blob urls', () => {
    const safe = sanitizeResourceUrl('blob:https://example.com/abc', sanitizer);
    expect(safe).not.toBeNull();
  });

  it('accepts safe data image urls', () => {
    const safe = sanitizeResourceUrl('data:image/png;base64,abc', sanitizer);
    expect(safe).not.toBeNull();
  });

  it('rejects dangerous javascript urls', () => {
    const safe = sanitizeResourceUrl('javascript:alert(1)', sanitizer);
    expect(safe).toBeNull();
  });

  it('rejects data urls with non-allowlisted mime types', () => {
    const safe = sanitizeResourceUrl('data:text/html,<script>alert(1)</script>', sanitizer);
    expect(safe).toBeNull();
  });
});
