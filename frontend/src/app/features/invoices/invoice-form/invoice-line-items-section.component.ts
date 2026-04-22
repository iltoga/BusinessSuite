
import { ChangeDetectionStrategy, Component, EventEmitter, Input, Output } from '@angular/core';
import { FormArray, FormGroup, ReactiveFormsModule } from '@angular/forms';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-invoice-line-items-section',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardComboboxComponent,
    ZardIconComponent,
    ZardInputDirective,
  ],
  templateUrl: './invoice-line-items-section.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceLineItemsSectionComponent {
  @Input({ required: true }) form!: FormGroup;
  @Input({ required: true }) invoiceApplications!: FormArray<FormGroup>;
  @Input({ required: true }) customerSelected = false;
  @Input({ required: true }) totalLabel = '';

  @Input({ required: true }) isLineLocked!: (group: FormGroup) => boolean;
  @Input({ required: true }) toComboboxValue!: (value: unknown) => string | null;
  @Input({ required: true }) availableProductOptionsForLine!: (
    group: FormGroup,
  ) => ZardComboboxOption[];
  @Input({ required: true }) availablePendingApplicationOptionsForLine!: (
    group: FormGroup,
  ) => ZardComboboxOption[];
  @Input({ required: true }) selectedProductPendingCount!: (group: FormGroup) => number;

  @Output() readonly addLineItem = new EventEmitter<void>();
  @Output() readonly removeLineItem = new EventEmitter<number>();
  @Output() readonly moveLineItemUp = new EventEmitter<number>();
  @Output() readonly moveLineItemDown = new EventEmitter<number>();
  @Output() readonly lineProductChange = new EventEmitter<{ group: FormGroup; value: string | null }>();
  @Output() readonly lineCustomerApplicationChange = new EventEmitter<{
    group: FormGroup;
    value: string | null;
  }>();
}
