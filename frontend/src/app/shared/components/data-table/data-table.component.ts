import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  output,
  signal,
  type TemplateRef,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import { ZardCheckboxComponent } from '@/shared/components/checkbox';
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
    ...ZardTableImports,
    ZardSkeletonComponent,
    ZardCheckboxComponent,
  ],
  templateUrl: './data-table.component.html',
  styleUrls: ['./data-table.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DataTableComponent<T = Record<string, any>> {
  data = input.required<readonly T[]>();
  columns = input.required<readonly ColumnConfig<T>[]>();
  totalItems = input<number>(0);
  isLoading = input<boolean>(false);
  skeletonRows = input<number>(10);

  pageChange = output<PageEvent>();
  sortChange = output<SortEvent>();

  private sortState = signal<SortEvent | null>(null);
  currentSort = computed(() => this.sortState());

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
}
