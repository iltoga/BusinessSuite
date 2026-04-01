import { isPlatformBrowser } from '@angular/common';
import { inject, Injectable, PLATFORM_ID, signal } from '@angular/core';

/**
 * Configuration for a single pending-field polling channel.
 */
export interface PendingFieldPollerConfig {
  /** Maximum number of retry attempts before giving up. */
  maxAttempts: number;
  /** Interval in milliseconds between retries. */
  intervalMs: number;
}

/**
 * A single polling channel that retries `loadApplication(id, { silent: true })`
 * until a condition is met or max attempts are exhausted.
 */
export class PendingFieldPoller {
  readonly enabled = signal(false);

  private attempts = 0;
  private timer: number | null = null;
  private readonly isBrowser: boolean;
  private readonly maxAttempts: number;
  private readonly intervalMs: number;
  private reloadFn: ((id: number) => void) | null = null;

  constructor(config: PendingFieldPollerConfig, isBrowser: boolean) {
    this.maxAttempts = config.maxAttempts;
    this.intervalMs = config.intervalMs;
    this.isBrowser = isBrowser;
  }

  /** Bind the reload callback (called once during service init). */
  bindReload(fn: (id: number) => void): void {
    this.reloadFn = fn;
  }

  /** Start polling. Typically called in ngOnInit from navigation state. */
  start(): void {
    this.enabled.set(true);
    this.attempts = 0;
  }

  /**
   * Called after each application reload. If `shouldContinue` returns false,
   * polling stops. Otherwise, schedules another retry if under the max.
   */
  handleRefresh(id: number, shouldContinue: boolean): void {
    if (!this.enabled()) {
      return;
    }

    if (!shouldContinue) {
      this.clear();
      return;
    }

    if (this.attempts >= this.maxAttempts) {
      this.clear();
      return;
    }

    this.schedule(id);
  }

  /** Schedule a retry on error (silent reload path). */
  scheduleRetry(id: number): void {
    if (this.enabled()) {
      this.schedule(id);
    }
  }

  /** Check if this poller is still actively polling. */
  isActive(): boolean {
    return this.enabled();
  }

  /** Stop polling and reset state. */
  clear(): void {
    this.enabled.set(false);
    this.attempts = 0;
    if (this.timer && this.isBrowser) {
      window.clearTimeout(this.timer);
    }
    this.timer = null;
  }

  private schedule(id: number): void {
    if (!this.isBrowser || !this.enabled()) {
      this.clear();
      return;
    }

    if (this.timer) {
      window.clearTimeout(this.timer);
    }

    this.timer = window.setTimeout(() => {
      this.timer = null;
      this.attempts += 1;
      this.reloadFn?.(id);
    }, this.intervalMs);
  }
}

/**
 * Manages all pending-field polling channels for the application detail view.
 * Provided at component level — each detail component gets its own instance.
 *
 * Consolidates the passport-refresh and due-date-refresh polling into a
 * single DRY abstraction.
 */
@Injectable()
export class PendingFieldRefreshService {
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));

  readonly passport = new PendingFieldPoller({ maxAttempts: 10, intervalMs: 1200 }, this.isBrowser);

  readonly dueDate = new PendingFieldPoller({ maxAttempts: 8, intervalMs: 400 }, this.isBrowser);

  /** Bind the reload callback for all pollers. */
  init(reloadFn: (id: number) => void): void {
    this.passport.bindReload(reloadFn);
    this.dueDate.bindReload(reloadFn);
  }

  /** Stop all pollers and clear timers. */
  destroy(): void {
    this.passport.clear();
    this.dueDate.clear();
  }
}
