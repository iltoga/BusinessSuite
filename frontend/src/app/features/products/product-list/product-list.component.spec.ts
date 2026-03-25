import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';

import { ProductsService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { JobService } from '@/core/services/job.service';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { ProductListComponent } from './product-list.component';

describe('ProductListComponent', () => {
  let component: ProductListComponent;
  let mockToastService: any;
  let mockProductsService: any;
  let mockRouter: any;
  let productImportExportService: any;
  const loadCurrentPage = () =>
    (component as any)
      .createListLoader({
        query: component.query(),
        page: component.page(),
        pageSize: component.pageSize(),
        ordering: component.ordering(),
        reloadToken: 0,
      })
      .subscribe();

  beforeEach(() => {
    mockToastService = {
      success: vi.fn(),
      error: vi.fn(),
      info: vi.fn(),
      warning: vi.fn(),
    };

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
      productsDeletePreviewRetrieve: vi.fn(),
      productsForceDeleteCreate: vi.fn(),
      productsDestroy: vi.fn(),
      productsPartialUpdate: vi.fn().mockReturnValue(of({})),
      productsPriceListPrintStartCreate: vi.fn().mockReturnValue(
        of({
          jobId: 'print-job-1',
          status: 'pending',
          progress: 0,
          queued: true,
          deduplicated: false,
        }),
      ),
    };

    productImportExportService = {
      startExport: vi.fn().mockReturnValue(of({ jobId: 'job-1' })),
      startImport: vi.fn().mockReturnValue(of({ jobId: 'job-2' })),
      downloadExport: vi.fn().mockReturnValue(of({ body: new Blob() })),
      downloadPriceListPdf: vi
        .fn()
        .mockReturnValue(of(new Blob(['pdf'], { type: 'application/pdf' }))),
    };

    mockRouter = {
      navigate: vi.fn(),
      getCurrentNavigation: vi.fn().mockReturnValue(null),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        { provide: Router, useValue: mockRouter },
        { provide: ActivatedRoute, useValue: { snapshot: { queryParams: {} } } },
        { provide: ProductsService, useValue: mockProductsService },
        { provide: ProductImportExportService, useValue: productImportExportService },
        {
          provide: JobService,
          useValue: {
            watchJob: vi.fn().mockReturnValue(of({ status: 'completed', progress: 100 })),
            openProgressDialog: vi
              .fn()
              .mockReturnValue(of({ status: 'completed', progress: 100, message: 'Done' })),
          },
        },
        { provide: ConfigService, useValue: { settings: { baseCurrency: 'IDR' } } },
        { provide: AuthService, useValue: { isSuperuser: vi.fn().mockReturnValue(true) } },
        { provide: GlobalToastService, useValue: mockToastService },
      ],
    });

    component = TestBed.runInInjectionContext(() => new ProductListComponent());
    (component as any).focusAfterLoad = vi.fn();
    component.ngOnInit();
    component.page.set(1);
    component.query.set('');
  });

  it('hides deprecated products by default and restores that default when the filter is cleared', () => {
    loadCurrentPage();
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
    loadCurrentPage();
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

    component.onColumnFilterChange({ column: 'deprecated', values: [] });
    loadCurrentPage();
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

  it('shows all products only when both deprecated states are explicitly selected', () => {
    component.onColumnFilterChange({ column: 'deprecated', values: ['active', 'deprecated'] });
    loadCurrentPage();

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

  it('loads category filter options from the server instead of deriving them from the current page', () => {
    loadCurrentPage();
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

  it('marks list-origin edits so save can return to the list', () => {
    component.query.set('visa');
    component.page.set(3);

    const editAction = component.actions().find((action) => action.label === 'Edit');
    expect(editAction).toBeTruthy();

    editAction!.action({ id: 12, deprecated: false } as any);

    expect(mockRouter.navigate).toHaveBeenCalledWith(['/products/12/edit'], {
      state: {
        from: 'products',
        focusId: 12,
        searchQuery: 'visa',
        page: 3,
        returnToList: true,
      },
    });
  });

  it('offers deprecate and activate actions for the correct row states', () => {
    const actions = component.actions();
    const deprecateAction = actions.find((action) => action.label === 'Deprecate');
    const activateAction = actions.find((action) => action.label === 'Activate');

    expect(deprecateAction).toBeTruthy();
    expect(activateAction).toBeTruthy();
    expect(deprecateAction?.shortcut).toBe('P');
    expect(activateAction?.shortcut).toBe('A');

    const reloadSpy = vi.spyOn(component, 'reload').mockImplementation(() => undefined);
    const activeRow = { id: 1, deprecated: false } as any;
    const deprecatedRow = { id: 2, deprecated: true } as any;

    expect(deprecateAction?.isVisible?.(activeRow)).toBe(true);
    expect(activateAction?.isVisible?.(activeRow)).toBe(false);
    deprecateAction?.action(activeRow);

    expect(mockProductsService.productsPartialUpdate).toHaveBeenCalledWith(1, {
      deprecated: true,
    });
    expect(mockToastService.success).toHaveBeenCalledWith('Product deprecated');
    expect(reloadSpy).toHaveBeenCalledTimes(1);

    expect(deprecateAction?.isVisible?.(deprecatedRow)).toBe(false);
    expect(activateAction?.isVisible?.(deprecatedRow)).toBe(true);
    activateAction?.action(deprecatedRow);

    expect(mockProductsService.productsPartialUpdate).toHaveBeenLastCalledWith(2, {
      deprecated: false,
    });
    expect(mockToastService.success).toHaveBeenLastCalledWith('Product activated');
    expect(reloadSpy).toHaveBeenCalledTimes(2);
  });

  it('starts the printable price list flow and opens print preview on success', async () => {
    vi.stubGlobal(
      'open',
      vi.fn(() => ({
        document: {
          head: { replaceChildren: vi.fn(), append: vi.fn() },
          body: { replaceChildren: vi.fn(), innerHTML: '' },
          documentElement: { insertBefore: vi.fn(), appendChild: vi.fn() },
          createElement: vi.fn(() => ({
            tagName: 'meta',
            textContent: '',
            setAttribute: vi.fn(),
          })),
        },
        addEventListener: vi.fn(),
        focus: vi.fn(),
        print: vi.fn(),
        close: vi.fn(),
        closed: false,
        location: {
          href: '',
          replace: vi.fn(),
        },
      })),
    );
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:print-preview');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => undefined);

    await component.startPrint();

    expect(mockProductsService.productsPriceListPrintStartCreate).toHaveBeenCalledTimes(1);
    expect(productImportExportService.downloadPriceListPdf).toHaveBeenCalledWith('print-job-1');
    expect(mockToastService.success).toHaveBeenCalledWith('Printable price list opened');
  });
});
