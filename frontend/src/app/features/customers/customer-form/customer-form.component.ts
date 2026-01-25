import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { CustomersService, type CustomerDetail } from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-customer-form',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
  ],
  templateUrl: './customer-form.component.html',
  styleUrls: ['./customer-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private customersService = inject(CustomersService);
  private toast = inject(GlobalToastService);

  readonly isLoading = signal(false);
  readonly isEditMode = signal(false);
  readonly customer = signal<CustomerDetail | null>(null);

  form = this.fb.group({
    customer_type: ['person'],
    title: [''],
    first_name: [''],
    last_name: [''],
    company_name: [''],
    email: ['', Validators.email],
    telephone: [''],
    whatsapp: [''],
    telegram: [''],
    passport_number: [''],
    passport_issue_date: [''],
    passport_expiration_date: [''],
    birthdate: [''],
    birth_place: [''],
    address_bali: [''],
    address_abroad: [''],
    active: [true],
  });

  ngOnInit(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.isEditMode.set(true);
      const id = Number(idParam);
      this.isLoading.set(true);
      this.customersService.getCustomer(id).subscribe({
        next: (data) => {
          this.customer.set(data);
          this.form.patchValue({
            customer_type: data.customerType ?? 'person',
            title: data.title ?? '',
            first_name: data.firstName ?? '',
            last_name: data.lastName ?? '',
            company_name: data.companyName ?? '',
            email: data.email ?? '',
            telephone: data.telephone ?? '',
            whatsapp: data.whatsapp ?? '',
            telegram: data.telegram ?? '',
            passport_number: data.passportNumber ?? '',
            passport_issue_date: data.passportExpirationDate ?? '',
            passport_expiration_date: data.passportExpirationDate ?? '',
            birthdate: data.birthdate ?? '',
            birth_place: data.birthPlace ?? '',
            address_bali: data.addressBali ?? '',
            address_abroad: data.addressAbroad ?? '',
            active: data.active ?? true,
          });
          this.isLoading.set(false);
        },
        error: () => {
          this.toast.error('Failed to load customer');
          this.isLoading.set(false);
        },
      });
    }
  }

  onSubmit(): void {
    if (this.form.invalid) {
      this.toast.error('Please fix validation errors');
      return;
    }

    const payload = this.form.getRawValue();
    this.isLoading.set(true);

    if (this.isEditMode()) {
      const id = Number(this.route.snapshot.paramMap.get('id'));
      this.customersService.updateCustomer(id, payload).subscribe({
        next: (data) => {
          this.toast.success('Customer updated');
          this.router.navigate(['/customers', data.id]);
        },
        error: () => {
          this.toast.error('Failed to update customer');
          this.isLoading.set(false);
        },
      });
    } else {
      this.customersService.createCustomer(payload).subscribe({
        next: (data) => {
          this.toast.success('Customer created');
          this.router.navigate(['/customers', data.id]);
        },
        error: () => {
          this.toast.error('Failed to create customer');
          this.isLoading.set(false);
        },
      });
    }
  }
}
