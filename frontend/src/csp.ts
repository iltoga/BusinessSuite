import crypto from 'node:crypto';

/**
 * Generate a base64 nonce suitable for CSP.
 * Default 16 bytes (128 bits) as recommended by MDN.
 */
export function generateNonce(bytes = 16): string {
  return crypto.randomBytes(bytes).toString('base64');
}

export function injectNonceToHtml(html: string, nonce: string): string {
  return html.replace(/<app(\s|>)/, `<app ngCspNonce="${nonce}"$1`);
}
