import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  PLATFORM_ID,
  computed,
  effect,
  forwardRef,
  inject,
  input,
  output,
  signal,
} from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

import { CustomersService } from '@/core/api/api/customers.service';
import type { Customer } from '@/core/api/model/customer';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';

type CustomerOptionSource = Pick<
  Customer,
  'id' | 'fullNameWithCompany' | 'fullName' | 'firstName' | 'lastName' | 'companyName'
>;

interface CustomerSelectOption extends ZardComboboxOption {
  sortLastName: string;
  sortFirstName: string;
  sortCompanyName: string;
}

const CUSTOMER_ORDERING = 'sort_last_name,sort_first_name,sort_company_name';

@Component({
  selector: 'app-customer-select',
  standalone: true,
  imports: [ZardComboboxComponent],
  templateUrl: './customer-select.component.html',
  styleUrls: ['./customer-select.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      multi: true,
      useExisting: forwardRef(() => CustomerSelectComponent),
    },
  ],
})
export class CustomerSelectComponent implements ControlValueAccessor {
  private customersService = inject(CustomersService);
  private destroyRef = inject(DestroyRef);
  private platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  readonly label = input<string>('Customer');
  readonly placeholder = input<string>('Select a customer...');
  readonly searchPlaceholder = input<string>('Search customers...');
  readonly emptyText = input<string>('No customers found.');
  readonly pageSize = input<number>(20);
  readonly selectedId = input<number | null>(null);
  readonly disabled = input<boolean>(false);
  readonly zStatus = input<'error' | 'success' | 'warning' | 'default' | undefined>();

  readonly selectedIdChange = output<number | null>();

  readonly isLoading = signal(false);
  readonly options = signal<CustomerSelectOption[]>([]);
  readonly internalValue = signal<string | null>(null);
  readonly isCvaDisabled = signal(false);

  private searchTimer: number | null = null;

  readonly isDisabled = computed(() => this.disabled() || this.isCvaDisabled());
  readonly emptyMessage = computed(() =>
    this.isLoading() ? 'Loading customers...' : this.emptyText(),
  );

  private onChange: (value: number | null) => void = () => {
    // ControlValueAccessor
  };

  private onTouched: () => void = () => {
    // ControlValueAccessor
  };

  constructor() {
    this.loadCustomers();

    effect(() => {
      const incoming = this.selectedId();
      if (incoming === null || incoming === undefined) {
        return;
      }
      const value = String(incoming);
      if (this.internalValue() !== value) {
        this.internalValue.set(value);
        this.ensureSelectedOption(incoming);
      }
    });

    this.destroyRef.onDestroy(() => {
      if (this.searchTimer && this.isBrowser) {
        try {
          window.clearTimeout(this.searchTimer);
        } catch {
          try {
            clearTimeout(this.searchTimer as any);
          } catch {}
        }
      }
    });
  }

  writeValue(value: number | string | null): void {
    if (value === null || value === undefined || value === '') {
      this.internalValue.set(null);
      return;
    }
    const stringValue = String(value);
    this.internalValue.set(stringValue);
    const numericValue = Number(value);
    if (!Number.isNaN(numericValue)) {
      this.ensureSelectedOption(numericValue);
    }
  }

  registerOnChange(fn: (value: number | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.isCvaDisabled.set(isDisabled);
  }

  onValueChange(value: string | null): void {
    this.internalValue.set(value);
    const numericValue = value ? Number(value) : null;
    this.onChange(Number.isNaN(numericValue as number) ? null : numericValue);
    this.selectedIdChange.emit(Number.isNaN(numericValue as number) ? null : numericValue);
  }

  onSearchChange(query: string): void {
    if (!this.isBrowser) return;

    if (this.searchTimer) {
      try {
        window.clearTimeout(this.searchTimer);
      } catch {
        try {
          clearTimeout(this.searchTimer as any);
        } catch {}
      }
    }
    this.searchTimer = window.setTimeout(() => {
      this.loadCustomers(query);
    }, 300);
  }

  onBlur(): void {
    this.onTouched();
  }

  private loadCustomers(search?: string): void {
    this.isLoading.set(true);
    this.customersService
      .customersList({
        ordering: CUSTOMER_ORDERING,
        page: 1,
        pageSize: this.pageSize(),
        search,
      })
      .subscribe({
      next: (response) => {
        const items = (response.results ?? []) as CustomerOptionSource[];
        this.options.set(this.sortCustomerOptions(items.map((customer) => this.mapCustomerOption(customer))));
        this.isLoading.set(false);
        const currentValue = this.internalValue();
        if (currentValue) {
          this.ensureSelectedOption(Number(currentValue));
        }
      },
      error: () => {
        this.isLoading.set(false);
      },
    });
  }

  private ensureSelectedOption(customerId: number): void {
    if (!customerId || Number.isNaN(customerId)) {
      return;
    }
    const exists = this.options().some((option) => option.value === String(customerId));
    if (exists) {
      return;
    }
    this.customersService.customersRetrieve({ id: customerId }).subscribe({
      next: (customer) => {
        const nextOption = this.mapCustomerOption(customer);
        this.options.update((current) => this.sortCustomerOptions([...current, nextOption]));
      },
    });
  }

  private mapCustomerOption(customer: CustomerOptionSource): CustomerSelectOption {
    const label =
      customer.fullNameWithCompany ||
      customer.fullName ||
      `${customer.firstName ?? ''} ${customer.lastName ?? ''}`.trim() ||
      `Customer #${customer.id}`;

    return {
      value: String(customer.id),
      label,
      sortLastName: this.toSortKey(
        customer.lastName ||
          customer.companyName ||
          customer.firstName ||
          customer.fullName ||
          customer.fullNameWithCompany,
      ),
      sortFirstName: this.toSortKey(
        customer.firstName ||
          customer.companyName ||
          customer.fullName ||
          customer.fullNameWithCompany,
      ),
      sortCompanyName: this.toSortKey(customer.companyName),
    };
  }

  private sortCustomerOptions(options: CustomerSelectOption[]): CustomerSelectOption[] {
    return [...options].sort((left, right) => {
      return (
        this.compareSortFields(left.sortLastName, right.sortLastName) ||
        this.compareSortFields(left.sortFirstName, right.sortFirstName) ||
        this.compareSortFields(left.sortCompanyName, right.sortCompanyName) ||
        this.compareSortFields(left.label, right.label) ||
        left.value.localeCompare(right.value)
      );
    });
  }

  private compareSortFields(left: string, right: string): number {
    return left.localeCompare(right, undefined, { sensitivity: 'base' });
  }

  private toSortKey(value?: string | null): string {
    return value?.trim() ?? '';
  }
}
