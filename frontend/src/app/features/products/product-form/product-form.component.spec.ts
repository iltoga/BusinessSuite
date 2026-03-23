import { signal } from '@angular/core';
import { FormBuilder } from '@angular/forms';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { type ProductCreateUpdate, type ProductDetail } from '@/core/api';

import { ProductFormComponent } from './product-form.component';

describe('ProductFormComponent', () => {
  type ProductFormHarness = any;

  const createHarness = (): ProductFormHarness => {
    const component = Object.create(ProductFormComponent.prototype) as ProductFormHarness;

    component.fb = new FormBuilder();
    component.configService = { settings: { baseCurrency: 'IDR' } };
    component.config = { entityType: 'products', entityLabel: 'Product' };
    component.router = {
      navigate: vi.fn(),
      getCurrentNavigation: vi.fn().mockReturnValue(null),
    };
    component.toast = {
      success: vi.fn(),
      error: vi.fn(),
    };
    component.documentTypes = signal([]);
    component.hasMultipleLastSteps = signal(false);
    component.isEditMode = signal(false);
    component.isLoading = signal(false);
    component.isSaving = signal(false);
    component.item = signal(null);
    component.product = signal(null);
    component.productsApi = {
      productsCreate: vi.fn().mockReturnValue(of({ id: 19 })),
      productsPartialUpdate: vi.fn().mockReturnValue(of({})),
      productsRetrieve: vi.fn().mockReturnValue(of({ tasks: [] })),
      productsUpdate: vi.fn(),
    };
    component.itemId = 3;

    component.form = (ProductFormComponent.prototype as any).buildForm.call(component);
    component.addTask = (ProductFormComponent.prototype as any).addTask.bind(component);
    component.patchForm = (ProductFormComponent.prototype as any).patchForm.bind(component);
    Object.defineProperty(component, 'tasksArray', {
      get() {
        return component.form.get('tasks');
      },
    });

    return component;
  };

  it('hydrates document ids and tasks when editing an existing product', () => {
    const component = createHarness();
    const item = {
      id: 3,
      name: 'KITAS',
      code: 'KITAS-1',
      basePrice: '100.00',
      retailPrice: '150.00',
      currency: 'usd',
      productType: 'visa',
      applicationWindowDays: 14,
      requiredDocumentTypes: [
        { id: 12, name: 'Passport' },
        { id: 18, name: 'Photo' },
      ],
      optionalDocumentTypes: [{ id: 22, name: 'Bank Statement' }],
      tasks: [
        {
          id: 7,
          step: 1,
          name: 'Collect docs',
          description: '',
          cost: '0.00',
          duration: 2,
          addTaskToCalendar: false,
          notifyCustomer: false,
          durationIsBusinessDays: true,
          notifyDaysBefore: 0,
          lastStep: true,
        },
      ],
    } as ProductDetail;

    component.patchForm(item);

    expect(component.form.get('requiredDocumentIds')?.value).toEqual([12, 18]);
    expect(component.form.get('optionalDocumentIds')?.value).toEqual([22]);
    expect(component.tasksArray.length).toBe(1);
    expect(component.tasksArray.at(0).get('id')?.value).toBe(7);
    expect(component.tasksArray.at(0).get('name')?.value).toBe('Collect docs');
    expect(component.form.get('currency')?.value).toBe('usd');
    expect(component.product()).toBe(item);
  });

  it('uses PATCH for product updates', () => {
    const component = createHarness();
    const dto = { name: 'KITAS' } as ProductCreateUpdate;

    component.saveUpdate(dto).subscribe();

    expect(component.productsApi.productsPartialUpdate).toHaveBeenCalledWith(3, dto);
    expect(component.productsApi.productsRetrieve).toHaveBeenCalledWith(3);
    expect(component.productsApi.productsUpdate).not.toHaveBeenCalled();
  });

  it('refreshes tasks after PATCH so newly created task ids are preserved for the next save', () => {
    const component = createHarness();
    const refreshedItem = {
      id: 3,
      name: 'KITAS',
      code: 'KITAS-1',
      basePrice: '100.00',
      retailPrice: '150.00',
      currency: 'IDR',
      productType: 'visa',
      requiredDocumentTypes: [],
      optionalDocumentTypes: [],
      tasks: [
        {
          id: 7,
          step: 1,
          name: 'Collect docs',
          description: '',
          cost: '0.00',
          duration: 2,
          addTaskToCalendar: false,
          notifyCustomer: false,
          durationIsBusinessDays: true,
          notifyDaysBefore: 0,
          lastStep: false,
        },
        {
          id: 11,
          step: 2,
          name: 'Verification',
          description: '',
          cost: '0.00',
          duration: 7,
          addTaskToCalendar: false,
          notifyCustomer: false,
          durationIsBusinessDays: true,
          notifyDaysBefore: 0,
          lastStep: true,
        },
      ],
    } as unknown as ProductDetail;
    component.productsApi.productsRetrieve.mockReturnValue(of(refreshedItem));

    component.saveUpdate({ name: 'KITAS' } as ProductCreateUpdate).subscribe();

    expect(component.tasksArray.length).toBe(2);
    expect(component.tasksArray.at(1).get('id')?.value).toBe(11);
    expect(component.item()).toBe(refreshedItem);
    expect(component.product()).toBe(refreshedItem);
  });

  it('returns create saves to the list with the new row focused', () => {
    const component = createHarness();
    component.itemId = null;
    component.form.patchValue({
      name: 'KITAS',
      code: 'KITAS-1',
    });
    component.router.getCurrentNavigation.mockReturnValue(null);
    history.replaceState({ searchQuery: 'visa', page: 2 }, '');

    component.onSubmit();

    expect(component.productsApi.productsCreate).toHaveBeenCalled();
    expect(component.itemId).toBe(19);
    expect(component.router.navigate).toHaveBeenCalledWith(['/products'], {
      state: {
        focusTable: true,
        focusId: 19,
        searchQuery: 'visa',
        page: 2,
      },
    });
  });

  it('returns list-origin edits back to the list after save', () => {
    const component = createHarness();
    component.itemId = 3;
    component.isEditMode.set(true);
    component.product.set({
      id: 3,
      name: 'KITAS',
      code: 'KITAS-1',
    } as ProductDetail);
    component.form.patchValue({
      name: 'KITAS Updated',
      code: 'KITAS-1',
    });
    component.productsApi.productsRetrieve.mockReturnValue(
      of({
        id: 3,
        tasks: [],
      } as unknown as ProductDetail),
    );
    component.router.getCurrentNavigation.mockReturnValue({
      extras: {
        state: {
          returnToList: true,
        },
      },
    });
    history.replaceState({ searchQuery: 'visa', page: 4 }, '');

    component.onSubmit();

    expect(component.router.navigate).toHaveBeenCalledWith(['/products'], {
      state: {
        focusTable: true,
        focusId: 3,
        searchQuery: 'visa',
        page: 4,
      },
    });
  });

  it('keeps direct or detail-origin edits on the edit route after save', () => {
    const component = createHarness();
    component.itemId = 3;
    component.isEditMode.set(true);
    component.product.set({
      id: 3,
      name: 'KITAS',
      code: 'KITAS-1',
    } as ProductDetail);
    component.form.patchValue({
      name: 'KITAS Updated',
      code: 'KITAS-1',
    });
    component.productsApi.productsRetrieve.mockReturnValue(
      of({
        id: 3,
        tasks: [],
      } as unknown as ProductDetail),
    );
    component.router.getCurrentNavigation.mockReturnValue(null);
    history.replaceState({ searchQuery: 'visa', page: 4 }, '');

    component.onSubmit();

    expect(component.router.navigate).toHaveBeenCalledWith(['/products/3/edit'], {
      state: {
        from: 'products',
        searchQuery: 'visa',
        page: 4,
      },
    });
  });

  it('falls back to the route focus id when no saved item id is available', () => {
    const component = createHarness();
    component.itemId = null;
    component.product.set(null);
    component.router.getCurrentNavigation.mockReturnValue(null);
    history.replaceState({ focusId: 41, searchQuery: 'visa', page: 2 }, '');

    component.goBack();

    expect(component.router.navigate).toHaveBeenCalledWith(['/products'], {
      state: {
        focusTable: true,
        focusId: 41,
        searchQuery: 'visa',
        page: 2,
      },
    });
  });
});
