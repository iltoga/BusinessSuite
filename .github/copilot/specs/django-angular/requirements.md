# Technical Requirements Specification: RevisBaliCRM Decoupling

| Metadata         | Details                         |
| :--------------- | :------------------------------ |
| **Project**      | RevisBaliCRM Frontend Migration |
| **Version**      | 2.1.0                           |
| **Status**       | Draft                           |
| **Date**         | January 24, 2026                |
| **Dependencies** | Design Document v2.1.0          |

## 1. Introduction

This document defines the functional and non-functional requirements for migrating the RevisBaliCRM application from a monolithic Django Template architecture to a decoupled system comprising a Django REST Framework (DRF) backend and an Angular 19+ Single Page Application (SPA).

The requirements are derived from the need to modernize the UI while strictly preserving business logic, ensuring type safety via OpenAPI contracts, and maintaining high performance through modern build tools like Bun.

## 2. Functional Requirements

### 2.1 API Contract & Data Interchange

**User Story:** As a frontend developer, I need a predictable, typed, and standard API surface to build features without guessing backend behavior.

- **FR-01 (OpenAPI Generation):** The backend **MUST** expose an OpenAPI 3.0 schema generated via `drf-spectacular`.
  - _Acceptance:_ Accessing `/api/schema/` returns a valid YAML/JSON schema covering all endpoints.
  - _Test Case:_

    ```python
    # tests/test_api_schema.py
    def test_openapi_schema_available():
        """
        GIVEN: The backend API is running
        WHEN: A GET request is made to /api/schema/
        THEN: Returns 200 with valid OpenAPI 3.0 schema
        AND: Schema contains all required endpoints
        """
        response = client.get('/api/schema/')
        assert response.status_code == 200
        schema = yaml.safe_load(response.content)
        assert schema['openapi'] == '3.0.0'
        assert 'paths' in schema
        assert '/api/customers/' in schema['paths']
    ```

- **FR-02 (Case Transformation):** The backend **MUST** automatically transform JSON keys from `snake_case` (Python) to `camelCase` (JS) using `djangorestframework-camel-case`.
  - _Acceptance:_ A GET request to `/api/customers/` returns `{ "firstName": "John" }`, not `{ "first_name": "John" }`.
  - _Example Implementation:_

    ```python
    # settings.py
    REST_FRAMEWORK = {
        'DEFAULT_RENDERER_CLASSES': (
            'djangorestframework_camel_case.render.CamelCaseJSONRenderer',
        ),
        'DEFAULT_PARSER_CLASSES': (
            'djangorestframework_camel_case.parser.CamelCaseJSONParser',
        ),
    }
    ```

  - _Example Request/Response:_

    ```typescript
    // Angular Service Call
    const customer = await customerService.create({
      firstName: 'John',
      lastName: 'Doe',
      phoneNumber: '+62123456789'
    });

    // Actual HTTP Request (network tab)
    POST /api/customers/
    {
      "first_name": "John",
      "last_name": "Doe",
      "phone_number": "+62123456789"
    }

    // Response
    {
      "id": 123,
      "firstName": "John",
      "lastName": "Doe",
      "phoneNumber": "+62123456789",
      "createdAt": "2026-01-24T10:00:00Z"
    }
    ```

- **FR-03 (Type Generation):** The frontend **MUST** auto-generate TypeScript interfaces and services from the OpenAPI schema using `@openapitools/openapi-generator-cli`.
  - _Acceptance:_ No manual TypeScript interfaces mirroring Django models exist in the codebase.
  - _Implementation:_

    ```json
    // package.json
    {
      "scripts": {
        "generate:api": "bunx @openapitools/openapi-generator-cli generate -i http://localhost:8000/api/schema/ -g typescript-angular -o src/app/core/api --additional-properties=fileNaming=kebab-case"
      }
    }
    ```

  - _Generated Files Example:_

    ```typescript
    // src/app/core/api/models/customer.ts
    export interface Customer {
      id: number;
      firstName: string;
      lastName: string;
      email: string;
      phoneNumber?: string;
      createdAt: string;
    }

    // src/app/core/api/services/customer-api.service.ts
    @Injectable({ providedIn: "root" })
    export class CustomerApiService {
      getCustomers(
        params?: CustomerListParams,
      ): Observable<CustomerListResponse> {}
      createCustomer(data: CreateCustomerDto): Observable<Customer> {}
      updateCustomer(
        id: number,
        data: UpdateCustomerDto,
      ): Observable<Customer> {}
      deleteCustomer(id: number): Observable<void> {}
    }
    ```

- **FR-04 (Standardized Errors):** The backend **MUST** return errors in a standardized format.
  - _Acceptance:_ The frontend has a global utility that maps these API errors directly to Angular Reactive Forms controls.
  - _Backend Implementation:_

    ```python
    # api/utils/exception_handler.py
    from rest_framework.views import exception_handler
    from rest_framework.response import Response

    def custom_exception_handler(exc, context):
        """
        Returns errors in format:
        {
            "code": "validation_error",
            "errors": {
                "email": ["This field must be unique."],
                "phoneNumber": ["Invalid phone number format."]
            }
        }
        """
        response = exception_handler(exc, context)

        if response is not None:
            custom_response = {
                'code': getattr(exc, 'default_code', 'error'),
                'errors': response.data
            }
            response.data = custom_response

        return response
    ```

  - _Frontend Implementation:_

    ```typescript
    // shared/utils/form-errors.ts
    import { FormGroup } from '@angular/forms';
    import { HttpErrorResponse } from '@angular/common/http';

    export function mapApiErrorsToForm(
      error: HttpErrorResponse,
      form: FormGroup
    ): void {
      if (error.status === 400 && error.error?.errors) {
        Object.entries(error.error.errors).forEach(([field, messages]) => {
          const control = form.get(field);
          if (control && Array.isArray(messages)) {
            control.setErrors({ server: messages[0] });
            control.markAsTouched();
          }
        });
      }
    }

    // Usage in components
    async onSubmit() {
      try {
        await this.customerService.create(this.form.value);
      } catch (error) {
        mapApiErrorsToForm(error as HttpErrorResponse, this.form);
      }
    }
    ```

### 2.2 Authentication & Security

**User Story:** As a user, I need to move seamlessly between the legacy system and the new app without repeated logins, while ensuring my data is secure.

- **FR-05 (Hybrid Auth):** The system **MUST** support a "Hybrid Authentication" mechanism during the migration phase.
  - _Acceptance:_ The API accepts both `SessionAuthentication` (for users coming from legacy views) and `JWTAuthentication` (via `djangorestframework-simplejwt` for direct SPA access).
  - _Implementation:_

    ```python
    # settings.py
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': [
            'rest_framework.authentication.SessionAuthentication',  # Legacy
            'rest_framework_simplejwt.authentication.JWTAuthentication',  # SPA
        ],
    }
    ```

- **FR-06 (Token Management):** The frontend **MUST** handle JWT Access/Refresh flows automatically via an `HttpInterceptor`.
  - _Acceptance:_ When an access token expires (401), the interceptor pauses requests, calls `/api/token/refresh/`, updates storage, and retries the original requests transparently.
  - _Implementation:_

    ```typescript
    // core/interceptors/jwt.interceptor.ts
    import { HttpInterceptorFn, HttpErrorResponse } from "@angular/common/http";
    import { inject } from "@angular/core";
    import { AuthService } from "../services/auth.service";
    import { catchError, switchMap, throwError } from "rxjs";

    export const jwtInterceptor: HttpInterceptorFn = (req, next) => {
      const authService = inject(AuthService);
      const token = authService.getAccessToken();

      if (token) {
        req = req.clone({
          setHeaders: { Authorization: `Bearer ${token}` },
        });
      }

      return next(req).pipe(
        catchError((error: HttpErrorResponse) => {
          if (error.status === 401 && !req.url.includes("/token/")) {
            return authService.refreshToken().pipe(
              switchMap(() => {
                const newToken = authService.getAccessToken();
                req = req.clone({
                  setHeaders: { Authorization: `Bearer ${newToken}` },
                });
                return next(req);
              }),
              catchError((err) => {
                authService.logout();
                return throwError(() => err);
              }),
            );
          }
          return throwError(() => error);
        }),
      );
    };
    ```

- **FR-07 (CORS Policy):** The backend **MUST** enforce strict CORS settings.
  - _Acceptance:_ `CORS_ALLOWED_ORIGINS` is populated via environment variables; `CORS_ALLOW_ALL_ORIGINS` is `False` in production.
  - _Implementation:_

    ```python
    # settings.py
    CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
        'http://localhost:4200',
        'https://app.revisbalicrm.com',
    ])
    CORS_ALLOW_ALL_ORIGINS = False
    CORS_ALLOW_CREDENTIALS = True
    ```

### 2.3 Core Business Modules

**User Story:** As a CRM operator, I need to perform my daily tasks (Customer management, Invoicing, OCR) with the same or better efficiency than the old system.

- **FR-08 (Feature Parity):** The Angular application **MUST** implement the following modules with 100% functional parity:
  - Customers (CRUD, Search, Detail View)
  - Products (CRUD, Pricing)
  - Applications (Workflows, Document Uploads)
  - Invoices & Payments (Generation, Partial Payments)
  - _Test Case:_

    ```typescript
    // tests/features/customers.spec.ts
    describe("Customer Management", () => {
      it("should create a customer with all required fields", async () => {
        const customer = await customerService.create({
          firstName: "John",
          lastName: "Doe",
          email: "john@example.com",
          phoneNumber: "+62123456789",
        });

        expect(customer.id).toBeDefined();
        expect(customer.firstName).toBe("John");
      });

      it("should search customers by name", async () => {
        const results = await customerService.search("John");
        expect(results.length).toBeGreaterThan(0);
      });
    });
    ```

- **FR-09 (OCR Workflow):** The document upload process **MUST** be asynchronous and poll-based.
  - _Acceptance:_ Uploading a passport triggers a background job. The UI displays a progress bar (polling `/api/ocr/status/{id}`) and updates the form with extracted data upon completion.
  - _Backend Implementation:_

    ```python
    # api/views/ocr.py
    from rest_framework.views import APIView
    from rest_framework.response import Response

    class OcrStatusView(APIView):
        """
        GET /api/ocr/status/{job_id}/

        Returns:
        {
            "status": "processing" | "complete" | "failed",
            "progress": 75,
            "data": { "firstName": "John", ... },
            "error": null
        }
        """
        def get(self, request, job_id):
            job = OcrJob.objects.get(id=job_id)
            return Response({
                'status': job.status,
                'progress': job.progress,
                'data': job.extracted_data if job.status == 'complete' else None,
                'error': job.error_message
            })
    ```

  - _Frontend Implementation:_ (See Design Doc 6.3.1)

- **FR-10 (Optimistic Updates):** High-frequency actions (e.g., marking a task as complete) **MUST** use Optimistic UI patterns.
  - _Acceptance:_ The UI updates immediately upon click; if the API call fails, the UI reverts and shows an error toast.
  - _Implementation:_

    ```typescript
    // Example: Toggle task completion
    async toggleTaskComplete(taskId: number) {
      const task = this.tasks().find(t => t.id === taskId);
      if (!task) return;

      // Optimistic update
      const previousStatus = task.isComplete;
      this.tasks.update(tasks =>
        tasks.map(t => t.id === taskId
          ? { ...t, isComplete: !t.isComplete }
          : t
        )
      );

      try {
        await this.taskApi.toggleComplete(taskId);
      } catch (error) {
        // Revert on failure
        this.tasks.update(tasks =>
          tasks.map(t => t.id === taskId
            ? { ...t, isComplete: previousStatus }
            : t
          )
        );
        this.toast.error('Failed to update task');
      }
    }
    ```

## 3. Non-Functional Requirements

### 3.1 Architecture & Code Quality

**User Story:** As a lead developer, I want the codebase to follow modern standards to ensure maintainability and scalability.

- **NFR-01 (Service Layer):** Business logic **MUST** be decoupled from Django Views and Serializers.
  - _Acceptance:_ Complex logic (e.g., invoice calculation) resides in `services.py` or a dedicated domain package, not in `views.py`.
  - _Example:_

    ```python
    # core/services/invoice_service.py
    class InvoiceService:
        """
        Business logic for invoice calculations.
        Keeps ViewSets and Serializers thin.
        """
        @staticmethod
        def calculate_totals(line_items: list) -> dict:
            subtotal = sum(item['quantity'] * item['price'] for item in line_items)
            tax = subtotal * Decimal('0.1')
            total = subtotal + tax
            return {
                'subtotal': subtotal,
                'tax': tax,
                'total': total
            }

    # api/viewsets/invoice_viewset.py
    class InvoiceViewSet(viewsets.ModelViewSet):
        @action(detail=True, methods=['post'])
        def calculate(self, request, pk=None):
            invoice = self.get_object()
            totals = InvoiceService.calculate_totals(invoice.line_items)
            return Response(totals)
    ```

- **NFR-02 (Angular Architecture):** The frontend **MUST** use Standalone Components and Signals.
  - _Acceptance:_ No `NgModule` definitions exist for feature modules. Local component state is managed via `signal()`, not `BehaviorSubject`.
  - _Validation:_ Add ESLint rule to prevent `@NgModule` usage:

    ```json
    // .eslintrc.json
    {
      "rules": {
        "@angular-eslint/no-ngmodule": "error"
      }
    }
    ```

- **NFR-03 (Component Library):** The UI **MUST** be built using ZardUI (Tailwind CSS v4).
  - _Acceptance:_ Standard elements (Buttons, Inputs, Dialogs) are imported from `@/shared/components/ui`, not built from scratch.
  - _Example:_

    ```typescript
    // ✅ GOOD
    import { ButtonComponent } from '@/shared/components/ui/button';

    // ❌ BAD - Building custom button from scratch
    @Component({
      template: '<button class="bg-blue-500 ...">Click</button>'
    })
    ```

### 3.2 Performance & Tooling

**User Story:** As a developer, I want fast build times and a responsive application.

- **NFR-04 (Build Tooling):** The project **MUST** use Bun as the package manager.
  - _Acceptance:_ A `bun.lockb` file exists in the root. CI pipelines use `bun install --frozen-lockfile`.
  - _Configuration:_

    ```toml
    # bunfig.toml
    [install]
    exact = true
    frozen-lockfile = true
    ```

- **NFR-05 (Query Optimization):** API endpoints **MUST** be optimized to prevent N+1 query issues.
  - _Acceptance:_ ViewSets use `select_related` and `prefetch_related`. API response times for list views are under 200ms for <100 items.
  - _Example:_

    ```python
    # api/viewsets/customer_viewset.py
    class CustomerViewSet(viewsets.ModelViewSet):
        def get_queryset(self):
            # ✅ GOOD - Prevents N+1
            return Customer.objects.select_related(
                'agent', 'country'
            ).prefetch_related(
                'applications'
            )

        # ❌ BAD - Causes N+1 queries
        # queryset = Customer.objects.all()
    ```

  - _Test Case:_

    ```python
    # tests/test_performance.py
    from django.test import TestCase
    from django.test.utils import override_settings
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    class CustomerApiPerformanceTest(TestCase):
        def test_customer_list_query_count(self):
            """Customer list should execute <= 3 queries regardless of item count"""
            with CaptureQueriesContext(connection) as context:
                response = self.client.get('/api/customers/')
                self.assertEqual(response.status_code, 200)
                self.assertLessEqual(len(context.captured_queries), 3)
    ```

- **NFR-06 (Change Detection):** All Angular components **MUST** use `ChangeDetectionStrategy.OnPush`.
  - _Acceptance:_ Verified via linting rule or code review checklist.
  - _Example:_

    ```typescript
    @Component({
      selector: "app-customer-list",
      standalone: true,
      changeDetection: ChangeDetectionStrategy.OnPush, // ✅ REQUIRED
      template: "...",
    })
    export class CustomerListComponent {}
    ```

### 3.3 Migration & Compatibility

**User Story:** As a product owner, I want to release features incrementally without downtime.

- **NFR-07 (Strangler Fig Pattern):** The system **MUST** allow serving specific routes via Angular while others remain on Django Templates.
  - _Acceptance:_ Nginx/Load Balancer configuration allows traffic splitting based on URL path.
  - _Nginx Configuration:_

    ```nginx
    # nginx.conf
    location /app/ {
        proxy_pass http://angular_app:4200;
    }

    location /api/ {
        proxy_pass http://django_backend:8000;
    }

    location / {
        # Legacy Django templates
        proxy_pass http://django_backend:8000;
    }
    ```

- **NFR-08 (Feature Toggles):** New features **MUST** be guarded by feature flags (e.g., `django-waffle`).
  - _Acceptance:_ A flag `ENABLE_ANGULAR_DASHBOARD` determines whether the root URL redirects to the Angular app or the legacy template view.
  - _Implementation:_

    ```python
    # views.py
    from waffle import flag_is_active

    def index(request):
        if flag_is_active(request, 'ENABLE_ANGULAR_DASHBOARD'):
            return render(request, 'angular_app/index.html')
        else:
            return render(request, 'legacy/dashboard.html')
    ```

## 4. Integration Requirements

### 4.1 Development Environment

- **IR-01:** Developers **MUST** use a local proxy configuration (`proxy.conf.json`) to route `/api` calls to the Django backend.

  ```json
  // proxy.conf.json
  {
    "/api": {
      "target": "http://127.0.0.1:8000",
      "secure": false,
      "changeOrigin": true,
      "logLevel": "debug"
    }
  }
  ```

- **IR-02:** `bunfig.toml` **MUST** be configured with `exact = true` to prevent dependency drift.

  ```toml
  # bunfig.toml
  [install]
  exact = true
  ```

### 4.2 Documentation

- **IR-03:** A `docs/shared_components.md` registry **MUST** be maintained for all reusable UI components.
- **IR-04:** A `docs/implementation_feedback.md` log **MUST** be updated after every sprint/feature completion.

## 5. Error Handling Standards

All components must follow these error handling patterns:

```typescript
// shared/utils/error-handler.ts
import { HttpErrorResponse } from "@angular/common/http";
import { inject } from "@angular/core";
import { Router } from "@angular/router";
import { GlobalToastService } from "../services/toast.service";

export function handleApiError(
  error: HttpErrorResponse,
  form?: FormGroup,
): void {
  const router = inject(Router);
  const toast = inject(GlobalToastService);

  if (error.status === 400 && error.error?.errors) {
    // Map validation errors to form controls (FR-04)
    if (form) {
      Object.entries(error.error.errors).forEach(([field, messages]) => {
        const control = form.get(field);
        if (control && Array.isArray(messages)) {
          control.setErrors({ server: messages[0] });
        }
      });
    }
  } else if (error.status === 401) {
    // Redirect to login
    router.navigate(["/login"]);
  } else if (error.status === 403) {
    toast.error("You do not have permission to perform this action");
  } else if (error.status === 404) {
    toast.error("Resource not found");
  } else {
    // Generic error toast
    toast.error("An unexpected error occurred");
  }
}

// Usage in components
try {
  await this.customerService.create(formData);
  this.toast.success("Customer created successfully");
} catch (error) {
  handleApiError(error as HttpErrorResponse, this.customerForm);
}
```
