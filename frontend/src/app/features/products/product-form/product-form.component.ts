import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
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
      this.addTask();
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

  toggleLastStep(index: number): void {
    this.tasksArray.controls.forEach((group, idx) => {
      if (idx !== index) {
        group.get('lastStep')?.setValue(false, { emitEvent: false });
      }
    });
  }

  save(): void {
    if (this.form.invalid || this.hasMultipleLastSteps()) {
      this.toast.error('Please fix validation errors before saving.');
      return;
    }

    this.isSaving.set(true);
    const rawValue = this.form.getRawValue();

    // Ensure types match ProductCreateUpdate (especially decimal strings)
    const payload: ProductCreateUpdate = {
      ...(rawValue as any),
      basePrice: rawValue.basePrice !== null ? String(rawValue.basePrice) : null,
      tasks: (rawValue.tasks || []).map((t: any) => ({
        ...t,
        cost: t.cost !== null ? String(t.cost) : '0',
      })),
    };

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
        if ((product.tasks ?? []).length === 0) {
          this.addTask();
        }

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
