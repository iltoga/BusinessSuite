import { PLATFORM_ID, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of, type Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import type { ColumnConfig } from '@/shared/components/data-table/data-table.component';

import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from './base-list.component';

interface TestItem {
  id: number;
  name: string;
}

class TestListHarness extends BaseListComponent<TestItem> {
  readonly columns = signal<ColumnConfig<TestItem>[]>([]);
  public testBulkDeleteQuery = this.bulkDeleteQuery;

  constructor() {
    super();
    this.config = {
      entityType: 'test-items',
      entityLabel: 'Test Items',
      defaultPageSize: 8,
      defaultOrdering: 'name',
    } as BaseListConfig<TestItem>;
  }

  protected override createListLoader(
    _params: ListRequestParams,
  ): Observable<PaginatedResponse<TestItem>> {
    return of({
      results: [
        { id: 1, name: 'Item 1' },
        { id: 2, name: 'Item 2' },
      ],
      count: 2,
    });
  }

  protected override focusAfterLoad(): void {}

  public testGetNewRoute(): string {
    return this.getNewRoute();
  }

  public testGetListRoute(): string {
    return this.getListRoute();
  }

  public testGetEditRoute(id: number): string {
    return this.getEditRoute(id);
  }

  public testGetDetailRoute(id: number): string {
    return this.getDetailRoute(id);
  }

  public testGetEntityTypeLabel(): string {
    return this.getEntityTypeLabel();
  }

  public testBuildUrlParams(): Record<string, string | null> {
    return this.buildUrlParams();
  }
}

function createRouteMock(queryParams: Record<string, string> = {}) {
  return { snapshot: { queryParams } };
}

describe('BaseListComponent', () => {
  let component: TestListHarness;
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let routeMock: ReturnType<typeof createRouteMock>;

  beforeEach(() => {
    sessionStorage.clear();
    routerMock = { navigate: vi.fn() };
    routeMock = createRouteMock();
    Object.defineProperty(window.history, 'state', {
      value: {},
      writable: true,
    });

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Router, useValue: routerMock },
        { provide: ActivatedRoute, useValue: routeMock },
        { provide: AuthService, useValue: { isSuperuser: signal(false) } },
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
      ],
    });

    component = TestBed.runInInjectionContext(() => new TestListHarness());
    component.ngOnInit();
  });

  afterEach(() => {
    sessionStorage.clear();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with default config values', () => {
    expect(component.pageSize()).toBe(8);
    expect(component.ordering()).toBe('name');
    expect(component.page()).toBe(1);
    expect(component.query()).toBe('');
  });

  it('should have totalPages computed correctly', () => {
    component.totalItems.set(25);
    component.pageSize.set(10);
    expect(component.totalPages()).toBe(3);
  });

  it('should build correct routes', () => {
    expect(component.testGetNewRoute()).toBe('/test-items/new');
    expect(component.testGetListRoute()).toBe('/test-items');
    expect(component.testGetEditRoute(123)).toBe('/test-items/123/edit');
    expect(component.testGetDetailRoute(456)).toBe('/test-items/456');
    expect(component.testGetEntityTypeLabel()).toBe('Test Items');
  });

  it('should handle query, page, and sort changes', () => {
    component.onQueryChange('  test search  ');
    expect(component.query()).toBe('test search');
    expect(component.page()).toBe(1);

    component.onPageChange(3);
    expect(component.page()).toBe(3);

    component.onSortChange({ column: 'name', direction: 'desc' });
    expect(component.ordering()).toBe('-name');
    expect(component.page()).toBe(1);
  });

  it('should update URL query params on state changes', () => {
    routerMock.navigate.mockClear();

    component.onQueryChange('search term');
    expect(routerMock.navigate).toHaveBeenCalledWith([], {
      relativeTo: routeMock,
      queryParams: expect.objectContaining({ q: 'search term', page: null }),
      replaceUrl: true,
    });

    routerMock.navigate.mockClear();
    component.onPageChange(5);
    expect(routerMock.navigate).toHaveBeenCalledWith([], {
      relativeTo: routeMock,
      queryParams: expect.objectContaining({ page: '5' }),
      replaceUrl: true,
    });

    routerMock.navigate.mockClear();
    component.onSortChange({ column: 'id', direction: 'desc' });
    expect(routerMock.navigate).toHaveBeenCalledWith([], {
      relativeTo: routeMock,
      queryParams: expect.objectContaining({ sort: '-id' }),
      replaceUrl: true,
    });
  });

  it('should omit default values from URL params', () => {
    const params = component.testBuildUrlParams();
    expect(params['q']).toBeNull();
    expect(params['page']).toBeNull();
    expect(params['sort']).toBeNull();
  });

  it('should open and cancel bulk delete state', () => {
    component.totalItems.set(100);
    component.openBulkDeleteDialog('Test Items', 'Test details');

    expect(component.bulkDeleteOpen()).toBe(true);
    expect(component.bulkDeleteData()).toEqual(
      expect.objectContaining({
        entityLabel: 'Test Items',
        totalCount: 100,
        mode: 'all',
      }),
    );

    component.onBulkDeleteCancelled();
    expect(component.bulkDeleteOpen()).toBe(false);
    expect(component.bulkDeleteData()).toBeNull();
    expect(component.testBulkDeleteQuery()).toBe('');
  });

  it('should ignore global shortcuts while an input is focused', () => {
    const inputElement = document.createElement('input');
    document.body.appendChild(inputElement);

    try {
      routerMock.navigate.mockClear();
      inputElement.focus();
      component.handleGlobalKeydown(new KeyboardEvent('keydown', { key: 'N' }));
      expect(routerMock.navigate).not.toHaveBeenCalled();
    } finally {
      inputElement.remove();
    }
  });

  it('should restore navigation state from window history when no URL params', () => {
    Object.defineProperty(window.history, 'state', {
      value: {
        focusTable: true,
        focusId: 123,
        page: 5,
        searchQuery: 'restored search',
      },
      writable: true,
    });

    component.ngOnInit();

    expect(component.page()).toBe(5);
    expect(component.query()).toBe('restored search');
  });

  it('should restore state from URL query params', () => {
    routeMock.snapshot.queryParams = { q: 'url search', page: '3', sort: '-id' };
    component.ngOnInit();

    expect(component.query()).toBe('url search');
    expect(component.page()).toBe(3);
    expect(component.ordering()).toBe('-id');
  });

  it('should prefer URL params over history state', () => {
    routeMock.snapshot.queryParams = { q: 'from-url', page: '7' };
    Object.defineProperty(window.history, 'state', {
      value: { searchQuery: 'from-state', page: 2 },
      writable: true,
    });

    component.ngOnInit();

    expect(component.query()).toBe('from-url');
    expect(component.page()).toBe(7);
  });

  it('keeps unrelated column filters when one filter is cleared', () => {
    component.onColumnFilterChange({ column: 'status', values: ['active'] });
    component.onColumnFilterChange({ column: 'category', values: ['visa'] });

    expect(component.columnFilters()).toEqual({
      status: ['active'],
      category: ['visa'],
    });

    component.onColumnFilterChange({ column: 'status', values: [] });

    expect(component.columnFilters()).toEqual({
      category: ['visa'],
    });
  });

  it('should include query params in goBack navigation', () => {
    component.onQueryChange('persisted');
    component.onPageChange(4);
    routerMock.navigate.mockClear();

    component.handleGlobalKeydown(new KeyboardEvent('keydown', { key: 'B' }));

    expect(routerMock.navigate).toHaveBeenCalledWith(
      ['/test-items'],
      expect.objectContaining({
        queryParams: expect.objectContaining({ q: 'persisted', page: '4' }),
      }),
    );
  });
});
