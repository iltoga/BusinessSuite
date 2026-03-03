import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, convertToParamMap } from '@angular/router';
import { RouterTestingModule } from '@angular/router/testing';
import { of } from 'rxjs';

import { ProductsService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ProductDetailComponent } from './product-detail.component';

describe('ProductDetailComponent', () => {
  let fixture: any;
  let component: ProductDetailComponent;

  const mockProductsService: Pick<ProductsService, 'productsRetrieve'> = {
    productsRetrieve: () => of({} as any),
  };

  const mockToastService: Pick<GlobalToastService, 'error'> = {
    error: () => undefined,
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProductDetailComponent, RouterTestingModule],
      providers: [
        { provide: ProductsService, useValue: mockProductsService },
        { provide: GlobalToastService, useValue: mockToastService },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { paramMap: convertToParamMap({}) } },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductDetailComponent);
    component = fixture.componentInstance;
  });

  it('hides documents and tasks cards when product has no documents and no tasks', () => {
    component.product.set({
      id: 36,
      code: 'BANK_FEE',
      name: 'BANK_FEE',
      requiredDocumentTypes: [],
      optionalDocumentTypes: [],
      tasks: [],
    } as any);
    component.isLoading.set(false);

    fixture.detectChanges();

    const host: HTMLElement = fixture.nativeElement;
    const text = String((host.innerText ?? host.textContent) || '');

    expect(text).not.toContain('Required documents');
    expect(text).not.toContain('Optional documents');
    expect(text).not.toContain('Tasks');
    expect(host.querySelectorAll('z-card').length).toBe(1);
  });

  it('shows documents and tasks cards when data is present', () => {
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
    component.isLoading.set(false);

    fixture.detectChanges();

    const host: HTMLElement = fixture.nativeElement;
    const text = String((host.innerText ?? host.textContent) || '');

    expect(text).toContain('Required documents');
    expect(text).toContain('Tasks');
    expect(host.querySelectorAll('z-card').length).toBe(3);
  });
});
