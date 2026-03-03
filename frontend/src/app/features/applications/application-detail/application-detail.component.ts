import { CdkDragDrop, DragDropModule, moveItemInArray } from '@angular/cdk/drag-drop';
import { CommonModule, formatDate, isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpEventType } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  effect,
  HostListener,
  inject,
  LOCALE_ID,
  PLATFORM_ID,
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
import { ConfigService } from '@/core/services/config.service';
import {
  DocumentCategorizationService,
  type CategorizationSseEvent,
  type CategorizationFileResult as ServiceFileResult,
  type ValidateCategoryResponse,
} from '@/core/services/document-categorization.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { DocumentPreviewComponent } from '@/shared/components/document-preview';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardIconComponent, type ZardIcon } from '@/shared/components/icon';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
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
import {
  buildLocalFilePreview,
  inferPreviewTypeFromUrl,
} from '@/shared/utils/document-preview-source';
import { Subscription } from 'rxjs';

import { MultiFileUploadComponent } from '@/shared/components/multi-file-upload/multi-file-upload.component';
import {
  CategorizationProgressComponent,
  type CategorizationApplyMapping,
  type CategorizationFileResult,
} from './categorization-progress/categorization-progress.component';

interface TimelineWorkflowItem {
  workflow: ApplicationWorkflow;
  gapDaysFromPrevious: number | null;
}

interface PreUploadValidationOutcome {
  status: 'valid' | 'invalid' | 'error';
  result: Record<string, unknown> | null;
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
    ImageMagnifierComponent,
    ZardInputDirective,
    ZardPopoverComponent,
    ZardPopoverDirective,
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    AppDatePipe,
    ...ZardTooltipImports,
    MultiFileUploadComponent,
    CategorizationProgressComponent,
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
  private categorizationService = inject(DocumentCategorizationService);

  readonly application = signal<ApplicationDetail | null>(null);
  readonly isLoading = signal(true);
  readonly isUploadOpen = signal(false);
  readonly selectedDocument = signal<ApplicationDocument | null>(null);
  readonly selectedFile = signal<File | null>(null);
  readonly uploadPreviewUrl = signal<string | null>(null);
  readonly uploadPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPreviewUrl = signal<string | null>(null);
  readonly existingPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPreviewLoading = signal(false);
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
  readonly inlinePreviewLoading = computed(() => {
    if (this.uploadPreviewUrl()) {
      return false;
    }
    return this.existingPreviewLoading();
  });

  readonly ocrPolling = signal(false);
  readonly ocrStatus = signal<string | null>(null);
  readonly ocrPreviewImage = signal<string | null>(null);
  readonly ocrReviewOpen = signal(false);
  readonly ocrReviewData = signal<OcrStatusResponse | null>(null);
  readonly ocrExtractedDataDialogOpen = signal(false);
  readonly ocrExtractedDataDialogText = signal('');
  readonly ocrMetadata = signal<Record<string, unknown> | null>(null);
  readonly ocrExtractedDataText = computed(() => this.buildOcrExtractedDataText());
  readonly ocrHasExtractedData = computed(() => this.ocrExtractedDataText() !== this.ocrNoDataText);
  readonly isAddDocumentDialogOpen = signal(false);
  readonly actionLoading = signal<string | null>(null);
  readonly workflowAction = signal<string | null>(null);

  // AI validation on upload
  readonly validateWithAi = signal(true);
  readonly aiValidationInProgress = signal(false);
  readonly preUploadValidationOutcome = signal<PreUploadValidationOutcome | null>(null);
  readonly preUploadValidationReason = computed(() =>
    this.buildPreUploadValidationReason(this.preUploadValidationOutcome()?.result ?? null),
  );
  readonly preUploadValidationIssues = computed(() => {
    const result = this.preUploadValidationOutcome()?.result ?? null;
    const issues = result?.['negative_issues'] ?? result?.['negativeIssues'];
    return Array.isArray(issues)
      ? issues.filter((issue): issue is string => typeof issue === 'string')
      : [];
  });
  readonly shouldShowSaveAnyway = computed(() => {
    const outcome = this.preUploadValidationOutcome();
    return (
      !!outcome &&
      outcome.status !== 'valid' &&
      this.isAiValidationEnabledForSelectedDocument() &&
      this.validateWithAi() &&
      !!this.selectedFile()
    );
  });
  readonly isAiValidationEnabledForSelectedDocument = computed(() =>
    Boolean(this.selectedDocument()?.docType?.aiValidation),
  );
  readonly originSearchQuery = signal<string | null>(null);
  readonly isSuperuser = this.authService.isSuperuser;
  readonly isSavingMeta = signal(false);
  readonly editableNotes = signal('');

  /**
   * Convert an incoming icon descriptor (often FontAwesome CSS classes) into a
   * lucide/zardUI name suitable for `<z-icon>`.  Returning an empty string
   * causes the template to skip rendering the icon.
   */
  mapIcon(icon: string | null | undefined): ZardIcon {
    if (!icon) {
      return '' as ZardIcon;
    }
    // handle common FontAwesome patterns like "fas fa-file-upload"
    const faMatch = icon.match(/fa[srlb]? fa-([^ ]+)/);
    if (faMatch) {
      const name = faMatch[1];
      const mapping: Record<string, ZardIcon> = {
        'file-upload': 'upload',
        magic: 'sparkles',
        spinner: 'loader-circle',
      };
      return (mapping[name] as ZardIcon) || (name as ZardIcon);
    }
    // otherwise assume the string is already a valid ZardIcon name
    return icon as ZardIcon;
  }
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
  readonly stayPermitSubmissionWindow = computed(() => {
    const app = this.application();
    if (!app || app.product?.productType !== 'visa') {
      return null;
    }

    const configuredStayPermitNames = this.getConfiguredStayPermitDocumentNames(app);
    if (configuredStayPermitNames.size === 0) {
      return null;
    }

    const candidateExpirations = (app.documents ?? [])
      .filter((document) => Boolean(document.docType?.isStayPermit))
      .filter((document) => configuredStayPermitNames.has(document.docType?.name ?? ''))
      .map((document) => this.parseApiDate(document.expirationDate))
      .filter((value): value is Date => Boolean(value));

    if (candidateExpirations.length === 0) {
      return null;
    }

    const sortedExpirations = [...candidateExpirations].sort((a, b) => a.getTime() - b.getTime());
    const lastDate = sortedExpirations[0]!;
    const windowDaysRaw = Number(app.product?.applicationWindowDays ?? 0);
    const windowDays = Number.isFinite(windowDaysRaw) ? Math.max(0, windowDaysRaw) : 0;

    const firstDate = new Date(lastDate.getFullYear(), lastDate.getMonth(), lastDate.getDate());
    firstDate.setDate(firstDate.getDate() - windowDays);

    return {
      firstDate,
      lastDate,
      firstDateIso: this.formatDateForApi(firstDate),
      lastDateIso: this.formatDateForApi(lastDate),
    };
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

  // AI Document Categorization
  readonly isCategorizationActive = signal(false);
  readonly categorizationJobId = signal<string | null>(null);
  readonly categorizationTotalFiles = signal(0);
  readonly categorizationProcessedFiles = signal(0);
  readonly categorizationResults = signal<CategorizationFileResult[]>([]);
  readonly categorizationComplete = signal(false);
  readonly categorizationStatusMessage = signal('');
  readonly categorizationProgressPercentOverride = signal<number | null>(null);
  readonly isCategorizationApplying = signal(false);
  readonly categorizationFiles = signal<File[]>([]);
  private categorizationSub: Subscription | null = null;

  private readonly workflowTimezone = 'Asia/Singapore';

  private pollTimer: number | null = null;
  private readonly ocrNoDataText = 'No OCR extracted data yet.';

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape' && this.ocrExtractedDataDialogOpen()) {
      event.preventDefault();
      this.dismissOcrExtractedDataDialog();
      return;
    }

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
  readonly hasConfiguredDocuments = computed(() => {
    const app = this.application();
    return !!app && this.getConfiguredDocumentNames(app).size > 0;
  });
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
  readonly workflowDueDateById = computed(() => {
    const dueDateById = new Map<number, Date | null>();
    for (const workflow of this.sortedWorkflows()) {
      dueDateById.set(workflow.id, workflow.dueDate ? this.parseApiDate(workflow.dueDate) : null);
    }
    return dueDateById;
  });
  readonly workflowStatusOptionsById = computed(() => {
    const optionsById = new Map<number, ZardComboboxOption[]>();
    for (const workflow of this.sortedWorkflows()) {
      const options: ZardComboboxOption[] = [
        { value: 'pending', label: 'Pending' },
        { value: 'processing', label: 'Processing' },
        { value: 'completed', label: 'Completed' },
        { value: 'rejected', label: 'Rejected' },
      ];
      optionsById.set(
        workflow.id,
        options.map((option) => ({
          ...option,
          disabled:
            option.value !== workflow.status &&
            this.isWorkflowStatusChangeBlocked(workflow, option.value),
        })),
      );
    }
    return optionsById;
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

        // Preserve local order while always refreshing document payloads so badges/metadata
        // (e.g. AI validation status/reason) update immediately after server-side changes.
        const currentIds = new Set(current.map((d) => d.id));
        const docsIds = new Set(docs.map((d) => d.id));
        const docsById = new Map(docs.map((d) => [d.id, d] as const));
        const sameIdSet =
          currentIds.size === docsIds.size && [...docsIds].every((id) => currentIds.has(id));

        if (!sameIdSet) {
          this.localUploadedDocuments.set([...docs]);
          return;
        }

        const merged = current
          .map((doc) => docsById.get(doc.id))
          .filter((doc): doc is ApplicationDocument => Boolean(doc));
        const hasOrderOrLengthDiff =
          merged.length !== current.length ||
          merged.some((doc, idx) => doc.id !== current[idx]?.id || doc !== current[idx]);
        if (hasOrderOrLengthDiff) {
          this.localUploadedDocuments.set(merged);
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
      this.categorizationSub?.unsubscribe();
      this.closeValidationStream();
    });
  }

  openUpload(document: ApplicationDocument): void {
    this.selectedDocument.set(document);
    this.selectedFile.set(null);
    this.clearPreUploadValidationOutcome();
    this.clearUploadPreview();
    this.loadExistingDocumentPreview(document);
    this.uploadProgress.set(null);
    this.ocrPreviewImage.set(null);
    this.ocrReviewOpen.set(false);
    this.ocrReviewData.set(null);
    this.ocrExtractedDataDialogOpen.set(false);
    this.ocrExtractedDataDialogText.set('');
    this.ocrMetadata.set(document.metadata ?? null);
    this.validateWithAi.set(true);
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
    this.ocrExtractedDataDialogOpen.set(false);
    this.ocrExtractedDataDialogText.set('');
    this.closeValidationStream();
    this.clearPreUploadValidationOutcome();
  }

  onFileSelected(file: File): void {
    this.existingPreviewLoading.set(false);
    this.selectedFile.set(file);
    this.clearPreUploadValidationOutcome();
    this.setUploadPreviewFromFile(file);
  }

  onFileCleared(): void {
    this.selectedFile.set(null);
    this.clearPreUploadValidationOutcome();
    this.clearUploadPreview();
    const document = this.selectedDocument();
    if (document) {
      this.loadExistingDocumentPreview(document);
    }
  }

  onValidateWithAiChanged(checked: boolean): void {
    this.validateWithAi.set(checked);
    this.clearPreUploadValidationOutcome();
  }

  onSaveDocument(): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    const formValue = this.uploadForm.getRawValue();
    const file = this.selectedFile();
    const shouldPreValidate =
      this.isAiValidationEnabledForSelectedDocument() && this.validateWithAi() && !!file;

    if (shouldPreValidate && file) {
      const preUploadOutcome = this.preUploadValidationOutcome();
      if (!preUploadOutcome) {
        this.runPreUploadAiValidation(document, file, formValue);
        return;
      }
      this.uploadDocument(
        document,
        formValue,
        file,
        preUploadOutcome.status,
        preUploadOutcome.result,
      );
      return;
    }

    const shouldClearAiValidation =
      !!file && this.isAiValidationEnabledForSelectedDocument() && !this.validateWithAi();
    this.uploadDocument(
      document,
      formValue,
      file,
      shouldClearAiValidation ? '' : undefined,
      shouldClearAiValidation ? null : undefined,
    );
  }

  private runPreUploadAiValidation(
    document: ApplicationDocument,
    file: File,
    formValue: ReturnType<typeof this.uploadForm.getRawValue>,
  ): void {
    this.isSaving.set(true);
    this.aiValidationInProgress.set(true);
    this.uploadProgress.set(null);

    this.categorizationService.validateCategory(document.id, file).subscribe({
      next: (response) => {
        const outcome = this.normalizePreUploadValidationOutcome(response);
        this.preUploadValidationOutcome.set(outcome);
        this.aiValidationInProgress.set(false);

        if (outcome.status === 'valid') {
          this.uploadDocument(document, formValue, file, outcome.status, outcome.result);
          return;
        }

        this.isSaving.set(false);
        this.toast.error(
          `AI validation failed: ${this.buildPreUploadValidationReason(outcome.result) || 'See details below.'}`,
        );
      },
      error: (error) => {
        const message = extractServerErrorMessage(error) || 'AI validation failed';
        this.preUploadValidationOutcome.set({
          status: 'error',
          result: {
            valid: false,
            confidence: 0,
            positive_analysis: '',
            negative_issues: [message],
            reasoning: message,
            extracted_expiration_date: null,
            extracted_doc_number: null,
            extracted_details_markdown: null,
          },
        });
        this.aiValidationInProgress.set(false);
        this.isSaving.set(false);
        this.toast.error(message);
      },
    });
  }

  private uploadDocument(
    document: ApplicationDocument,
    formValue: ReturnType<typeof this.uploadForm.getRawValue>,
    file: File | null,
    aiValidationStatusOverride?: '' | 'valid' | 'invalid' | 'error',
    aiValidationResultOverride?: Record<string, unknown> | null,
  ): void {
    this.isSaving.set(true);
    this.uploadProgress.set(0);

    const mergedPayload = this.mergeUploadFormWithValidationExtraction(
      {
        docNumber: formValue.docNumber || null,
        expirationDate: this.toApiDate(formValue.expirationDate),
        details: formValue.details || null,
      },
      aiValidationResultOverride ?? null,
    );
    const persistedAiValidationResultOverride =
      aiValidationStatusOverride === 'invalid' ? aiValidationResultOverride : null;

    this.applicationsService
      .updateDocument(
        document.id,
        {
          docNumber: mergedPayload.docNumber,
          expirationDate: mergedPayload.expirationDate,
          details: mergedPayload.details,
          metadata: this.ocrMetadata(),
        },
        file,
        false,
        aiValidationStatusOverride,
        persistedAiValidationResultOverride,
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
          this.aiValidationInProgress.set(false);
          this.isSaving.set(false);
        },
      });
  }

  private normalizePreUploadValidationOutcome(
    response: ValidateCategoryResponse,
  ): PreUploadValidationOutcome {
    const responseRecord = response as unknown as Record<string, unknown>;
    const rawStatus = String(responseRecord['validationStatus'] ?? '')
      .trim()
      .toLowerCase();
    let status: 'valid' | 'invalid' | 'error';
    if (rawStatus === 'valid' || rawStatus === 'invalid' || rawStatus === 'error') {
      status = rawStatus;
    } else {
      status = response.matches ? 'valid' : 'invalid';
    }

    const existingResult = responseRecord['validationResult'];
    const result =
      existingResult && typeof existingResult === 'object'
        ? this.normalizeValidationResultShape(existingResult as Record<string, unknown>)
        : {
            valid: status === 'valid',
            confidence: Number(response.confidence ?? 0),
            positive_analysis: status === 'valid' ? String(response.reasoning ?? '') : '',
            negative_issues:
              status === 'invalid'
                ? [String(response.reasoning ?? 'Validation failed')].filter(Boolean)
                : [],
            reasoning: String(response.reasoning ?? ''),
            extracted_expiration_date: null,
            extracted_doc_number: null,
            extracted_details_markdown: null,
          };

    return { status, result };
  }

  private mergeUploadFormWithValidationExtraction(
    payload: {
      docNumber: string | null;
      expirationDate: string | null;
      details: string | null;
    },
    validationResult: Record<string, unknown> | null,
  ): {
    docNumber: string | null;
    expirationDate: string | null;
    details: string | null;
  } {
    if (!validationResult) {
      return payload;
    }

    const extractedExpirationDate =
      typeof (
        validationResult['extracted_expiration_date'] ?? validationResult['extractedExpirationDate']
      ) === 'string'
        ? ((validationResult['extracted_expiration_date'] ??
            validationResult['extractedExpirationDate']) as string)
        : null;
    const extractedDocNumber =
      typeof (
        validationResult['extracted_doc_number'] ?? validationResult['extractedDocNumber']
      ) === 'string'
        ? (
            (validationResult['extracted_doc_number'] ??
              validationResult['extractedDocNumber']) as string
          ).trim() || null
        : null;
    const extractedDetails =
      typeof (
        validationResult['extracted_details_markdown'] ??
        validationResult['extractedDetailsMarkdown']
      ) === 'string'
        ? (
            (validationResult['extracted_details_markdown'] ??
              validationResult['extractedDetailsMarkdown']) as string
          ).trim() || null
        : null;

    return {
      expirationDate: payload.expirationDate || extractedExpirationDate || null,
      docNumber: payload.docNumber || extractedDocNumber || null,
      details: payload.details || extractedDetails || null,
    };
  }

  private buildPreUploadValidationReason(result: Record<string, unknown> | null): string {
    if (!result) {
      return '';
    }
    const negativeIssues = result['negative_issues'] ?? result['negativeIssues'];
    const issues = Array.isArray(negativeIssues)
      ? negativeIssues.filter((issue): issue is string => typeof issue === 'string')
      : [];
    if (issues.length > 0) {
      return issues.join('; ');
    }
    return String(result['reasoning'] ?? '');
  }

  private normalizeValidationResultShape(result: Record<string, unknown>): Record<string, unknown> {
    const normalized: Record<string, unknown> = { ...result };
    if ('negativeIssues' in result && !('negative_issues' in result)) {
      normalized['negative_issues'] = result['negativeIssues'];
    }
    if ('positiveAnalysis' in result && !('positive_analysis' in result)) {
      normalized['positive_analysis'] = result['positiveAnalysis'];
    }
    if ('extractedExpirationDate' in result && !('extracted_expiration_date' in result)) {
      normalized['extracted_expiration_date'] = result['extractedExpirationDate'];
    }
    if ('extractedDocNumber' in result && !('extracted_doc_number' in result)) {
      normalized['extracted_doc_number'] = result['extractedDocNumber'];
    }
    if ('extractedDetailsMarkdown' in result && !('extracted_details_markdown' in result)) {
      normalized['extracted_details_markdown'] = result['extractedDetailsMarkdown'];
    }
    return normalized;
  }

  private clearPreUploadValidationOutcome(): void {
    this.preUploadValidationOutcome.set(null);
  }

  closeValidationStream(): void {
    this.aiValidationInProgress.set(false);
  }

  runOcr(): void {
    const document = this.selectedDocument();
    const file = this.selectedFile();
    if (!document || !document.docType?.aiValidation) {
      return;
    }

    if (this.ocrPolling()) {
      return;
    }

    if (file) {
      this.startOcrForFile(document, file);
      return;
    }

    if (!document.fileLink) {
      this.toast.error('Select or upload a file before running OCR');
      return;
    }

    this.ocrPolling.set(true);
    this.ocrStatus.set('Preparing file');

    this.documentsService.downloadDocumentFile(document.id).subscribe({
      next: (blob) => {
        // Ignore stale response if user switched documents while request was in flight.
        if (this.selectedDocument()?.id !== document.id) {
          this.ocrPolling.set(false);
          this.ocrStatus.set(null);
          return;
        }

        const ocrFile = new File([blob], this.getOcrFileName(document, blob), {
          type: blob.type || 'application/octet-stream',
          lastModified: Date.now(),
        });
        this.startOcrForFile(document, ocrFile);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load file for OCR');
        this.ocrPolling.set(false);
        this.ocrStatus.set(null);
      },
    });
  }

  private startOcrForFile(document: ApplicationDocument, file: File): void {
    this.ocrPolling.set(true);
    this.ocrStatus.set('Queued');

    this.applicationsService
      .startDocumentOcr(file, {
        documentId: document.id,
        docTypeId: document.docType?.id,
      })
      .subscribe({
        next: (response) => {
          const statusUrl =
            ('statusUrl' in response && response.statusUrl) ||
            (response as { status_url?: string }).status_url;
          if (statusUrl) {
            this.pollOcrStatus(statusUrl, 0);
          } else {
            this.handleOcrResult(response as unknown as OcrStatusResponse);
          }
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to start OCR');
          this.ocrPolling.set(false);
        },
      });
  }

  private getOcrFileName(document: ApplicationDocument, blob: Blob): string {
    const link = document.fileLink ?? '';
    const basePath = link.split('?')[0]?.split('#')[0] ?? '';
    const lastSegment = basePath.split('/').filter(Boolean).pop();
    if (lastSegment) {
      try {
        return decodeURIComponent(lastSegment);
      } catch {
        return lastSegment;
      }
    }

    const extension =
      blob.type === 'application/pdf'
        ? 'pdf'
        : blob.type.startsWith('image/')
          ? (blob.type.split('/')[1] ?? 'jpg')
          : 'bin';
    return `document-${document.id}.${extension}`;
  }

  private buildOcrExtractedDataText(): string {
    const review = this.ocrReviewData();
    const metadata = this.ocrMetadata();
    const structuredData = this.getStructuredOcrData(review);
    const directText = this.getDirectOcrText(review);

    if (structuredData && Object.keys(structuredData).length > 0) {
      return JSON.stringify(structuredData, null, 2);
    }

    if (directText) {
      return directText;
    }

    const extracted: Record<string, unknown> = {};
    if (review) {
      const reviewRecord = review as unknown as Record<string, unknown>;
      for (const [key, value] of Object.entries(reviewRecord)) {
        if (value === undefined || value === null || value === '') {
          continue;
        }
        // Skip transport/presentation fields and keep only extracted payload.
        if (
          key === 'jobId' ||
          key === 'status' ||
          key === 'progress' ||
          key === 'previewUrl' ||
          key === 'preview_url' ||
          key === 'b64ResizedImage'
        ) {
          continue;
        }
        extracted[key] = value;
      }
    }

    if (Object.keys(extracted).length > 0) {
      return JSON.stringify(extracted, null, 2);
    }

    if (metadata && Object.keys(metadata).length > 0) {
      return JSON.stringify(metadata, null, 2);
    }

    return this.ocrNoDataText;
  }

  private getStructuredOcrData(
    status: OcrStatusResponse | null,
  ): Record<string, string | null> | null {
    if (!status) {
      return null;
    }

    const directStructured =
      status.structuredData ??
      (status as { structured_data?: Record<string, string | null> }).structured_data;
    if (directStructured && typeof directStructured === 'object') {
      return directStructured;
    }

    const textPayload = this.getDirectOcrText(status);
    if (!textPayload) {
      return null;
    }
    try {
      const parsed = JSON.parse(textPayload);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, string | null>;
      }
    } catch {
      return null;
    }
    return null;
  }

  applyOcrData(): void {
    const data = this.ocrReviewData();
    if (!data) {
      this.ocrReviewOpen.set(false);
      return;
    }

    const patchValue: {
      docNumber?: string;
      expirationDate?: Date | null;
      details?: string;
    } = {};

    if (data.mrzData) {
      patchValue.docNumber = data.mrzData.number ?? '';
      patchValue.expirationDate = this.parseApiDate(data.mrzData.expirationDateYyyyMmDd);
      this.ocrMetadata.set(data.mrzData ?? {});
    }

    const selected = this.selectedDocument();
    if (selected?.docType?.hasDetails) {
      const extractedDetails = this.buildOcrExtractedDataText();
      if (extractedDetails && extractedDetails !== this.ocrNoDataText) {
        const currentDetails = this.uploadForm.getRawValue().details ?? '';
        patchValue.details = this.mergeOcrDetails(currentDetails, extractedDetails);
      }
    }

    if (Object.keys(patchValue).length > 0) {
      this.uploadForm.patchValue(patchValue);
    }
    this.ocrReviewOpen.set(false);
  }

  dismissOcrReview(): void {
    this.ocrReviewOpen.set(false);
  }

  copyOcrExtractedData(): void {
    const payload = this.ocrExtractedDataDialogText();
    if (!payload.trim()) {
      return;
    }

    if (this.isBrowser && typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
      navigator.clipboard
        .writeText(payload)
        .then(() => this.toast.success('Extracted data copied'))
        .catch(() => this.toast.error('Failed to copy extracted data'));
      return;
    }

    this.toast.error('Clipboard API is not available in this browser');
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
            // Keep modal state in sync with the updated document returned by action hooks.
            this.selectedDocument.set(response.document);
            this.selectedFile.set(null);
            this.clearUploadPreview();
            this.loadExistingDocumentPreview(response.document);
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
    return this.workflowDueDateById().get(workflow.id) ?? null;
  }

  getWorkflowStatusOptions(workflow: ApplicationWorkflow): ZardComboboxOption[] {
    return this.workflowStatusOptionsById().get(workflow.id) ?? [];
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

  getUploadedDocumentRowClass(doc: ApplicationDocument): Record<string, boolean> {
    const expirationState = this.getDocumentExpirationState(doc);
    return {
      'uploaded-doc-row-expired': expirationState === 'expired',
      'uploaded-doc-row-expiring': expirationState === 'expiring',
    };
  }

  isDocumentAiValid(doc: ApplicationDocument): boolean {
    return doc.aiValidationStatus === 'valid' && this.getDocumentExpirationState(doc) === 'ok';
  }

  isDocumentAiInvalid(doc: ApplicationDocument): boolean {
    return doc.aiValidationStatus === 'invalid' || this.getDocumentExpirationState(doc) !== 'ok';
  }

  getDocumentValidationTooltip(doc: ApplicationDocument): string {
    if (!this.isDocumentAiInvalid(doc)) {
      return '';
    }
    const expirationReason = this.getDocumentExpirationReason(doc);
    if (expirationReason) {
      return expirationReason;
    }
    return String(doc.aiValidationResult?.['reasoning'] ?? '');
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

    if (field === 'docDate') {
      const submissionWindow = this.stayPermitSubmissionWindow();
      if (
        submissionWindow &&
        !this.isDateInRange(value, submissionWindow.firstDate, submissionWindow.lastDate)
      ) {
        this.toast.error(
          `Application date must be between ${submissionWindow.firstDateIso} and ${submissionWindow.lastDateIso} (inclusive) based on stay permit expiration.`,
        );
        return;
      }
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
    const readyFlag = typeof app.readyForInvoice === 'boolean' ? app.readyForInvoice : true;
    return readyFlag && app.status === 'completed' && !app.hasInvoice;
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
    const maxAttempts = 180;
    const intervalMs = 1000;

    if (attempt >= maxAttempts) {
      this.toast.error('OCR processing timed out');
      this.ocrPolling.set(false);
      return;
    }

    this.pollTimer = window.setTimeout(() => {
      this.applicationsService.getDocumentOcrStatus(statusUrl).subscribe({
        next: (status) => {
          if (status.status === 'completed') {
            this.handleOcrResult(status as unknown as OcrStatusResponse);
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
    const openedExtractedDataDialog = this.handleOcrExtractionForSelectedDocument();
    const previewUrl = status.previewUrl ?? (status as { preview_url?: string }).preview_url;
    if (previewUrl) {
      this.ocrPreviewImage.set(previewUrl);
    } else if (status.b64ResizedImage) {
      this.ocrPreviewImage.set(`data:image/jpeg;base64,${status.b64ResizedImage}`);
    }
    if (!openedExtractedDataDialog && status.mrzData) {
      this.ocrReviewOpen.set(true);
    } else {
      this.ocrReviewOpen.set(false);
    }
  }

  private getDirectOcrText(status: OcrStatusResponse | null): string | null {
    if (!status) {
      return null;
    }
    const textValue =
      typeof status.text === 'string'
        ? status.text
        : typeof (status as { result_text?: string }).result_text === 'string'
          ? (status as { result_text?: string }).result_text!
          : null;
    if (!textValue) {
      return null;
    }
    const trimmed = textValue.trim();
    return trimmed || null;
  }

  private mergeOcrDetails(currentDetails: string, extractedDetails: string): string {
    const current = (currentDetails ?? '').trim();
    const extracted = extractedDetails.trim();
    if (!extracted) {
      return currentDetails;
    }
    if (!current) {
      return extracted;
    }
    if (current.includes(extracted)) {
      return current;
    }
    return `${current}\n\n${extracted}`;
  }

  private getConfiguredStayPermitDocumentNames(application: ApplicationDetail): Set<string> {
    return this.getConfiguredDocumentNames(application);
  }

  private getConfiguredDocumentNames(application: ApplicationDetail): Set<string> {
    return new Set([
      ...this.parseDocumentNames(
        application.product?.requiredDocuments ?? (application.product as any)?.required_documents,
      ),
      ...this.parseDocumentNames(
        application.product?.optionalDocuments ?? (application.product as any)?.optional_documents,
      ),
    ]);
  }

  private parseDocumentNames(value: unknown): string[] {
    if (typeof value !== 'string' || !value.trim()) {
      return [];
    }
    return value
      .split(',')
      .map((item) => item.trim())
      .filter((item) => item.length > 0);
  }

  private getDocumentExpirationState(doc: ApplicationDocument): 'ok' | 'expiring' | 'expired' {
    const metadataState = String(doc.aiValidationResult?.['expiration_state'] ?? '').toLowerCase();
    if (metadataState === 'expired' || metadataState === 'expiring' || metadataState === 'ok') {
      return metadataState;
    }

    if (!doc.docType?.hasExpirationDate) {
      return 'ok';
    }

    const expirationDate = this.parseApiDate(doc.expirationDate);
    if (!expirationDate) {
      return 'ok';
    }

    const today = new Date();
    const todayDate = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (expirationDate.getTime() < todayDate.getTime()) {
      return 'expired';
    }

    const thresholdRaw = Number(doc.docType?.expiringThresholdDays ?? 0);
    const thresholdDays = Number.isFinite(thresholdRaw) ? Math.max(0, thresholdRaw) : 0;
    if (thresholdDays <= 0) {
      return 'ok';
    }

    const thresholdDate = new Date(
      todayDate.getFullYear(),
      todayDate.getMonth(),
      todayDate.getDate(),
    );
    thresholdDate.setDate(thresholdDate.getDate() + thresholdDays);
    if (expirationDate.getTime() <= thresholdDate.getTime()) {
      return 'expiring';
    }

    return 'ok';
  }

  private getDocumentExpirationReason(doc: ApplicationDocument): string {
    const metadataReason = String(doc.aiValidationResult?.['expiration_reason'] ?? '').trim();
    if (metadataReason) {
      return metadataReason;
    }

    const expirationState = this.getDocumentExpirationState(doc);
    if (expirationState === 'ok') {
      return '';
    }

    const expirationDate = this.parseApiDate(doc.expirationDate);
    if (!expirationDate) {
      return '';
    }

    if (expirationState === 'expired') {
      return `Document expired on ${this.formatDateForApi(expirationDate)}.`;
    }

    const thresholdRaw = Number(doc.docType?.expiringThresholdDays ?? 0);
    const thresholdDays = Number.isFinite(thresholdRaw) ? Math.max(0, thresholdRaw) : 0;
    return (
      'Document is expiring soon: expiration date ' +
      `${this.formatDateForApi(expirationDate)} is within ${thresholdDays} days.`
    );
  }

  private isDateInRange(value: Date, start: Date, end: Date): boolean {
    const dateValue = new Date(value.getFullYear(), value.getMonth(), value.getDate()).getTime();
    const startValue = new Date(start.getFullYear(), start.getMonth(), start.getDate()).getTime();
    const endValue = new Date(end.getFullYear(), end.getMonth(), end.getDate()).getTime();
    return dateValue >= startValue && dateValue <= endValue;
  }

  dismissOcrExtractedDataDialog(): void {
    this.ocrExtractedDataDialogOpen.set(false);
    this.ocrExtractedDataDialogText.set('');
  }

  private handleOcrExtractionForSelectedDocument(): boolean {
    const selected = this.selectedDocument();
    if (!selected) {
      return false;
    }

    const extractedDetails = this.buildOcrExtractedDataText();
    if (!extractedDetails || extractedDetails === this.ocrNoDataText) {
      this.ocrExtractedDataDialogOpen.set(false);
      this.ocrExtractedDataDialogText.set('');
      return false;
    }

    if (selected.docType?.hasDetails) {
      const currentDetails = this.uploadForm.getRawValue().details ?? '';
      const merged = this.mergeOcrDetails(currentDetails, extractedDetails);
      if (merged !== currentDetails) {
        this.uploadForm.patchValue({ details: merged });
      }
      this.ocrExtractedDataDialogOpen.set(false);
      this.ocrExtractedDataDialogText.set('');
      return false;
    }

    this.ocrExtractedDataDialogText.set(extractedDetails);
    this.ocrExtractedDataDialogOpen.set(true);
    return true;
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
    const preview = buildLocalFilePreview(file);
    this.uploadPreviewType.set(preview.type);
    this.uploadPreviewUrl.set(preview.url);
  }

  private loadExistingDocumentPreview(document: ApplicationDocument): void {
    this.clearExistingPreview();
    if (!document.fileLink) {
      return;
    }
    this.existingPreviewLoading.set(true);

    this.documentsService.downloadDocumentFile(document.id).subscribe({
      next: (blob) => {
        // Ignore stale async result if user switched document while request was in flight.
        if (this.selectedDocument()?.id !== document.id) {
          this.existingPreviewLoading.set(false);
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
          this.existingPreviewLoading.set(false);
          return;
        }

        this.existingPreviewType.set(type);
        this.existingPreviewUrl.set(url);
        this.existingPreviewLoading.set(false);
      },
      error: () => {
        this.clearExistingPreview();
        this.existingPreviewLoading.set(false);
      },
    });
  }

  private getPreviewTypeFromUrl(url?: string | null): 'image' | 'pdf' | 'unknown' {
    return inferPreviewTypeFromUrl(url);
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
    this.existingPreviewLoading.set(false);
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

  // ─── AI Document Categorization ───────────────────────────────

  onCategorizationFilesSelected(files: File[]): void {
    this.categorizationFiles.set(files);
  }

  onCategorizationFilesCleared(): void {
    this.categorizationFiles.set([]);
  }

  startCategorization(): void {
    const app = this.application();
    const files = this.categorizationFiles();
    if (!app || files.length === 0) return;

    this.isCategorizationActive.set(true);
    this.categorizationComplete.set(false);
    this.categorizationResults.set([]);
    this.categorizationProcessedFiles.set(0);
    this.categorizationProgressPercentOverride.set(0);
    this.categorizationTotalFiles.set(files.length);
    this.categorizationStatusMessage.set(`Preparing upload (${files.length} file(s))...`);

    this.categorizationService.createCategorizationJob(app.id, files.length).subscribe({
      next: (response) => {
        this.categorizationJobId.set(response.jobId);
        this.categorizationTotalFiles.set(response.totalFiles || files.length);
        this.categorizationStatusMessage.set('Connecting to progress stream...');
        this.watchCategorizationJob(response.jobId);

        this.categorizationService.uploadFilesToJob(response.jobId, files).subscribe({
          next: (event) => {
            if (event.type === HttpEventType.UploadProgress) {
              const total = Number(event.total || 0);
              const loaded = Number(event.loaded || 0);
              if (total > 0) {
                const percent = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
                this.categorizationProgressPercentOverride.set(percent);
                this.categorizationStatusMessage.set(`Uploading files... ${percent}%`);
              } else {
                this.categorizationStatusMessage.set('Uploading files...');
              }
            } else if (event.type === HttpEventType.Response) {
              this.categorizationStatusMessage.set('Upload complete. Starting AI processing...');
            }
          },
          error: (error) => {
            this.toast.error(extractServerErrorMessage(error) || 'Failed while uploading files');
            this.dismissCategorization();
          },
        });
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to initialize categorization');
        this.dismissCategorization();
      },
    });
  }

  private watchCategorizationJob(jobId: string): void {
    this.categorizationSub?.unsubscribe();

    this.categorizationSub = this.categorizationService.watchCategorizationJob(jobId).subscribe({
      next: (event: CategorizationSseEvent) => this.handleCategorizationEvent(event),
      error: () => {
        this.categorizationStatusMessage.set('Connection lost. Check results manually.');
        this.categorizationComplete.set(true);
      },
      complete: () => {
        // Stream ended — if not already marked complete, mark it now
        if (!this.categorizationComplete()) {
          this.categorizationComplete.set(true);
        }
      },
    });
  }

  private handleCategorizationEvent(event: CategorizationSseEvent): void {
    switch (event.type) {
      case 'start':
        this.categorizationProgressPercentOverride.set(0);
        this.categorizationProcessedFiles.set(0);
        this.categorizationStatusMessage.set(event.data['message'] ?? 'Starting...');
        break;

      case 'progress': {
        const totalFiles = Number(event.data['totalFiles'] ?? this.categorizationTotalFiles() ?? 0);
        const processedFiles = Number(
          event.data['processedFiles'] ?? this.categorizationProcessedFiles() ?? 0,
        );
        const overallPercent = Number(
          event.data['overallPercent'] ?? this.categorizationProgressPercentOverride() ?? 0,
        );

        if (totalFiles > 0) {
          this.categorizationTotalFiles.set(totalFiles);
        }
        if (processedFiles >= 0) {
          this.categorizationProcessedFiles.set(processedFiles);
        }
        if (Number.isFinite(overallPercent)) {
          this.categorizationProgressPercentOverride.set(
            Math.max(0, Math.min(100, Math.round(overallPercent))),
          );
        }
        this.categorizationStatusMessage.set(event.data['message'] ?? 'Processing...');
        break;
      }

      case 'file_upload_start': {
        const filename = event.data['filename'] ?? '';
        if (!filename) {
          break;
        }
        const current = [...this.categorizationResults()];
        const idx = current.findIndex((r) => r.filename === filename);
        const next: CategorizationFileResult = {
          itemId: '',
          filename,
          status: 'uploading',
          pipelineStage: 'uploading',
          aiValidationEnabled: null,
          documentType: null,
          documentTypeId: null,
          documentId: null,
          confidence: 0,
          reasoning: '',
          error: null,
          categorizationPass: 1,
          validationStatus: null,
          validationReasoning: null,
          validationNegativeIssues: null,
        };
        if (idx >= 0) {
          current[idx] = { ...current[idx], ...next };
        } else {
          current.push(next);
        }
        this.categorizationResults.set(current);
        break;
      }

      case 'file_uploaded': {
        const filename = event.data['filename'] ?? '';
        if (!filename) {
          break;
        }
        const current = [...this.categorizationResults()];
        const idx = current.findIndex((r) => r.filename === filename);
        if (idx >= 0) {
          current[idx] = {
            ...current[idx],
            status: 'queued',
            pipelineStage: 'uploaded',
          };
          this.categorizationResults.set(current);
        }
        break;
      }

      case 'upload_progress': {
        const uploadedFiles = Number(event.data['uploadedFiles'] ?? 0);
        const totalFiles = Number(event.data['totalFiles'] ?? this.categorizationTotalFiles() ?? 0);
        const uploadedBytes = Number(event.data['uploadedBytes'] ?? 0);
        const totalBytes = Number(event.data['totalBytes'] ?? 0);

        if (totalFiles > 0) {
          this.categorizationTotalFiles.set(totalFiles);
          this.categorizationProcessedFiles.set(Math.min(uploadedFiles, totalFiles));
        }

        if (totalBytes > 0) {
          const percent = Math.max(
            0,
            Math.min(100, Math.round((uploadedBytes / totalBytes) * 100)),
          );
          this.categorizationProgressPercentOverride.set(percent);
        }

        this.categorizationStatusMessage.set(
          event.data['message'] ?? `Uploading files... ${uploadedFiles}/${totalFiles}`,
        );
        break;
      }

      case 'upload_complete':
        this.categorizationStatusMessage.set(
          event.data['message'] ?? 'Upload complete. Processing...',
        );
        break;

      case 'file_start':
        this.categorizationStatusMessage.set(
          event.data['message'] ?? `Processing file ${(event.data['index'] ?? 0) + 1}...`,
        );
        // Add file to results in processing state if not already there
        if (event.data['filename']) {
          const current = this.categorizationResults();
          const exists = current.some((r) => r.filename === event.data['filename']);
          if (!exists) {
            this.categorizationResults.set([
              ...current,
              {
                itemId: '',
                filename: event.data['filename']!,
                status: 'processing',
                pipelineStage: 'categorizing',
                aiValidationEnabled: null,
                documentType: null,
                documentTypeId: null,
                documentId: null,
                confidence: 0,
                reasoning: '',
                error: null,
                categorizationPass: 1,
                validationStatus: null,
                validationReasoning: null,
                validationNegativeIssues: null,
              },
            ]);
          } else {
            const idx = current.findIndex((r) => r.filename === event.data['filename']);
            if (idx >= 0) {
              const updated = [...current];
              updated[idx] = {
                ...updated[idx],
                status: 'processing',
                pipelineStage: 'categorizing',
              };
              this.categorizationResults.set(updated);
            }
          }
        }
        break;

      case 'file_categorized': {
        this.categorizationProcessedFiles.update((v) => v + 1);
        const results = [...this.categorizationResults()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        const result: CategorizationFileResult = {
          itemId: event.data['itemId'] ?? '',
          filename: event.data['filename'] ?? '',
          status: 'categorized',
          pipelineStage: 'categorized',
          aiValidationEnabled:
            typeof event.data['aiValidationEnabled'] === 'boolean'
              ? event.data['aiValidationEnabled']
              : null,
          documentType: event.data['documentType'] ?? null,
          documentTypeId: event.data['documentTypeId'] ?? null,
          documentId: event.data['documentId'] ?? null,
          confidence: event.data['confidence'] ?? 0,
          reasoning: event.data['reasoning'] ?? '',
          error: null,
          categorizationPass: event.data['categorizationPass'] ?? 1,
          validationStatus: null,
          validationReasoning: null,
          validationNegativeIssues: null,
        };
        if (idx >= 0) {
          results[idx] = result;
        } else {
          results.push(result);
        }
        this.categorizationResults.set(results);
        this.categorizationStatusMessage.set(event.data['message'] ?? 'Processing...');
        break;
      }

      case 'file_error': {
        this.categorizationProcessedFiles.update((v) => v + 1);
        const results = [...this.categorizationResults()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        const errorResult: CategorizationFileResult = {
          itemId: '',
          filename: event.data['filename'] ?? '',
          status: 'error',
          pipelineStage: 'error',
          aiValidationEnabled: null,
          documentType: null,
          documentTypeId: null,
          documentId: null,
          confidence: 0,
          reasoning: '',
          error: event.data['error'] ?? 'Unknown error',
          categorizationPass: null,
          validationStatus: null,
          validationReasoning: null,
          validationNegativeIssues: null,
        };
        if (idx >= 0) {
          results[idx] = errorResult;
        } else {
          results.push(errorResult);
        }
        this.categorizationResults.set(results);
        break;
      }

      case 'file_categorizing_pass2': {
        const results = [...this.categorizationResults()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        if (idx >= 0) {
          results[idx] = { ...results[idx], categorizationPass: 2 };
          this.categorizationResults.set(results);
        }
        this.categorizationStatusMessage.set(
          event.data['message'] ?? 'Retrying with high-tier model...',
        );
        break;
      }

      case 'file_validating': {
        const results = [...this.categorizationResults()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        if (idx >= 0) {
          results[idx] = {
            ...results[idx],
            validationStatus: 'pending',
            pipelineStage: 'validating',
            aiValidationEnabled:
              typeof event.data['aiValidationEnabled'] === 'boolean'
                ? event.data['aiValidationEnabled']
                : results[idx].aiValidationEnabled,
          };
          this.categorizationResults.set(results);
        }
        this.categorizationStatusMessage.set(event.data['message'] ?? 'Validating document...');
        break;
      }

      case 'file_validated': {
        const results = [...this.categorizationResults()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        if (idx >= 0) {
          results[idx] = {
            ...results[idx],
            validationStatus:
              (event.data['validationStatus'] as CategorizationFileResult['validationStatus']) ??
              null,
            pipelineStage: 'validated',
            aiValidationEnabled:
              typeof event.data['aiValidationEnabled'] === 'boolean'
                ? event.data['aiValidationEnabled']
                : results[idx].aiValidationEnabled,
            validationReasoning: event.data['validationReasoning'] ?? null,
            validationNegativeIssues: event.data['validationNegativeIssues'] ?? null,
          };
          this.categorizationResults.set(results);
        }
        break;
      }

      case 'complete': {
        this.categorizationComplete.set(true);
        this.categorizationProgressPercentOverride.set(100);
        this.categorizationProcessedFiles.set(this.categorizationTotalFiles());
        this.categorizationStatusMessage.set(event.data['message'] ?? 'Complete');
        // Update results with final data including itemIds
        if (event.data['results']) {
          const finalResults: CategorizationFileResult[] = (
            event.data['results'] as ServiceFileResult[]
          ).map((r) => ({
            itemId: r.itemId,
            filename: r.filename,
            status: r.status as CategorizationFileResult['status'],
            pipelineStage: (r.pipelineStage ??
              (r.status as CategorizationFileResult['pipelineStage'])) as
              | 'uploading'
              | 'uploaded'
              | 'categorizing'
              | 'categorized'
              | 'validating'
              | 'validated'
              | 'error',
            aiValidationEnabled:
              typeof r.aiValidationEnabled === 'boolean' ? r.aiValidationEnabled : null,
            documentType: r.documentType,
            documentTypeId: r.documentTypeId,
            documentId: r.documentId,
            confidence: r.confidence,
            reasoning: r.reasoning,
            error: r.error ?? null,
            categorizationPass: r.categorizationPass ?? null,
            validationStatus: r.validationStatus ?? null,
            validationReasoning: r.validationReasoning ?? null,
            validationNegativeIssues: r.validationNegativeIssues ?? null,
          }));
          this.categorizationResults.set(finalResults);
        }
        break;
      }
    }

    this.maybeFinalizeCategorizationFromClientState();
  }

  private maybeFinalizeCategorizationFromClientState(): void {
    if (this.categorizationComplete()) {
      return;
    }

    const total = this.categorizationTotalFiles();
    const results = this.categorizationResults();
    if (total <= 0 || results.length < total) {
      return;
    }

    const isTerminal = (result: CategorizationFileResult): boolean => {
      if (result.status === 'error' || result.pipelineStage === 'error') {
        return true;
      }
      if (result.aiValidationEnabled === false) {
        return result.pipelineStage === 'categorized' || result.pipelineStage === 'validated';
      }
      if (result.validationStatus === 'valid' || result.validationStatus === 'invalid') {
        return true;
      }
      return false;
    };

    if (!results.every(isTerminal)) {
      return;
    }

    this.categorizationComplete.set(true);
    this.categorizationProcessedFiles.set(total);
    this.categorizationProgressPercentOverride.set(100);
    const currentMessage = this.categorizationStatusMessage().trim();
    if (!currentMessage || /processing|categorizing|validating|uploading/i.test(currentMessage)) {
      this.categorizationStatusMessage.set('Processing complete');
    }
  }

  onApplyCategorization(mappings: CategorizationApplyMapping[]): void {
    const jobId = this.categorizationJobId();
    if (!jobId) return;

    const normalizedMappings = mappings.filter(
      (mapping) => typeof mapping.itemId === 'string' && mapping.itemId.trim().length > 0,
    );
    if (normalizedMappings.length === 0) {
      this.toast.error('No valid matched files to apply yet. Please wait a moment and retry.');
      return;
    }

    this.isCategorizationApplying.set(true);

    this.categorizationService
      .applyResults(
        jobId,
        normalizedMappings.map((m) => ({
          itemId: m.itemId,
          documentId: m.documentId,
        })),
      )
      .subscribe({
        next: (response) => {
          this.isCategorizationApplying.set(false);
          if (response.totalApplied > 0) {
            this.toast.success(`${response.totalApplied} document(s) applied successfully`);
            // Reload application to reflect updated documents
            const app = this.application();
            if (app) {
              this.loadApplication(app.id);
            }
          }
          if (response.totalErrors > 0) {
            this.toast.error(`${response.totalErrors} document(s) failed to apply`);
          }
          this.dismissCategorization();
        },
        error: (error) => {
          this.isCategorizationApplying.set(false);
          this.toast.error(extractServerErrorMessage(error) || 'Failed to apply categorization');
        },
      });
  }

  dismissSelectedCategorization(selectedKeys: string[]): void {
    if (!selectedKeys || selectedKeys.length === 0) {
      return;
    }

    const current = this.categorizationResults();
    const selectedKeySet = new Set(selectedKeys);
    const remaining = current.filter(
      (result, index) => !selectedKeySet.has(this.getCategorizationResultKey(result, index)),
    );
    const dismissedCount = current.length - remaining.length;

    if (dismissedCount <= 0) {
      return;
    }

    this.categorizationResults.set(remaining);
    this.toast.success(`${dismissedCount} document(s) dismissed`);

    if (remaining.length === 0) {
      this.dismissCategorization();
    }
  }

  private getCategorizationResultKey(result: CategorizationFileResult, index: number): string {
    return result.itemId || `${result.filename}-${index}`;
  }

  dismissCategorization(): void {
    this.categorizationSub?.unsubscribe();
    this.categorizationSub = null;
    this.isCategorizationActive.set(false);
    this.categorizationJobId.set(null);
    this.categorizationTotalFiles.set(0);
    this.categorizationProcessedFiles.set(0);
    this.categorizationResults.set([]);
    this.categorizationComplete.set(false);
    this.categorizationStatusMessage.set('');
    this.categorizationProgressPercentOverride.set(null);
    this.categorizationFiles.set([]);
  }
}
