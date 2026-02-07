import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  AfterViewInit,
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  ElementRef,
  inject,
  input,
  OnDestroy,
  output,
  PLATFORM_ID,
  QueryList,
  signal,
  ViewChildren,
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
  /**
   * Optional keyboard shortcut (single character). If provided, this overrides the default
   * behavior of using the first letter of the label as the shortcut.
   */
  shortcut?: string;
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
export class DataTableComponent<T = Record<string, any>> implements AfterViewInit, OnDestroy {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly isBrowser = isPlatformBrowser(this.platformId);

  data = input.required<readonly T[]>();
  columns = input.required<readonly ColumnConfig<T>[]>();
  actions = input<readonly DataTableAction<T>[] | null>(null);
  totalItems = input<number>(0);
  isLoading = input<boolean>(false);
  skeletonRows = input<number>(10);

  // Pagination inputs for keyboard navigation
  currentPage = input<number>(1);
  totalPages = input<number>(1);

  pageChange = output<number>();
  sortChange = output<SortEvent>();

  private sortState = signal<SortEvent | null>(null);
  currentSort = computed(() => this.sortState());

  // Speed dial / selection
  selectedRow = signal<T | null>(null);

  /**
   * Internal flag to refocus the first row after data finishes loading.
   */
  private _refocusFirstRowAfterLoad = false;

  /**
   * If we need to focus a specific row by id but the table is still loading or the row is not present yet,
   * store the id here and try again once the data has updated.
   */
  private _pendingFocusId: number | string | null = null;

  // references to row elements for focus management
  @ViewChildren('rowRef', { read: ElementRef })
  private rowElements!: QueryList<ElementRef<HTMLElement>>;

  @ViewChildren('tableWrapper', { read: ElementRef })
  private tableWrapper!: QueryList<ElementRef<HTMLElement>>;

  constructor() {
    effect(() => {
      const d = this.data();
      const loading = this.isLoading();

      // If we have a pending focus id, try to find it after load finishes
      if (!loading) {
        if (this._pendingFocusId !== null) {
          const id = this._pendingFocusId;
          this._pendingFocusId = null;
          const index = (d || []).findIndex((r: any) => r && (r.id === id || r.id === Number(id)));
          if (index !== -1) {
            // Delay to allow DOM update
            setTimeout(() => this.focusRowByIndex(index), 10);
          }
        } else if (this._refocusFirstRowAfterLoad) {
          this._refocusFirstRowAfterLoad = false;
          if (d.length > 0) {
            // Delay to allow DOM update
            setTimeout(() => this.focusRowByIndex(0), 10);
          }
        }
      }

      if (d && d.length === 1) {
        this.selectedRow.set(d[0]);
      }
    });
  }

  ngAfterViewInit(): void {
    // Component initialization
  }

  ngOnDestroy(): void {
    // Cleanup
  }

  /**
   * Keyboard navigation for sections and arrows.
   */
  handleTableKeydown(event: KeyboardEvent): void {
    const key = event.key;

    // Section cycling: Tab jumps out of table
    if (key === 'Tab') {
      event.preventDefault();
      event.stopPropagation();

      if (event.shiftKey) {
        // Shift+Tab -> Search
        const search = document.querySelector('app-search-toolbar input') as HTMLElement;
        search?.focus();
      } else {
        // Tab -> Sidebar
        const sidebar = document.querySelector('aside a, aside button') as HTMLElement;
        sidebar?.focus();
      }
      return;
    }

    // Arrow navigation
    if (key === 'ArrowDown') {
      event.preventDefault();
      this.focusNextRow();
      return;
    }
    if (key === 'ArrowUp') {
      event.preventDefault();
      this.focusPreviousRow();
      return;
    }
  }

  focusFirstRowIfNone(): void {
    const data = this.data();

    // If the table is loading, flag it for focus after load finishes
    if (this.isLoading()) {
      this._refocusFirstRowAfterLoad = true;
      return;
    }

    if (!data || data.length === 0) return;

    // If a row is already selected, focus it. Otherwise focus the first one.
    const selected = this.selectedRow();
    const index = selected ? data.indexOf(selected) : -1;
    this.focusRowByIndex(index !== -1 ? index : 0);
  }

  /**
   * Focus a row by its id. If the table is still loading or the row isn't found yet, a pending
   * focus will be stored and retried once the data updates.
   */
  focusRowById(id: number | string): void {
    const data = this.data() ?? [];

    // If loading, store pending id and return
    if (this.isLoading()) {
      this._pendingFocusId = id;
      return;
    }

    const index = data.findIndex((r: any) => r && (r.id === id || r.id === Number(id)));
    if (index !== -1) {
      this.focusRowByIndex(index);
      return;
    }

    // Not found yet; set as pending so we'll attempt after the next load
    this._pendingFocusId = id;
  }

  private focusRowByIndex(index: number): void {
    const data = this.data();
    if (!data || data.length === 0) return;

    // Normalize index
    const normalizedIndex = ((index % data.length) + data.length) % data.length;
    const rowData = data[normalizedIndex];

    // Update state immediately to trigger aria-selected and tabindex updates in template
    this.selectedRow.set(rowData);

    // Try to focus immediately if elements are ready
    const elements = this.rowElements?.toArray() ?? [];
    const el = elements[normalizedIndex]?.nativeElement as HTMLElement | undefined;

    if (el) {
      this._applyFocusToElement(el);
    } else {
      // Elements not ready, retry a few times
      this._retryFocus(normalizedIndex, 1);
    }
  }

  private _applyFocusToElement(el: HTMLElement): void {
    el.setAttribute('tabindex', '0');
    try {
      el.focus({ preventScroll: true });
      el.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    } catch (e) {}
  }

  private _retryFocus(index: number, attempt: number): void {
    if (attempt > 10) return;

    setTimeout(() => {
      const elements = this.rowElements?.toArray() ?? [];
      const el = elements[index]?.nativeElement as HTMLElement | undefined;
      if (el) {
        this._applyFocusToElement(el);
        if (this.isBrowser && document.activeElement !== el && attempt < 5) {
          this._retryFocus(index, attempt + 1);
        }
      } else {
        this._retryFocus(index, attempt + 1);
      }
    }, 50);
  }

  private focusNextRow(): void {
    const data = this.data() ?? [];
    if (!data.length) return;
    const elements = this.rowElements?.toArray() ?? [];
    const activeEl = (document.activeElement as HTMLElement | null) ?? undefined;
    const elementIndex = activeEl ? elements.findIndex((e) => e.nativeElement === activeEl) : -1;
    const next = elementIndex === -1 ? 0 : (elementIndex + 1) % data.length;
    this.focusRowByIndex(next);
  }

  private focusPreviousRow(): void {
    const data = this.data() ?? [];
    if (!data.length) return;
    const elements = this.rowElements?.toArray() ?? [];
    const activeEl = (document.activeElement as HTMLElement | null) ?? undefined;
    const elementIndex = activeEl ? elements.findIndex((e) => e.nativeElement === activeEl) : -1;
    const prev =
      elementIndex === -1 ? data.length - 1 : (elementIndex - 1 + data.length) % data.length;
    this.focusRowByIndex(prev);
  }

  // Handle keydown events coming from a focused row
  handleRowNavigationKeydown(event: KeyboardEvent): void {
    const key = event.key;

    if (key === 'ArrowDown' || key === 'Down') {
      event.preventDefault();
      event.stopPropagation();
      this.focusNextRow();
      return;
    }
    if (key === 'ArrowUp' || key === 'Up') {
      event.preventDefault();
      event.stopPropagation();
      this.focusPreviousRow();
      return;
    }

    if (key === 'Tab') {
      this.handleTableKeydown(event);
      return;
    }

    // Page navigation: Left/Right arrows
    if (key === 'ArrowLeft' || key === 'Left') {
      event.preventDefault();
      event.stopPropagation();

      if (event.shiftKey) {
        if (this.currentPage() > 1) {
          this._refocusFirstRowAfterLoad = true;
          this.pageChange.emit(1);
        }
      } else if (this.currentPage() > 1) {
        this._refocusFirstRowAfterLoad = true;
        this.pageChange.emit(this.currentPage() - 1);
      }
      return;
    }

    if (key === 'ArrowRight' || key === 'Right') {
      event.preventDefault();
      event.stopPropagation();

      if (event.shiftKey) {
        if (this.currentPage() < this.totalPages()) {
          this._refocusFirstRowAfterLoad = true;
          this.pageChange.emit(this.totalPages());
        }
      } else if (this.currentPage() < this.totalPages()) {
        this._refocusFirstRowAfterLoad = true;
        this.pageChange.emit(this.currentPage() + 1);
      }
      return;
    }
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

    // Only handle if no modifiers (except Shift, which we check separately)
    if (event.ctrlKey || event.altKey || event.metaKey) return;

    const rawKey = event.key || '';
    const key = rawKey.toUpperCase();

    // Space: open row actions menu
    if (
      (rawKey === ' ' || rawKey === 'Space' || rawKey === 'Spacebar') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      // Only open when row is selected or single-row table
      if (this.selectedRow() === row || this.data()?.length === 1) {
        event.preventDefault();
        event.stopPropagation();
        const tr = event.currentTarget as HTMLElement | null;
        const btn = tr?.querySelector('button[z-dropdown]') as HTMLElement | null;
        if (btn) {
          btn.click();
        }
      }
      return;
    }

    // If Shift is pressed, it might be a global shortcut (like Shift+N for New Customer)
    // so let it bubble. Speed dial shortcuts are plain letters.
    if (event.shiftKey) return;

    // Only handle if the row is selected or the table has a single row
    if (this.selectedRow() !== row && this.data()?.length !== 1) return;

    const actions = this.actions() ?? [];
    for (const action of actions) {
      const first = (action.shortcut ?? (action.label || '').charAt(0)).toUpperCase();
      if (first === key) {
        event.preventDefault();
        event.stopPropagation();
        this.onActionSelect(action, row, event as unknown as Event);
        break;
      }
    }
  }
}
