import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';

@Injectable({
  providedIn: 'root',
})
export class LoggerService {
  private platformId = inject(PLATFORM_ID);
  private isBrowser = isPlatformBrowser(this.platformId);

  private originalConsole = {
    log: console.log,
    info: console.info,
    warn: console.warn,
    error: console.error,
    debug: console.debug,
  };

  /**
   * Initializes the logger by overriding the global console object in the browser.
   * This ensures all console.log/warn/error calls are captured and sent to the server.
   */
  init() {
    if (!this.isBrowser) {
      return;
    }

    const self = this;

    // Set a flag to avoid recursive logging if anything in this service logs
    let isInternalLogging = false;

    const override = (level: 'info' | 'warn' | 'error' | 'debug' | 'log', originalFn: Function) => {
      return (...args: any[]) => {
        // Always call original console first so user sees it in their devtools
        originalFn.apply(console, args);

        if (isInternalLogging) return;

        try {
          isInternalLogging = true;
          self.sendToServer(level === 'log' ? 'info' : level, args);
        } finally {
          isInternalLogging = false;
        }
      };
    };

    (console as any).log = override('log', this.originalConsole.log);
    (console as any).info = override('info', this.originalConsole.info);
    (console as any).warn = override('warn', this.originalConsole.warn);
    (console as any).error = override('error', this.originalConsole.error);
    (console as any).debug = override('debug', this.originalConsole.debug);

    console.info(
      '[LoggerService] Console overrides initialized. Client logs will be forwarded to server.',
    );
  }

  private sendToServer(level: string, args: any[]) {
    if (!this.isBrowser) return;

    try {
      const message = args
        .map((arg) => {
          if (arg instanceof Error) {
            return `${arg.message}\n${arg.stack}`;
          }
          if (typeof arg === 'object') {
            try {
              return JSON.stringify(arg);
            } catch (e) {
              return '[Circular or Unserializable Object]';
            }
          }
          return String(arg);
        })
        .join(' ');

      const url = window.location.pathname;

      // Use fetch instead of HttpClient to bypass interceptors and avoid circular dependencies
      fetch('/api/client-logs', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ level, message, url }),
        keepalive: true,
      }).catch(() => {
        /* Fail silently to avoid infinite loops or flooding and disrupting user experience */
      });
    } catch (e) {
      /* ignore */
    }
  }
}
