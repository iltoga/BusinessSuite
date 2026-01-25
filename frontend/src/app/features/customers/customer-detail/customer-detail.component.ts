import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { CustomersService, type CustomerDetail } from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-customer-detail',
  standalone: true,
  imports: [CommonModule, RouterLink, ZardButtonComponent, ZardCardComponent],
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
  readonly isLoading = signal(true);

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (!id) {
      this.toast.error('Customer not found');
      this.router.navigate(['/customers']);
      return;
    }

    this.customersService.getCustomer(id).subscribe({
      next: (data) => {
        this.customer.set(data);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load customer');
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
      error: () => this.toast.error('Failed to delete customer'),
    });
  }
}
