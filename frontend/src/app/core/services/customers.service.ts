/**
 * CustomersService — HTTP client wrapper for the customers API.
 *
 * ## Generated model migration
 * Customer-facing API models now come from `core/api/`, which is the
 * repository source of truth for OpenAPI-derived types.
 *
 * This service only performs lightweight URL normalization for file paths;
 * its payload mapping is otherwise aligned with the generated models.
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
import { unwrapApiRecord } from '@/core/utils/api-envelope';

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
    return this.http
      .post<{ id: number; active: boolean }>(`${this.apiUrl}${customerId}/toggle-active/`, {}, { headers })
      .pipe(
        map((response) => {
          const payload = unwrapApiRecord(response) as
            | {
                id?: number;
                active?: boolean;
              }
            | null;

          return {
            id: Number(payload?.id ?? customerId),
            active: Boolean(payload?.active),
          };
        }),
      );
  }

  getCustomer(customerId: number): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http
      .get<any>(`${this.apiUrl}${customerId}/`, { headers })
      .pipe(map((response) => this.mapCustomer(unwrapApiRecord(response) ?? response)));
  }

  createCustomer(payload: Record<string, unknown> | FormData): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http
      .post<any>(this.apiUrl, payload, { headers })
      .pipe(map((response) => this.mapCustomer(unwrapApiRecord(response) ?? response)));
  }

  updateCustomer(
    customerId: number,
    payload: Record<string, unknown> | FormData,
  ): Observable<Customer> {
    const headers = this.buildHeaders();
    return this.http
      .patch<any>(`${this.apiUrl}${customerId}/`, payload, { headers })
      .pipe(map((response) => this.mapCustomer(unwrapApiRecord(response) ?? response)));
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
      .post<{ deletedCount?: number }>(`${this.apiUrl}bulk-delete/`, payload, { headers })
      .pipe(
        map((response) => {
          const payload = unwrapApiRecord(response) as { deletedCount?: number; deleted_count?: number } | null;
          return {
            deletedCount: payload?.deletedCount ?? payload?.deleted_count ?? 0,
          };
        }),
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
    createdAt: item.createdAt ?? '',
    updatedAt: item.updatedAt ?? '',
    title: item.title ?? null,
    customerType: item.customerType ?? 'person',
    firstName: item.firstName ?? null,
    lastName: item.lastName ?? null,
    companyName: item.companyName ?? null,
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
    birthPlace: item.birthPlace ?? null,
    passportNumber: item.passportNumber ?? null,
    passportIssueDate: item.passportIssueDate ?? null,
    passportExpirationDate: item.passportExpirationDate ?? null,
    passportFile: this.normalizeFileUrl(item.passportFile ?? null),
    passportMetadata: item.passportMetadata ?? null,
    passportExpired: item.passportExpired ?? false,
    passportExpiringSoon: item.passportExpiringSoon ?? false,
    gender: item.gender ?? null,
    genderDisplay: item.genderDisplay ?? '',
    nationalityName: item.nationalityName ?? '',
    nationalityCode: item.nationalityCode ?? '',
    addressBali: item.addressBali ?? null,
    addressAbroad: item.addressAbroad ?? null,
    notifyDocumentsExpiration: item.notifyDocumentsExpiration ?? false,
    notifyBy: item.notifyBy ?? null,
    active: item.active ?? true,
    fullName: item.fullName ?? item.fullNameWithCompany ?? '',
    fullNameWithCompany: item.fullNameWithCompany ?? item.fullName ?? '',
  });

  private readonly mapProduct = (item: any): Product => ({
    id: Number(item?.id ?? 0),
    name: item?.name ?? '',
    code: item?.code ?? '',
    description: item?.description ?? '',
    immigrationId: item?.immigrationId ?? null,
    basePrice: item?.basePrice ?? null,
    retailPrice: item?.retailPrice ?? item?.basePrice ?? '0',
    currency: item?.currency ?? 'IDR',
    productCategory: Number(item?.productCategory ?? 0),
    productCategoryName: item?.productCategoryName ?? '',
    productType: item?.productType ?? '',
    validity: item?.validity ?? null,
    requiredDocuments: item?.requiredDocuments ?? '',
    optionalDocuments: item?.optionalDocuments ?? '',
    documentsMinValidity: item?.documentsMinValidity ?? null,
    applicationWindowDays: item?.applicationWindowDays ?? null,
    validationPrompt: item?.validationPrompt ?? '',
    deprecated: item?.deprecated ?? false,
    usesCustomerAppWorkflow: item?.usesCustomerAppWorkflow ?? false,
    createdAt: item?.createdAt ?? '',
    updatedAt: item?.updatedAt ?? '',
    createdBy: item?.createdBy ?? '',
    updatedBy: item?.updatedBy ?? '',
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
      docDate: item?.docDate ?? '',
      dueDate: item?.dueDate ?? null,
      status: item?.status ?? '',
      addDeadlinesToCalendar: item?.addDeadlinesToCalendar ?? false,
      notes: item?.notes ?? null,
      strField: item?.strField ?? '',
      statusDisplay: item?.statusDisplay ?? item?.status ?? '',
      productTypeDisplay: item?.productTypeDisplay ?? '',
      hasInvoice: Boolean(item?.hasInvoice ?? false),
      invoiceId: item?.invoiceId ?? null,
      isDocumentCollectionCompleted: Boolean(item?.isDocumentCollectionCompleted ?? false),
      readyForInvoice: Boolean(item?.readyForInvoice ?? false),
    };
  }

  private mapCustomerApplicationHistory(item: any): CustomerApplicationHistory {
    const base = this.mapUninvoicedApplication(item);
    const paymentStatus = (item?.paymentStatus ?? 'uninvoiced') as CustomerApplicationPaymentStatus;

    return {
      ...base,
      paymentStatus,
      paymentStatusDisplay:
        item?.paymentStatusDisplay ??
        (paymentStatus === 'paid'
          ? 'Paid'
          : paymentStatus === 'pending_payment'
            ? 'Pending Payment'
            : 'Uninvoiced'),
      invoiceStatus: item?.invoiceStatus ?? null,
      invoiceStatusDisplay:
        item?.invoiceStatusDisplay ?? (paymentStatus === 'uninvoiced' ? 'Uninvoiced' : '—'),
      submissionWindowLastDate: item?.submissionWindowLastDate ?? null,
    };
  }
}
