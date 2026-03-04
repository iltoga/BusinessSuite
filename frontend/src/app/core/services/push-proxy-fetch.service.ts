import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class PushProxyFetchService {
  private patchDepth = 0;
  private originalFetch: typeof window.fetch | null = null;

  async runWithGoogleApisProxy<T>(runner: () => Promise<T>): Promise<T> {
    if (typeof window === 'undefined' || typeof window.fetch !== 'function') {
      return runner();
    }

    this.installScopedProxy();
    try {
      return await runner();
    } finally {
      this.uninstallScopedProxy();
    }
  }

  private installScopedProxy(): void {
    if (this.patchDepth === 0) {
      this.originalFetch = window.fetch.bind(window);
      const baseFetch = this.originalFetch;
      window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> =>
        this.interceptGoogleApisFetch(baseFetch, input, init);
    }
    this.patchDepth += 1;
  }

  private uninstallScopedProxy(): void {
    if (this.patchDepth <= 0) {
      return;
    }
    this.patchDepth -= 1;
    if (this.patchDepth === 0 && this.originalFetch) {
      window.fetch = this.originalFetch;
      this.originalFetch = null;
    }
  }

  private resolveUrl(input: RequestInfo | URL): string {
    if (typeof input === 'string') {
      return input;
    }
    if (input instanceof URL) {
      return input.href;
    }
    return input.url;
  }

  private extractFetchHeaders(input: RequestInfo | URL, init?: RequestInit): Headers {
    const result = new Headers();
    if (input instanceof Request) {
      input.headers.forEach((value, key) => result.set(key, value));
    }
    if (init?.headers) {
      const extra =
        init.headers instanceof Headers
          ? init.headers
          : new Headers(init.headers as Record<string, string>);
      extra.forEach((value, key) => result.set(key, value));
    }
    return result;
  }

  private async resolveBody(
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<BodyInit | null | undefined> {
    if (init?.body !== undefined) {
      return init.body;
    }
    if (input instanceof Request) {
      return input.clone().text();
    }
    return undefined;
  }

  private async interceptGoogleApisFetch(
    originalFetch: typeof window.fetch,
    input: RequestInfo | URL,
    init?: RequestInit,
  ): Promise<Response> {
    const url = this.resolveUrl(input);
    if (!url.includes('fcmregistrations.googleapis.com') && !url.includes('firebaseinstallations.googleapis.com')) {
      return originalFetch(input, init);
    }

    const origHeaders = this.extractFetchHeaders(input, init);
    const djangoToken = localStorage.getItem('auth_token') || '';
    const body = await this.resolveBody(input, init);

    if (url.includes('fcmregistrations.googleapis.com')) {
      const fisAuth =
        origHeaders.get('x-goog-firebase-installations-auth') ||
        origHeaders.get('Authorization') ||
        '';
      const apiKey = origHeaders.get('x-goog-api-key') || '';

      return originalFetch('/api/push-notifications/fcm-register-proxy/', {
        method: 'POST',
        body,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${djangoToken}`,
          'X-FCM-Auth': fisAuth,
          'X-Goog-Api-Key': apiKey,
        },
      });
    }

    const match = url.match(/firebaseinstallations\.googleapis\.com\/v1\/projects\/[^/]+\/(.*)/);
    const pathSuffix = match ? match[1] : '';
    const firebaseAuth =
      origHeaders.get('x-goog-firebase-installations-auth') ||
      origHeaders.get('Authorization') ||
      '';
    const apiKey = origHeaders.get('x-goog-api-key') || '';

    return originalFetch('/api/push-notifications/firebase-install-proxy/', {
      method: 'POST',
      body,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${djangoToken}`,
        'X-Firebase-Auth': firebaseAuth,
        'X-Firebase-Path': pathSuffix,
        'X-Goog-Api-Key': apiKey,
      },
    });
  }
}
