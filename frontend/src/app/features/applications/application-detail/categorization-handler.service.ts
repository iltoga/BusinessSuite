import {
  DocumentCategorizationService,
  type CategorizationSseEvent,
  type CategorizationFileResult as ServiceFileResult,
} from '@/core/services/document-categorization.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { isCategorizationPipelineTerminal } from '@/core/utils/document-categorization-pipeline';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { HttpEventType } from '@angular/common/http';
import { inject, Injectable, signal } from '@angular/core';
import { Subject, Subscription } from 'rxjs';

import type {
  CategorizationApplyMapping,
  CategorizationFileResult,
} from './categorization-progress/categorization-progress.component';

/**
 * Encapsulates all AI document categorization state and logic.
 * Provided at component level — each ApplicationDetailComponent gets its own instance.
 */
@Injectable()
export class ApplicationCategorizationHandler {
  private readonly categorizationService = inject(DocumentCategorizationService);
  private readonly toast = inject(GlobalToastService);

  // ─── Public state ──────────────────────────────────────────────
  readonly isActive = signal(false);
  readonly jobId = signal<string | null>(null);
  readonly totalFiles = signal(0);
  readonly processedFiles = signal(0);
  readonly results = signal<CategorizationFileResult[]>([]);
  readonly isComplete = signal(false);
  readonly statusMessage = signal('');
  readonly progressPercentOverride = signal<number | null>(null);
  readonly isApplying = signal(false);
  readonly files = signal<File[]>([]);
  readonly lastActivitySummary = signal('');

  /** Parent should subscribe and reload the application when this fires. */
  readonly applicationReloadRequested = new Subject<void>();

  private sub: Subscription | null = null;

  // ─── File selection ────────────────────────────────────────────

  onFilesSelected(files: File[]): void {
    this.files.set(files);
  }

  onFilesCleared(): void {
    this.files.set([]);
  }

  // ─── Start categorization ─────────────────────────────────────

  start(appId: number): void {
    const files = this.files();
    if (files.length === 0) return;

    this.isActive.set(true);
    this.isComplete.set(false);
    this.results.set([]);
    this.processedFiles.set(0);
    this.progressPercentOverride.set(0);
    this.totalFiles.set(files.length);
    this.lastActivitySummary.set('');
    this.statusMessage.set(`Preparing upload (${files.length} file(s))...`);

    this.categorizationService.createCategorizationJob(appId, files.length).subscribe({
      next: (response) => {
        this.jobId.set(response.jobId);
        this.totalFiles.set(response.totalFiles || files.length);
        this.refreshStatusMessage(
          `Preparing upload (${response.totalFiles || files.length} file(s))...`,
        );
        this.watchJob(response.jobId);

        this.categorizationService.uploadFilesToJob(response.jobId, files).subscribe({
          next: (event) => {
            if (event.type === HttpEventType.UploadProgress) {
              const total = Number(event.total || 0);
              const loaded = Number(event.loaded || 0);
              if (total > 0) {
                const percent = Math.max(0, Math.min(100, Math.round((loaded / total) * 100)));
                this.progressPercentOverride.set(percent);
                this.refreshStatusMessage(`Uploading files... ${percent}%`);
              } else {
                this.refreshStatusMessage('Uploading files...');
              }
            } else if (event.type === HttpEventType.Response) {
              this.refreshStatusMessage('Upload complete — waiting for AI processing...');
            }
          },
          error: (error) => {
            this.toast.error(extractServerErrorMessage(error) || 'Failed while uploading files');
            this.dismiss();
          },
        });
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to initialize categorization');
        this.dismiss();
      },
    });
  }

  // ─── Apply / dismiss ──────────────────────────────────────────

  apply(mappings: CategorizationApplyMapping[]): void {
    const jobId = this.jobId();
    if (!jobId) return;

    const normalizedMappings = mappings.filter(
      (mapping) => typeof mapping.itemId === 'string' && mapping.itemId.trim().length > 0,
    );
    if (normalizedMappings.length === 0) {
      this.toast.error('No valid matched files to apply yet. Please wait a moment and retry.');
      return;
    }

    this.isApplying.set(true);

    this.categorizationService
      .applyResults(
        jobId,
        normalizedMappings.map((m) => ({ itemId: m.itemId, documentId: m.documentId })),
      )
      .subscribe({
        next: (response) => {
          this.isApplying.set(false);
          if (response.totalApplied > 0) {
            this.toast.success(`${response.totalApplied} document(s) applied successfully`);
            this.applicationReloadRequested.next();
          }
          if (response.totalErrors > 0) {
            this.toast.error(`${response.totalErrors} document(s) failed to apply`);
          }
          this.dismiss();
        },
        error: (error) => {
          this.isApplying.set(false);
          this.toast.error(extractServerErrorMessage(error) || 'Failed to apply categorization');
        },
      });
  }

  dismissSelected(selectedKeys: string[]): void {
    if (!selectedKeys || selectedKeys.length === 0) return;

    const current = this.results();
    const selectedKeySet = new Set(selectedKeys);
    const remaining = current.filter(
      (result, index) => !selectedKeySet.has(this.getResultKey(result, index)),
    );
    const dismissedCount = current.length - remaining.length;

    if (dismissedCount <= 0) return;

    this.results.set(remaining);
    this.toast.success(`${dismissedCount} document(s) dismissed`);

    if (remaining.length === 0) {
      this.dismiss();
    }
  }

  dismiss(): void {
    this.sub?.unsubscribe();
    this.sub = null;
    this.isActive.set(false);
    this.jobId.set(null);
    this.totalFiles.set(0);
    this.processedFiles.set(0);
    this.results.set([]);
    this.isComplete.set(false);
    this.statusMessage.set('');
    this.progressPercentOverride.set(null);
    this.files.set([]);
  }

  /** Call from the parent component's onDestroy to clean up subscriptions. */
  destroy(): void {
    this.sub?.unsubscribe();
    this.sub = null;
  }

  // ─── SSE watcher ──────────────────────────────────────────────

  private watchJob(jobId: string): void {
    this.sub?.unsubscribe();

    this.sub = this.categorizationService.watchCategorizationJob(jobId).subscribe({
      next: (event: CategorizationSseEvent) => this.handleEvent(event),
      error: () => {
        this.statusMessage.set('Connection lost. Waiting for the final pipeline state.');
        this.maybeFinalizeFromClientState();
      },
      complete: () => {
        this.maybeFinalizeFromClientState();
      },
    });
  }

  // ─── Event handler ────────────────────────────────────────────

  handleEvent(event: CategorizationSseEvent): void {
    switch (event.type) {
      case 'start':
        this.progressPercentOverride.set(0);
        this.processedFiles.set(0);
        this.refreshStatusMessage(
          `Starting categorization for ${this.totalFiles() || 0} file(s)...`,
        );
        break;

      case 'progress': {
        const totalFiles = Number(event.data['totalFiles'] ?? this.totalFiles() ?? 0);
        const processedFiles = Number(event.data['processedFiles'] ?? this.processedFiles() ?? 0);
        const overallPercent = Number(
          event.data['overallPercent'] ?? this.progressPercentOverride() ?? 0,
        );

        if (totalFiles > 0) this.totalFiles.set(totalFiles);
        if (processedFiles >= 0) this.processedFiles.set(processedFiles);
        if (Number.isFinite(overallPercent)) {
          this.progressPercentOverride.set(Math.max(0, Math.min(100, Math.round(overallPercent))));
        }

        const phase = String(event.data['phase'] ?? '').toLowerCase();
        const phaseFallback =
          phase === 'uploading'
            ? `Uploading ${processedFiles}/${totalFiles} files...`
            : phase === 'completed'
              ? 'Processing complete'
              : `Processing ${processedFiles}/${totalFiles} files...`;
        this.refreshStatusMessage(phaseFallback);
        break;
      }

      case 'file_upload_start': {
        const filename = event.data['filename'] ?? '';
        if (!filename) break;

        this.statusMessage.set(`Uploading: "${truncateFilename(filename)}"...`);
        const current = [...this.results()];
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
          validationProvider: null,
          validationProviderName: null,
          validationModel: null,
        };
        if (idx >= 0) {
          current[idx] = { ...current[idx], ...next };
        } else {
          current.push(next);
        }
        this.results.set(current);
        this.refreshStatusMessage();
        break;
      }

      case 'file_uploaded': {
        const filename = event.data['filename'] ?? '';
        if (!filename) break;

        this.statusMessage.set(`Queued: "${truncateFilename(filename)}" — waiting to process...`);
        const current = [...this.results()];
        const idx = current.findIndex((r) => r.filename === filename);
        if (idx >= 0) {
          current[idx] = { ...current[idx], status: 'queued', pipelineStage: 'uploaded' };
          this.results.set(current);
        }
        this.refreshStatusMessage();
        break;
      }

      case 'upload_progress': {
        const uploadedFiles = Number(event.data['uploadedFiles'] ?? 0);
        const totalFiles = Number(event.data['totalFiles'] ?? this.totalFiles() ?? 0);
        const uploadedBytes = Number(event.data['uploadedBytes'] ?? 0);
        const totalBytes = Number(event.data['totalBytes'] ?? 0);

        if (totalFiles > 0) {
          this.totalFiles.set(totalFiles);
          this.processedFiles.set(Math.min(uploadedFiles, totalFiles));
        }

        if (totalBytes > 0) {
          const percent = Math.max(
            0,
            Math.min(100, Math.round((uploadedBytes / totalBytes) * 100)),
          );
          this.progressPercentOverride.set(percent);
        }

        const currentFile =
          typeof event.data['currentFile'] === 'string' ? event.data['currentFile'] : null;
        this.refreshStatusMessage(
          currentFile
            ? `Uploading: "${truncateFilename(currentFile)}" (${uploadedFiles}/${totalFiles})`
            : `Uploading files... ${uploadedFiles}/${totalFiles}`,
        );
        break;
      }

      case 'upload_complete':
        this.refreshStatusMessage('Upload complete — waiting for AI processing...');
        break;

      case 'file_start': {
        const fileIndex = (event.data['index'] ?? 0) + 1;
        const fileTotal = this.totalFiles();
        const startFilename = event.data['filename']
          ? `"${truncateFilename(event.data['filename'])}" `
          : '';
        const fileStartMsg = `Categorizing: ${startFilename}(${fileIndex} of ${fileTotal})...`;
        this.lastActivitySummary.set(fileStartMsg);
        this.statusMessage.set(fileStartMsg);

        if (event.data['filename']) {
          const current = this.results();
          const exists = current.some((r) => r.filename === event.data['filename']);
          if (!exists) {
            this.results.set([
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
                validationProvider: null,
                validationProviderName: null,
                validationModel: null,
              },
            ]);
          } else {
            const current2 = this.results();
            const idx = current2.findIndex((r) => r.filename === event.data['filename']);
            if (idx >= 0) {
              const updated = [...current2];
              updated[idx] = {
                ...updated[idx],
                status: 'processing',
                pipelineStage: 'categorizing',
              };
              this.results.set(updated);
            }
          }
        }
        this.refreshStatusMessage();
        break;
      }

      case 'file_categorized': {
        this.processedFiles.update((v) => v + 1);
        const results = [...this.results()];
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
          validationProvider: null,
          validationProviderName: null,
          validationModel: null,
        };
        if (idx >= 0) {
          results[idx] = result;
        } else {
          results.push(result);
        }
        this.results.set(results);

        const catFilename = event.data['filename']
          ? `"${truncateFilename(event.data['filename'])}"`
          : 'file';
        const catDocType = event.data['documentType'] ? ` → ${event.data['documentType']}` : '';
        this.lastActivitySummary.set(`Categorized: ${catFilename}${catDocType}`);
        this.refreshStatusMessage();
        break;
      }

      case 'file_error': {
        this.processedFiles.update((v) => v + 1);
        const results = [...this.results()];
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
          validationProvider: null,
          validationProviderName: null,
          validationModel: null,
        };
        if (idx >= 0) {
          results[idx] = errorResult;
        } else {
          results.push(errorResult);
        }
        this.results.set(results);

        if (event.data['filename']) {
          const errFilename = `"${truncateFilename(event.data['filename'])}"`;
          const errMsg = event.data['error'] ? `: ${event.data['error']}` : '';
          this.lastActivitySummary.set(`Error on: ${errFilename}${errMsg}`);
        }
        this.refreshStatusMessage();
        break;
      }

      case 'file_categorizing_pass2': {
        const results = [...this.results()];
        const idx = results.findIndex((r) => r.filename === event.data['filename']);
        if (idx >= 0) {
          results[idx] = { ...results[idx], categorizationPass: 2 };
          this.results.set(results);
        }
        if (event.data['filename']) {
          const pass2Filename = `"${truncateFilename(event.data['filename'])}"`;
          this.lastActivitySummary.set(`Re-analyzing: ${pass2Filename} — high-tier model...`);
        }
        this.refreshStatusMessage();
        break;
      }

      case 'file_validating': {
        const results = [...this.results()];
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
          this.results.set(results);
        }
        if (event.data['filename']) {
          const valFilename = `"${truncateFilename(event.data['filename'])}"`;
          this.lastActivitySummary.set(`Validating: ${valFilename}...`);
        }
        this.refreshStatusMessage();
        break;
      }

      case 'file_validated': {
        const results = [...this.results()];
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
            validationProvider: event.data['validationProvider'] ?? null,
            validationProviderName: event.data['validationProviderName'] ?? null,
            validationModel: event.data['validationModel'] ?? null,
          };
          this.results.set(results);
        }
        if (event.data['filename']) {
          const validFilename = `"${truncateFilename(event.data['filename'])}"`;
          const valStatus = event.data['validationStatus'];
          const valLabel =
            valStatus === 'valid' ? '✓ valid' : valStatus === 'invalid' ? '✗ invalid' : 'checked';
          this.lastActivitySummary.set(`Validated: ${validFilename} — ${valLabel}`);
        }
        this.refreshStatusMessage();
        break;
      }

      case 'complete': {
        this.isComplete.set(true);
        this.progressPercentOverride.set(100);
        this.processedFiles.set(this.totalFiles());

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
            validationProvider: r.validationProvider ?? null,
            validationProviderName: r.validationProviderName ?? null,
            validationModel: r.validationModel ?? null,
          }));
          this.results.set(finalResults);
        }

        const finalResults = this.results();
        const matchedCount = finalResults.filter(
          (r) => r.status === 'categorized' && !!r.documentId,
        ).length;
        const noSlotCount = finalResults.filter(
          (r) => r.status === 'categorized' && !r.documentId,
        ).length;
        const errorCount = finalResults.filter((r) => r.status === 'error').length;
        const invalidCount = finalResults.filter((r) => r.validationStatus === 'invalid').length;
        const validationErrorCount = finalResults.filter(
          (r) => r.validationStatus === 'error',
        ).length;

        const summaryParts = [`${matchedCount} matched`];
        if (noSlotCount > 0) summaryParts.push(`${noSlotCount} no slot`);
        if (invalidCount > 0) summaryParts.push(`${invalidCount} invalid`);
        if (validationErrorCount > 0) summaryParts.push(`${validationErrorCount} validation error`);
        if (errorCount > 0) summaryParts.push(`${errorCount} error${errorCount === 1 ? '' : 's'}`);

        const summaryMessage = `Processing complete — ${summaryParts.join(', ')}`;
        this.lastActivitySummary.set(summaryMessage);
        this.statusMessage.set(summaryMessage);
        break;
      }
    }

    this.maybeFinalizeFromClientState();
  }

  // ─── Status message logic ─────────────────────────────────────

  private refreshStatusMessage(fallback?: string): void {
    if (this.isComplete()) {
      const summary =
        this.lastActivitySummary().trim() || fallback?.trim() || 'Processing complete';
      this.statusMessage.set(summary);
      return;
    }

    const results = this.results();

    const uploading = results.filter((r) => r.pipelineStage === 'uploading').map((r) => r.filename);
    if (uploading.length > 0) {
      this.statusMessage.set(buildStageMessage('Uploading', uploading));
      return;
    }

    const reanalyzing = results
      .filter((r) => r.pipelineStage === 'categorizing' && (r.categorizationPass ?? 1) > 1)
      .map((r) => r.filename);
    if (reanalyzing.length > 0) {
      this.statusMessage.set(buildStageMessage('Re-analyzing', reanalyzing));
      return;
    }

    const validating = results
      .filter((r) => r.pipelineStage === 'validating')
      .map((r) => r.filename);
    if (validating.length > 0) {
      this.statusMessage.set(buildStageMessage('Validating', validating));
      return;
    }

    const categorizing = results
      .filter((r) => r.pipelineStage === 'categorizing')
      .map((r) => r.filename);
    if (categorizing.length > 0) {
      this.statusMessage.set(buildStageMessage('Categorizing', categorizing));
      return;
    }

    const queued = results
      .filter((r) => r.pipelineStage === 'uploaded' || r.status === 'queued')
      .map((r) => r.filename);
    if (queued.length > 0) {
      this.statusMessage.set(buildStageMessage('Queued', queued, ' — waiting to process'));
      return;
    }

    // Prefer last meaningful activity over generic progress fallback
    const lastActivity = this.lastActivitySummary().trim();
    if (lastActivity) {
      this.statusMessage.set(lastActivity);
      return;
    }

    const fallbackMessage = fallback?.trim();
    if (fallbackMessage) {
      this.statusMessage.set(fallbackMessage);
      return;
    }

    const totalFiles = this.totalFiles();
    if (totalFiles > 0) {
      this.statusMessage.set(`Processing ${this.processedFiles()} / ${totalFiles} files...`);
    }
  }

  private maybeFinalizeFromClientState(): void {
    if (this.isComplete()) return;

    const total = this.totalFiles();
    const results = this.results();
    if (total <= 0 || results.length < total) return;
    if (!results.every((r) => isCategorizationPipelineTerminal(r))) return;

    this.isComplete.set(true);
    this.processedFiles.set(total);
    this.progressPercentOverride.set(100);
    const currentMessage = this.statusMessage().trim();
    if (
      !currentMessage ||
      /processing|categorizing|validating|uploading|connection lost/i.test(currentMessage)
    ) {
      this.statusMessage.set('Processing complete');
    }
  }

  private getResultKey(result: CategorizationFileResult, index: number): string {
    return result.itemId || `${result.filename}-${index}`;
  }
}

// ─── Reusable utilities ─────────────────────────────────────────

export function truncateFilename(filename: string, maxLen = 28): string {
  if (filename.length <= maxLen) return filename;
  const dotIdx = filename.lastIndexOf('.');
  const ext = dotIdx > 0 ? filename.slice(dotIdx) : '';
  const keepLen = maxLen - ext.length - 3;
  return keepLen > 4 ? `${filename.slice(0, keepLen)}...${ext}` : filename.slice(0, maxLen);
}

export function formatCategorizationFilenames(filenames: string[]): string {
  const normalized = [...new Set(filenames.filter(Boolean).map((f) => truncateFilename(f)))];
  if (normalized.length === 0) return '';
  if (normalized.length === 1) return `"${normalized[0]}"`;
  const shown = normalized
    .slice(0, 2)
    .map((f) => `"${f}"`)
    .join(', ');
  const remaining = normalized.length - 2;
  return remaining > 0 ? `${shown} +${remaining} more` : shown;
}

export function buildStageMessage(label: string, filenames: string[], suffix = '...'): string {
  const fileList = formatCategorizationFilenames(filenames);
  if (!fileList) return `${label}${suffix}`;
  if (filenames.length === 1) return `${label}: ${fileList}${suffix}`;
  return `${label} ${filenames.length} files: ${fileList}${suffix}`;
}
