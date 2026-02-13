import { Injectable, signal } from '@angular/core';
import { NavigationEnd, Router } from '@angular/router';
import { filter } from 'rxjs/operators';

export interface HelpLink {
  label: string;
  url: string;
}

export interface HelpContext {
  id?: string;
  briefExplanation: string;
  details?: string;
}

@Injectable({ providedIn: 'root' })
export class HelpService {
  private readonly _visible = signal(false);
  readonly visible = this._visible.asReadonly();

  // Cheatsheet visibility (dedicated global hotkeys drawer)
  private readonly _cheatsheetVisible = signal(false);
  readonly cheatsheetVisible = this._cheatsheetVisible.asReadonly();

  private readonly _context = signal<HelpContext | null>(null);
  readonly context = this._context.asReadonly();

  // Simple registry for help contexts by id or path prefix
  private readonly registry = new Map<string, HelpContext>([
    [
      '/',
      {
        id: '/',
        briefExplanation:
          'The Dashboard provides an overview of the visa processing system, including quick links to key features and recent activities.',
        details:
          'Use the navigation menu to access different sections. Check the summary cards for quick stats.',
      },
    ],
    [
      '/customers',
      {
        id: '/customers',
        briefExplanation:
          'The Customers view is used to manage customer records in the visa processing system. It allows searching, viewing, editing, and creating new customers.',
        details:
          'Use the search bar to find customers by name, email, or passport. Filter by status (active/disabled). Click on a customer to view details. Use the actions menu for editing or creating applications. The table supports sorting and pagination.',
      },
    ],
    // More specific customer routes
    [
      '/customers/new',
      {
        id: '/customers/new',
        briefExplanation: 'Create a new customer record in the system.',
        details:
          'Fill in the customer details form. Required fields include name, email, and nationality. Save to add the customer.',
      },
    ],
    [
      '/customers/',
      {
        id: '/customers/',
        briefExplanation:
          'View and edit customer profile details, including personal information, applications, and invoices.',
        details:
          'Navigate through tabs to see customer info, applications, and invoices. Use edit buttons to modify details.',
      },
    ],
    [
      '/invoices',
      {
        id: '/invoices',
        briefExplanation:
          'The Invoices view allows managing invoice creation, listing, and payment tracking for customer applications.',
        details: 'View all invoices, filter by status, create new invoices, and track payments.',
      },
    ],
    [
      '/products',
      {
        id: '/products',
        briefExplanation: 'Manage the product catalog and pricing for visa services.',
        details: 'Add, edit, or remove products. Set pricing and descriptions.',
      },
    ],
    // Applications
    [
      '/applications',
      {
        id: '/applications',
        briefExplanation:
          'The Applications view lists customer applications (DocApplication). Use it to search, filter, and take bulk actions on applications.',
        details:
          'Click an application to open its detail view. Use the search bar to filter by customer, product, or notes. Use the actions menu to edit, create invoices (shortcut: i), or force-close applications.',
      },
    ],
    [
      '/applications/new',
      {
        id: '/applications/new',
        briefExplanation: 'Create a new customer application.',
        details:
          'Select a customer and product, fill document and workflow details, then save to create the application.',
      },
    ],
    // Application detail prefix
    [
      '/applications/',
      {
        id: '/applications/',
        briefExplanation:
          'View and manage one application from start to finish.',
        details:
          'Use Tasks Timeline to see each stage in order. Update only the latest task status, and the next task appears automatically. Finished tasks stay visible as history. If an application is completed or rejected, you can still create an invoice.',
      },
    ],
    // Invoices additional entries
    [
      '/invoices/new',
      {
        id: '/invoices/new',
        briefExplanation: 'Create a new invoice.',
        details:
          'Select customer and add invoice lines. You can pre-fill from an application using the create invoice action.',
      },
    ],
    [
      '/invoices/import',
      {
        id: '/invoices/import',
        briefExplanation: 'Import invoices from a CSV file.',
        details:
          'Upload a properly formatted CSV to import invoices in bulk. Check the sample CSV layout before uploading.',
      },
    ],
    [
      '/invoices/',
      {
        id: '/invoices/',
        briefExplanation: 'View and manage an invoice.',
        details:
          'Review invoice items, payments, and download or send the invoice. Add payments using the payments modal.',
      },
    ],
    // Product new / detail
    [
      '/products/new',
      {
        id: '/products/new',
        briefExplanation: 'Create a new product.',
        details:
          'Add the product code, name, price, required documents, and workflow tasks. This defines new application types for customers.',
      },
    ],
    [
      '/products/',
      {
        id: '/products/',
        briefExplanation: 'View product details, required documents, and workflow steps.',
        details:
          'Edit pricing, required documents, and workflow steps for the product. Changes affect new applications created after the update.',
      },
    ],
    // Misc pages
    [
      '/letters/surat-permohonan',
      {
        id: '/letters/surat-permohonan',
        briefExplanation: 'Generate Surat Permohonan (request letters) for applications.',
        details:
          'Choose the application and export the generated Surat Permohonan document. Customize letter content if needed.',
      },
    ],
    [
      '/profile',
      {
        id: '/profile',
        briefExplanation: 'Your user profile.',
        details: 'Update your personal details and preferences.',
      },
    ],
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
      // Google Analytics / gtag
      if (typeof w.gtag === 'function') {
        w.gtag('event', 'help_open', { method: 'F1_or_button' });
        return;
      }

      // Generic analytics object (custom)
      if (w.analytics && typeof w.analytics.track === 'function') {
        w.analytics.track('help_open');
        return;
      }

      // Mixpanel
      if (w.mixpanel && typeof w.mixpanel.track === 'function') {
        w.mixpanel.track('help_open');
        return;
      }
    } catch (err) {
      // swallow telemetry errors; not critical
      // console.debug('Help telemetry failed', err);
    }
  }
}
