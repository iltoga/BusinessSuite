import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  DataTableComponent,
  type ColumnConfig,
} from '@/shared/components/data-table/data-table.component';
import { Component, signal } from '@angular/core';
import { of, type Observable } from 'rxjs';
import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from './base-list.component';

// Mock test component extending BaseListComponent
interface TestItem {
  id: number;
  name: string;
}

@Component({
  selector: 'app-test-list',
  standalone: true,
  imports: [DataTableComponent],
  template: '<app-data-table [data]="items()" [columns]="columns()" [isLoading]="isLoading()" />',
})
class TestListComponent extends BaseListComponent<TestItem> {
  readonly columns = signal<ColumnConfig<TestItem>[]>([]);

  // Expose protected property for testing
  public testBulkDeleteQuery = this.bulkDeleteQuery;

  constructor() {
    super();
    this.config = {
      entityType: 'test-items',
      entityLabel: 'Test Items',
      defaultPageSize: 10,
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

  // Expose protected methods for testing
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
  let component: TestListComponent;
  let fixture: ComponentFixture<TestListComponent>;

  beforeEach(async () => {
    Object.defineProperty(window.history, 'state', {
      value: {},
      writable: true,
    });

    await TestBed.configureTestingModule({
      imports: [TestListComponent],
      providers: [
        provideRouter([{ path: '**', redirectTo: '' }]),
        provideHttpClient(),
        { provide: AuthService, useValue: { isSuperuser: signal(false) } },
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TestListComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with default config values', () => {
    expect(component.pageSize()).toBe(10);
    expect(component.ordering()).toBe('name');
    expect(component.page()).toBe(1);
    expect(component.query()).toBe('');
  });

  it('should have isLoading as a signal', () => {
    // isLoading is now a Signal<boolean> from rxResource, not a WritableSignal
    expect(typeof component.isLoading).toBe('function');
    expect(typeof component.isLoading()).toBe('boolean');
  });

  it('should have totalPages computed correctly', async () => {
    await fixture.whenStable();
    component.totalItems.set(25);
    component.pageSize.set(10);
    fixture.detectChanges();
    expect(component.totalPages()).toBe(3);
  });

  it('should have bulkDeleteLabel computed correctly when query is empty', () => {
    component.query.set('');
    fixture.detectChanges();
    expect(component.bulkDeleteLabel()).toBe('Delete All Test Items');
  });

  it('should have bulkDeleteLabel computed correctly when query has value', () => {
    component.query.set('search term');
    fixture.detectChanges();
    expect(component.bulkDeleteLabel()).toBe('Delete Selected Test Items');
  });

  describe('navigation methods', () => {
    it('should get correct new route', () => {
      expect(component.testGetNewRoute()).toBe('/test-items/new');
    });

    it('should get correct list route', () => {
      expect(component.testGetListRoute()).toBe('/test-items');
    });

    it('should get correct edit route', () => {
      expect(component.testGetEditRoute(123)).toBe('/test-items/123/edit');
    });

    it('should get correct detail route', () => {
      expect(component.testGetDetailRoute(456)).toBe('/test-items/456');
    });

    it('should get entity type label', () => {
      expect(component.testGetEntityTypeLabel()).toBe('Test Items');
    });
  });

  describe('event handlers', () => {
    it('should handle query change', () => {
      component.onQueryChange('test search');
      expect(component.query()).toBe('test search');
      expect(component.page()).toBe(1);
    });

    it('should trim query value', () => {
      component.onQueryChange('  test search  ');
      expect(component.query()).toBe('test search');
    });

    it('should handle page change', () => {
      component.onPageChange(3);
      expect(component.page()).toBe(3);
    });

    it('should handle sort change with desc direction', () => {
      component.onSortChange({ column: 'name', direction: 'desc' });
      expect(component.ordering()).toBe('-name');
      expect(component.page()).toBe(1);
    });

    it('should handle sort change with asc direction', () => {
      component.onSortChange({ column: 'name', direction: 'asc' });
      expect(component.ordering()).toBe('name');
    });
  });

  describe('reload', () => {
    it('should increment reload token when calling reload', () => {
      const initialToken = component['reloadToken']();
      component.reload();
      expect(component['reloadToken']()).toBe(initialToken + 1);
    });
  });

  describe('bulk delete', () => {
    it('should open bulk delete dialog with correct data', () => {
      component.totalItems.set(100);
      component.query.set('');

      component.openBulkDeleteDialog('Test Items', 'Test details');

      expect(component.bulkDeleteOpen()).toBe(true);
      expect(component.bulkDeleteData()).toEqual(
        expect.objectContaining({
          entityLabel: 'Test Items',
          totalCount: 100,
          mode: 'all',
          detailsText: 'Test details',
        }),
      );
    });

    it('should open bulk delete dialog in selected mode when query exists', () => {
      component.query.set('search term');

      component.openBulkDeleteDialog('Test Items', 'Test details');

      expect(component.bulkDeleteData()?.mode).toBe('selected');
    });

    it('should handle bulk delete cancellation', () => {
      component.bulkDeleteOpen.set(true);
      component.bulkDeleteData.set({ entityLabel: 'Test', totalCount: 10 });
      component.testBulkDeleteQuery.set('test');

      component.onBulkDeleteCancelled();

      expect(component.bulkDeleteOpen()).toBe(false);
      expect(component.bulkDeleteData()).toBeNull();
      expect(component.testBulkDeleteQuery()).toBe('');
    });
  });

  describe('keyboard shortcuts', () => {
    it('should not handle keyboard shortcuts when input is focused', () => {
      // Mock an input element being focused
      const inputElement = document.createElement('input');
      document.body.appendChild(inputElement);
      inputElement.focus();

      const event = new KeyboardEvent('keydown', { key: 'N' });

      component.handleGlobalKeydown(event);

      // Should not throw or cause errors
      document.body.removeChild(inputElement);
    });
  });

  describe('navigation state restoration', () => {
    it('should restore navigation state from window.history', () => {
      // Mock window.history.state
      const originalState = window.history.state;
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
      fixture.detectChanges();

      expect(component.page()).toBe(5);
      expect(component.query()).toBe('restored search');

      // Restore original state
      Object.defineProperty(window.history, 'state', {
        value: originalState,
        writable: true,
      });
    });
  });
});
