import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  computed,
  Component,
  effect,
  HostListener,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { AuthService } from '@/core/services/auth.service';
import {
  CustomersService,
  type CustomerApplicationHistory,
  type CustomerApplicationPaymentStatus,
  type CustomerDetail,
} from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-customer-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
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
export class CustomerDetailComponent implements OnInit {
  private platformId = inject(PLATFORM_ID);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private customersService = inject(CustomersService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private readonly isBrowser = isPlatformBrowser(this.platformId);
  readonly applicationsPageSize = 10;

  readonly customer = signal<CustomerDetail | null>(null);
  readonly applicationsHistory = signal<CustomerApplicationHistory[]>([]);
  readonly isLoading = signal(true);
  readonly isSuperuser = this.authService.isSuperuser;
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

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    // Only trigger if no input is focused
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const customer = this.customer();
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

  readonly originSearchQuery = signal<string | null>(null);
  readonly originPage = signal<number | null>(null);
  readonly returnUrl = signal<string | null>(null);
  readonly returnState = signal<Record<string, unknown> | null>(null);

  constructor() {
    effect(() => {
      const page = this.applicationsPage();
      const totalPages = this.totalApplicationsPages();
      if (page > totalPages) {
        this.applicationsPage.set(totalPages);
      }
    });
  }

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    // capture searchQuery if navigated from a list
    const st = this.isBrowser ? (window as any).history.state || {} : {};
    this.originSearchQuery.set(st.searchQuery ?? null);
    this.returnUrl.set(typeof st.returnUrl === 'string' && st.returnUrl.startsWith('/') ? st.returnUrl : null);
    this.returnState.set(
      st.returnState && typeof st.returnState === 'object'
        ? (st.returnState as Record<string, unknown>)
        : null,
    );
    const page = Number(st.page);
    if (Number.isFinite(page) && page > 0) {
      this.originPage.set(Math.floor(page));
    }

    if (!id) {
      this.toast.error('Customer not found');
      this.router.navigate(['/customers'], {
        state: {
          focusTable: true,
          searchQuery: this.originSearchQuery(),
          page: this.originPage() ?? undefined,
        },
      });
      return;
    }

    // Fetch customer details
    this.customersService.getCustomer(id).subscribe({
      next: (data) => {
        this.customer.set(data);
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

  onEdit(): void {
    const customer = this.customer();
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

  onDelete(): void {
    const customer = this.customer();
    if (!customer) return;

    if (!confirm(`Delete customer ${customer.fullNameWithCompany}? This cannot be undone.`)) {
      return;
    }

    this.customersService.deleteCustomer(customer.id).subscribe({
      next: () => {
        this.toast.success('Customer deleted');
        this.router.navigate(['/customers'], {
          state: {
            focusTable: true,
            focusId: customer.id,
            searchQuery: this.originSearchQuery(),
            page: this.originPage() ?? undefined,
          },
        });
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete customer: ${message}` : 'Failed to delete customer',
        );
      },
    });
  }

  onCreateApplication(): void {
    const customer = this.customer();
    if (!customer) return;
    this.router.navigate(['/customers', customer.id, 'applications', 'new']);
  }

  onCreateInvoice(applicationId: number): void {
    this.router.navigate(['/invoices', 'new'], {
      queryParams: { applicationId },
      state: this.invoiceNavigationState(),
    });
  }

  goBack(): void {
    const returnUrl = this.returnUrl();
    if (returnUrl) {
      this.router.navigateByUrl(returnUrl, {
        state: this.returnState() ?? {
          searchQuery: this.originSearchQuery(),
          page: this.originPage() ?? undefined,
        },
      });
      return;
    }

    const customer = this.customer();
    this.router.navigate(['/customers'], {
      state: {
        focusTable: true,
        focusId: customer ? customer.id : undefined,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  canCreateInvoice(application: CustomerApplicationHistory): boolean {
    return !application.hasInvoice;
  }

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

  getPaymentStatusBadgeType(status: CustomerApplicationPaymentStatus): any {
    switch (status) {
      case 'paid':
        return 'success';
      case 'pending_payment':
        return 'warning';
      default:
        return 'outline';
    }
  }

  onApplicationsFilterChange(filter: 'all' | CustomerApplicationPaymentStatus): void {
    if (this.applicationsFilter() === filter) return;
    this.applicationsFilter.set(filter);
    this.applicationsPage.set(1);
  }

  goToPreviousApplicationsPage(): void {
    if (!this.hasPreviousApplicationsPage()) return;
    this.applicationsPage.update((value) => value - 1);
  }

  goToNextApplicationsPage(): void {
    if (!this.hasNextApplicationsPage()) return;
    this.applicationsPage.update((value) => value + 1);
  }

  openApplicationDetails(applicationId: number): void {
    const customer = this.customer();
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

  invoiceNavigationState(): Record<string, unknown> {
    const customer = this.customer();
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

}
