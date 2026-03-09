import { FormArray, FormBuilder } from '@angular/forms';

import { ApplicationFormDocumentsSectionComponent } from './application-form-documents-section.component';

describe('ApplicationFormDocumentsSectionComponent', () => {
  it('filters out additional stay permit types when one is already selected', () => {
    const component = new ApplicationFormDocumentsSectionComponent();
    const fb = new FormBuilder();

    component.documentsArray = new FormArray([
      fb.group({ docTypeId: ['1'], required: [true] }),
      fb.group({ docTypeId: [''], required: [false] }),
    ]);
    component.documentTypeOptions = [
      { value: '1', label: 'ITAS' },
      { value: '2', label: 'KITAS' },
      { value: '3', label: 'Passport' },
    ];
    component.selectedDocTypeIds = ['1'];
    component.stayPermitDocTypeIds = ['1', '2'];
    component.productSelected = true;
    component.documentsLoading = false;
    component.documentsPanelOpen = true;

    component.ngOnChanges();

    expect(component.filteredDocumentTypeOptions[1]).toEqual([{ value: '3', label: 'Passport' }]);
  });
});
