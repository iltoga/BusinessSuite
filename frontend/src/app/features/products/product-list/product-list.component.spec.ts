import { provideHttpClient } from '@angular/common/http';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { ProductsService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { JobService } from '@/core/services/job.service';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { ProductListComponent } from './product-list.component';

describe('ProductListComponent', () => {
  let fixture: ComponentFixture<ProductListComponent>;
  let component: ProductListComponent;
  let mockProductsService: {
    productsList: ReturnType<typeof vi.fn>;
    productsCategoryOptionsList: ReturnType<typeof vi.fn>;
    productsDeletePreviewRetrieve: ReturnType<typeof vi.fn>;
    productsForceDeleteCreate: ReturnType<typeof vi.fn>;
    productsDestroy: ReturnType<typeof vi.fn>;
  };

  beforeEach(async () => {
    mockProductsService = {
      productsList: vi.fn().mockReturnValue(
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
              retailPrice: '250000.00',
              deprecated: false,
            },
          ],
        }),
      ),
      productsCategoryOptionsList: vi.fn().mockReturnValue(
        of([
          { value: 'Visa Category', label: 'Visa Category' },
          { value: 'Zeta Category', label: 'Zeta Category' },
        ]),
      ),
      productsDeletePreviewRetrieve: vi.fn().mockReturnValue(
        of({
          can_delete: true,
          requires_force_delete: false,
          related_counts: {
            tasks: 0,
            applications: 0,
            workflows: 0,
            documents: 0,
            invoice_applications: 0,
            invoices: 0,
            payments: 0,
          },
          related_records: {
            tasks: [],
            applications: [],
            invoice_applications: [],
          },
        }),
      ),
      productsForceDeleteCreate: vi.fn().mockReturnValue(of({ deleted: true })),
      productsDestroy: vi.fn().mockReturnValue(of({ deleted: true })),
    };

    await TestBed.configureTestingModule({
      imports: [ProductListComponent],
      providers: [
        provideRouter([]),
        provideHttpClient(),
        { provide: ProductsService, useValue: mockProductsService },
        {
          provide: ProductImportExportService,
          useValue: {
            startExport: vi.fn().mockReturnValue(of({ job_id: 'job-1' })),
            startImport: vi.fn().mockReturnValue(of({ job_id: 'job-2' })),
            downloadExport: vi.fn().mockReturnValue(of({ body: new Blob() })),
          },
        },
        {
          provide: JobService,
          useValue: {
            watchJob: vi.fn().mockReturnValue(of({ status: 'completed', progress: 100 })),
          },
        },
        { provide: ConfigService, useValue: { settings: { baseCurrency: 'IDR' } } },
        {
          provide: AuthService,
          useValue: {
            isSuperuser: vi.fn().mockReturnValue(true),
          },
        },
        {
          provide: GlobalToastService,
          useValue: {
            success: vi.fn(),
            error: vi.fn(),
            info: vi.fn(),
            warning: vi.fn(),
          },
        },
      ],
    }).compileComponents();

    fixture = TestBed.createComponent(ProductListComponent);
    component = fixture.componentInstance;
  });

  it('hides deprecated products by default and restores that default when the filter is cleared', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    // Default filter is ['active'] → deprecated=false, hideDeprecated=false
    expect(mockProductsService.productsList).toHaveBeenLastCalledWith(
      false,
      false,
      'name',
      1,
      10,
      undefined,
      undefined,
      undefined,
    );

    component.onColumnFilterChange({ column: 'deprecated', values: ['deprecated'] });
    await fixture.whenStable();
    expect(mockProductsService.productsList).toHaveBeenLastCalledWith(
      true,
      false,
      'name',
      1,
      10,
      undefined,
      undefined,
      undefined,
    );

    // Clearing filter (empty) → deprecated=undefined, hideDeprecated=true
    component.onColumnFilterChange({ column: 'deprecated', values: [] });
    await fixture.whenStable();
    expect(mockProductsService.productsList).toHaveBeenLastCalledWith(
      undefined,
      true,
      'name',
      1,
      10,
      undefined,
      undefined,
      undefined,
    );
  });

  it('shows all products only when both deprecated states are explicitly selected', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    component.onColumnFilterChange({ column: 'deprecated', values: ['active', 'deprecated'] });
    await fixture.whenStable();

    // Both selected → deprecated=undefined, hideDeprecated=false
    expect(mockProductsService.productsList).toHaveBeenLastCalledWith(
      undefined,
      false,
      'name',
      1,
      10,
      undefined,
      undefined,
      undefined,
    );
  });

  it('loads category filter options from the server instead of deriving them from the current page', async () => {
    fixture.detectChanges();
    await fixture.whenStable();

    // Default filter ['active'] → deprecated=false, hideDeprecated=false
    expect(mockProductsService.productsCategoryOptionsList).toHaveBeenLastCalledWith(
      false,
      false,
      undefined,
    );
    expect(component.categoryFilterOptions()).toEqual([
      { value: 'Visa Category', label: 'Visa Category' },
      { value: 'Zeta Category', label: 'Zeta Category' },
    ]);
  });
});
