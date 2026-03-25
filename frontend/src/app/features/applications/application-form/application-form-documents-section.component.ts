
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
} from '@angular/core';
import { FormArray, ReactiveFormsModule } from '@angular/forms';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardIconComponent } from '@/shared/components/icon';

@Component({
  selector: 'app-application-form-documents-section',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardCardComponent,
    ZardIconComponent,
    ZardComboboxComponent,
    ZardButtonComponent
],
  templateUrl: './application-form-documents-section.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationFormDocumentsSectionComponent implements OnChanges {
  @Input({ required: true }) documentsArray!: FormArray;
  @Input({ required: true }) documentsLoading = false;
  @Input({ required: true }) documentsPanelOpen = false;
  @Input({ required: true }) documentTypeOptions: ZardComboboxOption[] = [];
  @Input({ required: true }) selectedDocTypeIds: string[] = [];
  @Input({ required: true }) stayPermitDocTypeIds: string[] = [];
  @Input({ required: true }) productSelected = false;

  filteredDocumentTypeOptions: Array<ZardComboboxOption[] | undefined> = [];

  @Output() readonly addDocument = new EventEmitter<void>();
  @Output() readonly removeDocument = new EventEmitter<number>();

  ngOnChanges(): void {
    this.rebuildFilteredDocumentTypeOptions();
  }

  private rebuildFilteredDocumentTypeOptions(): void {
    const allOptions = this.documentTypeOptions;
    this.filteredDocumentTypeOptions = this.documentsArray.controls.map((docGroup, index) => {
      const currentSelected = String(docGroup.get('docTypeId')?.value || '');
      const otherSelected = this.selectedDocTypeIds.filter(
        (_, selectedIndex) => selectedIndex !== index,
      );
      const hasOtherStayPermit = otherSelected.some((id) => this.stayPermitDocTypeIds.includes(id));

      return allOptions.filter(
        (opt) =>
          opt.value === currentSelected ||
          (!otherSelected.includes(opt.value) &&
            (!hasOtherStayPermit || !this.stayPermitDocTypeIds.includes(opt.value))),
      );
    });
  }
}
