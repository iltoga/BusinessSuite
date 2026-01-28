import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
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
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';

@Component({
  selector: 'app-customer-select',
  standalone: true,
  imports: [CommonModule, ZardComboboxComponent],
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

  readonly label = input<string>('Customer');
  readonly placeholder = input<string>('Select a customer...');
  readonly searchPlaceholder = input<string>('Search customers...');
  readonly emptyText = input<string>('No customers found.');
  readonly pageSize = input<number>(20);
  readonly selectedId = input<number | null>(null);
  readonly disabled = input<boolean>(false);

  readonly selectedIdChange = output<number | null>();

  readonly isLoading = signal(false);
  readonly options = signal<ZardComboboxOption[]>([]);
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
      if (this.searchTimer) {
        window.clearTimeout(this.searchTimer);
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
    if (this.searchTimer) {
      window.clearTimeout(this.searchTimer);
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
    this.customersService.customersList(undefined, 1, this.pageSize(), search).subscribe({
      next: (response) => {
        const items = response.results ?? [];
        this.options.set(items.map((customer) => this.mapCustomerOption(customer)));
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
    this.customersService.customersRetrieve(customerId).subscribe({
      next: (customer) => {
        const nextOption = this.mapCustomerOption(customer);
        this.options.update((current) => [nextOption, ...current]);
      },
    });
  }

  private mapCustomerOption(customer: {
    id: number;
    fullNameWithCompany?: string | null;
    fullName?: string | null;
    firstName?: string | null;
    lastName?: string | null;
  }): ZardComboboxOption {
    const label =
      customer.fullNameWithCompany ||
      customer.fullName ||
      `${customer.firstName ?? ''} ${customer.lastName ?? ''}`.trim() ||
      `Customer #${customer.id}`;

    return {
      value: String(customer.id),
      label,
    };
  }
}
