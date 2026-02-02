import { expect, it } from 'vitest';
import { generateNonce, injectNonceToHtml } from './csp';

it('generates unique nonces and reasonable length', () => {
  const set = new Set<string>();
  for (let i = 0; i < 1000; i++) {
    const n = generateNonce();
    expect(typeof n).toBe('string');
    expect(n.length).toBeGreaterThan(0);
    set.add(n);
  }
  expect(set.size).toBe(1000);
});

it('injects nonce into root app element', () => {
  const sample = '<!doctype html><html><head></head><body><app></app></body></html>';
  const nonce = 'abc123';
  const result = injectNonceToHtml(sample, nonce);
  expect(result).toContain('<app ngCspNonce="abc123">');
});
