import {
  ChangeDetectionStrategy,
  Component,
  computed,
  forwardRef,
  inject,
  input,
  model,
  signal,
  TemplateRef,
  viewChild,
  ViewEncapsulation,
} from '@angular/core';
import { NG_VALUE_ACCESSOR, type ControlValueAccessor } from '@angular/forms';

import { ConfigService } from '@/core/services/config.service';
import { ZardCalendarComponent } from '@/shared/components/calendar';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ZardInputGroupComponent } from '@/shared/components/input-group';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';

type SupportedDateFormat = 'dd-MM-yyyy' | 'yyyy-MM-dd' | 'dd/MM/yyyy' | 'MM/dd/yyyy';

@Component({
  selector: 'z-date-input',
  standalone: true,
  imports: [
    ZardInputDirective,
    ZardInputGroupComponent,
    ZardIconComponent,
    ZardPopoverComponent,
    ZardPopoverDirective,
    ZardCalendarComponent,
  ],
  template: `
    <z-input-group [zSize]="zSize()" [zAddonAfter]="calendarButton">
      <input
        z-input
        type="text"
        [placeholder]="effectivePlaceholder()"
        [value]="displayValue()"
        (input)="onInput($event)"
        (blur)="onBlur()"
        [disabled]="disabled()"
        class="w-full"
      />
    </z-input-group>

    <ng-template #calendarButton>
      <button
        type="button"
        tabindex="-1"
        class="flex items-center justify-center px-3 hover:bg-muted cursor-pointer"
        [disabled]="disabled()"
        zPopover
        #popoverDirective="zPopover"
        [zContent]="calendarTemplate"
        [zMatchTriggerWidth]="false"
        zTrigger="click"
        (zVisibleChange)="onPopoverVisibilityChange($event)"
      >
        <z-icon zType="calendar" class="h-4 w-4" />
      </button>
    </ng-template>

    <ng-template #calendarTemplate>
      <z-popover class="w-auto p-0">
        <z-calendar
          #calendar
          class="border-0"
          [value]="value() ?? null"
          [minDate]="minDate() ?? null"
          [maxDate]="maxDate() ?? null"
          [disabled]="disabled()"
          (dateChange)="onCalendarDateChange($event)"
        />
      </z-popover>
    </ng-template>
  `,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => ZardDateInputComponent),
      multi: true,
    },
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  encapsulation: ViewEncapsulation.None,
  exportAs: 'zDateInput',
})
export class ZardDateInputComponent implements ControlValueAccessor {
  private configService = inject(ConfigService);

  readonly calendarTemplate = viewChild.required<TemplateRef<unknown>>('calendarTemplate');
  readonly popoverDirective = viewChild<ZardPopoverDirective>('popoverDirective');
  readonly calendar = viewChild<ZardCalendarComponent>('calendar');

  readonly zSize = input<'sm' | 'default' | 'lg'>('default');
  readonly placeholder = input<string | null | undefined>(null);
  readonly value = model<Date | null | undefined>(null);
  readonly minDate = input<Date | null | undefined>(null);
  readonly maxDate = input<Date | null | undefined>(null);
  readonly disabled = model<boolean>(false);

  private inputValue = signal<string>('');
  private readonly configuredDateFormat = computed<SupportedDateFormat>(() =>
    this.normalizeDateFormat(this.configService.config().dateFormat),
  );

  // eslint-disable-next-line @typescript-eslint/no-empty-function
  private onChange: (value: Date | null) => void = () => {};
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  private onTouched: () => void = () => {};

  protected readonly effectivePlaceholder = computed(() => {
    const customPlaceholder = this.placeholder()?.trim();
    if (customPlaceholder) {
      return customPlaceholder;
    }
    return this.toPlaceholder(this.configuredDateFormat());
  });

  protected readonly displayValue = computed(() => {
    const date = this.value();
    if (date instanceof Date && !isNaN(date.getTime())) {
      return this.formatDateForDisplay(date);
    }
    return this.inputValue();
  });

  protected onInput(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.inputValue.set(input.value);
  }

  protected onBlur(): void {
    const dateStr = this.inputValue();
    if (!dateStr) {
      this.value.set(null);
      this.onChange(null);
      this.onTouched();
      return;
    }

    const date = this.parseDate(dateStr);
    if (date && !isNaN(date.getTime())) {
      this.value.set(date);
      this.onChange(date);
    }
    this.onTouched();
  }

  protected onCalendarDateChange(date: Date | Date[]): void {
    const singleDate = Array.isArray(date) ? (date[0] ?? null) : date;
    this.value.set(singleDate);
    this.inputValue.set(singleDate ? this.formatDateForDisplay(singleDate) : '');
    this.onChange(singleDate);
    this.onTouched();
    this.popoverDirective()?.hide();
  }

  protected onPopoverVisibilityChange(visible: boolean): void {
    if (visible) {
      setTimeout(() => {
        if (this.calendar()) {
          this.calendar()!.resetNavigation();
        }
      });
    }
  }

  private parseDate(dateStr: string): Date | null {
    const trimmed = dateStr.trim();
    if (!trimmed) {
      return null;
    }

    const configured = this.parseDateByFormat(trimmed, this.configuredDateFormat());
    if (configured) {
      return configured;
    }

    const fallbackFormats: SupportedDateFormat[] = [
      'dd-MM-yyyy',
      'yyyy-MM-dd',
      'dd/MM/yyyy',
      'MM/dd/yyyy',
    ];

    for (const format of fallbackFormats) {
      if (format === this.configuredDateFormat()) {
        continue;
      }
      const fallback = this.parseDateByFormat(trimmed, format);
      if (fallback) {
        return fallback;
      }
    }

    const parsed = new Date(trimmed);
    if (!Number.isNaN(parsed.getTime())) {
      return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }

    return null;
  }

  private formatDateForDisplay(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');

    switch (this.configuredDateFormat()) {
      case 'yyyy-MM-dd':
        return `${year}-${month}-${day}`;
      case 'dd/MM/yyyy':
        return `${day}/${month}/${year}`;
      case 'MM/dd/yyyy':
        return `${month}/${day}/${year}`;
      case 'dd-MM-yyyy':
      default:
        return `${day}-${month}-${year}`;
    }
  }

  writeValue(value: Date | null): void {
    this.value.set(value);
    this.inputValue.set(value ? this.formatDateForDisplay(value) : '');
  }

  registerOnChange(fn: (value: Date | null) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }

  private normalizeDateFormat(format: string | null | undefined): SupportedDateFormat {
    const normalized = (format ?? '').trim();
    if (normalized === 'yyyy-MM-dd') return 'yyyy-MM-dd';
    if (normalized === 'dd/MM/yyyy') return 'dd/MM/yyyy';
    if (normalized === 'MM/dd/yyyy') return 'MM/dd/yyyy';
    return 'dd-MM-yyyy';
  }

  private toPlaceholder(format: SupportedDateFormat): string {
    return format.replace('dd', 'DD').replace('yyyy', 'YYYY');
  }

  private parseDateByFormat(dateStr: string, format: SupportedDateFormat): Date | null {
    switch (format) {
      case 'yyyy-MM-dd': {
        const match = dateStr.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
        if (!match) return null;
        const [, year, month, day] = match;
        return this.buildDate(Number(year), Number(month), Number(day));
      }
      case 'dd/MM/yyyy': {
        const match = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (!match) return null;
        const [, day, month, year] = match;
        return this.buildDate(Number(year), Number(month), Number(day));
      }
      case 'MM/dd/yyyy': {
        const match = dateStr.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
        if (!match) return null;
        const [, month, day, year] = match;
        return this.buildDate(Number(year), Number(month), Number(day));
      }
      case 'dd-MM-yyyy':
      default: {
        const match = dateStr.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
        if (!match) return null;
        const [, day, month, year] = match;
        return this.buildDate(Number(year), Number(month), Number(day));
      }
    }
  }

  private buildDate(year: number, month: number, day: number): Date | null {
    if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
      return null;
    }
    if (month < 1 || month > 12 || day < 1 || day > 31) {
      return null;
    }

    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }
}
