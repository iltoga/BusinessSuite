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
}

interface CacheClearResponse {
  version: number;
  cleared: boolean;
  message: string;
}

interface CacheHealthResponse {
  ok: boolean;
  message: string;
  checkedAt: string;
  cacheBackend: string;
  cacheLocation: string;
  redisConfigured: boolean;
  redisConnected: boolean | null;
  writeReadDeleteOk: boolean;
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

@Component({
  selector: 'app-server-management',
  standalone: true,
  imports: [CommonModule, ZardCardComponent, ZardButtonComponent, ZardBadgeComponent],
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
  readonly isDesktop = signal(false);
  readonly desktopRuntimeStatus = signal<DesktopRuntimeStatus | null>(null);
  readonly desktopSyncStatus = signal<DesktopSyncStatus | null>(null);
  readonly desktopVaultStatus = signal<DesktopVaultStatus | null>(null);
  readonly desktopRuntimeLoading = signal(false);
  readonly desktopVaultLoading = signal(false);

  readonly missingFilesCount = computed(
    () => this.diagnosticResults().filter((r) => !r.exists).length,
  );

  readonly discrepancyCount = computed(
    () => this.diagnosticResults().filter((r) => r.discrepancy).length,
  );

  ngOnInit(): void {
    this.isDesktop.set(
      isPlatformBrowser(this.platformId) && this.desktopBridge.isDesktop(),
    );
    this.loadCacheStatus();
    this.loadCacheHealth();
    this.loadLocalResilience();
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
      .subscribe((response: any) => {
        if (response.ok) {
          this.toast.success('Cache cleared successfully');
          this.loadCacheHealth();
        } else {
          this.toast.error(response.message || 'Failed to clear cache');
        }
      });
  }

  loadCacheStatus(): void {
    this.cacheLoading.set(true);
    this.http
      .get<CacheStatusResponse>('/api/cache/status')
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load cache status');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        this.cacheStatus.set(response);
      });
  }

  toggleCache(): void {
    const currentStatus = this.cacheStatus();
    if (!currentStatus) {
      this.toast.error('Cache status not loaded');
      return;
    }

    const endpoint = currentStatus.enabled ? '/api/cache/disable' : '/api/cache/enable';
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
        this.cacheStatus.set(response);
        this.toast.success(response.message);
        this.loadCacheHealth();
      });
  }

  clearUserCache(): void {
    this.cacheLoading.set(true);
    this.http
      .post<CacheClearResponse>('/api/cache/clear', {})
      .pipe(
        catchError(() => {
          this.toast.error('Failed to clear user cache');
          return EMPTY;
        }),
        finalize(() => this.cacheLoading.set(false)),
      )
      .subscribe((response) => {
        this.toast.success(response.message);
        // Update cache status with new version
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
        this.toast.success(normalized.enabled ? 'Local resilience enabled' : 'Local resilience disabled');
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
    const passphrase = window.prompt('Enter local vault passphrase');
    if (!passphrase) {
      return;
    }

    this.desktopVaultLoading.set(true);
    try {
      const vault = await this.desktopBridge.unlockVault(passphrase);
      this.desktopVaultStatus.set(vault);
      if (vault.unlocked) {
        this.toast.success('Desktop vault unlocked');
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

  loadCacheHealth(showToast = false): void {
    this.cacheHealthLoading.set(true);
    this.http
      .get<CacheHealthResponse>('/api/server-management/cache-health/')
      .pipe(
        catchError(() => {
          this.toast.error('Failed to run cache health check');
          return EMPTY;
        }),
        finalize(() => this.cacheHealthLoading.set(false)),
      )
      .subscribe((response) => {
        this.cacheHealth.set(response);
        if (showToast) {
          if (response.ok) {
            this.toast.success(response.message);
          } else {
            this.toast.error(response.message);
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
      .subscribe((response: any) => {
        if (response.ok) {
          this.diagnosticResults.set(response.results || []);
          this.serverSettings.set(response.settings);

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
          this.toast.error(response.message || 'Diagnostic failed');
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
      .subscribe((response: any) => {
        if (response.ok) {
          this.repairResults.set(response.repairs || []);

          if (response.repairs?.length > 0) {
            this.toast.success(`Repaired ${response.repairs.length} media file paths`);
            // Re-run diagnostic to show updated status
            setTimeout(() => this.runMediaDiagnostic(), 1000);
          } else {
            this.toast.info('No repairs were needed or possible');
          }
        } else {
          this.toast.error(response.message || 'Repair failed');
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
    const normalized = String(mode || '').trim().toLowerCase();
    if (normalized === 'localprimary' || normalized === 'local_primary') {
      return 'Local Primary';
    }
    if (normalized === 'remoteprimary' || normalized === 'remote_primary') {
      return 'Remote Primary';
    }
    return mode || 'Unknown';
  }

  private normalizeLocalResilience(raw: any): LocalResilienceSettingsResponse {
    return {
      enabled: Boolean(raw?.enabled),
      encryptionRequired: Boolean(raw?.encryptionRequired ?? raw?.encryption_required ?? true),
      desktopMode: String(raw?.desktopMode ?? raw?.desktop_mode ?? 'localPrimary'),
      vaultEpoch: Number(raw?.vaultEpoch ?? raw?.vault_epoch ?? 1),
      updatedAt: raw?.updatedAt ?? raw?.updated_at,
      updatedBy: raw?.updatedBy ?? raw?.updated_by ?? null,
    };
  }
}
