import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';

import { CustomersService } from './customers.service';

describe('CustomersService', () => {
  let service: CustomersService;
  let httpMock: HttpTestingController;
  const authServiceMock = {
    getToken: vi.fn(() => 'test-token'),
  };

  beforeEach(() => {
    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [{ provide: AuthService, useValue: authServiceMock }],
    });

    service = TestBed.inject(CustomersService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    vi.clearAllMocks();
  });

  it('normalizes snake_case customer payloads into the generated Customer shape', () => {
    let actual: any;

    service.getCustomer(7).subscribe((customer) => {
      actual = customer;
    });

    const req = httpMock.expectOne('/api/customers/7/');
    expect(req.request.method).toBe('GET');
    expect(req.request.headers.get('Authorization')).toBe('Bearer test-token');

    req.flush({
      id: 7,
      createdAt: '2026-03-01T00:00:00Z',
      updatedAt: '2026-03-02T00:00:00Z',
      customerType: 'person',
      firstName: 'Stefano',
      lastName: 'Galassi',
      fullName: 'Stefano Galassi',
      fullNameWithCompany: 'Stefano Galassi',
      passportFile: 'media/passports/test.png',
      passportExpired: false,
      passportExpiringSoon: true,
      nationalityName: 'Italy',
      nationalityCode: 'ITA',
      genderDisplay: 'Male',
      notifyDocumentsExpiration: true,
      active: true,
    });

    expect(actual).toMatchObject({
      id: 7,
      customerType: 'person',
      firstName: 'Stefano',
      lastName: 'Galassi',
      fullName: 'Stefano Galassi',
      fullNameWithCompany: 'Stefano Galassi',
      passportFile: '/media/passports/test.png',
      passportExpired: false,
      passportExpiringSoon: true,
      nationalityName: 'Italy',
      nationalityCode: 'ITA',
      genderDisplay: 'Male',
      notifyDocumentsExpiration: true,
      active: true,
    });
  });

  it('maps paginated customer list responses using generated customer types', () => {
    let actual: any;

    service
      .list({ page: 2, pageSize: 5, query: 'gal', ordering: '-created_at', status: 'active' })
      .subscribe((response) => {
        actual = response;
      });

    const req = httpMock.expectOne(
      (request) =>
        request.url === '/api/customers/' &&
        request.params.get('page') === '2' &&
        request.params.get('page_size') === '5' &&
        request.params.get('status') === 'active' &&
        request.params.get('search') === 'gal' &&
        request.params.get('q') === 'gal' &&
        request.params.get('ordering') === '-created_at',
    );
    expect(req.request.method).toBe('GET');

    req.flush({
      count: 1,
      next: null,
      previous: null,
      results: [
        {
          id: 12,
          createdAt: '2026-03-03T00:00:00Z',
          updatedAt: '2026-03-04T00:00:00Z',
          fullName: 'Mario Rossi',
          fullNameWithCompany: 'Mario Rossi',
          email: 'mario@example.com',
          whatsapp: '+62 812 0000',
          passportNumber: 'A12345',
          nationalityName: 'Italy',
          nationalityCode: 'ITA',
          passportExpired: false,
          passportExpiringSoon: false,
          active: true,
          genderDisplay: '',
        },
      ],
    });

    expect(actual.count).toBe(1);
    expect(actual.results).toHaveLength(1);
    expect(actual.results[0]).toMatchObject({
      id: 12,
      fullName: 'Mario Rossi',
      fullNameWithCompany: 'Mario Rossi',
      email: 'mario@example.com',
      whatsapp: '+62 812 0000',
      passportNumber: 'A12345',
      nationalityName: 'Italy',
      nationalityCode: 'ITA',
    });
  });

  it('maps application history responses to generated history models with top-level productTypeDisplay', () => {
    let actual: any;

    service.getApplicationsHistory(21).subscribe((history) => {
      actual = history;
    });

    const req = httpMock.expectOne('/api/customers/21/applications-history/');
    expect(req.request.method).toBe('GET');

    req.flush({
      results: [
        {
          id: 31,
          customer: {
            id: 21,
            createdAt: '2026-03-01T00:00:00Z',
            updatedAt: '2026-03-02T00:00:00Z',
            customerType: 'person',
            firstName: 'Ada',
            lastName: 'Lovelace',
            fullName: 'Ada Lovelace',
            fullNameWithCompany: 'Ada Lovelace',
            passportExpired: false,
            passportExpiringSoon: false,
            nationalityName: 'United Kingdom',
            nationalityCode: 'GBR',
            genderDisplay: '',
            active: true,
          },
          product: {
            id: 9,
            name: 'Visa Extension',
            code: 'VX-1',
            productType: 'visa',
            basePrice: '1000000.00',
            retailPrice: '1500000.00',
            createdAt: '2026-03-01T00:00:00Z',
            updatedAt: '2026-03-02T00:00:00Z',
            createdBy: 'admin',
            updatedBy: 'admin',
            productCategory: 2,
            productCategoryName: 'Visa',
          },
          docDate: '2026-03-05',
          dueDate: '2026-03-10',
          addDeadlinesToCalendar: true,
          status: 'processing',
          notes: 'Priority',
          strField: 'VX-1 - Visa Extension',
          statusDisplay: 'Processing',
          productTypeDisplay: 'Visa',
          hasInvoice: true,
          invoiceId: 44,
          isDocumentCollectionCompleted: false,
          readyForInvoice: true,
          paymentStatus: 'pending_payment',
          paymentStatusDisplay: 'Pending Payment',
          invoiceStatus: 'sent',
          invoiceStatusDisplay: 'Sent',
          submissionWindowLastDate: '2026-03-12',
        },
      ],
    });

    expect(actual).toHaveLength(1);
    expect(actual[0]).toMatchObject({
      id: 31,
      docDate: '2026-03-05',
      dueDate: '2026-03-10',
      addDeadlinesToCalendar: true,
      status: 'processing',
      statusDisplay: 'Processing',
      productTypeDisplay: 'Visa',
      hasInvoice: true,
      invoiceId: 44,
      readyForInvoice: true,
      paymentStatus: 'pending_payment',
      paymentStatusDisplay: 'Pending Payment',
      invoiceStatus: 'sent',
      invoiceStatusDisplay: 'Sent',
      submissionWindowLastDate: '2026-03-12',
    });
    expect(actual[0].product).toMatchObject({
      id: 9,
      name: 'Visa Extension',
      code: 'VX-1',
      productType: 'visa',
    });
    expect(actual[0].customer).toMatchObject({
      id: 21,
      firstName: 'Ada',
      lastName: 'Lovelace',
      fullName: 'Ada Lovelace',
    });
  });
});
