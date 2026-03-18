import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { Observable } from 'rxjs';

import type { Customer, CustomerApplicationHistory } from '@/core/api';
import {
  CustomersService,
  type CustomerApplicationPaymentStatus,
} from '@/core/services/customers.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { CardSectionComponent } from '@/shared/components/card-section';
import { DetailFieldComponent } from '@/shared/components/detail-field';
import { DetailGridComponent } from '@/shared/components/detail-grid';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { SectionHeaderComponent } from '@/shared/components/section-header';
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { BaseDetailComponent, BaseDetailConfig } from '@/shared/core/base-detail.component';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

/**
 * Customer detail component
 *
 * Extends BaseDetailComponent to inherit common detail view patterns:
 * - Keyboard shortcuts (E for edit, D for delete, B/Left for back)
 * - Navigation state management (returnUrl, searchQuery, page)
 * - Loading states
 * - Delete confirmation
 */
@Component({
  selector: 'app-customer-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
    CardSectionComponent,
    SectionHeaderComponent,
    DetailFieldComponent,
    DetailGridComponent,
    ImageMagnifierComponent,
    ZardBadgeComponent,
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    AppDatePipe,
  ],
  templateUrl: './customer-detail.component.html',
  styleUrls: ['./customer-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerDetailComponent extends BaseDetailComponent<Customer> {
  private readonly customersService = inject(CustomersService);

  // Expose item as customer for template compatibility
  get customer() {
    return this.item;
  }

  // Passport image skeleton state
  readonly passportSkeletonVisible = signal(false);
  private passportImageAlreadyLoaded = false;
  private passportSkeletonTimer?: ReturnType<typeof setTimeout>;

  // Customer-specific state
  readonly applicationsHistory = signal<CustomerApplicationHistory[]>([]);
  readonly applicationsPageSize = 10;
  readonly applicationsFilter = signal<'all' | CustomerApplicationPaymentStatus>('all');
  readonly applicationsPage = signal(1);
  readonly applicationFilterOptions: ReadonlyArray<{
    value: 'all' | CustomerApplicationPaymentStatus;
    label: string;
  }> = [
    { value: 'all', label: 'All' },
    { value: 'uninvoiced', label: 'Uninvoiced' },
    { value: 'pending_payment', label: 'Pending Payment' },
    { value: 'paid', label: 'Paid' },
  ];

  // Computed properties for applications pagination
  readonly filteredApplications = computed(() => {
    const filter = this.applicationsFilter();
    const applications = this.applicationsHistory();
    if (filter === 'all') {
      return applications;
    }
    return applications.filter((application) => application.paymentStatus === filter);
  });
  readonly totalApplications = computed(() => this.filteredApplications().length);
  readonly totalApplicationsPages = computed(() =>
    Math.max(1, Math.ceil(this.totalApplications() / this.applicationsPageSize)),
  );
  readonly pagedApplications = computed(() => {
    const page = this.applicationsPage();
    const start = (page - 1) * this.applicationsPageSize;
    return this.filteredApplications().slice(start, start + this.applicationsPageSize);
  });
  readonly hasPreviousApplicationsPage = computed(() => this.applicationsPage() > 1);
  readonly hasNextApplicationsPage = computed(
    () => this.applicationsPage() < this.totalApplicationsPages(),
  );
  readonly applicationsStartIndex = computed(() => {
    const total = this.totalApplications();
    if (total === 0) return 0;
    return (this.applicationsPage() - 1) * this.applicationsPageSize + 1;
  });
  readonly applicationsEndIndex = computed(() =>
    Math.min(this.applicationsPage() * this.applicationsPageSize, this.totalApplications()),
  );

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customer',
      enableDelete: true,
      deleteRequiresSuperuser: true,
    } as BaseDetailConfig<Customer>;

    // Setup effect for applications page validation
    effect(() => {
      const page = this.applicationsPage();
      const totalPages = this.totalApplicationsPages();
      if (page > totalPages) {
        this.applicationsPage.set(totalPages);
      }
    });
    // Setup effect for passport image skeleton (only show if load takes >150ms)
    effect(() => {
      const passportFile = this.item()?.passportFile;
      clearTimeout(this.passportSkeletonTimer);
      this.passportSkeletonVisible.set(false);
      this.passportImageAlreadyLoaded = false;
      if (passportFile) {
        this.passportSkeletonTimer = setTimeout(() => {
          if (!this.passportImageAlreadyLoaded) {
            this.passportSkeletonVisible.set(true);
          }
        }, 150);
      }
    });
  }

  onPassportImageLoaded(): void {
    this.passportImageAlreadyLoaded = true;
    clearTimeout(this.passportSkeletonTimer);
    this.passportSkeletonVisible.set(false);
  }

  /**
   */
  protected override loadItem(id: number): Observable<Customer> {
    // Note: This returns the Observable directly
    // The subscription and error handling is managed by BaseDetailComponent
    return this.customersService.getCustomer(id);
  }

  /**
   * Delete customer - overrides base class method
   */
  protected override deleteItem(id: number): Observable<any> {
    return this.customersService.deleteCustomer(id);
  }

  /**
   * Initialize component - loads customer and applications history
   */
  override ngOnInit(): void {
    // Call base ngOnInit for standard initialization
    // Note: We need to manually handle the loading since we have two data sources
    if (!this.isBrowser) return;

    this.restoreNavigationState();

    // Get item ID from route
    const idParam = this.route.snapshot.paramMap.get('id');

    if (idParam) {
      const id = Number(idParam);
      if (Number.isFinite(id)) {
        this.itemId = id;
        this.loadCustomerAndHistory(id);
      } else {
        this.toast.error('Invalid customer ID');
        this.goBack();
      }
    } else {
      this.toast.error('Customer not found');
      this.goBack();
    }
  }

  /**
   * Handle keyboard shortcuts - extends base class
   */
  override handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const customer = this.item();
    if (!customer) return;

    // E --> Edit
    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.onEdit();
    }

    // D --> Delete (only for superusers)
    if (event.key === 'D' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (this.isSuperuser()) {
        event.preventDefault();
        this.onDelete();
      }
    }

    // B or Left Arrow --> Back
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
   * Edit customer
   */
  onEdit(): void {
    const customer = this.item();
    if (!customer) return;
    this.router.navigate(['/customers', customer.id, 'edit'], {
      state: {
        from: 'customers',
        focusId: customer.id,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  /**
   * Create new application for customer
   */
  onCreateApplication(): void {
    const customer = this.item();
    if (!customer) return;
    this.router.navigate(['/customers', customer.id, 'applications', 'new']);
  }

  /**
   * Create invoice for application
   */
  onCreateInvoice(applicationId: number): void {
    this.router.navigate(['/invoices', 'new'], {
      queryParams: { applicationId },
      state: this.invoiceNavigationState(),
    });
  }

  /**
   * Check if invoice can be created for application
   */
  canCreateInvoice(application: CustomerApplicationHistory): boolean {
    return !application.hasInvoice;
  }

  /**
   * Get status badge type
   */
  getStatusBadgeType(status: string): any {
    switch (status.toLowerCase()) {
      case 'completed':
        return 'success';
      case 'pending':
        return 'warning';
      case 'rejected':
        return 'destructive';
      default:
        return 'outline';
    }
  }

  /**
   * Get payment status badge type
   */
  getPaymentStatusBadgeType(status: string): any {
    switch (status) {
      case 'paid':
        return 'success';
      case 'pending_payment':
        return 'warning';
      default:
        return 'outline';
    }
  }

  /**
   * Handle applications filter change
   */
  onApplicationsFilterChange(filter: 'all' | CustomerApplicationPaymentStatus): void {
    if (this.applicationsFilter() === filter) return;
    this.applicationsFilter.set(filter);
    this.applicationsPage.set(1);
  }

  /**
   * Go to previous applications page
   */
  goToPreviousApplicationsPage(): void {
    if (!this.hasPreviousApplicationsPage()) return;
    this.applicationsPage.update((value) => value - 1);
  }

  /**
   * Go to next applications page
   */
  goToNextApplicationsPage(): void {
    if (!this.hasNextApplicationsPage()) return;
    this.applicationsPage.update((value) => value + 1);
  }

  /**
   * Open application details
   */
  openApplicationDetails(applicationId: number): void {
    const customer = this.item();
    if (!customer) return;
    this.router.navigate(['/applications', applicationId], {
      state: {
        from: 'customer-detail',
        customerId: customer.id,
        returnUrl: `/customers/${customer.id}`,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  /**
   * Get invoice navigation state
   */
  invoiceNavigationState(): Record<string, unknown> {
    const customer = this.item();
    if (!customer) {
      return {};
    }
    return {
      from: 'customer-detail',
      customerId: customer.id,
      returnUrl: `/customers/${customer.id}`,
      searchQuery: this.originSearchQuery(),
      page: this.originPage() ?? undefined,
    };
  }

  /**
   * Load customer and applications history
   */
  private loadCustomerAndHistory(id: number): void {
    this.isLoading.set(true);

    // Fetch customer details
    this.customersService.getCustomer(id).subscribe({
      next: (data) => {
        this.item.set(data);
      },
      error: () => {
        this.toast.error('Failed to load customer');
        this.isLoading.set(false);
      },
    });

    // Fetch applications history
    this.customersService.getApplicationsHistory(id).subscribe({
      next: (data) => {
        this.applicationsHistory.set(data);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load applications history');
        this.isLoading.set(false);
      },
    });
  }
}
