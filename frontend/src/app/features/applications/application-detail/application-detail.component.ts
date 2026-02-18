import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { CommonModule, formatDate, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  HostListener,
  inject,
  PLATFORM_ID,
  LOCALE_ID,
  signal,
  untracked,
  type OnInit,
} from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { DocumentTypesService } from '@/core/api/api/document-types.service';
import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
  type ApplicationWorkflow,
  type DocumentAction,
  type OcrStatusResponse,
} from '@/core/services/applications.service';
import { AuthService } from '@/core/services/auth.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ConfigService } from '@/core/services/config.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { DocumentPreviewComponent } from '@/shared/components/document-preview';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { downloadBlob } from '@/shared/utils/file-download';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

interface TimelineWorkflowItem {
  workflow: ApplicationWorkflow;
  gapDaysFromPrevious: number | null;
}

@Component({
  selector: 'app-application-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    FormsModule,
    DragDropModule,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ZardComboboxComponent,
    ZardDateInputComponent,
    DocumentPreviewComponent,
    FileUploadComponent,
    ZardIconComponent,
    ZardInputDirective,
    ZardPopoverComponent,
    ZardPopoverDirective,
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    AppDatePipe,
    ...ZardTooltipImports,
  ],
  templateUrl: './application-detail.component.html',
  styleUrls: ['./application-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private applicationsService = inject(ApplicationsService);
  private documentsService = inject(DocumentsService);
  private documentTypesService = inject(DocumentTypesService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private fb = inject(FormBuilder);
  private destroyRef = inject(DestroyRef);
  private platformId = inject(PLATFORM_ID);
  private locale = inject(LOCALE_ID);
  private configService = inject(ConfigService);
  private readonly isBrowser = isPlatformBrowser(this.platformId);
  private http = inject(HttpClient);

  readonly application = signal<ApplicationDetail | null>(null);
  readonly isLoading = signal(true);
  readonly isUploadOpen = signal(false);
  readonly selectedDocument = signal<ApplicationDocument | null>(null);
  readonly selectedFile = signal<File | null>(null);
  readonly uploadPreviewUrl = signal<string | null>(null);
  readonly uploadPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPreviewUrl = signal<string | null>(null);
  readonly existingPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly uploadProgress = signal<number | null>(null);
  readonly isSaving = signal(false);
  readonly inlinePreviewUrl = computed(() => {
    const uploadUrl = this.uploadPreviewUrl();
    if (uploadUrl) {
      return uploadUrl;
    }
    return this.existingPreviewUrl();
  });
  readonly inlinePreviewType = computed(() => {
    if (this.uploadPreviewUrl()) {
      return this.uploadPreviewType();
    }
    return this.existingPreviewType();
  });

  readonly ocrPolling = signal(false);
  readonly ocrStatus = signal<string | null>(null);
  readonly ocrPreviewImage = signal<string | null>(null);
  readonly ocrReviewOpen = signal(false);
  readonly ocrReviewData = signal<OcrStatusResponse | null>(null);
  readonly ocrMetadata = signal<Record<string, unknown> | null>(null);
  readonly isAddDocumentDialogOpen = signal(false);
  readonly actionLoading = signal<string | null>(null);
  readonly workflowAction = signal<string | null>(null);
  readonly originSearchQuery = signal<string | null>(null);
  readonly isSuperuser = this.authService.isSuperuser;
  readonly isSavingMeta = signal(false);
  readonly editableNotes = signal('');
  readonly selectedNewDocType = signal<string | null>(null);
  readonly docTypeOptions = signal<ZardComboboxOption[]>([]);
  readonly filteredDocTypeOptions = computed(() => {
    const options = this.docTypeOptions();
    const app = this.application();
    if (!app) {
      return options;
    }
    const existingDocTypeIds = new Set(
      (app.documents ?? [])
        .map((doc) => doc.docType?.id)
        .filter((id): id is number => typeof id === 'number')
        .map((id) => String(id)),
    );
    return options.filter((opt) => !existingDocTypeIds.has(opt.value));
  });

  // Computed signals for stable object references in templates
  readonly docDateAsDate = computed(() => {
    const value = this.application()?.docDate;
    return value ? new Date(value) : null;
  });

  readonly dueDateAsDate = computed(() => {
    const value = this.application()?.dueDate;
    return value ? new Date(value) : null;
  });
  readonly hasWorkflowTasks = computed(() => {
    const app = this.application();
    if (!app) {
      return false;
    }
    return this.sortedWorkflows().length > 0 || !!app.nextTask || !!app.hasNextTask;
  });
  readonly isDueDateLocked = computed(() => this.hasWorkflowTasks());
  readonly dueDateLockedTooltip =
    'Please update Due date in Task Timeline to change this deadline.';
  readonly dueDateContextLabel = computed(() => {
    const app = this.application();
    if (!app) {
      return 'Next Deadline: —';
    }

    const taskName =
      app.nextTask?.name?.trim() ||
      app.workflows?.find((workflow) => workflow.isCurrentStep)?.task?.name?.trim() ||
      app.workflows?.find((workflow) => workflow.dueDate === app.dueDate)?.task?.name?.trim() ||
      '';

    return taskName ? `Next Deadline (${taskName})` : 'Next Deadline: —';
  });
  readonly customerNotificationOptions = computed<ZardComboboxOption[]>(() => {
    const customer = this.application()?.customer;
    const options: ZardComboboxOption[] = [];
    if (customer?.whatsapp) {
      options.push({ value: 'whatsapp', label: 'WhatsApp' });
    }
    if (customer?.email) {
      options.push({ value: 'email', label: 'Email' });
    }
    return options;
  });
  readonly canNotifyCustomer = computed(() => this.customerNotificationOptions().length > 0);

  // PDF Merge and Selection
  readonly localUploadedDocuments = signal<ApplicationDocument[]>([]);
  readonly selectedDocumentIds = signal<Set<number>>(new Set());
  readonly areAllUploadedDocumentsSelected = computed(() => {
    const documents = this.localUploadedDocuments();
    if (documents.length === 0) {
      return false;
    }

    const selectedIds = this.selectedDocumentIds();
    return documents.every((document) => selectedIds.has(document.id));
  });
  readonly isUploadedDocumentSelectionPartial = computed(() => {
    const documents = this.localUploadedDocuments();
    if (documents.length === 0) {
      return false;
    }

    const selectedIds = this.selectedDocumentIds();
    const selectedCount = documents.reduce(
      (count, document) => count + (selectedIds.has(document.id) ? 1 : 0),
      0,
    );

    return selectedCount > 0 && selectedCount < documents.length;
  });
  readonly isMerging = signal(false);
  private readonly workflowTimezone = 'Asia/Singapore';

  private pollTimer: number | null = null;

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const application = this.application();
    if (!application) return;

    // B or Left Arrow --> Back
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.goBack();
    }
  }

  readonly uploadedDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => doc.completed),
  );
  readonly requiredDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => doc.required && !doc.completed),
  );
  readonly optionalDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => !doc.required && !doc.completed),
  );
  readonly documentCollectionStatus = computed<{
    label:
      | 'Document Collection Pending'
      | 'Document Collection Incomplete'
      | 'Document Collection Complete';
    type: 'default' | 'secondary' | 'warning' | 'success' | 'destructive';
  }>(() => {
    const documents = this.application()?.documents ?? [];
    const uploadedCount = documents.filter((doc) => doc.completed).length;
    const requiredDocuments = documents.filter((doc) => doc.required);
    const uploadedRequiredCount = requiredDocuments.filter((doc) => doc.completed).length;

    if (uploadedCount === 0) {
      return { label: 'Document Collection Pending', type: 'warning' };
    }

    if (uploadedRequiredCount === requiredDocuments.length) {
      return { label: 'Document Collection Complete', type: 'success' };
    }

    return { label: 'Document Collection Incomplete', type: 'secondary' };
  });

  readonly sortedWorkflows = computed(() => {
    const workflows = this.application()?.workflows ?? [];
    return [...workflows].sort((a, b) => (a.task?.step ?? 0) - (b.task?.step ?? 0));
  });

  readonly timelineItems = computed<TimelineWorkflowItem[]>(() => {
    const workflows = this.sortedWorkflows();
    return workflows.map((workflow, index) => ({
      workflow,
      gapDaysFromPrevious: index > 0 ? this.calculateGapDays(workflows[index - 1], workflow) : null,
    }));
  });

  readonly canReopen = computed(() => !!this.application()?.isApplicationCompleted);

  readonly uploadForm = this.fb.group({
    docNumber: [''],
    expirationDate: [null as Date | null],
    details: [''],
  });

  constructor() {
    effect(() => {
      const docs = this.uploadedDocuments();
      untracked(() => {
        const current = this.localUploadedDocuments();

        // Sync local list only if the SET of documents changed (new upload, deletion, etc.)
        // but preserve the local order if it's just a reorder.
        const currentIds = new Set(current.map((d) => d.id));
        const docsIds = new Set(docs.map((d) => d.id));

        const needsSync =
          currentIds.size !== docsIds.size || [...docsIds].some((id) => !currentIds.has(id));

        if (needsSync) {
          this.localUploadedDocuments.set([...docs]);
        }
      });
    });
  }

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    const st = this.isBrowser ? (window as any).history.state || {} : {};
    this.originSearchQuery.set(st.searchQuery ?? null);
    if (!id) {
      this.toast.error('Invalid application ID');
      this.isLoading.set(false);
      return;
    }
    this.loadApplication(id);
    this.loadDocumentTypes();

    this.destroyRef.onDestroy(() => {
      if (this.pollTimer) {
        if (this.isBrowser) {
          window.clearTimeout(this.pollTimer);
        }
      }
      this.clearUploadPreview();
      this.clearExistingPreview();
    });
  }

  openUpload(document: ApplicationDocument): void {
    this.selectedDocument.set(document);
    this.selectedFile.set(null);
    this.clearUploadPreview();
    this.loadExistingDocumentPreview(document);
    this.uploadProgress.set(null);
    this.ocrPreviewImage.set(null);
    this.ocrReviewOpen.set(false);
    this.ocrReviewData.set(null);
    this.ocrMetadata.set(document.metadata ?? null);
    this.uploadForm.reset({
      docNumber: document.docNumber ?? '',
      expirationDate: this.parseApiDate(document.expirationDate),
      details: document.details ?? '',
    });
    this.isUploadOpen.set(true);
  }

  closeUpload(): void {
    this.isUploadOpen.set(false);
    this.selectedDocument.set(null);
    this.selectedFile.set(null);
    this.clearUploadPreview();
    this.clearExistingPreview();
    this.uploadProgress.set(null);
    this.ocrPolling.set(false);
    this.ocrStatus.set(null);
  }

  onFileSelected(file: File): void {
    this.selectedFile.set(file);
    this.setUploadPreviewFromFile(file);
  }

  onFileCleared(): void {
    this.selectedFile.set(null);
    this.clearUploadPreview();
    const document = this.selectedDocument();
    if (document) {
      this.loadExistingDocumentPreview(document);
    }
  }

  onSaveDocument(): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    this.isSaving.set(true);
    this.uploadProgress.set(0);

    const formValue = this.uploadForm.getRawValue();

    this.applicationsService
      .updateDocument(
        document.id,
        {
          docNumber: formValue.docNumber || null,
          expirationDate: this.toApiDate(formValue.expirationDate),
          details: formValue.details || null,
          metadata: this.ocrMetadata(),
        },
        this.selectedFile(),
      )
      .subscribe({
        next: (state) => {
          if (state.state === 'progress') {
            this.uploadProgress.set(state.progress);
          } else {
            this.uploadProgress.set(state.progress);
            this.replaceDocument(state.document);
            this.toast.success('Document updated');
            this.isSaving.set(false);
            this.closeUpload();
          }
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to update document');
          this.isSaving.set(false);
        },
      });
  }

  runOcr(): void {
    const document = this.selectedDocument();
    const file = this.selectedFile();
    if (!document || !document.docType?.hasOcrCheck) {
      return;
    }
    if (!file) {
      this.toast.error('Select a file before running OCR');
      return;
    }

    this.ocrPolling.set(true);
    this.ocrStatus.set('Queued');

    this.applicationsService.startOcrCheck(file, document.docType.name).subscribe({
      next: (response) => {
        const statusUrl =
          ('statusUrl' in response && response.statusUrl) ||
          (response as { status_url?: string }).status_url;
        if (statusUrl) {
          this.pollOcrStatus(statusUrl, 0);
        } else {
          this.handleOcrResult(response as OcrStatusResponse);
        }
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to start OCR');
        this.ocrPolling.set(false);
      },
    });
  }

  applyOcrData(): void {
    const data = this.ocrReviewData();
    if (!data?.mrzData) {
      this.ocrReviewOpen.set(false);
      return;
    }

    this.uploadForm.patchValue({
      docNumber: data.mrzData.number ?? '',
      expirationDate: this.parseApiDate(data.mrzData.expirationDateYyyyMmDd),
    });
    this.ocrMetadata.set(data.mrzData ?? {});
    this.ocrReviewOpen.set(false);
  }

  dismissOcrReview(): void {
    this.ocrReviewOpen.set(false);
  }

  executeAction(action: DocumentAction): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    this.actionLoading.set(action.name);

    this.applicationsService.executeDocumentAction(document.id, action.name).subscribe({
      next: (response) => {
        if (response.success) {
          this.toast.success(response.message ?? 'Action completed successfully');
          if (response.document) {
            this.replaceDocument(response.document);
            // Update selected document with new data
            this.selectedDocument.set(response.document);
            // Update file name in upload component if file was uploaded
            if (response.document.fileLink) {
              this.selectedFile.set(null);
            }
          }
        } else {
          this.toast.error('Action failed');
        }
        this.actionLoading.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to execute action');
        this.actionLoading.set(null);
      },
    });
  }

  viewDocument(doc: ApplicationDocument): void {
    this.documentsService.downloadDocumentFile(doc.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const popup = window.open(url, '_blank');
        if (!popup) {
          this.toast.error('Popup blocked. Please allow popups for this site.');
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      },
      error: (error) => {
        if (doc.fileLink) {
          window.open(doc.fileLink, '_blank');
          return;
        }
        this.toast.error(extractServerErrorMessage(error) || 'Failed to open document');
      },
    });
  }

  toggleDocumentSelection(id: number): void {
    const selected = new Set(this.selectedDocumentIds());
    if (selected.has(id)) {
      selected.delete(id);
    } else {
      selected.add(id);
    }
    this.selectedDocumentIds.set(selected);
  }

  selectAllDocuments(): void {
    const allIds = this.localUploadedDocuments().map((d) => d.id);
    this.selectedDocumentIds.set(new Set(allIds));
  }

  deselectAllDocuments(): void {
    this.selectedDocumentIds.set(new Set());
  }

  toggleAllUploadedDocumentsSelection(): void {
    if (this.areAllUploadedDocumentsSelected()) {
      this.deselectAllDocuments();
      return;
    }
    this.selectAllDocuments();
  }

  onDocumentDrop(event: CdkDragDrop<ApplicationDocument[]>): void {
    const docs = [...this.localUploadedDocuments()];
    moveItemInArray(docs, event.previousIndex, event.currentIndex);
    this.localUploadedDocuments.set(docs);
  }

  mergeAndDownloadSelected(): void {
    const selectedIds = this.selectedDocumentIds();
    if (selectedIds.size < 1) {
      this.toast.error('Select at least one document to merge');
      return;
    }

    // Preserve the order from the local reorderable list
    const orderedIds = this.localUploadedDocuments()
      .filter((d) => selectedIds.has(d.id))
      .map((d) => d.id);

    this.isMerging.set(true);
    this.documentsService.mergePdf(orderedIds).subscribe({
      next: (blob: Blob) => {
        const app = this.application();
        const customerName = app?.customer.fullName || 'documents';
        const filename = `merged_${customerName.toLowerCase().replace(/\s+/g, '_')}_${app?.id ?? 'export'}.pdf`;
        downloadBlob(blob, filename);
        this.isMerging.set(false);
        this.toast.success('PDF merged and downloaded');
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to merge documents');
        this.isMerging.set(false);
      },
    });
  }

  advanceWorkflow(): void {
    const app = this.application();
    if (!app) return;

    this.workflowAction.set('advance');
    this.applicationsService.advanceWorkflow(app.id).subscribe({
      next: () => {
        this.toast.success('Workflow advanced');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to advance workflow');
        this.workflowAction.set(null);
      },
    });
  }

  deleteApplication(): void {
    const app = this.application();
    if (!app || !this.isSuperuser()) return;

    if (confirm(`Are you sure you want to delete application #${app.id}?`)) {
      this.workflowAction.set('delete');
      this.applicationsService.deleteApplication(app.id).subscribe({
        next: () => {
          this.toast.success('Application deleted');
          this.goBack();
          this.workflowAction.set(null);
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to delete application');
          this.workflowAction.set(null);
        },
      });
    }
  }

  updateWorkflowStatus(workflowId: number, status: string | null): void {
    const app = this.application();
    if (!app || !status) return;
    const workflow = this.sortedWorkflows().find((entry) => entry.id === workflowId);
    if (workflow && this.isWorkflowStatusChangeBlocked(workflow, status)) {
      this.toast.error(this.getWorkflowStatusBlockedMessage(workflow));
      return;
    }

    this.workflowAction.set(`status-${workflowId}`);
    this.applicationsService.updateWorkflowStatus(app.id, workflowId, status).subscribe({
      next: () => {
        this.toast.success('Workflow status updated');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update workflow status');
        this.workflowAction.set(null);
      },
    });
  }

  updateWorkflowDueDate(workflow: ApplicationWorkflow, value: Date | null): void {
    const app = this.application();
    if (!app || !value || !this.isWorkflowDueDateEditable(workflow)) {
      return;
    }

    const dueDate = this.formatDateForApi(value);
    this.workflowAction.set(`due-${workflow.id}`);
    this.applicationsService.updateWorkflowDueDate(app.id, workflow.id, dueDate).subscribe({
      next: () => {
        this.toast.success('Task due date updated');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update task due date');
        this.workflowAction.set(null);
      },
    });
  }

  rollbackWorkflow(workflow: ApplicationWorkflow): void {
    const app = this.application();
    if (!app || !this.canRollbackWorkflow(workflow)) {
      return;
    }

    if (
      !confirm(
        `Rollback Step ${workflow.task.step}? This removes the current task and reopens the previous task.`,
      )
    ) {
      return;
    }

    this.workflowAction.set(`rollback-${workflow.id}`);
    this.applicationsService.rollbackWorkflow(app.id, workflow.id).subscribe({
      next: () => {
        this.toast.success('Current task rolled back');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to rollback current task');
        this.workflowAction.set(null);
      },
    });
  }

  reopenApplication(): void {
    const app = this.application();
    if (!app) return;

    this.workflowAction.set('reopen');
    this.applicationsService.reopenApplication(app.id).subscribe({
      next: () => {
        this.toast.success('Application re-opened');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to re-open application');
        this.workflowAction.set(null);
      },
    });
  }

  canForceClose(): boolean {
    const app = this.application();
    return !!(
      app &&
      (app as any).canForceClose &&
      app.status !== 'completed' &&
      app.status !== 'rejected' &&
      !app.isDocumentCollectionCompleted
    );
  }

  confirmForceClose(): void {
    const app = this.application();
    if (!app) {
      return;
    }
    if (!this.canForceClose()) {
      this.toast.error('You cannot force close this application');
      return;
    }

    if (confirm(`Force close application #${app.id}? This will mark it as completed.`)) {
      this.workflowAction.set('force-close');
      this.applicationsService.forceClose(app.id, app as any).subscribe({
        next: () => {
          this.toast.success('Application force closed');
          this.loadApplication(app.id);
          this.workflowAction.set(null);
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to force close application');
          this.workflowAction.set(null);
        },
      });
    }
  }

  canCreateInvoice(): boolean {
    const app = this.application();
    return !!(app && this.isReadyForInvoice(app));
  }

  createInvoice(): void {
    const app = this.application();
    if (!app || !this.canCreateInvoice()) return;
    // Navigate to invoice creation page with applicationId pre-filled
    this.router.navigate(['/invoices', 'new'], {
      queryParams: { applicationId: app.id },
      state: {
        from: 'applications',
        focusId: app.id,
        searchQuery: this.originSearchQuery(),
      },
    });
  }

  getApplicationStatusVariant(
    status: string,
  ): 'default' | 'secondary' | 'warning' | 'success' | 'destructive' {
    switch (status) {
      case 'completed':
        return 'success';
      case 'rejected':
        return 'destructive';
      case 'processing':
        return 'warning';
      case 'pending':
      default:
        return 'secondary';
    }
  }

  getWorkflowStatusVariant(
    status: string,
    isOverdue?: boolean,
  ): 'default' | 'secondary' | 'warning' | 'success' | 'destructive' {
    if (isOverdue && status !== 'completed' && status !== 'rejected') {
      return 'destructive';
    }
    switch (status) {
      case 'completed':
        return 'success';
      case 'processing':
        return 'warning';
      case 'rejected':
        return 'destructive';
      case 'pending':
      default:
        return 'secondary';
    }
  }

  getWorkflowDotClass(status: string): string {
    switch (status) {
      case 'completed':
        return 'timeline-dot-completed';
      case 'rejected':
        return 'timeline-dot-rejected';
      case 'processing':
        return 'timeline-dot-processing';
      case 'pending':
      default:
        return 'timeline-dot-pending';
    }
  }

  isWorkflowEditable(workflow: ApplicationWorkflow): boolean {
    if (!this.application()) {
      return false;
    }
    if (workflow.status === 'completed' || workflow.status === 'rejected') {
      return false;
    }
    const currentWorkflow = this.sortedWorkflows().at(-1);
    return !!currentWorkflow && currentWorkflow.id === workflow.id;
  }

  isWorkflowDueDateEditable(workflow: ApplicationWorkflow): boolean {
    return this.isWorkflowEditable(workflow);
  }

  canRollbackWorkflow(workflow: ApplicationWorkflow): boolean {
    const app = this.application();
    if (!app || app.status === 'completed' || app.status === 'rejected') {
      return false;
    }
    if (workflow.task.step <= 1) {
      return false;
    }
    const currentWorkflow = this.sortedWorkflows().at(-1);
    return !!currentWorkflow && currentWorkflow.id === workflow.id;
  }

  getWorkflowDueDateAsDate(workflow: ApplicationWorkflow): Date | null {
    return workflow.dueDate ? new Date(workflow.dueDate) : null;
  }

  getWorkflowStatusOptions(workflow: ApplicationWorkflow): ZardComboboxOption[] {
    const options: ZardComboboxOption[] = [
      { value: 'pending', label: 'Pending' },
      { value: 'processing', label: 'Processing' },
      { value: 'completed', label: 'Completed' },
      { value: 'rejected', label: 'Rejected' },
    ];
    return options.map((option) => ({
      ...option,
      disabled:
        option.value !== workflow.status &&
        this.isWorkflowStatusChangeBlocked(workflow, option.value),
    }));
  }

  getWorkflowStatusGuardMessage(workflow: ApplicationWorkflow): string | null {
    const isBlocked =
      this.isWorkflowStatusChangeBlocked(workflow, 'processing') ||
      this.isWorkflowStatusChangeBlocked(workflow, 'completed');
    if (!isBlocked) {
      return null;
    }
    const previousWorkflow = this.getPreviousWorkflow(workflow);
    if (!previousWorkflow?.dueDate) {
      return null;
    }
    const formattedDate = this.formatDateForDisplay(previousWorkflow.dueDate);
    return `Processing/Completed available on or after ${formattedDate} (GMT+8).`;
  }

  getTimelineGapLabel(days: number | null): string {
    if (days === null) {
      return '';
    }
    if (days <= 0) {
      return 'Started same day';
    }
    if (days === 1) {
      return 'Started after 1 day';
    }
    return `Started after ${days} days`;
  }

  /**
   * Navigate back to the previous view that opened this page.
   * Strategy:
   * 1. If navigation state provides a `from`/`returnUrl`, navigate there
   * 2. Else, if there is a browser history, use Location.back()
   * 3. Fallback to the customer view
   */
  goBack(): void {
    const nav = this.router.getCurrentNavigation();
    const st = (nav && nav.extras && (nav.extras.state as any)) || (history.state as any) || {};

    const focusState: Record<string, unknown> = {
      focusTable: true,
    };
    if (st.focusId) {
      focusState['focusId'] = st.focusId;
    }
    if (st.searchQuery) {
      focusState['searchQuery'] = st.searchQuery;
    }

    if (st.from === 'applications') {
      this.router.navigate(['/applications'], { state: focusState });
      return;
    }
    if (typeof st.returnUrl === 'string' && st.returnUrl.startsWith('/')) {
      this.router.navigateByUrl(st.returnUrl, { state: { searchQuery: st.searchQuery ?? null } });
      return;
    }
    if (st.from === 'customer-detail' && st.customerId) {
      this.router.navigate(['/customers', st.customerId], {
        state: { searchQuery: st.searchQuery ?? null },
      });
      return;
    }
    if (st.from === 'customers') {
      this.router.navigate(['/customers'], { state: focusState });
      return;
    }
    if (st.from === 'dashboard') {
      this.router.navigate(['/dashboard']);
      return;
    }

    // Edge case: newly created applications should return to the list and focus the first row.
    this.router.navigate(['/applications'], { state: { focusTable: true } });
  }

  onInlineDateChange(field: 'docDate' | 'dueDate', value: Date | null): void {
    if (!value) return;
    if (field === 'dueDate' && this.isDueDateLocked()) {
      this.toast.error(this.dueDateLockedTooltip);
      return;
    }
    const iso = this.formatDateForApi(value);
    this.updateApplicationPartial(
      { [field]: iso } as any,
      `${field === 'docDate' ? 'Document' : 'Due'} date updated`,
    );
  }

  onCalendarToggle(enabled: boolean): void {
    this.updateApplicationPartial({ addDeadlinesToCalendar: enabled }, 'Calendar sync updated');
  }

  onNotifyCustomerToggle(enabled: boolean): void {
    if (!enabled) {
      this.updateApplicationPartial(
        { notifyCustomerToo: false, notifyCustomerChannel: null },
        'Customer notifications updated',
      );
      return;
    }

    const options = this.customerNotificationOptions();
    if (options.length === 0) {
      return;
    }

    const current = this.application()?.notifyCustomerChannel;
    const nextChannel = options.some((opt) => opt.value === current)
      ? current
      : (options[0]?.value as 'whatsapp' | 'email');

    this.updateApplicationPartial(
      { notifyCustomerToo: true, notifyCustomerChannel: nextChannel },
      'Customer notifications updated',
    );
  }

  onNotifyCustomerChannelChange(value: string | null): void {
    if (!value) {
      return;
    }
    this.updateApplicationPartial(
      { notifyCustomerToo: true, notifyCustomerChannel: value },
      'Customer notification channel updated',
    );
  }

  onNotesBlur(): void {
    const app = this.application();
    if (!app) return;
    const next = this.editableNotes().trim();
    if ((app.notes ?? '').trim() === next) return;
    this.updateApplicationPartial({ notes: next }, 'Notes updated');
  }

  addApplicationDocument(): void {
    const docTypeId = this.selectedNewDocType();
    const app = this.application();
    if (!docTypeId || !app) return;
    const payloadDocs = app.documents.map((d) => ({ id: d.docType.id, required: d.required }));
    if (!payloadDocs.some((d) => String(d.id) === String(docTypeId))) {
      payloadDocs.push({ id: Number(docTypeId), required: true });
    }
    this.updateApplicationPartial({ documentTypes: payloadDocs }, 'Document added');
    this.closeAddDocumentDialog();
  }

  openAddDocumentDialog(): void {
    if (this.filteredDocTypeOptions().length === 0) {
      this.toast.error('No additional document types available');
      return;
    }
    this.selectedNewDocType.set(null);
    this.isAddDocumentDialogOpen.set(true);
  }

  closeAddDocumentDialog(): void {
    this.isAddDocumentDialogOpen.set(false);
    this.selectedNewDocType.set(null);
  }

  removeApplicationDocument(doc: ApplicationDocument): void {
    const app = this.application();
    if (!app) return;
    const payloadDocs = app.documents
      .filter((d) => d.docType.id !== doc.docType.id)
      .map((d) => ({ id: d.docType.id, required: d.required }));
    this.updateApplicationPartial({ documentTypes: payloadDocs }, 'Document removed');
  }

  private updateApplicationPartial(payload: Record<string, unknown>, successMessage: string): void {
    const app = this.application();
    if (!app || this.isSavingMeta()) return;
    this.isSavingMeta.set(true);
    this.http.patch<any>(`/api/customer-applications/${app.id}/`, payload).subscribe({
      next: () => {
        this.toast.success(successMessage);
        this.loadApplication(app.id);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update application');
        this.isSavingMeta.set(false);
      },
    });
  }

  private loadDocumentTypes(): void {
    this.documentTypesService.documentTypesList().subscribe({
      next: (types) =>
        this.docTypeOptions.set((types ?? []).map((t) => ({ value: String(t.id), label: t.name }))),
      error: () => this.docTypeOptions.set([]),
    });
  }

  private loadApplication(id: number): void {
    this.isLoading.set(true);
    this.applicationsService.getApplication(id).subscribe({
      next: (data) => {
        const normalized = {
          ...data,
          notifyCustomer:
            data?.notifyCustomer ?? data?.notifyCustomerToo ?? data?.notify_customer_too ?? false,
          notifyCustomerChannel:
            data?.notifyCustomerChannel ?? data?.notify_customer_channel ?? null,
          readyForInvoice: data?.readyForInvoice ?? data?.ready_for_invoice ?? undefined,
        };
        this.application.set(normalized);
        this.editableNotes.set(normalized?.notes ?? '');
        this.isLoading.set(false);
        this.isSavingMeta.set(false);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load application');
        this.isLoading.set(false);
        this.isSavingMeta.set(false);
      },
    });
  }

  private isReadyForInvoice(app: ApplicationDetail): boolean {
    if (typeof app.readyForInvoice === 'boolean') {
      return app.readyForInvoice;
    }

    if (app.status === 'completed' || app.status === 'rejected') {
      return true;
    }

    const requiredDocuments = app.documents.filter((document) => document.required);
    const completedRequiredDocuments = requiredDocuments.filter((document) => document.completed);
    return requiredDocuments.length === completedRequiredDocuments.length;
  }

  private calculateGapDays(
    previous: ApplicationWorkflow,
    current: ApplicationWorkflow,
  ): number | null {
    const previousEnd = this.parseIsoDate(previous.completionDate);
    const currentStart = this.parseIsoDate(current.startDate);
    if (!previousEnd || !currentStart) {
      return null;
    }
    const msInDay = 24 * 60 * 60 * 1000;
    const diff = Math.round((currentStart.getTime() - previousEnd.getTime()) / msInDay);
    return Math.max(0, diff);
  }

  private getPreviousWorkflow(workflow: ApplicationWorkflow): ApplicationWorkflow | null {
    const workflows = this.sortedWorkflows();
    const index = workflows.findIndex((item) => item.id === workflow.id);
    if (index <= 0) {
      return null;
    }
    return workflows[index - 1] ?? null;
  }

  private isWorkflowStatusChangeBlocked(
    workflow: ApplicationWorkflow,
    nextStatus: string,
  ): boolean {
    if (nextStatus === 'rejected') {
      return false;
    }
    if (workflow.status !== 'pending') {
      return false;
    }
    if (nextStatus !== 'processing' && nextStatus !== 'completed') {
      return false;
    }

    const previousWorkflow = this.getPreviousWorkflow(workflow);
    const previousDueDate = this.parseIsoDate(previousWorkflow?.dueDate);
    if (!previousDueDate) {
      return false;
    }

    const today = this.getTodayInWorkflowTimezoneDate();
    return previousDueDate.getTime() > today.getTime();
  }

  private getWorkflowStatusBlockedMessage(workflow: ApplicationWorkflow): string {
    const previousWorkflow = this.getPreviousWorkflow(workflow);
    if (!previousWorkflow?.dueDate) {
      return 'Status can be updated to Rejected only until previous step due date is reached.';
    }
    const formattedDate = this.formatDateForDisplay(previousWorkflow.dueDate);
    return `You can set Processing/Completed only on or after ${formattedDate} (GMT+8).`;
  }

  private getTodayInWorkflowTimezoneDate(): Date {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: this.workflowTimezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date());
    const year = Number(parts.find((part) => part.type === 'year')?.value);
    const month = Number(parts.find((part) => part.type === 'month')?.value);
    const day = Number(parts.find((part) => part.type === 'day')?.value);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return new Date();
    }
    return new Date(Date.UTC(year, month - 1, day));
  }

  private parseIsoDate(value?: string | null): Date | null {
    if (!value) {
      return null;
    }
    const parts = value.split('-');
    if (parts.length !== 3) {
      return null;
    }
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    const day = Number(parts[2]);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return null;
    }
    return new Date(Date.UTC(year, month - 1, day));
  }

  private pollOcrStatus(statusUrl: string, attempt: number): void {
    const maxAttempts = 90;
    const intervalMs = 2000;

    if (attempt >= maxAttempts) {
      this.toast.error('OCR processing timed out');
      this.ocrPolling.set(false);
      return;
    }

    this.pollTimer = window.setTimeout(() => {
      this.applicationsService.getOcrStatus(statusUrl).subscribe({
        next: (status) => {
          if (status.status === 'completed') {
            this.handleOcrResult(status);
            return;
          }
          if (status.status === 'failed') {
            this.toast.error(status.error ?? 'OCR failed');
            this.ocrPolling.set(false);
            return;
          }
          if (typeof status.progress === 'number') {
            this.ocrStatus.set(`Processing ${status.progress}%`);
          } else {
            this.ocrStatus.set('Processing');
          }
          this.pollOcrStatus(statusUrl, attempt + 1);
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to check OCR status');
          this.ocrPolling.set(false);
        },
      });
    }, intervalMs);
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.ocrPolling.set(false);
    this.ocrStatus.set('Completed');
    this.ocrReviewData.set(status);
    const previewUrl = status.previewUrl ?? (status as { preview_url?: string }).preview_url;
    if (previewUrl) {
      this.ocrPreviewImage.set(previewUrl);
    } else if (status.b64ResizedImage) {
      this.ocrPreviewImage.set(`data:image/jpeg;base64,${status.b64ResizedImage}`);
    }
    this.ocrReviewOpen.set(true);
  }

  private replaceDocument(updated: ApplicationDocument): void {
    const application = this.application();
    if (!application) {
      return;
    }
    const documents = application.documents.map((doc) =>
      doc.id === updated.id ? { ...doc, ...updated } : doc,
    );
    const requiredDocs = documents.filter((doc) => doc.required);
    const allRequiredCompleted = requiredDocs.length
      ? requiredDocs.every((doc) => doc.completed)
      : Boolean(application.isDocumentCollectionCompleted);
    this.application.set({
      ...application,
      documents,
      isDocumentCollectionCompleted: allRequiredCompleted,
    });
  }

  private setUploadPreviewFromFile(file: File): void {
    this.clearUploadPreview();
    const type = file.type.toLowerCase();
    if (type.startsWith('image/')) {
      this.uploadPreviewType.set('image');
    } else if (type === 'application/pdf' || file.name.toLowerCase().endsWith('.pdf')) {
      this.uploadPreviewType.set('pdf');
    } else if (/\.(png|jpe?g)$/i.test(file.name)) {
      this.uploadPreviewType.set('image');
    } else {
      this.uploadPreviewType.set('unknown');
      this.uploadPreviewUrl.set(null);
      return;
    }
    this.uploadPreviewUrl.set(URL.createObjectURL(file));
  }

  private loadExistingDocumentPreview(document: ApplicationDocument): void {
    this.clearExistingPreview();
    if (!document.fileLink) {
      return;
    }

    this.documentsService.downloadDocumentFile(document.id).subscribe({
      next: (blob) => {
        // Ignore stale async result if user switched document while request was in flight.
        if (this.selectedDocument()?.id !== document.id) {
          return;
        }

        const url = URL.createObjectURL(blob);
        const mime = (blob.type || '').toLowerCase();
        const urlType = this.getPreviewTypeFromUrl(document.fileLink);

        let type: 'image' | 'pdf' | 'unknown' = 'unknown';
        if (mime.startsWith('image/')) {
          type = 'image';
        } else if (mime === 'application/pdf') {
          type = 'pdf';
        } else {
          type = urlType;
        }

        if (type === 'unknown') {
          URL.revokeObjectURL(url);
          return;
        }

        this.existingPreviewType.set(type);
        this.existingPreviewUrl.set(url);
      },
      error: () => {
        this.clearExistingPreview();
      },
    });
  }

  private getPreviewTypeFromUrl(url?: string | null): 'image' | 'pdf' | 'unknown' {
    if (!url) {
      return 'unknown';
    }
    const lower = url.toLowerCase();
    if (lower.endsWith('.pdf')) {
      return 'pdf';
    }
    if (/\.(png|jpe?g)$/i.test(lower)) {
      return 'image';
    }
    return 'unknown';
  }

  private clearUploadPreview(): void {
    const url = this.uploadPreviewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        // ignore
      }
    }
    this.uploadPreviewUrl.set(null);
    this.uploadPreviewType.set('unknown');
  }

  private clearExistingPreview(): void {
    const url = this.existingPreviewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        // ignore
      }
    }
    this.existingPreviewUrl.set(null);
    this.existingPreviewType.set('unknown');
  }

  private formatDateForApi(value: Date): string {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, '0');
    const day = String(value.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private toApiDate(value: unknown): string | null {
    const parsed = this.parseApiDate(value);
    if (!parsed) {
      return null;
    }
    return this.formatDateForApi(parsed);
  }

  private parseApiDate(value: unknown): Date | null {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    if (typeof value !== 'string') {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const match = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (!match) {
      const parsed = new Date(trimmed);
      if (Number.isNaN(parsed.getTime())) {
        return null;
      }
      return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }

  private formatDateForDisplay(value: string): string {
    const parsed = this.parseApiDate(value);
    if (!parsed) {
      return value;
    }
    return formatDate(
      parsed,
      this.normalizeDateFormat(this.configService.settings.dateFormat),
      this.locale,
    );
  }

  private normalizeDateFormat(format: string | null | undefined): string {
    const normalized = (format ?? '').trim();
    if (['dd-MM-yyyy', 'yyyy-MM-dd', 'dd/MM/yyyy', 'MM/dd/yyyy'].includes(normalized)) {
      return normalized;
    }
    return 'dd-MM-yyyy';
  }
}
