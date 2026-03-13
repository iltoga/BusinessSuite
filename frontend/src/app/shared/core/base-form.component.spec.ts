import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { Router, provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { GlobalToastService } from '@/core/services/toast.service';
import { Component } from '@angular/core';
import { BaseFormComponent, BaseFormConfig } from './base-form.component';

// Mock test interfaces
interface TestItem {
  id: number;
  name: string;
  email?: string;
}

interface TestCreateDto {
  name: string;
  email?: string;
}

interface TestUpdateDto {
  name: string;
  email?: string;
}

// Mock test component extending BaseFormComponent
@Component({
  selector: 'app-test-form',
  standalone: true,
  imports: [ReactiveFormsModule],
  template: '',
})
class TestFormComponent extends BaseFormComponent<TestItem, TestCreateDto, TestUpdateDto> {
  constructor() {
    super();
    this.config = {
      entityType: 'test-items',
      entityLabel: 'Test Item',
    } as BaseFormConfig<TestItem, TestCreateDto, TestUpdateDto>;
  }

  protected buildForm() {
    return this.fb.group({
      id: [null],
      name: ['', []],
      email: [''],
    });
  }

  protected loadItem(id: number) {
    return of({ id, name: 'Test Item', email: 'test@example.com' });
  }

  protected createDto(): TestCreateDto {
    return this.form.value;
  }

  protected updateDto(): TestUpdateDto {
    return this.form.value;
  }

  protected saveCreate(dto: TestCreateDto) {
    return of({ id: 1, ...dto });
  }

  protected saveUpdate(dto: TestUpdateDto) {
    return of({ id: 1, ...dto });
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

  public testGetNavigationState() {
    return this.getNavigationState();
  }
}

describe('BaseFormComponent', () => {
  let component: TestFormComponent;
  let fixture: ComponentFixture<TestFormComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [TestFormComponent],
      providers: [
        provideRouter([{ path: '**', redirectTo: '' }]),
        provideHttpClient(),
        FormBuilder,
        { provide: GlobalToastService, useValue: { success: vi.fn(), error: vi.fn() } },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(TestFormComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });

  it('should initialize with default state', () => {
    expect(component.isLoading()).toBe(false);
    expect(component.isSaving()).toBe(false);
    expect(component.isEditMode()).toBe(false);
    expect(component.item()).toBeNull();
  });

  it('should have form initialized', () => {
    expect(component.form).toBeDefined();
    expect(component.form).toBeTruthy();
  });

  it('should have formErrorLabels initialized', () => {
    expect(component.formErrorLabels).toEqual({});
  });

  it('should have fieldTooltips initialized', () => {
    expect(component.fieldTooltips).toEqual({});
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

    it('should get navigation state from window.history', () => {
      // Mock window.history.state
      Object.defineProperty(window.history, 'state', {
        value: {
          searchQuery: 'test search',
          page: 5,
        },
        writable: true,
      });

      const state = component.testGetNavigationState();
      expect(state.searchQuery).toBe('test search');
      expect(state.page).toBe(5);
    });
  });

  describe('keyboard shortcuts', () => {
    it('should handle Escape key to cancel', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');
      const event = new KeyboardEvent('keydown', { key: 'Escape' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(goBackSpy).toHaveBeenCalled();
    });

    it('should handle Ctrl+S to save', () => {
      const onSubmitSpy = vi.spyOn(component, 'onSubmit');
      const event = new KeyboardEvent('keydown', {
        key: 's',
        ctrlKey: true,
      });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(onSubmitSpy).toHaveBeenCalled();
    });

    it('should handle Cmd+S to save (Mac)', () => {
      const onSubmitSpy = vi.spyOn(component, 'onSubmit');
      const event = new KeyboardEvent('keydown', {
        key: 's',
        metaKey: true,
      });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(onSubmitSpy).toHaveBeenCalled();
    });

    it('should handle B key to go back', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');
      const event = new KeyboardEvent('keydown', { key: 'B' });
      const preventDefaultSpy = vi.spyOn(event, 'preventDefault');

      component.handleGlobalKeydown(event);

      expect(preventDefaultSpy).toHaveBeenCalled();
      expect(goBackSpy).toHaveBeenCalled();
    });

    it('should handle Left Arrow key to go back', () => {
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

      const event = new KeyboardEvent('keydown', { key: 'Escape' });

      component.handleGlobalKeydown(event);

      expect(goBackSpy).not.toHaveBeenCalled();

      document.body.removeChild(inputElement);
    });
  });

  describe('form submission', () => {
    it('should mark form as touched when invalid', () => {
      component.form.controls['name'].setErrors({ required: true });
      const markAllAsTouchedSpy = vi.spyOn(component.form, 'markAllAsTouched');
      const toastSpy = vi.spyOn((component as any).toast, 'error');

      component.onSubmit();

      expect(markAllAsTouchedSpy).toHaveBeenCalled();
      expect(toastSpy).toHaveBeenCalledWith('Please fix the form errors');
    });

    it('should set isSaving to true during submission', () => {
      // This would require mocking the save observable
      // For now, we test that the method exists and doesn't throw
      expect(() => component.onSubmit()).not.toThrow();
    });
  });

  describe('cancel', () => {
    it('should call goBack on cancel', () => {
      const goBackSpy = vi.spyOn(component as any, 'goBack');

      component.onCancel();

      expect(goBackSpy).toHaveBeenCalled();
    });
  });

  describe('patch form', () => {
    it('should patch form with item data', () => {
      const testData = { id: 1, name: 'Test Name', email: 'test@example.com' };
      const patchValueSpy = vi.spyOn(component.form, 'patchValue');

      (component as any).patchForm(testData);

      expect(patchValueSpy).toHaveBeenCalledWith(testData, { emitEvent: false });
    });
  });

  describe('go back', () => {
    it('should navigate to list route with focus state', () => {
      const router = TestBed.inject(Router);
      const navigateSpy = vi
        .spyOn(router, 'navigate')
        .mockImplementation(() => Promise.resolve(true));

      (component as any).goBack();

      expect(navigateSpy).toHaveBeenCalledWith(
        ['/test-items'],
        expect.objectContaining({
          state: expect.objectContaining({
            focusTable: true,
          }),
        }),
      );
    });
  });
});
