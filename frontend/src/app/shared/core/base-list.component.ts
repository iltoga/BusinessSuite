import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  Signal,
  viewChild,
  type OnInit,
  type ResourceRef,
  type WritableSignal,
} from '@angular/core';
import { rxResource } from '@angular/core/rxjs-interop';
import { ActivatedRoute, Router, type Params } from '@angular/router';
import { catchError, of, type Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Paginated response shape expected from list API calls.
 */
export interface PaginatedResponse<T> {
  results?: T[];
  count?: number;
}

/**
 * Parameters passed to the list loader function.
 */
export interface ListRequestParams {
  query: string;
  page: number;
  pageSize: number;
  ordering: string | undefined;
  /** Monotonically increasing counter — change triggers a reload */
  reloadToken: number;
}

/**
 * Configuration for list component behavior
 */
export interface BaseListConfig<T> {
  /** Entity type name for routes (e.g., 'customers', 'products') */
  entityType: string;
  /** Entity label for messages (e.g., 'Customer', 'Product') */
  entityLabel?: string;
  /** Default page size */
  defaultPageSize?: number;
  /** Default ordering */
  defaultOrdering?: string;
  /** Enable bulk delete */
  enableBulkDelete?: boolean;
  /** Enable superuser-only delete */
  enableDelete?: boolean;
  /** Custom new route path (defaults to '/{entityType}/new') */
  newRoute?: string;
}

/**
 * Base list component providing common patterns for list views
 *
 * Uses Angular's `rxResource()` API for declarative, signal‑native data
 * fetching with automatic request cancellation and built-in loading state.
 *
 * Features:
 * - Signal-based state management
 * - Keyboard shortcuts (Shift+N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management after navigation
 * - Bulk delete support
 *
 * @example
 * ```typescript
 * @Component({ ... })
 * export class CustomerListComponent extends BaseListComponent<Customer> {
 *   private readonly service = inject(CustomersService);
 *
 *   constructor() {
 *     super({
 *       entityType: 'customers',
 *       defaultPageSize: 8,
 *       enableBulkDelete: true,
 *       enableDelete: true,
 *     });
 *   }
 *
 *   protected override createListLoader(
 *     params: ListRequestParams,
 *   ): Observable<PaginatedResponse<Customer>> {
 *     return this.service.list({ ... });
 *   }
 * }
 * ```
 */
@Component({
  selector: 'app-base-list',
  standalone: true,
  imports: [CommonModule],
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export abstract class BaseListComponent<T> implements OnInit {
  protected readonly authService = inject(AuthService);
  protected readonly toast = inject(GlobalToastService);
  protected readonly router = inject(Router);
  protected readonly route = inject(ActivatedRoute);
  protected readonly platformId = inject(PLATFORM_ID);
  protected readonly destroyRef = inject(DestroyRef);
  protected readonly isBrowser = isPlatformBrowser(this.platformId);

  // ── State signals ──────────────────────────────────────────────────
  readonly items: WritableSignal<T[]> = signal([]);
  readonly query = signal('');
  readonly page = signal(1);
  readonly totalItems = signal(0);
  readonly isSuperuser = this.authService.isSuperuser;

  // State signals that need config-based initialization (set in constructor)
  readonly pageSize: WritableSignal<number>;
  readonly ordering: WritableSignal<string | undefined>;

  /**
   * Bump this signal to force `listResource` to re-fetch even when the
   * query/page/ordering signals have not changed (e.g. after a delete).
   */
  protected readonly reloadToken = signal(0);

  // ── Bulk delete signals ────────────────────────────────────────────
  readonly bulkDeleteOpen = signal(false);
  readonly bulkDeleteData = signal<any | null>(null);
  protected readonly bulkDeleteQuery = signal<string>('');

  /**
   * Bulk delete label - can be overridden by child class
   */
  readonly bulkDeleteLabel = computed(() =>
    this.query().trim()
      ? `Delete Selected ${this.getEntityTypeLabel()}`
      : `Delete All ${this.getEntityTypeLabel()}`,
  );

  // ── Focus management ───────────────────────────────────────────────
  private readonly focusTableOnInit = signal(false);
  private readonly focusIdOnInit = signal<number | null>(null);

  // Data table reference for focus management
  protected readonly dataTable = viewChild.required(DataTableComponent);

  // ── rxResource ─────────────────────────────────────────────────────
  /**
   * The core reactive resource that drives data fetching.
   * Re-fetches automatically when any tracked signal changes.
   */
  protected readonly listResource: ResourceRef<PaginatedResponse<T>>;

  /**
   * Derived `isLoading` signal that mirrors the resource's loading state.
   */
  readonly isLoading: Signal<boolean>;

  /**
   * Columns configuration - must be implemented by child
   */
  abstract readonly columns: Signal<ColumnConfig<T>[]>;

  /**
   * Actions configuration - optional
   */
  readonly actions: Signal<any[]> = signal([]);

  /**
   * Total pages computed
   */
  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  // Configuration - must be set by child class
  protected config!: BaseListConfig<T>;

  constructor() {
    this.pageSize = signal(8);
    this.ordering = signal(undefined);

    // Create the rxResource — the `request` function captures all signal
    // dependencies so the resource automatically re-fetches when any of
    // them change.
    this.listResource = rxResource<PaginatedResponse<T>, ListRequestParams>({
      params: () => ({
        query: this.query(),
        page: this.page(),
        pageSize: this.pageSize(),
        ordering: this.ordering(),
        reloadToken: this.reloadToken(),
      }),
      stream: ({ params }) => {
        if (!this.isBrowser) {
          return of({ results: [], count: 0 });
        }
        return this.createListLoader(params).pipe(
          catchError((err) => {
            this.toast.error(this.getLoadErrorMessage(err));
            return of({ results: [], count: 0 });
          }),
        );
      },
      defaultValue: { results: [], count: 0 },
    });

    this.isLoading = this.listResource.isLoading;

    // Sync resource value → items + totalItems signals whenever
    // a new page of data arrives.
    effect(() => {
      const response = this.listResource.value();
      if (response) {
        // Prevent state drop to 0 during rxResource Reloading phases
        // which momentarily emits the defaultValue, causing search box buttons to flicker.
        const isTransientLoadingState =
          this.listResource.isLoading() &&
          response.count === 0 &&
          (!response.results || response.results.length === 0);

        if (!isTransientLoadingState) {
          this.items.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          // Defer focus management to ensure Angular has flushed the items signal to the template bindings
          setTimeout(() => this.focusAfterLoad(), 0);
        }
      }
    });
  }

  /**
   * Create the Observable that fetches a page of data.
   * Child classes implement this to call their API service.
   */
  protected abstract createListLoader(params: ListRequestParams): Observable<PaginatedResponse<T>>;

  /**
   * Imperatively trigger a reload (e.g. after a delete or mutation).
   * This bumps `reloadToken`, which the resource is tracking.
   */
  reload(): void {
    this.reloadToken.update((t) => t + 1);
  }

  /**
   * Get the error message for a failed load operation.
   * Override in child to customize.
   */
  protected getLoadErrorMessage(_err?: unknown): string {
    const label = this.getEntityTypeLabel().toLowerCase();
    return `Failed to load ${label}`;
  }

  // ── Route helpers ──────────────────────────────────────────────────

  /**
   * Get the route for creating a new item
   */
  protected getNewRoute(): string {
    return this.config.newRoute ?? `/${this.config.entityType}/new`;
  }

  /**
   * Get the route for listing items
   */
  protected getListRoute(): string {
    return `/${this.config.entityType}`;
  }

  /**
   * Get the route for editing an item
   */
  protected getEditRoute(id: number | string): string {
    return `/${this.config.entityType}/${id}/edit`;
  }

  /**
   * Get the route for viewing an item detail
   */
  protected getDetailRoute(id: number | string): string {
    return `/${this.config.entityType}/${id}`;
  }

  /**
   * Get the entity label (plural form for messages)
   */
  protected getEntityTypeLabel(): string {
    return this.config.entityLabel ?? this.config.entityType;
  }

  // ── Navigation helpers ─────────────────────────────────────────────

  /**
   * Navigate to create new item
   */
  protected navigateToNew(state?: Record<string, unknown>): void {
    this.router.navigate([this.getNewRoute()], {
      state: {
        from: this.config.entityType,
        searchQuery: this.query(),
        page: this.page(),
        ...state,
      },
    });
  }

  /**
   * Navigate to edit item
   */
  protected navigateToEdit(id: number | string, state?: Record<string, unknown>): void {
    this.router.navigate([this.getEditRoute(id)], {
      state: {
        from: this.config.entityType,
        focusId: id,
        searchQuery: this.query(),
        page: this.page(),
        ...state,
      },
    });
  }

  /**
   * Navigate to view item detail
   */
  protected navigateToDetail(id: number | string, state?: Record<string, unknown>): void {
    this.router.navigate([this.getDetailRoute(id)], {
      state: {
        from: this.config.entityType,
        focusId: id,
        searchQuery: this.query(),
        page: this.page(),
        ...state,
      },
    });
  }

  /**
   * Navigate back to list
   */
  protected goBack(): void {
    this.router.navigate([this.getListRoute()], {
      queryParams: this.buildUrlParams(),
      state: {
        focusTable: true,
        searchQuery: this.query(),
        page: this.page(),
      },
    });
  }

  // ── Event handlers ─────────────────────────────────────────────────

  /**
   * Handle query change
   */
  onQueryChange(value: string): void {
    const trimmed = value.trim();
    if (this.query() === trimmed) return;
    this.query.set(trimmed);
    this.page.set(1);
    this.updateUrl();
    // rxResource re-fetches automatically because query() changed
  }

  /**
   * Handle page change
   */
  onPageChange(page: number): void {
    this.page.set(page);
    this.updateUrl();
    // rxResource re-fetches automatically because page() changed
  }

  /**
   * Handle sort change
   */
  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.updateUrl();
    // rxResource re-fetches automatically because ordering() changed
  }

  /**
   * Handle keyboard shortcuts
   */
  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput = this.isInputElement(activeElement);

    if (isInput) return;

    // Shift+N or N for New
    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.navigateToNew();
    }

    // B or Left Arrow for Back
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.goBack();
    }
  }

  // ── Bulk delete ────────────────────────────────────────────────────

  /**
   * Open bulk delete dialog
   */
  openBulkDeleteDialog(entityLabel: string, detailsText: string): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';

    this.bulkDeleteQuery.set(query);
    this.bulkDeleteData.set({
      entityLabel,
      totalCount: this.totalItems(),
      query: query || null,
      mode,
      detailsText,
    });
    this.bulkDeleteOpen.set(true);
  }

  /**
   * Handle bulk delete confirmation
   */
  protected handleBulkDelete(
    deleteFn: (query: string) => any,
    successMessage?: (count: number) => string,
  ): void {
    const query = this.bulkDeleteQuery();

    deleteFn(query).subscribe({
      next: (response: any) => {
        const payload = unwrapApiRecord(response) as {
          deletedCount?: number;
          deleted_count?: number;
        } | null;
        const count = payload?.deletedCount ?? payload?.deleted_count ?? 0;
        this.toast.success(successMessage?.(count) ?? `Deleted ${count} item(s)`);
        this.bulkDeleteOpen.set(false);
        this.bulkDeleteData.set(null);
        this.bulkDeleteQuery.set('');
        this.reload();
      },
      error: (error: any) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(message ? `Failed to delete items: ${message}` : 'Failed to delete items');
        this.bulkDeleteOpen.set(false);
        this.bulkDeleteData.set(null);
      },
    });
  }

  /**
   * Cancel bulk delete
   */
  onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.bulkDeleteQuery.set('');
  }

  // ── Navigation state restoration ───────────────────────────────────

  /**
   * Build URL query params from current signal state.
   * Returns only non-default values to keep URLs clean.
   */
  protected buildUrlParams(): Record<string, string | null> {
    const params: Record<string, string | null> = {};

    // Query — omit when empty
    const q = this.query();
    params['q'] = q || null;

    // Page — omit when 1 (default)
    const page = this.page();
    params['page'] = page > 1 ? String(page) : null;

    // Sort — omit when matching the config default
    const sort = this.ordering();
    params['sort'] = sort && sort !== this.config?.defaultOrdering ? sort : null;

    // Merge with child-specific params
    return { ...params, ...this.getExtraUrlParams() };
  }

  /**
   * Hook for child classes to add extra URL query params
   * (e.g., column filters, status filter).
   * Return `null` for a key to omit it from the URL.
   */
  protected getExtraUrlParams(): Record<string, string | null> {
    return {};
  }

  /**
   * Hook for child classes to restore extra URL query params.
   * Called during init when URL params are present.
   */
  protected restoreExtraUrlParams(_params: Params): void {
    // No-op by default — children override this.
  }

  /**
   * Sync current signal state to URL query params.
   * Uses `replaceUrl` to avoid polluting browser history on every change.
   */
  protected updateUrl(): void {
    if (!this.isBrowser) return;

    this.router.navigate([], {
      relativeTo: this.route,
      queryParams: this.buildUrlParams(),
      replaceUrl: true,
    });
  }

  /**
   * Restore state from URL query params.
   * Returns true if any relevant params were found.
   */
  private restoreFromUrl(): boolean {
    if (!this.isBrowser) return false;

    const params = this.route.snapshot.queryParams;
    let found = false;

    const q = params['q'];
    if (q) {
      this.query.set(String(q));
      found = true;
    }

    const page = params['page'];
    if (page) {
      const n = Number(page);
      if (Number.isFinite(n) && n > 0) {
        this.page.set(Math.floor(n));
        found = true;
      }
    }

    const sort = params['sort'];
    if (sort) {
      this.ordering.set(String(sort));
      found = true;
    }

    // Let children restore their own params
    this.restoreExtraUrlParams(params);

    return found;
  }

  /**
   * Restore navigation state from window.history
   */
  protected restoreNavigationState(skipSearchAndPage = false): void {
    if (!this.isBrowser) return;

    const state = window.history.state || {};
    this.focusTableOnInit.set(Boolean(state.focusTable));
    this.focusIdOnInit.set(state.focusId ? Number(state.focusId) : null);

    // When URL params already restored search/page, skip history.state fallback
    if (skipSearchAndPage) return;

    const restoredPage = Number(state.page);
    if (Number.isFinite(restoredPage) && restoredPage > 0) {
      this.page.set(Math.floor(restoredPage));
    }

    if (state.searchQuery) {
      this.query.set(String(state.searchQuery));
    }
  }

  /**
   * Focus table or specific row after load
   */
  protected focusAfterLoad(): void {
    const table = this.dataTable();
    if (!table) return;

    const focusId = this.focusIdOnInit();
    if (focusId) {
      this.focusIdOnInit.set(null);
      table.focusRowById(focusId);
    } else if (this.focusTableOnInit()) {
      this.focusTableOnInit.set(false);
      table.focusFirstRowIfNone();
    }
  }

  /**
   * Check if element is an input
   */
  private isInputElement(element: Element | null): boolean {
    return (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      (element instanceof HTMLElement && element.isContentEditable)
    );
  }

  ngOnInit(): void {
    if (!this.isBrowser) return;

    if (this.config) {
      if (this.config.defaultPageSize !== undefined) {
        this.pageSize.set(this.config.defaultPageSize);
      }
      if (this.config.defaultOrdering !== undefined) {
        this.ordering.set(this.config.defaultOrdering);
      }
    }

    // URL query params are the primary source of truth (survives page refresh)
    const hasUrlState = this.restoreFromUrl();

    // Fall back to history.state for focus hints,
    // and for search/page when no URL params are present
    this.restoreNavigationState(hasUrlState);

    // Ensure URL reflects the current state (e.g., when restored from history.state)
    this.updateUrl();

    // The rxResource will automatically start fetching because it was
    // created in the constructor and its signal dependencies are now set.
  }
}
