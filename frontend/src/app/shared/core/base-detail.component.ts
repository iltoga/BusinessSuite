import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  type OnInit,
  type WritableSignal,
} from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { catchError, finalize, Observable, tap, throwError } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Configuration for detail component behavior
 */
export interface BaseDetailConfig<T> {
  /** Entity type name for routes (e.g., 'customers', 'invoices') */
  entityType: string;
  /** Entity label for messages (e.g., 'Customer', 'Invoice') */
  entityLabel: string;
  /** List route to go back to (defaults to '/{entityType}') */
  listRoute?: string;
  /** Enable delete action */
  enableDelete?: boolean;
  /** Enable edit action */
  enableEdit?: boolean;
  /** Require superuser for delete */
  deleteRequiresSuperuser?: boolean;
  /** Custom messages */
  messages?: {
    loadError?: string;
    deleteConfirm?: (item: T) => string;
    deleteSuccess?: string;
    deleteError?: string;
  };
}

/**
 * Base detail component providing common patterns for detail/detail views
 *
 * Features:
 * - Keyboard shortcuts (E for edit, D for delete, B/Left for back)
 * - Navigation state management (returnUrl, searchQuery, page)
 * - Loading states
 * - Delete confirmation
 * - Edit navigation
 *
 * @example
 * ```typescript
 * @Component({
 *   selector: 'app-customer-detail',
 *   templateUrl: './customer-detail.component.html',
 * })
 * export class CustomerDetailComponent extends BaseDetailComponent<Customer> {
 *   constructor() {
 *     super({
 *       entityType: 'customers',
 *       entityLabel: 'Customer',
 *       enableDelete: true,
 *       deleteRequiresSuperuser: true,
 *     });
 *   }
 *
 *   protected override loadItem(id: number): Observable<Customer> {
 *     return this.service.getCustomer(id);
 *   }
 *
 *   protected override deleteItem(id: number): Observable<any> {
 *     return this.service.deleteCustomer(id);
 *   }
 * }
 * ```
 */
@Component({
  selector: 'app-base-detail',
  standalone: true,
  imports: [],
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export abstract class BaseDetailComponent<T> implements OnInit {
  protected readonly route = inject(ActivatedRoute);
  protected readonly router = inject(Router);
  protected readonly authService = inject(AuthService);
  protected readonly toast = inject(GlobalToastService);
  protected readonly platformId = inject(PLATFORM_ID);
  protected readonly destroyRef = inject(DestroyRef);
  protected readonly isBrowser = isPlatformBrowser(this.platformId);

  // State signals
  readonly item: WritableSignal<T | null> = signal(null);
  readonly isLoading: WritableSignal<boolean> = signal(true);
  readonly isSuperuser = this.authService.isSuperuser;

  // Navigation state
  readonly originSearchQuery = signal<string | null>(null);
  readonly originPage = signal<number | null>(null);
  readonly returnUrl = signal<string | null>(null);
  readonly returnState = signal<Record<string, unknown> | null>(null);

  // Item ID from route
  protected itemId: number | null = null;

  // Configuration - must be set by child class
  protected config!: BaseDetailConfig<T>;

  constructor() {}

  /**
   * Load item by ID - must be implemented by child class
   */
  protected abstract loadItem(id: number): Observable<T>;

  /**
   * Delete item - must be implemented by child class if delete is enabled
   */
  protected abstract deleteItem(id: number): Observable<any>;

  /**
   * Get the list route
   */
  protected getListRoute(): string {
    return this.config.listRoute ?? `/${this.config.entityType}`;
  }

  /**
   * Get the edit route
   */
  protected getEditRoute(id: number): string {
    return `/${this.config.entityType}/${id}/edit`;
  }

  /**
   * Get the detail route
   */
  protected getDetailRoute(id: number): string {
    return `/${this.config.entityType}/${id}`;
  }

  /**
   * Navigate to edit
   */
  protected navigateToEdit(): void {
    if (!this.itemId) return;

    this.router.navigate([this.getEditRoute(this.itemId)], {
      state: {
        from: this.config.entityType,
        focusId: this.itemId,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  /**
   * Navigate back to list or return URL
   */
  protected goBack(): void {
    const returnUrl = this.returnUrl();

    if (returnUrl) {
      this.router.navigateByUrl(returnUrl, {
        state: this.returnState() ?? {
          searchQuery: this.originSearchQuery(),
          page: this.originPage() ?? undefined,
        },
      });
      return;
    }

    const focusState: Record<string, unknown> = {
      focusTable: true,
      focusId: this.itemId ?? undefined,
      searchQuery: this.originSearchQuery(),
    };

    if (this.originPage()) {
      focusState['page'] = this.originPage();
    }

    this.router.navigate([this.getListRoute()], { state: focusState });
  }

  /**
   * Handle delete action
   */
  protected onDelete(): void {
    if (!this.itemId || !this.item()) return;

    // Check permissions
    if (this.config.deleteRequiresSuperuser && !this.isSuperuser()) {
      return;
    }

    const confirmMessage =
      this.config.messages?.deleteConfirm?.(this.item()!) ??
      `Delete ${this.config.entityLabel.toLowerCase()}? This cannot be undone.`;

    if (!confirm(confirmMessage)) {
      return;
    }

    this.deleteItem(this.itemId).subscribe({
      next: () => {
        const successMessage =
          this.config.messages?.deleteSuccess ?? `${this.config.entityLabel} deleted successfully`;
        this.toast.success(successMessage);

        this.goBack();
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        const errorMessage =
          this.config.messages?.deleteError ??
          `Failed to delete ${this.config.entityLabel.toLowerCase()}`;
        this.toast.error(message ?? errorMessage);
      },
    });
  }

  /**
   * Handle keyboard shortcuts
   */
  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput = this.isInputElement(activeElement);

    if (isInput) return;

    const canEdit = this.config.enableEdit !== false;
    const canDelete =
      this.config.enableDelete !== false &&
      (!this.config.deleteRequiresSuperuser || this.isSuperuser());

    // E for Edit
    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (canEdit) {
        event.preventDefault();
        this.navigateToEdit();
      }
    }

    // D for Delete (superusers only if required)
    if (event.key === 'D' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (canDelete) {
        event.preventDefault();
        this.onDelete();
      }
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
   * Check if element is an input
   */
  private isInputElement(element: Element | null): boolean {
    return (
      element instanceof HTMLInputElement ||
      element instanceof HTMLTextAreaElement ||
      (element instanceof HTMLElement && element.isContentEditable)
    );
  }

  /**
   * Restore navigation state from window.history
   */
  protected restoreNavigationState(): void {
    if (!this.isBrowser) return;

    const state = window.history.state || {};

    this.originSearchQuery.set(state.searchQuery ?? null);
    this.returnUrl.set(
      typeof state.returnUrl === 'string' && state.returnUrl.startsWith('/')
        ? state.returnUrl
        : null,
    );
    this.returnState.set(
      state.returnState && typeof state.returnState === 'object'
        ? (state.returnState as Record<string, unknown>)
        : null,
    );

    const page = Number(state.page);
    if (Number.isFinite(page) && page > 0) {
      this.originPage.set(Math.floor(page));
    }
  }

  /**
   * Load item for detail view
   */
  protected loadItemForDetail(id: number): void {
    if (!this.isBrowser) return;

    this.isLoading.set(true);

    this.loadItem(id)
      .pipe(
        tap((item) => {
          this.item.set(item);
        }),
        catchError((error) => {
          const message = extractServerErrorMessage(error);
          const errorMessage =
            this.config.messages?.loadError ??
            `Failed to load ${this.config.entityLabel.toLowerCase()}`;

          this.toast.error(message ?? errorMessage);

          // Navigate back on load error
          this.goBack();
          return throwError(() => error);
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe();
  }

  ngOnInit(): void {
    if (!this.isBrowser) return;

    this.restoreNavigationState();

    // Get item ID from route
    const idParam = this.route.snapshot.paramMap.get('id');

    if (idParam) {
      const id = Number(idParam);
      if (Number.isFinite(id)) {
        this.itemId = id;
        this.loadItemForDetail(id);
      } else {
        this.toast.error(`Invalid ${this.config.entityLabel.toLowerCase()} ID`);
        this.goBack();
      }
    } else {
      this.toast.error(`${this.config.entityLabel} not found`);
      this.goBack();
    }
  }
}
