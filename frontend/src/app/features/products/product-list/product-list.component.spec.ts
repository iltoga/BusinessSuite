import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';

import { ProductsService } from '@/core/api';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { RouterTestingModule } from '@angular/router/testing';
import { ProductListComponent } from './product-list.component';

describe('ProductListComponent', () => {
  let fixture: any;
  let component: ProductListComponent;
  let httpMock: HttpTestingController;

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
      imports: [ProductListComponent, RouterTestingModule, HttpClientTestingModule],
      providers: [
        { provide: ProductsService, useValue: mockProductsService },
        { provide: ProductImportExportService, useValue: mockProductImportExportService },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductListComponent);
    component = fixture.componentInstance;
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  function flushProductsList(): void {
    const req = httpMock.expectOne((request) => request.url.startsWith('/api/products/'));
    expect(req.request.method).toBe('GET');
    req.flush({
      count: 1,
      results: [
        {
          id: 1,
          name: 'TEST',
          code: 'T-1',
          description: 'Short test description',
          productType: 'visa',
          basePrice: '200000.00',
          retailPrice: '250000.00',
        },
      ],
    });
  }

  it('should render product type and formatted base price in the table', async () => {
    // trigger ngOnInit through Angular lifecycle
    fixture.detectChanges();
    flushProductsList();

    await fixture.whenStable();
    fixture.detectChanges();
    const el: HTMLElement = fixture.nativeElement;
    const text = String((el.innerText ?? el.textContent) || '');
    expect(text).toContain('Visa');
    expect(text).toContain('****');
    // description should be present in the list
    expect(text).toContain('Short test description');
  });

  it('should reveal base prices when clicking the header eye toggle', async () => {
    fixture.detectChanges();
    flushProductsList();

    await fixture.whenStable();
    fixture.detectChanges();

    const host: HTMLElement = fixture.nativeElement;
    const toggle = host.querySelector(
      'button[aria-label="Show base prices"]',
    ) as HTMLButtonElement | null;
    expect(toggle).toBeTruthy();

    toggle?.click();
    fixture.detectChanges();

    const text = String((host.innerText ?? host.textContent) || '');
    expect(text).toContain('Rp');
    expect(text).not.toContain('****');
  });
});
