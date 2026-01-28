import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { CustomersService } from '@/core/api/api/customers.service';
import { DocumentTypesService } from '@/core/api/api/document-types.service';
import { ProductsService } from '@/core/api/api/products.service';
import type { Customer } from '@/core/api/model/customer';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardInputDirective } from '@/shared/components/input';
import { CommonModule, Location } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
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
    ZardInputDirective,
    ZardComboboxComponent,
    CustomerSelectComponent,
    ZardDateInputComponent,
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

  private destroy$ = new Subject<void>();

  readonly selectedCustomer = signal<Customer | null>(null);
  readonly products = signal<any[]>([]);
  readonly documentTypes = signal<any[]>([]);
  readonly isEditMode = signal(false);
  readonly applicationId = signal<number | null>(null);
  readonly isLoading = signal(false);

  readonly form = this.fb.group({
    customer: [null as string | null, Validators.required],
    product: [null as string | null, Validators.required],
    // use Date object so z-date-input binds correctly
    docDate: [new Date()],
    notes: [''],
    documents: this.fb.array([]),
  });

  readonly isSubmitting = signal(false);

  readonly productOptions = computed<ZardComboboxOption[]>(() => {
    return this.products().map((p) => ({
      value: String(p.id),
      label: `${p.name} (${p.code})`,
    }));
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

    this.loadProducts();
    this.loadDocumentTypes();
  }

  private loadApplication(id: number): void {
    this.isLoading.set(true);
    this.customerApplicationsService.customerApplicationsRetrieve(id).subscribe({
      next: (app: any) => {
        const docDate = app.docDate ? new Date(app.docDate) : new Date();
        const customerId = Number(app.customer?.id ?? app.customer);
        this.form.patchValue({
          customer: String(customerId),
          product: String(app.product?.id ?? app.product),
          docDate: docDate,
          notes: app.notes ?? '',
        });
        if (customerId) {
          this.loadCustomerDetail(customerId);
        }
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load application');
        this.isLoading.set(false);
      },
    });
  }

  private loadProducts() {
    this.productsService.productsList(undefined, 1, 100).subscribe({
      next: (res) => this.products.set(res.results ?? []),
      error: () => this.toast.error('Failed to load products'),
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
      },
      error: () => this.toast.error('Failed to load product documents'),
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
    const docGroup = this.fb.group({
      docTypeId: [String(docTypeId), Validators.required],
      required: [required],
    });
    this.documentsArray.push(docGroup);
  }

  removeDocument(index: number) {
    this.documentsArray.removeAt(index);
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

  ngOnDestroy(): void {
    this.destroy$.next();
    this.destroy$.complete();
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
          error: () => {
            this.toast.error('Failed to update application');
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
        error: () => {
          this.toast.error('Failed to create application');
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
    const stateFrom =
      (nav && nav.extras && (nav.extras.state as any)?.from) ||
      (history.state && (history.state as any).from);
    if (stateFrom) {
      if (typeof stateFrom === 'string') {
        this.router.navigateByUrl(stateFrom);
      } else {
        this.router.navigate(stateFrom as any[]);
      }
      return;
    }

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

    this.router.navigate(['/applications']);
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
