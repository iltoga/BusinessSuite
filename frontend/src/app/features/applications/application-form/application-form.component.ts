import { ComputeService } from '@/core/api/api/compute.service';
import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { CustomersService } from '@/core/api/api/customers.service';
import { DocumentTypesService } from '@/core/api/api/document-types.service';
import { ProductsService } from '@/core/api/api/products.service';
import type { Customer } from '@/core/api/model/customer';
import type { DocApplicationCreateUpdate } from '@/core/api/model/doc-application-create-update';
import { GlobalToastService } from '@/core/services/toast.service';
import { FormNavigationFacadeService } from '@/features/shared/services/form-navigation-facade.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ProductSelectComponent } from '@/shared/components/product-select';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';
import { Location } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  computed,
  HostListener,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import {
  AbstractControl,
  FormArray,
  FormBuilder,
  ReactiveFormsModule,
  Validators,
} from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import {
  distinctUntilChanged,
  finalize,
  map,
  of,
  pairwise,
  shareReplay,
  startWith,
  Subject,
  takeUntil,
  type Observable,
} from 'rxjs';
import { ApplicationFormDocumentsSectionComponent } from './application-form-documents-section.component';

interface ApplicationDocumentTypeOption {
  id: number;
  name: string;
  isStayPermit: boolean;
}

interface ApplicationCalendarTaskOption {
  id: number;
  step: number;
  name: string;
  addTaskToCalendar: boolean;
}

interface ProductDocumentsAdapter {
  requiredDocuments: ApplicationDocumentTypeOption[];
  optionalDocuments: ApplicationDocumentTypeOption[];
  tasks: ApplicationCalendarTaskOption[];
  calendarTask: ApplicationCalendarTaskOption | null;
}

interface ApplicationFormSnapshot {
  customerId: number | null;
  productId: number | null;
  docDate: Date;
  dueDate: Date;
  addDeadlinesToCalendar: boolean;
  notifyCustomer: boolean;
  notifyCustomerChannel: 'whatsapp' | 'email';
  notes: string;
}

interface ApplicationFormNavigationState {
  from?: string;
  focusId?: number | null;
  searchQuery?: string | null;
  returnUrl?: string;
  customerId?: number;
  page?: number;
  awaitPassportImport?: boolean;
}

@Component({
  selector: 'app-application-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardButtonComponent,
    ZardCardComponent,
    ZardIconComponent,
    ZardComboboxComponent,
    CustomerSelectComponent,
    ProductSelectComponent,
    ZardDateInputComponent,
    FormErrorSummaryComponent,
    ApplicationFormDocumentsSectionComponent,
    ...ZardTooltipImports,
  ],
  templateUrl: './application-form.component.html',
  styleUrls: ['./application-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationFormComponent implements OnInit, OnDestroy {
  private fb = inject(FormBuilder);
  private customersService = inject(CustomersService);
  private customerApplicationsService = inject(CustomerApplicationsService);
  private computeService = inject(ComputeService);
  private productsService = inject(ProductsService);
  private documentTypesService = inject(DocumentTypesService);
  private toast = inject(GlobalToastService);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private location = inject(Location);
  private cdr = inject(ChangeDetectorRef);
  private formNavigationFacade = inject(FormNavigationFacadeService);

  private destroy$ = new Subject<void>();
  private productDocumentsCache = new Map<number, ProductDocumentsAdapter>();
  private productDocumentsRequests = new Map<number, Observable<ProductDocumentsAdapter>>();

  readonly selectedCustomer = signal<Customer | null>(null);
  readonly documentTypes = signal<ApplicationDocumentTypeOption[]>([]);
  readonly isEditMode = signal(false);
  readonly applicationId = signal<number | null>(null);
  readonly isLoading = signal(false);
  readonly initialProductId = signal<number | null>(null);
  readonly nextDeadlineTaskName = signal<string | null>(null);
  // Loading state and open/closed state for the Documents panel
  readonly documentsLoading = signal(false);
  readonly documentsPanelOpen = signal(false);

  readonly form = this.fb.group({
    customer: [null as string | null, Validators.required],
    product: [null as string | null, Validators.required],
    // use Date object so z-date-input binds correctly
    docDate: [new Date(), Validators.required],
    dueDate: [new Date(), Validators.required],
    addDeadlinesToCalendar: [true],
    notifyCustomer: [false],
    notifyCustomerChannel: ['whatsapp' as 'whatsapp' | 'email'],
    notes: [''],
    documents: this.fb.array([]),
  });

  readonly formErrorLabels: Record<string, string> = {
    customer: 'Customer',
    product: 'Product',
    docDate: 'Application Submission Date',
    dueDate: 'Due Date',
    addDeadlinesToCalendar: 'Add deadlines to calendar',
    notifyCustomer: 'Notify customer',
    notifyCustomerChannel: 'Customer notification channel',
    notes: 'Notes',
    documents: 'Documents',
  };

  readonly isSubmitting = signal(false);

  private dueDateValidator = (control: AbstractControl) => {
    const docDate = this.form?.get('docDate')?.value as Date | null;
    const dueDate = control?.value as Date | null;
    if (docDate && dueDate && dueDate < docDate) {
      return { dueBeforeDocDate: true };
    }
    return null;
  };

  readonly customerNotificationOptions = computed<ZardComboboxOption[]>(() => {
    const customer = this.selectedCustomer();
    const options: ZardComboboxOption[] = [];
    if (customer?.whatsapp) {
      options.push({ value: 'whatsapp', label: 'WhatsApp' });
    }
    if (customer?.email) {
      options.push({ value: 'email', label: 'Email' });
    }
    return options;
  });

  readonly canNotifyCustomer = computed(() => this.customerNotificationOptions().length > 0);
  readonly dueDateContextLabel = computed(() => {
    const taskName = this.nextDeadlineTaskName();
    return taskName ? `(Next Deadline: ${taskName})` : '(Next Deadline: —)';
  });

  readonly documentTypeOptions = computed<ZardComboboxOption[]>(() => {
    return this.documentTypes().map((dt) => ({
      value: String(dt.id),
      label: dt.name,
    }));
  });

  /**
   * Track selected document type IDs to filter them out from other rows' options.
   */
  readonly selectedDocTypeIds = toSignal(
    this.form.get('documents')!.valueChanges.pipe(
      startWith(this.form.get('documents')!.value),
      map((docs) =>
        (Array.isArray(docs) ? docs : [])
          .map((d) => {
            const doc = d as { docTypeId?: string | number | null };
            return doc?.docTypeId ? String(doc.docTypeId) : '';
          })
          .filter((id: string) => id !== ''),
      ),
    ),
    { initialValue: [] as string[] },
  );
  readonly stayPermitDocTypeIds = computed(() =>
    this.documentTypes()
      .filter((doc) => doc.isStayPermit)
      .map((doc) => String(doc.id)),
  );

  get documentsArray() {
    return this.form.get('documents') as FormArray;
  }

  ngOnInit(): void {
    this.form.get('dueDate')?.setValidators([Validators.required, this.dueDateValidator]);
    this.form.get('notifyCustomerChannel')?.disable({ emitEvent: false });
    const url = this.router.url;
    const editMatch = url.match(/\/applications\/(\d+)\/edit/);

    if (editMatch) {
      // Edit mode: /applications/:id/edit
      const id = Number(editMatch[1]);
      this.isEditMode.set(true);
      this.applicationId.set(id);
      this.setEditModeControls(true);
      this.loadApplication(id);
    } else {
      // Create mode - check if customer is pre-selected
      this.setEditModeControls(false);
      const customerIdParam = this.route.snapshot.paramMap.get('id');
      if (customerIdParam) {
        this.form.patchValue({ customer: customerIdParam });
        this.loadCustomerDetail(Number(customerIdParam));
      }

      // Load customer detail when customer ID changes
      this.form
        .get('customer')
        ?.valueChanges.pipe(distinctUntilChanged(), takeUntil(this.destroy$))
        .subscribe((customerId) => {
          if (customerId) {
            this.loadCustomerDetail(Number(customerId));
          } else {
            this.selectedCustomer.set(null);
            this.syncNotifyCustomerAvailability();
            // If product is set, reload docs (to re-evaluate without customer)
            const productId = this.form.get('product')?.value;
            if (productId) {
              this.loadProductDocuments(Number(productId));
            }
          }
        });

      // Load product documents when product changes
      this.form
        .get('product')
        ?.valueChanges.pipe(distinctUntilChanged(), takeUntil(this.destroy$))
        .subscribe((productId) => {
          if (!productId) {
            this.documentsArray.clear();
            this.nextDeadlineTaskName.set(null);
            return;
          }
          this.loadProductDocuments(Number(productId));
        });
    }

    this.form
      .get('docDate')
      ?.valueChanges.pipe(
        startWith(this.form.get('docDate')?.value),
        pairwise(),
        takeUntil(this.destroy$),
      )
      .subscribe(([previousDocDateRaw, currentDocDateRaw]) => {
        this.form.get('dueDate')?.updateValueAndValidity();

        const previousDocDate = this.toDateOnly(previousDocDateRaw);
        const currentDocDate = this.toDateOnly(currentDocDateRaw);
        const currentDueDate = this.toDateOnly(this.form.get('dueDate')?.value);

        if (!previousDocDate || !currentDocDate || !currentDueDate) {
          return;
        }

        const dayDelta = this.diffInDays(previousDocDate, currentDocDate);
        if (dayDelta === 0) {
          return;
        }

        this.form.patchValue(
          { dueDate: this.addDays(currentDueDate, dayDelta) },
          { emitEvent: false },
        );
      });

    this.form
      .get('product')
      ?.valueChanges.pipe(distinctUntilChanged(), takeUntil(this.destroy$))
      .subscribe((productId) => {
        if (!productId) return;
        const numericProductId = Number(productId);
        if (this.isEditMode() && this.initialProductId() === numericProductId) {
          return;
        }
        this.tryAutoDueDateCalculation(numericProductId);
      });

    this.form
      .get('notifyCustomer')
      ?.valueChanges.pipe(takeUntil(this.destroy$))
      .subscribe((enabled) => {
        const channelControl = this.form.get('notifyCustomerChannel');
        if (!enabled) {
          this.form.patchValue({ notifyCustomerChannel: 'whatsapp' }, { emitEvent: false });
          channelControl?.disable({ emitEvent: false });
          return;
        }
        if (this.canNotifyCustomer()) {
          channelControl?.enable({ emitEvent: false });
        }
      });

    // Ensure initial disabled/enabled state is correct before any customer is selected.
    this.syncNotifyCustomerAvailability();
    this.loadDocumentTypes();
  }

  private loadApplication(id: number): void {
    this.isLoading.set(true);
    this.customerApplicationsService.customerApplicationsRetrieve(id).subscribe({
      next: (rawApp) => {
        const app = this.adaptApplicationSnapshot(rawApp);
        this.form.patchValue(
          {
            customer: app.customerId ? String(app.customerId) : null,
            product: app.productId ? String(app.productId) : null,
            docDate: app.docDate,
            dueDate: app.dueDate,
            addDeadlinesToCalendar: app.addDeadlinesToCalendar,
            notifyCustomer: app.notifyCustomer,
            notifyCustomerChannel: app.notifyCustomerChannel,
            notes: app.notes,
          },
          { emitEvent: false },
        );
        if (app.customerId) {
          this.loadCustomerDetail(app.customerId);
        }

        // Ensure product documents are loaded when editing an application
        if (app.productId) {
          this.initialProductId.set(app.productId);
          // open the documents panel and load documents
          this.documentsPanelOpen.set(true);
          this.loadProductDocuments(app.productId);
        }

        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load application');
        this.isLoading.set(false);
      },
    });
  }

  private loadCustomerDetail(customerId: number): void {
    this.customersService.customersRetrieve(customerId).subscribe({
      next: (customer) => {
        this.selectedCustomer.set(customer);
        this.syncNotifyCustomerAvailability();
        // Refresh documents if product is already selected to re-check for auto-imports
        const productId = this.form.get('product')?.value;
        if (productId && !this.isEditMode()) {
          this.loadProductDocuments(Number(productId));
        }
      },
      error: () => {
        this.selectedCustomer.set(null);
        this.syncNotifyCustomerAvailability();
      },
    });
  }

  private loadDocumentTypes() {
    this.documentTypesService.documentTypesList().subscribe({
      next: (res) => this.documentTypes.set(this.adaptDocumentTypes(res)),
      error: () => this.toast.error('Failed to load document types'),
    });
  }

  private loadProductDocuments(productId: number) {
    // Show loader and ensure the documents panel is opened
    this.documentsLoading.set(true);
    this.documentsPanelOpen.set(true);

    this.getProductDocuments(productId).subscribe({
      next: (rawData) => {
        const data = rawData;
        const deadlineTask = data.calendarTask;
        // Do not clear an already computed label from productsRetrieve() if this
        // lighter endpoint does not include task details.
        if (deadlineTask) {
          this.nextDeadlineTaskName.set(this.getTaskName(deadlineTask));
        }

        this.documentsArray.clear();
        let stayPermitAdded = false;
        const processDocs = (docs: ApplicationDocumentTypeOption[], required: boolean) => {
          docs.forEach((dt) => {
            if (dt.isStayPermit) {
              if (stayPermitAdded) {
                return;
              }
              stayPermitAdded = true;
            }
            if (this.checkPassportAutoImport(dt.id)) {
              return; // Skip adding to form correctly
            }
            this.addDocument(dt.id, required);
          });
        };

        processDocs(data.requiredDocuments, true);
        processDocs(data.optionalDocuments, false);

        this.documentsLoading.set(false);
        // ensure template updates under OnPush
        this.cdr.markForCheck();
      },
      error: () => {
        this.nextDeadlineTaskName.set(null);
        this.documentsLoading.set(false);
        this.cdr.markForCheck();
        this.toast.error('Failed to load product documents');
      },
    });
  }

  /**
   * Check if passport can be auto-imported for the selected customer.
   */
  private checkPassportAutoImport(docTypeId: number | string): boolean {
    const customerId = this.form.get('customer')?.value;
    if (!customerId) return false;

    // Find if this docTypeId corresponds to "Passport"
    const docType = this.documentTypes().find((dt) => String(dt.id) === String(docTypeId));
    if (docType?.name !== 'Passport') return false;

    const customer = this.selectedCustomer();
    if (!customer) return false;

    // Check if customer has passport file and number
    return !!(customer.passportFile && customer.passportNumber);
  }

  addDocument(docTypeId: number | string = '', required = true) {
    // Ensure panel is open when a document is added manually
    this.documentsPanelOpen.set(true);

    if (docTypeId && this.wouldCreateDuplicateStayPermit(docTypeId)) {
      this.toast.error('Only one stay permit document type can be added to an application.');
      return;
    }

    const docGroup = this.fb.group({
      docTypeId: [String(docTypeId), Validators.required],
      required: [required],
    });
    this.documentsArray.push(docGroup);
  }

  removeDocument(index: number) {
    this.documentsArray.removeAt(index);
  }

  /**
   * Called when the `Product` select emits a change. Ensure the product control
   * is synchronized and immediately load the product's documents so they appear
   * straight away in the UI.
   */
  onProductSelected(productId: number | null): void {
    if (productId) {
      const current = this.form.get('product')?.value;
      // Keep the form value as a string (existing code uses strings elsewhere)
      const asString = String(productId);
      if (current !== asString) {
        this.form.patchValue({ product: asString });
      }
      // Open panel - loading will be handled by valueChanges subscription
      this.documentsPanelOpen.set(true);
    } else {
      // Clear selection and any document rows and close panel
      this.form.patchValue({ product: null });
      this.documentsArray.clear();
      this.documentsPanelOpen.set(false);
    }
  }

  private setEditModeControls(disabled: boolean): void {
    const customerControl = this.form.get('customer');
    const productControl = this.form.get('product');

    if (disabled) {
      customerControl?.disable({ emitEvent: false });
      productControl?.enable({ emitEvent: false });
    } else {
      customerControl?.enable({ emitEvent: false });
      productControl?.enable({ emitEvent: false });
    }
  }

  private tryAutoDueDateCalculation(productId: number): void {
    this.getProductDocuments(productId).subscribe({
      next: (productDetails) => {
        const task = this.getCalendarTaskFromProduct(productDetails);
        this.nextDeadlineTaskName.set(this.getTaskName(task));
        const doc = this.toDateOnly(this.form.get('docDate')?.value);
        if (!doc) return;
        if (!task) {
          this.form.patchValue({ dueDate: doc });
          return;
        }
        const start = this.toApiDate(doc);
        if (!start) return;
        this.computeService.computeDocWorkflowDueDateRetrieve(start, task.id).subscribe({
          next: (res) => {
            const payload = this.toRecord(res);
            const computedDueDate = payload?.['dueDate'];
            if (!computedDueDate) return;
            const parsedDueDate = this.toDateOnly(computedDueDate);
            if (!parsedDueDate) return;
            this.form.patchValue({ dueDate: parsedDueDate }, { emitEvent: false });
          },
        });
      },
    });
  }

  private getProductDocuments(productId: number): Observable<ProductDocumentsAdapter> {
    const cached = this.productDocumentsCache.get(productId);
    if (cached) {
      return of(cached);
    }

    const inflight = this.productDocumentsRequests.get(productId);
    if (inflight) {
      return inflight;
    }

    const request$ = this.productsService.productsGetProductByIdRetrieve(productId).pipe(
      map((rawData) => this.adaptProductDocuments(rawData)),
      map((data) => {
        this.productDocumentsCache.set(productId, data);
        return data;
      }),
      finalize(() => {
        this.productDocumentsRequests.delete(productId);
      }),
      shareReplay(1),
    );

    this.productDocumentsRequests.set(productId, request$);
    return request$;
  }

  private getCalendarTaskFromProduct(product: unknown): ApplicationCalendarTaskOption | null {
    const adapted = this.adaptProductDocuments(product);
    if (adapted.calendarTask) {
      return adapted.calendarTask;
    }
    if (!adapted.tasks.length) {
      return null;
    }
    const sortedTasks = [...adapted.tasks].sort((a, b) => a.step - b.step);
    return sortedTasks[0] ?? null;
  }

  private getTaskName(task: ApplicationCalendarTaskOption | null): string | null {
    const rawName = typeof task?.name === 'string' ? task.name.trim() : '';
    return rawName || null;
  }

  private syncNotifyCustomerAvailability(): void {
    const notifyControl = this.form.get('notifyCustomer');
    const channelControl = this.form.get('notifyCustomerChannel');
    const options = this.customerNotificationOptions();
    const canNotify = options.length > 0;

    if (!canNotify) {
      this.form.patchValue(
        { notifyCustomer: false, notifyCustomerChannel: 'whatsapp' },
        { emitEvent: false },
      );
      notifyControl?.disable({ emitEvent: false });
      channelControl?.disable({ emitEvent: false });
      return;
    }

    notifyControl?.enable({ emitEvent: false });
    const current = this.form.get('notifyCustomerChannel')?.value;
    if (!options.some((opt) => opt.value === current)) {
      this.form.patchValue(
        { notifyCustomerChannel: options[0]!.value as 'whatsapp' | 'email' },
        { emitEvent: false },
      );
    }

    if (notifyControl?.value) {
      channelControl?.enable({ emitEvent: false });
    } else {
      channelControl?.disable({ emitEvent: false });
    }
  }

  submit(): void {
    if (this.form.invalid) {
      // mark fields as touched to show validation
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);
    const sourceState = (history.state as ApplicationFormNavigationState) || {};
    const detailState: Record<string, unknown> = {
      from: sourceState.from ?? 'applications',
      focusId: sourceState.focusId ?? null,
      searchQuery: sourceState.searchQuery ?? null,
      returnUrl: sourceState.returnUrl,
      customerId: sourceState.customerId,
    };
    const sourcePage = Number(sourceState.page);
    if (Number.isFinite(sourcePage) && sourcePage > 0) {
      detailState['page'] = Math.floor(sourcePage);
    }

    const docDateStr = this.toApiDate(this.form.value.docDate);
    if (!docDateStr) {
      this.toast.error('Application submission date is required');
      this.isSubmitting.set(false);
      return;
    }

    if (this.isEditMode() && this.applicationId()) {
      // Update mode
      const dueDateStr = this.toApiDate(this.form.value.dueDate);
      const payload: Omit<DocApplicationCreateUpdate, 'id'> = {
        customer: Number(this.form.getRawValue().customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        dueDate: dueDateStr,
        addDeadlinesToCalendar: this.form.value.addDeadlinesToCalendar ?? undefined,
        notifyCustomerToo: this.form.value.notifyCustomer ?? undefined,
        notifyCustomerChannel: this.form.value.notifyCustomer
          ? this.form.value.notifyCustomerChannel
          : null,
        notes: this.form.value.notes,
      };

      this.customerApplicationsService
        .customerApplicationsPartialUpdate(
          this.applicationId()!,
          payload as unknown as DocApplicationCreateUpdate,
        )
        .subscribe({
          next: (application) => {
            this.toast.success('Application updated');
            const id = application?.id ?? this.applicationId();
            this.router.navigate(['/applications', id], { state: detailState });
            this.isSubmitting.set(false);
          },
          error: (error) => {
            applyServerErrorsToForm(this.form, error);
            this.form.markAllAsTouched();
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message ? `Failed to update application: ${message}` : 'Failed to update application',
            );
            this.isSubmitting.set(false);
          },
        });
    } else {
      // Create mode
      const dueDateStr = this.toApiDate(this.form.value.dueDate);
      const payload: Omit<DocApplicationCreateUpdate, 'id'> = {
        customer: Number(this.form.getRawValue().customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        dueDate: dueDateStr,
        addDeadlinesToCalendar: this.form.value.addDeadlinesToCalendar ?? undefined,
        notifyCustomerToo: this.form.value.notifyCustomer ?? undefined,
        notifyCustomerChannel: this.form.value.notifyCustomer
          ? this.form.value.notifyCustomerChannel
          : null,
        notes: this.form.value.notes,
        documentTypes: this.form.value.documents as Array<Record<string, unknown>>,
      };

      this.customerApplicationsService
        .customerApplicationsCreate(payload as unknown as DocApplicationCreateUpdate)
        .subscribe({
          next: (application) => {
            this.toast.success('Application created');
            const id = application?.id;
            if (id) {
              detailState['awaitPassportImport'] = this.shouldAwaitPassportImport(application);
              this.router.navigate(['/applications', id], { state: detailState });
            } else {
              this.router.navigate(['/applications'], {
                state: {
                  focusTable: true,
                  searchQuery: sourceState.searchQuery ?? null,
                  page:
                    Number.isFinite(sourcePage) && sourcePage > 0
                      ? Math.floor(sourcePage)
                      : undefined,
                },
              });
            }
            this.isSubmitting.set(false);
          },
          error: (error) => {
            applyServerErrorsToForm(this.form, error);
            this.form.markAllAsTouched();
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message ? `Failed to create application: ${message}` : 'Failed to create application',
            );
            this.isSubmitting.set(false);
          },
        });
    }
  }

  /**
   * Navigate back to the view that opened this form.
   * Uses navigation state `from` if present, then browser history, then sensible fallbacks.
   */
  goBack(): void {
    this.formNavigationFacade.goBackFromApplicationForm({
      router: this.router,
      route: this.route,
      location: this.location,
      applicationId: this.applicationId(),
      isEditMode: this.isEditMode(),
      selectedCustomerId: this.form.value.customer,
    });
  }

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
  }

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
      this.submit();
      return;
    }

    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    // B or Left Arrow -> Go back to list that opened the view and focus originating row
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

  private adaptApplicationSnapshot(raw: unknown): ApplicationFormSnapshot {
    const source = this.toRecord(raw);
    const docDate = this.toDateOnly(source?.['docDate']) ?? new Date();
    const dueDate = this.toDateOnly(source?.['dueDate']) ?? docDate;
    const notifyCustomerRaw = source?.['notifyCustomer'] ?? source?.['notifyCustomerToo'];
    const notifyChannelRaw = source?.['notifyCustomerChannel'];
    const notifyCustomerChannel: 'whatsapp' | 'email' =
      notifyChannelRaw === 'email' ? 'email' : 'whatsapp';

    return {
      customerId: this.toNumber(
        source?.['customer'] ?? this.toRecord(source?.['customer'])?.['id'],
      ),
      productId: this.toNumber(source?.['product'] ?? this.toRecord(source?.['product'])?.['id']),
      docDate,
      dueDate,
      addDeadlinesToCalendar: Boolean(source?.['addDeadlinesToCalendar'] ?? true),
      notifyCustomer: Boolean(notifyCustomerRaw),
      notifyCustomerChannel,
      notes: typeof source?.['notes'] === 'string' ? source['notes'] : '',
    };
  }

  private adaptDocumentTypes(raw: unknown): ApplicationDocumentTypeOption[] {
    if (!Array.isArray(raw)) {
      return [];
    }
    return raw
      .map((entry) => this.toRecord(entry))
      .filter((entry): entry is Record<string, unknown> => !!entry)
      .map((entry) => ({
        id: this.toNumber(entry['id']) ?? 0,
        name: typeof entry['name'] === 'string' ? entry['name'] : '',
        isStayPermit: Boolean(entry['isStayPermit'] ?? entry['is_stay_permit']),
      }))
      .filter((entry) => entry.id > 0 && entry.name.length > 0);
  }

  private adaptProductDocuments(raw: unknown): ProductDocumentsAdapter {
    const source = this.toRecord(raw);
    const productContainer = this.toRecord(source?.['product']) ?? source;
    const explicitTask = this.adaptCalendarTask(source?.['calendarTask']);

    const tasks = Array.isArray(productContainer?.['tasks'])
      ? (productContainer['tasks'] as unknown[])
          .map((task) => this.adaptCalendarTask(task))
          .filter((task): task is ApplicationCalendarTaskOption => !!task)
      : [];

    const calendarTask = explicitTask ?? tasks.find((task) => task.addTaskToCalendar) ?? null;

    return {
      requiredDocuments: this.adaptDocumentTypes(source?.['requiredDocuments']),
      optionalDocuments: this.adaptDocumentTypes(source?.['optionalDocuments']),
      tasks,
      calendarTask,
    };
  }

  private adaptCalendarTask(raw: unknown): ApplicationCalendarTaskOption | null {
    const source = this.toRecord(raw);
    if (!source) {
      return null;
    }
    const id = this.toNumber(source['id']);
    if (!id) {
      return null;
    }
    return {
      id,
      step: this.toNumber(source['step']) ?? 0,
      name: typeof source['name'] === 'string' ? source['name'] : '',
      addTaskToCalendar: Boolean(source['addTaskToCalendar']),
    };
  }

  private wouldCreateDuplicateStayPermit(docTypeId: number | string): boolean {
    const target = this.documentTypes().find((doc) => String(doc.id) === String(docTypeId));
    if (!target?.isStayPermit) {
      return false;
    }

    return this.documentsArray.controls.some((control) => {
      const currentId = String(control.get('docTypeId')?.value ?? '');
      if (!currentId || currentId === String(docTypeId)) {
        return false;
      }
      const currentDoc = this.documentTypes().find((doc) => String(doc.id) === currentId);
      return Boolean(currentDoc?.isStayPermit);
    });
  }

  private toRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  }

  private toNumber(value: unknown): number | null {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private toDateOnly(raw: unknown): Date | null {
    if (raw == null) return null;

    if (raw instanceof Date) {
      if (Number.isNaN(raw.getTime())) return null;
      return new Date(raw.getFullYear(), raw.getMonth(), raw.getDate());
    }

    if (typeof raw === 'string') {
      const isoDateMatch = raw.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (isoDateMatch) {
        const [, year, month, day] = isoDateMatch;
        return new Date(Number(year), Number(month) - 1, Number(day));
      }
      const parsed = new Date(raw);
      if (!Number.isNaN(parsed.getTime())) {
        return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
      }
    }

    return null;
  }

  private toApiDate(raw: unknown): string | null {
    const date = this.toDateOnly(raw);
    if (!date) return null;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private shouldAwaitPassportImport(application: unknown): boolean {
    const raw = this.toRecord(application);
    if (!raw) {
      return false;
    }

    const product = this.toRecord(raw['product']);
    const documents = Array.isArray(raw['documents']) ? raw['documents'] : [];
    const configuredDocumentNames = new Set(
      [
        ...this.parseDocumentNames(product?.['requiredDocuments']),
        ...this.parseDocumentNames(product?.['optionalDocuments']),
      ].map((name) => name.toLowerCase()),
    );

    if (!configuredDocumentNames.has('passport')) {
      return false;
    }

    return !documents.some((document) => {
      const rawDocument = this.toRecord(document);
      const docType = this.toRecord(rawDocument?.['docType'] ?? rawDocument?.['doc_type']);
      const docTypeName = docType?.['name'];
      return typeof docTypeName === 'string' && docTypeName.trim().toLowerCase() === 'passport';
    });
  }

  private parseDocumentNames(value: unknown): string[] {
    if (typeof value !== 'string' || !value.trim()) {
      return [];
    }
    return value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }

  private diffInDays(from: Date, to: Date): number {
    const fromUtc = Date.UTC(from.getFullYear(), from.getMonth(), from.getDate());
    const toUtc = Date.UTC(to.getFullYear(), to.getMonth(), to.getDate());
    return Math.round((toUtc - fromUtc) / (24 * 60 * 60 * 1000));
  }

  private addDays(date: Date, days: number): Date {
    const next = new Date(date.getFullYear(), date.getMonth(), date.getDate());
    next.setDate(next.getDate() + days);
    return next;
  }
}
