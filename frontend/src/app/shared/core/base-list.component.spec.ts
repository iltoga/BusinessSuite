import { PLATFORM_ID, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
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
}

describe('BaseListComponent', () => {
  let component: TestListHarness;
  let routerMock: { navigate: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    routerMock = { navigate: vi.fn() };
    Object.defineProperty(window.history, 'state', {
      value: {},
      writable: true,
    });

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Router, useValue: routerMock },
        { provide: AuthService, useValue: { isSuperuser: signal(false) } },
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
      ],
    });

    component = TestBed.runInInjectionContext(() => new TestListHarness());
    component.ngOnInit();
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
      inputElement.focus();
      component.handleGlobalKeydown(new KeyboardEvent('keydown', { key: 'N' }));
      expect(routerMock.navigate).not.toHaveBeenCalled();
    } finally {
      inputElement.remove();
    }
  });

  it('should restore navigation state from window history', () => {
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
});
