/**
 * Generate a base64 nonce suitable for CSP.
 * Default 16 bytes (128 bits) as recommended by MDN.
 * Uses Web Crypto API in browser, falls back to Node's crypto when available.
 */
export function generateNonce(bytes = 16): string {
  // Browser environment: use Web Crypto API
  if (typeof window !== 'undefined' && window.crypto && (window.crypto as any).getRandomValues) {
    const array = new Uint8Array(bytes);
    (window.crypto as any).getRandomValues(array);
    let binary = '';
    for (let i = 0; i < array.length; i++) {
      binary += String.fromCharCode(array[i]);
    }
    return btoa(binary).replace(/=+$/, '');
  }

  // Node environment: require dynamically to avoid bundler errors
  try {
    // eslint-disable-next-line @typescript-eslint/no-var-requires
    // @ts-ignore
    const nodeCrypto = require('crypto');
    return nodeCrypto.randomBytes(bytes).toString('base64').replace(/=+$/, '');
  } catch (e) {
    // Last-resort fallback (not cryptographically strong)
    let s = '';
    for (let i = 0; i < bytes; i++) {
      s += String.fromCharCode(Math.floor(Math.random() * 256));
    }
    return btoa(s).replace(/=+$/, '');
  }
}

export function injectNonceToHtml(html: string, nonce: string): string {
  return html.replace(/<app(\s|>)/, `<app ngCspNonce="${nonce}"$1`);
}
