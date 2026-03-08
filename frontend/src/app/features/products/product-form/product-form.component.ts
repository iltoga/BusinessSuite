import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Observable } from 'rxjs';

import {
  DocumentTypesService,
  ProductsService,
  type DocumentType,
  type ProductCreateUpdate,
  type ProductDetail,
} from '@/core/api';
import { ConfigService } from '@/core/services/config.service';
import {
  BaseFormComponent,
  BaseFormConfig,
} from '@/shared/core/base-form.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import {
  SortableMultiSelectComponent,
  type SortableOption,
} from '@/shared/components/sortable-multi-select';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

type ProductTask = NonNullable<ProductDetail['tasks']>[number];

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
    CommonModule,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
    SortableMultiSelectComponent,
    ZardIconComponent,
    ...ZardTooltipImports,
    FormErrorSummaryComponent,
  ],
  templateUrl: './product-form.component.html',
  styleUrls: ['./product-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductFormComponent extends BaseFormComponent<
  ProductDetail,
  ProductCreateUpdate,
  ProductCreateUpdate
> implements OnInit {
  private readonly productsApi = inject(ProductsService);
  private readonly documentTypesApi = inject(DocumentTypesService);
  private readonly configService = inject(ConfigService);

  // Product-specific state
  readonly documentTypes = signal<DocumentType[]>([]);

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
  };

  // Field tooltips
  override readonly fieldTooltips: Record<string, string> = {
    name: 'Display name shown to your team when selecting this product.',
    code: 'Unique internal code used in search, reports, and references.',
    productType: 'Controls visa-specific labels and related workflow expectations.',
    currency: '2-3 letter currency code used for pricing (for example IDR or USD).',
    basePrice: 'Your internal/base cost for this product.',
    retailPrice: 'Customer-facing price. It must be equal to or higher than base price.',
    validity: 'How many days the product outcome remains valid (optional).',
    documentsMinValidity:
      'Minimum remaining validity required for supporting documents (for visa, usually passport validity).',
    applicationWindowDays:
      "How many days before expiry of the customer's Stay Permit this product can be submitted or renewed.",
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
  };

  constructor() {
    super();
    this.config = {
      entityType: 'products',
      entityLabel: 'Product',
    } as BaseFormConfig<ProductDetail, ProductCreateUpdate, ProductCreateUpdate>;
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
    return this.productsApi.productsRetrieve(id);
  }

  /**
   * Create DTO from form value
   */
  protected override createDto(): ProductCreateUpdate {
    return this.buildPayload();
  }

  /**
   * Update DTO from form value
   */
  protected override updateDto(): ProductCreateUpdate {
    return this.buildPayload();
  }

  /**
   * Save new product
   */
  protected override saveCreate(dto: ProductCreateUpdate): Observable<any> {
    return this.productsApi.productsCreate(dto);
  }

  /**
   * Update existing product
   */
  protected override saveUpdate(dto: ProductCreateUpdate): Observable<any> {
    return this.productsApi.productsUpdate(this.itemId!, dto);
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    // Call base ngOnInit for standard initialization
    super.ngOnInit();

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
  override onCancel(): void {
    this.navigateBack();
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

      console.group('Product Form Validation Errors');
      Object.keys(this.form.controls).forEach((key) => {
        const control = this.form.get(key);
        if (control?.invalid) {
          console.error(`Field "${key}" is invalid:`, control.errors);
        }
      });
      this.tasksArray.controls.forEach((group, index) => {
        if (group.invalid) {
          console.error(`Task ${index + 1} is invalid:`, group.errors);
          Object.keys(group.controls).forEach((key) => {
            if (group.get(key)?.invalid) {
              console.error(`  - Task field "${key}" is invalid:`, group.get(key)?.errors);
            }
          });
        }
      });
      console.groupEnd();

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
    return this.form.get('productType')?.value === 'visa'
      ? 'Passport min validity (days)'
      : 'Documents min validity (days)';
  }

  /**
   * Get application window days label based on product type
   */
  applicationWindowDaysLabel(): string {
    return this.form.get('productType')?.value === 'visa'
      ? 'Application window (days before stay permit expiry)'
      : 'Application window (days)';
  }

  /**
   * Get tasks form array
   */
  get tasksArray(): FormArray<FormGroup> {
    return this.form.get('tasks') as FormArray<FormGroup>;
  }

  // Private methods

  private buildPayload(): ProductCreateUpdate {
    const rawValue = this.form.getRawValue();
    const sourceState = (history.state as any) || {};
    const detailNavigationState: Record<string, unknown> = {
      from: sourceState.from ?? 'products',
      searchQuery: sourceState.searchQuery ?? null,
    };
    const sourcePage = Number(sourceState.page);
    if (Number.isFinite(sourcePage) && sourcePage > 0) {
      detailNavigationState['page'] = Math.floor(sourcePage);
    }

    return {
      id: this.product()?.id ?? 0,
      name: rawValue.name ?? '',
      code: rawValue.code ?? '',
      description: rawValue.description ?? '',
      productType: rawValue.productType as ProductCreateUpdate.ProductTypeEnum,
      basePrice: rawValue.basePrice !== null ? String(rawValue.basePrice) : null,
      retailPrice: rawValue.retailPrice !== null ? String(rawValue.retailPrice) : undefined,
      currency:
        String(rawValue.currency ?? '')
          .trim()
          .toUpperCase() || undefined,
      validity: rawValue.validity,
      documentsMinValidity: rawValue.documentsMinValidity,
      applicationWindowDays: rawValue.applicationWindowDays,
      validationPrompt: rawValue.validationPrompt ?? '',
      requiredDocumentIds: rawValue.requiredDocumentIds,
      optionalDocumentIds: rawValue.optionalDocumentIds,
      tasks: (rawValue.tasks || []).map((t: any) => {
        const task: any = {
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
      }),
    };
  }

  private loadDocumentTypes(): void {
    this.documentTypesApi.documentTypesList().subscribe({
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
    const notifyCustomerControl = group.get('notifyCustomer');
    if (!addToCalendarControl || !notifyCustomerControl) {
      return;
    }

    const applyState = (enabled: boolean) => {
      if (enabled) {
        notifyCustomerControl.enable({ emitEvent: false });
        return;
      }
      notifyCustomerControl.setValue(false, { emitEvent: false });
      notifyCustomerControl.disable({ emitEvent: false });
    };

    applyState(Boolean(addToCalendarControl.value));
    addToCalendarControl.valueChanges.subscribe((enabled) => applyState(Boolean(enabled)));
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

  private navigateBack(): void {
    const nav = this.router.getCurrentNavigation();
    const st = (nav && nav.extras && (nav.extras.state as any)) || (history.state as any);

    const focusState: Record<string, unknown> = { focusTable: true };
    if (st?.focusId) {
      focusState['focusId'] = st.focusId;
    } else if (this.product()?.id) {
      focusState['focusId'] = this.product()?.id;
    }
    if (st?.searchQuery) {
      focusState['searchQuery'] = st.searchQuery;
    }
    const page = Number(st?.page);
    if (Number.isFinite(page) && page > 0) {
      focusState['page'] = Math.floor(page);
    }

    this.router.navigate(['/products'], { state: focusState });
  }
}
