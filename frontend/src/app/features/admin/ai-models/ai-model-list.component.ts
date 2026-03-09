import { CommonModule } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  type WritableSignal,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import {
  BaseListComponent,
  BaseListConfig,
} from '@/shared/core/base-list.component';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  DataTableComponent,
  type ColumnConfig,
  type DataTableAction,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

interface AiModelItem {
  id: number;
  provider: string;
  model_id: string;
  name: string;
  description: string;
}

/**
 * AI Model list component
 * 
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 */
@Component({
  selector: 'app-ai-model-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    SearchToolbarComponent,
    ZardButtonComponent,
    ZardCardComponent,
    DataTableComponent,
    ConfirmDialogComponent,
  ],
  templateUrl: './ai-model-list.component.html',
  styleUrls: ['./ai-model-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModelListComponent extends BaseListComponent<AiModelItem> {
  private readonly http = inject(HttpClient);

  // AI Model-specific state
  readonly pendingDelete = signal<AiModelItem | null>(null);
  readonly showDeleteConfirm = computed(() => this.pendingDelete() !== null);

  // Columns configuration
  readonly columns = computed<ColumnConfig<AiModelItem>[]>(() => [
    { key: 'provider', header: 'Provider', sortable: true, sortKey: 'provider' },
    { key: 'name', header: 'Name', sortable: true, sortKey: 'name' },
    { key: 'model_id', header: 'Model ID', sortable: true, sortKey: 'model_id' },
    { key: 'description', header: 'Description' },
    { key: 'actions', header: 'Actions' },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<AiModelItem>[]>(() => [
    {
      label: 'Edit',
      icon: 'settings',
      variant: 'warning',
      shortcut: 'e',
      action: (item) => this.edit(item),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      shortcut: 'd',
      action: (item) => this.requestDelete(item),
    },
  ]);

  constructor() {
    super();
    this.config = {
      entityType: 'admin/ai-models',
      entityLabel: 'AI Models',
      defaultOrdering: 'provider,name',
    } as BaseListConfig<AiModelItem>;
  }

  /**
   * Load AI models from API
   */
  protected override loadItems(): void {
    if (!this.isBrowser) return;

    const ordering = this.ordering() ?? 'provider,name';
    let params = new HttpParams().set('ordering', ordering);
    const search = this.query();
    if (search) {
      params = params.set('search', search);
    }

    this.isLoading.set(true);
    this.http.get<AiModelItem[]>('/api/ai-models/', { params }).subscribe({
      next: (rows) => {
        this.items.set(rows ?? []);
        this.totalItems.set(rows?.length ?? 0);
        this.isLoading.set(false);
        this.focusAfterLoad();
      },
      error: (error) => {
        this.isLoading.set(false);
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load models');
      },
    });
  }

  /**
   * Handle sort change
   */
  override onSortChange(event: SortEvent): void {
    const sortPrefix = event.direction === 'desc' ? '-' : '';
    this.ordering.set(`${sortPrefix}${event.column}`);
    this.loadItems();
  }

  /**
   * Handle enter in search to focus table
   */
  onEnterSearch(): void {
    this.dataTable().focusFirstRowIfNone();
  }

  /**
   * Create new AI model
   */
  createNew(): void {
    this.router.navigate(['/admin/ai-models/new']);
  }

  /**
   * Edit AI model
   */
  edit(item: AiModelItem): void {
    this.router.navigate(['/admin/ai-models', item.id, 'edit']);
  }

  /**
   * Request delete for AI model
   */
  requestDelete(item: AiModelItem): void {
    this.pendingDelete.set(item);
  }

  /**
   * Cancel delete
   */
  cancelDelete(): void {
    this.pendingDelete.set(null);
  }

  /**
   * Confirm delete
   */
  confirmDelete(): void {
    const model = this.pendingDelete();
    if (!model) return;

    this.isLoading.set(true);
    this.http.delete(`/api/ai-models/${model.id}/`).subscribe({
      next: () => {
        this.toast.success('Model deleted');
        this.pendingDelete.set(null);
        this.loadItems();
      },
      error: (error) => {
        this.isLoading.set(false);
        this.toast.error(extractServerErrorMessage(error) || 'Failed to delete model');
      },
    });
  }
}
