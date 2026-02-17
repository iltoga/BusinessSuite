import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
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
  type CustomerDetail,
  type UninvoicedApplication,
} from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardIconComponent } from '@/shared/components/icon';
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
    ZardIconComponent,
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

  readonly customer = signal<CustomerDetail | null>(null);
  readonly uninvoicedApplications = signal<UninvoicedApplication[]>([]);
  readonly isLoading = signal(true);
  readonly isSuperuser = this.authService.isSuperuser;
  readonly magnifierActive = signal(false);
  readonly magnifierLensX = signal(0);
  readonly magnifierLensY = signal(0);
  readonly magnifierBgX = signal(0);
  readonly magnifierBgY = signal(0);
  readonly magnifierLensSize = 300;
  readonly magnifierZoom = 4;
  readonly magnifierEnabled = signal(false);

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
      this.router.navigate(['/customers', customer.id, 'edit']);
    }

    // D --> Delete (only for superusers)
    if (event.key === 'D' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      if (this.isSuperuser()) {
        event.preventDefault();
        this.onDelete();
      }
    }

    // B or Left Arrow --> Back to list
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      const customer = this.customer();
      this.router.navigate(['/customers'], {
        state: {
          focusTable: true,
          focusId: customer ? customer.id : undefined,
          searchQuery: this.originSearchQuery(),
        },
      });
    }
  }

  readonly originSearchQuery = signal<string | null>(null);

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    // capture searchQuery if navigated from a list
    const st = this.isBrowser ? (window as any).history.state || {} : {};
    this.originSearchQuery.set(st.searchQuery ?? null);

    if (!id) {
      this.toast.error('Customer not found');
      this.router.navigate(['/customers'], {
        state: { focusTable: true, searchQuery: this.originSearchQuery() },
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

    // Fetch uninvoiced applications
    this.customersService.getUninvoicedApplications(id).subscribe({
      next: (data) => {
        this.uninvoicedApplications.set(data);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load applications');
        this.isLoading.set(false);
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
          state: { focusTable: true, focusId: customer.id, searchQuery: this.originSearchQuery() },
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
    });
  }

  canCreateInvoice(application: UninvoicedApplication): boolean {
    return !!application.readyForInvoice && !application.hasInvoice;
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

  toggleMagnifier(): void {
    const enabled = !this.magnifierEnabled();
    this.magnifierEnabled.set(enabled);
    if (!enabled) {
      this.magnifierActive.set(false);
    }
  }

  onPassportMouseEnter(): void {
    if (!this.magnifierEnabled()) return;
    this.magnifierActive.set(true);
  }

  onPassportMouseLeave(): void {
    this.magnifierActive.set(false);
  }

  onPassportMouseMove(event: MouseEvent): void {
    if (!this.magnifierEnabled()) return;

    const image = event.currentTarget as HTMLImageElement | null;
    if (!image) return;

    const rect = image.getBoundingClientRect();
    const x = event.clientX - rect.left;
    const y = event.clientY - rect.top;
    const clampedX = Math.max(0, Math.min(x, rect.width));
    const clampedY = Math.max(0, Math.min(y, rect.height));
    const halfLens = this.magnifierLensSize / 2;

    this.magnifierLensX.set(clampedX - halfLens);
    this.magnifierLensY.set(clampedY - halfLens);
    this.magnifierBgX.set((clampedX / rect.width) * 100);
    this.magnifierBgY.set((clampedY / rect.height) * 100);
  }
}
