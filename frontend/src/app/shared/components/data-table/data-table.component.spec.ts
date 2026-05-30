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
  let viewportApi: {
    scrollToIndex: ReturnType<typeof vi.fn>;
    checkViewportSize: ReturnType<typeof vi.fn>;
  };

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

  const setTableWrapperTop = (top: number) => {
    const el = document.createElement('div');
    Object.defineProperty(el, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top, bottom: top + 100, left: 0, right: 100, width: 100, height: 100 }),
    });
    const queryList = new QueryList<ElementRef<HTMLElement>>();
    queryList.reset([new ElementRef(el)]);
    queryList.notifyOnChanges();
    (component as any).tableWrapper = queryList;
  };

  const setMeasuredTableWrapper = (top: number, headerHeight: number, rowHeights: number[]) => {
    const wrapper = document.createElement('div');
    Object.defineProperty(wrapper, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({ top, bottom: top + 100, left: 0, right: 100, width: 100, height: 100 }),
    });

    const header = document.createElement('thead');
    header.setAttribute('z-table-header', '');
    Object.defineProperty(header, 'getBoundingClientRect', {
      configurable: true,
      value: () => ({
        top,
        bottom: headerHeight,
        left: 0,
        right: 100,
        width: 100,
        height: headerHeight,
      }),
    });
    wrapper.appendChild(header);

    const body = document.createElement('tbody');
    body.setAttribute('z-table-body', '');

    rowHeights.forEach((rowHeight) => {
      const row = document.createElement('tr');
      row.setAttribute('z-table-row', '');
      Object.defineProperty(row, 'getBoundingClientRect', {
        configurable: true,
        value: () => ({
          top: 0,
          bottom: rowHeight,
          left: 0,
          right: 100,
          width: 100,
          height: rowHeight,
        }),
      });
      body.appendChild(row);
    });

    wrapper.appendChild(body);

    const queryList = new QueryList<ElementRef<HTMLElement>>();
    queryList.reset([new ElementRef(wrapper)]);
    queryList.notifyOnChanges();
    (component as any).tableWrapper = queryList;
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
      itemSizePx: () => 50,
      preferredVisibleRowCount: () => 11,
      minimumVisibleRowCount: () => 0,
      useMeasuredHeights: () => false,
      tableHeaderHeightPx: () => 48,
      viewportBottomSpacingPx: () => 96,
      pageChange: { emit: (page: number) => (lastPageEmitted = page) },
    });
    viewportApi = { scrollToIndex: vi.fn(), checkViewportSize: vi.fn() };
    (component as any).viewport = () => viewportApi;
    document.documentElement.style.setProperty('--app-ui-scale', '1');
  });

  afterEach(() => {
    component.ngOnDestroy();
    document.documentElement.style.removeProperty('--app-ui-scale');
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

  it('keeps a stable visual table height while enough viewport height is available', () => {
    currentData = Array.from({ length: 10 }, (_, index) => ({ id: index + 1 }));
    setTableWrapperTop(220);
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      writable: true,
      value: 900,
    });
    document.documentElement.style.setProperty('--app-ui-scale', '0.75');

    (component as any).refreshViewportMetrics();

    expect(component.preferredTableVisualHeightPx()).toBe(548);
    expect(component.tableViewportHeightPx()).toBeCloseTo(730.6667, 3);
    expect(viewportApi.checkViewportSize).toHaveBeenCalled();
  });

  it('uses the slightly taller shared default when enough rows are available', () => {
    currentData = Array.from({ length: 20 }, (_, index) => ({ id: index + 1 }));

    expect(component.preferredTableVisualHeightPx()).toBe(598);
  });

  it('reserves extra height when a list requests a minimum visible row floor', () => {
    currentData = Array.from({ length: 10 }, (_, index) => ({ id: index + 1 }));
    Object.assign(component, {
      minimumVisibleRowCount: () => 11,
    });

    expect(component.preferredTableVisualHeightPx()).toBe(598);
  });

  it('does not reserve extra empty height for no-results states', () => {
    currentData = [];
    Object.assign(component, {
      minimumVisibleRowCount: () => 11,
    });

    expect(component.preferredTableVisualHeightPx()).toBe(98);
  });

  it('uses measured header and row heights when enabled for per-view visual alignment', () => {
    currentData = Array.from({ length: 9 }, (_, index) => ({ id: index + 1 }));
    Object.assign(component, {
      preferredVisibleRowCount: () => 9,
      minimumVisibleRowCount: () => 9,
      useMeasuredHeights: () => true,
    });
    setMeasuredTableWrapper(220, 44, [62, 62, 62]);
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      writable: true,
      value: 1000,
    });

    (component as any).refreshViewportMetrics();

    expect(component.effectiveTableHeaderVisualHeightPx()).toBe(44);
    expect(component.effectiveItemVisualHeightPx()).toBe(62);
    expect(component.preferredTableVisualHeightPx()).toBe(602);
    expect(component.tableViewportHeightPx()).toBe(602);
  });

  it('caps the table height and enables in-table scrolling when the window is shorter than the preferred table height', () => {
    currentData = Array.from({ length: 20 }, (_, index) => ({ id: index + 1 }));
    setTableWrapperTop(260);
    Object.defineProperty(window, 'innerHeight', {
      configurable: true,
      writable: true,
      value: 560,
    });
    document.documentElement.style.setProperty('--app-ui-scale', '0.8');

    (component as any).refreshViewportMetrics();

    expect(component.preferredTableVisualHeightPx()).toBe(598);
    expect(component.tableViewportHeightPx()).toBeCloseTo(255, 3);
    expect(viewportApi.checkViewportSize).toHaveBeenCalled();
  });
});
