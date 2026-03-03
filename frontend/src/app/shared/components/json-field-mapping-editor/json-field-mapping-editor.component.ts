import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  forwardRef,
  inject,
  Input,
  OnDestroy,
  signal,
} from '@angular/core';
import {
  ControlValueAccessor,
  FormArray,
  FormBuilder,
  FormControl,
  FormGroup,
  NG_VALUE_ACCESSOR,
  ReactiveFormsModule,
} from '@angular/forms';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardInputDirective } from '@/shared/components/input';
import { Subscription } from 'rxjs';

interface FieldMappingValue {
  field_name: string;
  description: string;
}

type FieldMappingRowForm = FormGroup<{
  fieldName: FormControl<string>;
  description: FormControl<string>;
}>;

@Component({
  selector: 'app-json-field-mapping-editor',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, ZardCardComponent, ZardButtonComponent, ZardInputDirective],
  templateUrl: './json-field-mapping-editor.component.html',
  styleUrls: ['./json-field-mapping-editor.component.css'],
  providers: [
    {
      provide: NG_VALUE_ACCESSOR,
      useExisting: forwardRef(() => JsonFieldMappingEditorComponent),
      multi: true,
    },
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class JsonFieldMappingEditorComponent implements ControlValueAccessor, OnDestroy {
  @Input() title = 'JSON Fields';
  @Input() description = 'Configure fields as JSON array entries.';

  private readonly fb = inject(FormBuilder);
  private readonly subscriptions = new Subscription();
  private onChange: (value: string) => void = () => {};
  private onTouched: () => void = () => {};
  private isWritingValue = false;

  readonly parseError = signal<string | null>(null);
  readonly form = this.fb.group({
    items: this.fb.array<FieldMappingRowForm>([]),
  });

  get items(): FormArray<FieldMappingRowForm> {
    return this.form.controls.items;
  }

  constructor() {
    this.ensureAtLeastOneRow();
    this.subscriptions.add(
      this.items.valueChanges.subscribe(() => {
        if (this.isWritingValue) {
          return;
        }
        this.emitJsonValue();
      }),
    );
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  writeValue(value: string | null | undefined): void {
    this.isWritingValue = true;
    this.setRowsFromJson(value);
    this.isWritingValue = false;
  }

  registerOnChange(fn: (value: string) => void): void {
    this.onChange = fn;
  }

  registerOnTouched(fn: () => void): void {
    this.onTouched = fn;
  }

  setDisabledState(isDisabled: boolean): void {
    if (isDisabled) {
      this.form.disable({ emitEvent: false });
      return;
    }
    this.form.enable({ emitEvent: false });
  }

  addRow(): void {
    this.items.push(this.createRow());
    this.handleTouched();
    this.emitJsonValue();
  }

  removeRow(index: number): void {
    if (this.items.length <= 1) {
      this.items.at(0).patchValue({ fieldName: '', description: '' }, { emitEvent: false });
      this.handleTouched();
      this.emitJsonValue();
      return;
    }
    this.items.removeAt(index);
    this.handleTouched();
    this.emitJsonValue();
  }

  trackByIndex(index: number): number {
    return index;
  }

  handleTouched(): void {
    this.onTouched();
  }

  private setRowsFromJson(rawValue: string | null | undefined): void {
    const parsed = this.parseJsonValue(rawValue);
    this.items.clear({ emitEvent: false });
    if (parsed.length > 0) {
      parsed.forEach((entry) => {
        this.items.push(
          this.createRow({
            fieldName: entry.field_name,
            description: entry.description,
          }),
          { emitEvent: false },
        );
      });
    }
    this.ensureAtLeastOneRow();
  }

  private parseJsonValue(rawValue: string | null | undefined): FieldMappingValue[] {
    this.parseError.set(null);
    const source = String(rawValue ?? '').trim();
    if (!source) {
      return [];
    }

    try {
      const parsed = JSON.parse(source);
      if (!Array.isArray(parsed)) {
        this.parseError.set('Expected a JSON array.');
        return [];
      }
      const normalized = parsed
        .map((item) => {
          if (!item || typeof item !== 'object') {
            return null;
          }
          const fieldName = String(
            (item as Record<string, unknown>)['field_name'] ??
              (item as Record<string, unknown>)['fieldName'] ??
              '',
          ).trim();
          const description = String((item as Record<string, unknown>)['description'] ?? '').trim();
          if (!fieldName) {
            return null;
          }
          return { field_name: fieldName, description };
        })
        .filter((item): item is FieldMappingValue => item !== null);
      return normalized;
    } catch {
      this.parseError.set('Invalid JSON format. Existing value could not be parsed.');
      return [];
    }
  }

  private emitJsonValue(): void {
    if (this.isWritingValue) {
      return;
    }
    this.parseError.set(null);
    const payload = this.items.controls
      .map((control) => ({
        field_name: control.controls.fieldName.value.trim(),
        description: control.controls.description.value.trim(),
      }))
      .filter((row) => row.field_name.length > 0);

    this.onChange(payload.length > 0 ? JSON.stringify(payload, null, 2) : '');
  }

  private ensureAtLeastOneRow(): void {
    if (this.items.length > 0) {
      return;
    }
    this.items.push(this.createRow(), { emitEvent: false });
  }

  private createRow(initial?: { fieldName?: string; description?: string }): FieldMappingRowForm {
    return this.fb.group({
      fieldName: this.fb.nonNullable.control(initial?.fieldName ?? ''),
      description: this.fb.nonNullable.control(initial?.description ?? ''),
    });
  }
}
