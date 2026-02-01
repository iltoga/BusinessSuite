import { CommonModule } from '@angular/common';
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
import { catchError, EMPTY, finalize, Subscription, forkJoin, of } from 'rxjs';

import { BackupsService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';
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
        <div class="flex gap-4 items-center">
          <label class="flex items-center gap-2">
            <input type="checkbox" [checked]="selectAll()" (change)="toggleSelectAll($event)" />
            <span class="text-sm">Select all</span>
          </label>

          <button
            z-button
            zType="destructive"
            (click)="deleteSelectedBackups()"
            [zDisabled]="isOperationRunning() || selectedFiles().length === 0"
          >
            Delete Selected
          </button>

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
          [progress]="uploadProgress()"
          [fileName]="uploadFileName()"
          [helperText]="uploadHelperText()"
          (fileSelected)="uploadBackup($event)"
          (cleared)="clearUploadSelection()"
        >
          Drop backup files here or click to select
        </app-file-upload>
      </z-card>

      <!-- Progress Bar -->
      @if (operationProgress() !== null) {
        <z-card class="p-4">
          <div class="space-y-1">
            <div class="flex items-center justify-between text-xs text-muted-foreground">
              <span>{{ operationLabel() }}</span>
              <span>{{ operationProgress() }}%</span>
            </div>
            <div class="h-2 w-full rounded-full bg-muted">
              <div class="h-2 rounded-full bg-primary" [style.width.%]="operationProgress()"></div>
            </div>
          </div>
        </z-card>
      }

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
    <ng-template #selectTemplate let-item>
      <input
        type="checkbox"
        aria-label="Select backup"
        [checked]="isSelected(item.filename)"
        (click)="toggleSelect(item.filename, $event)"
      />
    </ng-template>

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
        <button
          z-button
          zType="destructive"
          zSize="sm"
          (click)="deleteBackup(item.filename)"
          [zDisabled]="isOperationRunning()"
        >
          Delete
        </button>
      </div>
    </ng-template>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BackupsComponent implements OnInit, OnDestroy {
  @ViewChild('selectTemplate', { static: true }) selectTemplate!: TemplateRef<any>;
  @ViewChild('statusTemplate', { static: true }) statusTemplate!: TemplateRef<any>;
  @ViewChild('sizeTemplate', { static: true }) sizeTemplate!: TemplateRef<any>;
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;
  @ViewChild('createdAtTemplate', { static: true }) createdAtTemplate!: TemplateRef<any>;

  private backupsApi = inject(BackupsService);
  private authService = inject(AuthService);
  private sseService = inject(SseService);
  private toast = inject(GlobalToastService);

  readonly backups = signal<Backup[]>([]);
  readonly isLoading = signal(true);
  readonly isOperationRunning = signal(false);
  readonly logMessages = signal<string[]>([]);
  readonly includeUsers = signal(false);
  readonly uploadProgress = signal<number | null>(null);
  readonly uploadFileName = signal<string | null>(null);
  readonly uploadHelperText = signal<string | null>(null);
  readonly operationProgress = signal<number | null>(null);
  readonly operationLabel = signal<string>('Operation progress');
  readonly selectedFiles = signal<string[]>([]);
  readonly selectAll = signal(false);

  private sseSubscription: Subscription | null = null;

  columns: ColumnConfig[] = [
    { key: 'select', header: '', sortable: false },
    { key: 'filename', header: 'Filename', sortable: true },
    { key: 'createdAt', header: 'Created', sortable: true },
    { key: 'type', header: 'Type', sortable: true },
    { key: 'size', header: 'Size', sortable: true },
    { key: 'status', header: 'Status', sortable: false },
    { key: 'actions', header: '' },
  ];

  ngOnInit(): void {
    // Set templates after view init
    this.columns[0].template = this.selectTemplate;
    this.columns[2].template = this.createdAtTemplate;
    this.columns[4].template = this.sizeTemplate;
    this.columns[5].template = this.statusTemplate;
    this.columns[6].template = this.actionsTemplate;

    this.loadBackups();
  }

  ngOnDestroy(): void {
    this.clearSseSubscription();
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
    if (this.isOperationRunning()) {
      return;
    }
    this.isOperationRunning.set(true);
    this.logMessages.set([]);
    this.operationProgress.set(null);
    this.operationLabel.set('Backup progress');

    this.clearSseSubscription();
    const token = this.authService.getToken();
    const tokenParam = token ? `&token=${token}` : '';
    this.sseSubscription = this.sseService
      .connect<{
        message?: string;
        progress?: number;
      }>(`/api/backups/start/?include_users=${this.includeUsers()}${tokenParam}`)
      .subscribe({
        next: (data) => {
          const message = data.message;
          if (message) {
            this.logMessages.update((msgs) => [...msgs, message]);
          }
          if (typeof data.progress === 'number') {
            this.operationProgress.set(data.progress);
          }
          if (data.message?.includes('Backup finished')) {
            this.isOperationRunning.set(false);
            this.operationProgress.set(100);
            this.toast.success('Backup completed successfully');
            this.loadBackups();
            this.clearSseSubscription();
            setTimeout(() => this.operationProgress.set(null), 1500);
          }
        },
        error: () => {
          this.isOperationRunning.set(false);
          this.operationProgress.set(null);
          this.toast.error('Backup failed');
          this.clearSseSubscription();
        },
      });
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
    this.operationProgress.set(0);
    this.operationLabel.set('Restore progress');

    this.clearSseSubscription();
    const token = this.authService.getToken();
    const tokenParam = token ? `&token=${token}` : '';
    this.sseSubscription = this.sseService
      .connect<{
        message?: string;
        progress?: string | number;
      }>(`/api/backups/restore/?file=${filename}&include_users=${this.includeUsers()}${tokenParam}`)
      .subscribe({
        next: (data) => {
          const message = data.message;
          if (message) {
            this.logMessages.update((msgs) => [...msgs, message]);
          }
          if (data.progress !== undefined) {
            const progress =
              typeof data.progress === 'number' ? data.progress : Number.parseFloat(data.progress);
            if (!Number.isNaN(progress)) {
              this.operationProgress.set(progress);
            }
          }
          if (data.message?.includes('Restore finished')) {
            this.isOperationRunning.set(false);
            this.operationProgress.set(100);
            this.toast.success('Restore completed successfully');
            this.clearSseSubscription();
            setTimeout(() => this.operationProgress.set(null), 1500);
          }
        },
        error: () => {
          this.isOperationRunning.set(false);
          this.operationProgress.set(null);
          this.toast.error('Restore failed');
          this.clearSseSubscription();
        },
      });
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

    this.uploadFileName.set(file.name);
    this.uploadHelperText.set('Uploading backup...');
    this.uploadProgress.set(0);

    this.isOperationRunning.set(true);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', '/api/backups/upload/', true);
    xhr.responseType = 'json';

    const token = this.authService.getToken();
    if (token) {
      xhr.setRequestHeader('Authorization', `Bearer ${token}`);
    }
    xhr.setRequestHeader('ngsw-bypass', 'true');

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable && event.total > 0) {
        const percent = Math.round((event.loaded / event.total) * 100);
        this.uploadProgress.set(percent);
      }
    };

    xhr.onload = () => {
      this.isOperationRunning.set(false);
      const response = (xhr.response || {}) as {
        ok?: boolean;
        error?: string;
        filename?: string;
      };

      if (xhr.status >= 200 && xhr.status < 300 && response.ok) {
        this.uploadProgress.set(100);
        this.uploadHelperText.set('Upload complete');
        this.toast.success('Backup uploaded successfully');
        this.loadBackups();
        setTimeout(() => this.uploadProgress.set(null), 1500);
      } else {
        this.uploadProgress.set(null);
        this.uploadHelperText.set(null);
        this.toast.error(response.error || 'Upload failed');
      }
    };

    xhr.onerror = () => {
      this.isOperationRunning.set(false);
      this.uploadProgress.set(null);
      this.uploadHelperText.set(null);
      this.toast.error('Failed to upload backup');
    };

    xhr.send(formData);
  }

  clearUploadSelection(): void {
    this.uploadFileName.set(null);
    this.uploadProgress.set(null);
    this.uploadHelperText.set(null);
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

  deleteBackup(filename: string): void {
    if (!confirm(`Are you sure you want to delete "${filename}"? This action cannot be undone.`)) {
      return;
    }

    this.isOperationRunning.set(true);
    this.backupsApi
      .backupsDeleteFileDestroy(filename)
      .pipe(
        catchError(() => {
          this.toast.error('Failed to delete backup');
          return EMPTY;
        }),
        finalize(() => this.isOperationRunning.set(false)),
      )
      .subscribe((response: any) => {
        if (response.ok) {
          this.toast.success(`Deleted ${response.deleted}`);
          this.loadBackups();
          // remove from selectedFiles if present
          this.selectedFiles.set(this.selectedFiles().filter((f) => f !== filename));
        } else {
          this.toast.error(response.error || 'Delete failed');
        }
      });
  }

  isSelected(filename: string): boolean {
    return this.selectedFiles().includes(filename);
  }

  toggleSelect(filename: string, event: Event): void {
    event.stopPropagation();
    const current = this.selectedFiles();
    if (current.includes(filename)) {
      this.selectedFiles.set(current.filter((f) => f !== filename));
    } else {
      this.selectedFiles.set([...current, filename]);
    }
    // Keep selectAll flag in sync
    const allVisible = this.backups().map((b) => b.filename);
    this.selectAll.set(allVisible.length > 0 && allVisible.every((f) => this.selectedFiles().includes(f)));
  }

  toggleSelectAll(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.selectAll.set(checked);
    if (checked) {
      this.selectedFiles.set(this.backups().map((b) => b.filename));
    } else {
      this.selectedFiles.set([]);
    }
  }

  deleteSelectedBackups(): void {
    if (!this.selectedFiles().length) return;
    if (!confirm(`Are you sure you want to delete ${this.selectedFiles().length} selected backups? This action cannot be undone.`)) {
      return;
    }

    this.isOperationRunning.set(true);

    const observables = this.selectedFiles().map((filename) =>
      this.backupsApi.backupsDeleteFileDestroy(filename).pipe(
        catchError((err) => of({ ok: false, error: err?.message || 'Failed' })),
      ),
    );

    forkJoin(observables)
      .pipe(
        finalize(() => this.isOperationRunning.set(false)),
      )
      .subscribe((results: any[]) => {
        const failed = results.filter((r) => !r?.ok);
        if (failed.length === 0) {
          this.toast.success(`Deleted ${results.length} backup(s)`);
        } else {
          this.toast.error(`${failed.length} deletions failed`);
        }
        this.selectedFiles.set([]);
        this.selectAll.set(false);
        this.loadBackups();
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

  private clearSseSubscription(): void {
    if (this.sseSubscription) {
      this.sseSubscription.unsubscribe();
      this.sseSubscription = null;
    }
  }
}
