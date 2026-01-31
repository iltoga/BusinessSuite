import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, forwardRef, model } from '@angular/core';
import { ControlValueAccessor, NG_VALUE_ACCESSOR } from '@angular/forms';

import { ZardIconComponent } from '@/shared/components/icon';
import { mergeClasses } from '@/shared/utils/merge-classes';

@Component({
  selector: 'z-checkbox',
  standalone: true,
  imports: [CommonModule, ZardIconComponent],
  template: `
    <label
      class="flex items-center gap-2 cursor-pointer"
      [class.opacity-50]="disabled()"
      [class.cursor-not-allowed]="disabled()"
    >
      <div
        [class]="checkboxClasses()"
        (click)="toggle()"
        role="checkbox"
        tabindex="0"
        [attr.aria-checked]="checked()"
        (keydown.space)="toggle(); $event.preventDefault()"
        (keydown.enter)="toggle()"
      >
        @if (checked()) {
          <z-icon zType="check" class="h-3 w-3 text-primary-foreground" />
        }
      </div>
      <ng-content />
    </label>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => ZardCheckboxComponent),
      multi: true,
    },
  ],
})
export class ZardCheckboxComponent implements ControlValueAccessor {
  readonly disabled = model(false);
  readonly checked = model(false);

  readonly checkboxClasses = computed(() =>
    mergeClasses(
      'h-4 w-4 rounded border flex items-center justify-center transition-colors',
      this.checked()
        ? 'bg-primary border-primary'
        : 'bg-background border-input hover:border-primary',
      this.disabled() ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer',
    ),
  );

  private onChange: (value: boolean) => void = () => {};
  private onTouched: () => void = () => {};

  toggle(): void {
    if (this.disabled()) return;
    const newValue = !this.checked();
    this.checked.set(newValue);
    this.onChange(newValue);
    this.onTouched();
  }

  // ControlValueAccessor implementation
  writeValue(value: boolean): void {
    this.checked.set(!!value);
  }

  registerOnChange(fn: (value: boolean) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    this.disabled.set(isDisabled);
  }
}
