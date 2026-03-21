import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { catchError, EMPTY, finalize } from 'rxjs';

import { ServerManagementService } from '@/core/api/api/server-management.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon';

interface AdminAppSettingItem {
  name: string;
  value: string | null;
  effectiveValue: unknown;
  defaultValue: unknown;
  scope: 'backend' | 'frontend' | 'both' | string;
  description: string;
  source: 'hardcoded' | 'django' | 'env' | 'database' | string;
}

@Component({
  selector: 'app-application-settings',
  standalone: true,
  imports: [
    CommonModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardIconComponent,
    ...ZardDropdownImports,
  ],
  templateUrl: './application-settings.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationSettingsComponent implements OnInit {
  private readonly serverManagementApi = inject(ServerManagementService);
  private readonly toast = inject(GlobalToastService);

  readonly appSettings = signal<AdminAppSettingItem[]>([]);
  readonly appSettingsLoading = signal(false);
  readonly appSettingDraft = signal({ name: '', value: '', scope: 'backend', description: '' });

  ngOnInit(): void {
    this.loadAppSettings();
  }

  loadAppSettings(): void {
    this.appSettingsLoading.set(true);
    this.serverManagementApi
      .serverManagementAppSettingsRetrieve()
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load app settings');
          return EMPTY;
        }),
        finalize(() => this.appSettingsLoading.set(false)),
      )
      .subscribe((response) => {
        const payload = unwrapApiRecord(response) as { items?: AdminAppSettingItem[] } | null;
        this.appSettings.set(Array.isArray(payload?.items) ? payload.items : []);
      });
  }

  createAppSetting(): void {
    const draft = this.appSettingDraft();
    const name = String(draft.name || '')
      .trim()
      .toUpperCase();
    if (!name) {
      this.toast.error('Setting name is required');
      return;
    }

    this.serverManagementApi
      .serverManagementAppSettingsCreate({
        name,
        value: draft.value,
        scope: draft.scope,
        description: draft.description,
      })
      .pipe(
        catchError((error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to create app setting');
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.toast.success('App setting saved');
        this.appSettingDraft.set({ name: '', value: '', scope: 'backend', description: '' });
        this.loadAppSettings();
      });
  }

  updateAppSetting(item: AdminAppSettingItem, value: string): void {
    this.serverManagementApi
      .serverManagementAppSettingsPartialUpdate(item.name, {
        value,
        scope: item.scope,
        description: item.description,
      })
      .pipe(
        catchError((error) => {
          this.toast.error(extractServerErrorMessage(error) || `Failed to update ${item.name}`);
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.toast.success(`Updated ${item.name}`);
        this.loadAppSettings();
      });
  }

  deleteAppSetting(name: string): void {
    this.serverManagementApi
      .serverManagementAppSettingsDestroy(name)
      .pipe(
        catchError((error) => {
          this.toast.error(extractServerErrorMessage(error) || `Failed to delete ${name}`);
          return EMPTY;
        }),
      )
      .subscribe(() => {
        this.toast.success(`Deleted ${name}`);
        this.loadAppSettings();
      });
  }

  setAppSettingDraftField(field: 'name' | 'value' | 'scope' | 'description', event: Event): void {
    const target = event.target as HTMLInputElement | HTMLSelectElement;
    const value = String(target.value ?? '');
    this.appSettingDraft.update((current) => ({ ...current, [field]: value }));
  }
}
