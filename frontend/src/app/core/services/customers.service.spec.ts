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
      created_at: '2026-03-01T00:00:00Z',
      updated_at: '2026-03-02T00:00:00Z',
      customer_type: 'person',
      first_name: 'Stefano',
      last_name: 'Galassi',
      full_name: 'Stefano Galassi',
      full_name_with_company: 'Stefano Galassi',
      passport_file: 'media/passports/test.png',
      passport_expired: false,
      passport_expiring_soon: true,
      nationality_name: 'Italy',
      nationality_code: 'ITA',
      gender_display: 'Male',
      notify_documents_expiration: true,
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
          created_at: '2026-03-03T00:00:00Z',
          updated_at: '2026-03-04T00:00:00Z',
          full_name: 'Mario Rossi',
          full_name_with_company: 'Mario Rossi',
          email: 'mario@example.com',
          whatsapp: '+62 812 0000',
          passport_number: 'A12345',
          nationality_name: 'Italy',
          nationality_code: 'ITA',
          passport_expired: false,
          passport_expiring_soon: false,
          active: true,
          gender_display: '',
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
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-02T00:00:00Z',
            customer_type: 'person',
            first_name: 'Ada',
            last_name: 'Lovelace',
            full_name: 'Ada Lovelace',
            full_name_with_company: 'Ada Lovelace',
            passport_expired: false,
            passport_expiring_soon: false,
            nationality_name: 'United Kingdom',
            nationality_code: 'GBR',
            gender_display: '',
            active: true,
          },
          product: {
            id: 9,
            name: 'Visa Extension',
            code: 'VX-1',
            product_type: 'visa',
            base_price: '1000000.00',
            retail_price: '1500000.00',
            created_at: '2026-03-01T00:00:00Z',
            updated_at: '2026-03-02T00:00:00Z',
            created_by: 'admin',
            updated_by: 'admin',
            product_category: 2,
            product_category_name: 'Visa',
          },
          doc_date: '2026-03-05',
          due_date: '2026-03-10',
          add_deadlines_to_calendar: true,
          status: 'processing',
          notes: 'Priority',
          str_field: 'VX-1 - Visa Extension',
          status_display: 'Processing',
          product_type_display: 'Visa',
          has_invoice: true,
          invoice_id: 44,
          is_document_collection_completed: false,
          ready_for_invoice: true,
          payment_status: 'pending_payment',
          payment_status_display: 'Pending Payment',
          invoice_status: 'sent',
          invoice_status_display: 'Sent',
          submission_window_last_date: '2026-03-12',
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
