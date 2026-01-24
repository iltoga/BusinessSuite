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
- [ ] Review generated TypeScript interfaces from OpenAPI
- [ ] Verify backend endpoint exists and matches OpenAPI schema
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

- [ ] **0.1 Initialize Feedback & Documentation System**
  - [ ] 0.1.1 Create `docs/shared_components.md`.
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

      ```typescript
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
      ```

      ```

      ```

  - [ ] 0.1.2 Create `docs/implementation_feedback.md`.
    - Structure:

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
      ```

    - _Action:_ Commit these files to the repository root immediately.

- [ ] **0.2 Backend API Configuration (The Contract)**
  - [ ] 0.2.1 Install and Configure `drf-spectacular`.
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

  - [ ] 0.2.2 Install and Configure `djangorestframework-camel-case`.
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

  - [ ] 0.2.3 Implement Standardized Error Handling.
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

  - [ ] 0.2.4 Configure CORS and Hybrid Auth.
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

- [ ] **0.3 Frontend Scaffold (Bun + Angular + ZardUI)**
  - [ ] 0.3.1 Initialize Angular Project with Bun.
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

  - [ ] 0.3.2 Initialize ZardUI (Tailwind v4).
    - Run: `cd frontend && bunx @ngzard/ui init`
    - Select:
      - Theme: Neutral
      - Use CSS variables: Yes
      - Default paths: Yes
    - Verify files created:
      - `tailwind.config.js` (or v4 CSS)
      - `components.json`
      - `src/styles.css` (with Tailwind directives)

  - [ ] 0.3.3 Configure Proxy for Development.
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

- [ ] **1.1 API Client Generation**
  - [ ] 1.1.1 Setup OpenAPI Generator.
    - Add to `frontend/package.json`:

      ```json
      {
        "scripts": {
          "generate:api": "bunx @openapitools/openapi-generator-cli generate -i http://localhost:8000/api/schema/ -g typescript-angular -o src/app/core/api --additional-properties=fileNaming=kebab-case,ngVersion=19"
        }
      }
      ```

  - [ ] 1.1.2 Generate Clients.
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

- [ ] **1.2 Authentication Module**
  - [ ] 1.2.1 Implement `AuthService`.
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

  - [ ] 1.2.2 Implement `AuthInterceptor` (Functional).
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

  - [ ] 1.2.3 Implement `AuthGuard`.
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

- [ ] **1.3 Shared UI Components (ZardUI)**
  - [ ] 1.3.1 Install Base Components.
    - Run: `bunx @ngzard/ui add button input label card table dialog toast badge avatar dropdown separator skeleton`
    - _Verify:_ Check `src/app/shared/components/ui/` for generated components.

  - [ ] 1.3.2 Create `DataTableComponent` (Smart Wrapper).
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

  - [ ] 1.3.3 Create `ConfirmDialogComponent`.
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

  - [ ] 1.3.4 Create `GlobalToastService`.
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

- [ ] **1.4 Application Layouts**
  - [ ] 1.4.1 Create `MainLayoutComponent`.
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

  - [ ] 1.4.2 Create `AuthLayoutComponent`.
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

- [ ] **2.1 Login Page**
  - [ ] 2.1.1 Create `features/auth/login/login.component.ts`.
  - [ ] 2.1.2 Implement Form.

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

  - [ ] 2.1.3 UX Improvements.
    - Use ZardUI `Input` with error states
    - Add loading state to submit button
    - Show password toggle

- [ ] **2.2 Dashboard (Placeholder)**
  - [ ] 2.2.1 Create `features/dashboard/dashboard.component.ts`.
  - [ ] 2.2.2 Add basic stats cards.

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

  - [ ] 2.2.3 Connect to `MainLayout` in `app.routes.ts`.

## Phase 3: Vertical Slice 1 - Customer Management

**Goal:** Full CRUD for Customers, proving the pattern.

- [ ] **3.1 Backend Preparation**
  - [ ] 3.1.1 Audit `CustomerViewSet`.

    ```python
    class CustomerViewSet(viewsets.ModelViewSet):
        queryset = Customer.objects.select_related('agent', 'country').all()
        serializer_class = CustomerSerializer
        filter_backends = [SearchFilter, OrderingFilter]
        search_fields = ['first_name', 'last_name', 'email']
    ```

  - [ ] 3.1.2 Refactor Logic (if needed).
    - Move complex creation logic to `core/services/customer_service.py`.

- [ ] **3.2 Customer List View**
  - [ ] 3.2.1 Create `features/customers/customer-list/`.
  - [ ] 3.2.2 Implement State with Signals.
  - [ ] 3.2.3 Use `DataTableComponent` from shared.
  - [ ] 3.2.4 Implement debounced search.

- [ ] **3.3 Customer Create/Edit Form**
  - [ ] 3.3.1 Create typed FormGroup.
  - [ ] 3.3.2 Implement `FormErrorMapper` utility.
  - [ ] 3.3.3 Test validation error mapping.

## Phase 4: Vertical Slice 2 - Applications & OCR

- [ ] **4.1 Backend: OCR & File Handling**
  - Verify `DocumentViewSet` and OCR status endpoint

- [ ] **4.2 Shared File Upload Component**
  - Create drag-drop zone with progress bar

- [ ] **4.3 Application Detail View**
  - Implement OCR polling pattern
  - Show extracted data review modal

## Phase 5: Vertical Slice 3 - Invoices & Payments

- [ ] **5.1 Invoice Management**
  - Dynamic FormArray for line items
  - Computed totals using signals

- [ ] **5.2 Payment Recording**
  - Payment modal component
  - Validation against balance due

## Phase 6: Integration, Testing, and Cutover

- [ ] **6.1 Feature Flagging**
  - Install `django-waffle`
  - Create `ENABLE_ANGULAR_FRONTEND` flag

- [ ] **6.2 Production Build & Deployment**
  - Configure Nginx routing
  - Deploy Angular build

- [ ] **6.3 Final Validation**
  - End-to-end testing
  - Update documentation
  - Complete feedback log
