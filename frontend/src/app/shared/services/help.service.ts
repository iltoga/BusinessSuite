import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

export interface HelpLink {
  label: string;
  url: string;
}

export interface HelpContext {
  id?: string;
  briefExplanation?: string;
  details?: string;
  contentUrl?: string;
}

@Injectable({ providedIn: 'root' })
export class HelpService {
  private readonly http = inject(HttpClient);
  private readonly _visible = signal(false);
  readonly visible = this._visible.asReadonly();

  // Cheatsheet visibility (dedicated global hotkeys drawer)
  private readonly _cheatsheetVisible = signal(false);
  readonly cheatsheetVisible = this._cheatsheetVisible.asReadonly();

  private readonly _context = signal<HelpContext | null>(null);
  readonly context = this._context.asReadonly();

  private readonly _helpContent = signal<string | null>(null);
  readonly helpContent = this._helpContent.asReadonly();

  private readonly _isLoading = signal(false);
  readonly isLoading = this._isLoading.asReadonly();

  // Simple registry for help contexts by id or path prefix
  private readonly registry = new Map<string, HelpContext>([
    ['/', { id: '/', contentUrl: '/help/dashboard/index.md' }],
    ['/customers', { id: '/customers', contentUrl: '/help/customers/list.md' }],
    ['/customers/new', { id: '/customers/new', contentUrl: '/help/customers/new.md' }],
    ['/customers/', { id: '/customers/', contentUrl: '/help/customers/detail.md' }],
    [
      '/customers/bulk-delete',
      { id: '/customers/bulk-delete', contentUrl: '/help/customers/bulk-delete.md' },
    ],
    ['/applications', { id: '/applications', contentUrl: '/help/applications/list.md' }],
    ['/applications/new', { id: '/applications/new', contentUrl: '/help/applications/new.md' }],
    ['/applications/', { id: '/applications/', contentUrl: '/help/applications/detail.md' }],
    [
      '/applications/search',
      { id: '/applications/search', contentUrl: '/help/applications/search.md' },
    ],
    [
      '/applications/bulk-delete',
      { id: '/applications/bulk-delete', contentUrl: '/help/applications/bulk-delete.md' },
    ],
    ['/products', { id: '/products', contentUrl: '/help/products/list.md' }],
    ['/products/new', { id: '/products/new', contentUrl: '/help/products/new.md' }],
    ['/products/', { id: '/products/', contentUrl: '/help/products/detail.md' }],
    ['/products/search', { id: '/products/search', contentUrl: '/help/products/search.md' }],
    [
      '/products/bulk-delete',
      { id: '/products/bulk-delete', contentUrl: '/help/products/bulk-delete.md' },
    ],
    ['/invoices', { id: '/invoices', contentUrl: '/help/invoices/list.md' }],
    ['/invoices/new', { id: '/invoices/new', contentUrl: '/help/invoices/new.md' }],
    ['/invoices/import', { id: '/invoices/import', contentUrl: '/help/invoices/import.md' }],
    ['/invoices/', { id: '/invoices/', contentUrl: '/help/invoices/detail.md' }],
    ['/invoices/search', { id: '/invoices/search', contentUrl: '/help/invoices/search.md' }],
    [
      '/invoices/bulk-delete',
      { id: '/invoices/bulk-delete', contentUrl: '/help/invoices/bulk-delete.md' },
    ],
    [
      '/letters/surat-permohonan',
      { id: '/letters/surat-permohonan', contentUrl: '/help/letters/surat-permohonan.md' },
    ],
    ['/admin/systemcosts', { id: '/admin/systemcosts', contentUrl: '/help/admin/system-costs.md' }],
    ['/profile', { id: '/profile', contentUrl: '/help/profile/index.md' }],
  ]);

  private readonly _openCount = signal(0);
  readonly openCount = this._openCount.asReadonly();

  constructor(private router: Router) {
    // Update help context automatically on navigation
    this.router.events.pipe(filter((e) => e instanceof NavigationEnd)).subscribe((e) => {
      const nav = e as NavigationEnd;
      this.setContextForPath(nav.urlAfterRedirects);
    });
  }

  open() {
    // Only increment when transitioning from closed -> open
    if (!this._visible()) {
      this._openCount.update((c) => c + 1);
      this.reportOpenEvent();
    }

    this._visible.set(true);
  }

  close() {
    this._visible.set(false);
  }

  toggle() {
    // Increment when toggling to open
    this._visible.update((v) => {
      const next = !v;
      if (next) {
        this._openCount.update((c) => c + 1);
        this.reportOpenEvent();
      }
      return next;
    });
  }

  openCheatsheet() {
    if (!this._cheatsheetVisible()) {
      this._cheatsheetVisible.set(true);
    }
  }

  closeCheatsheet() {
    this._cheatsheetVisible.set(false);
  }

  toggleCheatsheet() {
    this._cheatsheetVisible.update((v) => !v);
  }

  setContext(ctx: HelpContext) {
    this._context.set(ctx);

    if (ctx.contentUrl) {
      this._isLoading.set(true);
      this.http.get(ctx.contentUrl, { responseType: 'text' }).subscribe({
        next: (content) => {
          this._helpContent.set(content);
          this._isLoading.set(false);
        },
        error: (err) => {
          if (!this.isTokenExpiredError(err)) {
            console.error('Failed to load help content', err);
            this._helpContent.set('Failed to load help content.');
          } else {
            // Expired auth token is handled globally via redirect to /login.
            // Avoid noisy console errors from background help content fetches.
            this._helpContent.set(null);
          }
          this._isLoading.set(false);
        },
      });
    } else {
      this._helpContent.set(null);
    }
  }

  register(id: string, ctx: HelpContext) {
    this.registry.set(id, ctx);
  }

  setContextById(id: string) {
    const ctx = this.registry.get(id);
    if (ctx) {
      this.setContext(ctx);
    }
  }

  setContextForPath(path: string) {
    // Match by longest prefix
    let match: HelpContext | null = null;
    let matchLen = -1;
    for (const [id, ctx] of this.registry.entries()) {
      if (path === id && id.length > matchLen) {
        match = ctx;
        matchLen = id.length;
      } else if (path.startsWith(id) && id.length > matchLen) {
        match = ctx;
        matchLen = id.length;
      }
    }

    if (match) {
      this.setContext(match);
    } else {
      // default fallback
      this.setContext({
        briefExplanation: 'Contextual help for this page is not available.',
      });
    }
  }

  private reportOpenEvent() {
    // Simple telemetry hook: increment local counter and attempt to send to global analytics
    try {
      const w: any = window as any;
      const contextId = this._context()?.id || 'unknown';
      const totalOpens = this._openCount();
      console.info(
        `[HelpService] Help drawer opened context=${contextId} open_count=${totalOpens}`,
      );

      // Google Analytics / gtag
      if (typeof w.gtag === 'function') {
        w.gtag('event', 'help_open', {
          method: 'F1_or_button',
          context: contextId,
          open_count: totalOpens,
        });
        return;
      }

      // Generic analytics object (custom)
      if (w.analytics && typeof w.analytics.track === 'function') {
        w.analytics.track('help_open', { context: contextId, open_count: totalOpens });
        return;
      }

      // Mixpanel
      if (w.mixpanel && typeof w.mixpanel.track === 'function') {
        w.mixpanel.track('help_open', { context: contextId, open_count: totalOpens });
        return;
      }
    } catch (err) {
      // swallow telemetry errors; not critical
      // console.debug('Help telemetry failed', err);
    }
  }

  private isTokenExpiredError(err: unknown): boolean {
    return err instanceof Error && err.message === 'Token expired';
  }
}
