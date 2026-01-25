import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  CustomersService,
  type CountryCode,
  type CustomerDetail,
} from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardDateInputComponent } from '@/shared/components/date-input';
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
    ZardDateInputComponent,
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
  readonly countries = signal<CountryCode[]>([]);
  readonly isPerson = signal(true); // Track if customer type is 'person'

  form = this.fb.group({
    customer_type: ['person'],
    title: [''],
    first_name: [''],
    last_name: [''],
    company_name: [''],
    gender: [''],
    nationality: [''],
    birthdate: [null as Date | null],
    birth_place: [''],
    passport_number: [''],
    passport_issue_date: [null as Date | null],
    passport_expiration_date: [null as Date | null],
    npwp: [''],
    email: ['', Validators.email],
    telephone: [''],
    whatsapp: [''],
    telegram: [''],
    facebook: [''],
    instagram: [''],
    twitter: [''],
    address_bali: [''],
    address_abroad: [''],
    notify_documents_expiration: [false],
    notify_by: [''],
    active: [true],
  });

  // Title options
  readonly titleOptions = [
    { value: '', label: '---------' },
    { value: 'Mr', label: 'Mr' },
    { value: 'Mrs', label: 'Mrs' },
    { value: 'Ms', label: 'Ms' },
    { value: 'Miss', label: 'Miss' },
    { value: 'Dr', label: 'Dr' },
    { value: 'Prof', label: 'Prof' },
  ];

  // Gender options
  readonly genderOptions = [
    { value: '', label: '---------' },
    { value: 'M', label: 'Male' },
    { value: 'F', label: 'Female' },
  ];

  // Notify by options
  readonly notifyByOptions = [
    { value: '', label: '---------' },
    { value: 'Email', label: 'Email' },
    { value: 'SMS', label: 'SMS' },
    { value: 'WhatsApp', label: 'WhatsApp' },
    { value: 'Telegram', label: 'Telegram' },
    { value: 'Telephone', label: 'Telephone' },
  ];

  ngOnInit(): void {
    // Load countries for the nationality dropdown
    this.customersService.getCountries().subscribe({
      next: (data) => this.countries.set(data),
      error: () => this.toast.error('Failed to load countries'),
    });

    // Set up conditional validation based on customer_type changes
    this.form.get('customer_type')?.valueChanges.subscribe((customerType) => {
      // Update isPerson signal
      this.isPerson.set(customerType === 'person');

      const firstNameControl = this.form.get('first_name');
      const lastNameControl = this.form.get('last_name');
      const companyNameControl = this.form.get('company_name');

      if (customerType === 'person') {
        firstNameControl?.setValidators([Validators.required]);
        lastNameControl?.setValidators([Validators.required]);
        companyNameControl?.clearValidators();
      } else if (customerType === 'company') {
        firstNameControl?.clearValidators();
        lastNameControl?.clearValidators();
        companyNameControl?.setValidators([Validators.required]);
      }

      firstNameControl?.updateValueAndValidity({ emitEvent: false });
      lastNameControl?.updateValueAndValidity({ emitEvent: false });
      companyNameControl?.updateValueAndValidity({ emitEvent: false });
    });

    // Load customer data if in edit mode
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.isEditMode.set(true);
      const id = Number(idParam);
      this.isLoading.set(true);
      this.customersService.getCustomer(id).subscribe({
        next: (data) => {
          this.customer.set(data);
          // Update isPerson immediately based on loaded data
          this.isPerson.set(data.customerType === 'person');
          this.form.patchValue({
            customer_type: data.customerType ?? 'person',
            title: data.title ?? '',
            first_name: data.firstName ?? '',
            last_name: data.lastName ?? '',
            company_name: data.companyName ?? '',
            gender: data.gender ?? '',
            nationality: data.nationality ?? '',
            birthdate: data.birthdate ? new Date(data.birthdate) : null,
            birth_place: data.birthPlace ?? '',
            passport_number: data.passportNumber ?? '',
            passport_issue_date: data.passportIssueDate ? new Date(data.passportIssueDate) : null,
            passport_expiration_date: data.passportExpirationDate
              ? new Date(data.passportExpirationDate)
              : null,
            npwp: data.npwp ?? '',
            email: data.email ?? '',
            telephone: data.telephone ?? '',
            whatsapp: data.whatsapp ?? '',
            telegram: data.telegram ?? '',
            facebook: data.facebook ?? '',
            instagram: data.instagram ?? '',
            twitter: data.twitter ?? '',
            address_bali: data.addressBali ?? '',
            address_abroad: data.addressAbroad ?? '',
            notify_documents_expiration: data.notifyDocumentsExpiration ?? false,
            notify_by: data.notifyBy ?? '',
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

    const rawValue = this.form.getRawValue();
    const payload = {
      ...rawValue,
      birthdate: rawValue.birthdate ? rawValue.birthdate.toISOString().split('T')[0] : '',
      passport_issue_date: rawValue.passport_issue_date
        ? rawValue.passport_issue_date.toISOString().split('T')[0]
        : '',
      passport_expiration_date: rawValue.passport_expiration_date
        ? rawValue.passport_expiration_date.toISOString().split('T')[0]
        : '',
    };
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
