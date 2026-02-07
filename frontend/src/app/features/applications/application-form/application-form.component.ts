import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { CustomersService } from '@/core/api/api/customers.service';
import { DocumentTypesService } from '@/core/api/api/document-types.service';
import { ProductsService } from '@/core/api/api/products.service';
import type { Customer } from '@/core/api/model/customer';
import { AuthService } from '@/core/services/auth.service';
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
import { FormArray, FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { map, startWith, Subject, takeUntil } from 'rxjs';

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
  ],
  templateUrl: './application-form.component.html',
  styleUrls: ['./application-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationFormComponent implements OnInit, OnDestroy {
  private fb = inject(FormBuilder);
  private customersService = inject(CustomersService);
  private customerApplicationsService = inject(CustomerApplicationsService);
  private productsService = inject(ProductsService);
  private documentTypesService = inject(DocumentTypesService);
  private authService = inject(AuthService);
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
  // Loading state and open/closed state for the Documents panel
  readonly documentsLoading = signal(false);
  readonly documentsPanelOpen = signal(false);

  readonly form = this.fb.group({
    customer: [null as string | null, Validators.required],
    product: [null as string | null, Validators.required],
    // use Date object so z-date-input binds correctly
    docDate: [new Date()],
    notes: [''],
    documents: this.fb.array([]),
  });

  readonly formErrorLabels: Record<string, string> = {
    customer: 'Customer',
    product: 'Product',
    docDate: 'Document Date',
    notes: 'Notes',
    documents: 'Documents',
  };

  readonly isSubmitting = signal(false);

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

      // Load product documents when product or customer changes (only in create mode)
      this.form
        .get('product')
        ?.valueChanges.pipe(takeUntil(this.destroy$))
        .subscribe((productId) => {
          if (productId) {
            this.loadProductDocuments(Number(productId));
          } else {
            this.documentsArray.clear();
          }
        });

      this.form
        .get('customer')
        ?.valueChanges.pipe(takeUntil(this.destroy$))
        .subscribe((customerId) => {
          if (customerId) {
            this.loadCustomerDetail(Number(customerId));
          }
          const productId = this.form.get('product')?.value;
          if (productId) {
            this.loadProductDocuments(Number(productId));
          }
        });
    }

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
          notes: app.notes ?? '',
        });
        if (customerId) {
          this.loadCustomerDetail(customerId);
        }

        // Ensure product documents are loaded when editing an application
        if (productId) {
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
      next: (customer) => this.selectedCustomer.set(customer),
      error: () => this.selectedCustomer.set(null),
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

        if (passportAutoImported) {
          this.toast.info('Passport file automatically imported from Customer profile');
        }

        this.documentsLoading.set(false);
        // ensure template updates under OnPush
        this.cdr.markForCheck();
      },
      error: () => {
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
      // Open panel and load documents immediately
      this.documentsPanelOpen.set(true);
      this.loadProductDocuments(Number(productId));
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
      productControl?.disable({ emitEvent: false });
    } else {
      customerControl?.enable({ emitEvent: false });
      productControl?.enable({ emitEvent: false });
    }
  }

  submit(): void {
    if (this.form.invalid) {
      // mark fields as touched to show validation
      this.form.markAllAsTouched();
      return;
    }

    this.isSubmitting.set(true);

    const docValue = this.form.value.docDate;
    const docDateStr = docValue instanceof Date ? docValue.toISOString().slice(0, 10) : docValue;

    if (this.isEditMode() && this.applicationId()) {
      // Update mode
      const payload = {
        customer: Number(this.form.value.customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        notes: this.form.value.notes,
      };

      const headers = this.buildAuthHeaders();

      this.http
        .patch(`/api/customer-applications/${this.applicationId()}/`, payload, { headers })
        .subscribe({
          next: () => {
            this.toast.success('Application updated');
            this.router.navigate(['/applications', this.applicationId()]);
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
      const payload = {
        customer: Number(this.form.value.customer),
        product: Number(this.form.value.product),
        docDate: docDateStr,
        notes: this.form.value.notes,
        documentTypes: this.form.value.documents,
      };

      const headers = this.buildAuthHeaders();

      // Use the main endpoint which supports document_types via DocApplicationCreateUpdateSerializer
      this.http.post('/api/customer-applications/', payload, { headers }).subscribe({
        next: (res: any) => {
          this.toast.success('Application created');
          const id = res?.id;
          if (id) {
            this.router.navigate(['/applications', id]);
          } else {
            // fallback to applications list if id is missing in response
            this.router.navigate(['/applications']);
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
    const nav = this.router.getCurrentNavigation();
    const st = (nav && nav.extras && (nav.extras.state as any)) || (history.state as any);

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
}
