import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  forwardRef,
  input,
  model,
  signal,
  TemplateRef,
  viewChild,
  ViewEncapsulation,
} from '@angular/core';
import { NG_VALUE_ACCESSOR, type ControlValueAccessor } from '@angular/forms';

import { ZardCalendarComponent } from '@/shared/components/calendar';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ZardInputGroupComponent } from '@/shared/components/input-group';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';

@Component({
  selector: 'z-date-input',
  standalone: true,
  imports: [
    CommonModule,
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
        [placeholder]="placeholder()"
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
          [value]="value()"
          [minDate]="minDate()"
          [maxDate]="maxDate()"
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
  readonly calendarTemplate = viewChild.required<TemplateRef<unknown>>('calendarTemplate');
  readonly popoverDirective = viewChild<ZardPopoverDirective>('popoverDirective');
  readonly calendar = viewChild<ZardCalendarComponent>('calendar');

  readonly zSize = input<'sm' | 'default' | 'lg'>('default');
  readonly placeholder = input<string>('DD-MM-YYYY');
  readonly value = model<Date | null>(null);
  readonly minDate = input<Date | null>(null);
  readonly maxDate = input<Date | null>(null);
  readonly disabled = model<boolean>(false);

  private inputValue = signal<string>('');

  // eslint-disable-next-line @typescript-eslint/no-empty-function
  private onChange: (value: Date | null) => void = () => {};
  // eslint-disable-next-line @typescript-eslint/no-empty-function
  private onTouched: () => void = () => {};

  protected readonly displayValue = computed(() => {
    const date = this.value();
    if (date instanceof Date && !isNaN(date.getTime())) {
      return this.formatDateToDDMMYYYY(date);
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
    this.inputValue.set(singleDate ? this.formatDateToDDMMYYYY(singleDate) : '');
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
    // Try parsing DD-MM-YYYY format
    const ddmmyyyyMatch = dateStr.match(/^(\d{1,2})-(\d{1,2})-(\d{4})$/);
    if (ddmmyyyyMatch) {
      const [, day, month, year] = ddmmyyyyMatch;
      return new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    }

    // Try parsing ISO format (YYYY-MM-DD)
    const isoMatch = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (isoMatch) {
      const [, year, month, day] = isoMatch;
      return new Date(parseInt(year), parseInt(month) - 1, parseInt(day));
    }

    // Try parsing other common formats (DD/MM/YYYY, MM/DD/YYYY)
    const slashMatch = dateStr.match(/^(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})$/);
    if (slashMatch) {
      const [, first, second, year] = slashMatch;
      // Assume DD/MM/YYYY format (European)
      return new Date(parseInt(year), parseInt(second) - 1, parseInt(first));
    }

    return null;
  }

  private formatDateToDDMMYYYY(date: Date): string {
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${day}-${month}-${year}`;
  }

  writeValue(value: Date | null): void {
    this.value.set(value);
    this.inputValue.set(value ? this.formatDateToDDMMYYYY(value) : '');
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
}
