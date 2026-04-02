import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { catchError, EMPTY, finalize, Subscription } from 'rxjs';

import { ServerManagementService } from '@/core/api';
import {
  DesktopBridgeService,
  DesktopRuntimeStatus,
  DesktopSyncStatus,
  DesktopVaultStatus,
} from '@/core/services/desktop-bridge.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { createAsyncRequestMetadata } from '@/core/utils/request-metadata';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { ServerManagementAiWorkflowComponent } from './server-management-ai-workflow.component';
import { ServerManagementAiWorkflowFacade } from './server-management-ai-workflow.facade';
import {
  AiModelDefinition,
  AiModelProviderCatalog,
  AiProviderModelOption,
  AiWorkflowFailoverProvider,
  AiWorkflowFeature,
} from './server-management-ai-workflow.models';
import {
  MediaCleanupStreamEvent,
  ServerManagementMediaCleanupStreamService,
} from './server-management-media-cleanup-stream.service';
import {
  CacheHealthResponse,
  CacheStatusResponse,
  LocalResilienceSettingsResponse,
  MediaCleanupFile,
  MediaCleanupResult,
  MediaDiagnosticResult,
  normalizeCacheHealth,
  normalizeCacheStatus,
  normalizeLocalResilience,
  normalizeMediaCleanupFile,
  normalizeMediaCleanupResult,
  normalizeMediaDiagnosticResponse,
  normalizeMediaRepairResponse,
  normalizeServerActionResponse,
  normalizeUiSettings,
  normalizeVaultResetResponse,
  ServerActionResponse,
  ServerSettings,
  toOptionalNumber,
  toOptionalString,
  UiSettingsResponse,
} from './server-management-normalizers';

type ServerActionName = 'clearCache' | 'mediaDiagnostic' | 'mediaRepair' | 'mediaCleanup';

@Component({
  selector: 'app-server-management',
  standalone: true,
  imports: [
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    ServerManagementAiWorkflowComponent,
    ...ZardTooltipImports,
  ],
  templateUrl: './server-management.component.html',
  styleUrls: ['./server-management.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerManagementComponent implements OnInit, OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly serverManagementApi = inject(ServerManagementService);
  private readonly mediaCleanupStream = inject(ServerManagementMediaCleanupStreamService);
  private readonly desktopBridge = inject(DesktopBridgeService);
  private readonly toast = inject(GlobalToastService);
  private readonly aiWorkflowFacade = inject(ServerManagementAiWorkflowFacade);
  private mediaCleanupSubscription: Subscription | null = null;

  readonly isLoading = signal(false);
  readonly activeServerAction = signal<ServerActionName | null>(null);
  readonly diagnosticResults = signal<MediaDiagnosticResult[]>([]);
  readonly repairResults = signal<string[]>([]);
  readonly cleanupDryRun = signal(true);
  readonly cleanupResult = signal<MediaCleanupResult | null>(null);
  readonly serverSettings = signal<ServerSettings | null>(null);

  // Cache management state
  readonly cacheStatus = signal<CacheStatusResponse | null>(null);
  readonly cacheLoading = signal(false);
  readonly cacheHealth = signal<CacheHealthResponse | null>(null);
  readonly cacheHealthLoading = signal(false);
  readonly localResilience = signal<LocalResilienceSettingsResponse | null>(null);
  readonly localResilienceLoading = signal(false);
  readonly localResilienceSaving = signal(false);
  readonly uiSettings = signal<UiSettingsResponse | null>(null);
  readonly uiSettingsLoading = signal(false);
  readonly uiSettingsSaving = signal(false);
  readonly aiWorkflowStatus = this.aiWorkflowFacade.aiWorkflowStatus;
  readonly aiWorkflowLoading = this.aiWorkflowFacade.aiWorkflowLoading;
  readonly aiWorkflowSaving = this.aiWorkflowFacade.aiWorkflowSaving;
  readonly aiWorkflowDraft = this.aiWorkflowFacade.aiWorkflowDraft;
  readonly isDesktop = signal(false);
  readonly desktopRuntimeStatus = signal<DesktopRuntimeStatus | null>(null);
  readonly desktopSyncStatus = signal<DesktopSyncStatus | null>(null);
  readonly desktopVaultStatus = signal<DesktopVaultStatus | null>(null);
  readonly desktopVaultPassphrase = signal('');
  readonly desktopRuntimeLoading = signal(false);
  readonly desktopVaultLoading = signal(false);
  readonly aiModelTypeaheadPageSize = this.aiWorkflowFacade.aiModelTypeaheadPageSize;

  readonly missingFilesCount = computed(
    () => this.diagnosticResults().filter((r) => !r.exists).length,
  );

  readonly discrepancyCount = computed(
    () => this.diagnosticResults().filter((r) => r.discrepancy).length,
  );

  readonly allProviderModelLoader = this.aiWorkflowFacade.allProviderModelLoader;
  readonly openrouterModelLoader = this.aiWorkflowFacade.openrouterModelLoader;
  readonly openaiModelLoader = this.aiWorkflowFacade.openaiModelLoader;
  readonly groqModelLoader = this.aiWorkflowFacade.groqModelLoader;

  ngOnInit(): void {
    this.isDesktop.set(isPlatformBrowser(this.platformId) && this.desktopBridge.isDesktop());
    this.loadCacheStatus();
    this.loadCacheHealth();
    this.loadLocalResilience();
    this.loadUiSettings();
    this.loadAiWorkflowStatus();
    void this.loadDesktopResilienceState();
  }

  ngOnDestroy(): void {
    this.stopMediaCleanupStream();
  }

  clearCache(): void {
    this.startServerAction('clearCache');
    this.isLoading.set(true);
    this.serverManagementApi
      .serverManagementClearCacheCreate({})
      .pipe(
        catchError(() => {
          this.toast.error('Failed to clear cache');
          return EMPTY;
        }),
        finalize(() => this.finishServerAction('clearCache')),
      )
      .subscribe((response) => {
        const normalized = normalizeServerActionResponse(response);
        if (normalized.ok) {
          this.toast.success(normalized.message || 'Cache cleared successfully');
          this.loadCacheHealth();
        } else {
          this.toast.error(normalized.message || 'Failed to clear cache');
        }
      });
  }

  loadCacheStatus(): void {
    this.cacheLoading.set(true);
    this.serverManagementApi
      .serverManagementCacheStatusRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load cache status');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        this.cacheStatus.set(normalizeCacheStatus(response));
      });
  }

  toggleCache(): void {
    const currentStatus = this.cacheStatus();
    if (!currentStatus) {
      this.toast.error('Cache status not loaded');
      return;
    }

    this.cacheLoading.set(true);

    (currentStatus.enabled
      ? this.serverManagementApi.serverManagementCacheDisableCreate()
      : this.serverManagementApi.serverManagementCacheEnableCreate()
    )
      .pipe(
        catchError(() => {
          this.toast.error(`Failed to ${currentStatus.enabled ? 'disable' : 'enable'} cache`);
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = normalizeCacheStatus(response);
        this.cacheStatus.set(normalized);
        this.toast.success(normalized.message);
        this.loadCacheHealth();
      });
  }

  clearAllCache(): void {
    this.cacheLoading.set(true);
    this.serverManagementApi
      .serverManagementClearCacheCreate({})
      .pipe(
        catchError(() => {
          this.toast.error('Failed to clear cache');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = normalizeServerActionResponse(response);
        if (normalized.ok) {
          this.toast.success(normalized.message || 'Cache cleared');
        } else {
          this.toast.error(normalized.message || 'Failed to clear cache');
        }
        // Update cache status after clearing
        this.loadCacheStatus();
        this.loadCacheHealth();
      });
  }

  runCacheHealthCheck(): void {
    this.loadCacheHealth(true);
  }

  loadLocalResilience(): void {
    this.localResilienceLoading.set(true);
    this.serverManagementApi
      .serverManagementLocalResilienceRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load local resilience settings');
          return EMPTY;
        }),
        finalize(() => this.localResilienceLoading.set(false)),
      )
      .subscribe((response) => {
        this.localResilience.set(normalizeLocalResilience(response));
      });
  }

  toggleLocalResilience(): void {
    const current = this.localResilience();
    if (!current || this.localResilienceSaving()) {
      return;
    }

    this.localResilienceSaving.set(true);
    this.serverManagementApi
      .serverManagementLocalResiliencePartialUpdate({
        requestBody: {
          enabled: !current.enabled,
        },
      })
      .pipe(
        catchError(() => {
          this.toast.error('Failed to update local resilience setting');
          return EMPTY;
        }),
        finalize(() => this.localResilienceSaving.set(false)),
      )
      .subscribe((response) => {
        const normalized = normalizeLocalResilience(response);
        this.localResilience.set(normalized);
        this.toast.success(
          normalized.enabled ? 'Local resilience enabled' : 'Local resilience disabled',
        );
      });
  }

  resetLocalVault(): void {
    if (this.localResilienceSaving()) {
      return;
    }

    this.localResilienceSaving.set(true);
    this.serverManagementApi
      .serverManagementLocalResilienceResetVaultCreate()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to reset local media vault');
          return EMPTY;
        }),
        finalize(() => this.localResilienceSaving.set(false)),
      )
      .subscribe((response) => {
        const payload = normalizeVaultResetResponse(response);
        if (!payload.ok) {
          this.toast.error(payload.message || 'Failed to reset local media vault');
          return;
        }

        this.toast.success(payload.message || 'Local media vault reset requested');
        if (this.isDesktop() && payload.vaultEpoch) {
          void this.desktopBridge.setVaultEpoch(payload.vaultEpoch);
          void this.loadDesktopResilienceState();
        }
        this.loadLocalResilience();
      });
  }

  async loadDesktopResilienceState(): Promise<void> {
    if (!this.isDesktop()) {
      return;
    }
    const [runtime, sync, vault] = await Promise.all([
      this.desktopBridge.getRuntimeStatus(),
      this.desktopBridge.getSyncStatus(),
      this.desktopBridge.getVaultStatus(),
    ]);
    this.desktopRuntimeStatus.set(runtime);
    this.desktopSyncStatus.set(sync);
    this.desktopVaultStatus.set(vault);
  }

  async startDesktopLocalRuntime(): Promise<void> {
    if (!this.isDesktop() || this.desktopRuntimeLoading()) {
      return;
    }
    this.desktopRuntimeLoading.set(true);
    try {
      const runtime = await this.desktopBridge.startLocalRuntime();
      this.desktopRuntimeStatus.set(runtime);
      if (runtime.running && runtime.healthy) {
        this.toast.success('Desktop local runtime is running');
      } else {
        this.toast.info(runtime.reason || 'Desktop local runtime start requested');
      }
      this.desktopSyncStatus.set(await this.desktopBridge.getSyncStatus());
    } catch {
      this.toast.error('Failed to start desktop local runtime');
    } finally {
      this.desktopRuntimeLoading.set(false);
    }
  }

  async stopDesktopLocalRuntime(): Promise<void> {
    if (!this.isDesktop() || this.desktopRuntimeLoading()) {
      return;
    }
    this.desktopRuntimeLoading.set(true);
    try {
      const runtime = await this.desktopBridge.stopLocalRuntime();
      this.desktopRuntimeStatus.set(runtime);
      this.desktopSyncStatus.set(await this.desktopBridge.getSyncStatus());
      this.toast.success('Desktop local runtime stopped');
    } catch {
      this.toast.error('Failed to stop desktop local runtime');
    } finally {
      this.desktopRuntimeLoading.set(false);
    }
  }

  async unlockDesktopVault(): Promise<void> {
    if (!this.isDesktop() || this.desktopVaultLoading()) {
      return;
    }
    const passphrase = this.desktopVaultPassphrase().trim();
    if (!passphrase) {
      this.toast.error('Enter the local vault passphrase');
      return;
    }

    this.desktopVaultLoading.set(true);
    try {
      const vault = await this.desktopBridge.unlockVault(passphrase);
      this.desktopVaultStatus.set(vault);
      if (vault.unlocked) {
        this.toast.success('Desktop vault unlocked');
        this.desktopVaultPassphrase.set('');
      } else {
        this.toast.error(vault.lastError || 'Failed to unlock desktop vault');
      }
      this.desktopRuntimeStatus.set(await this.desktopBridge.getRuntimeStatus());
      this.desktopSyncStatus.set(await this.desktopBridge.getSyncStatus());
    } finally {
      this.desktopVaultLoading.set(false);
    }
  }

  async lockDesktopVault(): Promise<void> {
    if (!this.isDesktop() || this.desktopVaultLoading()) {
      return;
    }
    this.desktopVaultLoading.set(true);
    try {
      const vault = await this.desktopBridge.lockVault();
      this.desktopVaultStatus.set(vault);
      this.toast.success('Desktop vault locked');
    } finally {
      this.desktopVaultLoading.set(false);
    }
  }

  loadUiSettings(): void {
    this.uiSettingsLoading.set(true);
    this.serverManagementApi
      .serverManagementUiSettingsRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load UI settings');
          return EMPTY;
        }),
        finalize(() => this.uiSettingsLoading.set(false)),
      )
      .subscribe((response) => {
        this.uiSettings.set(normalizeUiSettings(response));
      });
  }

  loadAiWorkflowStatus(): void {
    this.aiWorkflowFacade.loadAiWorkflowStatus();
  }

  saveAiWorkflowSettings(): void {
    this.aiWorkflowFacade.saveAiWorkflowSettings();
  }

  resetAiWorkflowDraft(): void {
    this.aiWorkflowFacade.resetAiWorkflowDraft();
  }

  getAiSettingValue(name: string | null | undefined): string {
    return this.aiWorkflowFacade.getAiSettingValue(name);
  }

  getAiSettingBool(name: string | null | undefined): boolean {
    return this.aiWorkflowFacade.getAiSettingBool(name);
  }

  setAiSettingFromEvent(name: string | null | undefined, event: Event): void {
    this.aiWorkflowFacade.setAiSettingFromEvent(name, event);
  }

  setAiSettingNumberFromEvent(name: string, event: Event): void {
    this.aiWorkflowFacade.setAiSettingNumberFromEvent(name, event);
  }

  setAiSettingBoolFromEvent(name: string, event: Event): void {
    this.aiWorkflowFacade.setAiSettingBoolFromEvent(name, event);
  }

  getPrimaryModelValue(): string {
    return this.aiWorkflowFacade.getPrimaryModelValue();
  }

  onPrimaryModelValueChange(value: string | string[] | null): void {
    this.aiWorkflowFacade.onPrimaryModelValueChange(value);
  }

  onModelSettingComboboxChange(
    settingName: string | null | undefined,
    value: string | string[] | null,
  ): void {
    this.aiWorkflowFacade.onModelSettingComboboxChange(settingName, value);
  }

  getDraftFallbackProviderOrder(): string[] {
    return this.aiWorkflowFacade.getDraftFallbackProviderOrder();
  }

  toggleFallbackProvider(provider: string, enabled: boolean): void {
    this.aiWorkflowFacade.toggleFallbackProvider(provider, enabled);
  }

  getModelProviderCatalogMap(): Record<string, AiModelProviderCatalog> {
    return this.aiWorkflowFacade.getModelProviderCatalogMap();
  }

  getProviderKeys(): string[] {
    return this.aiWorkflowFacade.getProviderKeys();
  }

  getProviderDisplayName(provider: string): string {
    return this.aiWorkflowFacade.getProviderDisplayName(provider);
  }

  getModelsForProvider(provider: string): AiModelDefinition[] {
    return this.aiWorkflowFacade.getModelsForProvider(provider);
  }

  getCurrentPrimaryProvider(): string {
    return this.aiWorkflowFacade.getCurrentPrimaryProvider();
  }

  getAllProviderModels(): AiProviderModelOption[] {
    return this.aiWorkflowFacade.getAllProviderModels();
  }

  getModelsForSetting(
    settingName: string | null | undefined,
    providerFallback?: string | null | undefined,
  ): AiModelDefinition[] {
    return this.aiWorkflowFacade.getModelsForSetting(settingName, providerFallback);
  }

  getFeatureProvider(feature: AiWorkflowFeature): string {
    return this.aiWorkflowFacade.getFeatureProvider(feature);
  }

  formatModelCapabilities(model: AiModelDefinition): string {
    return this.aiWorkflowFacade.formatModelCapabilities(model);
  }

  findModelDefinition(
    provider: string,
    modelId: string | null | undefined,
  ): AiModelDefinition | null {
    return this.aiWorkflowFacade.findModelDefinition(provider, modelId);
  }

  findModelDefinitionForSetting(
    settingName: string | null | undefined,
    providerFallback: string | null | undefined,
    modelId: string | null | undefined,
  ): AiModelDefinition | null {
    return this.aiWorkflowFacade.findModelDefinitionForSetting(
      settingName,
      providerFallback,
      modelId,
    );
  }

  toggleOverlayMenuPreference(): void {
    const current = this.uiSettings();
    if (!current || this.uiSettingsSaving()) {
      return;
    }

    this.uiSettingsSaving.set(true);
    this.serverManagementApi
      .serverManagementUiSettingsPartialUpdate({
        requestBody: {
          useOverlayMenu: !current.useOverlayMenu,
        },
      })
      .pipe(
        catchError(() => {
          this.toast.error('Failed to update menu mode');
          return EMPTY;
        }),
        finalize(() => this.uiSettingsSaving.set(false)),
      )
      .subscribe((response) => {
        const normalized = normalizeUiSettings(response);
        this.uiSettings.set(normalized);
        this.toast.success(
          normalized.useOverlayMenu
            ? 'Overlay top menu enabled for web + PWA'
            : 'Sidebar menu restored for web (PWA auto-overlay remains available)',
        );
      });
  }

  loadCacheHealth(showToast = false): void {
    this.cacheHealthLoading.set(true);
    this.serverManagementApi
      .serverManagementCacheHealthRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to run cache health check');
          return EMPTY;
        }),
        finalize(() => this.cacheHealthLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = normalizeCacheHealth(response);
        this.cacheHealth.set(normalized);
        if (showToast) {
          const userCacheIsDisabled =
            this.cacheStatus()?.enabled === false ||
            normalized.userCacheEnabled === false ||
            normalized.probeSkipped === true;

          if (userCacheIsDisabled) {
            this.toast.info(
              normalized.message ||
                'Cache is disabled for your user. Backend connectivity can still be healthy.',
            );
          } else if (normalized.ok) {
            this.toast.success(normalized.message);
          } else {
            this.toast.error(normalized.message);
          }
        }
      });
  }

  runMediaDiagnostic(): void {
    this.startServerAction('mediaDiagnostic');
    this.isLoading.set(true);
    this.diagnosticResults.set([]);
    this.repairResults.set([]);

    this.serverManagementApi
      .serverManagementMediaDiagnosticRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to run media diagnostic');
          return EMPTY;
        }),
        finalize(() => this.finishServerAction('mediaDiagnostic')),
      )
      .subscribe((response) => {
        const normalized = normalizeMediaDiagnosticResponse(response);
        if (normalized.ok) {
          this.diagnosticResults.set(normalized.results);
          this.serverSettings.set(normalized.settings);

          const missing = this.missingFilesCount();
          const discrepancies = this.discrepancyCount();

          let message = `Diagnostic complete: ${this.diagnosticResults().length} files checked`;
          if (missing > 0) {
            message += `, ${missing} missing`;
          }
          if (discrepancies > 0) {
            message += `, ${discrepancies} with URL issues`;
          }

          this.toast.success(message);
        } else {
          this.toast.error(normalized.message || 'Diagnostic failed');
        }
      });
  }

  repairMediaPaths(): void {
    if (this.diagnosticResults().length === 0) {
      this.toast.error('Run diagnostic first to identify issues');
      return;
    }

    this.startServerAction('mediaRepair');
    this.isLoading.set(true);
    this.repairResults.set([]);

    this.serverManagementApi
      .serverManagementMediaRepairCreate()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to repair media paths');
          return EMPTY;
        }),
        finalize(() => this.finishServerAction('mediaRepair')),
      )
      .subscribe((response) => {
        const normalized = normalizeMediaRepairResponse(response);
        if (normalized.ok) {
          this.repairResults.set(normalized.repairs);

          if (normalized.repairs.length > 0) {
            this.toast.success(`Repaired ${normalized.repairs.length} media file paths`);
            // Re-run diagnostic to show updated status
            setTimeout(() => this.runMediaDiagnostic(), 1000);
          } else {
            this.toast.info('No repairs were needed or possible');
          }
        } else {
          this.toast.error(normalized.message || 'Repair failed');
        }
      });
  }

  runMediaCleanup(): void {
    this.startServerAction('mediaCleanup');
    this.isLoading.set(true);
    this.cleanupResult.set(this.createCleanupProgressState(this.cleanupDryRun()));
    this.stopMediaCleanupStream();

    const requestMetadata = createAsyncRequestMetadata();
    this.mediaCleanupSubscription = this.mediaCleanupStream
      .connect(this.cleanupDryRun(), requestMetadata)
      .subscribe({
        next: (event) => this.handleMediaCleanupStreamEvent(event),
        error: () => {
          this.toast.error('Failed to clean unlinked media files');
          this.finishServerAction('mediaCleanup');
          this.stopMediaCleanupStream();
        },
        complete: () => {
          this.finishServerAction('mediaCleanup');
          this.stopMediaCleanupStream();
        },
      });
  }

  private handleMediaCleanupStreamEvent(event: MediaCleanupStreamEvent): void {
    if (event.cleanup) {
      const normalizedCleanup = normalizeMediaCleanupResult(event.cleanup);
      if (normalizedCleanup) {
        this.cleanupResult.set(normalizedCleanup);
      }
    } else {
      this.applyMediaCleanupProgress(event);
    }

    if (event.event === 'media_cleanup_failed') {
      this.toast.error(event.message || event.error || 'Media cleanup failed');
      this.finishServerAction('mediaCleanup');
      this.stopMediaCleanupStream();
      return;
    }

    if (event.event === 'media_cleanup_finished') {
      const cleanup = this.cleanupResult();
      if (!cleanup) {
        this.toast.error(event.message || 'Media cleanup failed');
      } else if (cleanup.dryRun) {
        this.toast.success(`Preview found ${cleanup.orphanedFiles} unlinked files`);
      } else if (cleanup.errors.length > 0) {
        this.toast.info(
          `Deleted ${cleanup.deletedFiles} files, with ${cleanup.errors.length} issue(s)`,
        );
      } else {
        this.toast.success(`Deleted ${cleanup.deletedFiles} unlinked files`);
      }
      this.finishServerAction('mediaCleanup');
      this.stopMediaCleanupStream();
    }
  }

  private applyMediaCleanupProgress(event: MediaCleanupStreamEvent): void {
    const current = this.cleanupResult() ?? this.createCleanupProgressState(Boolean(event.dryRun));
    const nextFiles = [...current.files];
    const foundFile = normalizeMediaCleanupFile(event.file);
    if (foundFile && !nextFiles.some((entry) => entry.path === foundFile.path)) {
      nextFiles.push(foundFile);
    }

    this.cleanupResult.set({
      ...current,
      message: toOptionalString(event.message) ?? current.message,
      dryRun: Boolean(event.dryRun ?? current.dryRun),
      prefixes: Array.isArray(event.prefixes)
        ? event.prefixes.map((entry) => String(entry))
        : current.prefixes,
      scannedFiles: toOptionalNumber(event.scannedFiles) ?? current.scannedFiles,
      referencedFiles: toOptionalNumber(event.referencedFiles) ?? current.referencedFiles,
      orphanedFiles: toOptionalNumber(event.orphanedFiles) ?? current.orphanedFiles,
      deletedFiles: toOptionalNumber(event.deletedFiles) ?? current.deletedFiles,
      totalOrphanBytes: toOptionalNumber(event.totalOrphanBytes) ?? current.totalOrphanBytes,
      errors: Array.isArray(event.errors)
        ? event.errors.map((entry) => String(entry))
        : current.errors,
      files: nextFiles,
      storageBackend: toOptionalString(event.storage?.backend) ?? current.storageBackend,
      storageProvider: toOptionalString(event.storage?.provider) ?? current.storageProvider,
    });
  }

  private createCleanupProgressState(dryRun: boolean): MediaCleanupResult {
    return {
      ok: true,
      message: dryRun ? 'Scanning for unlinked files...' : 'Deleting unlinked files...',
      dryRun,
      prefixes: [],
      scannedFiles: 0,
      referencedFiles: 0,
      orphanedFiles: 0,
      deletedFiles: 0,
      totalOrphanBytes: 0,
      files: [],
      errors: [],
    };
  }

  private startServerAction(action: ServerActionName): void {
    this.activeServerAction.set(action);
  }

  private finishServerAction(action: ServerActionName): void {
    if (this.activeServerAction() === action) {
      this.activeServerAction.set(null);
    }
    this.isLoading.set(false);
  }

  private stopMediaCleanupStream(): void {
    this.mediaCleanupSubscription?.unsubscribe();
    this.mediaCleanupSubscription = null;
  }

  getCacheBackendType(cacheBackend?: string | null): string {
    if (!cacheBackend) {
      return 'Unknown';
    }
    const backendTokens = cacheBackend.split('.');
    return backendTokens[backendTokens.length - 1] || cacheBackend;
  }

  getLocalDesktopModeLabel(mode: string | null | undefined): string {
    const normalized = String(mode || '')
      .trim()
      .toLowerCase();
    if (normalized === 'localprimary' || normalized === 'local_primary') {
      return 'Local Primary';
    }
    if (normalized === 'remoteprimary' || normalized === 'remote_primary') {
      return 'Remote Primary';
    }
    return mode || 'Unknown';
  }

  getFailoverProviderBadgeType(
    provider: AiWorkflowFailoverProvider,
  ): 'default' | 'secondary' | 'destructive' {
    return this.aiWorkflowFacade.getFailoverProviderBadgeType(provider);
  }

  getFailoverProviderStatus(provider: AiWorkflowFailoverProvider): string {
    return this.aiWorkflowFacade.getFailoverProviderStatus(provider);
  }

}
