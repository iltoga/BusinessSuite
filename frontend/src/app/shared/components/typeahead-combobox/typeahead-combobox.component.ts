import type { ZardComboboxOption as BaseOption } from '@/shared/components/combobox/combobox.component';
import { isPlatformBrowser } from '@angular/common';
import {
  afterNextRender,
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  ElementRef,
  forwardRef,
  inject,
  Injector,
  input,
  output,
  PLATFORM_ID,
  runInInjectionContext,
  signal,
  viewChild,
  ViewEncapsulation,
} from '@angular/core';
import { NG_VALUE_ACCESSOR, type ControlValueAccessor } from '@angular/forms';
import { Observable } from 'rxjs';

import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { type ZardComboboxVariants } from '@/shared/components/combobox/combobox.variants';
import { ZardCommandEmptyComponent } from '@/shared/components/command/command-empty.component';
import { ZardCommandInputComponent } from '@/shared/components/command/command-input.component';
import { ZardCommandListComponent } from '@/shared/components/command/command-list.component';
import { ZardCommandOptionComponent } from '@/shared/components/command/command-option.component';
import {
  ZardCommandComponent,
  type ZardCommandOption,
} from '@/shared/components/command/command.component';
import { ZardEmptyComponent } from '@/shared/components/empty/empty.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import {
  ZardPopoverComponent,
  ZardPopoverDirective,
} from '@/shared/components/popover/popover.component';
import { mergeClasses } from '@/shared/utils/merge-classes';

/**
 * Enhanced option for TypeaheadCombobox
 */
export interface TypeaheadOption extends BaseOption {
  search?: string;
  display?: string;
  code?: string;
  description?: string;
}

@Component({
  selector: 'app-typeahead-combobox',
  standalone: true,
  imports: [
    ZardButtonComponent,
    ZardCommandComponent,
    ZardCommandInputComponent,
    ZardCommandListComponent,
    ZardCommandEmptyComponent,
    ZardCommandOptionComponent,
    ZardPopoverDirective,
    ZardPopoverComponent,
    ZardEmptyComponent,
    ZardIconComponent,
  ],
  template: `
    <button
      type="button"
      z-button
      zPopover
      [zContent]="popoverContent"
      [zType]="buttonVariant()"
      [class]="buttonClasses()"
      [disabled]="disabled()"
      role="combobox"
      [attr.aria-expanded]="open()"
      (zVisibleChange)="setOpen($event)"
      #popoverTrigger
    >
      <span class="flex-1 truncate text-left">
        {{ displayValue() ?? placeholder() }}
      </span>
      <z-icon zType="chevrons-up-down" class="ml-2 shrink-0 opacity-50" />
    </button>

    <ng-template #popoverContent>
      <z-popover [class]="popoverClasses()">
        <z-command
          class="min-h-auto"
          (zCommandSelected)="handleSelect($event)"
          [zRemote]="true"
          #commandRef
        >
          @if (searchable()) {
            <z-command-input
              [placeholder]="searchPlaceholder()"
              (valueChange)="onSearch($event)"
              #commandInputRef
            />
          }

          <z-command-list role="listbox">
            @if (isLoading() && options().length === 0) {
              <div class="p-2 text-sm text-center text-muted-foreground italic">Loading...</div>
            } @else if (options().length === 0 && !isLoading()) {
              <z-command-empty>
                <z-empty [zDescription]="emptyText()" />
              </z-command-empty>
            }

            @for (option of options(); track option.value) {
              <z-command-option
                [zValue]="option.value"
                [zLabel]="option.search ?? option.label"
                [zDisabled]="option.disabled ?? false"
                [zIcon]="option.icon"
                [attr.aria-selected]="isSelected(option.value)"
              >
                <div class="flex-1 min-w-0">
                  <div class="truncate font-medium">
                    {{ option.label }}
                  </div>
                  @if (option.code || option.description) {
                    <div class="text-xs opacity-60 truncate">
                      @if (option.code) {
                        <span class="font-semibold">{{ option.code }}</span>
                      }
                      @if (option.code && option.description) {
                        <span> - </span>
                      }
                      {{ option.description }}
                    </div>
                  }
                </div>
                @if (isSelected(option.value)) {
                  <z-icon zType="check" class="ml-auto shrink-0" />
                }
              </z-command-option>
            }

            @if (hasMore()) {
              <div #sentinel class="p-2 text-xs text-center text-muted-foreground italic">
                @if (isLoading()) {
                  Loading more...
                }
              </div>
            }
          </z-command-list>
        </z-command>
      </z-popover>
    </ng-template>
  `,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => TypeaheadComboboxComponent),
      multi: true,
    },
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
})
export class TypeaheadComboboxComponent implements ControlValueAccessor {
  private platformId = inject(PLATFORM_ID);
  private readonly injector = inject(Injector);

  // Signals for state
  readonly open = signal(false);
  readonly internalValue = signal<string | null>(null);
  readonly internalValues = signal<string[]>([]);
  readonly options = signal<TypeaheadOption[]>([]);
  readonly isLoading = signal(false);
  readonly currentPage = signal(1);
  readonly hasMore = signal(false);
  readonly searchQuery = signal('');

  // Inputs
  readonly placeholder = input<string>('Select...');
  readonly searchPlaceholder = input<string>('Search...');
  readonly emptyText = input<string>('No results found.');
  readonly zWidth = input<ZardComboboxVariants['zWidth']>('default');
  readonly zStatus = input<'error' | 'success' | 'warning' | 'default' | undefined>();
  readonly disabled = input<boolean>(false);
  readonly buttonVariant = input<'default' | 'outline' | 'secondary' | 'ghost'>('outline');
  readonly searchable = input<boolean>(true);
  readonly multiselect = input<boolean>(false);
  readonly pageSize = input<number>(20);

  // A function provided by parent (passed as signal or direct value)
  // We use a getter-like input for these functions
  readonly loadOptions = input<((q?: string, page?: number) => Observable<any[]>) | undefined>(
    undefined,
  );
  readonly mapFn = input<((item: any) => TypeaheadOption) | undefined>(undefined);

  // External value control from CVA/Inputs
  readonly value = input<string | string[] | null | undefined>(undefined);
  readonly valueChange = output<string | string[] | null>();

  // Element refs
  readonly popoverDirective = viewChild.required(ZardPopoverDirective);
  readonly buttonRef = viewChild.required('popoverTrigger', { read: ElementRef });
  readonly commandRef = viewChild('commandRef', { read: ZardCommandComponent });
  readonly commandInputRef = viewChild('commandInputRef', { read: ZardCommandInputComponent });
  readonly sentinel = viewChild<ElementRef>('sentinel');

  private searchTimer: number | null = null;
  private onChange: (v: string | string[] | null) => void = () => {};
  private onTouched: () => void = () => {};
  private observer: IntersectionObserver | null = null;

  constructor() {
    effect(() => {
      const val = this.value();
      if (val === undefined) {
        return;
      }
      if (this.multiselect()) {
        const normalized = this.normalizeIncomingValues(val);
        if (!this.arraysEqual(this.internalValues(), normalized)) {
          this.internalValues.set(normalized);
        }
      } else {
        const normalized = Array.isArray(val) ? (val[0] ?? null) : (val ?? null);
        if (normalized !== this.internalValue()) {
          this.internalValue.set(normalized);
        }
      }
    });

    effect(() => {
      if (this.multiselect()) {
        const single = this.internalValue();
        if (single && this.internalValues().length === 0) {
          this.internalValues.set([single]);
        }
      } else {
        const values = this.internalValues();
        if (!this.internalValue() && values.length > 0) {
          this.internalValue.set(values[0]);
        }
      }
    });

    // Setup intersection observer for infinite scroll
    effect((onCleanup) => {
      const el = this.sentinel();
      if (el) {
        this.observer = new IntersectionObserver(
          (entries) => {
            if (entries[0].isIntersecting && !this.isLoading() && this.hasMore()) {
              this.loadNextPage();
            }
          },
          { threshold: 0.1 },
        );
        this.observer.observe(el.nativeElement);
        onCleanup(() => {
          this.observer?.disconnect();
          this.observer = null;
        });
      }
    });
  }

  // Classes
  protected readonly buttonClasses = computed(() =>
    mergeClasses(
      'w-full justify-between',
      this.zStatus() === 'error' ? 'border-destructive text-destructive' : '',
    ),
  );

  protected readonly popoverClasses = computed(() => {
    const width = this.zWidth();
    return `${width === 'full' ? 'w-full' : 'w-[250px]'} p-0`;
  });

  protected readonly displayValue = computed(() => {
    if (this.multiselect()) {
      const values = this.internalValues();
      if (values.length === 0) return null;

      const labels = values
        .map((value) => {
          const option = this.options().find((o) => o.value === value);
          return option?.display ?? option?.label ?? null;
        })
        .filter((label): label is string => !!label && label.trim().length > 0);

      if (labels.length === 0) {
        return `${values.length} selected`;
      }
      if (labels.length <= 2) {
        return labels.join(', ');
      }
      return `${labels.slice(0, 2).join(', ')} +${labels.length - 2}`;
    }

    const val = this.internalValue();
    if (!val) return null;
    const opt = this.options().find((o) => o.value === val);
    return opt?.display ?? opt?.label ?? val;
  });

  // Methods
  setOpen(open: boolean) {
    this.open.set(open);
    if (open) {
      // Always reset search on open to provide a fresh list as requested
      this.searchQuery.set('');
      this.performSearch('', 1);

      runInInjectionContext(this.injector, () =>
        afterNextRender(() => {
          this.commandRef()?.refreshOptions();
          if (this.searchable()) {
            this.commandInputRef()?.focus();
          }
        }),
      );
    }
  }

  handleSelect(cmd: ZardCommandOption) {
    const val = cmd.value as string;
    if (this.multiselect()) {
      const selected = new Set(this.internalValues());
      if (selected.has(val)) {
        selected.delete(val);
      } else {
        selected.add(val);
      }

      const nextValues = [...selected];
      this.internalValues.set(nextValues);
      this.onChange(nextValues);
      this.valueChange.emit(nextValues);
      this.onTouched();
      return;
    }

    const newVal = val === this.internalValue() ? null : val;
    this.internalValue.set(newVal);
    this.onChange(newVal);
    this.valueChange.emit(newVal);
    this.onTouched();

    // Clear search on selection so it's ready for next time
    this.searchQuery.set('');

    this.popoverDirective().hide();
    this.buttonRef().nativeElement.focus();
  }

  onSearch(q: string) {
    if (!isPlatformBrowser(this.platformId)) return;

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
      this.searchQuery.set(q);
      this.performSearch(q, 1);
    }, 250);
  }

  loadNextPage() {
    this.performSearch(this.searchQuery(), this.currentPage() + 1);
  }

  protected isSelected(value: string): boolean {
    if (this.multiselect()) {
      return this.internalValues().includes(value);
    }
    return this.internalValue() === value;
  }

  private performSearch(q: string, page: number) {
    const loaderFn = this.loadOptions?.();
    if (!loaderFn) return;

    if (page === 1) {
      // Keep selected options while refreshing page 1 to avoid button text flicker.
      const selectedValues = this.multiselect()
        ? new Set(this.internalValues())
        : new Set(this.internalValue() ? [this.internalValue() as string] : []);
      const selectedOptions = this.options().filter((option) => selectedValues.has(option.value));
      this.options.set(selectedOptions);
    }

    this.isLoading.set(true);
    loaderFn(q, page).subscribe({
      next: (items) => {
        const mapper = this.mapFn?.();
        const mapped = (items || []).map((i) => (mapper ? mapper(i) : (i as TypeaheadOption)));

        if (page === 1) {
          this.options.update((current) => this.mergeUniqueOptions([...current, ...mapped]));
        } else {
          this.options.update((prev) => this.mergeUniqueOptions([...prev, ...mapped]));
        }

        this.currentPage.set(page);
        this.hasMore.set(mapped.length >= this.pageSize());
        this.isLoading.set(false);

        // Notify command component that options changed
        runInInjectionContext(this.injector, () =>
          afterNextRender(() => {
            this.commandRef()?.refreshOptions();
          }),
        );
      },
      error: () => this.isLoading.set(false),
    });
  }

  // CVA
  writeValue(v: string | string[] | null) {
    if (Array.isArray(v)) {
      const normalizedValues = this.normalizeIncomingValues(v);
      this.internalValues.set(normalizedValues);
      this.internalValue.set(normalizedValues[0] ?? null);
      return;
    }
    if (this.multiselect()) {
      this.internalValues.set(this.normalizeIncomingValues(v));
      return;
    }
    const normalized = v ?? null;
    this.internalValue.set(normalized);
  }
  registerOnChange(fn: any) {
    this.onChange = fn;
  }
  registerOnTouched(fn: any) {
    this.onTouched = fn;
  }
  setDisabledState(d: boolean) {
    /* handled via input */
  }

  private normalizeIncomingValues(value: string | string[] | null | undefined): string[] {
    const raw = Array.isArray(value) ? value : [];
    return this.dedupeStrings(raw);
  }

  private dedupeStrings(values: string[]): string[] {
    const seen = new Set<string>();
    const result: string[] = [];
    for (const raw of values) {
      const value = String(raw ?? '').trim();
      if (!value || seen.has(value)) continue;
      seen.add(value);
      result.push(value);
    }
    return result;
  }

  private arraysEqual(left: string[], right: string[]): boolean {
    if (left.length !== right.length) return false;
    for (let index = 0; index < left.length; index += 1) {
      if (left[index] !== right[index]) {
        return false;
      }
    }
    return true;
  }

  private mergeUniqueOptions(options: TypeaheadOption[]): TypeaheadOption[] {
    const map = new Map<string, TypeaheadOption>();
    for (const option of options) {
      map.set(option.value, option);
    }
    return [...map.values()];
  }
}
