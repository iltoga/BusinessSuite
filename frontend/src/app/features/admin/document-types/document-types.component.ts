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
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold tracking-tight">Document Types</h1>
        <button z-button (click)="createNew()" [zDisabled]="isFormOpen()">Add Document Type</button>
      </div>

      <!-- Create/Edit Form Card -->
      @if (isFormOpen()) {
        <z-card class="p-6">
          <div class="space-y-4">
            <div class="flex items-center justify-between">
              <h2 class="text-lg font-semibold">
                {{ editingDocumentType() ? 'Edit' : 'Add' }} Document Type
              </h2>
              <button z-button zType="ghost" zSize="sm" (click)="closeForm()">Cancel</button>
            </div>

            <form [formGroup]="documentTypeForm" (ngSubmit)="saveDocumentType()" class="space-y-4">
              <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div class="space-y-2">
                  <label class="text-sm font-medium" for="name">Name *</label>
                  <input
                    z-input
                    id="name"
                    formControlName="name"
                    placeholder="Enter document type name"
                    [zStatus]="
                      documentTypeForm.get('name')?.invalid && documentTypeForm.get('name')?.touched
                        ? 'error'
                        : undefined
                    "
                  />
                  @if (
                    documentTypeForm.get('name')?.invalid && documentTypeForm.get('name')?.touched
                  ) {
                    <p class="text-sm text-destructive">Document type name is required</p>
                  }
                </div>

                <div class="space-y-2">
                  <label class="text-sm font-medium" for="validationRuleRegex"
                    >Validation Rule Regex</label
                  >
                  <input
                    z-input
                    id="validationRuleRegex"
                    formControlName="validationRuleRegex"
                    placeholder="Enter regex pattern"
                  />
                </div>
              </div>

              <div class="space-y-2">
                <label class="text-sm font-medium" for="description">Description</label>
                <textarea
                  z-input
                  id="description"
                  formControlName="description"
                  placeholder="Enter description"
                  rows="3"
                ></textarea>
              </div>

              <div class="grid grid-cols-2 md:grid-cols-3 gap-4">
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="hasOcrCheck" class="rounded" />
                  <span class="text-sm">Has OCR Check</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="hasExpirationDate" class="rounded" />
                  <span class="text-sm">Has Expiration Date</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="hasDocNumber" class="rounded" />
                  <span class="text-sm">Has Document Number</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="hasFile" class="rounded" />
                  <span class="text-sm">Has File</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="hasDetails" class="rounded" />
                  <span class="text-sm">Has Details</span>
                </label>
                <label class="flex items-center gap-2 cursor-pointer">
                  <input type="checkbox" formControlName="isInRequiredDocuments" class="rounded" />
                  <span class="text-sm">In Required Documents</span>
                </label>
              </div>

              <div class="flex justify-end gap-2 pt-4">
                <button z-button zType="outline" type="button" (click)="closeForm()">Cancel</button>
                <button
                  z-button
                  type="submit"
                  [zDisabled]="documentTypeForm.invalid || isSaving()"
                  [zLoading]="isSaving()"
                >
                  {{ editingDocumentType() ? 'Update' : 'Create' }}
                </button>
              </div>
            </form>
          </div>
        </z-card>
      }

      <!-- Table -->
      <z-card class="p-0">
        <app-data-table [data]="documentTypes()" [columns]="columns" [isLoading]="isLoading()" />
      </z-card>

      <!-- Confirm Delete Dialog -->
      <app-confirm-dialog
        [isOpen]="showConfirmDelete()"
        title="Delete Document Type"
        [message]="confirmDeleteMessage()"
        [destructive]="true"
        (confirmed)="confirmDelete()"
        (cancelled)="showConfirmDelete.set(false)"
      />
    </div>

    <!-- Actions Template for DataTable -->
    <ng-template #actionsTemplate let-item>
      <div class="flex items-center gap-2 flex-nowrap whitespace-nowrap">
        <z-button zType="warning" zSize="sm" (click)="editDocumentType(item)">Edit</z-button>
        <z-button zType="destructive" zSize="sm" (click)="deleteDocumentType(item)"
          >Delete</z-button
        >
      </div>
    </ng-template>
  `,
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
