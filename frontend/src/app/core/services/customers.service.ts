/**
 * CustomersService — HTTP client wrapper for the customers API.
 *
 * ## Generated model migration
 * Customer-facing API models now come from `core/api/`, which is the
 * repository source of truth for OpenAPI-derived types.
 *
 * **Implementation note:** This service still performs light normalization so
 * UI callers remain resilient to snake_case payloads and relative file URLs,
 * but its public types should stay aligned with the generated models.
 *
 * ## Methods
 * | Method | Description |
 * |---|---|
 * | `getCustomers(query)` | Paginated customer list with search/filter params |
 * | `getCustomer(id)` | Full customer detail |
 * | `createCustomer(data)` | Create a new customer |
 * | `updateCustomer(id, data)` | Full or partial update |
 * | `deleteCustomer(id)` | Hard delete |
 * | `getUninvoicedApplications(customerId)` | Applications not yet linked to an invoice |
 * | `getApplicationHistory(customerId)` | Full payment-status history |
 * | `getCountryCodes()` | ISO country / nationality lookup list |
 */
import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import type {
  CountryCode,
  Customer,
  CustomerApplicationHistory,
  CustomerUninvoicedApplication,
  PaginatedCustomerApplicationHistoryList,
  PaginatedCustomerList,
  PaginatedCustomerUninvoicedApplicationList,
  Product,
} from '@/core/api';
import { AuthService } from '@/core/services/auth.service';

export type CustomerApplicationPaymentStatus = 'uninvoiced' | 'pending_payment' | 'paid';

export interface CustomerListQuery {
  page: number;
  pageSize: number;
  query?: string;
  ordering?: string;
  status?: 'all' | 'active' | 'disabled';
}

export interface BulkDeleteResult {
  deletedCount: number;
}

@Injectable({
  providedIn: 'root',
})
export class CustomersService {
  private http = inject(HttpClient);
  private authService = inject(AuthService);
  private apiUrl = '/api/customers/';

  list(query: CustomerListQuery): Observable<PaginatedCustomerList> {
    let params = new HttpParams()
      .set('page', query.page)
      .set('page_size', query.pageSize)
      .set('status', query.status ?? 'active');

    if (query.query) {
      params = params.set('search', query.query).set('q', query.query);
    }

    if (query.ordering) {
      params = params.set('ordering', query.ordering);
    }

    const token = this.authService.getToken();
    const headers = token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;

    return this.http
      .get<PaginatedCustomerList | Record<string, unknown>>(this.apiUrl, { params, headers })
      .pipe(
        map((response) => ({
          count:
            response && typeof response === 'object' && 'count' in response
              ? Number((response as { count?: number }).count ?? 0)
              : 0,
          next:
            response && typeof response === 'object' && 'next' in response
              ? ((response as { next?: string | null }).next ?? null)
              : null,
          previous:
            response && typeof response === 'object' && 'previous' in response
              ? ((response as { previous?: string | null }).previous ?? null)
              : null,
          results: this.extractResults(response).map((item) => this.mapCustomer(item)),
        })),
      );
  }

  toggleActive(customerId: number): Observable<{ id: number; active: boolean }> {
    const token = this.authService.getToken();
    const headers = token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
    return this.http.post<{ id: number; active: boolean }>(
      `${this.apiUrl}${customerId}/toggle-active/`,
      {},
      { headers },
    );
  }

  getCustomer(customerId: number): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http
      .get<any>(`${this.apiUrl}${customerId}/`, { headers })
      .pipe(map(this.mapCustomer));
  }

  createCustomer(payload: Record<string, unknown> | FormData): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http.post<any>(this.apiUrl, payload, { headers }).pipe(map(this.mapCustomer));
  }

  updateCustomer(
    customerId: number,
    payload: Record<string, unknown> | FormData,
  ): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http
      .patch<any>(`${this.apiUrl}${customerId}/`, payload, { headers })
      .pipe(map(this.mapCustomer));
  }

  deleteCustomer(customerId: number): Observable<void> {
    const headers = this.buildHeaders();
    return this.http.delete<void>(`${this.apiUrl}${customerId}/`, { headers });
  }

  bulkDeleteCustomers(query?: string, hideDisabled: boolean = true): Observable<BulkDeleteResult> {
    const headers = this.buildHeaders();
    const payload = {
      searchQuery: query ?? '',
      hideDisabled,
    };
    return this.http
      .post<{
        deletedCount?: number;
        deleted_count?: number;
      }>(`${this.apiUrl}bulk-delete/`, payload, { headers })
      .pipe(
        map((response) => ({
          deletedCount: response.deletedCount ?? response.deleted_count ?? 0,
        })),
      );
  }

  getUninvoicedApplications(customerId: number): Observable<CustomerUninvoicedApplication[]> {
    const headers = this.buildHeaders();
    return this.http
      .get<
        | PaginatedCustomerUninvoicedApplicationList
        | CustomerUninvoicedApplication[]
        | Record<string, unknown>
      >(`/api/customers/${customerId}/uninvoiced-applications/`, { headers })
      .pipe(
        map((response) =>
          this.extractResults(response).map((item) => this.mapUninvoicedApplication(item)),
        ),
      );
  }

  getApplicationsHistory(customerId: number): Observable<CustomerApplicationHistory[]> {
    const headers = this.buildHeaders();
    return this.http
      .get<
        | PaginatedCustomerApplicationHistoryList
        | CustomerApplicationHistory[]
        | Record<string, unknown>
      >(`/api/customers/${customerId}/applications-history/`, { headers })
      .pipe(
        map((response) =>
          this.extractResults(response).map((item) => this.mapCustomerApplicationHistory(item)),
        ),
      );
  }

  getCountries(): Observable<CountryCode[]> {
    const headers = this.buildHeaders();
    return this.http.get<CountryCode[]>('/api/country-codes/', { headers });
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  private extractResults<T>(
    response: T[] | { results?: T[] } | Record<string, unknown> | null | undefined,
  ): T[] {
    if (Array.isArray(response)) {
      return response;
    }
    if (
      response &&
      typeof response === 'object' &&
      Array.isArray((response as { results?: T[] }).results)
    ) {
      return (response as { results: T[] }).results;
    }
    return [];
  }

  private readonly mapCustomer = (item: any): Customer => ({
    id: item.id,
    createdAt: item.created_at ?? item.createdAt ?? '',
    updatedAt: item.updated_at ?? item.updatedAt ?? '',
    title: item.title ?? null,
    customerType: item.customer_type ?? item.customerType ?? 'person',
    firstName: item.first_name ?? item.firstName ?? null,
    lastName: item.last_name ?? item.lastName ?? null,
    companyName: item.company_name ?? item.companyName ?? null,
    email: item.email ?? null,
    telephone: item.telephone ?? null,
    whatsapp: item.whatsapp ?? null,
    telegram: item.telegram ?? null,
    facebook: item.facebook ?? null,
    instagram: item.instagram ?? null,
    twitter: item.twitter ?? null,
    npwp: item.npwp ?? null,
    nationality: item.nationality ?? null,
    birthdate: item.birthdate ?? null,
    birthPlace: item.birth_place ?? item.birthPlace ?? null,
    passportNumber: item.passport_number ?? item.passportNumber ?? null,
    passportIssueDate: item.passport_issue_date ?? item.passportIssueDate ?? null,
    passportExpirationDate: item.passport_expiration_date ?? item.passportExpirationDate ?? null,
    passportFile: this.normalizeFileUrl(item.passport_file ?? item.passportFile ?? null),
    passportMetadata: item.passport_metadata ?? item.passportMetadata ?? null,
    passportExpired: item.passport_expired ?? item.passportExpired ?? false,
    passportExpiringSoon: item.passport_expiring_soon ?? item.passportExpiringSoon ?? false,
    gender: item.gender ?? null,
    genderDisplay: item.gender_display ?? item.genderDisplay ?? '',
    nationalityName: item.nationality_name ?? item.nationalityName ?? '',
    nationalityCode: item.nationality_code ?? item.nationalityCode ?? '',
    addressBali: item.address_bali ?? item.addressBali ?? null,
    addressAbroad: item.address_abroad ?? item.addressAbroad ?? null,
    notifyDocumentsExpiration:
      item.notify_documents_expiration ?? item.notifyDocumentsExpiration ?? false,
    notifyBy: item.notify_by ?? item.notifyBy ?? null,
    active: item.active ?? true,
    fullName: item.full_name ?? item.fullName ?? item.full_name_with_company ?? '',
    fullNameWithCompany:
      item.full_name_with_company ?? item.fullNameWithCompany ?? item.full_name ?? '',
  });

  private readonly mapProduct = (item: any): Product => ({
    id: Number(item?.id ?? 0),
    name: item?.name ?? '',
    code: item?.code ?? '',
    description: item?.description ?? '',
    immigrationId: item?.immigration_id ?? item?.immigrationId ?? null,
    basePrice: item?.base_price ?? item?.basePrice ?? null,
    retailPrice:
      item?.retail_price ?? item?.retailPrice ?? item?.base_price ?? item?.basePrice ?? '0',
    currency: item?.currency ?? 'IDR',
    productCategory: Number(item?.product_category ?? item?.productCategory ?? 0),
    productCategoryName: item?.product_category_name ?? item?.productCategoryName ?? '',
    productType: item?.product_type ?? item?.productType ?? '',
    validity: item?.validity ?? null,
    requiredDocuments: item?.required_documents ?? item?.requiredDocuments ?? '',
    optionalDocuments: item?.optional_documents ?? item?.optionalDocuments ?? '',
    documentsMinValidity: item?.documents_min_validity ?? item?.documentsMinValidity ?? null,
    applicationWindowDays: item?.application_window_days ?? item?.applicationWindowDays ?? null,
    validationPrompt: item?.validation_prompt ?? item?.validationPrompt ?? '',
    deprecated: item?.deprecated ?? false,
    usesCustomerAppWorkflow:
      item?.uses_customer_app_workflow ?? item?.usesCustomerAppWorkflow ?? false,
    createdAt: item?.created_at ?? item?.createdAt ?? '',
    updatedAt: item?.updated_at ?? item?.updatedAt ?? '',
    createdBy: item?.created_by ?? item?.createdBy ?? '',
    updatedBy: item?.updated_by ?? item?.updatedBy ?? '',
  });

  private normalizeFileUrl(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    // Keep already-absolute/special URLs intact.
    if (
      trimmed.startsWith('http://') ||
      trimmed.startsWith('https://') ||
      trimmed.startsWith('data:') ||
      trimmed.startsWith('blob:')
    ) {
      return trimmed;
    }
    // Convert relative storage paths (e.g. "documents/...") to root-relative URLs.
    if (!trimmed.startsWith('/')) {
      return `/${trimmed}`;
    }
    return trimmed;
  }

  private mapUninvoicedApplication(item: any): CustomerUninvoicedApplication {
    return {
      id: Number(item?.id ?? 0),
      customer: this.mapCustomer(item?.customer ?? {}),
      product: this.mapProduct(item?.product ?? {}),
      docDate: item?.docDate ?? item?.doc_date ?? '',
      dueDate: item?.dueDate ?? item?.due_date ?? null,
      status: item?.status ?? '',
      addDeadlinesToCalendar:
        item?.addDeadlinesToCalendar ?? item?.add_deadlines_to_calendar ?? false,
      notes: item?.notes ?? null,
      strField: item?.strField ?? item?.str_field ?? '',
      statusDisplay: item?.statusDisplay ?? item?.status_display ?? item?.status ?? '',
      productTypeDisplay:
        item?.productTypeDisplay ??
        item?.product_type_display ??
        item?.product?.productTypeDisplay ??
        '',
      hasInvoice: Boolean(item?.hasInvoice ?? item?.has_invoice ?? false),
      invoiceId: item?.invoiceId ?? item?.invoice_id ?? null,
      isDocumentCollectionCompleted: Boolean(
        item?.isDocumentCollectionCompleted ?? item?.is_document_collection_completed ?? false,
      ),
      readyForInvoice: Boolean(item?.readyForInvoice ?? item?.ready_for_invoice ?? false),
    };
  }

  private mapCustomerApplicationHistory(item: any): CustomerApplicationHistory {
    const base = this.mapUninvoicedApplication(item);
    const paymentStatus = (item?.paymentStatus ??
      item?.payment_status ??
      'uninvoiced') as CustomerApplicationPaymentStatus;

    return {
      ...base,
      paymentStatus,
      paymentStatusDisplay:
        item?.paymentStatusDisplay ??
        item?.payment_status_display ??
        (paymentStatus === 'paid'
          ? 'Paid'
          : paymentStatus === 'pending_payment'
            ? 'Pending Payment'
            : 'Uninvoiced'),
      invoiceStatus: item?.invoiceStatus ?? item?.invoice_status ?? null,
      invoiceStatusDisplay:
        item?.invoiceStatusDisplay ??
        item?.invoice_status_display ??
        item?.invoiceStatus ??
        item?.invoice_status ??
        (paymentStatus === 'uninvoiced' ? 'Uninvoiced' : '—'),
      submissionWindowLastDate:
        item?.submissionWindowLastDate ?? item?.submission_window_last_date ?? null,
    };
  }
}
