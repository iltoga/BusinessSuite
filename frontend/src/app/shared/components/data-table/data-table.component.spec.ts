import { ElementRef, PLATFORM_ID, QueryList } from '@angular/core';
import { TestBed } from '@angular/core/testing';

import { DataTableComponent, type ColumnConfig } from './data-table.component';

describe('DataTableComponent (keyboard shortcuts)', () => {
  let component: DataTableComponent<any>;
  let currentData: any[];
  let currentActions: any[] | null;
  let currentPage = 1;
  let totalPages = 1;
  let lastPageEmitted: number | null;

  const sampleRow = { id: 1, name: 'John Doe' };
  const columns: ColumnConfig[] = [{ key: 'name', header: 'Name' }];

  const setRowElements = (rows: Array<{ id: number }>) => {
    const elements = rows.map((row) => {
      const el = document.createElement('div');
      el.classList.toggle('selected', component.selectedRow()?.id === row.id);
      el.focus = vi.fn();
      return new ElementRef(el);
    });
    const queryList = new QueryList<ElementRef<HTMLElement>>();
    queryList.reset(elements);
    queryList.notifyOnChanges();
    (component as any).rowElements = queryList;
  };

  beforeEach(() => {
    vi.useFakeTimers();
    currentData = [];
    currentActions = null;
    currentPage = 1;
    totalPages = 1;
    lastPageEmitted = null;

    TestBed.configureTestingModule({
      providers: [{ provide: PLATFORM_ID, useValue: 'browser' }],
    });

    component = TestBed.runInInjectionContext(() => new DataTableComponent<any>());
    Object.assign(component, {
      data: () => currentData,
      columns: () => columns,
      actions: () => currentActions,
      currentPage: () => currentPage,
      totalPages: () => totalPages,
      isLoading: () => false,
      pageChange: { emit: (page: number) => (lastPageEmitted = page) },
    });
    (component as any).viewport = () => ({ scrollToIndex: vi.fn() });
  });

  afterEach(() => {
    component.ngOnDestroy();
    vi.useRealTimers();
  });

  it('should auto-select when only one row is present', () => {
    currentData = [sampleRow];
    component.focusFirstRowIfNone();
    expect(component.selectedRow()).toBe(sampleRow);
  });

  it('selectRow should focus the provided row element when available', () => {
    let focused = false;
    const tr: any = { focus: () => (focused = true), tabIndex: 0 };

    component.selectRow(sampleRow, { currentTarget: tr } as unknown as Event);

    expect(component.selectedRow()).toBe(sampleRow);
    expect(focused).toBe(true);
  });

  it('handleRowKeydown should trigger matching action by first letter', () => {
    let called = false;
    currentData = [sampleRow];
    currentActions = [
      { label: 'Edit', icon: 'settings', action: (row: any) => (called = row === sampleRow) },
      { label: 'Delete', icon: 'trash', action: () => undefined },
    ];

    component.handleRowKeydown(
      {
        key: 'E',
        target: { tagName: 'DIV' },
        preventDefault: () => undefined,
        stopPropagation: () => undefined,
      } as unknown as KeyboardEvent,
      sampleRow,
    );
    expect(called).toBe(true);
  });

  it('should preserve selected id after data reload', () => {
    currentData = [{ id: 1 }, { id: 2 }];
    component.selectedRow.set(currentData[1]);
    setRowElements(currentData);

    currentData = [{ id: 1 }, { id: 2 }];
    setRowElements(currentData);
    component.focusFirstRowIfNone();

    expect((component.selectedRow() as any)?.id).toBe(2);
  });

  it('ArrowUp should wrap to the previous row', () => {
    currentData = [{ id: 1 }, { id: 2 }, { id: 3 }];
    component.selectedRow.set(currentData[0]);
    setRowElements(currentData);

    component.handleRowNavigationKeydown({
      key: 'ArrowUp',
      preventDefault: () => undefined,
      stopPropagation: () => undefined,
    } as unknown as KeyboardEvent);

    vi.runAllTimers();
    expect(component.selectedRow()).toEqual(currentData[2]);
  });

  it('ArrowLeft and ArrowRight should emit pageChange', () => {
    currentData = [{ id: 1 }];
    currentPage = 2;
    totalPages = 3;

    component.handleRowNavigationKeydown({
      key: 'ArrowRight',
      preventDefault: () => undefined,
      stopPropagation: () => undefined,
    } as unknown as KeyboardEvent);
    expect(lastPageEmitted).toBe(3);

    lastPageEmitted = null;
    component.handleRowNavigationKeydown({
      key: 'ArrowLeft',
      preventDefault: () => undefined,
      stopPropagation: () => undefined,
    } as unknown as KeyboardEvent);
    expect(lastPageEmitted).toBe(1);
  });
});
