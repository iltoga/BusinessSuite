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
    component.documentTypes = vi.fn();
    component.productsApi = {
      productsPartialUpdate: vi.fn().mockReturnValue(of({})),
      productsRetrieve: vi.fn().mockReturnValue(of({ tasks: [] })),
      productsUpdate: vi.fn(),
    };
    component.item = {
      value: null,
      set(value: ProductDetail | null) {
        this.value = value;
      },
    };
    component.product = {
      value: null,
      set(value: ProductDetail | null) {
        this.value = value;
      },
      update: vi.fn(),
    };
    component.itemId = 3;

    component.form = ProductFormComponent.prototype.buildForm.call(component);
    component.addTask = ProductFormComponent.prototype.addTask.bind(component);
    component.patchForm = ProductFormComponent.prototype.patchForm.bind(component);
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
    expect(component.product.value).toBe(item);
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
    } as ProductDetail;
    component.productsApi.productsRetrieve.mockReturnValue(of(refreshedItem));

    component.saveUpdate({ name: 'KITAS' } as ProductCreateUpdate).subscribe();

    expect(component.tasksArray.length).toBe(2);
    expect(component.tasksArray.at(1).get('id')?.value).toBe(11);
    expect(component.item.value).toBe(refreshedItem);
    expect(component.product.value).toBe(refreshedItem);
  });
});
