import { HttpClient, HttpParams } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  TemplateRef,
  ViewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { catchError, EMPTY, finalize, map, type Observable } from 'rxjs';

import { DocumentTypesService } from '@/core/api';
import { DocumentType } from '@/core/api/model/document-type';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  ColumnConfig,
  DataTableAction,
  DataTableComponent,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { JsonFieldMappingEditorComponent } from '@/shared/components/json-field-mapping-editor';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from '@/shared/core/base-list.component';

/**
 * Document Types component
 *
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 *
 * Note: This component has complex deprecation logic that is component-specific
 */
@Component({
  selector: 'app-document-types',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardInputDirective,
    DataTableComponent,
    SearchToolbarComponent,
    ConfirmDialogComponent,
    JsonFieldMappingEditorComponent,
    PaginationControlsComponent,
  ],
  templateUrl: './document-types.component.html',
  styleUrls: ['./document-types.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentTypesComponent extends BaseListComponent<DocumentType> {
  @ViewChild('documentTypeModalTemplate', { static: true })
  documentTypeModalTemplate!: TemplateRef<any>;
  @ViewChild('descriptionTemplate', { static: true })
  descriptionTemplate!: TemplateRef<{ $implicit: DocumentType; value: unknown; row: DocumentType }>;
  @ViewChild('dataTable') localDataTable?: DataTableComponent<DocumentType>;

  private readonly fb = inject(FormBuilder);
  private readonly http = inject(HttpClient);
  private readonly documentTypesApi = inject(DocumentTypesService);
  private readonly dialogService = inject(ZardDialogService);

  // Document types-specific state
  private dialogRef: any = null;
  readonly includeDeprecated = signal(false);
  readonly isDialogOpen = signal(false);
  readonly isSaving = signal(false);
  readonly editingDocumentType = signal<DocumentType | null>(null);
  readonly showConfirmDelete = signal(false);
  readonly confirmDeleteMessage = signal('');
  readonly showDeprecationConfirm = signal(false);
  readonly deprecationConfirmMessage = signal('');
  readonly pendingDeprecationPayload = signal<DocumentType | null>(null);
  readonly pendingEditId = signal<number | null>(null);

  // Columns configuration
  readonly columns = computed<ColumnConfig<DocumentType>[]>(() => [
    { key: 'name', header: 'Name', sortable: true },
    {
      key: 'description',
      header: 'Description',
      sortable: false,
      template: this.descriptionTemplate,
    },
    { key: 'autoGeneration', header: 'Auto', sortable: false },
    { key: 'aiValidation', header: 'AI Validation', sortable: false },
    { key: 'deprecated', header: 'Deprecated', sortable: false },
    { key: 'hasExpirationDate', header: 'Expiration', sortable: false },
    { key: 'actions', header: 'Actions', width: '4%' },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<DocumentType>[]>(() => [
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
  ]);

  // Document type form
  readonly documentTypeForm = this.fb.group({
    name: ['', Validators.required],
    description: [''],
    validationRuleRegex: [''],
    validationRuleAiPositive: [''],
    validationRuleAiNegative: [''],
    aiStructuredOutput: [''],
    aiValidation: [true],
    deprecated: [false],
    autoGeneration: [false],
    hasExpirationDate: [false],
    expiringThresholdDays: [null as number | null, [Validators.min(0)]],
    isStayPermit: [false],
    hasDocNumber: [false],
    hasFile: [false],
    hasDetails: [false],
    isInRequiredDocuments: [false],
  });

  constructor() {
    super();
    this.config = {
      entityType: 'admin/document-types',
      entityLabel: 'Document Types',
      defaultPageSize: 12,
    } as BaseListConfig<DocumentType>;
  }

  /**
   * Create the Observable that fetches document types.
   * The API returns a flat array, so we wrap it in a PaginatedResponse.
   */
  protected override createListLoader(
    params: ListRequestParams,
  ): Observable<PaginatedResponse<DocumentType>> {
    const query = params.query?.trim();
    const page = params.page || 1;
    const pageSize = params.pageSize || this.pageSize();

    return this.documentTypesApi
      .documentTypesList(undefined, !this.includeDeprecated(), params.ordering, query || undefined)
      .pipe(
        map((data) => {
          const items = data || [];
          this.openPendingEditIfRequested(items);

          // Client-side pagination for non-paginated endpoint
          const start = (page - 1) * pageSize;
          const results = items.slice(start, start + pageSize);

          return {
            results,
            count: items.length,
          };
        }),
      );
  }

  /**
   * Handle sort change
   */
  override onSortChange(event: SortEvent): void {
    const ordering = event.direction === 'desc' ? `-${event.column}` : event.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.reload();
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    super.ngOnInit();

    this.bindStayPermitRule();
    this.bindExpirationThresholdRule();

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
  }

  /**
   * Handle toggle include deprecated
   */
  onToggleIncludeDeprecated(value: boolean): void {
    this.includeDeprecated.set(value);
    this.reload();
  }

  /**
   * Handle enter in search to focus table
   */
  onEnterSearch(): void {
    this.dataTable().focusFirstRowIfNone();
  }

  /**
   * Open pending edit if requested
   */
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

  /**
   * Create new document type
   */
  createNew(): void {
    this.editingDocumentType.set(null);
    this.documentTypeForm.reset({
      name: '',
      description: '',
      validationRuleRegex: '',
      validationRuleAiPositive: '',
      validationRuleAiNegative: '',
      aiStructuredOutput: '',
      aiValidation: true,
      deprecated: false,
      autoGeneration: false,
      hasExpirationDate: false,
      expiringThresholdDays: null,
      isStayPermit: false,
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
      zCustomClasses:
        'border-2 border-primary/30 sm:max-w-[760px] max-h-[calc(100vh-2rem)] overflow-hidden',
      zWidth: '760px',
      zOnCancel: () => {
        this.isDialogOpen.set(false);
        this.editingDocumentType.set(null);
        this.dialogRef = null;
      },
    });
    this.isDialogOpen.set(true);
  }

  /**
   * Edit document type
   */
  editDocumentType(documentType: DocumentType): void {
    this.editingDocumentType.set(documentType);
    this.documentTypeForm.patchValue({
      name: documentType.name || '',
      description: documentType.description || '',
      validationRuleRegex: documentType.validationRuleRegex || '',
      validationRuleAiPositive: documentType.validationRuleAiPositive || '',
      validationRuleAiNegative: documentType.validationRuleAiNegative || '',
      aiStructuredOutput: documentType.aiStructuredOutput || '',
      aiValidation: documentType.aiValidation ?? true,
      deprecated: documentType.deprecated ?? false,
      autoGeneration: documentType.autoGeneration ?? false,
      hasExpirationDate: documentType.hasExpirationDate || false,
      expiringThresholdDays: documentType.expiringThresholdDays ?? null,
      isStayPermit: documentType.isStayPermit || false,
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
      zCustomClasses:
        'border-2 border-primary/30 sm:max-w-[760px] max-h-[calc(100vh-2rem)] overflow-hidden',
      zWidth: '760px',
      zOnCancel: () => {
        this.isDialogOpen.set(false);
        this.editingDocumentType.set(null);
        this.dialogRef = null;
      },
    });
    this.isDialogOpen.set(true);
  }

  /**
   * Save document type
   */
  saveDocumentType(): void {
    if (this.documentTypeForm.invalid) return;

    this.isSaving.set(true);
    const formValue = this.documentTypeForm.getRawValue();
    const documentTypeData: DocumentType = {
      id: this.editingDocumentType()?.id ?? 0,
      name: formValue.name!,
      description: formValue.description || '',
      validationRuleRegex: formValue.validationRuleRegex || '',
      validationRuleAiPositive: formValue.validationRuleAiPositive || '',
      validationRuleAiNegative: formValue.validationRuleAiNegative || '',
      aiStructuredOutput: formValue.aiStructuredOutput || '',
      aiValidation: formValue.aiValidation ?? true,
      deprecated: formValue.deprecated || false,
      autoGeneration: formValue.autoGeneration || false,
      hasExpirationDate: formValue.hasExpirationDate || false,
      expiringThresholdDays: formValue.expiringThresholdDays ?? null,
      isStayPermit: formValue.isStayPermit || false,
      hasDocNumber: formValue.hasDocNumber || false,
      hasFile: formValue.hasFile || false,
      hasDetails: formValue.hasDetails || false,
      isInRequiredDocuments: formValue.isInRequiredDocuments || false,
    };

    if (this.editingDocumentType()) {
      this.updateDocumentType(this.editingDocumentType()!.id!, documentTypeData, false);
      return;
    }

    const request = this.documentTypesApi.documentTypesCreate(documentTypeData);

    request
      .pipe(
        catchError(() => {
          this.toast.error('Failed to save document type');
          return EMPTY;
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe(() => {
        this.toast.success('Document type created successfully');
        this.closeForm();
        this.reload();
      });
  }

  /**
   * Update document type
   */
  private updateDocumentType(
    documentTypeId: number,
    payload: DocumentType,
    deprecateRelatedProducts: boolean,
  ): void {
    let params = new HttpParams();
    if (deprecateRelatedProducts) {
      params = params.set('deprecate_related_products', 'true');
    }

    this.http
      .put<DocumentType>(`/api/document-types/${documentTypeId}/`, payload, { params })
      .pipe(
        catchError((error) => {
          if (
            error?.status === 409 &&
            error?.error?.code === 'deprecated_products_confirmation_required'
          ) {
            const relatedProducts = Array.isArray(error?.error?.details?.relatedProducts)
              ? error.error.details.relatedProducts
              : Array.isArray(error?.error?.relatedProducts)
                ? error.error.relatedProducts
                : [];
            const relatedNames = relatedProducts
              .map((product: any) => `${product.code} - ${product.name}`)
              .join('\n• ');

            this.pendingDeprecationPayload.set(payload);
            this.deprecationConfirmMessage.set(
              relatedProducts.length
                ? `Deprecating this document type will also deprecate these products:\n\n• ${relatedNames}\n\nContinue?`
                : 'Deprecating this document type will also deprecate related products. Continue?',
            );
            this.showDeprecationConfirm.set(true);
            this.isSaving.set(false);
            return EMPTY;
          }

          this.toast.error('Failed to save document type');
          this.isSaving.set(false);
          return EMPTY;
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe(() => {
        this.toast.success('Document type updated successfully');
        this.showDeprecationConfirm.set(false);
        this.pendingDeprecationPayload.set(null);
        this.closeForm();
        this.reload();
      });
  }

  /**
   * Confirm deprecation cascade
   */
  confirmDeprecationCascade(): void {
    const payload = this.pendingDeprecationPayload();
    const editingId = this.editingDocumentType()?.id;
    if (!payload || !editingId) {
      this.showDeprecationConfirm.set(false);
      return;
    }
    this.isSaving.set(true);
    this.updateDocumentType(editingId, payload, true);
  }

  /**
   * Cancel deprecation cascade
   */
  cancelDeprecationCascade(): void {
    this.showDeprecationConfirm.set(false);
    this.pendingDeprecationPayload.set(null);
  }

  /**
   * Delete document type
   */
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
        const payload = unwrapApiRecord(result) as {
          canDelete?: boolean;
          message?: string | null;
          warning?: string | null;
        } | null;

        if (!payload?.canDelete) {
          this.toast.error(payload?.message || 'This document type cannot be deleted');
          return;
        }

        this.confirmDeleteMessage.set(
          payload?.warning ||
            `Are you sure you want to delete "${documentType.name}"? This action cannot be undone.`,
        );
        this.editingDocumentType.set(documentType);
        this.showConfirmDelete.set(true);
      });
  }

  /**
   * Confirm delete
   */
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
        this.reload();
      });
  }

  /**
   * Close form dialog
   */
  closeForm(): void {
    if (this.dialogRef) {
      this.dialogRef.close();
      this.dialogRef = null;
    }
    this.isDialogOpen.set(false);
    this.showDeprecationConfirm.set(false);
    this.pendingDeprecationPayload.set(null);
    this.editingDocumentType.set(null);
  }

  /**
   * Bind stay permit rule
   */
  private bindStayPermitRule(): void {
    const isStayPermitControl = this.documentTypeForm.get('isStayPermit');
    if (!isStayPermitControl) {
      return;
    }

    this.syncStayPermitExpirationState(Boolean(isStayPermitControl.value));
    isStayPermitControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((isStayPermit) => {
        this.syncStayPermitExpirationState(Boolean(isStayPermit));
      });
  }

  /**
   * Bind expiration threshold rule
   */
  private bindExpirationThresholdRule(): void {
    const hasExpirationDateControl = this.documentTypeForm.get('hasExpirationDate');
    if (!hasExpirationDateControl) {
      return;
    }

    this.syncExpirationThresholdState(Boolean(hasExpirationDateControl.value));
    hasExpirationDateControl.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((hasExpirationDate) => {
        this.syncExpirationThresholdState(Boolean(hasExpirationDate));
      });
  }

  /**
   * Sync expiration threshold state
   */
  private syncExpirationThresholdState(hasExpirationDate: boolean): void {
    const expiringThresholdControl = this.documentTypeForm.get('expiringThresholdDays');
    if (!expiringThresholdControl) {
      return;
    }

    if (hasExpirationDate) {
      expiringThresholdControl.enable({ emitEvent: false });
      return;
    }

    expiringThresholdControl.setValue(null, { emitEvent: false });
    expiringThresholdControl.disable({ emitEvent: false });
  }

  /**
   * Sync stay permit expiration state
   */
  private syncStayPermitExpirationState(isStayPermit: boolean): void {
    const hasExpirationDateControl = this.documentTypeForm.get('hasExpirationDate');
    if (!hasExpirationDateControl) {
      return;
    }

    if (isStayPermit) {
      hasExpirationDateControl.setValue(true, { emitEvent: false });
      hasExpirationDateControl.disable({ emitEvent: false });
      this.syncExpirationThresholdState(true);
      return;
    }

    hasExpirationDateControl.enable({ emitEvent: false });
    this.syncExpirationThresholdState(Boolean(hasExpirationDateControl.value));
  }
}
