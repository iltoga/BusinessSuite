import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
  type TemplateRef,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ShortcutHighlightPipe } from './shortcut-highlight.pipe';

import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent, type ZardIcon } from '@/shared/components/icon';
import { ZardSkeletonComponent } from '@/shared/components/skeleton';
import { ZardTableImports } from '@/shared/components/table';

export interface ColumnConfig<T = any> {
  key: string;
  header: string;
  subtitle?: string;
  sortable?: boolean;
  sortKey?: string;
  template?: TemplateRef<{ $implicit: T; value: any; row: T }>;
}

export interface PageEvent {
  page: number;
  pageSize: number;
}

export type DataTableActionVariant =
  | 'default'
  | 'secondary'
  | 'destructive'
  | 'warning'
  | 'success'
  | 'outline'
  | 'ghost';

export interface DataTableAction<T = any> {
  label: string;
  icon: ZardIcon;
  action: (item: T) => void;
  isDestructive?: boolean;
  variant?: DataTableActionVariant;
}

export interface SortEvent {
  column: string;
  direction: 'asc' | 'desc';
}

@Component({
  selector: 'app-data-table',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ZardButtonComponent,
    ZardIconComponent,
    ...ZardDropdownImports,
    ...ZardTableImports,
    ZardSkeletonComponent,
    ZardCheckboxComponent,
    // shortcut pipe for highlighting first letter
    ShortcutHighlightPipe,
  ],
  templateUrl: './data-table.component.html',
  styleUrls: ['./data-table.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataTableComponent<T = Record<string, any>> {
  data = input.required<readonly T[]>();
  columns = input.required<readonly ColumnConfig<T>[]>();
  actions = input<readonly DataTableAction<T>[] | null>(null);
  totalItems = input<number>(0);
  isLoading = input<boolean>(false);
  skeletonRows = input<number>(10);

  // Speed dial / selection
  selectedRow = signal<T | null>(null);

  pageChange = output<PageEvent>();
  sortChange = output<SortEvent>();

  private sortState = signal<SortEvent | null>(null);
  currentSort = computed(() => this.sortState());

  constructor() {
    // If table has exactly one item, preselect it
    // Note: runs every time `data` changes
    effect(() => {
      const d = this.data();
      if (d && d.length === 1) {
        this.selectedRow.set(d[0]);
      }
    });
  }

  onSort(column: ColumnConfig<T>): void {
    if (!column.sortable) return;

    const current = this.sortState();
    const direction =
      current?.column === (column.sortKey ?? column.key) && current.direction === 'asc'
        ? 'desc'
        : 'asc';
    const nextSort: SortEvent = { column: column.sortKey ?? column.key, direction };
    this.sortState.set(nextSort);
    this.sortChange.emit(nextSort);
  }

  getCellValue(row: T, key: string): string {
    const value = (row as Record<string, unknown>)[key];
    return value === null || value === undefined ? '' : String(value);
  }

  getRawValue(row: T, key: string): unknown {
    return (row as Record<string, unknown>)[key];
  }

  onActionSelect(action: DataTableAction<T>, row: T, event?: Event): void {
    event?.stopPropagation();
    action.action(row);
  }

  selectRow(row: T, event?: Event): void {
    this.selectedRow.set(row);

    // Try to focus the row element if available from the event
    const target = (event?.currentTarget ?? event?.target) as HTMLElement | undefined;
    if (target && typeof target.focus === 'function') {
      target.focus();
    }
  }

  handleRowKeydown(event: KeyboardEvent, row: T): void {
    const tag = (event.target as HTMLElement)?.tagName ?? '';
    if (tag === 'INPUT' || tag === 'TEXTAREA') return;

    const key = (event.key || '').toUpperCase();

    // Only handle if the row is selected or the table has a single row
    if (this.selectedRow() !== row && this.data()?.length !== 1) return;

    const actions = this.actions() ?? [];
    for (const action of actions) {
      const first = (action.label || '').charAt(0).toUpperCase();
      if (first === key) {
        event.preventDefault();
        event.stopPropagation();
        this.onActionSelect(action, row, event as unknown as Event);
        break;
      }
    }
  }
}
