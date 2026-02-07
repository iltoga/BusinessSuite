import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface CustomerListItem {
  id: number;
  fullNameWithCompany: string;
  fullName?: string;
  email: string | null;
  telephone: string | null;
  whatsapp: string | null;
  passportNumber: string | null;
  passportExpirationDate: string | null;
  passportExpired: boolean;
  passportExpiringSoon: boolean;
  active: boolean;
  nationalityName: string;
  nationalityCode: string;
  createdAt: string;
  updatedAt: string | null;
}

export interface CustomerDetail extends CustomerListItem {
  customerType?: string | null;
  title?: string | null;
  firstName?: string | null;
  lastName?: string | null;
  companyName?: string | null;
  telegram?: string | null;
  facebook?: string | null;
  instagram?: string | null;
  twitter?: string | null;
  birthdate?: string | null;
  birthPlace?: string | null;
  addressBali?: string | null;
  addressAbroad?: string | null;
  nationality?: string | null;
  gender?: string | null;
  npwp?: string | null;
  passportIssueDate?: string | null;
  passportFile?: string | null;
  passportMetadata?: Record<string, unknown> | null;
  notifyDocumentsExpiration?: boolean | null;
  notifyBy?: string | null;
}

export interface UninvoicedApplication {
  id: number;
  customer: CustomerDetail;
  product: {
    id: number;
    name: string;
    code: string;
    product_type: string;
    base_price: string;
  };
  doc_date: string;
  due_date: string;
  status: string;
  notes: string;
  created_at: string;
  updated_at: string;
  created_by: number;
  updated_by: number;
  str_field: string;
}

export interface CountryCode {
  country: string;
  countryIdn: string;
  alpha2Code: string;
  alpha3Code: string;
  numericCode: string;
}

export interface PaginatedResponse<T> {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
}

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

  list(query: CustomerListQuery): Observable<PaginatedResponse<CustomerListItem>> {
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

    return this.http.get<PaginatedResponse<any>>(this.apiUrl, { params, headers }).pipe(
      map((response) => ({
        ...response,
        results: (response.results ?? []).map(this.mapCustomer),
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

  getCustomer(customerId: number): Observable<CustomerDetail> {
    const headers = this.buildHeaders();
    return this.http
      .get<any>(`${this.apiUrl}${customerId}/`, { headers })
      .pipe(map(this.mapCustomer));
  }

  createCustomer(payload: Record<string, unknown> | FormData): Observable<CustomerDetail> {
    const headers = this.buildHeaders();
    return this.http.post<any>(this.apiUrl, payload, { headers }).pipe(map(this.mapCustomer));
  }

  updateCustomer(
    customerId: number,
    payload: Record<string, unknown> | FormData,
  ): Observable<CustomerDetail> {
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

  getUninvoicedApplications(customerId: number): Observable<UninvoicedApplication[]> {
    const headers = this.buildHeaders();
    return this.http.get<UninvoicedApplication[]>(
      `/api/invoices/get_customer_applications/${customerId}/`,
      { headers },
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

  private readonly mapCustomer = (item: any): CustomerDetail => ({
    id: item.id,
    fullNameWithCompany:
      item.full_name_with_company ?? item.fullNameWithCompany ?? item.full_name ?? '',
    fullName: item.full_name ?? item.fullName ?? item.full_name_with_company ?? '',
    email: item.email ?? null,
    telephone: item.telephone ?? null,
    whatsapp: item.whatsapp ?? null,
    passportNumber: item.passport_number ?? item.passportNumber ?? null,
    passportIssueDate: item.passport_issue_date ?? item.passportIssueDate ?? null,
    passportExpirationDate: item.passport_expiration_date ?? item.passportExpirationDate ?? null,
    passportExpired: item.passport_expired ?? item.passportExpired ?? false,
    passportExpiringSoon: item.passport_expiring_soon ?? item.passportExpiringSoon ?? false,
    active: item.active ?? true,
    nationalityName: item.nationality_name ?? item.nationalityName ?? '',
    nationalityCode: item.nationality_code ?? item.nationalityCode ?? '',
    createdAt: item.created_at ?? item.createdAt ?? '',
    updatedAt: item.updated_at ?? item.updatedAt ?? null,
    customerType: item.customer_type ?? item.customerType ?? null,
    title: item.title ?? null,
    firstName: item.first_name ?? item.firstName ?? null,
    lastName: item.last_name ?? item.lastName ?? null,
    companyName: item.company_name ?? item.companyName ?? null,
    telegram: item.telegram ?? null,
    facebook: item.facebook ?? null,
    instagram: item.instagram ?? null,
    twitter: item.twitter ?? null,
    birthdate: item.birthdate ?? null,
    birthPlace: item.birth_place ?? item.birthPlace ?? null,
    addressBali: item.address_bali ?? item.addressBali ?? null,
    addressAbroad: item.address_abroad ?? item.addressAbroad ?? null,
    nationality: item.nationality ?? null,
    gender: item.gender ?? null,
    npwp: item.npwp ?? null,
    passportFile: item.passport_file ?? item.passportFile ?? null,
    passportMetadata: item.passport_metadata ?? item.passportMetadata ?? null,
    notifyDocumentsExpiration:
      item.notify_documents_expiration ?? item.notifyDocumentsExpiration ?? null,
    notifyBy: item.notify_by ?? item.notifyBy ?? null,
  });
}
