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
import { FormsModule } from '@angular/forms';
import { catchError, EMPTY, finalize, of, Subscription } from 'rxjs';

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
import { ZardIconComponent } from '@/shared/components/icon';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

interface Backup {
  filename: string;
  size: number | null;
  type: string;
  includedFiles: number | null;
  hasUsers: boolean;
  createdAt: string | null;
  selected?: boolean;
}

@Component({
  selector: 'app-backups',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    ZardCheckboxComponent,
    ZardIconComponent,
    DataTableComponent,
    FileUploadComponent,
    AppDatePipe,
  ],
  templateUrl: './backups.component.html',
  styleUrls: ['./backups.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class BackupsComponent implements OnInit, OnDestroy {
  @ViewChild('selectTemplate', { static: true }) selectTemplate!: TemplateRef<any>;
  @ViewChild('statusTemplate', { static: true }) statusTemplate!: TemplateRef<any>;
  @ViewChild('sizeTemplate', { static: true }) sizeTemplate!: TemplateRef<any>;
  @ViewChild('actionsTemplate', { static: true }) actionsTemplate!: TemplateRef<any>;
  @ViewChild('createdAtTemplate', { static: true }) createdAtTemplate!: TemplateRef<any>;

  private backupsApi = inject(BackupsService);
  private sseService = inject(SseService);
  private authService = inject(AuthService);
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

  // Selection state
  readonly selectedFiles = signal<string[]>([]);
  readonly selectAllValue = signal(false);

  // Live log accordion open by default
  readonly logOpen = signal(true);

  // bridge property for ngModel two-way binding on <z-checkbox>
  get selectAllFlag(): boolean {
    return this.selectAllValue();
  }
  set selectAllFlag(val: boolean) {
    this.onSelectAllChange(val);
  }

  private sseSubscription: Subscription | null = null;

  toggleLogOpen(): void {
    this.logOpen.update((v) => !v);
  }

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
        this.backups.set(response?.backups?.map((b: Backup) => ({ ...b, selected: false })) || []);
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
    this.sseSubscription = this.sseService
      .connect<{
        message?: string;
        progress?: number;
      }>(`/api/backups/start/?include_users=${this.includeUsers()}`)
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
    this.sseSubscription = this.sseService
      .connect<{
        message?: string;
        progress?: string | number;
      }>(`/api/backups/restore/?file=${filename}&include_users=${this.includeUsers()}`)
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
      .subscribe((response: any) => {
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
      .backupsDeleteDestroy(filename)
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
          // update "Select all" flag
          const allSelected = this.backups().every((b) => b.selected);
          this.selectAllValue.set(allSelected);
        } else {
          this.toast.error(response.error || 'Delete failed');
        }
      });
  }

  onSelectAllChange(checked: boolean): void {
    this.selectAllValue.set(checked);
    this.backups.update((backups) => backups.map((b) => ({ ...b, selected: checked })));
    this.selectedFiles.set(checked ? this.backups().map((b) => b.filename) : []);
  }

  onItemSelectChange(item: Backup, selected: boolean): void {
    item.selected = selected;
    if (selected) {
      if (!this.selectedFiles().includes(item.filename)) {
        this.selectedFiles.set([...this.selectedFiles(), item.filename]);
      }
    } else {
      this.selectedFiles.set(this.selectedFiles().filter((f) => f !== item.filename));
    }
    // update "Select all" flag
    const allSelected = this.backups().every((b) => b.selected);
    this.selectAllValue.set(allSelected);
  }

  deleteSelectedBackups(): void {
    const selectedFilenames = this.backups()
      .filter((b) => b.selected)
      .map((b) => b.filename);
    if (!selectedFilenames.length) return;
    if (
      !confirm(
        `Are you sure you want to delete ${selectedFilenames.length} selected backups? This action cannot be undone.`,
      )
    ) {
      return;
    }

    this.isOperationRunning.set(true);
    this.backupsApi
      .backupsDeleteMultipleCreate({ filenames: selectedFilenames })
      .pipe(
        catchError((err) => {
          this.toast.error('Failed to delete selected backups');
          return of(null);
        }),
        finalize(() => this.isOperationRunning.set(false)),
      )
      .subscribe((response: any) => {
        if (response) {
          const deletedCount = response.deleted?.length || 0;
          const errorCount = response.errors?.length || 0;
          if (errorCount === 0) {
            this.toast.success(`Deleted ${deletedCount} backup(s)`);
          } else {
            this.toast.info(`Deleted ${deletedCount} backup(s), ${errorCount} failed`);
          }
          this.backups.update((backups) => backups.map((b) => ({ ...b, selected: false })));
          this.selectedFiles.set([]);
          this.selectAllValue.set(false);
          this.loadBackups();
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

  private clearSseSubscription(): void {
    if (this.sseSubscription) {
      this.sseSubscription.unsubscribe();
      this.sseSubscription = null;
    }
  }
}
