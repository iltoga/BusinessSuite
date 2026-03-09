import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

/**
 * Base HTTP service providing common HTTP operations with authentication
 * 
 * Extend this class to create services with consistent HTTP handling:
 * 
 * @example
 * ```typescript
 * @Injectable({ providedIn: 'root' })
 * export class CustomersService extends BaseHttpService {
 *   list(params?: any): Observable<Customer[]> {
 *     return this.get<Customer[]>('/api/customers/', { params });
 *   }
 *   
 *   create(data: CustomerCreateDto): Observable<Customer> {
 *     return this.post<Customer>('/api/customers/', data);
 *   }
 * }
 * ```
 */
@Injectable()
export abstract class BaseHttpService {
  protected readonly http = inject(HttpClient);
  protected readonly authService = inject(AuthService);

  /**
   * Build HTTP headers with authentication token
   * 
   * @param additional - Additional headers to include
   * @returns HttpHeaders with authentication
   */
  protected buildHeaders(additional?: HttpHeaders): HttpHeaders {
    const token = this.authService.getToken();
    let headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    if (token) {
      headers = headers.set('Authorization', `Bearer ${token}`);
    }

    if (additional) {
      additional.keys().forEach(key => {
        const value = additional.getAll(key);
        if (value) {
          headers = headers.set(key, value);
        }
      });
    }

    return headers;
  }

  /**
   * Build form-data headers with authentication token
   * 
   * @param additional - Additional headers to include
   * @returns HttpHeaders for form-data requests
   */
  protected buildFormDataHeaders(additional?: HttpHeaders): HttpHeaders {
    const token = this.authService.getToken();
    let headers = new HttpHeaders();

    if (token) {
      headers = headers.set('Authorization', `Bearer ${token}`);
    }

    if (additional) {
      additional.keys().forEach(key => {
        const value = additional.getAll(key);
        if (value) {
          headers = headers.set(key, value);
        }
      });
    }

    return headers;
  }

  /**
   * HTTP GET request with authentication
   * 
   * @param url - The endpoint URL
   * @param options - Request options
   * @returns Observable of response type
   */
  protected get<T>(url: string, options?: {
    params?: HttpParams | Record<string, any>;
    headers?: HttpHeaders;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildHeaders(options?.headers),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.get<T>(url, httpOptions);
  }

  /**
   * HTTP POST request with authentication
   * 
   * @param url - The endpoint URL
   * @param body - Request body
   * @param options - Request options
   * @returns Observable of response type
   */
  protected post<T>(url: string, body: any, options?: {
    params?: HttpParams | Record<string, any>;
    headers?: HttpHeaders;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildHeaders(options?.headers),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.post<T>(url, body, httpOptions);
  }

  /**
   * HTTP POST request with form-data
   * 
   * @param url - The endpoint URL
   * @param formData - Form data to send
   * @param options - Request options
   * @returns Observable of response type
   */
  protected postFormData<T>(url: string, formData: FormData, options?: {
    params?: HttpParams | Record<string, any>;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildFormDataHeaders(),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.post<T>(url, formData, httpOptions);
  }

  /**
   * HTTP PUT request with authentication
   * 
   * @param url - The endpoint URL
   * @param body - Request body
   * @param options - Request options
   * @returns Observable of response type
   */
  protected put<T>(url: string, body: any, options?: {
    params?: HttpParams | Record<string, any>;
    headers?: HttpHeaders;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildHeaders(options?.headers),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.put<T>(url, body, httpOptions);
  }

  /**
   * HTTP PUT request with form-data
   * 
   * @param url - The endpoint URL
   * @param formData - Form data to send
   * @param options - Request options
   * @returns Observable of response type
   */
  protected putFormData<T>(url: string, formData: FormData, options?: {
    params?: HttpParams | Record<string, any>;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildFormDataHeaders(),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.put<T>(url, formData, httpOptions);
  }

  /**
   * HTTP PATCH request with authentication
   * 
   * @param url - The endpoint URL
   * @param body - Request body
   * @param options - Request options
   * @returns Observable of response type
   */
  protected patch<T>(url: string, body: any, options?: {
    params?: HttpParams | Record<string, any>;
    headers?: HttpHeaders;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildHeaders(options?.headers),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.patch<T>(url, body, httpOptions);
  }

  /**
   * HTTP PATCH request with form-data
   * 
   * @param url - The endpoint URL
   * @param formData - Form data to send
   * @param options - Request options
   * @returns Observable of response type
   */
  protected patchFormData<T>(url: string, formData: FormData, options?: {
    params?: HttpParams | Record<string, any>;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams } = {
      headers: this.buildFormDataHeaders(),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    return this.http.patch<T>(url, formData, httpOptions);
  }

  /**
   * HTTP DELETE request with authentication
   * 
   * @param url - The endpoint URL
   * @param options - Request options
   * @returns Observable of response type
   */
  protected delete<T>(url: string, options?: {
    params?: HttpParams | Record<string, any>;
    headers?: HttpHeaders;
    body?: any;
  }): Observable<T> {
    let httpOptions: { headers: HttpHeaders, params?: HttpParams, body?: any } = {
      headers: this.buildHeaders(options?.headers),
    };

    if (options?.params) {
      httpOptions = {
        ...httpOptions,
        params: options.params instanceof HttpParams
          ? options.params
          : new HttpParams({ fromObject: options.params }),
      };
    }

    if (options?.body !== undefined) {
      httpOptions = { ...httpOptions, body: options.body };
    }

    return this.http.delete<T>(url, httpOptions);
  }

  // Response normalization utilities

  /**
   * Convert a value to a number, returning a default if invalid
   */
  protected asNumber(value: unknown, defaultValue = 0): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : defaultValue;
  }

  /**
   * Convert a value to a nullable number
   */
  protected asNullableNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === '') return null;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  /**
   * Convert a value to a string, returning a default if null/undefined
   */
  protected asString(value: unknown, defaultValue = ''): string {
    return value != null ? String(value) : defaultValue;
  }

  /**
   * Convert a value to a nullable string
   */
  protected asNullableString(value: unknown): string | null {
    return value != null ? String(value) : null;
  }

  /**
   * Convert a value to an array
   */
  protected asArray<T>(value: unknown): T[] {
    return Array.isArray(value) ? value : [];
  }

  /**
   * Convert a value to a record (object)
   */
  protected asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' && !Array.isArray(value)
      ? value as Record<string, unknown>
      : {};
  }

  /**
   * Convert a value to a boolean
   */
  protected asBoolean(value: unknown, defaultValue = false): boolean {
    if (typeof value === 'boolean') return value;
    if (typeof value === 'string') {
      return ['true', '1', 'yes', 'y'].includes(value.toLowerCase());
    }
    if (typeof value === 'number') {
      return value !== 0;
    }
    return defaultValue;
  }

  /**
   * Safely access a nested property by path
   * 
   * @param obj - The object to access
   * @param path - Dot-separated path (e.g., 'user.address.city')
   * @param defaultValue - Default value if path doesn't exist
   */
  protected getNestedProperty<T = unknown>(
    obj: Record<string, unknown>,
    path: string,
    defaultValue?: T
  ): T | undefined {
    const keys = path.split('.');
    let current: unknown = obj;

    for (const key of keys) {
      if (current == null || typeof current !== 'object') {
        return defaultValue;
      }
      current = (current as Record<string, unknown>)[key];
    }

    return (current as T) ?? defaultValue;
  }
}
