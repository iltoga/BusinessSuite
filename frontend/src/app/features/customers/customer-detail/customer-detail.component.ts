import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  OnInit,
  inject,
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
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { HelpService } from '@/shared/services/help.service';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-customer-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ZardButtonComponent,
    ZardCardComponent,
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
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private customersService = inject(CustomersService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private help = inject(HelpService);

  readonly customer = signal<CustomerDetail | null>(null);
  readonly uninvoicedApplications = signal<UninvoicedApplication[]>([]);
  readonly isLoading = signal(true);
  readonly isSuperuser = this.authService.isSuperuser;

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
    const st = (window as any).history.state || {};
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

        // Update contextual help for this specific customer (dynamic title)
        this.help.setContext({
          id: `/customers/${id}`,
          briefExplanation: `Customer profile for ${data.fullNameWithCompany}. View and manage customer details, applications, and invoices.`,
          details: `Email: ${data.email ?? 'no email'}. Use tabs to navigate between profile, applications, and invoices. Edit customer information or create new applications.`,
        });
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
}
