import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideHttpClient } from '@angular/common/http';
import { describe, it, expect, beforeEach, vi } from 'vitest';

import { BaseListComponent, BaseListConfig } from './base-list.component';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { DataTableComponent, type ColumnConfig } from '@/shared/components/data-table/data-table.component';
import { Component, signal } from '@angular/core';

// Mock test component extending BaseListComponent
interface TestItem {
  id: number;
  name: string;
}

@Component({
  selector: 'app-test-list',
  standalone: true,
  imports: [DataTableComponent],
  template: '',
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

  public loadItems(): void {
    // Mock implementation
    this.items.set([
      { id: 1, name: 'Item 1' },
      { id: 2, name: 'Item 2' },
    ]);
    this.totalItems.set(2);
    this.isLoading.set(false);
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
    await TestBed.configureTestingModule({
      imports: [TestListComponent],
      providers: [
        provideRouter([]),
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

  it('should have items signal initialized', () => {
    expect(component.items()).toEqual([
      { id: 1, name: 'Item 1' },
      { id: 2, name: 'Item 2' },
    ]);
  });

  it('should have totalPages computed correctly', () => {
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
      vi.spyOn(component, 'loadItems');
      component.onQueryChange('test search');
      expect(component.query()).toBe('test search');
      expect(component.page()).toBe(1);
    });

    it('should trim query value', () => {
      component.onQueryChange('  test search  ');
      expect(component.query()).toBe('test search');
    });

    it('should handle page change', () => {
      vi.spyOn(component, 'loadItems');
      component.onPageChange(3);
      expect(component.page()).toBe(3);
    });

    it('should handle sort change with desc direction', () => {
      vi.spyOn(component, 'loadItems');
      component.onSortChange({ column: 'name', direction: 'desc' });
      expect(component.ordering()).toBe('-name');
      expect(component.page()).toBe(1);
    });

    it('should handle sort change with asc direction', () => {
      vi.spyOn(component, 'loadItems');
      component.onSortChange({ column: 'name', direction: 'asc' });
      expect(component.ordering()).toBe('name');
    });
  });

  describe('bulk delete', () => {
    it('should open bulk delete dialog with correct data', () => {
      component.totalItems.set(100);
      component.query.set('');
      
      component.openBulkDeleteDialog('Test Items', 'Test details');
      
      expect(component.bulkDeleteOpen()).toBe(true);
      expect(component.bulkDeleteData()).toEqual(expect.objectContaining({
        entityLabel: 'Test Items',
        totalCount: 100,
        mode: 'all',
        detailsText: 'Test details',
      }));
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
    it('should handle N key for new item', () => {
      const router = TestBed.inject<any>(AuthService).router;
      const navigateSpy = vi.spyOn(router, 'navigate').mockImplementation(() => Promise.resolve(true));
      
      const event = new KeyboardEvent('keydown', { key: 'N' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
      
      component.handleGlobalKeydown(event);
      
      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(navigateSpy).toHaveBeenCalledWith(['/test-items/new'], expect.any(Object));
    });

    it('should handle B key for back', () => {
      const router = TestBed.inject<any>(AuthService).router;
      const navigateSpy = vi.spyOn(router, 'navigate').mockImplementation(() => Promise.resolve(true));
      
      const event = new KeyboardEvent('keydown', { key: 'B' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
      
      component.handleGlobalKeydown(event);
      
      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(navigateSpy).toHaveBeenCalledWith(['/test-items'], expect.any(Object));
    });

    it('should handle Left Arrow key for back', () => {
      const router = TestBed.inject<any>(AuthService).router;
      const navigateSpy = vi.spyOn(router, 'navigate').mockImplementation(() => Promise.resolve(true));
      
      const event = new KeyboardEvent('keydown', { key: 'ArrowLeft' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
      
      component.handleGlobalKeydown(event);
      
      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(navigateSpy).toHaveBeenCalledWith(['/test-items'], expect.any(Object));
    });

    it('should not handle keyboard shortcuts when input is focused', () => {
      const router = TestBed.inject<any>(AuthService).router;
      const navigateSpy = vi.spyOn(router, 'navigate').mockImplementation(() => Promise.resolve(true));
      
      // Mock an input element being focused
      const inputElement = document.createElement('input');
      document.body.appendChild(inputElement);
      inputElement.focus();
      
      const event = new KeyboardEvent('keydown', { key: 'N' });
      
      component.handleGlobalKeydown(event);
      
      expect(navigateSpy).not.toHaveBeenCalled();
      
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
