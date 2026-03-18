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
import { FormBuilder, FormGroup } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  catchError,
  finalize,
  map,
  Observable,
  of,
  switchMap,
  tap,
  throwError,
  timeout,
  TimeoutError,
} from 'rxjs';

import { GlobalToastService } from '@/core/services/toast.service';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Configuration for form component behavior
 */
export interface BaseFormConfig<T, CreateDto, UpdateDto> {
  /** Entity type name for routes (e.g., 'customers', 'products') */
  entityType: string;
  /** Entity label for messages (e.g., 'Customer', 'Product') */
  entityLabel: string;
  /** List route to go back to */
  listRoute?: string;
  /** Enable toast notifications */
  enableToasts?: boolean;
  /** Custom success messages */
  messages?: {
    createSuccess?: string;
    updateSuccess?: string;
    loadError?: string;
    saveError?: string;
  };
}

/**
 * Base form component providing common patterns for create/edit forms
 *
 * Features:
 * - Keyboard shortcuts (Ctrl/Cmd+S to save, Escape to cancel)
 * - Edit mode detection from route
 * - Server error handling
 * - Navigation state management
 * - Loading states
 *
 * @example
 * ```typescript
 * @Component({
 *   selector: 'app-customer-form',
 *   templateUrl: './customer-form.component.html',
 * })
 * export class CustomerFormComponent extends BaseFormComponent<
 *   Customer,
 *   CustomerCreateDto,
 *   CustomerUpdateDto
 * > {
 *   constructor() {
 *     super({
 *       entityType: 'customers',
 *       entityLabel: 'Customer',
 *     });
 *   }
 *
 *   protected override buildForm(): FormGroup {
 *     return this.fb.group({
 *       // form controls
 *     });
 *   }
 *
 *   protected override loadItem(id: number): Observable<Customer> {
 *     return this.service.getCustomer(id);
 *   }
 *
 *   protected override createDto(): CustomerCreateDto {
 *     return this.form.value;
 *   }
 *
 *   protected override updateDto(): CustomerUpdateDto {
 *     return this.form.value;
 *   }
 *
 *   protected override saveCreate(dto: CustomerCreateDto): Observable<any> {
 *     return this.service.createCustomer(dto);
 *   }
 *
 *   protected override saveUpdate(dto: CustomerUpdateDto): Observable<any> {
 *     return this.service.updateCustomer(this.itemId!, dto);
 *   }
 * }
 * ```
 */
@Component({
  selector: 'app-base-form',
  standalone: true,
  imports: [],
  template: '',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export abstract class BaseFormComponent<T, CreateDto, UpdateDto> implements OnInit {
  private static readonly SAVE_TIMEOUT_MS = 30_000;

  protected readonly fb = inject(FormBuilder);
  protected readonly route = inject(ActivatedRoute);
  protected readonly router = inject(Router);
  protected readonly toast = inject(GlobalToastService);
  protected readonly platformId = inject(PLATFORM_ID);
  protected readonly destroyRef = inject(DestroyRef);
  protected readonly isBrowser = isPlatformBrowser(this.platformId);

  // State signals
  readonly isLoading: WritableSignal<boolean> = signal(false);
  readonly isSaving: WritableSignal<boolean> = signal(false);
  readonly isEditMode: WritableSignal<boolean> = signal(false);
  readonly item: WritableSignal<T | null> = signal(null);

  // Form control - must be initialized in buildForm()
  form!: FormGroup;

  // Item ID from route
  protected itemId: number | null = null;

  // Error labels for form error display
  readonly formErrorLabels: Record<string, string> = {};

  // Field tooltips for help text
  readonly fieldTooltips: Record<string, string> = {};

  // Configuration - must be set by child class
  protected config!: BaseFormConfig<T, CreateDto, UpdateDto>;

  constructor() {}

  /**
   * Build the form group - must be implemented by child class
   */
  protected abstract buildForm(): FormGroup;

  /**
   * Load item by ID for edit mode - must be implemented by child class
   */
  protected abstract loadItem(id: number): Observable<T>;

  /**
   * Create DTO from form value for create mode - must be implemented by child class
   */
  protected abstract createDto(): CreateDto;

  /**
   * Update DTO from form value for edit mode - must be implemented by child class
   */
  protected abstract updateDto(): UpdateDto;

  /**
   * Save operation for create mode - must be implemented by child class
   */
  protected abstract saveCreate(dto: CreateDto): Observable<any>;

  /**
   * Save operation for update mode - must be implemented by child class
   */
  protected abstract saveUpdate(dto: UpdateDto): Observable<any>;

  /**
   * Get the list route to navigate back to
   */
  protected getListRoute(): string {
    return this.config.listRoute ?? `/${this.config.entityType}`;
  }

  /**
   * Get the edit route for an item
   */
  protected getEditRoute(id: number): string {
    return `/${this.config.entityType}/${id}/edit`;
  }

  /**
   * Get the detail route for an item
   */
  protected getDetailRoute(id: number): string {
    return `/${this.config.entityType}/${id}`;
  }

  /**
   * Timeout used for create/update operations so buttons do not remain disabled forever
   * when the network path stalls upstream.
   */
  protected getSaveTimeoutMs(): number {
    return BaseFormComponent.SAVE_TIMEOUT_MS;
  }

  /**
   * Navigate back to list
   */
  protected goBack(): void {
    this.router.navigate([this.getListRoute()], {
      state: {
        focusTable: true,
        focusId: this.itemId ?? undefined,
        searchQuery: this.getNavigationState().searchQuery,
        page: this.getNavigationState().page,
      },
    });
  }

  /**
   * Navigate to edit mode after creation
   */
  protected navigateToEdit(id: number): void {
    this.router.navigate([this.getEditRoute(id)], {
      state: {
        from: this.config.entityType,
        searchQuery: this.getNavigationState().searchQuery,
        page: this.getNavigationState().page,
      },
    });
  }

  /**
   * Navigate to detail view
   */
  protected navigateToDetail(id: number): void {
    this.router.navigate([this.getDetailRoute(id)], {
      state: {
        from: this.config.entityType,
        searchQuery: this.getNavigationState().searchQuery,
        page: this.getNavigationState().page,
      },
    });
  }

  /**
   * Get navigation state from window.history
   */
  protected getNavigationState(): { searchQuery: string | null; page: number | null } {
    if (!this.isBrowser) {
      return { searchQuery: null, page: null };
    }

    const state = window.history.state || {};
    return {
      searchQuery: state.searchQuery ?? null,
      page: state.page ? Number(state.page) : null,
    };
  }

  /**
   * Handle keyboard shortcuts
   */
  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput = this.isInputElement(activeElement);

    if (isInput) return;

    // Escape to cancel
    if (event.key === 'Escape') {
      event.preventDefault();
      this.onCancel();
      return;
    }

    // Ctrl/Cmd+S to save
    if ((event.ctrlKey || event.metaKey) && (event.key === 's' || event.key === 'S')) {
      event.preventDefault();
      this.onSubmit();
      return;
    }

    // B or Left Arrow to go back
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.onCancel();
    }
  }

  /**
   * Submit form
   */
  onSubmit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      this.toast.error('Please fix the form errors');
      return;
    }

    this.isSaving.set(true);

    const save$ = this.isEditMode()
      ? this.saveUpdate(this.updateDto())
      : this.saveCreate(this.createDto());

    save$
      .pipe(
        timeout({ first: this.getSaveTimeoutMs() }),
        tap(() => {
          const message = this.isEditMode()
            ? (this.config.messages?.updateSuccess ??
              `${this.config.entityLabel} updated successfully`)
            : (this.config.messages?.createSuccess ??
              `${this.config.entityLabel} created successfully`);
          if (this.config.enableToasts !== false) {
            this.toast.success(message);
          }
        }),
        map(() => (this.isEditMode() ? this.itemId : null)),
        switchMap((id) => {
          // Navigate after successful save
          if (id) {
            this.navigateToEdit(id);
          } else {
            this.goBack();
          }
          return of(null);
        }),
        catchError((error) => {
          const message =
            error instanceof TimeoutError
              ? `${this.config.entityLabel} save timed out. Please try again.`
              : extractServerErrorMessage(error);
          const errorMessage =
            this.config.messages?.saveError ??
            `Failed to ${this.isEditMode() ? 'update' : 'create'} ${this.config.entityLabel.toLowerCase()}`;

          if (this.config.enableToasts !== false) {
            this.toast.error(message ?? errorMessage);
          }

          // Apply server errors to form
          applyServerErrorsToForm(this.form, error);
          return throwError(() => error);
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe({ error: () => undefined });
  }

  /**
   * Cancel and go back
   */
  onCancel(): void {
    this.goBack();
  }

  /**
   * Patch form with loaded item data
   */
  protected patchForm(item: T): void {
    this.form.patchValue(item as any, { emitEvent: false });
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
    // Initialize form
    this.form = this.buildForm();

    // Check if we're in edit mode
    const idParam = this.route.snapshot.paramMap.get('id');

    if (idParam) {
      const id = Number(idParam);
      if (Number.isFinite(id)) {
        this.itemId = id;
        this.isEditMode.set(true);
        this.loadItemForEdit(id);
      }
    }
  }

  /**
   * Load item for edit mode
   */
  private loadItemForEdit(id: number): void {
    if (!this.isBrowser) return;

    this.isLoading.set(true);

    this.loadItem(id)
      .pipe(
        tap((item) => {
          this.item.set(item);
          this.patchForm(item);
        }),
        catchError((error) => {
          const message = extractServerErrorMessage(error);
          const errorMessage =
            this.config.messages?.loadError ??
            `Failed to load ${this.config.entityLabel.toLowerCase()}`;

          if (this.config.enableToasts !== false) {
            this.toast.error(message ?? errorMessage);
          }

          // Navigate back on load error
          this.goBack();
          return throwError(() => error);
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe();
  }
}
