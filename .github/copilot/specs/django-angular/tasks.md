# Implementation Plan: RevisBaliCRM Decoupling

| Metadata            | Details                             |
| :------------------ | :---------------------------------- |
| **Project**         | RevisBaliCRM Frontend Migration     |
| **Version**         | 2.1.0                               |
| **Status**          | Ready for Execution                 |
| **Methodology**     | Strangler Fig Pattern (Incremental) |
| **Package Manager** | Bun                                 |

## Pre-Task Checklist Template

**Copy this checklist before implementing any feature module:**

### Before Starting Implementation

- [ ] Check `docs/shared_components.md` for reusable components
- [ ] Audit existing Django views/templates/unicorn components and any jQuery/JS for the feature being migrated; capture UI logic and edge cases
- [ ] Identify and design shared/reusable Angular components to replicate legacy UI behaviors (search, filters, pagination, status badges)
- [ ] Review generated TypeScript interfaces from OpenAPI
- [ ] Verify backend endpoint exists and matches OpenAPI schema
- [ ] Preserve existing routes and views; if a new API is required for Angular, add a new endpoint and tag the old one with: "TO BE REMOVED WHEN ANGULAR FRONTEND IS COMPLETE"
- [ ] Run `bun run generate:api` if schema changed
- [ ] Create feature flag in Django Waffle if needed
- [ ] Review anti-patterns in Design Doc section 7

### After Completing Implementation

- [ ] Update `docs/shared_components.md` with new reusable components
- [ ] Update `docs/implementation_feedback.md` with refactor suggestions
- [ ] Add component tests (minimum 80% coverage)
- [ ] Verify `ChangeDetectionStrategy.OnPush` is used
- [ ] Check for N+1 queries in backend (Django Debug Toolbar)
- [ ] Verify error handling follows standard patterns
- [ ] Test optimistic updates (if applicable)

---

## Phase 0: Foundation, Tooling, and Documentation Setup

**Goal:** Establish the feedback loops, backend API contracts, and frontend build environment before writing feature code.

- [x] **0.1 Initialize Feedback & Documentation System**
  - [x] 0.1.1 Create `docs/shared_components.md`.
    - Structure:

      ````markdown
      # Shared Components Registry

      ## Rules of Engagement

      - **ALWAYS** check this list before building a new UI component
      - If a component exists here, reuse it; do not rebuild
      - Document new shared components immediately after creation

      ## Component Index

      | Component Name | Selector       | Location                     | ZardUI Deps | Status   |
      | -------------- | -------------- | ---------------------------- | ----------- | -------- |
      | DataTable      | app-data-table | shared/components/data-table | Table       | ✅ Ready |

      ## Component Details

      ### DataTableComponent

      **Location:** `src/app/shared/components/data-table/data-table.component.ts`

      **Interface:**

      ```typescript
      @Component({
        selector: "app-data-table",
        standalone: true,
        imports: [TableModule, CommonModule],
      })
      export class DataTableComponent<T> {
        @Input() data = input.required<Signal<T[]>>();
        @Input() columns = input.required<ColumnConfig[]>();
        // ... see full spec in Design Doc
      }
      ```
      ````

      **Usage Example:**

      ````typescript
      // In customer-list.component.ts
      columns = [
        { key: 'name', header: 'Customer Name', sortable: true },
        { key: 'email', header: 'Email' }
      ];

      <app-data-table
        [data]="customers"
        [columns]="columns"
        (pageChange)="onPageChange($event)"
      />


      ```markdown
      # Implementation Feedback Log

      ## Progress Log

      - **2026-01-24:** Completed Phase 0 - Foundation setup

      ## Reuse Hints

      - Created `StatusBadge` in Customer module → Move to Shared for Invoice module

      ## Refactor Requests

      - `CustomerForm` is too large (500+ lines) → Break address section into sub-component

      ## Technical Debt

      - Need to add unit tests for `DataTableComponent`

      ## Wins & Lessons Learned

      - OpenAPI generation works perfectly, saving ~4 hours per module
      ````

    - _Action:_ Commit these files to the repository root immediately.

- [x] **0.2 Backend API Configuration (The Contract)**
  - [x] 0.2.1 Install and Configure `drf-spectacular`.
    - Install: `pip install drf-spectacular`.
    - Update `settings.py`:

      ```python
      INSTALLED_APPS = [
          # ...
          'drf_spectacular',
      ]

      REST_FRAMEWORK = {
          'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
      }

      SPECTACULAR_SETTINGS = {
          'TITLE': 'RevisBaliCRM API',
          'DESCRIPTION': 'API for RevisBaliCRM application',
          'VERSION': '1.0.0',
          'SERVE_INCLUDE_SCHEMA': False,
      }
      ```

    - Add URL:

      ```python
      # urls.py
      from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

      urlpatterns = [
          path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
          path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
      ]
      ```

    - _Test:_ Visit `http://localhost:8000/api/schema/` and verify YAML output.

  - [x] 0.2.2 Install and Configure `djangorestframework-camel-case`.
    - Install: `pip install djangorestframework-camel-case`.
    - Update `settings.py`:

      ```python
      REST_FRAMEWORK = {
          'DEFAULT_RENDERER_CLASSES': (
              'djangorestframework_camel_case.render.CamelCaseJSONRenderer',
          ),
          'DEFAULT_PARSER_CLASSES': (
              'djangorestframework_camel_case.parser.CamelCaseJSONParser',
          ),
      }
      ```

    - _Validation Test:_

      ```python
      # api/views/test_view.py
      from rest_framework.views import APIView
      from rest_framework.response import Response

      class TestCamelCaseView(APIView):
          def get(self, request):
              return Response({
                  'first_name': 'John',
                  'last_name': 'Doe'
              })
      ```

      - Expected browser response: `{"firstName":"John","lastName":"Doe"}`

  - [x] 0.2.3 Implement Standardized Error Handling.
    - Create `api/utils/exception_handler.py`:

      ```python
      from rest_framework.views import exception_handler
      from rest_framework.response import Response

      def custom_exception_handler(exc, context):
          response = exception_handler(exc, context)

          if response is not None:
              custom_response = {
                  'code': getattr(exc, 'default_code', 'error'),
                  'errors': response.data
              }
              response.data = custom_response

          return response
      ```

    - Register in `settings.py`:

      ```python
      REST_FRAMEWORK = {
          'EXCEPTION_HANDLER': 'api.utils.exception_handler.custom_exception_handler',
      }
      ```

    - _Test:_

      ```python
      # Test invalid email in CustomerSerializer
      response = client.post('/api/customers/', {'email': 'invalid'})
      # Expected: {"code": "validation_error", "errors": {"email": ["Enter a valid email."]}}
      ```

  - [x] 0.2.4 Configure CORS and Hybrid Auth.
    - Install: `pip install django-cors-headers djangorestframework-simplejwt`.
    - Update `settings.py`:

      ```python
      INSTALLED_APPS = [
          'corsheaders',
          # ...
      ]

      MIDDLEWARE = [
          'corsheaders.middleware.CorsMiddleware',
          # ... (before CommonMiddleware)
      ]

      CORS_ALLOWED_ORIGINS = [
          'http://localhost:4200',
          'https://app.revisbalicrm.com',
      ]
      CORS_ALLOW_ALL_ORIGINS = False
      CORS_ALLOW_CREDENTIALS = True

      REST_FRAMEWORK = {
          'DEFAULT_AUTHENTICATION_CLASSES': [
              'rest_framework.authentication.SessionAuthentication',
              'rest_framework_simplejwt.authentication.JWTAuthentication',
          ],
      }
      ```

- [x] **0.3 Frontend Scaffold (Bun + Angular + ZardUI)**
  - [x] 0.3.1 Initialize Angular Project with Bun.
    - Run: `ng new frontend --style=css --routing --ssr=false --package-manager=bun`
    - Create `bunfig.toml`:

      ```toml
      [install]
      exact = true
      ```

    - Update `angular.json`:

      ```json
      {
        "cli": {
          "packageManager": "bun"
        }
      }
      ```

    - _Verify:_ Run `cd frontend && bun install` successfully.

  - [x] 0.3.2 Initialize ZardUI (Tailwind v4).
    - Run: `cd frontend && bunx @ngzard/ui init`
    - Select:
      - Theme: Neutral
      - Use CSS variables: Yes
      - Default paths: Yes
    - Verify files created:
      - `tailwind.config.js` (or v4 CSS)
      - `components.json`
      - `src/styles.css` (with Tailwind directives)

  - [x] 0.3.3 Configure Proxy for Development.
    - Create `frontend/proxy.conf.json`:

      ```json
      {
        "/api": {
          "target": "http://127.0.0.1:8000",
          "secure": false,
          "changeOrigin": true,
          "logLevel": "debug"
        }
      }
      ```

    - Update `angular.json` serve options:

      ```json
      {
        "serve": {
          "options": {
            "proxyConfig": "proxy.conf.json"
          }
        }
      }
      ```

    - _Test:_ Start backend and frontend, call `/api/schema/` from Angular app.

## Phase 1: Core Architecture & Shared Services

**Goal:** Build the "shell" of the Angular application, including Auth, API clients, and the base UI library.

- [x] **1.1 API Client Generation**
  - [x] 1.1.1 Setup OpenAPI Generator.
    - Add to `frontend/package.json`:

      ```json
      {
        "scripts": {
          "generate:api": "bunx @openapitools/openapi-generator-cli generate -i http://localhost:8000/api/schema/ -g typescript-angular -o src/app/core/api --additional-properties=fileNaming=kebab-case,ngVersion=19"
        }
      }
      ```

  - [x] 1.1.2 Generate Clients.
    - Ensure backend is running: `python manage.py runserver`
    - Run: `cd frontend && bun run generate:api`
    - _Validation:_ Check `src/app/core/api` for:
      - `models/` directory with TypeScript interfaces
      - `services/` directory with API service classes
      - `api.module.ts` (can be ignored for standalone)
    - _Example Generated File:_

      ```typescript
      // src/app/core/api/models/customer.ts
      export interface Customer {
        id: number;
        firstName: string;
        lastName: string;
        email: string;
        phoneNumber?: string;
      }
      ```

- [x] **1.2 Authentication Module**
  - [x] 1.2.1 Implement `AuthService`.
    - Create `src/app/core/services/auth.service.ts`:

      ```typescript
      import { Injectable, signal } from "@angular/core";
      import { Router } from "@angular/router";
      import { HttpClient } from "@angular/common/http";

      export interface User {
        id: number;
        email: string;
        firstName: string;
        lastName: string;
      }

      export interface LoginRequest {
        username: string;
        password: string;
      }

      export interface AuthResponse {
        token: string;
        user: User;
      }

      @Injectable({ providedIn: "root" })
      export class AuthService {
        private userSignal = signal<User | null>(null);
        readonly user = this.userSignal.asReadonly();

        constructor(
          private http: HttpClient,
          private router: Router,
        ) {
          this.loadUserFromStorage();
        }

        async login(credentials: LoginRequest): Promise<void> {
          const response = await this.http
            .post<AuthResponse>("/api/token/", credentials)
            .toPromise();

          if (response) {
            localStorage.setItem("access_token", response.token);
            localStorage.setItem("user", JSON.stringify(response.user));
            this.userSignal.set(response.user);
          }
        }

        logout(): void {
          localStorage.removeItem("access_token");
          localStorage.removeItem("user");
          this.userSignal.set(null);
          this.router.navigate(["/login"]);
        }

        isAuthenticated(): boolean {
          return !!localStorage.getItem("access_token");
        }

        private loadUserFromStorage(): void {
          const userJson = localStorage.getItem("user");
          if (userJson) {
            this.userSignal.set(JSON.parse(userJson));
          }
        }
      }
      ```

  - [x] 1.2.2 Implement `AuthInterceptor` (Functional).
    - Create `src/app/core/interceptors/auth.interceptor.ts`:

      ```typescript
      import { HttpInterceptorFn } from "@angular/common/http";

      export const authInterceptor: HttpInterceptorFn = (req, next) => {
        const token = localStorage.getItem("access_token");

        if (token && !req.url.includes("/api/token/")) {
          req = req.clone({
            setHeaders: {
              Authorization: `Token ${token}`,
            },
          });
        }

        return next(req);
      };
      ```

    - Register in `src/app/app.config.ts`:

      ```typescript
      import {
        provideHttpClient,
        withInterceptors,
      } from "@angular/common/http";
      import { authInterceptor } from "./core/interceptors/auth.interceptor";

      export const appConfig: ApplicationConfig = {
        providers: [
          provideHttpClient(withInterceptors([authInterceptor])),
          // ...
        ],
      };
      ```

  - [x] 1.2.3 Implement `AuthGuard`.
    - Create `src/app/core/guards/auth.guard.ts`:

      ```typescript
      import { inject } from "@angular/core";
      import { Router, CanActivateFn } from "@angular/router";
      import { AuthService } from "../services/auth.service";

      export const authGuard: CanActivateFn = () => {
        const authService = inject(AuthService);
        const router = inject(Router);

        if (authService.isAuthenticated()) {
          return true;
        }

        return router.createUrlTree(["/login"]);
      };
      ```

    - _Usage in routes:_

      ```typescript
      // app.routes.ts
      export const routes: Routes = [
        {
          path: "dashboard",
          canActivate: [authGuard],
          loadComponent: () =>
            import("./features/dashboard/dashboard.component"),
        },
      ];
      ```

- [x] **1.3 Shared UI Components (ZardUI)**
  - [x] 1.3.1 Install Base Components.
    - Run: `bunx @ngzard/ui add button input label card table dialog toast badge avatar dropdown separator skeleton`
    - _Verify:_ Check `src/app/shared/components/ui/` for generated components.

  - [x] 1.3.2 Create `DataTableComponent` (Smart Wrapper).
    - Path: `src/app/shared/components/data-table/`
    - Create files:
      - `data-table.component.ts`
      - `data-table.component.html`
      - `data-table.component.css`
    - Implementation:

      ```typescript
      // data-table.component.ts
      import {
        Component,
        input,
        output,
        ChangeDetectionStrategy,
      } from "@angular/core";
      import { CommonModule } from "@angular/common";
      import { TableModule } from "../ui/table";

      export interface ColumnConfig {
        key: string;
        header: string;
        sortable?: boolean;
        template?: TemplateRef<any>;
      }

      export interface PageEvent {
        page: number;
        pageSize: number;
      }

      export interface SortEvent {
        column: string;
        direction: "asc" | "desc";
      }

      @Component({
        selector: "app-data-table",
        standalone: true,
        imports: [CommonModule, TableModule],
        templateUrl: "./data-table.component.html",
        changeDetection: ChangeDetectionStrategy.OnPush,
      })
      export class DataTableComponent<T> {
        data = input.required<T[]>();
        columns = input.required<ColumnConfig[]>();
        totalItems = input<number>(0);
        isLoading = input<boolean>(false);

        pageChange = output<PageEvent>();
        sortChange = output<SortEvent>();
      }
      ```

    - _Documentation:_ Add entry to `docs/shared_components.md`.

  - [x] 1.3.3 Create `ConfirmDialogComponent`.
    - Path: `src/app/shared/components/confirm-dialog/`
    - Implementation:

      ```typescript
      @Component({
        selector: "app-confirm-dialog",
        standalone: true,
        imports: [DialogModule, ButtonComponent],
        template: `
          <app-dialog [open]="isOpen()" (openChange)="onOpenChange($event)">
            <app-dialog-content>
              <app-dialog-header>
                <app-dialog-title>{{ title() }}</app-dialog-title>
              </app-dialog-header>
              <app-dialog-description>
                {{ message() }}
              </app-dialog-description>
              <app-dialog-footer>
                <app-button variant="outline" (click)="cancel()"
                  >Cancel</app-button
                >
                <app-button (click)="confirm()">Confirm</app-button>
              </app-dialog-footer>
            </app-dialog-content>
          </app-dialog>
        `,
      })
      export class ConfirmDialogComponent {
        isOpen = input<boolean>(false);
        title = input<string>("Confirm Action");
        message = input<string>("Are you sure?");

        confirmed = output<void>();
        cancelled = output<void>();
      }
      ```

    - _Documentation:_ Add entry to `docs/shared_components.md`.

  - [x] 1.3.4 Create `GlobalToastService`.
    - Install: `bun add ngx-sonner`
    - Create `src/app/core/services/toast.service.ts`:

      ```typescript
      import { Injectable } from "@angular/core";
      import { toast } from "ngx-sonner";

      @Injectable({ providedIn: "root" })
      export class GlobalToastService {
        success(message: string): void {
          toast.success(message);
        }

        error(message: string): void {
          toast.error(message);
        }

        loading(message: string): void {
          toast.loading(message);
        }

        info(message: string): void {
          toast.info(message);
        }
      }
      ```

- [x] **1.4 Application Layouts**
  - [x] 1.4.1 Create `MainLayoutComponent`.
    - Path: `src/app/shared/layouts/main-layout/`
    - Features:
      - Sidebar with navigation links
      - Topbar with user menu
      - Content area with `<router-outlet>`
      - Responsive (collapsible sidebar on mobile)
    - Structure:

      ```typescript
      @Component({
        selector: "app-main-layout",
        standalone: true,
        imports: [CommonModule, RouterOutlet, AvatarComponent, DropdownModule],
        template: `
          <div class="flex h-screen">
            <aside class="w-64 bg-gray-900 text-white">
              <!-- Navigation -->
            </aside>
            <div class="flex-1 flex flex-col">
              <header class="h-16 bg-white shadow">
                <!-- User Menu -->
              </header>
              <main class="flex-1 overflow-auto p-6">
                <router-outlet />
              </main>
            </div>
          </div>
        `,
      })
      export class MainLayoutComponent {}
      ```

  - [x] 1.4.2 Create `AuthLayoutComponent`.
    - Path: `src/app/shared/layouts/auth-layout/`
    - Structure: Centered card for login forms
    - Template:

      ```typescript
      @Component({
        template: `
          <div class="min-h-screen flex items-center justify-center bg-gray-50">
            <app-card class="w-full max-w-md">
              <router-outlet />
            </app-card>
          </div>
        `,
      })
      export class AuthLayoutComponent {}
      ```

## Phase 2: Feature Implementation - Authentication & Dashboard

**Goal:** Allow users to log in and view a basic dashboard.

- [x] **2.1 Login Page**
  - [x] 2.1.1 Create `features/auth/login/login.component.ts`.
  - [x] 2.1.2 Implement Form.

    ```typescript
    import { Component } from "@angular/core";
    import {
      FormBuilder,
      ReactiveFormsModule,
      Validators,
    } from "@angular/forms";
    import { AuthService } from "@/core/services/auth.service";
    import { GlobalToastService } from "@/core/services/toast.service";
    import { Router } from "@angular/router";

    @Component({
      selector: "app-login",
      standalone: true,
      imports: [ReactiveFormsModule, InputComponent, ButtonComponent],
      templateUrl: "./login.component.html",
    })
    export class LoginComponent {
      loginForm = this.fb.group({
        username: ["", [Validators.required, Validators.email]],
        password: ["", Validators.required],
      });

      isLoading = signal(false);

      constructor(
        private fb: FormBuilder,
        private authService: AuthService,
        private toast: GlobalToastService,
        private router: Router,
      ) {}

      async onSubmit() {
        if (this.loginForm.invalid) return;

        this.isLoading.set(true);
        try {
          await this.authService.login(this.loginForm.value);
          this.toast.success("Login successful");
          this.router.navigate(["/dashboard"]);
        } catch (error) {
          this.toast.error("Invalid credentials");
        } finally {
          this.isLoading.set(false);
        }
      }
    }
    ```

  - [x] 2.1.3 UX Improvements.
    - Use ZardUI `Input` with error states
    - Add loading state to submit button
    - Show password toggle

- [x] **2.2 Dashboard (Placeholder)**
  - [x] 2.2.1 Create `features/dashboard/dashboard.component.ts`.
  - [x] 2.2.2 Add basic stats cards.

    ```typescript
    @Component({
      template: `
        <div class="grid grid-cols-3 gap-4">
          <app-card>
            <h3>Total Customers</h3>
            <p class="text-3xl">{{ stats().customers }}</p>
          </app-card>
          <app-card>
            <h3>Active Applications</h3>
            <p class="text-3xl">{{ stats().applications }}</p>
          </app-card>
          <app-card>
            <h3>Pending Invoices</h3>
            <p class="text-3xl">{{ stats().invoices }}</p>
          </app-card>
        </div>
      `,
    })
    export class DashboardComponent {
      stats = signal({ customers: 0, applications: 0, invoices: 0 });

      async ngOnInit() {
        const data = await this.api.getDashboardStats();
        this.stats.set(data);
      }
    }
    ```

  - [x] 2.2.3 Connect to `MainLayout` in `app.routes.ts`.

## Phase 3: Vertical Slice 1 - Customer Management

**Goal:** Full CRUD for Customers, proving the pattern.

- [x] **3.0 Legacy UI & Logic Audit (Mandatory)**
  - [x] 3.0.1 Review `customers/views/*.py`, Unicorn components, and Django templates used for the list/detail/create flows.
  - [x] 3.0.2 Review any related frontend JS (jQuery/vanilla) and document behaviors to replicate.
  - [x] 3.0.3 Identify shared components to extract (search toolbar, pagination, status badges, action groups) and add them to `docs/shared_components.md`.
  - [x] 3.0.4 Determine real-time needs and SSE endpoints used by legacy flows; define Angular replacement strategy (SSE + fallback polling).

- [x] **3.1 Backend Preparation**
  - [x] 3.1.1 Audit `CustomerViewSet`.

    ```python
    class CustomerViewSet(viewsets.ModelViewSet):
        queryset = Customer.objects.select_related('agent', 'country').all()
        serializer_class = CustomerSerializer
        filter_backends = [SearchFilter, OrderingFilter]
        search_fields = ['first_name', 'last_name', 'email']
    ```

  - [x] 3.1.2 Refactor Logic (if needed).
    - Move complex creation logic to `core/services/customer_service.py`.

- [x] **3.2 Customer List View**
  - [x] 3.2.1 Create `features/customers/customer-list/`.
  - [x] 3.2.2 Implement State with Signals.
  - [x] 3.2.3 Use `DataTableComponent` from shared.
  - [x] 3.2.4 Implement debounced search.

- [x] **3.3 Customer Create/Edit Form**
  - [x] 3.3.1 Create typed FormGroup.
  - [x] 3.3.2 Implement `FormErrorMapper` utility.
  - [x] 3.3.3 Test validation error mapping.

## Phase 4: Vertical Slice 2 - Application Detail & OCR

- [x] **4.1 Backend: OCR & File Handling**
  - [x] Verify `DocumentViewSet` and OCR status endpoint

- [x] **4.2 Shared File Upload Component**
  - [x] Create drag-drop zone with progress bar

- [x] **4.3 Application Detail View**
  - [x] Implement OCR polling pattern
  - [x] Show extracted data review modal

---

## Phase 5: Products Management

**Goal:** Full CRUD for Products with inline Tasks formset, replicating Django legacy behavior.

### 5.0 Legacy UI & Logic Audit

- [x] **5.0.1** Review `products/views/*.py` for CRUD logic:
  - `ProductListView`: paginated list with search via `ProductManager.search_products()`
  - `ProductDetailView`: shows product + related tasks
  - `ProductCreateView` / `ProductUpdateView`: form + `TaskModelFormSet` inline formset
  - Delete logic: `Product.can_be_deleted()` checks for related invoices/applications

- [x] **5.0.2** Review `products/forms/product_form.py`:
  - `SortableSelectMultiple` widget for drag-drop document ordering
  - Required/optional documents stored as comma-separated names
  - POST data uses `required_documents_multiselect` / `optional_documents_multiselect`

- [x] **5.0.3** Review `products/forms/task_form.py`:
  - `TaskModelFormSet` with `extra=0`, `max_num=10`, `can_delete=True`
  - Validation: `notify_days_before <= duration`, unique step per product, single `last_step`

### 5.1 Backend API Preparation

- [x] **5.1.1** Verify `ProductViewSet` is read-only; add write endpoints if needed:

  ```python
  # api/views.py - Extend ProductViewSet to ModelViewSet for full CRUD
  class ProductViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
      permission_classes = [IsAuthenticated]
      queryset = Product.objects.prefetch_related('tasks').all()
      serializer_class = ProductSerializer
      # ... existing config
  ```

- [x] **5.1.2** Create `ProductDetailSerializer` with nested tasks:

  ```python
  # api/serializers/product_serializer.py
  class TaskNestedSerializer(serializers.ModelSerializer):
      class Meta:
          model = Task
          fields = ['id', 'step', 'name', 'description', 'cost',
                    'duration', 'duration_is_business_days',
                    'notify_days_before', 'last_step']

  class ProductDetailSerializer(serializers.ModelSerializer):
      tasks = TaskNestedSerializer(many=True, read_only=True)
      required_document_types = DocumentTypeSerializer(many=True, read_only=True)
      optional_document_types = DocumentTypeSerializer(many=True, read_only=True)

      class Meta:
          model = Product
          fields = ['id', 'name', 'code', 'description', 'immigration_id',
                    'base_price', 'product_type', 'validity',
                    'required_documents', 'optional_documents',
                    'documents_min_validity', 'tasks',
                    'required_document_types', 'optional_document_types']
  ```

- [x] **5.1.3** Add `ProductCreateUpdateSerializer` with tasks write support:

  ```python
  class ProductCreateUpdateSerializer(serializers.ModelSerializer):
      tasks = TaskNestedSerializer(many=True)
      required_document_ids = serializers.ListField(
          child=serializers.IntegerField(), write_only=True, required=False)
      optional_document_ids = serializers.ListField(
          child=serializers.IntegerField(), write_only=True, required=False)

      class Meta:
          model = Product
          fields = ['name', 'code', 'description', 'immigration_id',
                    'base_price', 'product_type', 'validity',
                    'documents_min_validity', 'tasks',
                    'required_document_ids', 'optional_document_ids']

      def create(self, validated_data):
          tasks_data = validated_data.pop('tasks', [])
          req_ids = validated_data.pop('required_document_ids', [])
          opt_ids = validated_data.pop('optional_document_ids', [])

          # Convert IDs to comma-separated names preserving order
          req_docs = DocumentType.objects.filter(pk__in=req_ids)
          opt_docs = DocumentType.objects.filter(pk__in=opt_ids)
          docs_by_pk = {d.pk: d.name for d in list(req_docs) + list(opt_docs)}

          validated_data['required_documents'] = ','.join(
              docs_by_pk[pk] for pk in req_ids if pk in docs_by_pk)
          validated_data['optional_documents'] = ','.join(
              docs_by_pk[pk] for pk in opt_ids if pk in docs_by_pk)

          product = Product.objects.create(**validated_data)
          for task_data in tasks_data:
              Task.objects.create(product=product, **task_data)
          return product
  ```

- [x] **5.1.4** Run `bun run generate:api` to generate TypeScript clients

### 5.2 Product List View

- [x] **5.2.1** Create `features/products/product-list/product-list.component.ts`:

  ```typescript
  // Pseudocode - reuse DataTableComponent pattern from customer-list
  @Component({
    selector: 'app-product-list',
    standalone: true,
    imports: [DataTableComponent, SearchToolbarComponent, PaginationControlsComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ProductListComponent implements OnInit {
    private productsApi = inject(ProductsService); // Generated API client

    readonly products = signal<Product[]>([]);
    readonly isLoading = signal(true);
    readonly searchQuery = signal('');
    readonly currentPage = signal(1);
    readonly totalPages = signal(1);

    readonly columns: ColumnConfig[] = [
      { key: 'code', header: 'Code', sortable: true },
      { key: 'name', header: 'Name', sortable: true },
      { key: 'productType', header: 'Type', sortable: true },
      { key: 'basePrice', header: 'Base Price', sortable: true },
      { key: 'actions', header: '', template: this.actionsTemplate },
    ];

    ngOnInit(): void {
      this.loadProducts();
    }

    loadProducts(): void {
      this.isLoading.set(true);
      this.productsApi.productsList(this.currentPage(), 15, this.searchQuery())
        .subscribe({
          next: (response) => {
            this.products.set(response.results ?? []);
            this.totalPages.set(Math.ceil((response.count ?? 0) / 15));
            this.isLoading.set(false);
          },
          error: () => {
            this.toast.error('Failed to load products');
            this.isLoading.set(false);
          }
        });
    }
  }
  ```

- [x] **5.2.2** Add route `/products` to `app.routes.ts`

- [x] **5.2.3** Add navigation link to sidebar

### 5.3 Product Detail View

- [x] **5.3.1** Create `features/products/product-detail/product-detail.component.ts`:

  ```typescript
  // Show product info + tasks table + required/optional documents
  @Component({
    selector: 'app-product-detail',
    standalone: true,
    imports: [ZardCardComponent, ZardBadgeComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ProductDetailComponent implements OnInit {
    readonly product = signal<ProductDetail | null>(null);
    readonly isLoading = signal(true);

    // Computed: tasks sorted by step
    readonly sortedTasks = computed(() =>
      [...(this.product()?.tasks ?? [])].sort((a, b) => a.step - b.step)
    );
  }
  ```

- [x] **5.3.2** Add route `/products/:id` to `app.routes.ts`

### 5.4 Product Create/Edit Form

- [ ] **5.4.1** Create shared `SortableMultiSelectComponent`:

  ```typescript
  // Replicates Django's SortableSelectMultiple widget
  // Features: drag-drop reordering, checkbox selection, preserves order
  @Component({
    selector: "app-sortable-multi-select",
    standalone: true,
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class SortableMultiSelectComponent {
    options = input.required<{ id: number; label: string }[]>();
    selectedIds = input<number[]>([]);
    label = input<string>("");

    selectedIdsChange = output<number[]>();

    // Use @angular/cdk DragDropModule for reordering
  }
  ```

- [x] **5.4.2** Create `features/products/product-form/product-form.component.ts`:

  ```typescript
  @Component({
    selector: "app-product-form",
    standalone: true,
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ProductFormComponent implements OnInit {
    private fb = inject(FormBuilder);
    private route = inject(ActivatedRoute);

    readonly isEditMode = signal(false);
    readonly isSaving = signal(false);
    readonly documentTypes = signal<DocumentType[]>([]);

    // FormArray for tasks (replaces Django's TaskModelFormSet)
    readonly productForm = this.fb.group({
      name: ["", Validators.required],
      code: ["", Validators.required],
      description: [""],
      basePrice: [0, [Validators.required, Validators.min(0)]],
      productType: ["visa", Validators.required],
      validity: [null as number | null],
      documentsMinValidity: [null as number | null],
      requiredDocumentIds: [[] as number[]],
      optionalDocumentIds: [[] as number[]],
      tasks: this.fb.array<FormGroup>([]),
    });

    get tasksArray(): FormArray {
      return this.productForm.get("tasks") as FormArray;
    }

    addTask(): void {
      const taskGroup = this.fb.group({
        id: [null],
        step: [this.tasksArray.length + 1, Validators.required],
        name: ["", Validators.required],
        description: [""],
        cost: [0, Validators.min(0)],
        duration: [0, [Validators.required, Validators.min(0)]],
        durationIsBusinessDays: [true],
        notifyDaysBefore: [0, Validators.min(0)],
        lastStep: [false],
      });
      this.tasksArray.push(taskGroup);
    }

    removeTask(index: number): void {
      this.tasksArray.removeAt(index);
      // Renumber steps
      this.tasksArray.controls.forEach((ctrl, i) => {
        ctrl.patchValue({ step: i + 1 });
      });
    }

    // Validation: only one lastStep allowed
    validateLastStep(): boolean {
      const lastStepCount = this.tasksArray.controls.filter(
        (c) => c.value.lastStep,
      ).length;
      return lastStepCount <= 1;
    }
  }
  ```

- [x] **5.4.3** Add routes `/products/new` and `/products/:id/edit`

- [x] **5.4.4** Add `SortableMultiSelectComponent` to `docs/shared_components.md`

### 5.5 Product Deletion

- [x] **5.5.1** Implement delete with confirmation dialog:

  ```typescript
  // Use ConfirmDialogComponent from shared
  // Show warning if related applications exist (from can_be_deleted())
  onDelete(): void {
    this.productsApi.productsCanDelete(this.product()!.id).subscribe({
      next: (result) => {
        if (!result.canDelete) {
          this.toast.error(result.message);
          return;
        }
        if (result.warning) {
          this.confirmMessage.set(result.warning);
        }
        this.showConfirmDialog.set(true);
      }
    });
  }
  ```

---

## Phase 6: Customer Applications List & CRUD

**Goal:** Full applications management with document creation, workflow steps, and status tracking.

### 6.0 Legacy UI & Logic Audit

- [x] **6.0.1** Review `customer_applications/views/*.py`:
  - `DocApplicationListView`: paginated with search via `DocApplicationManager.search_doc_applications()`
  - `DocApplicationCreateView`: complex logic including:
    - `DocumentCreateFormSet` for initial documents
    - Auto-creation of first workflow step
    - Passport auto-import from customer or previous application
  - `DocApplicationUpdateView`: add new documents via `NewDocumentFormSet`
  - `DocApplicationDetailView`: shows documents, workflows, status

- [x] **6.0.2** Review `customer_applications/forms/doc_application.py`:
  - Customer/Product selects (disabled on edit)
  - doc_date with today's default

- [x] **6.0.3** Review `customer_applications/models/doc_application.py` properties:
  - `is_document_collection_completed`: all required docs completed
  - `is_application_completed`: last workflow step completed
  - `has_next_task`, `next_task`: workflow progression logic
  - `get_completed_documents()`, `get_incomplete_documents()`: ordered by product config

### 6.1 Backend API Preparation

- [x] **6.1.1** Extend `CustomerApplicationViewSet` for full CRUD:

  ```python
  class CustomerApplicationViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
      permission_classes = [IsAuthenticated]
      filter_backends = [filters.SearchFilter, filters.OrderingFilter]
      search_fields = ['product__name', 'product__code', 'customer__first_name',
                       'customer__last_name', 'doc_date']
      ordering_fields = ['doc_date', 'status', 'created_at']
      ordering = ['-id']

      def get_serializer_class(self):
          if self.action in ['create', 'update', 'partial_update']:
              return DocApplicationCreateUpdateSerializer
          return DocApplicationDetailSerializer

      @action(detail=True, methods=['post'], url_path='advance-workflow')
      def advance_workflow(self, request, pk=None):
          """Complete current workflow and create next step."""
          application = self.get_object()
          # Logic from has_next_task / next_task properties
          ...
  ```

- [x] **6.1.2** Create `DocApplicationCreateUpdateSerializer`: (implemented)

- [ ] **6.1.3** Run `bun run generate:api`

- [ ] **6.1.2** Create `DocApplicationCreateUpdateSerializer`:

  ```python
  class DocApplicationCreateUpdateSerializer(serializers.ModelSerializer):
      document_types = serializers.ListField(
          child=serializers.DictSerializer(), write_only=True, required=False
      )  # [{doc_type_id, required}]

      class Meta:
          model = DocApplication
          fields = ['customer', 'product', 'doc_date', 'notes', 'document_types']

      def create(self, validated_data):
          doc_types = validated_data.pop('document_types', [])
          user = self.context['request'].user

          with transaction.atomic():
              validated_data['created_by'] = user
              application = DocApplication.objects.create(**validated_data)

              # Create documents from doc_types
              for dt in doc_types:
                  doc_type = DocumentType.objects.get(pk=dt['doc_type_id'])
                  Document.objects.create(
                      doc_application=application,
                      doc_type=doc_type,
                      required=dt.get('required', True),
                      created_by=user,
                      created_at=timezone.now(),
                      updated_at=timezone.now(),
                  )

              # Create first workflow step
              first_task = application.product.tasks.order_by('step').first()
              if first_task:
                  DocWorkflow.objects.create(
                      doc_application=application,
                      task=first_task,
                      start_date=timezone.now().date(),
                      due_date=calculate_due_date(...),
                      status='pending',
                      created_by=user,
                  )

              # Auto-import passport if applicable
              if application.product.required_documents and 'Passport' in application.product.required_documents:
                  self._import_passport(application, user)

              return application
  ```

- [ ] **6.1.3** Run `bun run generate:api`

### 6.2 Application List View

- [ ] **6.2.1** Create `features/applications/application-list/application-list.component.ts`:

  ```typescript
  @Component({
    selector: 'app-application-list',
    standalone: true,
    imports: [DataTableComponent, SearchToolbarComponent,
              PaginationControlsComponent, ZardBadgeComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ApplicationListComponent implements OnInit {
    readonly columns: ColumnConfig[] = [
      { key: 'id', header: '#', sortable: true },
      { key: 'customer.fullName', header: 'Customer', sortable: false },
      { key: 'product.name', header: 'Product', sortable: true },
      { key: 'docDate', header: 'Date', sortable: true },
      { key: 'status', header: 'Status', template: this.statusTemplate },
      { key: 'actions', header: '', template: this.actionsTemplate },
    ];

    // Status badge colors
    readonly statusVariants: Record<string, string> = {
      pending: 'default',
      processing: 'secondary',
      completed: 'success',
      rejected: 'destructive',
    };
  }
  ```

- [ ] **6.2.2** Add route `/applications` to `app.routes.ts`

### 6.3 Application Create Form

- [ ] **6.3.1** Create `features/applications/application-form/application-form.component.ts`:

  ```typescript
  @Component({
    selector: "app-application-form",
    standalone: true,
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ApplicationFormComponent implements OnInit {
    private customersApi = inject(CustomersService);
    private productsApi = inject(ProductsService);

    readonly customers = signal<Customer[]>([]);
    readonly products = signal<Product[]>([]);
    readonly selectedProduct = signal<ProductDetail | null>(null);
    readonly documentTypes = signal<
      { docType: DocumentType; required: boolean }[]
    >([]);

    readonly applicationForm = this.fb.group({
      customerId: [null as number | null, Validators.required],
      productId: [null as number | null, Validators.required],
      docDate: [new Date().toISOString().split("T")[0], Validators.required],
      notes: [""],
    });

    // When product changes, load document types from product config
    onProductChange(productId: number): void {
      this.productsApi.productsRetrieve(productId).subscribe({
        next: (product) => {
          this.selectedProduct.set(product);
          // Parse required_documents and optional_documents
          const reqNames = (product.requiredDocuments || "")
            .split(",")
            .filter(Boolean);
          const optNames = (product.optionalDocuments || "")
            .split(",")
            .filter(Boolean);

          // Fetch DocumentTypes and set up checkboxes
          this.documentTypesApi.documentTypesList().subscribe((docTypes) => {
            const docs: { docType: DocumentType; required: boolean }[] = [];
            for (const name of reqNames) {
              const dt = docTypes.find((d) => d.name.trim() === name.trim());
              if (dt) docs.push({ docType: dt, required: true });
            }
            for (const name of optNames) {
              const dt = docTypes.find((d) => d.name.trim() === name.trim());
              if (dt) docs.push({ docType: dt, required: false });
            }
            this.documentTypes.set(docs);
          });
        },
      });
    }
  }
  ```

- [ ] **6.3.2** Create shared `CustomerSelectComponent` (searchable dropdown):

  ```typescript
  // Reusable select with async search for customers
  @Component({
    selector: "app-customer-select",
    standalone: true,
  })
  export class CustomerSelectComponent {
    selectedId = input<number | null>(null);
    disabled = input<boolean>(false);

    selectedIdChange = output<number>();

    // Uses ZardUI Popover + Command for searchable dropdown
  }
  ```

- [ ] **6.3.3** Add routes `/applications/new`, `/customers/:customerId/applications/new`

### 6.4 Workflow Progression

- [ ] **6.4.1** Add workflow actions to application detail:

  ```typescript
  // In existing application-detail.component.ts
  readonly canAdvanceWorkflow = computed(() => {
    const app = this.application();
    if (!app) return false;
    return app.isDocumentCollectionCompleted && app.hasNextTask;
  });

  advanceWorkflow(): void {
    this.applicationsApi.customerApplicationsAdvanceWorkflow(this.application()!.id)
      .subscribe({
        next: () => {
          this.toast.success('Workflow advanced');
          this.loadApplication(this.application()!.id);
        },
        error: () => this.toast.error('Failed to advance workflow')
      });
  }
  ```

- [ ] **6.4.2** Show workflow timeline in detail view

---

## Phase 7: Letters (Surat Permohonan)

**Goal:** Generate DOCX letters with customer data pre-filled, replicating Django's LetterService.

### 7.0 Legacy UI & Logic Audit

- [ ] **7.0.1** Review `letters/views.py`:
  - `SuratPermohonanView`: form with customer select + editable fields
  - `DownloadSuratPermohonanView`: POST generates DOCX via `LetterService`

- [ ] **7.0.2** Review `letters/forms.py`:
  - `SuratPermohonanForm`: customer dropdown, visa_type, personal fields
  - Fields auto-populated from customer data but editable

- [ ] **7.0.3** Review `letters/services/LetterService.py`:
  - `generate_letter_data()`: merges customer data with form overrides
  - `generate_letter_document()`: uses `mailmerge` library on DOCX template
  - Date formatting, gender translation (Indonesian), address line splitting

### 7.1 Backend API Preparation

- [ ] **7.1.1** Create `LettersViewSet`:

  ```python
  # api/views.py
  class LettersViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
      permission_classes = [IsAuthenticated]

      @action(detail=False, methods=['post'], url_path='surat-permohonan')
      def generate_surat_permohonan(self, request):
          customer_id = request.data.get('customer_id')
          if not customer_id:
              return self.error_response('Customer is required', status.HTTP_400_BAD_REQUEST)

          try:
              customer = Customer.objects.get(pk=customer_id)
          except Customer.DoesNotExist:
              return self.error_response('Customer not found', status.HTTP_404_NOT_FOUND)

          extra_data = {
              'doc_date': request.data.get('doc_date'),
              'visa_type': request.data.get('visa_type'),
              'name': request.data.get('name'),
              'gender': request.data.get('gender'),
              'country': request.data.get('country'),
              'birth_place': request.data.get('birth_place'),
              'birthdate': request.data.get('birthdate'),
              'passport_no': request.data.get('passport_no'),
              'passport_exp_date': request.data.get('passport_exp_date'),
              'address_bali': request.data.get('address_bali'),
          }

          service = LetterService(customer, settings.DOCX_SURAT_PERMOHONAN_TEMPLATE)
          try:
              data = service.generate_letter_data(extra_data)
              buffer = service.generate_letter_document(data)

              response = FileResponse(
                  buffer,
                  as_attachment=True,
                  filename=f'surat_permohonan_{customer.full_name}.docx',
                  content_type='application/vnd.openxmlformats-officedocument.wordprocessingml.document'
              )
              return response
          except FileNotFoundError as e:
              return self.error_response(str(e), status.HTTP_500_INTERNAL_SERVER_ERROR)

      @action(detail=False, methods=['get'], url_path='customer-data/(?P<customer_id>[^/.]+)')
      def get_customer_data(self, request, customer_id=None):
          """Get customer data pre-filled for the form."""
          customer = get_object_or_404(Customer, pk=customer_id)
          return Response({
              'name': customer.full_name,
              'gender': customer.gender or customer.get_gender_display(),
              'country': customer.nationality.alpha3_code if customer.nationality else None,
              'birthPlace': customer.birth_place or '',
              'birthdate': customer.birthdate.isoformat() if customer.birthdate else None,
              'passportNo': customer.passport_number or '',
              'passportExpDate': customer.passport_expiration_date.isoformat() if customer.passport_expiration_date else None,
              'addressBali': customer.address_bali or '',
          })
  ```

- [ ] **7.1.2** Add route to `api/urls.py`:

  ```python
  router.register(r'letters', LettersViewSet, basename='letters')
  ```

- [ ] **7.1.3** Run `bun run generate:api`

### 7.2 Surat Permohonan Form Component

- [ ] **7.2.1** Create `features/letters/surat-permohonan/surat-permohonan.component.ts`:

  ```typescript
  @Component({
    selector: 'app-surat-permohonan',
    standalone: true,
    imports: [ReactiveFormsModule, CustomerSelectComponent, ZardInputDirective,
              ZardButtonComponent, ZardSelectComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class SuratPermohonanComponent {
    private lettersApi = inject(LettersService);
    private countriesApi = inject(CountryCodesService);

    readonly countries = signal<CountryCode[]>([]);
    readonly isGenerating = signal(false);

    readonly form = this.fb.group({
      customerId: [null as number | null, Validators.required],
      docDate: [new Date().toISOString().split('T')[0], Validators.required],
      visaType: ['voa', Validators.required],
      name: ['', Validators.required],
      gender: [''],
      country: [null as string | null],  // alpha3 code
      birthPlace: [''],
      birthdate: [null as string | null],
      passportNo: [''],
      passportExpDate: [null as string | null],
      addressBali: [''],
    });

    readonly visaTypeOptions = [
      { value: 'voa', label: 'VOA' },
      { value: 'C1', label: 'C1' },
    ];

    // When customer changes, fetch and populate data
    onCustomerChange(customerId: number): void {
      this.lettersApi.lettersCustomerData(customerId).subscribe({
        next: (data) => {
          this.form.patchValue({
            name: data.name,
            gender: data.gender,
            country: data.country,
            birthPlace: data.birthPlace,
            birthdate: data.birthdate,
            passportNo: data.passportNo,
            passportExpDate: data.passportExpDate,
            addressBali: data.addressBali,
          });
        }
      });
    }

    generateLetter(): void {
      if (this.form.invalid) return;

      this.isGenerating.set(true);
      const formValue = this.form.getRawValue();

      this.lettersApi.lettersSuratPermohonan({
        customerId: formValue.customerId!,
        docDate: formValue.docDate,
        visaType: formValue.visaType,
        name: formValue.name,
        gender: formValue.gender,
        country: formValue.country,
        birthPlace: formValue.birthPlace,
        birthdate: formValue.birthdate,
        passportNo: formValue.passportNo,
        passportExpDate: formValue.passportExpDate,
        addressBali: formValue.addressBali,
      }, { observe: 'response', responseType: 'blob' }).subscribe({
        next: (response) => {
          // Download the blob
          const blob = response.body!;
          const url = window.URL.createObjectURL(blob);
          const a = document.createElement('a');
          a.href = url;
          a.download = `surat_permohonan_${formValue.name}.docx`;
          a.click();
          window.URL.revokeObjectURL(url);

          this.toast.success('Letter generated successfully');
          this.isGenerating.set(false);
        },
        error: () => {
          this.toast.error('Failed to generate letter');
          this.isGenerating.set(false);
        }
      });
    }
  }
  ```

- [ ] **7.2.2** Add route `/letters/surat-permohonan` to `app.routes.ts`

- [ ] **7.2.3** Add navigation link to sidebar under "Letters" section

---

## Phase 8: Invoices & Payments

**Goal:** Invoice management with line items, payments recording, and balance tracking.

- [ ] **8.1 Invoice Management**
  - [ ] Dynamic FormArray for line items (applications + amounts)
  - [ ] Computed totals using signals
  - [ ] Status badges (paid, partial, unpaid, overdue)
  - [ ] Customer application selection (exclude already invoiced)

- [ ] **8.2 Payment Recording**
  - [ ] Payment modal component
  - [ ] Validation against balance due (cannot overpay)
  - [ ] Payment history list

---

## Phase 9: Integration, Testing, and Cutover

- [ ] **9.1 Feature Flagging**
  - [ ] Install `django-waffle`
  - [ ] Create `ENABLE_ANGULAR_FRONTEND` flag
  - [ ] Conditional routing based on flag

- [ ] **9.2 Production Build & Deployment**
  - [ ] Configure Nginx routing (API vs Angular routes)
  - [ ] Deploy Angular build to `staticfiles/`
  - [ ] Configure CSP headers

- [ ] **9.3 Final Validation**
  - [ ] End-to-end testing all modules
  - [ ] Performance testing (N+1 queries audit)
  - [ ] Accessibility audit
  - [ ] Update `docs/implementation_feedback.md`
  - [ ] Complete feedback log

---

## Phase 10: Admin & Maintenance Tools (CRITICAL - RECENTLY ADDED)

**Goal:** Migrate system administration, maintenance, and backup/restore tools from legacy Django UI, preserving superuser-only access and real-time feedback.

### 10.0 Legacy UI & Logic Audit

- [ ] Review `admin_tools/views.py` and `admin_tools/services.py` for backup/restore mechanics (tar.zst, SQL dumpdata, media collection).
- [ ] Audit `admin_tools/components/document_type_list.py` (Unicorn) for document type CRUD rules.
- [ ] Review `admin_tools/templates/admin_tools/` for UI specifics: SSE logging, diagnostic result rendering.
- [ ] Audit `admin_tools/services.py` for media diagnostic vs repair logic.

### 10.1 Backend API Modernization (Security & Performance)

- [ ] **10.1.1 Enhance Auth Response**: Update `TokenAuthView` in `api/views.py` to include `isSuperuser` and `fullName` in token response.
- [ ] **10.1.2 Rebuild DocumentType API**:
  - Update `DocumentTypeSerializer` to include `validationRuleRegex`.
  - Convert `DocumentTypeViewSet` from `ReadOnlyModelViewSet` to `ModelViewSet`.
  - Add search/ordering by name/description.
- [ ] **10.1.3 Implement BackupsViewSet**:
  - `GET /api/backups/`: List local backups with metadata.
  - `POST /api/backups/start/`: Trigger SSE backup stream (using `services.backup_all`).
  - `GET /api/backups/{filename}/download/`: Secure download for backup archives.
  - `POST /api/backups/upload/`: Multi-part upload for existing archives.
  - `POST /api/backups/restore/`: Trigger SSE restore stream (using `services.restore_from_file`).
  - `DELETE /api/backups/`: Purge all backups (with secondary confirmation).
- [ ] **10.1.4 Implement ServerManagementViewSet**:
  - `POST /api/server-management/clear-cache/`: Global cache purge.
  - `GET /api/server-management/media-diagnostic/`: Comprehensive check of disk vs DB.
  - `POST /api/server-management/media-repair/`: Automated path fixing.
- [ ] **10.1.5 Schema Generation**: Run `bun run generate:api` to sync TypeScript clients.

### 10.2 Angular Admin Foundations

- [ ] **10.2.1 Superuser Authorization**:
  - Update `AuthService` to track `isSuperuser` status via signals.
  - Create `superuser.guard.ts` to protect `/admin/**` routes.
- [ ] **10.2.2 Admin Layout**: Add an "Admin" sidebar section with sub-links: Document Types, Backup/Restore, Server.

### 10.3 Document Types Management

- [ ] **10.3.1 Feature Module**: Create `features/admin/document-types/`.
- [ ] **10.3.2 CRUD Interface**: Replicate the Unicorn component behavior using `DataTableComponent`.
- [ ] **10.3.3 Integrity Enforcement**: Implement frontend validation to prevent deletion of document types referenced by products (using `can_be_deleted` endpoint).

### 10.4 Backup & Restore Module

- [ ] **10.4.1 Feature Module**: Create `features/admin/backups/`.
- [ ] **10.4.2 Dashboard View**: Cards for available backups with size/type badges (e.g., "Full" for backups with users).
- [ ] **10.4.3 Real-time SSE Log**: Create a terminal-style component to display the backup/restore log using `SseService`.
- [ ] **10.4.4 Restore Workflow**: Implementation of "Include Users" toggle and file upload zone.

### 10.5 Server Management Dashboard

- [ ] **10.5.1 Feature Module**: Create `features/admin/server-management/`.
- [ ] **10.5.2 Actions Bar**: Clean ZardUI buttons for cache and media maintenance.
- [ ] **10.5.3 Diagnostic View**: JSON/Table viewer for media diagnostic results, highlighting discrepancies (e.g., "Missing on disk").

### 10.6 Privileged Actions in Feature Modules

- [ ] **10.6.1 Bulk Deletion in Products**:
  - Add "Delete All" / "Delete Selected" button to `ProductListComponent` (visible only to superusers).
  - Implement `products/delete-all` API endpoint integration.
- [ ] **10.6.2 Force Delete Invoice**:
  - Implement a "Force Delete" option in Invoice deletion workflow for superusers.
  - Implement cascade deletion flag for associated Customer Applications as seen in legacy `InvoiceDeleteView`.

### 10.7 Navigation & UX

- [ ] Update `app.routes.ts` with lazy-loaded admin routes: - Implement `products/delete-all` API endpoint integration.
- [ ] **10.6.2 Force Delete Invoice**:
  - Implement a "Force Delete" option in Invoice deletion workflow for superusers.
  - Implement cascade deletion flag for associated Customer Applications as seen in legacy `InvoiceDeleteView`.

### 10.7 Navigation & UX

- [ ] Update `app.routes.ts` with lazy-loaded admin routes:
      `{ path: 'admin', canActivate: [superuserGuard], children: [...] }`
- [ ] Add sidebar icons (Settings, Database, Server) for admin sections.
- [ ] Ensure superuser-only elements are conditionally rendered across the entire SPA using a `directive` or `signal`.

---

## Phase 11: User Profile View (NEW FEATURE - ANGULAR EXCLUSIVE)

**Goal:** Add a user profile view accessible from the top-right profile icon, allowing users to view and edit their profile information using ZardUI components and following UX standards.

### 11.0 UX Research & Design

- [x] **11.0.1** Research UX standards for profile sections using ZardUI component documentation:
  - Profile icon in top-right header (MatIconButton pattern)
  - Dropdown menu for profile actions (logout, settings)
  - Profile view with avatar, personal info, and edit functionality
  - Form fields with proper spacing and validation

- [x] **11.0.2** Define profile data structure:
  - Display: full name, email, role, last login
  - Editable: first name, last name, email, phone, avatar upload
  - Security: password change (separate modal)

### 11.1 Backend API Preparation

- [ ] **11.1.1** Extend `TokenAuthView` to include user profile data in auth response:

  ```python
  # api/views.py
  class TokenAuthView(ApiErrorHandlingMixin, ObtainAuthToken):
      def post(self, request, *args, **kwargs):
          response = super().post(request, *args, **kwargs)
          if response.status_code == 200:
              user = request.user
              response.data.update({
                  'user': {
                      'id': user.id,
                      'username': user.username,
                      'firstName': user.first_name,
                      'lastName': user.last_name,
                      'email': user.email,
                      'isSuperuser': user.is_superuser,
                      'fullName': user.get_full_name(),
                      'lastLogin': user.last_login.isoformat() if user.last_login else None,
                  }
              })
          return response
  ```

- [ ] **11.1.2** Create `UserProfileViewSet` for profile management:

  ```python
  class UserProfileViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
      permission_classes = [IsAuthenticated]

      @action(detail=False, methods=['get'])
      def me(self, request):
          """Get current user profile."""
          user = request.user
          return Response({
              'id': user.id,
              'username': user.username,
              'firstName': user.first_name,
              'lastName': user.last_name,
              'email': user.email,
              'isSuperuser': user.is_superuser,
              'fullName': user.get_full_name(),
              'lastLogin': user.last_login.isoformat() if user.last_login else None,
          })

      @action(detail=False, methods=['patch'])
      def update_profile(self, request):
          """Update user profile."""
          user = request.user
          serializer = UserProfileUpdateSerializer(user, data=request.data, partial=True)
          if serializer.is_valid():
              serializer.save()
              return Response(serializer.data)
          return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

      @action(detail=False, methods=['post'])
      def change_password(self, request):
          """Change user password."""
          serializer = ChangePasswordSerializer(data=request.data, context={'user': user})
          if serializer.is_valid():
              user.set_password(serializer.validated_data['new_password'])
              user.save()
              return Response({'message': 'Password changed successfully'})
          return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
  ```

- [ ] **11.1.3** Create serializers:

  ```python
  class UserProfileUpdateSerializer(serializers.ModelSerializer):
      class Meta:
          model = User
          fields = ['first_name', 'last_name', 'email']

  class ChangePasswordSerializer(serializers.Serializer):
      old_password = serializers.CharField(required=True)
      new_password = serializers.CharField(required=True, validators=[validate_password])
      confirm_password = serializers.CharField(required=True)

      def validate(self, data):
          if data['new_password'] != data['confirm_password']:
              raise serializers.ValidationError("Passwords don't match")
          if not self.context['user'].check_password(data['old_password']):
              raise serializers.ValidationError("Old password is incorrect")
          return data
  ```

- [ ] **11.1.4** Add routes to `api/urls.py`:

  ```python
  router.register(r'user-profile', UserProfileViewSet, basename='user-profile')
  ```

- [ ] **11.1.5** Run `bun run generate:api`

### 11.2 Angular Profile Implementation

- [ ] **11.2.1** Update `AuthService` to store user profile data:

  ```typescript
  // core/services/auth.service.ts
  readonly currentUser = signal<UserProfile | null>(null);

  login(credentials: LoginCredentials): Observable<TokenResponse> {
    return this.http.post<TokenResponse>(`${this.apiUrl}/auth/token/`, credentials).pipe(
      tap(response => {
        this.token.set(response.token);
        this.currentUser.set(response.user);  // Store user data
      })
    );
  }
  ```

- [ ] **11.2.2** Update `MainLayoutComponent` to add profile icon:

  ```typescript
  // shared/layouts/main-layout.component.ts
  @Component({
    selector: 'app-main-layout',
    standalone: true,
    imports: [ZardButtonComponent, ZardAvatarComponent, ZardDropdownComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class MainLayoutComponent {
    private authService = inject(AuthService);

    readonly currentUser = this.authService.currentUser;

    readonly profileMenuItems = computed(() => [
      { label: 'Profile', action: () => this.router.navigate(['/profile']) },
      { label: 'Settings', action: () => this.router.navigate(['/settings']) },
      { label: 'Logout', action: () => this.logout() },
    ]);

    logout(): void {
      this.authService.logout();
      this.router.navigate(['/login']);
    }
  }
  ```

- [ ] **11.2.3** Create `features/profile/profile.component.ts`:

  ```typescript
  @Component({
    selector: 'app-profile',
    standalone: true,
    imports: [ReactiveFormsModule, ZardCardComponent, ZardInputDirective,
              ZardButtonComponent, ZardAvatarComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ProfileComponent implements OnInit {
    private profileApi = inject(UserProfileService);
    private authService = inject(AuthService);

    readonly currentUser = this.authService.currentUser;
    readonly isEditing = signal(false);
    readonly isSaving = signal(false);

    readonly profileForm = this.fb.group({
      firstName: ['', Validators.required],
      lastName: ['', Validators.required],
      email: ['', [Validators.required, Validators.email]],
    });

    ngOnInit(): void {
      this.loadProfile();
    }

    loadProfile(): void {
      this.profileApi.userProfileMe().subscribe({
        next: (user) => {
          this.profileForm.patchValue({
            firstName: user.firstName,
            lastName: user.lastName,
            email: user.email,
          });
        }
      });
    }

    toggleEdit(): void {
      this.isEditing.set(!this.isEditing());
      if (!this.isEditing()) {
        this.profileForm.patchValue({
          firstName: this.currentUser()?.firstName,
          lastName: this.currentUser()?.lastName,
          email: this.currentUser()?.email,
        });
      }
    }

    saveProfile(): void {
      if (this.profileForm.invalid) return;

      this.isSaving.set(true);
      this.profileApi.userProfileUpdateProfile(this.profileForm.value).subscribe({
        next: (user) => {
          this.authService.currentUser.set(user);
          this.isEditing.set(false);
          this.toast.success('Profile updated successfully');
        },
        error: () => this.toast.error('Failed to update profile'),
        complete: () => this.isSaving.set(false)
      });
    }
  }
  ```

- [ ] **11.2.4** Add route `/profile` to `app.routes.ts`

- [ ] **11.2.5** Add `ProfileComponent` to `docs/shared_components.md`

### 11.3 Password Change Modal

- [ ] **11.3.1** Create `ChangePasswordModalComponent`:

- [ ] **11.2.4** Add route `/profile` to `app.routes.ts`

- [ ] **11.2.5** Add `ProfileComponent` to `docs/shared_components.md`

### 11.3 Password Change Modal

- [ ] **11.3.1** Create `ChangePasswordModalComponent`:

  ```typescript
  @Component({
    selector: 'app-change-password-modal',
    standalone: true,
    imports: [ReactiveFormsModule, ZardInputDirective, ZardButtonComponent, ...],
    changeDetection: ChangeDetectionStrategy.OnPush,
  })
  export class ChangePasswordModalComponent {
    readonly isOpen = input(false);
    readonly isOpenChange = output<boolean>();

    readonly passwordForm = this.fb.group({
      oldPassword: ['', Validators.required],
      newPassword: ['', [Validators.required, Validators.minLength(8)]],
      confirmPassword: ['', Validators.required],
    }, { validators: passwordMatchValidator });

    changePassword(): void {
      if (this.passwordForm.invalid) return;

      this.profileApi.userProfileChangePassword(this.passwordForm.value).subscribe({
        next: () => {
          this.toast.success('Password changed successfully');
          this.isOpenChange.emit(false);
          this.passwordForm.reset();
        },
        error: () => this.toast.error('Failed to change password')
      });
    }
  }
  ```

- [ ] **11.3.2** Integrate modal into `ProfileComponent`

### 11.4 Avatar Upload (Optional Enhancement)

- [ ] **11.4.1** Add avatar field to user model and API
- [ ] **11.4.2** Implement file upload in profile component
- [ ] **11.4.3** Display avatar in header and profile view

### 11.5 Testing & Validation

- [ ] **11.5.1** Add unit tests for profile component
- [ ] **11.5.2** Test profile editing workflow
- [ ] **11.5.3** Validate password change security
- [ ] **11.5.4** Update `docs/implementation_feedback.md` with UX learnings
