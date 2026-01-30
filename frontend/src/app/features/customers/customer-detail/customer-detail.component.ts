import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  CustomersService,
  type CustomerDetail,
  type UninvoicedApplication,
} from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
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
    ZardBadgeComponent,
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
  private toast = inject(GlobalToastService);

  readonly customer = signal<CustomerDetail | null>(null);
  readonly uninvoicedApplications = signal<UninvoicedApplication[]>([]);
  readonly isLoading = signal(true);

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (!id) {
      this.toast.error('Customer not found');
      this.router.navigate(['/customers']);
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
        this.router.navigate(['/customers']);
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
