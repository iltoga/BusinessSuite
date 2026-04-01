import { isPlatformBrowser } from '@angular/common';
import {
  computed,
  effect,
  inject,
  Injectable,
  isDevMode,
  PLATFORM_ID,
  signal,
  untracked,
  type Signal,
} from '@angular/core';

import { CdkDragDrop, moveItemInArray } from '@angular/cdk/drag-drop';

import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
  type DocumentAction,
} from '@/core/services/applications.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  getDocumentAiValidationBadge,
  type PipelineBadgeState,
} from '@/core/utils/document-categorization-pipeline';
import { ZardDialogService } from '@/shared/components/dialog';
import {
  DocumentViewDialogContentComponent,
  type DocumentViewDialogData,
} from '@/shared/components/document-view-dialog';
import { formatDateForApi, parseApiDate } from '@/shared/utils/date-parsing';
import { downloadBlob } from '@/shared/utils/file-download';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { catchError, forkJoin, of } from 'rxjs';

import type { CategorizationFileResult } from './categorization-progress/categorization-progress.component';
import { DocumentUploadService } from './document-upload.service';

/**
 * Callbacks the parent component provides so the service can read / mutate
 * shared state it does not own.
 */
export interface DocumentCollectionHost {
  application: Signal<ApplicationDetail | null>;
  categorizationResults: Signal<CategorizationFileResult[]>;
  isDevelopmentMode: boolean;
  replaceDocument(updated: ApplicationDocument): void;
  displayDate(value: string | null | undefined): string;
}

/**
 * Encapsulates document-collection state and logic:
 * document lists (uploaded/required/optional), selection, PDF merge,
 * auto-generation, document-action execution, AI validation badges,
 * and expiration state.
 *
 * Provided at component level — each ApplicationDetailComponent gets its own instance.
 */
@Injectable()
export class DocumentCollectionService {
  private readonly applicationsService = inject(ApplicationsService);
  private readonly documentsService = inject(DocumentsService);
  private readonly toast = inject(GlobalToastService);
  private readonly dialogService = inject(ZardDialogService);
  private readonly uploadService = inject(DocumentUploadService);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  readonly isDevelopmentMode = isDevMode();

  private host!: DocumentCollectionHost;

  // ─── Document list computed signals ────────────────────────

  readonly uploadedDocuments = computed(() =>
    (this.host?.application()?.documents ?? []).filter((doc) => doc.completed),
  );

  readonly requiredDocuments = computed(() =>
    (this.host?.application()?.documents ?? []).filter((doc) => doc.required && !doc.completed),
  );

  readonly optionalDocuments = computed(() =>
    (this.host?.application()?.documents ?? []).filter((doc) => !doc.required && !doc.completed),
  );

  readonly documentCollectionStatus = computed<{
    label:
      | 'Document Collection Pending'
      | 'Document Collection Incomplete'
      | 'Document Collection Complete';
    type: 'default' | 'secondary' | 'warning' | 'success' | 'destructive';
  }>(() => {
    const documents = this.host?.application()?.documents ?? [];
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

  // ─── Selection & ordering state ────────────────────────────

  readonly actionLoading = signal<string | null>(null);
  readonly isAutoGeneratingAll = signal(false);
  readonly localUploadedDocuments = signal<ApplicationDocument[]>([]);
  readonly selectedDocumentIds = signal<Set<number>>(new Set());
  readonly isMerging = signal(false);

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

  readonly canAutoGenerateAnyDocuments = computed(() => {
    const docs = [...this.requiredDocuments(), ...this.optionalDocuments()];
    return docs.some((doc) => this.canShowAutomaticShortcut(doc));
  });

  constructor() {
    // Keep localUploadedDocuments in sync with the computed uploadedDocuments list.
    // Preserves local ordering while refreshing document payloads (badges, metadata).
    effect(() => {
      const docs = this.uploadedDocuments();
      untracked(() => {
        if (!this.host) return;
        const current = this.localUploadedDocuments();

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

  init(host: DocumentCollectionHost): void {
    this.host = host;
  }

  // ─── Selection ─────────────────────────────────────────────

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

  // ─── PDF merge ─────────────────────────────────────────────

  mergeAndDownloadSelected(): void {
    const selectedIds = this.selectedDocumentIds();
    if (selectedIds.size < 1) {
      this.toast.error('Select at least one document to merge');
      return;
    }

    const orderedIds = this.localUploadedDocuments()
      .filter((d) => selectedIds.has(d.id))
      .map((d) => d.id);

    this.isMerging.set(true);
    this.documentsService.mergePdf(orderedIds).subscribe({
      next: (blob: Blob) => {
        const app = this.host.application();
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

  // ─── Auto-generation ──────────────────────────────────────

  canShowAutomaticShortcut(doc: ApplicationDocument): boolean {
    return this.getAutomaticShortcutAction(doc) !== null;
  }

  getAutomaticShortcutLabel(doc: ApplicationDocument): string {
    return this.getAutomaticShortcutAction(doc)?.label ?? 'Run automatic document action';
  }

  getAutomaticShortcutTooltip(doc: ApplicationDocument): string {
    const action = this.getAutomaticShortcutAction(doc);
    if (!action) {
      return '';
    }
    return `${action.label} without opening the upload dialog`;
  }

  runAutomaticShortcut(doc: ApplicationDocument): void {
    const action = this.getAutomaticShortcutAction(doc);
    if (!action) {
      return;
    }
    this.executeDocumentAction(action, doc);
  }

  autoGenerateAllDocuments(): void {
    const docs = [...this.requiredDocuments(), ...this.optionalDocuments()].filter((doc) =>
      this.canShowAutomaticShortcut(doc),
    );
    if (docs.length === 0) return;

    this.isAutoGeneratingAll.set(true);

    const requests = docs.map((doc) => {
      const action = this.getAutomaticShortcutAction(doc);
      if (!action) return of(null);
      return this.applicationsService
        .executeDocumentAction(doc.id, action.name)
        .pipe(catchError((error) => of({ success: false, error, document: undefined })));
    });

    forkJoin(requests).subscribe({
      next: (results) => {
        let successCount = 0;
        let errorCount = 0;

        results.forEach((res) => {
          if (res && 'success' in res && res.success) {
            successCount++;
            if (res.document) {
              this.host.replaceDocument(res.document);
            }
          } else if (res) {
            errorCount++;
          }
        });

        if (successCount > 0 && errorCount === 0) {
          this.toast.success(
            `Successfully started auto-generation for ${successCount} document(s)`,
          );
        } else if (successCount > 0) {
          this.toast.error(
            `Started auto-generation for ${successCount} document(s), but ${errorCount} failed`,
          );
        } else if (errorCount > 0) {
          this.toast.error('Failed to auto-generate documents');
        }

        this.isAutoGeneratingAll.set(false);
      },
      error: () => {
        this.toast.error('An unexpected error occurred during auto-generation');
        this.isAutoGeneratingAll.set(false);
      },
    });
  }

  isAutomaticShortcutLoading(doc: ApplicationDocument): boolean {
    const actionName = this.getAutomaticShortcutAction(doc)?.name;
    if (!actionName) return false;

    if (this.isAutoGeneratingAll()) {
      return true;
    }

    return this.isActionLoadingFor(doc, actionName);
  }

  isActionLoadingFor(doc: ApplicationDocument, actionName: string): boolean {
    return this.actionLoading() === this.buildActionLoadingKey(doc.id, actionName);
  }

  // ─── Document action execution ─────────────────────────────

  executeAction(action: DocumentAction): void {
    this.executeDocumentAction(action);
  }

  executeDocumentAction(
    action: DocumentAction,
    documentOverride?: ApplicationDocument | null,
  ): void {
    const document = documentOverride ?? this.uploadService.selectedDocument();
    if (!document) {
      return;
    }

    this.actionLoading.set(this.buildActionLoadingKey(document.id, action.name));

    this.applicationsService.executeDocumentAction(document.id, action.name).subscribe({
      next: (response) => {
        if (response.success) {
          this.toast.success(response.message ?? 'Action completed successfully');
          if (response.document) {
            this.host.replaceDocument(response.document);
            // Keep modal state in sync with the updated document returned by action hooks.
            this.uploadService.selectedDocument.set(response.document);
            this.uploadService.selectedFile.set(null);
            this.uploadService.clearUploadPreview();
            this.uploadService.loadExistingDocumentPreview(response.document);
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

  // ─── Document viewing ──────────────────────────────────────

  viewDocument(doc: ApplicationDocument): void {
    if (!this.isBrowser) return;
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

  isFileOnlyDocument(doc: ApplicationDocument): boolean {
    return !!doc.fileLink && !this.hasDocumentTextFields(doc);
  }

  hasDocumentTextFields(doc: ApplicationDocument): boolean {
    return !!doc.docNumber || !!doc.expirationDate || !!doc.details;
  }

  hasViewableContent(doc: ApplicationDocument): boolean {
    return !!doc.fileLink || this.hasDocumentTextFields(doc);
  }

  openDocumentViewDialog(doc: ApplicationDocument): void {
    const data: DocumentViewDialogData = { document: doc };
    const hasFile = !!doc.fileLink;
    const width = hasFile ? '720px' : '500px';
    const maxW = hasFile ? 'max-w-[720px] sm:max-w-[720px]' : 'max-w-[500px] sm:max-w-[500px]';
    this.dialogService.create({
      zTitle: doc.docType.name,
      zContent: DocumentViewDialogContentComponent,
      zData: data,
      zHideFooter: true,
      zClosable: true,
      zWidth: width,
      zCustomClasses: maxW,
    });
  }

  // ─── AI validation badges & expiration ─────────────────────

  getUploadedDocumentRowClass(doc: ApplicationDocument): Record<string, boolean> {
    const expirationState = this.getDocumentExpirationState(doc);
    return {
      'uploaded-doc-row-expired': expirationState === 'expired',
      'uploaded-doc-row-expiring': expirationState === 'expiring',
    };
  }

  isDocumentAiValid(doc: ApplicationDocument): boolean {
    return (
      this.getDocumentAiCheckBadge(doc)?.label === 'Valid' &&
      this.getDocumentExpirationState(doc) === 'ok'
    );
  }

  isDocumentAiInvalid(doc: ApplicationDocument): boolean {
    const badge = this.getDocumentAiCheckBadge(doc);
    return (
      badge?.label === 'Invalid' ||
      badge?.label === 'Error' ||
      this.getDocumentExpirationState(doc) !== 'ok'
    );
  }

  getDocumentAiCheckBadge(doc: ApplicationDocument): PipelineBadgeState | null {
    return getDocumentAiValidationBadge(doc, this.getActiveCategorizationResultForDocument(doc.id));
  }

  getDocumentValidationTooltip(doc: ApplicationDocument): string {
    const activePipelineResult = this.getActiveCategorizationResultForDocument(doc.id);
    if (
      activePipelineResult?.validationStatus === 'invalid' ||
      activePipelineResult?.validationStatus === 'error'
    ) {
      const details = [
        activePipelineResult.validationReasoning ?? '',
        ...(activePipelineResult.validationNegativeIssues ?? []),
      ]
        .map((entry) => entry.trim())
        .filter(Boolean);
      const runtimeLabel = this.uploadService.formatAiRuntimeLabel(
        activePipelineResult.validationProviderName ?? null,
        activePipelineResult.validationProvider ?? null,
        activePipelineResult.validationModel ?? null,
      );
      if (!this.host.isDevelopmentMode || !runtimeLabel) {
        return details.join('\n');
      }
      return details.length > 0
        ? `${details.join('\n')}\nAI runtime: ${runtimeLabel}`
        : `AI runtime: ${runtimeLabel}`;
    }

    if (!this.isDocumentAiInvalid(doc)) {
      return '';
    }
    const expirationReason = this.getDocumentExpirationReason(doc);
    const fallbackReasoning = String(doc.aiValidationResult?.['reasoning'] ?? '');
    const baseMessage = expirationReason || fallbackReasoning;
    if (!this.host.isDevelopmentMode) {
      return baseMessage;
    }

    const runtime = this.uploadService.extractValidationRuntimeMetadata(
      doc.aiValidationResult ?? null,
    );
    const runtimeLabel = this.uploadService.formatAiRuntimeLabel(
      runtime.providerName,
      runtime.provider,
      runtime.model,
    );
    if (!runtimeLabel) {
      return baseMessage;
    }
    return baseMessage
      ? `${baseMessage}\nAI runtime: ${runtimeLabel}`
      : `AI runtime: ${runtimeLabel}`;
  }

  // ─── Private helpers ───────────────────────────────────────

  private getAutomaticShortcutAction(doc: ApplicationDocument): DocumentAction | null {
    if (!doc.docType?.autoGeneration) {
      return null;
    }

    const actions = doc.extraActions ?? [];
    if (actions.length === 0) {
      return null;
    }

    const preferredNames = ['auto_generate', 'upload_default'];
    for (const name of preferredNames) {
      const match = actions.find((action) => action.name === name);
      if (match) {
        return match;
      }
    }

    return actions[0] ?? null;
  }

  private buildActionLoadingKey(documentId: number, actionName: string): string {
    return `${documentId}:${actionName}`;
  }

  private getActiveCategorizationResultForDocument(
    documentId: number,
  ): CategorizationFileResult | null {
    return (
      this.host.categorizationResults().find((result) => result.documentId === documentId) ?? null
    );
  }

  private getDocumentExpirationState(doc: ApplicationDocument): 'ok' | 'expiring' | 'expired' {
    const metadataState = String(doc.aiValidationResult?.['expiration_state'] ?? '').toLowerCase();
    if (metadataState === 'expired' || metadataState === 'expiring' || metadataState === 'ok') {
      return metadataState;
    }

    if (!doc.docType?.hasExpirationDate) {
      return 'ok';
    }

    const expirationDate = parseApiDate(doc.expirationDate);
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

    const expirationDate = parseApiDate(doc.expirationDate);
    if (!expirationDate) {
      return '';
    }

    if (expirationState === 'expired') {
      return `Document expired on ${this.host.displayDate(formatDateForApi(expirationDate))}.`;
    }

    const thresholdRaw = Number(doc.docType?.expiringThresholdDays ?? 0);
    const thresholdDays = Number.isFinite(thresholdRaw) ? Math.max(0, thresholdRaw) : 0;
    return (
      'Document is expiring soon: expiration date ' +
      `${this.host.displayDate(formatDateForApi(expirationDate))} is within ${thresholdDays} days.`
    );
  }
}
