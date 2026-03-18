import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router, convertToParamMap } from '@angular/router';
import { of } from 'rxjs';

import { ProductsService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';

import { ProductDetailComponent } from './product-detail.component';

describe('ProductDetailComponent', () => {
  let component: ProductDetailComponent;

  const mockProductsService: Pick<ProductsService, 'productsRetrieve'> = {
    productsRetrieve: () => of({} as any),
  };

  const mockToastService: Pick<GlobalToastService, 'error'> = {
    error: () => undefined,
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Router, useValue: { navigate: () => Promise.resolve(true) } },
        { provide: ProductsService, useValue: mockProductsService },
        { provide: GlobalToastService, useValue: mockToastService },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({}) } },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new ProductDetailComponent());
  });

  it('reports no documents or tasks when product has neither', () => {
    component.product.set({
      id: 36,
      code: 'BANK_FEE',
      name: 'BANK_FEE',
      requiredDocumentTypes: [],
      optionalDocumentTypes: [],
      tasks: [],
    } as any);
    expect(component.requiredDocuments()).toEqual([]);
    expect(component.optionalDocuments()).toEqual([]);
    expect(component.hasAnyDocuments()).toBe(false);
    expect(component.tasks()).toEqual([]);
    expect(component.hasTasks()).toBe(false);
  });

  it('reports documents and tasks when product data is present', () => {
    component.product.set({
      id: 36,
      code: 'BANK_FEE',
      name: 'BANK_FEE',
      requiredDocumentTypes: [{ id: 1, name: 'Passport' }],
      optionalDocumentTypes: [],
      tasks: [
        {
          id: 1,
          step: 1,
          name: 'Collect docs',
          duration: 2,
          addTaskToCalendar: false,
          notifyDaysBefore: 0,
          notifyCustomer: false,
          lastStep: true,
        },
      ],
    } as any);
    expect(component.requiredDocuments()).toHaveLength(1);
    expect(component.requiredDocuments()[0]?.name).toBe('Passport');
    expect(component.hasAnyDocuments()).toBe(true);
    expect(component.tasks()).toHaveLength(1);
    expect(component.tasks()[0]?.name).toBe('Collect docs');
    expect(component.hasTasks()).toBe(true);
  });
});
