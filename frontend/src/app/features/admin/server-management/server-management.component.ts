import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';
import { catchError, EMPTY, finalize } from 'rxjs';

import { ServerManagementService } from '@/core/api';
import {
  DesktopBridgeService,
  DesktopRuntimeStatus,
  DesktopSyncStatus,
  DesktopVaultStatus,
} from '@/core/services/desktop-bridge.service';
import { GlobalToastService } from '@/core/services/toast.service';
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
  AiWorkflowStatusResponse,
} from './server-management-ai-workflow.models';

interface MediaDiagnosticResult {
  model: string;
  id: number;
  field: string;
  path: string;
  absPath: string;
  exists: boolean;
  url: string;
  fileLink?: string;
  discrepancy: boolean;
}

interface ServerSettings {
  mediaRoot: string;
  mediaUrl: string;
  debug: boolean;
}

interface CacheStatusResponse {
  enabled: boolean;
  version: number;
  message: string;
  cacheBackend?: string;
  cacheLocation?: string;
  globalEnabled?: boolean;
  userEnabled?: boolean;
}

interface CacheHealthResponse {
  ok: boolean;
  message: string;
  checkedAt: string;
  cacheBackend: string;
  cacheLocation: string;
  redisConfigured: boolean;
  redisConnected: boolean | null;
  userCacheEnabled?: boolean;
  probeSkipped?: boolean;
  writeReadDeleteOk: boolean | null;
  probeLatencyMs: number;
  errors: string[];
}

interface LocalResilienceSettingsResponse {
  enabled: boolean;
  encryptionRequired: boolean;
  desktopMode: 'localPrimary' | 'remotePrimary' | string;
  vaultEpoch: number;
  updatedAt?: string;
  updatedBy?: {
    id: number;
    username?: string | null;
    email?: string | null;
  } | null;
}

interface UiSettingsResponse {
  useOverlayMenu: boolean;
  updatedAt?: string;
  updatedBy?: {
    id: number;
    username?: string | null;
    email?: string | null;
  } | null;
}

interface ServerActionResponse {
  ok: boolean;
  message: string;
}

interface MediaDiagnosticResponse {
  ok: boolean;
  message: string;
  results: MediaDiagnosticResult[];
  settings: ServerSettings | null;
}

interface MediaRepairResponse {
  ok: boolean;
  message: string;
  repairs: string[];
}

@Component({
  selector: 'app-server-management',
  standalone: true,
  imports: [
    CommonModule,
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
export class ServerManagementComponent implements OnInit {
  private readonly platformId = inject(PLATFORM_ID);
  private serverManagementApi = inject(ServerManagementService);
  private http = inject(HttpClient);
  private desktopBridge = inject(DesktopBridgeService);
  private toast = inject(GlobalToastService);
  private aiWorkflowFacade = inject(ServerManagementAiWorkflowFacade);

  readonly isLoading = signal(false);
  readonly diagnosticResults = signal<MediaDiagnosticResult[]>([]);
  readonly repairResults = signal<string[]>([]);
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

  clearCache(): void {
    this.isLoading.set(true);
    this.serverManagementApi
      .serverManagementClearCacheCreate()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to clear cache');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeServerActionResponse(response);
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
    this.http
      .get<CacheStatusResponse>('/api/server-management/cache-status/')
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load cache status');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        this.cacheStatus.set(this.normalizeCacheStatus(response));
      });
  }

  toggleCache(): void {
    const currentStatus = this.cacheStatus();
    if (!currentStatus) {
      this.toast.error('Cache status not loaded');
      return;
    }

    const endpoint = currentStatus.enabled
      ? '/api/server-management/cache-disable/'
      : '/api/server-management/cache-enable/';
    this.cacheLoading.set(true);

    this.http
      .post<CacheStatusResponse>(endpoint, {})
      .pipe(
        catchError(() => {
          this.toast.error(`Failed to ${currentStatus.enabled ? 'disable' : 'enable'} cache`);
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeCacheStatus(response);
        this.cacheStatus.set(normalized);
        this.toast.success(normalized.message);
        this.loadCacheHealth();
      });
  }

  clearAllCache(): void {
    this.cacheLoading.set(true);
    this.serverManagementApi
      .serverManagementClearCacheCreate()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to clear cache');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeServerActionResponse(response);
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
        this.localResilience.set(this.normalizeLocalResilience(response));
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
        enabled: !current.enabled,
      })
      .pipe(
        catchError(() => {
          this.toast.error('Failed to update local resilience setting');
          return EMPTY;
        }),
        finalize(() => this.localResilienceSaving.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeLocalResilience(response);
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
        const payload = response as { ok?: boolean; message?: string; vaultEpoch?: number };
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
        this.uiSettings.set(this.normalizeUiSettings(response));
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

  findModelDefinition(provider: string, modelId: string | null | undefined): AiModelDefinition | null {
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
        useOverlayMenu: !current.useOverlayMenu,
      })
      .pipe(
        catchError(() => {
          this.toast.error('Failed to update menu mode');
          return EMPTY;
        }),
        finalize(() => this.uiSettingsSaving.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeUiSettings(response);
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
        const normalized = this.normalizeCacheHealth(response);
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
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeMediaDiagnosticResponse(response);
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

    this.isLoading.set(true);
    this.repairResults.set([]);

    this.serverManagementApi
      .serverManagementMediaRepairCreate()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to repair media paths');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response) => {
        const normalized = this.normalizeMediaRepairResponse(response);
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

  getFailoverProviderBadgeType(provider: AiWorkflowFailoverProvider): 'default' | 'secondary' | 'destructive' {
    return this.aiWorkflowFacade.getFailoverProviderBadgeType(provider);
  }

  getFailoverProviderStatus(provider: AiWorkflowFailoverProvider): string {
    return this.aiWorkflowFacade.getFailoverProviderStatus(provider);
  }

  private normalizeLocalResilience(raw: unknown): LocalResilienceSettingsResponse {
    const source = this.toRecord(raw);
    return {
      enabled: Boolean(source?.['enabled']),
      encryptionRequired: Boolean(source?.['encryptionRequired'] ?? source?.['encryption_required'] ?? true),
      desktopMode: String(source?.['desktopMode'] ?? source?.['desktop_mode'] ?? 'localPrimary'),
      vaultEpoch: Number(source?.['vaultEpoch'] ?? source?.['vault_epoch'] ?? 1),
      updatedAt: this.toOptionalString(source?.['updatedAt'] ?? source?.['updated_at']),
      updatedBy: this.toRecord(source?.['updatedBy'] ?? source?.['updated_by']) as
        | LocalResilienceSettingsResponse['updatedBy']
        | null,
    };
  }

  private normalizeUiSettings(raw: unknown): UiSettingsResponse {
    const source = this.toRecord(raw);
    return {
      useOverlayMenu: Boolean(source?.['useOverlayMenu'] ?? source?.['use_overlay_menu'] ?? false),
      updatedAt: this.toOptionalString(source?.['updatedAt'] ?? source?.['updated_at']),
      updatedBy: this.toRecord(source?.['updatedBy'] ?? source?.['updated_by']) as
        | UiSettingsResponse['updatedBy']
        | null,
    };
  }

  private normalizeCacheHealth(raw: unknown): CacheHealthResponse {
    const source = this.toRecord(raw);
    const redisConnectedRaw = source?.['redisConnected'] ?? source?.['redis_connected'];
    const writeReadDeleteRaw = source?.['writeReadDeleteOk'] ?? source?.['write_read_delete_ok'];
    return {
      ok: Boolean(source?.['ok']),
      message: String(source?.['message'] ?? 'Cache health check complete'),
      checkedAt: String(source?.['checkedAt'] ?? source?.['checked_at'] ?? ''),
      cacheBackend: String(source?.['cacheBackend'] ?? source?.['cache_backend'] ?? ''),
      cacheLocation: String(source?.['cacheLocation'] ?? source?.['cache_location'] ?? ''),
      redisConfigured: Boolean(source?.['redisConfigured'] ?? source?.['redis_configured'] ?? false),
      redisConnected:
        redisConnectedRaw === null || redisConnectedRaw === undefined
          ? null
          : Boolean(redisConnectedRaw),
      userCacheEnabled:
        source?.['userCacheEnabled'] === undefined
          ? (source?.['user_cache_enabled'] as boolean | undefined)
          : (source?.['userCacheEnabled'] as boolean | undefined),
      probeSkipped:
        source?.['probeSkipped'] === undefined
          ? (source?.['probe_skipped'] as boolean | undefined)
          : (source?.['probeSkipped'] as boolean | undefined),
      writeReadDeleteOk:
        writeReadDeleteRaw === null || writeReadDeleteRaw === undefined
          ? null
          : Boolean(writeReadDeleteRaw),
      probeLatencyMs: Number(source?.['probeLatencyMs'] ?? source?.['probe_latency_ms'] ?? 0),
      errors: Array.isArray(source?.['errors'])
        ? (source?.['errors'] as unknown[]).map((e) => String(e))
        : [],
    };
  }

  private normalizeCacheStatus(raw: unknown): CacheStatusResponse {
    const source = this.toRecord(raw);
    const globalEnabledRaw = source?.['globalEnabled'] ?? source?.['global_enabled'];
    const userEnabledRaw = source?.['userEnabled'] ?? source?.['user_enabled'];
    return {
      enabled: Boolean(source?.['enabled']),
      version: Number(source?.['version'] ?? 1),
      message: String(source?.['message'] ?? 'Cache status updated'),
      cacheBackend: String(source?.['cacheBackend'] ?? source?.['cache_backend'] ?? ''),
      cacheLocation: String(source?.['cacheLocation'] ?? source?.['cache_location'] ?? ''),
      globalEnabled:
        globalEnabledRaw === undefined ? undefined : Boolean(globalEnabledRaw),
      userEnabled: userEnabledRaw === undefined ? undefined : Boolean(userEnabledRaw),
    };
  }

  private normalizeServerActionResponse(raw: unknown): ServerActionResponse {
    const source = this.toRecord(raw);
    return {
      ok: Boolean(source?.['ok']),
      message: this.toOptionalString(source?.['message']) ?? '',
    };
  }

  private normalizeMediaDiagnosticResponse(raw: unknown): MediaDiagnosticResponse {
    const source = this.toRecord(raw);
    return {
      ok: Boolean(source?.['ok']),
      message: this.toOptionalString(source?.['message']) ?? '',
      results: Array.isArray(source?.['results'])
        ? (source['results'] as unknown[])
            .map((entry) => this.normalizeMediaDiagnosticResult(entry))
            .filter((entry): entry is MediaDiagnosticResult => !!entry)
        : [],
      settings: this.normalizeServerSettings(source?.['settings']),
    };
  }

  private normalizeMediaRepairResponse(raw: unknown): MediaRepairResponse {
    const source = this.toRecord(raw);
    return {
      ok: Boolean(source?.['ok']),
      message: this.toOptionalString(source?.['message']) ?? '',
      repairs: Array.isArray(source?.['repairs'])
        ? (source['repairs'] as unknown[]).map((entry) => String(entry))
        : [],
    };
  }

  private normalizeServerSettings(raw: unknown): ServerSettings | null {
    const source = this.toRecord(raw);
    if (!source) {
      return null;
    }
    return {
      mediaRoot: String(source['mediaRoot'] ?? source['media_root'] ?? ''),
      mediaUrl: String(source['mediaUrl'] ?? source['media_url'] ?? ''),
      debug: Boolean(source['debug']),
    };
  }

  private normalizeMediaDiagnosticResult(raw: unknown): MediaDiagnosticResult | null {
    const source = this.toRecord(raw);
    if (!source) {
      return null;
    }
    return {
      model: String(source['model'] ?? ''),
      id: Number(source['id'] ?? 0),
      field: String(source['field'] ?? ''),
      path: String(source['path'] ?? ''),
      absPath: String(source['absPath'] ?? source['abs_path'] ?? ''),
      exists: Boolean(source['exists']),
      url: String(source['url'] ?? ''),
      fileLink: this.toOptionalString(source['fileLink'] ?? source['file_link']),
      discrepancy: Boolean(source['discrepancy']),
    };
  }

  private toRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  }

  private toOptionalString(value: unknown): string | undefined {
    if (typeof value !== 'string') {
      return undefined;
    }
    return value;
  }
}
