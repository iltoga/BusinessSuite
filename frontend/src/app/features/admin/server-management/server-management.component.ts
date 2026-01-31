import { CommonModule } from '@angular/common';
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

@Component({
  selector: 'app-server-management',
  standalone: true,
  imports: [CommonModule, ZardCardComponent, ZardButtonComponent, ZardBadgeComponent],
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold tracking-tight">Server Management</h1>
      </div>

      <!-- Server Actions -->
      <z-card class="p-6">
        <h3 class="text-lg font-medium mb-4">Server Actions</h3>
        <div class="flex gap-4">
          <button z-button (click)="clearCache()" [zDisabled]="isLoading()" zType="outline">
            @if (isLoading()) {
              <span>Clearing...</span>
            } @else {
              <span>Clear Cache</span>
            }
          </button>
          <button z-button (click)="runMediaDiagnostic()" [zDisabled]="isLoading()" zType="outline">
            @if (isLoading()) {
              <span>Running...</span>
            } @else {
              <span>Media Diagnostic</span>
            }
          </button>
          <button
            z-button
            (click)="repairMediaPaths()"
            [zDisabled]="isLoading() || !diagnosticResults().length"
            zType="outline"
          >
            @if (isLoading()) {
              <span>Repairing...</span>
            } @else {
              <span>Repair Media Paths</span>
            }
          </button>
        </div>
      </z-card>

      <!-- Server Settings -->
      @if (serverSettings()) {
        <z-card class="p-6">
          <h3 class="text-lg font-medium mb-4">Server Settings</h3>
          <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label class="text-sm font-medium text-muted-foreground">Media Root</label>
              <p class="text-sm font-mono bg-muted p-2 rounded mt-1">
                {{ serverSettings()!.mediaRoot }}
              </p>
            </div>
            <div>
              <label class="text-sm font-medium text-muted-foreground">Media URL</label>
              <p class="text-sm font-mono bg-muted p-2 rounded mt-1">
                {{ serverSettings()!.mediaUrl }}
              </p>
            </div>
            <div>
              <label class="text-sm font-medium text-muted-foreground">Debug Mode</label>
              <div class="mt-1">
                <z-badge [zType]="serverSettings()!.debug ? 'destructive' : 'default'">
                  {{ serverSettings()!.debug ? 'ON' : 'OFF' }}
                </z-badge>
              </div>
            </div>
          </div>
        </z-card>
      }

      <!-- Media Diagnostic Results -->
      @if (diagnosticResults().length > 0) {
        <z-card class="p-0">
          <div class="p-4 border-b">
            <div class="flex items-center justify-between">
              <h3 class="text-lg font-medium">Media Files Diagnostic</h3>
              <div class="flex gap-2">
                <z-badge zType="secondary"> Total: {{ diagnosticResults().length }} </z-badge>
                <z-badge zType="destructive"> Missing: {{ missingFilesCount() }} </z-badge>
                <z-badge zType="default"> With Discrepancy: {{ discrepancyCount() }} </z-badge>
              </div>
            </div>
          </div>
          <div class="max-h-96 overflow-auto">
            <table class="w-full">
              <thead class="bg-muted text-left">
                <tr>
                  <th class="px-4 py-2 text-sm font-medium">Model</th>
                  <th class="px-4 py-2 text-sm font-medium">ID</th>
                  <th class="px-4 py-2 text-sm font-medium">Field</th>
                  <th class="px-4 py-2 text-sm font-medium">Path</th>
                  <th class="px-4 py-2 text-sm font-medium">Exists</th>
                  <th class="px-4 py-2 text-sm font-medium">Issues</th>
                </tr>
              </thead>
              <tbody>
                @for (
                  result of diagnosticResults();
                  track result.model + result.id + result.field
                ) {
                  <tr class="border-b">
                    <td class="px-4 py-2 text-sm">{{ result.model }}</td>
                    <td class="px-4 py-2 text-sm">{{ result.id }}</td>
                    <td class="px-4 py-2 text-sm font-mono">{{ result.field }}</td>
                    <td class="px-4 py-2 text-sm font-mono truncate max-w-xs" [title]="result.path">
                      {{ result.path }}
                    </td>
                    <td class="px-4 py-2">
                      <z-badge [zType]="result.exists ? 'default' : 'destructive'">
                        {{ result.exists ? 'Yes' : 'No' }}
                      </z-badge>
                    </td>
                    <td class="px-4 py-2">
                      <div class="flex gap-1">
                        @if (!result.exists) {
                          <z-badge zType="destructive" class="text-xs">Missing</z-badge>
                        }
                        @if (result.discrepancy) {
                          <z-badge zType="secondary" class="text-xs">URL Mismatch</z-badge>
                        }
                      </div>
                    </td>
                  </tr>
                }
              </tbody>
            </table>
          </div>
        </z-card>
      }

      <!-- Repair Results -->
      @if (repairResults().length > 0) {
        <z-card class="p-6">
          <h3 class="text-lg font-medium mb-4">Media Repair Results</h3>
          <div class="space-y-2">
            @for (repair of repairResults(); track $index) {
              <div class="text-sm bg-muted p-2 rounded font-mono">
                {{ repair }}
              </div>
            }
          </div>
        </z-card>
      }
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ServerManagementComponent implements OnInit {
  private serverManagementApi = inject(ServerManagementService);
  private toast = inject(GlobalToastService);

  readonly isLoading = signal(false);
  readonly diagnosticResults = signal<MediaDiagnosticResult[]>([]);
  readonly repairResults = signal<string[]>([]);
  readonly serverSettings = signal<ServerSettings | null>(null);

  readonly missingFilesCount = computed(
    () => this.diagnosticResults().filter((r) => !r.exists).length,
  );

  readonly discrepancyCount = computed(
    () => this.diagnosticResults().filter((r) => r.discrepancy).length,
  );

  ngOnInit(): void {
    // Load initial diagnostic if needed
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
        } else {
          this.toast.error(response.message || 'Failed to clear cache');
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
}
