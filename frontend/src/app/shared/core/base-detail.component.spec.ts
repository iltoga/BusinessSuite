import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { Component } from '@angular/core';
import { Observable, of } from 'rxjs';
import { BaseDetailComponent, BaseDetailConfig } from './base-detail.component';

// Mock test interface
interface TestItem {
  id: number;
  name: string;
}

// Mock test component extending BaseDetailComponent
@Component({
  selector: 'app-test-detail',
  standalone: true,
  imports: [],
  template: '',
})
class TestDetailComponent extends BaseDetailComponent<TestItem> {
  constructor() {
    super();
    this.config = {
      entityType: 'test-items',
      entityLabel: 'Test Item',
      enableDelete: true,
      deleteRequiresSuperuser: false,
    } as BaseDetailConfig<TestItem>;
  }

  protected loadItem(id: number): Observable<TestItem> {
    return of({ id, name: 'Test Item' });
  }

  protected deleteItem(id: number): Observable<any> {
    return of({ success: true });
  }

  // Expose protected methods for testing
  public testGetListRoute(): string {
    return this.getListRoute();
  }

  public testGetEditRoute(id: number): string {
    return this.getEditRoute(id);
  }

  public testGetDetailRoute(id: number): string {
    return this.getDetailRoute(id);
  }
}

describe('BaseDetailComponent', () => {
  let component: TestDetailComponent;
  let fixture: ComponentFixture<TestDetailComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestDetailComponent],
      providers: [
        provideRouter([{ path: '**', redirectTo: '' }]),
        provideHttpClient(),
        { provide: AuthService, useValue: { isSuperuser: vi.fn(() => false) } },
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TestDetailComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with default state', () => {
    expect(component.isLoading()).toBe(true);
    expect(component.item()).toBeNull();
  });

  it('should have navigation state signals initialized', () => {
    expect(component.originSearchQuery()).toBeNull();
    expect(component.originPage()).toBeNull();
    expect(component.returnUrl()).toBeNull();
    expect(component.returnState()).toBeNull();
  });

  describe('navigation methods', () => {
    it('should get correct list route', () => {
      expect(component.testGetListRoute()).toBe('/test-items');
    });

    it('should get correct edit route', () => {
      expect(component.testGetEditRoute(123)).toBe('/test-items/123/edit');
    });

    it('should get correct detail route', () => {
      expect(component.testGetDetailRoute(456)).toBe('/test-items/456');
    });

    it('should navigate to edit', () => {
      const router = TestBed.inject(Router);
      const navigateSpy = vi
        .spyOn(router, 'navigate')
        .mockImplementation(() => Promise.resolve(true));

      (component as any).itemId = 123;
      (component as any).navigateToEdit();

      expect(navigateSpy).toHaveBeenCalledWith(['/test-items/123/edit'], expect.any(Object));
    });

    it('should not navigate to edit if itemId is null', () => {
      const router = TestBed.inject(Router);
      const navigateSpy = vi
        .spyOn(router, 'navigate')
        .mockImplementation(() => Promise.resolve(true));

      (component as any).itemId = null;
      (component as any).navigateToEdit();

      expect(navigateSpy).not.toHaveBeenCalled();
    });
  });

  describe('go back', () => {
    it('should navigate to return URL if available', () => {
      const router = TestBed.inject(Router);
      const navigateByUrlSpy = vi
        .spyOn(router, 'navigateByUrl')
        .mockImplementation(() => Promise.resolve(true));
      const navigateSpy = vi.spyOn(router, 'navigate');

      component.returnUrl.set('/custom-return-url');
      (component as any).goBack();

      expect(navigateByUrlSpy).toHaveBeenCalledWith('/custom-return-url', expect.any(Object));
      expect(navigateSpy).not.toHaveBeenCalled();
    });

    it('should navigate to list route if no return URL', () => {
      const router = TestBed.inject(Router);
      const navigateSpy = vi
        .spyOn(router, 'navigate')
        .mockImplementation(() => Promise.resolve(true));

      (component as any).itemId = 123;
      (component as any).goBack();

      expect(navigateSpy).toHaveBeenCalledWith(
        ['/test-items'],
        expect.objectContaining({
          state: expect.objectContaining({
            focusTable: true,
            focusId: 123,
          }),
        }),
      );
    });
  });

  describe('keyboard shortcuts', () => {
    it('should handle E key for edit', () => {
      const navigateToEditSpy = vi.spyOn(component as any, 'navigateToEdit');
      const event = new KeyboardEvent('keydown', { key: 'E' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(navigateToEditSpy).toHaveBeenCalled();
    });

    it('should handle D key for delete when enabled', () => {
      const onDeleteSpy = vi.spyOn(component as any, 'onDelete');
      const event = new KeyboardEvent('keydown', { key: 'D' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(onDeleteSpy).toHaveBeenCalled();
    });

    it('should not handle D key for delete when disabled', () => {
      (component as any).config.enableDelete = false;
      const onDeleteSpy = vi.spyOn(component as any, 'onDelete');
      const event = new KeyboardEvent('keydown', { key: 'D' });

      component.handleGlobalKeydown(event);

      expect(onDeleteSpy).not.toHaveBeenCalled();
    });

    it('should not handle D key for delete when requires superuser but user is not superuser', () => {
      (component as any).config.deleteRequiresSuperuser = true;
      const onDeleteSpy = vi.spyOn(component as any, 'onDelete');
      const event = new KeyboardEvent('keydown', { key: 'D' });

      component.handleGlobalKeydown(event);

      expect(onDeleteSpy).not.toHaveBeenCalled();
    });

    it('should handle B key for back', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');
      const event = new KeyboardEvent('keydown', { key: 'B' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(goBackSpy).toHaveBeenCalled();
    });

    it('should handle Left Arrow key for back', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');
      const event = new KeyboardEvent('keydown', { key: 'ArrowLeft' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(goBackSpy).toHaveBeenCalled();
    });

    it('should not handle keyboard shortcuts when input is focused', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');

      // Mock an input element being focused
      const inputElement = document.createElement('input');
      document.body.appendChild(inputElement);
      inputElement.focus();

      const event = new KeyboardEvent('keydown', { key: 'B' });

      component.handleGlobalKeydown(event);

      expect(goBackSpy).not.toHaveBeenCalled();

      document.body.removeChild(inputElement);
    });
  });

  describe('delete', () => {
    it('should not delete if itemId is null', () => {
      (component as any).itemId = null;
      component.item.set(null);

      expect(() => (component as any).onDelete()).not.toThrow();
    });

    it('should not delete if item is null', () => {
      (component as any).itemId = 123;
      component.item.set(null);

      expect(() => (component as any).onDelete()).not.toThrow();
    });

    it('should not delete if requires superuser and user is not superuser', () => {
      (component as any).config.deleteRequiresSuperuser = true;
      (component as any).itemId = 123;
      component.item.set({ id: 123, name: 'Test' });

      const deleteItemSpy = vi.spyOn(component as any, 'deleteItem');

      (component as any).onDelete();

      expect(deleteItemSpy).not.toHaveBeenCalled();
    });

    it('should show confirmation dialog before delete', () => {
      // Mock window.confirm
      const originalConfirm = window.confirm;
      window.confirm = vi.fn(() => false); // User cancels

      (component as any).itemId = 123;
      component.item.set({ id: 123, name: 'Test' });

      const deleteItemSpy = vi.spyOn(component as any, 'deleteItem');

      (component as any).onDelete();

      expect(window.confirm).toHaveBeenCalled();
      expect(deleteItemSpy).not.toHaveBeenCalled();

      window.confirm = originalConfirm;
    });

    it('should call deleteItem and show success toast on confirmation', () => {
      const originalConfirm = window.confirm;
      window.confirm = vi.fn(() => true); // User confirms

      (component as any).itemId = 123;
      component.item.set({ id: 123, name: 'Test' });

      const deleteItemSpy = vi
        .spyOn(component as any, 'deleteItem')
        .mockReturnValue(of({ success: true }));
      const toastSpy = vi.spyOn((component as any).toast, 'success');

      (component as any).onDelete();

      expect(deleteItemSpy).toHaveBeenCalledWith(123);
      expect(toastSpy).toHaveBeenCalled();

      window.confirm = originalConfirm;
    });

    it('should show error toast on delete failure', () => {
      const originalConfirm = window.confirm;
      window.confirm = vi.fn(() => true);

      (component as any).itemId = 123;
      component.item.set({ id: 123, name: 'Test' });

      vi.spyOn(component as any, 'deleteItem').mockReturnValue(
        vi.fn().mockReturnValue({
          subscribe: vi.fn((callbacks: any) => {
            callbacks.error({ error: { detail: 'Delete failed' } });
          }),
        })(),
      );
      const toastSpy = vi.spyOn((component as any).toast, 'error');

      (component as any).onDelete();

      expect(toastSpy).toHaveBeenCalled();

      window.confirm = originalConfirm;
    });
  });

  describe('navigation state restoration', () => {
    it('should restore navigation state from window.history', () => {
      // Mock window.history.state
      Object.defineProperty(window.history, 'state', {
        value: {
          searchQuery: 'restored search',
          page: 5,
          returnUrl: '/return-url',
          returnState: { custom: 'state' },
        },
        writable: true,
      });

      (component as any).restoreNavigationState();

      expect(component.originSearchQuery()).toBe('restored search');
      expect(component.originPage()).toBe(5);
      expect(component.returnUrl()).toBe('/return-url');
      expect(component.returnState()).toEqual({ custom: 'state' });
    });

    it('should not set returnUrl if it does not start with /', () => {
      Object.defineProperty(window.history, 'state', {
        value: {
          returnUrl: 'invalid-url',
        },
        writable: true,
      });

      (component as any).restoreNavigationState();

      expect(component.returnUrl()).toBeNull();
    });
  });

  describe('load item for detail', () => {
    it('should load item and set state', () => {
      const loadItemSpy = vi
        .spyOn(component as any, 'loadItem')
        .mockReturnValue(of({ id: 123, name: 'Loaded Item' }));

      (component as any).itemId = 123;
      (component as any).loadItemForDetail(123);

      expect(loadItemSpy).toHaveBeenCalledWith(123);
    });
  });
});
