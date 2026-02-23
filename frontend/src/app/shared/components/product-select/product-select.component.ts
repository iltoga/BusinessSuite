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

import { ProductsService } from '@/core/api/api/products.service';
import { type ZardComboboxVariants } from '@/shared/components/combobox/combobox.variants';
import {
  TypeaheadComboboxComponent,
  type TypeaheadOption,
} from '@/shared/components/typeahead-combobox/typeahead-combobox.component';
import { map } from 'rxjs/operators';

@Component({
  selector: 'app-product-select',
  standalone: true,
  imports: [CommonModule, TypeaheadComboboxComponent],
  templateUrl: './product-select.component.html',
  styleUrls: ['./product-select.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      multi: true,
      useExisting: forwardRef(() => ProductSelectComponent),
    },
  ],
})
export class ProductSelectComponent implements ControlValueAccessor {
  private productsService = inject(ProductsService);
  private destroyRef = inject(DestroyRef);

  readonly label = input<string>('Product');
  readonly placeholder = input<string>('Select a product...');
  readonly searchPlaceholder = input<string>('Search products...');
  readonly emptyText = input<string>('No products found.');
  readonly pageSize = input<number>(20);
  readonly selectedId = input<number | null>(null);
  readonly disabled = input<boolean>(false);
  readonly zStatus = input<'error' | 'success' | 'warning' | 'default' | undefined>();
  readonly zWidth = input<ZardComboboxVariants['zWidth']>('default');

  readonly selectedIdChange = output<number | null>();

  readonly internalValue = signal<string | null>(null);
  readonly options = signal<TypeaheadOption[]>([]);
  readonly isCvaDisabled = signal(false);

  readonly isDisabled = computed(() => this.disabled() || this.isCvaDisabled());

  private onChange: (value: number | null) => void = () => {};
  private onTouched: () => void = () => {};

  constructor() {
    effect(() => {
      const incoming = this.selectedId();
      if (incoming !== null && incoming !== undefined) {
        const value = String(incoming);
        if (this.internalValue() !== value) {
          this.internalValue.set(value);
          this.ensureSelectedOption(incoming);
        }
      }
    });
  }

  // Loader function for Typeahead wrapper
  readonly productLoader = (q?: string, page = 1) => {
    return this.productsService
      .productsList(undefined, page, this.pageSize(), q)
      .pipe(map((resp: any) => resp.results ?? []));
  };

  // Map function for Typeahead wrapper
  readonly productMap = (p: any): TypeaheadOption => this.mapProductOption(p);

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

  onValueChange(value: string | string[] | null): void {
    const normalized = Array.isArray(value) ? (value[0] ?? null) : value;
    this.internalValue.set(normalized);
    const numericValue = normalized ? Number(normalized) : null;
    const finalValue = Number.isNaN(numericValue as number) ? null : numericValue;
    this.onChange(finalValue);
    this.selectedIdChange.emit(finalValue);
  }

  private ensureSelectedOption(productId: number): void {
    if (!productId || Number.isNaN(productId)) return;

    // Check if we already have it in current options
    if (this.options().some((opt) => opt.value === String(productId))) return;

    // Load specifically to ensure we can display the label
    this.productsService.productsGetProductByIdRetrieve(productId).subscribe({
      next: (product) => {
        const opt = this.mapProductOption(product as any);
        this.options.update((curr) => [opt, ...curr]);
      },
    });
  }

  private mapProductOption(product: any): TypeaheadOption {
    const normalizedProduct = product?.product ?? product;
    const name = normalizedProduct.name ?? `Product #${normalizedProduct.id}`;
    const code = normalizedProduct.code ?? '';
    const desc = (normalizedProduct.description ?? '').trim();

    // The wrapper will use these for two-line display
    return {
      value: String(normalizedProduct.id),
      label: name,
      code: code || undefined,
      description: desc || undefined,
      // Search across name, code, AND description
      search: `${name} ${code} ${desc}`.trim(),
      // Display value in the collapsed button
      display: code ? `${code} - ${name}` : name,
    };
  }
}
