import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnInit,
  signal,
} from '@angular/core';
import { catchError, EMPTY, finalize } from 'rxjs';

import { ServerManagementService } from '@/core/api';
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
  userCacheEnabled?: boolean;
  probeSkipped?: boolean;
  writeReadDeleteOk: boolean | null;
  probeLatencyMs: number;
  errors: string[];
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
  private serverManagementApi = inject(ServerManagementService);
  private http = inject(HttpClient);
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

  readonly missingFilesCount = computed(
    () => this.diagnosticResults().filter((r) => !r.exists).length,
  );

  readonly discrepancyCount = computed(
    () => this.diagnosticResults().filter((r) => r.discrepancy).length,
  );

  ngOnInit(): void {
    this.loadCacheStatus();
    this.loadCacheHealth();
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
      .get<CacheStatusResponse>('/api/cache/status/')
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

    const endpoint = currentStatus.enabled ? '/api/cache/disable/' : '/api/cache/enable/';
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
      .post<CacheClearResponse>('/api/cache/clear/', {})
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
          const userCacheIsDisabled =
            this.cacheStatus()?.enabled === false ||
            response.userCacheEnabled === false ||
            response.probeSkipped === true;

          if (userCacheIsDisabled) {
            this.toast.info(
              response.message ||
                'Cache is disabled for your user. Backend connectivity can still be healthy.',
            );
          } else if (response.ok) {
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
}
