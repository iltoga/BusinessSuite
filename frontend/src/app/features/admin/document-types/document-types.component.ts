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
import { Router } from '@angular/router';
import { catchError, EMPTY, finalize } from 'rxjs';

import { DocumentTypesService } from '@/core/api';
import { DocumentType } from '@/core/api/model/document-type';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  ColumnConfig,
  DataTableAction,
  DataTableComponent,
} from '@/shared/components/data-table/data-table.component';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';

@Component({
  selector: 'app-document-types',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardInputDirective,
    DataTableComponent,
    SearchToolbarComponent,
    ConfirmDialogComponent,
  ],
  templateUrl: './document-types.component.html',
  styleUrls: ['./document-types.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentTypesComponent implements OnInit {
  @ViewChild('documentTypeModalTemplate', { static: true })
  documentTypeModalTemplate!: TemplateRef<any>;
  @ViewChild('dataTable') dataTable?: DataTableComponent<DocumentType>;

  private fb = inject(FormBuilder);
  private router = inject(Router);
  private documentTypesApi = inject(DocumentTypesService);
  private toast = inject(GlobalToastService);
  private dialogService = inject(ZardDialogService);

  private dialogRef: any = null;

  readonly documentTypes = signal<DocumentType[]>([]);
  readonly isLoading = signal(true);
  readonly query = signal('');
  readonly isDialogOpen = signal(false);
  readonly isSaving = signal(false);
  readonly editingDocumentType = signal<DocumentType | null>(null);
  readonly showConfirmDelete = signal(false);
  readonly confirmDeleteMessage = signal('');
  readonly pendingEditId = signal<number | null>(null);

  columns: ColumnConfig<DocumentType>[] = [
    { key: 'name', header: 'Name', sortable: true },
    { key: 'description', header: 'Description', sortable: false },
    { key: 'hasOcrCheck', header: 'OCR Check', sortable: false },
    { key: 'hasExpirationDate', header: 'Expiration', sortable: false },
    { key: 'actions', header: 'Actions' },
  ];
  readonly actions: DataTableAction<DocumentType>[] = [
    {
      label: 'View details',
      icon: 'eye',
      variant: 'default',
      shortcut: 'v',
      action: (item) =>
        this.router.navigate(['/admin/document-types', item.id], {
          state: {
            from: 'admin-document-types',
            focusId: item.id,
            searchQuery: this.query(),
          },
        }),
    },
    {
      label: 'Edit',
      icon: 'settings',
      variant: 'warning',
      shortcut: 'e',
      action: (item) => this.editDocumentType(item),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      shortcut: 'd',
      action: (item) => this.deleteDocumentType(item),
    },
  ];

  readonly documentTypeForm = this.fb.group({
    name: ['', Validators.required],
    description: [''],
    validationRuleRegex: [''],
    validationRuleAiPositive: [''],
    validationRuleAiNegative: [''],
    hasOcrCheck: [false],
    hasExpirationDate: [false],
    hasDocNumber: [false],
    hasFile: [false],
    hasDetails: [false],
    isInRequiredDocuments: [false],
  });

  ngOnInit(): void {
    if (typeof window !== 'undefined') {
      const state = (window as any).history.state ?? {};
      const openEditId = Number(state.openEditId ?? 0);
      if (openEditId > 0) {
        this.pendingEditId.set(openEditId);
      }
      if (typeof state.searchQuery === 'string' && state.searchQuery.trim()) {
        this.query.set(state.searchQuery.trim());
      }
    }
    this.loadDocumentTypes();
  }

  onQueryChange(value: string): void {
    const trimmed = value.trim();
    if (this.query() === trimmed) return;
    this.query.set(trimmed);
    this.loadDocumentTypes();
  }

  onEnterSearch(): void {
    this.dataTable?.focusFirstRowIfNone();
  }

  private loadDocumentTypes(): void {
    const query = this.query().trim();
    this.isLoading.set(true);
    this.documentTypesApi
      .documentTypesList(undefined, query || undefined)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load document types');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((data) => {
        const items = data || [];
        this.documentTypes.set(items);
        this.openPendingEditIfRequested(items);
      });
  }

  private openPendingEditIfRequested(items: DocumentType[]): void {
    const pendingId = this.pendingEditId();
    if (!pendingId) {
      return;
    }

    const fromList = items.find((item) => item.id === pendingId);
    if (fromList) {
      this.pendingEditId.set(null);
      this.editDocumentType(fromList);
      return;
    }

    this.pendingEditId.set(null);
    this.documentTypesApi
      .documentTypesRetrieve(pendingId)
      .pipe(
        catchError(() => {
          this.toast.error('Could not load the selected document type for editing');
          return EMPTY;
        }),
      )
      .subscribe((documentType) => this.editDocumentType(documentType));
  }

  createNew(): void {
    this.editingDocumentType.set(null);
    this.documentTypeForm.reset({
      name: '',
      description: '',
      validationRuleRegex: '',
      validationRuleAiPositive: '',
      validationRuleAiNegative: '',
      hasOcrCheck: false,
      hasExpirationDate: false,
      hasDocNumber: false,
      hasFile: false,
      hasDetails: false,
      isInRequiredDocuments: false,
    });

    this.dialogRef = this.dialogService.create({
      zTitle: 'Add Document Type',
      zContent: this.documentTypeModalTemplate,
      zHideFooter: true,
      zClosable: true,
      // Custom sizing and border for clearer modal presentation
      zCustomClasses: 'border-2 border-primary/30 sm:max-w-[760px]',
      zWidth: '760px',
      zOnCancel: () => {
        // ensure internal state is reset when the dialog is closed via header X or backdrop
        this.isDialogOpen.set(false);
        this.editingDocumentType.set(null);
        this.dialogRef = null;
      },
    });
    this.isDialogOpen.set(true);
  }

  editDocumentType(documentType: DocumentType): void {
    this.editingDocumentType.set(documentType);
    this.documentTypeForm.patchValue({
      name: documentType.name || '',
      description: documentType.description || '',
      validationRuleRegex: documentType.validationRuleRegex || '',
      validationRuleAiPositive: documentType.validationRuleAiPositive || '',
      validationRuleAiNegative: documentType.validationRuleAiNegative || '',
      hasOcrCheck: documentType.hasOcrCheck || false,
      hasExpirationDate: documentType.hasExpirationDate || false,
      hasDocNumber: documentType.hasDocNumber || false,
      hasFile: documentType.hasFile || false,
      hasDetails: documentType.hasDetails || false,
      isInRequiredDocuments: documentType.isInRequiredDocuments || false,
    });

    this.dialogRef = this.dialogService.create({
      zTitle: 'Edit Document Type',
      zContent: this.documentTypeModalTemplate,
      zHideFooter: true,
      zClosable: true,
      // Custom sizing and border for clearer modal presentation
      zCustomClasses: 'border-2 border-primary/30 sm:max-w-[760px]',
      zWidth: '760px',
      zOnCancel: () => {
        // ensure internal state is reset when the dialog is closed via header X or backdrop
        this.isDialogOpen.set(false);
        this.editingDocumentType.set(null);
        this.dialogRef = null;
      },
    });
    this.isDialogOpen.set(true);
  }

  saveDocumentType(): void {
    if (this.documentTypeForm.invalid) return;

    this.isSaving.set(true);
    const formValue = this.documentTypeForm.value;
    const documentTypeData: DocumentType = {
      id: this.editingDocumentType()?.id ?? 0,
      name: formValue.name!,
      description: formValue.description || '',
      validationRuleRegex: formValue.validationRuleRegex || '',
      validationRuleAiPositive: formValue.validationRuleAiPositive || '',
      validationRuleAiNegative: formValue.validationRuleAiNegative || '',
      hasOcrCheck: formValue.hasOcrCheck || false,
      hasExpirationDate: formValue.hasExpirationDate || false,
      hasDocNumber: formValue.hasDocNumber || false,
      hasFile: formValue.hasFile || false,
      hasDetails: formValue.hasDetails || false,
      isInRequiredDocuments: formValue.isInRequiredDocuments || false,
    };

    const request = this.editingDocumentType()
      ? this.documentTypesApi.documentTypesUpdate(this.editingDocumentType()!.id!, documentTypeData)
      : this.documentTypesApi.documentTypesCreate(documentTypeData);

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
    if (this.dialogRef) {
      this.dialogRef.close();
      this.dialogRef = null;
    }
    this.isDialogOpen.set(false);
    this.editingDocumentType.set(null);
  }
}
