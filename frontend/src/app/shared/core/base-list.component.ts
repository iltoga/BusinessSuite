import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  Signal,
  viewChild,
  type OnInit,
  type WritableSignal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router } from '@angular/router';
import { Subject, catchError, of, switchMap } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

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
 * @Component({
 *   selector: 'app-customer-list',
 *   templateUrl: './customer-list.component.html',
 * })
 * export class CustomerListComponent extends BaseListComponent<CustomerListItem> {
 *   constructor() {
 *     super({
 *       entityType: 'customers',
 *       defaultPageSize: 8,
 *       enableBulkDelete: true,
 *       enableDelete: true,
 *     });
 *   }
 * 
 *   protected override loadItems(): void {
 *     // Custom implementation
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
  protected readonly platformId = inject(PLATFORM_ID);
  protected readonly destroyRef = inject(DestroyRef);
  protected readonly isBrowser = isPlatformBrowser(this.platformId);

  // State signals
  readonly items: WritableSignal<T[]> = signal([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly totalItems = signal(0);
  readonly isSuperuser = this.authService.isSuperuser;

  // State signals that need config-based initialization (set in constructor)
  readonly pageSize: WritableSignal<number>;
  readonly ordering: WritableSignal<string | undefined>;

  // Bulk delete signals
  readonly bulkDeleteOpen = signal(false);
  readonly bulkDeleteData = signal<any | null>(null);
  protected readonly bulkDeleteQuery = signal<string>('');

  /**
   * Bulk delete label - can be overridden by child class
   */
  readonly bulkDeleteLabel = computed(() =>
    this.query().trim() ? `Delete Selected ${this.getEntityTypeLabel()}` : `Delete All ${this.getEntityTypeLabel()}`,
  );

  // Focus management
  private readonly focusTableOnInit = signal(false);
  private readonly focusIdOnInit = signal<number | null>(null);

  // Data table reference for focus management
  protected readonly dataTable = viewChild.required(DataTableComponent);

  // Load trigger for rxMethod pattern
  protected readonly loadItemsTrigger$ = new Subject<void>();

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
    this.pageSize = signal(10);
    this.ordering = signal(undefined);
  }

  /**
   * Load items from service - must be implemented by child class
   */
  protected abstract loadItems(): void;

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
      state: {
        focusTable: true,
        searchQuery: this.query(),
        page: this.page(),
      },
    });
  }

  /**
   * Handle query change
   */
  onQueryChange(value: string): void {
    const trimmed = value.trim();
    if (this.query() === trimmed) return;
    this.query.set(trimmed);
    this.page.set(1);
    this.loadItems();
  }

  /**
   * Handle page change
   */
  onPageChange(page: number): void {
    this.page.set(page);
    this.loadItems();
  }

  /**
   * Handle sort change
   */
  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.loadItems();
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
        const payload = response as { deletedCount?: number; deleted_count?: number };
        const count = payload.deletedCount ?? payload.deleted_count ?? 0;
        this.toast.success(successMessage?.(count) ?? `Deleted ${count} item(s)`);
        this.bulkDeleteOpen.set(false);
        this.bulkDeleteData.set(null);
        this.bulkDeleteQuery.set('');
        this.loadItems();
      },
      error: (error: any) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete items: ${message}` : 'Failed to delete items',
        );
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

  /**
   * Restore navigation state from window.history
   */
  protected restoreNavigationState(): void {
    if (!this.isBrowser) return;

    const state = window.history.state || {};
    this.focusTableOnInit.set(Boolean(state.focusTable));
    this.focusIdOnInit.set(state.focusId ? Number(state.focusId) : null);

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

    this.restoreNavigationState();
    this.loadItems();
  }
}
