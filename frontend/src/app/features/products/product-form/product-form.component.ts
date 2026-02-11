import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  DocumentTypesService,
  ProductsService,
  type DocumentType,
  type ProductCreateUpdate,
  type ProductDetail,
} from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import {
  SortableMultiSelectComponent,
  type SortableOption,
} from '@/shared/components/sortable-multi-select';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

type ProductTask = NonNullable<ProductDetail['tasks']>[number];

@Component({
  selector: 'app-product-form',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
    SortableMultiSelectComponent,
    ZardIconComponent,
    FormErrorSummaryComponent,
  ],
  templateUrl: './product-form.component.html',
  styleUrls: ['./product-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private productsApi = inject(ProductsService);
  private documentTypesApi = inject(DocumentTypesService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

  readonly isLoading = signal(false);
  readonly isSaving = signal(false);
  readonly isEditMode = signal(false);
  readonly product = signal<ProductDetail | null>(null);
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

  readonly form = this.fb.group({
    name: ['', Validators.required],
    code: ['', Validators.required],
    description: [''],
    basePrice: [0],
    productType: ['visa', Validators.required],
    validity: [null as number | null],
    documentsMinValidity: [null as number | null],
    requiredDocumentIds: [[] as number[]],
    optionalDocumentIds: [[] as number[]],
    tasks: this.fb.array<FormGroup>([]),
  });

  readonly formErrorLabels: Record<string, string> = {
    name: 'Name',
    code: 'Code',
    description: 'Description',
    basePrice: 'Base Price',
    productType: 'Product Type',
    validity: 'Validity',
    documentsMinValidity: 'Documents Min Validity',
    requiredDocumentIds: 'Required Documents',
    optionalDocumentIds: 'Optional Documents',
    tasks: 'Tasks',
  };

  readonly hasMultipleLastSteps = computed(() => {
    const tasks = this.tasksArray.controls;
    return tasks.filter((group) => group.get('lastStep')?.value).length > 1;
  });

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    // Esc --> Cancel
    if (event.key === 'Escape') {
      event.preventDefault();
      this.goBack();
      return;
    }

    // cmd+s (mac) or ctrl+s (windows/linux) --> save
    const isSaveKey = (event.ctrlKey || event.metaKey) && (event.key === 's' || event.key === 'S');
    if (isSaveKey) {
      event.preventDefault();
      this.save();
      return;
    }

    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    // B or Left Arrow --> Back to list
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

  get tasksArray(): FormArray<FormGroup> {
    return this.form.get('tasks') as FormArray<FormGroup>;
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    this.loadDocumentTypes();

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.isEditMode.set(true);
      const id = Number(idParam);
      this.loadProduct(id);
    } else {
      // Tasks are optional for new products. Do not add a default empty task here.
    }
  }

  onRequiredDocsChange(ids: number[]): void {
    this.form.get('requiredDocumentIds')?.setValue(ids);
  }

  onOptionalDocsChange(ids: number[]): void {
    this.form.get('optionalDocumentIds')?.setValue(ids);
  }

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
        durationIsBusinessDays: [task?.durationIsBusinessDays ?? true],
        notifyDaysBefore: [task?.notifyDaysBefore ?? 0, [Validators.min(0)]],
        lastStep: [task?.lastStep ?? false],
      },
      {
        validators: [this.taskDurationValidator],
      },
    );
    this.tasksArray.push(group);
  }

  removeTask(index: number): void {
    this.tasksArray.removeAt(index);
    this.renumberSteps();
  }

  goBack(): void {
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

    this.router.navigate(['/products'], { state: focusState });
  }

  toggleLastStep(index: number): void {
    this.tasksArray.controls.forEach((group, idx) => {
      if (idx !== index) {
        group.get('lastStep')?.setValue(false, { emitEvent: false });
      }
    });
  }

  save(): void {
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
      } else {
        this.toast.error('Please fix validation errors in the form (check Tasks section).');
      }
      return;
    }

    this.isSaving.set(true);
    const rawValue = this.form.getRawValue();

    // Ensure types match ProductCreateUpdate and map to snake_case for API
    const payload: ProductCreateUpdate = {
      name: rawValue.name ?? '',
      code: rawValue.code ?? '',
      description: rawValue.description ?? '',
      product_type: rawValue.productType as any,
      base_price: rawValue.basePrice !== null ? String(rawValue.basePrice) : null,
      validity: rawValue.validity,
      documents_min_validity: rawValue.documentsMinValidity,
      required_document_ids: rawValue.requiredDocumentIds,
      optional_document_ids: rawValue.optionalDocumentIds,
      tasks: (rawValue.tasks || []).map((t: any) => {
        const task: any = {
          step: t.step,
          name: t.name,
          description: t.description,
          cost: t.cost !== null ? String(t.cost) : '0',
          duration: t.duration,
          add_task_to_calendar: t.addTaskToCalendar,
          duration_is_business_days: t.durationIsBusinessDays,
          notify_days_before: t.notifyDaysBefore,
          last_step: t.lastStep,
        };
        if (t.id != null) {
          task.id = t.id;
        }
        return task;
      }),
    } as any;

    if (this.isEditMode() && this.product()) {
      this.productsApi.productsUpdate(this.product()!.id, payload).subscribe({
        next: (product: ProductCreateUpdate) => {
          this.toast.success('Product updated successfully');
          this.router.navigate(['/products', product.id]);
        },
        error: (error) => {
          applyServerErrorsToForm(this.form, error);
          this.form.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to update product: ${message}` : 'Failed to update product',
          );
          this.isSaving.set(false);
        },
      });
      return;
    }

    this.productsApi.productsCreate(payload).subscribe({
      next: (product: ProductCreateUpdate) => {
        this.toast.success('Product created successfully');
        this.router.navigate(['/products', product.id]);
      },
      error: (error) => {
        applyServerErrorsToForm(this.form, error);
        this.form.markAllAsTouched();
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to create product: ${message}` : 'Failed to create product',
        );
        this.isSaving.set(false);
      },
    });
  }

  private loadDocumentTypes(): void {
    this.documentTypesApi.documentTypesList().subscribe({
      next: (items: DocumentType[]) => this.documentTypes.set(items ?? []),
      error: () => this.toast.error('Failed to load document types'),
    });
  }

  private loadProduct(id: number): void {
    this.isLoading.set(true);
    this.productsApi.productsRetrieve(id).subscribe({
      next: (product: ProductDetail) => {
        this.product.set(product);
        this.form.patchValue({
          name: product.name ?? '',
          code: product.code ?? '',
          description: product.description ?? '',
          basePrice: product.basePrice ? Number(product.basePrice) : 0,
          productType: product.productType ?? 'visa',
          validity: product.validity ?? null,
          documentsMinValidity: product.documentsMinValidity ?? null,
          requiredDocumentIds: (product.requiredDocumentTypes ?? []).map(
            (doc: DocumentType) => doc.id,
          ),
          optionalDocumentIds: (product.optionalDocumentTypes ?? []).map(
            (doc: DocumentType) => doc.id,
          ),
        });

        this.tasksArray.clear();
        (product.tasks ?? []).forEach((task) => this.addTask(task));
        // Do not auto-add an empty task when the product has no tasks — tasks are optional.

        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load product');
        this.isLoading.set(false);
      },
    });
  }

  private renumberSteps(): void {
    this.tasksArray.controls.forEach((group, index) => {
      group.get('step')?.setValue(index + 1);
    });
  }

  private taskDurationValidator(group: FormGroup) {
    const duration = Number(group.get('duration')?.value ?? 0);
    const notify = Number(group.get('notifyDaysBefore')?.value ?? 0);
    if (notify > duration) {
      return { notifyBeforeDuration: true };
    }
    return null;
  }
}
