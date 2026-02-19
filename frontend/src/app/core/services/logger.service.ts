import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';
import { AuthService } from '@/core/services/auth.service';

@Injectable({
  providedIn: 'root',
})
export class LoggerService {
  private platformId = inject(PLATFORM_ID);
  private authService = inject(AuthService);
  private isBrowser = isPlatformBrowser(this.platformId);
  private readonly clientLogEndpoint = '/_observability/client-logs';
  private readonly ignoredPatterns = [
    'trackMicrotaskNotificationForDebugging',
    '_ChangeDetectionSchedulerImpl.notify',
    'markAncestorsForTraversal',
    'signalSetFn',
    '/_observability/client-logs',
    '[LoggerService] Console overrides initialized.',
    'Angular is running in development mode.',
    'Angular hydrated ',
    'NG0912: Component ID generation collision detected.',
    '[vite] server connection lost. Polling for restart...',
    '[ChromeTransport] chromePort disconnected',
    'Failed to connect to MetaMask',
    'chrome-extension://',
  ];
  private readonly dedupWindowMs = 3000;
  private readonly dedupCache = new Map<string, number>();

  private originalConsole: Pick<Console, 'log' | 'info' | 'warn' | 'error' | 'debug'> = {
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

    const globalLoggerState = (window as any).__revisLoggerState as
      | {
          initialized: boolean;
          originalConsole?: Pick<Console, 'log' | 'info' | 'warn' | 'error' | 'debug'>;
        }
      | undefined;

    if (globalLoggerState?.initialized) {
      return;
    }

    if (globalLoggerState?.originalConsole) {
      this.originalConsole = globalLoggerState.originalConsole;
    } else {
      (window as any).__revisLoggerState = {
        initialized: false,
        originalConsole: this.originalConsole,
      };
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
    (window as any).__revisLoggerState = {
      initialized: true,
      originalConsole: this.originalConsole,
    };

    console.info(
      '[LoggerService] Console overrides initialized. Client logs will be forwarded to server.',
    );
  }

  private sendToServer(level: string, args: any[]) {
    if (!this.isBrowser) return;
    if (this.shouldSkipForwarding(level, args)) return;

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
      const username = this.getCurrentUsername();
      const payload = JSON.stringify({ level, message, url, username });

      // Prefer sendBeacon to avoid Promise/microtask feedback loops in dev-mode tracing.
      if (navigator.sendBeacon) {
        const blob = new Blob([payload], { type: 'application/json' });
        navigator.sendBeacon(this.clientLogEndpoint, blob);
        return;
      }

      // Fallback for browsers without sendBeacon support.
      fetch(this.clientLogEndpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: payload,
        keepalive: true,
      }).catch(() => {
        /* Fail silently to avoid flooding and disrupting user experience */
      });
    } catch (e) {
      /* ignore */
    }
  }

  private getCurrentUsername(): string | null {
    const claims = this.authService.claims();
    const usernameCandidate = claims?.fullName || claims?.sub || claims?.email || null;
    if (!usernameCandidate) {
      return null;
    }

    const trimmed = String(usernameCandidate).trim();
    return trimmed ? trimmed.slice(0, 120) : null;
  }

  private shouldSkipForwarding(level: string, args: any[]): boolean {
    if (level === 'debug') {
      return true;
    }

    const combined = args
      .map((arg) => {
        if (arg instanceof Error) {
          return `${arg.message}\n${arg.stack ?? ''}`;
        }
        return typeof arg === 'string' ? arg : '';
      })
      .join(' ');

    if (this.ignoredPatterns.some((pattern) => combined.includes(pattern))) {
      return true;
    }

    // Drop repeated identical lines in a short window to reduce observability noise.
    const key = `${level}|${combined}`.slice(0, 1024);
    const now = Date.now();
    const lastSeen = this.dedupCache.get(key);
    this.dedupCache.set(key, now);

    // Opportunistic cleanup to prevent unbounded growth.
    if (this.dedupCache.size > 500) {
      for (const [cacheKey, seenAt] of this.dedupCache.entries()) {
        if (now - seenAt > this.dedupWindowMs * 5) {
          this.dedupCache.delete(cacheKey);
        }
      }
    }

    return typeof lastSeen === 'number' && now - lastSeen < this.dedupWindowMs;
  }
}
