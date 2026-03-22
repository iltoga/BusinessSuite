import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { map, type Observable } from 'rxjs';

import { AiModelsService } from '@/core/api/api/ai-models.service';
import type { AiModel } from '@/core/api/model/ai-model';
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
import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from '@/shared/core/base-list.component';
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
  private readonly aiModelsApi = inject(AiModelsService);

  // AI Model-specific state
  readonly pendingDelete = signal<AiModelItem | null>(null);
  readonly showDeleteConfirm = computed(() => this.pendingDelete() !== null);

  // Columns configuration
  readonly columns = computed<ColumnConfig<AiModelItem>[]>(() => [
    { key: 'provider', header: 'Provider', sortable: true, sortKey: 'provider', width: '12%' },
    { key: 'name', header: 'Name', sortable: true, sortKey: 'name', width: '20%' },
    { key: 'model_id', header: 'Model ID', sortable: true, sortKey: 'model_id', width: '25%' },
    { key: 'description', header: 'Description', width: '35%' },
    { key: 'actions', header: 'Actions', width: '4%' },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<AiModelItem>[]>(() => [
    {
      label: 'View details',
      icon: 'eye',
      variant: 'default',
      shortcut: 'v',
      action: (item) =>
        this.router.navigate(['/admin/ai-models', item.id], {
          state: {
            from: 'admin-ai-models',
            focusId: item.id,
            searchQuery: this.query(),
          },
        }),
    },
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
   * Create the Observable that fetches AI models.
   * The API returns a flat array, so we wrap it in a PaginatedResponse.
   */
  protected override createListLoader(
    params: ListRequestParams,
  ): Observable<PaginatedResponse<AiModelItem>> {
    const ordering = params.ordering ?? 'provider,name';
    const search = params.query;

    return this.aiModelsApi.aiModelsList(ordering, search || undefined).pipe(
      map((rows) => {
        const mappedRows = (rows ?? []).map((item) => this.mapAiModel(item));
        return {
          results: mappedRows,
          count: mappedRows.length,
        };
      }),
    );
  }

  /**
   * Handle sort change
   */
  override onSortChange(event: SortEvent): void {
    const sortPrefix = event.direction === 'desc' ? '-' : '';
    this.ordering.set(`${sortPrefix}${event.column}`);
    this.reload();
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

    this.aiModelsApi.aiModelsDestroy(model.id).subscribe({
      next: () => {
        this.toast.success('Model deleted');
        this.pendingDelete.set(null);
        this.reload();
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to delete model');
      },
    });
  }

  private mapAiModel(item: AiModel): AiModelItem {
    return {
      id: item.id,
      provider: item.provider,
      model_id: item.modelId,
      name: item.name,
      description: item.description ?? '',
    };
  }
}
