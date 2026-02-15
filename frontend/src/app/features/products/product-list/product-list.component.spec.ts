import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ProductsService } from '@/core/api';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { RouterTestingModule } from '@angular/router/testing';
import { ProductListComponent } from './product-list.component';

describe('ProductListComponent', () => {
  let fixture: any;
  let component: ProductListComponent;

  const mockProductsService: any = {
    productsList: (_ordering?: string, _page?: number, _pageSize?: number, _search?: string) =>
      of({
        count: 1,
        results: [
          {
            id: 1,
            name: 'TEST',
            code: 'T-1',
            description: 'Short test description',
            productType: 'visa',
            basePrice: '200000.00',
          },
        ],
      }),
    productsCanDeleteRetrieve: () => of({ can_delete: true }),
  };
  const mockProductImportExportService: any = {
    startExport: () => of({ job_id: 'job-1', status: 'pending', progress: 0 }),
    startImport: () => of({ job_id: 'job-2', status: 'pending', progress: 0 }),
    downloadExport: () => of({ body: new Blob(), headers: { get: () => null } }),
    pollJob: () => of({ status: 'completed', progress: 100 }),
  };

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ProductListComponent, RouterTestingModule],
      providers: [
        { provide: ProductsService, useValue: mockProductsService },
        { provide: ProductImportExportService, useValue: mockProductImportExportService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductListComponent);
    component = fixture.componentInstance;
  });

  it('should render product type and formatted base price in the table', async () => {
    // trigger loading
    component.ngOnInit();

    // wait a bit for async subscription
    await new Promise((r) => setTimeout(r, 0));
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const text = String((el.innerText ?? el.textContent) || '');
    expect(text).toContain('Visa');
    // formatted as currency using the component helper or template; check numeric part
    expect(text).toContain('200');
    // description should be present in the list
    expect(text).toContain('Short test description');
  });
});
