import { DragDropModule } from '@angular/cdk/drag-drop';
import { formatDate as angularFormatDate, CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  HostListener,
  inject,
  isDevMode,
  LOCALE_ID,
  PLATFORM_ID,
  signal,
  type OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { DocumentTypesService } from '@/core/api/api/document-types.service';
import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
  type ApplicationWorkflow,
  type DocumentAction,
} from '@/core/services/applications.service';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { CardSectionComponent } from '@/shared/components/card-section';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { DocumentPreviewComponent } from '@/shared/components/document-preview';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardIconComponent, type ZardIcon } from '@/shared/components/icon';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { ZardInputDirective } from '@/shared/components/input';

import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import {
  formatDateForApi,
  formatDateForDisplay,
  isDateInRange,
  parseApiDate,
} from '@/shared/utils/date-parsing';

import { extractServerErrorMessage } from '@/shared/utils/form-errors';

import {
  ApplicationDeleteDialogComponent,
  type ApplicationDeleteDialogData,
} from '@/shared/components/application-delete-dialog';
import { MultiFileUploadComponent } from '@/shared/components/multi-file-upload/multi-file-upload.component';
import { AddDocumentDialogComponent } from './add-document-dialog.component';
import { ApplicationWorkflowTimelineComponent } from './application-workflow-timeline.component';
import { ApplicationCategorizationHandler } from './categorization-handler.service';
import {
  CategorizationProgressComponent,
  type CategorizationApplyMapping,
} from './categorization-progress/categorization-progress.component';
import { DocumentCollectionService } from './document-collection.service';
import { DocumentUploadService } from './document-upload.service';
import { OcrDataDialogComponent } from './ocr-data-dialog.component';
import { ApplicationOcrService } from './ocr-flow.service';
import { OcrReviewDialogComponent } from './ocr-review-dialog.component';
import { PendingFieldRefreshService } from './pending-field-refresh.service';
import { ApplicationWorkflowService } from './workflow.service';

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
    CardSectionComponent,
    ZardComboboxComponent,
    ZardDateInputComponent,
    DocumentPreviewComponent,
    FileUploadComponent,
    ZardIconComponent,
    ImageMagnifierComponent,
    ZardInputDirective,
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    AppDatePipe,
    ...ZardTooltipImports,
    MultiFileUploadComponent,
    CategorizationProgressComponent,
    ApplicationWorkflowTimelineComponent,
    AddDocumentDialogComponent,
    ApplicationDeleteDialogComponent,
    OcrReviewDialogComponent,
    OcrDataDialogComponent,
  ],
  providers: [
    ApplicationCategorizationHandler,
    ApplicationOcrService,
    ApplicationWorkflowService,
    PendingFieldRefreshService,
    DocumentUploadService,
    DocumentCollectionService,
  ],
  templateUrl: './application-detail.component.html',
  styleUrls: ['./application-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private applicationsService = inject(ApplicationsService);
  private documentTypesService = inject(DocumentTypesService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private destroyRef = inject(DestroyRef);
  private platformId = inject(PLATFORM_ID);
  private locale = inject(LOCALE_ID);
  private configService = inject(ConfigService);
  private readonly isBrowser = isPlatformBrowser(this.platformId);
  readonly isDevelopmentMode = isDevMode();
  // Categorization handler (extracted service — provides all categorization state & logic)
  readonly catHandler = inject(ApplicationCategorizationHandler);
  readonly ocrService = inject(ApplicationOcrService);
  readonly workflowService = inject(ApplicationWorkflowService);
  private readonly pendingRefresh = inject(PendingFieldRefreshService);
  readonly uploadService = inject(DocumentUploadService);
  readonly collectionService = inject(DocumentCollectionService);

  readonly application = signal<ApplicationDetail | null>(null);
  readonly isLoading = signal(true);

  // Upload — delegated to uploadService
  readonly isUploadOpen = this.uploadService.isOpen;
  readonly selectedDocument = this.uploadService.selectedDocument;
  readonly selectedFile = this.uploadService.selectedFile;
  readonly uploadPreviewUrl = this.uploadService.uploadPreviewUrl;
  readonly uploadPreviewType = this.uploadService.uploadPreviewType;
  readonly existingPreviewUrl = this.uploadService.existingPreviewUrl;
  readonly existingPreviewType = this.uploadService.existingPreviewType;
  readonly existingPreviewLoading = this.uploadService.existingPreviewLoading;
  readonly uploadProgress = this.uploadService.uploadProgress;
  readonly isSaving = this.uploadService.isSaving;
  readonly inlinePreviewUrl = this.uploadService.inlinePreviewUrl;
  readonly inlinePreviewType = this.uploadService.inlinePreviewType;
  readonly inlinePreviewLoading = this.uploadService.inlinePreviewLoading;

  // OCR — delegated to ocrService
  readonly ocrPolling = this.ocrService.polling;
  readonly ocrStatus = this.ocrService.status;
  readonly ocrPreviewImage = this.ocrService.previewImage;
  readonly ocrReviewOpen = this.ocrService.reviewOpen;
  readonly ocrReviewData = this.ocrService.reviewData;
  readonly ocrExtractedDataDialogOpen = this.ocrService.extractedDataDialogOpen;
  readonly ocrExtractedDataDialogText = this.ocrService.extractedDataDialogText;
  readonly ocrMetadata = this.ocrService.metadata;
  readonly ocrExtractedDataText = this.ocrService.extractedDataText;
  readonly ocrHasExtractedData = this.ocrService.hasExtractedData;
  readonly ocrPreviewExpanded = this.ocrService.previewExpanded;
  readonly isAddDocumentDialogOpen = signal(false);
  readonly actionLoading = this.collectionService.actionLoading;
  readonly workflowAction = this.workflowService.action;

  readonly deleteWithInvoiceOpen = signal(false);
  readonly deleteWithInvoiceData = signal<ApplicationDeleteDialogData | null>(null);

  readonly isAutoGeneratingAll = this.collectionService.isAutoGeneratingAll;
  readonly canAutoGenerateAnyDocuments = this.collectionService.canAutoGenerateAnyDocuments;

  // AI validation on upload — delegated to uploadService
  readonly validateWithAi = this.uploadService.validateWithAi;
  readonly aiValidationInProgress = this.uploadService.aiValidationInProgress;
  readonly preUploadValidationOutcome = this.uploadService.preUploadValidationOutcome;
  readonly preUploadValidationReason = this.uploadService.preUploadValidationReason;
  readonly preUploadValidationRuntimeLabel = this.uploadService.preUploadValidationRuntimeLabel;
  readonly preUploadValidationIssues = this.uploadService.preUploadValidationIssues;
  readonly shouldShowSaveAnyway = this.uploadService.shouldShowSaveAnyway;
  readonly isAiValidationEnabledForSelectedDocument =
    this.uploadService.isAiValidationEnabledForSelectedDocument;
  readonly originSearchQuery = signal<string | null>(null);
  readonly originPage = signal<number | null>(null);
  readonly isSuperuser = this.authService.isSuperuser;
  readonly isAdminOrManager = this.authService.isAdminOrManager;
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
  readonly availableDocumentTypes = signal<
    Array<{ id: number; name: string; isStayPermit: boolean }>
  >([]);
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
    const hasStayPermitAlready = (app.documents ?? []).some((doc) =>
      Boolean(doc.docType?.isStayPermit),
    );
    const stayPermitTypeIds = new Set(
      this.availableDocumentTypes()
        .filter((docType) => docType.isStayPermit)
        .map((docType) => String(docType.id)),
    );
    return options.filter(
      (opt) =>
        !existingDocTypeIds.has(opt.value) &&
        (!hasStayPermitAlready || !stayPermitTypeIds.has(opt.value)),
    );
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
  readonly hasWorkflowTasks = this.workflowService.hasWorkflowTasks;
  readonly stepOneWorkflow = this.workflowService.stepOneWorkflow;
  readonly isApplicationDateLocked = this.workflowService.isApplicationDateLocked;
  readonly applicationDateLockedTooltip =
    'Application submission date cannot be changed after Step 1 is completed.';
  readonly isDueDateLocked = this.workflowService.isDueDateLocked;
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
  readonly passportImportPending = computed(() => {
    const app = this.application();
    if (!app || !this.pendingRefresh.passport.enabled()) {
      return false;
    }
    return this.isPassportConfigured(app) && !this.hasPassportDocument(app);
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
      .map((document) => parseApiDate(document.expirationDate))
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
      firstDateIso: formatDateForApi(firstDate),
      lastDateIso: formatDateForApi(lastDate),
      firstDateDisplay: this.displayDate(formatDateForApi(firstDate)),
      lastDateDisplay: this.displayDate(formatDateForApi(lastDate)),
    };
  });
  readonly submissionWindowMinDate = computed(
    () => this.stayPermitSubmissionWindow()?.firstDate ?? null,
  );
  readonly submissionWindowMaxDate = computed(
    () => this.stayPermitSubmissionWindow()?.lastDate ?? null,
  );
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
  readonly canRollbackWorkflowFn = this.workflowService.canRollbackWorkflowFn;
  readonly isWorkflowDueDateEditableFn = this.workflowService.isWorkflowDueDateEditableFn;
  readonly isWorkflowEditableFn = this.workflowService.isWorkflowEditableFn;
  readonly getWorkflowStatusGuardMessageFn = this.workflowService.getWorkflowStatusGuardMessageFn;

  // PDF Merge and Selection — delegated to collectionService
  readonly localUploadedDocuments = this.collectionService.localUploadedDocuments;
  readonly selectedDocumentIds = this.collectionService.selectedDocumentIds;
  readonly areAllUploadedDocumentsSelected = this.collectionService.areAllUploadedDocumentsSelected;
  readonly isUploadedDocumentSelectionPartial =
    this.collectionService.isUploadedDocumentSelectionPartial;
  readonly isMerging = this.collectionService.isMerging;

  // AI Document Categorization — delegated to catHandler
  readonly isCategorizationActive = this.catHandler.isActive;
  readonly categorizationTotalFiles = this.catHandler.totalFiles;
  readonly categorizationProcessedFiles = this.catHandler.processedFiles;
  readonly categorizationResults = this.catHandler.results;
  readonly categorizationComplete = this.catHandler.isComplete;
  readonly categorizationStatusMessage = this.catHandler.statusMessage;
  readonly categorizationProgressPercentOverride = this.catHandler.progressPercentOverride;
  readonly isCategorizationApplying = this.catHandler.isApplying;
  readonly categorizationFiles = this.catHandler.files;

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

  readonly uploadedDocuments = this.collectionService.uploadedDocuments;
  readonly hasConfiguredDocuments = computed(() => {
    const app = this.application();
    return !!app && this.getConfiguredDocumentNames(app).size > 0;
  });
  readonly requiredDocuments = this.collectionService.requiredDocuments;
  readonly optionalDocuments = this.collectionService.optionalDocuments;
  readonly documentCollectionStatus = this.collectionService.documentCollectionStatus;

  readonly sortedWorkflows = this.workflowService.sortedWorkflows;
  readonly timelineItems = this.workflowService.timelineItems;
  readonly pendingStartNotice = this.workflowService.pendingStartNotice;

  readonly canReopen = this.workflowService.canReopen;

  readonly uploadForm = this.uploadService.uploadForm;

  constructor() {
    // When categorization applies results, reload the application
    this.catHandler.applicationReloadRequested
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        const app = this.application();
        if (app) this.loadApplication(app.id);
      });
  }

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    const st = this.isBrowser ? (window as any).history.state || {} : {};
    this.originSearchQuery.set(st.searchQuery ?? null);
    if (Boolean(st.awaitPassportImport)) {
      this.pendingRefresh.passport.start();
    }
    const page = Number(st.page);
    if (Number.isFinite(page) && page > 0) {
      this.originPage.set(Math.floor(page));
    }
    if (!id) {
      this.toast.error('Invalid application ID');
      this.isLoading.set(false);
      return;
    }
    this.loadApplication(id);
    this.loadDocumentTypes();

    this.workflowService.init({
      application: this.application,
      loadApplication: (appId) => this.loadApplication(appId),
      applyApplicationFromActionResponse: (response) =>
        this.applyApplicationFromActionResponse(response),
      patchApplicationLocally: (mutator) => this.patchApplicationLocally(mutator),
      displayDate: (value) => this.displayDate(value as string),
      stayPermitSubmissionWindow: this.stayPermitSubmissionWindow,
    });

    this.pendingRefresh.init((appId) => this.loadApplication(appId, { silent: true }));

    this.uploadService.init({
      application: this.application,
      ocrMetadata: this.ocrMetadata,
      replaceDocument: (updated) => this.replaceDocument(updated),
      loadApplication: (appId, options) => this.loadApplication(appId, options),
      resetOcrOnOpen: (document) => {
        this.ocrPreviewImage.set(null);
        this.ocrReviewOpen.set(false);
        this.ocrReviewData.set(null);
        this.ocrExtractedDataDialogOpen.set(false);
        this.ocrExtractedDataDialogText.set('');
        this.ocrMetadata.set(document.metadata ?? null);
      },
      resetOcrOnClose: () => {
        this.ocrPolling.set(false);
        this.ocrStatus.set(null);
        this.ocrExtractedDataDialogOpen.set(false);
        this.ocrExtractedDataDialogText.set('');
      },
    });

    this.collectionService.init({
      application: this.application,
      categorizationResults: this.catHandler.results,
      isDevelopmentMode: this.isDevelopmentMode,
      replaceDocument: (updated) => this.replaceDocument(updated),
      displayDate: (value) => this.displayDate(value as string),
    });

    this.destroyRef.onDestroy(() => {
      this.ocrService.destroy();
      this.pendingRefresh.destroy();
      this.uploadService.destroy();
      this.catHandler.destroy();
    });
  }

  openUpload(document: ApplicationDocument): void {
    this.uploadService.open(document);
  }

  closeUpload(): void {
    this.uploadService.close();
  }

  onFileSelected(file: File): void {
    this.uploadService.onFileSelected(file);
  }

  onFileCleared(): void {
    this.uploadService.onFileCleared();
  }

  onValidateWithAiChanged(checked: boolean): void {
    this.uploadService.onValidateWithAiChanged(checked);
  }

  onSaveDocument(): void {
    this.uploadService.onSaveDocument();
  }

  closeValidationStream(): void {
    this.uploadService.closeValidationStream();
  }

  runOcr(): void {
    this.ocrService.runOcrWithCallback(this.selectedDocument(), this.selectedFile(), (status) => {
      const selected = this.selectedDocument();
      const currentDetails = this.uploadForm.getRawValue().details ?? '';
      const openedDialog = this.ocrService.handleOcrExtractionForSelectedDocument(
        selected,
        currentDetails,
        (merged) => this.uploadForm.patchValue({ details: merged }),
      );
      if (!openedDialog && status.mrzData) {
        this.ocrService.reviewOpen.set(true);
      } else {
        this.ocrService.reviewOpen.set(false);
      }
    });
  }

  applyOcrData(): void {
    this.ocrService.applyOcrData(
      this.selectedDocument(),
      this.uploadForm.getRawValue().details ?? '',
      (patch) => this.uploadForm.patchValue(patch),
    );
  }

  dismissOcrReview(): void {
    this.ocrService.dismissReview();
  }

  executeAction(action: DocumentAction): void {
    this.collectionService.executeAction(action);
  }

  canShowAutomaticShortcut(doc: ApplicationDocument): boolean {
    return this.collectionService.canShowAutomaticShortcut(doc);
  }

  getAutomaticShortcutLabel(doc: ApplicationDocument): string {
    return this.collectionService.getAutomaticShortcutLabel(doc);
  }

  getAutomaticShortcutTooltip(doc: ApplicationDocument): string {
    return this.collectionService.getAutomaticShortcutTooltip(doc);
  }

  runAutomaticShortcut(doc: ApplicationDocument): void {
    this.collectionService.runAutomaticShortcut(doc);
  }

  autoGenerateAllDocuments(): void {
    this.collectionService.autoGenerateAllDocuments();
  }

  isAutomaticShortcutLoading(doc: ApplicationDocument): boolean {
    return this.collectionService.isAutomaticShortcutLoading(doc);
  }

  isActionLoadingFor(doc: ApplicationDocument, actionName: string): boolean {
    return this.collectionService.isActionLoadingFor(doc, actionName);
  }

  viewDocument(doc: ApplicationDocument): void {
    this.collectionService.viewDocument(doc);
  }

  isFileOnlyDocument(doc: ApplicationDocument): boolean {
    return this.collectionService.isFileOnlyDocument(doc);
  }

  hasDocumentTextFields(doc: ApplicationDocument): boolean {
    return this.collectionService.hasDocumentTextFields(doc);
  }

  hasViewableContent(doc: ApplicationDocument): boolean {
    return this.collectionService.hasViewableContent(doc);
  }

  openDocumentViewDialog(doc: ApplicationDocument): void {
    this.collectionService.openDocumentViewDialog(doc);
  }

  toggleDocumentSelection(id: number): void {
    this.collectionService.toggleDocumentSelection(id);
  }

  selectAllDocuments(): void {
    this.collectionService.selectAllDocuments();
  }

  deselectAllDocuments(): void {
    this.collectionService.deselectAllDocuments();
  }

  toggleAllUploadedDocumentsSelection(): void {
    this.collectionService.toggleAllUploadedDocumentsSelection();
  }

  onDocumentDrop(event: any): void {
    this.collectionService.onDocumentDrop(event);
  }

  mergeAndDownloadSelected(): void {
    this.collectionService.mergeAndDownloadSelected();
  }

  advanceWorkflow(): void {
    this.workflowService.advanceWorkflow();
  }

  deleteApplication(): void {
    const app = this.application();
    if (!app || !this.isAdminOrManager()) return;

    if (app.hasInvoice) {
      this.deleteWithInvoiceData.set({
        applicationId: app.id,
        invoiceId: app.invoiceId,
      });
      this.deleteWithInvoiceOpen.set(true);
      return;
    }

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

  confirmDeleteWithInvoiceAction(): void {
    const app = this.application();
    if (!app) return;

    this.workflowAction.set('delete');
    this.applicationsService.deleteApplication(app.id, true).subscribe({
      next: () => {
        this.toast.success('Application deleted');
        this.deleteWithInvoiceOpen.set(false);
        this.deleteWithInvoiceData.set(null);
        this.goBack();
        this.workflowAction.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to delete application');
        this.deleteWithInvoiceOpen.set(false);
        this.deleteWithInvoiceData.set(null);
        this.workflowAction.set(null);
      },
    });
  }

  cancelDeleteWithInvoiceAction(): void {
    this.deleteWithInvoiceOpen.set(false);
    this.deleteWithInvoiceData.set(null);
  }

  updateWorkflowStatus(workflowId: number, status: string | null): void {
    this.workflowService.updateWorkflowStatus(workflowId, status);
  }

  updateWorkflowDueDate(workflow: ApplicationWorkflow, value: Date | null): void {
    this.workflowService.updateWorkflowDueDate(workflow, value);
  }

  rollbackWorkflow(workflow: ApplicationWorkflow): void {
    this.workflowService.rollbackWorkflow(workflow);
  }

  reopenApplication(): void {
    this.workflowService.reopenApplication();
  }

  canForceClose(): boolean {
    return this.workflowService.canForceClose();
  }

  confirmForceClose(): void {
    this.workflowService.confirmForceClose();
  }

  canCreateInvoice(): boolean {
    const app = this.application();
    return !!(app && !app.hasInvoice);
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
        page: this.originPage() ?? undefined,
      },
    });
  }

  customerDetailLink(): Array<string | number> {
    const customerId = this.application()?.customer?.id;
    return ['/customers', customerId ?? ''];
  }

  customerDetailState(): Record<string, unknown> {
    const app = this.application();
    const currentState = this.isBrowser
      ? ((history.state as Record<string, unknown> | null) ?? {})
      : {};
    return {
      from: 'application-detail',
      applicationId: app?.id,
      customerId: app?.customer?.id,
      returnUrl: app ? `/applications/${app.id}` : '/applications',
      returnState: { ...currentState },
      searchQuery: this.originSearchQuery(),
      page: this.originPage() ?? undefined,
    };
  }

  getApplicationHeaderTitle(): string {
    const app = this.application();
    if (!app) {
      return '';
    }

    const code = app.product?.code?.trim() || '—';
    const name = app.product?.name?.trim() || '—';
    if (code === name) {
      return `Application #${app.id} - ${code}`;
    }

    return `Application #${app.id} - ${code} - ${name}`;
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

  getUploadedDocumentRowClass(doc: ApplicationDocument): Record<string, boolean> {
    return this.collectionService.getUploadedDocumentRowClass(doc);
  }

  isDocumentAiValid(doc: ApplicationDocument): boolean {
    return this.collectionService.isDocumentAiValid(doc);
  }

  isDocumentAiInvalid(doc: ApplicationDocument): boolean {
    return this.collectionService.isDocumentAiInvalid(doc);
  }

  getDocumentAiCheckBadge(doc: ApplicationDocument): any {
    return this.collectionService.getDocumentAiCheckBadge(doc);
  }

  getDocumentValidationTooltip(doc: ApplicationDocument): string {
    return this.collectionService.getDocumentValidationTooltip(doc);
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
    const page = Number(st.page ?? this.originPage());
    if (Number.isFinite(page) && page > 0) {
      focusState['page'] = Math.floor(page);
    }

    if (st.from === 'applications') {
      this.router.navigate(['/applications'], { state: focusState });
      return;
    }
    if (typeof st.returnUrl === 'string' && st.returnUrl.startsWith('/')) {
      this.router.navigateByUrl(st.returnUrl, {
        state: { searchQuery: st.searchQuery ?? null, page: st.page ?? this.originPage() ?? null },
      });
      return;
    }
    if (st.from === 'customer-detail' && st.customerId) {
      this.router.navigate(['/customers', st.customerId], {
        state: { searchQuery: st.searchQuery ?? null, page: st.page ?? this.originPage() ?? null },
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
    this.router.navigate(['/applications'], {
      state: {
        focusTable: true,
        page: this.originPage() ?? undefined,
      },
    });
  }

  onInlineDateChange(field: 'docDate' | 'dueDate', value: Date | null): void {
    if (!value) return;
    if (field === 'docDate' && this.isApplicationDateLocked()) {
      this.toast.error(this.applicationDateLockedTooltip);
      return;
    }
    if (field === 'dueDate' && this.isDueDateLocked()) {
      this.toast.error(this.dueDateLockedTooltip);
      return;
    }

    if (field === 'docDate') {
      const submissionWindow = this.stayPermitSubmissionWindow();
      if (
        submissionWindow &&
        !isDateInRange(value, submissionWindow.firstDate, submissionWindow.lastDate)
      ) {
        this.toast.error(
          `Application submission date must be between ${submissionWindow.firstDateDisplay} and ${submissionWindow.lastDateDisplay} (inclusive) based on stay permit expiration.`,
        );
        return;
      }
    }

    const iso = formatDateForApi(value);
    this.updateApplicationPartial(
      { [field]: iso } as any,
      `${field === 'docDate' ? 'Application submission' : 'Due'} date updated`,
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

  addApplicationDocument(docTypeId?: string): void {
    const resolvedDocTypeId = docTypeId ?? this.selectedNewDocType();
    const app = this.application();
    if (!resolvedDocTypeId || !app) return;
    const selectedDocType = this.availableDocumentTypes().find(
      (doc) => String(doc.id) === String(resolvedDocTypeId),
    );
    if (
      selectedDocType?.isStayPermit &&
      app.documents.some(
        (document) =>
          Boolean(document.docType?.isStayPermit) &&
          String(document.docType?.id) !== String(resolvedDocTypeId),
      )
    ) {
      this.toast.error('Only one stay permit document type can be added to an application.');
      return;
    }
    const payloadDocs = app.documents.map((d) => ({ id: d.docType.id, required: d.required }));
    if (!payloadDocs.some((d) => String(d.id) === String(resolvedDocTypeId))) {
      payloadDocs.push({ id: Number(resolvedDocTypeId), required: true });
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
    const isDocDateUpdate = Object.prototype.hasOwnProperty.call(payload, 'docDate');
    if (isDocDateUpdate) {
      this.pendingRefresh.dueDate.start();
    }
    this.isSavingMeta.set(true);
    this.applicationsService.updateApplicationPartial(app.id, payload).subscribe({
      next: (response) => {
        const applied = this.applyApplicationFromActionResponse(response);
        this.toast.success(successMessage);
        if (applied) {
          const current = this.application();
          if (isDocDateUpdate && current) {
            this.pendingRefresh.dueDate.handleRefresh(
              app.id,
              this.shouldAwaitDueDateRefresh(current),
            );
          }
          this.isSavingMeta.set(false);
          return;
        }
        this.loadApplication(app.id);
      },
      error: (error) => {
        if (isDocDateUpdate) {
          this.pendingRefresh.dueDate.clear();
        }
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update application');
        this.isSavingMeta.set(false);
      },
    });
  }

  private patchApplicationLocally(
    mutator: (current: ApplicationDetail) => ApplicationDetail,
  ): boolean {
    const current = this.application();
    if (!current) {
      return false;
    }
    const next = mutator(current);
    this.application.set(next);
    return true;
  }

  private normalizeApplicationPayload(raw: any): ApplicationDetail {
    const docDate = raw?.docDate ?? raw?.doc_date;
    const dueDate = raw?.dueDate ?? raw?.due_date ?? null;
    return {
      ...raw,
      docDate: docDate ?? '',
      dueDate,
      addDeadlinesToCalendar: raw?.addDeadlinesToCalendar ?? raw?.add_deadlines_to_calendar,
      notifyCustomer: raw?.notifyCustomer ?? raw?.notifyCustomerToo ?? false,
      notifyCustomerChannel: raw?.notifyCustomerChannel ?? raw?.notify_customer_channel ?? null,
      readyForInvoice: raw?.readyForInvoice ?? raw?.ready_for_invoice ?? undefined,
    };
  }

  private applyApplicationFromActionResponse(response: unknown): boolean {
    if (!response || typeof response !== 'object') {
      return false;
    }
    const raw = response as Record<string, unknown>;
    const id = Number(raw['id']);
    const workflows = raw['workflows'];
    const documents = raw['documents'];
    if (!Number.isFinite(id) || !Array.isArray(workflows) || !Array.isArray(documents)) {
      return false;
    }
    const normalized = this.normalizeApplicationPayload(raw);
    this.application.set(normalized);
    this.editableNotes.set(normalized?.notes ?? '');
    return true;
  }

  private loadDocumentTypes(): void {
    this.documentTypesService.documentTypesList().subscribe({
      next: (types) => {
        const normalized = (types ?? []).map((t) => ({
          id: Number(t.id),
          name: t.name,
          isStayPermit: Boolean(t.isStayPermit),
        }));
        this.availableDocumentTypes.set(normalized);
        this.docTypeOptions.set(normalized.map((t) => ({ value: String(t.id), label: t.name })));
      },
      error: () => {
        this.availableDocumentTypes.set([]);
        this.docTypeOptions.set([]);
      },
    });
  }

  private loadApplication(id: number, options?: { silent?: boolean }): void {
    if (!options?.silent) {
      this.isLoading.set(true);
    }
    this.applicationsService.getApplication(id).subscribe({
      next: (data) => {
        const normalized = this.normalizeApplicationPayload(data);
        this.application.set(normalized);
        this.editableNotes.set(normalized?.notes ?? '');
        this.pendingRefresh.passport.handleRefresh(
          id,
          this.isPassportConfigured(normalized) && !this.hasPassportDocument(normalized),
        );
        this.pendingRefresh.dueDate.handleRefresh(id, this.shouldAwaitDueDateRefresh(normalized));
        if (!options?.silent) {
          this.isLoading.set(false);
        }
        this.isSavingMeta.set(false);
      },
      error: (error) => {
        if (options?.silent) {
          this.pendingRefresh.passport.scheduleRetry(id);
          this.pendingRefresh.dueDate.scheduleRetry(id);
          if (this.pendingRefresh.passport.isActive() || this.pendingRefresh.dueDate.isActive()) {
            return;
          }
        }
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load application');
        this.isLoading.set(false);
        this.isSavingMeta.set(false);
      },
    });
  }

  private shouldAwaitDueDateRefresh(application: ApplicationDetail): boolean {
    const dueDate = typeof application.dueDate === 'string' ? application.dueDate.trim() : '';
    if (dueDate) {
      return false;
    }

    if (application.addDeadlinesToCalendar === false) {
      return false;
    }

    return Boolean(application.hasNextTask || application.nextTask);
  }

  private isPassportConfigured(application: ApplicationDetail): boolean {
    return this.getConfiguredDocumentNames(application).has('Passport');
  }

  private hasPassportDocument(application: ApplicationDetail): boolean {
    return (application.documents ?? []).some(
      (document) => (document.docType?.name ?? '').trim().toLowerCase() === 'passport',
    );
  }

  private getConfiguredStayPermitDocumentNames(application: ApplicationDetail): Set<string> {
    return this.getConfiguredDocumentNames(application);
  }

  private getConfiguredDocumentNames(application: ApplicationDetail): Set<string> {
    return new Set([
      ...this.parseDocumentNames(application.product?.requiredDocuments),
      ...this.parseDocumentNames(application.product?.optionalDocuments),
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

  // isDateInRange → isDateInRange (shared)

  dismissOcrExtractedDataDialog(): void {
    this.ocrService.dismissExtractedDataDialog();
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

  // formatDateForApi, toApiDate, parseApiDate, normalizeDateFormat → shared/utils/date-parsing

  /** Thin wrapper delegates to the shared `formatDateForDisplay` with instance context. */
  private displayDate(value: string | null | undefined): string {
    return formatDateForDisplay(
      value,
      angularFormatDate,
      this.configService.settings.dateFormat,
      this.locale,
    );
  }

  // ─── AI Document Categorization (delegated to catHandler) ────

  onCategorizationFilesSelected(files: File[]): void {
    this.catHandler.onFilesSelected(files);
  }

  onCategorizationFilesCleared(): void {
    this.catHandler.onFilesCleared();
  }

  startCategorization(): void {
    const app = this.application();
    if (!app) return;
    this.catHandler.start(app.id);
  }

  onApplyCategorization(mappings: CategorizationApplyMapping[]): void {
    this.catHandler.apply(mappings);
  }

  dismissSelectedCategorization(selectedKeys: string[]): void {
    this.catHandler.dismissSelected(selectedKeys);
  }

  dismissCategorization(): void {
    this.catHandler.dismiss();
  }
}
