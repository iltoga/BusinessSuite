import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpParams } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

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
export class AiModelListComponent {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);
  private readonly toast = inject(GlobalToastService);
  private readonly platformId = inject(PLATFORM_ID);

  private readonly isBrowser = isPlatformBrowser(this.platformId);
  private readonly dataTable = viewChild.required(DataTableComponent<AiModelItem>);

  readonly items = signal<AiModelItem[]>([]);
  readonly query = signal('');
  readonly loading = signal(false);
  readonly ordering = signal('provider,name');

  readonly pendingDelete = signal<AiModelItem | null>(null);
  readonly showDeleteConfirm = computed(() => this.pendingDelete() !== null);

  readonly columns = computed<ColumnConfig<AiModelItem>[]>(() => [
    { key: 'provider', header: 'Provider', sortable: true, sortKey: 'provider' },
    { key: 'name', header: 'Name', sortable: true, sortKey: 'name' },
    { key: 'model_id', header: 'Model ID', sortable: true, sortKey: 'model_id' },
    { key: 'description', header: 'Description' },
    { key: 'actions', header: 'Actions' },
  ]);

  readonly actions = computed<DataTableAction<AiModelItem>[]>(() => [
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
    this.load();
  }

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    if (!this.isBrowser) return;

    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.createNew();
    }
  }

  onQueryChange(value: string): void {
    this.query.set(value.trim());
    this.load();
  }

  onEnterSearch(): void {
    this.dataTable().focusFirstRowIfNone();
  }

  onSortChange(event: SortEvent): void {
    const sortPrefix = event.direction === 'desc' ? '-' : '';
    this.ordering.set(`${sortPrefix}${event.column}`);
    this.load();
  }

  createNew(): void {
    this.router.navigate(['/admin/ai-models/new']);
  }

  edit(item: AiModelItem): void {
    this.router.navigate(['/admin/ai-models', item.id, 'edit']);
  }

  requestDelete(item: AiModelItem): void {
    this.pendingDelete.set(item);
  }

  cancelDelete(): void {
    this.pendingDelete.set(null);
  }

  confirmDelete(): void {
    const model = this.pendingDelete();
    if (!model) return;

    this.loading.set(true);
    this.http.delete(`/api/ai-models/${model.id}/`).subscribe({
      next: () => {
        this.toast.success('Model deleted');
        this.pendingDelete.set(null);
        this.load();
      },
      error: (error) => {
        this.loading.set(false);
        this.toast.error(extractServerErrorMessage(error) || 'Failed to delete model');
      },
    });
  }

  private load(): void {
    let params = new HttpParams().set('ordering', this.ordering());
    const search = this.query();
    if (search) {
      params = params.set('search', search);
    }

    this.loading.set(true);
    this.http.get<AiModelItem[]>('/api/ai-models/', { params }).subscribe({
      next: (rows) => {
        this.items.set(rows ?? []);
        this.loading.set(false);
      },
      error: (error) => {
        this.loading.set(false);
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load models');
      },
    });
  }
}
