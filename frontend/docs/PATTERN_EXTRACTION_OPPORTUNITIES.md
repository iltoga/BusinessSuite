# Code Pattern Extraction Opportunities

## Executive Summary

This document identifies opportunities for extracting shared patterns into base classes, utilities, and services across the Angular application. Following the successful refactoring of 8 core components (100% completion) into base classes, significant additional opportunities exist.

**Total Estimated Code Reduction: 3,110 - 4,690 lines**

---

## Priority Matrix

| Priority  | Pattern                        | Files         | Code Reduction | Effort   |
| --------- | ------------------------------ | ------------- | -------------- | -------- |
| 🔴 HIGH   | Migrate admin list components  | 4+            | 600-800 lines  | 8-12 hrs |
| 🔴 HIGH   | Migrate admin form components  | 4+            | 800-1200 lines | 8-16 hrs |
| 🔴 HIGH   | Create BaseHttpService         | 10+ services  | 500-800 lines  | 4-6 hrs  |
| 🟡 MEDIUM | Shared utility modules         | 10+ files     | 200-300 lines  | 3-4 hrs  |
| 🟡 MEDIUM | SSE connection service         | 3+ components | 300-450 lines  | 4-6 hrs  |
| 🟡 MEDIUM | File upload/download utils     | 5+ components | 100-150 lines  | 2-3 hrs  |
| 🟡 MEDIUM | Form validation utils          | 5+ components | 250-400 lines  | 3-4 hrs  |
| 🟢 LOW    | Job tracking enhancement       | 3+ components | 60-90 lines    | 1-2 hrs  |
| 🟢 LOW    | Error handling standardization | 20+ files     | 50-100 lines   | 2-3 hrs  |

---

## 1. HIGH PRIORITY: Admin Component Migration

### 1.1 List Components Not Using BaseListComponent

**Affected Components:**

- `ai-model-list.component.ts`
- `holidays.component.ts`
- `document-types.component.ts`
- `backups.component.ts`

**Current Pattern (repeated in each):**

```typescript
// State management
readonly items = signal<T[]>([]);
readonly query = signal('');
readonly loading = signal(false);
readonly ordering = signal('field');

// Pagination handlers
onQueryChange(value: string): void { ... }
onSortChange(event: SortEvent): void { ... }

// Keyboard shortcuts
@HostListener('window:keydown', ['$event'])
handleGlobalKeydown(event: KeyboardEvent): void { ... }

// Navigation state restoration
const state = (window as any).history.state ?? {};
// restore searchQuery, page, etc.
```

**Recommendation:** Extend `BaseListComponent<T>`

**Benefits:**

- 40-60% code reduction per component
- Consistent keyboard shortcuts
- Automatic navigation state management
- Built-in bulk delete support

**Migration Steps:**

1. Change class to extend `BaseListComponent<T>`
2. Implement `loadItems()` method
3. Move columns/actions to computed properties
4. Remove duplicated state and handlers

---

### 1.2 Form Components Not Using BaseFormComponent

**Affected Components:**

- `ai-model-form.component.ts`
- Holiday form dialog
- Document-type form dialog
- `application-settings.component.ts`

**Current Pattern (repeated in each):**

```typescript
// Form state
readonly isSaving = signal(false);
readonly isEditMode = signal(false);
readonly form = this.fb.group({ ... });

// Save method
save(): void {
  this.form.markAllAsTouched();
  if (this.form.invalid) {
    this.toast.error('Please fill in all required fields');
    return;
  }
  this.isSaving.set(true);
  const payload = this.form.getRawValue();
  const req = id ? this.http.put(url, payload) : this.http.post(url, payload);
  req.subscribe({
    next: () => { this.router.navigate([...]); },
    error: (error) => {
      const message = extractServerErrorMessage(error);
      this.toast.error(message);
      applyServerErrorsToForm(this.form, error);
    },
    finalize: () => this.isSaving.set(false)
  });
}

// Keyboard shortcuts
@HostListener('window:keydown', ['$event'])
handleGlobalKeydown(event: KeyboardEvent): void {
  if ((event.ctrlKey || event.metaKey) && event.key === 's') {
    event.preventDefault();
    this.onSubmit();
  }
  if (event.key === 'Escape') {
    this.onCancel();
  }
}
```

**Recommendation:** Extend `BaseFormComponent<T, CreateDto, UpdateDto>`

**Benefits:**

- 50-70% code reduction per component
- Consistent error handling
- Automatic edit mode detection
- Built-in keyboard shortcuts

---

## 2. HIGH PRIORITY: BaseHttpService

### Current Problem

Every service duplicates HTTP infrastructure code:

```typescript
// Duplicated in 10+ services
private buildHeaders(): HttpHeaders | undefined {
  const token = this.authService.getToken();
  return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
}

// Duplicated response normalization
private readonly mapCustomer = (item: any): CustomerDetail => ({
  id: item.id,
  fullName: item.full_name ?? item.fullName,
  passportNumber: item.passport_number ?? item.passportNumber,
  // ... dozens of field mappings
});

// Duplicated type guards
private asRecord(value: unknown): Record<string, unknown> { ... }
private toNumber(value: unknown): number { ... }
private toOptionalString(value: unknown): string | undefined { ... }
```

### Proposed Solution

Create `/core/services/base-http.service.ts`:

```typescript
@Injectable({ providedIn: 'root' })
export abstract class BaseHttpService {
  protected readonly http = inject(HttpClient);
  protected readonly authService = inject(AuthService);

  protected buildHeaders(additional?: HttpHeaders): HttpHeaders {
    const token = this.authService.getToken();
    const headers = new HttpHeaders({
      'Content-Type': 'application/json',
    });

    const withAuth = token ? headers.set('Authorization', `Bearer ${token}`) : headers;

    return additional ? withAuth.set(additional) : withAuth;
  }

  protected get<T>(url: string, options?: any): Observable<T> {
    return this.http.get<T>(url, { headers: this.buildHeaders(), ...options });
  }

  protected post<T>(url: string, body: any, options?: any): Observable<T> {
    return this.http.post<T>(url, body, { headers: this.buildHeaders(), ...options });
  }

  protected put<T>(url: string, body: any, options?: any): Observable<T> {
    return this.http.put<T>(url, body, { headers: this.buildHeaders(), ...options });
  }

  protected patch<T>(url: string, body: any, options?: any): Observable<T> {
    return this.http.patch<T>(url, body, { headers: this.buildHeaders(), ...options });
  }

  protected delete<T>(url: string, options?: any): Observable<T> {
    return this.http.delete<T>(url, { headers: this.buildHeaders(), ...options });
  }

  // Response normalization utilities
  protected asRecord(value: unknown): Record<string, unknown> {
    return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
  }

  protected toNumber(value: unknown, defaultValue = 0): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : defaultValue;
  }

  protected toString(value: unknown, defaultValue = ''): string {
    return value != null ? String(value) : defaultValue;
  }

  protected toArray<T>(value: unknown, mapper?: (item: any) => T): T[] {
    if (!Array.isArray(value)) return [];
    return mapper ? value.map(mapper) : value;
  }
}
```

**Usage Example:**

```typescript
@Injectable({ providedIn: 'root' })
export class CustomersService extends BaseHttpService {
  list(params: any): Observable<CustomerListResponse> {
    return this.get('/api/customers/', { params });
  }

  private mapCustomer(item: any): CustomerDetail {
    return {
      id: this.toNumber(item.id),
      fullName: this.toString(item.full_name),
      passportNumber: this.toString(item.passport_number),
    };
  }
}
```

**Benefits:**

- 30-40% code reduction across services
- Consistent auth header handling
- Standardized response normalization
- Easier testing with mock services

---

## 3. MEDIUM PRIORITY: Shared Utility Modules

### 3.1 Currency Formatting Utility

**Current:** Duplicated in 4+ components

**Proposed:** `/shared/utils/currency.ts`

```typescript
export interface FormatCurrencyOptions {
  currency?: string;
  locale?: string;
  minimumFractionDigits?: number;
  maximumFractionDigits?: number;
}

export function formatCurrency(
  value: string | number | null | undefined,
  options: FormatCurrencyOptions = {},
): string {
  if (value === null || value === undefined || value === '') return '—';

  const num = Number(value);
  if (Number.isNaN(num)) return String(value);

  const {
    currency = 'IDR',
    locale = 'id-ID',
    minimumFractionDigits = 0,
    maximumFractionDigits = 0,
  } = options;

  try {
    return new Intl.NumberFormat(locale, {
      style: 'currency',
      currency,
      minimumFractionDigits,
      maximumFractionDigits,
    }).format(num);
  } catch {
    return `${currency} ${num.toLocaleString(locale)}`;
  }
}

export function parseCurrency(value: string): number | null {
  const cleaned = value.replace(/[^0-9.-]/g, '');
  const parsed = parseFloat(cleaned);
  return Number.isFinite(parsed) ? parsed : null;
}
```

---

### 3.2 Date Parsing Utility

**Current:** Duplicated in 3+ components

**Proposed:** `/shared/utils/date-parsing.ts`

```typescript
export interface ParseDateOptions {
  formats?: string[];
  strict?: boolean;
}

export function parseDate(value: unknown, options: ParseDateOptions = {}): Date | null {
  if (value instanceof Date) {
    return isNaN(value.getTime()) ? null : value;
  }

  if (typeof value !== 'string') return null;

  const trimmed = value.trim();
  if (!trimmed) return null;

  const { formats = ['ISO'], strict = false } = options;

  // Try ISO format first
  if (formats.includes('ISO')) {
    const isoMatch = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (isoMatch) {
      const [, year, month, day] = isoMatch.map(Number);
      const date = new Date(year, month - 1, day);
      if (date.getFullYear() === year && date.getMonth() === month - 1 && date.getDate() === day) {
        return date;
      }
    }
  }

  // Try generic parsing
  if (formats.includes('generic')) {
    const parsed = new Date(trimmed);
    if (!isNaN(parsed.getTime())) {
      return strict ? null : new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
  }

  return null;
}

export function formatDate(date: Date | null, format = 'yyyy-MM-dd'): string {
  if (!date) return '';

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  switch (format) {
    case 'yyyy-MM-dd':
      return `${year}-${month}-${day}`;
    case 'dd-MM-yyyy':
      return `${day}-${month}-${year}`;
    case 'dd/MM/yyyy':
      return `${day}/${month}/${year}`;
    case 'MM/dd/yyyy':
      return `${month}/${day}/${year}`;
    default:
      return `${year}-${month}-${day}`;
  }
}
```

---

### 3.3 Type Guard Utility

**Current:** Duplicated in 5+ files

**Proposed:** `/shared/utils/type-guards.ts`

```typescript
export function asNumber(value: unknown, defaultValue = 0): number {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : defaultValue;
}

export function asNullableNumber(value: unknown): number | null {
  if (value === null || value === undefined || value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

export function asString(value: unknown, defaultValue = ''): string {
  return value != null ? String(value) : defaultValue;
}

export function asNullableString(value: unknown): string | null {
  return value != null ? String(value) : null;
}

export function asArray<T>(value: unknown): T[] {
  return Array.isArray(value) ? value : [];
}

export function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : {};
}

export function asBoolean(value: unknown, defaultValue = false): boolean {
  if (typeof value === 'boolean') return value;
  if (typeof value === 'string') {
    return ['true', '1', 'yes'].includes(value.toLowerCase());
  }
  return defaultValue;
}
```

---

## 4. MEDIUM PRIORITY: SSE Connection Service

### Current Pattern (duplicated in 3+ components)

```typescript
private sseSubscription: Subscription | null = null;
private reconnectTimeoutId: number | null = null;
private reconnectAttempt = 0;
private readonly reconnectBaseDelayMs = 2000;
private readonly reconnectMaxDelayMs = 30000;

private connectLiveStream(): void {
  this.clearReconnectTimeout();
  this.liveConnecting.set(true);
  this.liveConnected.set(false);
  this.streamSubscription?.unsubscribe();
  this.streamSubscription = this.sseService.connect(url).subscribe({
    next: (event) => this.handleLiveEvent(event),
    error: () => {
      this.liveConnecting.set(false);
      this.liveConnected.set(false);
      this.scheduleReconnect();
    },
  });
}

private scheduleReconnect(): void {
  this.clearReconnectTimeout();
  const delay = Math.min(
    this.reconnectMaxDelayMs,
    this.reconnectBaseDelayMs * 2 ** this.reconnectAttempt,
  );
  this.reconnectAttempt += 1;
  this.reconnectTimeoutId = window.setTimeout(() => this.connectLiveStream(), delay);
}

private clearReconnectTimeout(): void {
  if (this.reconnectTimeoutId !== null) {
    window.clearTimeout(this.reconnectTimeoutId);
    this.reconnectTimeoutId = null;
  }
}

ngOnDestroy(): void {
  this.clearReconnectTimeout();
  this.streamSubscription?.unsubscribe();
}
```

### Proposed Solution

Create `/core/services/sse-connection.service.ts`:

```typescript
export interface SseConnectionConfig {
  url: string;
  reconnectBaseDelayMs?: number;
  reconnectMaxDelayMs?: number;
  maxReconnectAttempts?: number;
}

export interface SseConnectionState {
  connected: boolean;
  connecting: boolean;
  error: string | null;
  reconnectAttempt: number;
}

@Injectable({ providedIn: 'root' })
export class SseConnectionService implements OnDestroy {
  private readonly sseService = inject(SseService);
  private readonly destroyRef = inject(DestroyRef);

  private subscription: Subscription | null = null;
  private reconnectTimeoutId: number | null = null;
  private reconnectAttempt = 0;

  private readonly state = signal<SseConnectionState>({
    connected: false,
    connecting: false,
    error: null,
    reconnectAttempt: 0,
  });

  readonly connected = computed(() => this.state().connected);
  readonly connecting = computed(() => this.state().connecting);
  readonly error = computed(() => this.state().error);

  connect(config: SseConnectionConfig): Observable<any> {
    const {
      url,
      reconnectBaseDelayMs = 2000,
      reconnectMaxDelayMs = 30000,
      maxReconnectAttempts = 10,
    } = config;

    return new Observable((observer) => {
      const connect = () => {
        this.updateState({ connecting: true, connected: false, error: null });

        this.subscription = this.sseService.connect(url).subscribe({
          next: (event) => {
            this.updateState({ connecting: false, connected: true, error: null });
            this.reconnectAttempt = 0;
            observer.next(event);
          },
          error: (err) => {
            this.reconnectAttempt++;

            if (this.reconnectAttempt >= maxReconnectAttempts) {
              this.updateState({
                connecting: false,
                connected: false,
                error: 'Max reconnect attempts reached',
                reconnectAttempt: this.reconnectAttempt,
              });
              observer.error(err);
              return;
            }

            const delay = Math.min(
              reconnectMaxDelayMs,
              reconnectBaseDelayMs * 2 ** this.reconnectAttempt,
            );

            this.updateState({
              connecting: false,
              connected: false,
              error: `Reconnecting in ${Math.round(delay / 1000)}s...`,
              reconnectAttempt: this.reconnectAttempt,
            });

            this.reconnectTimeoutId = window.setTimeout(connect, delay);
          },
          complete: () => {
            this.updateState({ connecting: false, connected: false, error: null });
            observer.complete();
          },
        });
      };

      connect();

      // Cleanup on unsubscribe
      return () => {
        this.clearReconnectTimeout();
        this.subscription?.unsubscribe();
      };
    });
  }

  disconnect(): void {
    this.clearReconnectTimeout();
    this.subscription?.unsubscribe();
    this.updateState({ connected: false, connecting: false, error: null });
  }

  private updateState(partial: Partial<SseConnectionState>): void {
    this.state.update((current) => ({ ...current, ...partial }));
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeoutId !== null) {
      window.clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
  }

  ngOnDestroy(): void {
    this.disconnect();
  }
}
```

**Usage:**

```typescript
@Component({...})
export class BackupsComponent implements OnInit, OnDestroy {
  private readonly sseConnection = inject(SseConnectionService);
  private readonly destroyRef = inject(DestroyRef);

  ngOnInit(): void {
    this.sseConnection
      .connect({ url: '/api/backups/stream/' })
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(event => this.handleBackupEvent(event));
  }

  // Access connection state
  readonly isConnected = this.sseConnection.connected;
  readonly isConnecting = this.sseConnection.connecting;
  readonly connectionError = this.sseConnection.error;
}
```

---

## 5. MEDIUM PRIORITY: File Upload/Download Utilities

### Current Pattern

Duplicated file handling across components.

### Proposed Enhancement

Enhance existing `/shared/utils/file-download.ts` and create `/shared/utils/file-upload.ts`:

```typescript
// file-download.ts
export function downloadBlob(blob: Blob, filename: string): void {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
}

export function downloadFromUrl(url: string, filename: string): void {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.target = '_blank';
  link.click();
}

// file-upload.ts
export interface UploadProgress {
  loaded: number;
  total: number;
  percentage: number;
}

export function uploadWithProgress(
  http: HttpClient,
  url: string,
  file: File,
  additionalData?: Record<string, any>,
  headers?: HttpHeaders,
): Observable<{ progress: UploadProgress; response?: any }> {
  const formData = new FormData();
  formData.append('file', file);

  if (additionalData) {
    Object.entries(additionalData).forEach(([key, value]) => {
      formData.append(key, String(value));
    });
  }

  return new Observable((observer) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url, true);
    xhr.responseType = 'json';

    if (headers) {
      headers.forEach((value, key) => {
        xhr.setRequestHeader(key, value);
      });
    }

    xhr.upload.onprogress = (event) => {
      if (event.lengthComputable) {
        observer.next({
          progress: {
            loaded: event.loaded,
            total: event.total,
            percentage: Math.round((event.loaded / event.total) * 100),
          },
        });
      }
    };

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        observer.next({
          progress: { loaded: xhr.response.size, total: xhr.response.size, percentage: 100 },
          response: xhr.response,
        });
        observer.complete();
      } else {
        observer.error({ status: xhr.status, statusText: xhr.statusText });
      }
    };

    xhr.onerror = () => {
      observer.error({ status: 0, statusText: 'Network error' });
    };

    xhr.send(formData);
  });
}

export function createFilePreview(file: File): { url: string; type: 'image' | 'pdf' | 'unknown' } {
  const url = URL.createObjectURL(file);
  const type = file.type.startsWith('image/')
    ? 'image'
    : file.type === 'application/pdf'
      ? 'pdf'
      : 'unknown';
  return { url, type };
}

export function revokeFilePreview(url: string): void {
  if (url && url.startsWith('blob:')) {
    try {
      URL.revokeObjectURL(url);
    } catch {
      // Ignore cleanup errors
    }
  }
}
```

---

## 6. Implementation Roadmap

### Phase 1: Base Class Migration (Week 1-2)

- [ ] Migrate `ai-model-list.component.ts`
- [ ] Migrate `holidays.component.ts`
- [ ] Migrate `document-types.component.ts`
- [ ] Migrate `backups.component.ts`
- [ ] Migrate `ai-model-form.component.ts`
- [ ] Update tests for migrated components

**Estimated Effort:** 16-28 hours
**Code Reduction:** 1,400-2,000 lines

### Phase 2: Service Refactoring (Week 3-4)

- [ ] Create `BaseHttpService`
- [ ] Migrate `CustomersService`
- [ ] Migrate `ProductsService`
- [ ] Migrate `InvoicesService`
- [ ] Migrate `ApplicationsService`
- [ ] Update all consumers

**Estimated Effort:** 20-30 hours
**Code Reduction:** 500-800 lines

### Phase 3: Utility Extraction (Week 5-6)

- [ ] Create `currency.ts` utilities
- [ ] Create `date-parsing.ts` utilities
- [ ] Create `type-guards.ts` utilities
- [ ] Replace duplicated code across components
- [ ] Add comprehensive tests

**Estimated Effort:** 12-18 hours
**Code Reduction:** 200-300 lines

### Phase 4: Advanced Patterns (Week 7-8)

- [ ] Create `SseConnectionService`
- [ ] Enhance file upload/download utilities
- [ ] Create validation utilities
- [ ] Standardize error handling

**Estimated Effort:** 14-20 hours
**Code Reduction:** 450-650 lines

---

## 7. Testing Strategy

For each extraction:

1. **Unit Tests:** Test base classes/utilities in isolation
2. **Integration Tests:** Test components using new base classes
3. **Regression Tests:** Ensure existing functionality unchanged
4. **Performance Tests:** Verify no performance degradation

---

## 8. Success Metrics

- **Code Reduction:** 3,110-4,690 lines removed
- **Test Coverage:** Maintain or improve current coverage
- **Build Time:** No significant increase
- **Bundle Size:** No significant increase
- **Developer Velocity:** Faster component creation
- **Bug Rate:** Reduced due to centralized logic

---

## 9. Risks and Mitigation

| Risk                   | Impact | Mitigation                                |
| ---------------------- | ------ | ----------------------------------------- |
| Breaking changes       | High   | Incremental migration, feature flags      |
| Performance regression | Medium | Performance testing before/after          |
| Test coverage gaps     | Medium | Comprehensive test suite for base classes |
| Learning curve         | Low    | Documentation and examples                |

---

## 10. Conclusion

This extraction initiative will significantly improve code maintainability, reduce duplication, and accelerate future development. The phased approach allows for incremental adoption with minimal disruption.

**Next Steps:**

## 9. Risks and Mitigation

| Risk                   | Impact | Mitigation                                |
| ---------------------- | ------ | ----------------------------------------- |
| Breaking changes       | High   | Incremental migration, feature flags      |
| Performance regression | Medium | Performance testing before/after          |
| Test coverage gaps     | Medium | Comprehensive test suite for base classes |
| Learning curve         | Low    | Documentation and examples                |

---

## 10. Conclusion

This extraction initiative will significantly improve code maintainability, reduce duplication, and accelerate future development. The phased approach allows for incremental adoption with minimal disruption.

**Next Steps:**

1. Review and prioritize recommendations
2. Create detailed implementation tickets
3. Begin Phase 1 migrations
4. Establish code review guidelines for new components
