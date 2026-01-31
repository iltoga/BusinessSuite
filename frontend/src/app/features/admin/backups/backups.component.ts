import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnDestroy,
  OnInit,
  signal,
  TemplateRef,
  ViewChild,
} from '@angular/core';
import { catchError, EMPTY, finalize } from 'rxjs';

import { BackupsService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import {
  ColumnConfig,
  DataTableComponent,
} from '@/shared/components/data-table/data-table.component';
import { FileUploadComponent } from '@/shared/components/file-upload/file-upload.component';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

interface Backup {
  filename: string;
  size: number | null;
  type: string;
  includedFiles: number | null;
  hasUsers: boolean;
  createdAt: string | null;
}

@Component({
  selector: 'app-backups',
  standalone: true,
  imports: [
    CommonModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    ZardCheckboxComponent,
    DataTableComponent,
    FileUploadComponent,
    AppDatePipe,
  ],
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-bold tracking-tight">Backup & Restore</h1>
        <div class="flex gap-2">
          <button
            z-button
            zType="outline"
            (click)="deleteAllBackups()"
            [zDisabled]="isOperationRunning()"
          >
            Delete All
          </button>
          <button z-button (click)="startBackup()" [zDisabled]="isOperationRunning()">
            Start Backup
          </button>
        </div>
      </div>

      <!-- Backup Options -->
      <z-card class="p-4">
        <div class="flex items-center gap-4">
          <z-checkbox [checked]="includeUsers()" (click)="toggleIncludeUsers()">
            <span class="text-sm">Include users/groups/permissions (full backup)</span>
          </z-checkbox>
        </div>
      </z-card>

      <!-- File Upload -->
      <z-card class="p-4">
        <h3 class="text-lg font-medium mb-4">Upload Backup</h3>
        <app-file-upload
          accept=".json,.gz,.tar.gz,.tgz,.tar.zst,.zst"
          [disabled]="isOperationRunning()"
          (fileSelected)="uploadBackup($event)"
        >
          Drop backup files here or click to select
        </app-file-upload>
      </z-card>

      <!-- Live Log -->
      @if (logMessages().length > 0) {
        <z-card class="p-0">
          <div class="p-4 border-b">
            <h3 class="text-lg font-medium">Live Log</h3>
          </div>
          <div class="p-4 bg-slate-950 text-green-400 font-mono text-sm max-h-80 overflow-auto">
            @for (msg of logMessages(); track $index) {
              <div>{{ msg }}</div>
            }
          </div>
        </z-card>
      }

      <!-- Available Backups -->
      <z-card class="p-0">
        <div class="p-4 border-b">
          <h3 class="text-lg font-medium">Available Backups</h3>
        </div>
        <app-data-table [data]="backups()" [columns]="columns" [isLoading]="isLoading()" />
      </z-card>
    </div>

    <!-- Created At Template -->
    <ng-template #createdAtTemplate let-item>
      {{ item.createdAt | appDate: 'datetime' }}
    </ng-template>

    <!-- Status Template -->
    <ng-template #statusTemplate let-item>
      <div class="flex gap-1">
        @if (item.hasUsers) {
          <z-badge zType="default">Full</z-badge>
        }
        @if (item.includedFiles !== null && item.includedFiles > 0) {
          <z-badge zType="secondary">Files: {{ item.includedFiles }}</z-badge>
        }
      </div>
    </ng-template>

    <!-- Size Template -->
    <ng-template #sizeTemplate let-item>
      {{ formatFileSize(item.size) }}
    </ng-template>

    <!-- Actions Template -->
    <ng-template #actionsTemplate let-item>
      <div class="flex gap-2">
        <button
          z-button
          zType="ghost"
          zSize="sm"
          (click)="downloadBackup(item.filename)"
          [zDisabled]="isOperationRunning()"
        >
          Download
        </button>
        <button
          z-button
          zType="ghost"
          zSize="sm"
          (click)="restoreBackup(item.filename)"
          [zDisabled]="isOperationRunning()"
        >
          Restore
        </button>
      </div>
    </ng-template>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BackupsComponent implements OnInit, OnDestroy {
  @ViewChild('statusTemplate', { static: true }) statusTemplate!: TemplateRef<any>;
  @ViewChild('sizeTemplate', { static: true }) sizeTemplate!: TemplateRef<any>;
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;
  @ViewChild('createdAtTemplate', { static: true }) createdAtTemplate!: TemplateRef<any>;

  private backupsApi = inject(BackupsService);
  private http = inject(HttpClient);
  private toast = inject(GlobalToastService);

  readonly backups = signal<Backup[]>([]);
  readonly isLoading = signal(true);
  readonly isOperationRunning = signal(false);
  readonly logMessages = signal<string[]>([]);
  readonly includeUsers = signal(false);

  private eventSource: EventSource | null = null;

  columns: ColumnConfig[] = [
    { key: 'filename', header: 'Filename', sortable: true },
    { key: 'createdAt', header: 'Created', sortable: true },
    { key: 'type', header: 'Type', sortable: true },
    { key: 'size', header: 'Size', sortable: true },
    { key: 'status', header: 'Status', sortable: false },
    { key: 'actions', header: '' },
  ];

  ngOnInit(): void {
    // Set templates after view init
    this.columns[1].template = this.createdAtTemplate;
    this.columns[3].template = this.sizeTemplate;
    this.columns[4].template = this.statusTemplate;
    this.columns[5].template = this.actionsTemplate;

    this.loadBackups();
  }

  ngOnDestroy(): void {
    this.closeEventSource();
  }

  toggleIncludeUsers(): void {
    this.includeUsers.update((v) => !v);
  }

  private loadBackups(): void {
    this.isLoading.set(true);
    this.backupsApi
      .backupsRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load backups');
          return EMPTY;
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response: any) => {
        this.backups.set(response?.backups || []);
      });
  }

  startBackup(): void {
    this.isOperationRunning.set(true);
    this.logMessages.set([]);

    // Use SSE for real-time backup progress
    this.eventSource = new EventSource(`/api/backups/start/?include_users=${this.includeUsers()}`);

    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.message) {
        this.logMessages.update((msgs) => [...msgs, data.message]);
      }
      if (data.message?.includes('Backup finished')) {
        this.closeEventSource();
        this.isOperationRunning.set(false);
        this.toast.success('Backup completed successfully');
        this.loadBackups(); // Refresh list
      }
    };

    this.eventSource.onerror = () => {
      this.closeEventSource();
      this.isOperationRunning.set(false);
      this.toast.error('Backup failed');
    };
  }

  restoreBackup(filename: string): void {
    if (
      !confirm(
        `Are you sure you want to restore from "${filename}"? This will overwrite existing data.`,
      )
    ) {
      return;
    }

    this.isOperationRunning.set(true);
    this.logMessages.set([]);

    // Use SSE for real-time restore progress
    this.eventSource = new EventSource(
      `/api/backups/restore/?file=${filename}&include_users=${this.includeUsers()}`,
    );

    this.eventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.message) {
        this.logMessages.update((msgs) => [...msgs, data.message]);
      }
      if (data.progress) {
        this.logMessages.update((msgs) => [...msgs, `Progress: ${data.progress}%`]);
      }
      if (data.message?.includes('Restore finished')) {
        this.closeEventSource();
        this.isOperationRunning.set(false);
        this.toast.success('Restore completed successfully');
      }
    };

    this.eventSource.onerror = () => {
      this.closeEventSource();
      this.isOperationRunning.set(false);
      this.toast.error('Restore failed');
    };
  }

  downloadBackup(filename: string): void {
    this.backupsApi
      .backupsDownloadRetrieve(filename)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to download backup');
          return EMPTY;
        }),
      )
      .subscribe((response) => {
        // Create download link
        const blob = new Blob([response], { type: 'application/octet-stream' });
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        link.click();
        window.URL.revokeObjectURL(url);
      });
  }

  uploadBackup(file: File): void {
    const formData = new FormData();
    formData.append('backup_file', file);

    this.isOperationRunning.set(true);
    // Use HttpClient directly since generated API doesn't support FormData uploads correctly
    this.http
      .post<{ ok: boolean; error?: string; filename?: string }>('/api/backups/upload/', formData)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to upload backup');
          return EMPTY;
        }),
        finalize(() => this.isOperationRunning.set(false)),
      )
      .subscribe((response: any) => {
        if (response.ok) {
          this.toast.success('Backup uploaded successfully');
          this.loadBackups();
        } else {
          this.toast.error(response.error || 'Upload failed');
        }
      });
  }

  deleteAllBackups(): void {
    if (!confirm('Are you sure you want to delete ALL backups? This action cannot be undone.')) {
      return;
    }

    this.isOperationRunning.set(true);
    this.backupsApi
      .backupsDeleteAllDestroy()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to delete backups');
          return EMPTY;
        }),
        finalize(() => this.isOperationRunning.set(false)),
      )
      .subscribe((response: any) => {
        if (response.ok) {
          this.toast.success(`Deleted ${response.deleted} backup files`);
          this.loadBackups();
        } else {
          this.toast.error(response.error || 'Delete failed');
        }
      });
  }

  formatFileSize(bytes: number | null): string {
    if (!bytes) return 'Unknown';
    const units = ['B', 'KB', 'MB', 'GB'];
    let size = bytes;
    let unitIndex = 0;
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024;
      unitIndex++;
    }
    return `${Math.round(size * 100) / 100} ${units[unitIndex]}`;
  }

  private closeEventSource(): void {
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
  }
}
