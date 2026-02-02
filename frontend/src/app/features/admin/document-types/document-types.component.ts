import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnInit,
  signal,
  TemplateRef,
  ViewChild,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { catchError, EMPTY, finalize } from 'rxjs';

import { DocumentTypesService } from '@/core/api';
import { DocumentType } from '@/core/api/model/document-type';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  ColumnConfig,
  DataTableComponent,
} from '@/shared/components/data-table/data-table.component';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-document-types',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    ZardCheckboxComponent,
    ZardInputDirective,
    DataTableComponent,
    ConfirmDialogComponent,
  ],
  templateUrl: './document-types.component.html',
  styleUrls: ['./document-types.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentTypesComponent implements OnInit {
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;

  private fb = inject(FormBuilder);
  private documentTypesApi = inject(DocumentTypesService);
  private toast = inject(GlobalToastService);

  readonly documentTypes = signal<DocumentType[]>([]);
  readonly isLoading = signal(true);
  readonly isFormOpen = signal(false);
  readonly isSaving = signal(false);
  readonly editingDocumentType = signal<DocumentType | null>(null);
  readonly showConfirmDelete = signal(false);
  readonly confirmDeleteMessage = signal('');

  columns: ColumnConfig[] = [
    { key: 'name', header: 'Name', sortable: true },
    { key: 'description', header: 'Description', sortable: false },
    { key: 'hasOcrCheck', header: 'OCR Check', sortable: false },
    { key: 'hasExpirationDate', header: 'Expiration', sortable: false },
    { key: 'actions', header: '' },
  ];

  readonly documentTypeForm = this.fb.group({
    name: ['', Validators.required],
    description: [''],
    validationRuleRegex: [''],
    hasOcrCheck: [false],
    hasExpirationDate: [false],
    hasDocNumber: [false],
    hasFile: [false],
    hasDetails: [false],
    isInRequiredDocuments: [false],
  });

  ngOnInit(): void {
    this.columns[this.columns.length - 1].template = this.actionsTemplate;
    this.loadDocumentTypes();
  }

  private loadDocumentTypes(): void {
    this.isLoading.set(true);
    this.documentTypesApi
      .documentTypesList()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load document types');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((data) => {
        this.documentTypes.set(data || []);
      });
  }

  createNew(): void {
    this.editingDocumentType.set(null);
    this.documentTypeForm.reset({
      name: '',
      description: '',
      validationRuleRegex: '',
      hasOcrCheck: false,
      hasExpirationDate: false,
      hasDocNumber: false,
      hasFile: false,
      hasDetails: false,
      isInRequiredDocuments: false,
    });
    this.isFormOpen.set(true);
  }

  editDocumentType(documentType: DocumentType): void {
    this.editingDocumentType.set(documentType);
    this.documentTypeForm.patchValue({
      name: documentType.name || '',
      description: documentType.description || '',
      validationRuleRegex: '',
      hasOcrCheck: documentType.hasOcrCheck || false,
      hasExpirationDate: documentType.hasExpirationDate || false,
      hasDocNumber: documentType.hasDocNumber || false,
      hasFile: documentType.hasFile || false,
      hasDetails: documentType.hasDetails || false,
      isInRequiredDocuments: documentType.isInRequiredDocuments || false,
    });
    this.isFormOpen.set(true);
  }

  saveDocumentType(): void {
    if (this.documentTypeForm.invalid) return;

    this.isSaving.set(true);
    const formValue = this.documentTypeForm.value;
    const documentTypeData: Partial<DocumentType> = {
      name: formValue.name!,
      description: formValue.description || '',
      hasOcrCheck: formValue.hasOcrCheck || false,
      hasExpirationDate: formValue.hasExpirationDate || false,
      hasDocNumber: formValue.hasDocNumber || false,
      hasFile: formValue.hasFile || false,
      hasDetails: formValue.hasDetails || false,
      isInRequiredDocuments: formValue.isInRequiredDocuments || false,
    };

    const request = this.editingDocumentType()
      ? this.documentTypesApi.documentTypesUpdate(
          this.editingDocumentType()!.id!,
          documentTypeData as any,
        )
      : this.documentTypesApi.documentTypesCreate(documentTypeData as any);

    request
      .pipe(
        catchError(() => {
          this.toast.error('Failed to save document type');
          return EMPTY;
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe(() => {
        const action = this.editingDocumentType() ? 'updated' : 'created';
        this.toast.success(`Document type ${action} successfully`);
        this.closeForm();
        this.loadDocumentTypes();
      });
  }

  deleteDocumentType(documentType: DocumentType): void {
    this.documentTypesApi
      .documentTypesCanDeleteRetrieve(documentType.id!)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to check if document type can be deleted');
          return EMPTY;
        }),
      )
      .subscribe((result: any) => {
        if (!result.canDelete) {
          this.toast.error(result.message);
          return;
        }

        this.confirmDeleteMessage.set(
          result.warning ||
            `Are you sure you want to delete "${documentType.name}"? This action cannot be undone.`,
        );
        this.editingDocumentType.set(documentType);
        this.showConfirmDelete.set(true);
      });
  }

  confirmDelete(): void {
    const documentType = this.editingDocumentType();
    if (!documentType) return;

    this.documentTypesApi
      .documentTypesDestroy(documentType.id!)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to delete document type');
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.toast.success('Document type deleted successfully');
        this.showConfirmDelete.set(false);
        this.editingDocumentType.set(null);
        this.loadDocumentTypes();
      });
  }

  closeForm(): void {
    this.isFormOpen.set(false);
    this.editingDocumentType.set(null);
  }
}
