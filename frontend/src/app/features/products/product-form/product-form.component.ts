import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { Observable, switchMap, tap } from 'rxjs';

import {
  DocumentTypesService,
  ProductCreateUpdateRequestProductTypeEnum,
  ProductsService,
  type DocumentType,
  type ProductCreateUpdate,
  type ProductCreateUpdateRequest,
  type ProductDetail,
} from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import {
  SortableMultiSelectComponent,
  type SortableOption,
} from '@/shared/components/sortable-multi-select';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { BaseFormComponent, BaseFormConfig } from '@/shared/core/base-form.component';

type ProductTask = NonNullable<ProductDetail['tasks']>[number];
type ProductTaskRequest = NonNullable<ProductCreateUpdateRequest['tasks']>[number];
type ProductNavigationState = {
  searchQuery: string | null;
  page: number | null;
  focusId: number | null;
  returnToList: boolean;
  returnToDetail: boolean;
};

/**
 * Product form component
 *
 * Extends BaseFormComponent to inherit common form patterns:
 * - Keyboard shortcuts (Ctrl/Cmd+S to save, Escape to cancel)
 * - Edit mode detection from route
 * - Server error handling
 * - Loading states
 */
@Component({
  selector: 'app-product-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
    ZardCheckboxComponent,
    SortableMultiSelectComponent,
    ZardIconComponent,
    ...ZardTooltipImports,
    FormErrorSummaryComponent,
  ],
  templateUrl: './product-form.component.html',
  styleUrls: ['./product-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductFormComponent
  extends BaseFormComponent<ProductDetail, ProductCreateUpdateRequest, ProductCreateUpdateRequest>
  implements OnInit
{
  private readonly productsApi = inject(ProductsService);
  private readonly documentTypesApi = inject(DocumentTypesService);
  private readonly configService = inject(ConfigService);
  private readonly authService = inject(AuthService);

  // Product-specific state
  readonly documentTypes = signal<DocumentType[]>([]);
  readonly isAdminOrManager = this.authService.isAdminOrManager;

  readonly requiredOptions = computed<SortableOption[]>(() =>
    this.documentTypes()
      .filter((doc) => doc.isInRequiredDocuments)
      .map((doc) => ({ id: doc.id, label: doc.name })),
  );

  readonly optionalOptions = computed<SortableOption[]>(() =>
    this.documentTypes()
      .filter((doc) => !doc.isInRequiredDocuments)
      .map((doc) => ({ id: doc.id, label: doc.name })),
  );

  readonly hasMultipleLastSteps = computed(() => {
    if (!this.showWorkflowSections()) {
      return false;
    }
    const tasks = this.tasksArray.controls;
    return tasks.filter((group) => group.get('lastStep')?.value).length > 1;
  });

  // Product reference for template compatibility
  readonly product = signal<ProductDetail | null>(null);

  // Form error labels
  override readonly formErrorLabels: Record<string, string> = {
    name: 'Name',
    code: 'Code',
    description: 'Description',
    basePrice: 'Base Price',
    retailPrice: 'Retail Price',
    currency: 'Currency',
    productType: 'Product Type',
    validity: 'Validity',
    documentsMinValidity: 'Documents Min Validity',
    applicationWindowDays: 'Application Window Days',
    validationPrompt: 'Validation Prompt',
    requiredDocumentIds: 'Required Documents',
    optionalDocumentIds: 'Optional Documents',
    tasks: 'Tasks',
    deprecated: 'Deprecated',
  };

  // Field tooltips
  override readonly fieldTooltips: Record<string, string> = {
    name: 'Display name shown to your team when selecting this product.',
    code: 'Unique internal code used in search, reports, and references.',
    productType: 'Controls product-specific labels and related workflow expectations.',
    currency: '2-3 letter currency code used for pricing (for example IDR or USD).',
    basePrice: 'Your internal/base cost for this product.',
    retailPrice: 'Customer-facing price. It must be equal to or higher than base price.',
    validity: 'How many days the product outcome remains valid (optional).',
    documentsMinValidity: 'Minimum remaining validity required for supporting documents.',
    applicationWindowDays:
      'How many days before the relevant deadline this product can be submitted or renewed.',
    description: 'Internal notes that explain what this product is for.',
    validationPrompt:
      'Optional AI instruction added to document validation for applications that use this product.',
    requiredDocumentIds: 'Documents that must be provided before the application can be completed.',
    optionalDocumentIds: 'Documents that are helpful but not mandatory for this product.',
    taskStep: 'Execution order in the workflow. Each step number must be unique.',
    taskName: 'Short task title shown in timelines and task lists.',
    taskDescription: 'Extra instructions for the team handling this step.',
    taskCost: 'Optional internal cost for this individual task.',
    taskDuration: 'Expected duration for this task in days.',
    taskAddToCalendar: 'When enabled, this step creates a calendar due event.',
    taskNotifyCustomer: 'Sends customer notifications for calendar-enabled tasks.',
    taskNotifyDaysBefore: 'How many days before due date customer reminders are sent.',
    taskDurationIsBusinessDays: 'Use business days instead of calendar days for task duration.',
    taskLastStep: 'Marks the final workflow step. Only one task can be the last step.',
    deprecated:
      'When enabled, this product is marked as deprecated and hidden from selection in new records.',
  };

  constructor() {
    super();
    this.config = {
      entityType: 'products',
      entityLabel: 'Product',
      rbacModel: 'product',
    } as BaseFormConfig<ProductDetail, ProductCreateUpdateRequest, ProductCreateUpdateRequest>;
  }

  /**
   * Build the product form
   */
  protected override buildForm(): FormGroup {
    return this.fb.group(
      {
        name: ['', Validators.required],
        code: ['', Validators.required],
        description: [''],
        basePrice: [0, [Validators.min(0)]],
        retailPrice: [0, [Validators.min(0)]],
        currency: [
          this.configService.settings.baseCurrency ?? 'IDR',
          [
            Validators.required,
            Validators.minLength(2),
            Validators.maxLength(3),
            Validators.pattern(/^[A-Za-z]{2,3}$/),
          ],
        ],
        productType: ['visa', Validators.required],
        validity: [null as number | null],
        documentsMinValidity: [null as number | null],
        applicationWindowDays: [null as number | null, [Validators.min(0)]],
        validationPrompt: [''],
        deprecated: [false],
        requiredDocumentIds: [[] as number[]],
        optionalDocumentIds: [[] as number[]],
        tasks: this.fb.array<FormGroup>([]),
      },
      { validators: [this.retailPriceValidator] },
    );
  }

  /**
   * Load product for edit mode
   */
  protected override loadItem(id: number): Observable<ProductDetail> {
    return this.productsApi.productsRetrieve({ id });
  }

  /**
   * Create DTO from form value
   */
  protected override createDto(): ProductCreateUpdateRequest {
    return this.buildPayload();
  }

  /**
   * Update DTO from form value
   */
  protected override updateDto(): ProductCreateUpdateRequest {
    return this.buildPayload();
  }

  /**
   * Save new product
   */
  protected override saveCreate(dto: ProductCreateUpdateRequest): Observable<ProductCreateUpdate> {
    return this.productsApi.productsCreate({ productCreateUpdateRequest: dto }).pipe(
      tap((item) => {
        const createdId = this.parsePositiveInteger(item?.id);
        if (createdId !== null) {
          this.itemId = createdId;
        }
      }),
    );
  }

  /**
   * Update existing product
   */
  protected override saveUpdate(dto: ProductCreateUpdateRequest): Observable<ProductDetail> {
    return this.productsApi
      .productsPartialUpdate({ id: this.itemId!, productCreateUpdateRequest: dto })
      .pipe(
        switchMap(() => this.productsApi.productsRetrieve({ id: this.itemId! })),
        tap((item) => {
          this.item.set(item);
          this.patchForm(item);
        }),
      );
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    // Call base ngOnInit for standard initialization
    super.ngOnInit();

    this.initializeWorkflowSectionAvailability();

    if (!this.isBrowser) return;

    this.loadDocumentTypes();
  }

  /**
   * Handle keyboard shortcuts - extends base class
   */
  override handleGlobalKeydown(event: KeyboardEvent): void {
    // Call base for standard shortcuts
    super.handleGlobalKeydown(event);
  }

  /**
   * Go back to list - override to preserve navigation state
   */
  protected override goBack(): void {
    const navigationState = this.getNavigationState();
    const focusState: Record<string, unknown> = { focusTable: true };
    const focusId = this.resolveFocusId();

    if (focusId !== null) {
      focusState['focusId'] = focusId;
    }

    if (navigationState.searchQuery !== null) {
      focusState['searchQuery'] = navigationState.searchQuery;
    }

    if (navigationState.page !== null) {
      focusState['page'] = navigationState.page;
    }

    this.router.navigate([this.getListRoute()], { state: focusState });
  }

  protected override navigateToEdit(id: number): void {
    if (this.getNavigationState().returnToList) {
      this.goBack();
      return;
    }

    if (this.getNavigationState().returnToDetail) {
      this.navigateToDetail(id);
      return;
    }

    super.navigateToEdit(id);
  }

  override onCancel(): void {
    this.goBack();
  }

  protected override patchForm(item: ProductDetail): void {
    this.product.set(item);
    const canViewBasePrice = this.isAdminOrManager();

    this.form.patchValue(
      {
        name: item.name ?? '',
        code: item.code ?? '',
        description: item.description ?? '',
        basePrice: canViewBasePrice
          ? item.basePrice !== null && item.basePrice !== undefined
            ? Number(item.basePrice)
            : 0
          : 0,
        retailPrice:
          item.retailPrice !== null && item.retailPrice !== undefined
            ? Number(item.retailPrice)
            : 0,
        currency: item.currency ?? this.configService.settings.baseCurrency ?? 'IDR',
        productType: item.productType ?? 'visa',
        validity: item.validity ?? null,
        documentsMinValidity: item.documentsMinValidity ?? null,
        applicationWindowDays: item.applicationWindowDays ?? null,
        validationPrompt: item.validationPrompt ?? '',
        deprecated: item.deprecated ?? false,
        requiredDocumentIds: (item.requiredDocumentTypes ?? []).map((doc) => doc.id),
        optionalDocumentIds: (item.optionalDocumentTypes ?? []).map((doc) => doc.id),
      },
      { emitEvent: false },
    );

    this.tasksArray.clear({ emitEvent: false });
    (item.tasks ?? []).forEach((task) => this.addTask(task));
    this.updateWorkflowSectionAvailability();
  }

  /**
   * Save product - override to add custom validation
   */
  override onSubmit(): void {
    if (this.form.invalid || this.hasMultipleLastSteps()) {
      this.form.markAllAsTouched();
      this.tasksArray.controls.forEach((group) => {
        group.markAllAsTouched();
        Object.values(group.controls).forEach((control) => control.markAsTouched());
      });

      if (this.hasMultipleLastSteps()) {
        this.toast.error('Only one task can be marked as the last step.');
      } else if (this.form.errors?.['retailPriceBelowBase']) {
        this.toast.error('Retail price must be greater than or equal to base price.');
      } else {
        this.toast.error('Please fix validation errors in the form (check Tasks section).');
      }
      return;
    }

    // Call base onSubmit
    super.onSubmit();
  }

  /**
   * Handle required documents change
   */
  onRequiredDocsChange(ids: number[]): void {
    this.form.get('requiredDocumentIds')?.setValue(ids);
  }

  /**
   * Handle optional documents change
   */
  onOptionalDocsChange(ids: number[]): void {
    this.form.get('optionalDocumentIds')?.setValue(ids);
  }

  /**
   * Normalize currency field
   */
  normalizeCurrency(): void {
    const control = this.form.get('currency');
    const raw = String(control?.value ?? '')
      .trim()
      .toUpperCase();
    control?.setValue(raw, { emitEvent: false });
  }

  /**
   * Add task to form array
   */
  addTask(task?: Partial<ProductTask>): void {
    const group = this.fb.group(
      {
        id: [task?.id ?? null],
        step: [task?.step ?? this.tasksArray.length + 1, Validators.required],
        name: [task?.name ?? '', Validators.required],
        description: [task?.description ?? ''],
        cost: [task?.cost ? Number(task.cost) : 0],
        duration: [task?.duration ?? 0, [Validators.required, Validators.min(0)]],
        addTaskToCalendar: [task?.addTaskToCalendar ?? false],
        notifyCustomer: [task?.notifyCustomer ?? false],
        durationIsBusinessDays: [task?.durationIsBusinessDays ?? true],
        notifyDaysBefore: [task?.notifyDaysBefore ?? 0, [Validators.min(0)]],
        lastStep: [task?.lastStep ?? false],
      },
      {
        validators: [this.taskDurationValidator],
      },
    );
    this.syncTaskNotifyCustomerAvailability(group);
    this.tasksArray.push(group);
  }

  /**
   * Remove task from form array
   */
  removeTask(index: number): void {
    this.tasksArray.removeAt(index);
    this.renumberSteps();
  }

  /**
   * Toggle last step for task
   */
  toggleLastStep(index: number): void {
    this.tasksArray.controls.forEach((group, idx) => {
      if (idx !== index) {
        group.get('lastStep')?.setValue(false, { emitEvent: false });
      }
    });
  }

  /**
   * Get documents min validity label based on product type
   */
  documentsMinValidityLabel(): string {
    return this.isVisaProductType()
      ? 'Passport min validity (days)'
      : 'Documents min validity (days)';
  }

  /**
   * Get application window days label based on product type
   */
  applicationWindowDaysLabel(): string {
    return this.isVisaProductType()
      ? 'Application window (days before stay permit expiry)'
      : 'Application window (days)';
  }

  /**
   * Whether workflow-specific UI should be shown for the selected product type.
   */
  showWorkflowSections(): boolean {
    return this.isVisaProductType();
  }

  /**
   * Get product type tooltip based on selected type
   */
  productTypeTooltip(): string {
    return this.isVisaProductType()
      ? 'Visa-specific labels and workflow guidance are enabled for this product.'
      : 'Generic product labels and workflow guidance are enabled for this product.';
  }

  /**
   * Get documents minimum validity tooltip based on product type
   */
  documentsMinValidityTooltip(): string {
    return this.isVisaProductType()
      ? 'Minimum remaining passport validity required for this visa product.'
      : 'Minimum remaining validity required for supporting documents for this product.';
  }

  /**
   * Get application window tooltip based on product type
   */
  applicationWindowDaysTooltip(): string {
    return this.isVisaProductType()
      ? "How many days before the customer's stay permit expires this product can be submitted or renewed."
      : 'How many days before the relevant deadline this product should be submitted or renewed.';
  }

  /**
   * Get AI validation prompt placeholder based on product type
   */
  validationPromptPlaceholder(): string {
    return this.isVisaProductType()
      ? "Optional product-specific context injected during AI document validation (e.g. 'Passport validity must be at least 12 months for this visa type')."
      : "Optional product-specific context injected during AI document validation (e.g. 'Supporting receipt must clearly show the paid amount and payment date').";
  }

  /**
   * Get tasks form array
   */
  get tasksArray(): FormArray<FormGroup> {
    return this.form.get('tasks') as FormArray<FormGroup>;
  }

  // Private methods

  private buildPayload(): ProductCreateUpdateRequest {
    const rawValue = this.form.getRawValue();
    const basePrice = this.isAdminOrManager() ? rawValue.basePrice : 0;
    const includeWorkflowSections = this.showWorkflowSections();
    const rawTasks = (rawValue.tasks ?? []) as ProductTaskRequest[];
    return {
      name: rawValue.name ?? '',
      code: rawValue.code ?? '',
      description: rawValue.description ?? '',
      productType: this.normalizeProductType(rawValue.productType),
      basePrice: basePrice !== null ? String(basePrice) : null,
      retailPrice: rawValue.retailPrice !== null ? String(rawValue.retailPrice) : undefined,
      currency:
        String(rawValue.currency ?? '')
          .trim()
          .toUpperCase() || undefined,
      validity: rawValue.validity,
      documentsMinValidity: rawValue.documentsMinValidity,
      applicationWindowDays: rawValue.applicationWindowDays,
      validationPrompt: rawValue.validationPrompt ?? '',
      deprecated: rawValue.deprecated ?? false,
      requiredDocumentIds: includeWorkflowSections ? rawValue.requiredDocumentIds : [],
      optionalDocumentIds: includeWorkflowSections ? rawValue.optionalDocumentIds : [],
      tasks: includeWorkflowSections
        ? rawTasks.map((t): ProductTaskRequest => {
            const task: ProductTaskRequest = {
              step: t.step,
              name: t.name,
              description: t.description,
              cost: t.cost !== null ? String(t.cost) : '0',
              duration: t.duration,
              addTaskToCalendar: t.addTaskToCalendar,
              notifyCustomer: t.notifyCustomer,
              durationIsBusinessDays: t.durationIsBusinessDays,
              notifyDaysBefore: t.notifyDaysBefore,
              lastStep: t.lastStep,
            };
            if (t.id != null) {
              task.id = t.id;
            }
            return task;
          })
        : [],
    };
  }

  private loadDocumentTypes(): void {
    this.documentTypesApi.documentTypesList({}).subscribe({
      next: (items: DocumentType[]) => this.documentTypes.set(items ?? []),
      error: () => this.toast.error('Failed to load document types'),
    });
  }

  private renumberSteps(): void {
    this.tasksArray.controls.forEach((group, index) => {
      group.get('step')?.setValue(index + 1);
    });
  }

  private syncTaskNotifyCustomerAvailability(group: FormGroup): void {
    const addToCalendarControl = group.get('addTaskToCalendar');
    if (!addToCalendarControl) {
      return;
    }

    this.applyTaskNotifyCustomerAvailability(group);
    addToCalendarControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.applyTaskNotifyCustomerAvailability(group));
  }

  private taskDurationValidator(group: FormGroup) {
    const duration = Number(group.get('duration')?.value ?? 0);
    const notify = Number(group.get('notifyDaysBefore')?.value ?? 0);
    if (notify > duration) {
      return { notifyBeforeDuration: true };
    }
    return null;
  }

  private retailPriceValidator(group: FormGroup) {
    const baseRaw = group.get('basePrice')?.value;
    const retailRaw = group.get('retailPrice')?.value;

    const base =
      baseRaw === null || baseRaw === undefined || baseRaw === '' ? null : Number(baseRaw);
    const retail =
      retailRaw === null || retailRaw === undefined || retailRaw === '' ? null : Number(retailRaw);

    if (base === null || retail === null || Number.isNaN(base) || Number.isNaN(retail)) {
      return null;
    }

    if (retail < base) {
      return { retailPriceBelowBase: true };
    }
    return null;
  }

  private normalizeProductType(value: unknown): ProductCreateUpdateRequestProductTypeEnum {
    switch (
      String(value ?? '')
        .trim()
        .toLowerCase()
    ) {
      case ProductCreateUpdateRequestProductTypeEnum.Other:
        return ProductCreateUpdateRequestProductTypeEnum.Other;
      case ProductCreateUpdateRequestProductTypeEnum.Visa:
      default:
        return ProductCreateUpdateRequestProductTypeEnum.Visa;
    }
  }

  private isVisaProductType(): boolean {
    return (
      this.normalizeProductType(this.form.get('productType')?.value) ===
      ProductCreateUpdateRequestProductTypeEnum.Visa
    );
  }

  private initializeWorkflowSectionAvailability(): void {
    const productTypeControl = this.form.get('productType');
    if (!productTypeControl) {
      return;
    }

    this.updateWorkflowSectionAvailability();
    productTypeControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.updateWorkflowSectionAvailability());
  }

  private updateWorkflowSectionAvailability(): void {
    const shouldShowWorkflowSections = this.showWorkflowSections();
    const workflowControls = [
      this.form.get('requiredDocumentIds'),
      this.form.get('optionalDocumentIds'),
      this.form.get('tasks'),
    ];

    workflowControls.forEach((control) => {
      if (!control) {
        return;
      }

      if (shouldShowWorkflowSections) {
        control.enable({ emitEvent: false });
        return;
      }

      control.disable({ emitEvent: false });
    });

    if (shouldShowWorkflowSections) {
      this.tasksArray.controls.forEach((group) => this.applyTaskNotifyCustomerAvailability(group));
    }
  }

  private applyTaskNotifyCustomerAvailability(group: FormGroup): void {
    const addToCalendarControl = group.get('addTaskToCalendar');
    const notifyCustomerControl = group.get('notifyCustomer');
    if (!addToCalendarControl || !notifyCustomerControl || group.disabled) {
      return;
    }

    if (addToCalendarControl.value) {
      notifyCustomerControl.enable({ emitEvent: false });
      return;
    }

    notifyCustomerControl.setValue(false, { emitEvent: false });
    notifyCustomerControl.disable({ emitEvent: false });
  }

  protected override getNavigationState(): ProductNavigationState {
    const currentState = this.router.getCurrentNavigation()?.extras.state as
      | Record<string, unknown>
      | undefined;
    const historyState =
      typeof window !== 'undefined'
        ? (window.history.state as Record<string, unknown> | undefined)
        : undefined;
    const mergedState = {
      ...(historyState ?? {}),
      ...(currentState ?? {}),
    };

    return {
      searchQuery:
        typeof mergedState['searchQuery'] === 'string' ? mergedState['searchQuery'] : null,
      page: this.parsePositiveInteger(mergedState['page']),
      focusId: this.parsePositiveInteger(mergedState['focusId']),
      returnToList: mergedState['returnToList'] === true,
      returnToDetail: mergedState['returnToDetail'] === true,
    };
  }

  private resolveFocusId(): number | null {
    const navigationState = this.getNavigationState();
    return (
      this.parsePositiveInteger(this.itemId) ??
      this.parsePositiveInteger(this.product()?.id) ??
      navigationState.focusId
    );
  }

  private parsePositiveInteger(value: unknown): number | null {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null;
    }
    return Math.floor(parsed);
  }
}
