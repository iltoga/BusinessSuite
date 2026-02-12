import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { ComputeService } from '@/core/api/api/compute.service';
import { CustomersService } from '@/core/api/api/customers.service';
import { DocumentTypesService } from '@/core/api/api/document-types.service';
import { ProductsService } from '@/core/api/api/products.service';
import type { Customer } from '@/core/api/model/customer';
import { AuthService } from '@/core/services/auth.service';
import { JobService } from '@/core/services/job.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ProductSelectComponent } from '@/shared/components/product-select';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { TypeaheadComboboxComponent } from '@/shared/components/typeahead-combobox';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';
import { CommonModule, Location } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
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
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { map, pairwise, startWith, Subject, takeUntil } from 'rxjs';

@Component({
  selector: 'app-application-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
    ZardIconComponent,
    ZardInputDirective,
    ZardComboboxComponent,
    CustomerSelectComponent,
    ProductSelectComponent,
    TypeaheadComboboxComponent,
    ZardDateInputComponent,
    FormErrorSummaryComponent,
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
  private authService = inject(AuthService);
  private jobService = inject(JobService);
  private toast = inject(GlobalToastService);
  private http = inject(HttpClient);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private location = inject(Location);
  private cdr = inject(ChangeDetectorRef);

  private destroy$ = new Subject<void>();

  readonly selectedCustomer = signal<Customer | null>(null);
  readonly documentTypes = signal<any[]>([]);
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
    docDate: 'Document Date',
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
        (docs || [])
          .map((d: any) => (d?.docTypeId ? String(d.docTypeId) : ''))
          .filter((id: string) => id !== ''),
      ),
    ),
    { initialValue: [] as string[] },
  );

  /**
   * Filter document type options for a specific row to exclude already selected types,
   * but keep the currently selected type for that row in the list.
   */
  getFilteredDocumentTypes(index: number): ZardComboboxOption[] {
    const allOptions = this.documentTypeOptions();
    const currentSelected = String(this.documentsArray.at(index).get('docTypeId')?.value || '');
    const otherSelected = this.selectedDocTypeIds().filter((_, i) => i !== index);

    return allOptions.filter(
      (opt) => opt.value === currentSelected || !otherSelected.includes(opt.value),
    );
  }

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
        ?.valueChanges.pipe(takeUntil(this.destroy$))
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
        ?.valueChanges.pipe(takeUntil(this.destroy$))
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
      ?.valueChanges.pipe(takeUntil(this.destroy$))
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
      next: (app: any) => {
        const docDate = app.docDate ? new Date(app.docDate) : new Date();
        const customerId = Number(app.customer?.id ?? app.customer);
        const productId = Number(app.product?.id ?? app.product);
        this.form.patchValue({
          customer: String(customerId),
          product: productId ? String(productId) : null,
          docDate: docDate,
          dueDate: app.dueDate ? new Date(app.dueDate) : docDate,
          addDeadlinesToCalendar: app.addDeadlinesToCalendar ?? true,
          notifyCustomer: app.notifyCustomer ?? false,
          notifyCustomerChannel: app.notifyCustomerChannel ?? 'whatsapp',
          notes: app.notes ?? '',
        }, { emitEvent: false });
        if (customerId) {
          this.loadCustomerDetail(customerId);
        }

        // Ensure product documents are loaded when editing an application
        if (productId) {
          this.initialProductId.set(productId);
          // open the documents panel and load documents
          this.documentsPanelOpen.set(true);
          this.loadProductDocuments(productId);
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
      next: (res) => this.documentTypes.set(res ?? []),
      error: () => this.toast.error('Failed to load document types'),
    });
  }

  private loadProductDocuments(productId: number) {
    // Show loader and ensure the documents panel is opened
    this.documentsLoading.set(true);
    this.documentsPanelOpen.set(true);

    this.productsService.productsGetProductByIdRetrieve(productId).subscribe({
      next: (data: any) => {
        const deadlineTask = this.getCalendarTaskFromProduct(data);
        this.nextDeadlineTaskName.set(this.getTaskName(deadlineTask));

        this.documentsArray.clear();
        let passportAutoImported = false;

        const processDocs = (docs: any[], required: boolean) => {
          if (!docs) return;
          docs.forEach((dt: any) => {
            if (this.checkPassportAutoImport(dt.id)) {
              passportAutoImported = true;
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
    this.productsService.productsRetrieve(productId).subscribe({
      next: (product: any) => {
        const task = this.getCalendarTaskFromProduct(product);
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
            const computedDueDate = res?.dueDate ?? res?.due_date;
            if (!computedDueDate) return;
            const parsedDueDate = this.toDateOnly(computedDueDate);
            if (!parsedDueDate) return;
            this.form.patchValue({ dueDate: parsedDueDate }, { emitEvent: false });
          },
        });
      },
    });
  }

  private getCalendarTaskFromProduct(product: any): any | null {
    const tasks = Array.isArray(product?.tasks) ? product.tasks : [];
    return (
      tasks.find(
        (task: any) => task?.addTaskToCalendar === true || task?.add_task_to_calendar === true,
      ) ??
      null
    );
  }

  private getTaskName(task: any): string | null {
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

    const docDateStr = this.toApiDate(this.form.value.docDate);

    if (this.isEditMode() && this.applicationId()) {
      // Update mode
      const dueDateStr = this.toApiDate(this.form.value.dueDate);
      const payload = {
        customer: Number(this.form.getRawValue().customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        dueDate: dueDateStr,
        addDeadlinesToCalendar: this.form.value.addDeadlinesToCalendar,
        notifyCustomer: this.form.value.notifyCustomer,
        notifyCustomerChannel: this.form.value.notifyCustomer
          ? this.form.value.notifyCustomerChannel
          : null,
        notes: this.form.value.notes,
      };

      const headers = this.buildAuthHeaders();

      this.http
        .patch<any>(`/api/customer-applications/${this.applicationId()}/`, payload, { headers })
        .subscribe({
          next: (job) => {
            this.jobService
              .openProgressDialog(job.id, 'Updating Application')
              .subscribe((finalJob) => {
                if (finalJob?.status === 'completed') {
                  this.toast.success('Application updated');
                  this.router.navigate(['/applications', this.applicationId()]);
                }
                this.isSubmitting.set(false);
              });
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
      const payload = {
        customer: Number(this.form.getRawValue().customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        dueDate: dueDateStr,
        addDeadlinesToCalendar: this.form.value.addDeadlinesToCalendar,
        notifyCustomer: this.form.value.notifyCustomer,
        notifyCustomerChannel: this.form.value.notifyCustomer
          ? this.form.value.notifyCustomerChannel
          : null,
        notes: this.form.value.notes,
        documentTypes: this.form.value.documents,
      };

      const headers = this.buildAuthHeaders();

      // Use the main endpoint which supports document_types via DocApplicationCreateUpdateSerializer
      this.http.post<any>('/api/customer-applications/', payload, { headers }).subscribe({
        next: (job) => {
          this.jobService
            .openProgressDialog(job.id, 'Creating Application')
            .subscribe((finalJob) => {
              if (finalJob?.status === 'completed') {
                this.toast.success('Application created');
                const id = finalJob.result?.id;
                if (id) {
                  this.router.navigate(['/applications', id]);
                } else {
                  this.router.navigate(['/applications']);
                }
              }
              this.isSubmitting.set(false);
            });
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
    const nav = this.router.getCurrentNavigation();
    // Be safe under SSR by preferring router navigation state and guarding access to window.history
    let st: any = (nav && nav.extras && (nav.extras.state as any)) || {};
    try {
      if (typeof window !== 'undefined' && history && (history as any).state) {
        st = { ...(st || {}), ...((history as any).state || {}) };
      }
    } catch {
      // ignore (SSR or no history)
    }

    const stateFrom = st?.from;
    const focusId = st?.focusId;

    const focusState: Record<string, unknown> = { focusTable: true };
    if (focusId) {
      focusState['focusId'] = focusId;
    } else if (this.applicationId()) {
      focusState['focusId'] = this.applicationId();
    }

    // Preserve searchQuery from the original navigation state so the list restores the search box
    if (st?.searchQuery) {
      focusState['searchQuery'] = st.searchQuery;
    }

    // If source list is known, go back there with focus
    if (stateFrom === 'customers') {
      this.router.navigate(['/customers'], { state: focusState });
      return;
    }
    if (stateFrom === 'applications') {
      this.router.navigate(['/applications'], { state: focusState });
      return;
    }

    // Fallback logic if from state is missing
    try {
      if (window.history.length > 1) {
        this.location.back();
        return;
      }
    } catch (e) {
      // ignore
    }

    // Fallbacks: if customer param present, go to customer; if editing, go to application; else go to applications list
    const customerIdParam = this.route.snapshot.paramMap.get('id') || this.form.value.customer;
    if (customerIdParam) {
      this.router.navigate(['/customers', Number(customerIdParam)]);
      return;
    }

    if (this.isEditMode() && this.applicationId()) {
      this.router.navigate(['/applications', this.applicationId()]);
      return;
    }

    this.router.navigate(['/applications'], { state: focusState });
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

  private buildAuthHeaders(): HttpHeaders | undefined {
    let token = this.authService.getToken();
    if (!token && this.authService.isMockEnabled()) {
      this.authService.initMockAuth();
      token = this.authService.getToken();
    }
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
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
