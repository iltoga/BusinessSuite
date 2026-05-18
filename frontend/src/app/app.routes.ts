import { adminOrManagerGuard } from '@/core/guards/admin-or-manager.guard';
import { authGuard } from '@/core/guards/auth.guard';
import { rbacMenuGuard } from '@/core/guards/rbac-menu.guard';
import { Routes } from '@angular/router';
import { AuthLayoutComponent } from './shared/layouts/auth-layout/auth-layout.component';
import { MainLayoutComponent } from './shared/layouts/main-layout/main-layout.component';

export const routes: Routes = [
  {
    path: 'login',
    component: AuthLayoutComponent,
    children: [
      {
        path: '',
        loadComponent: () => import('./features/auth/login/login.component').then((c) => c.LoginComponent),
      },
    ],
  },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      {
        path: 'dashboard',
        loadComponent: () => import('./features/dashboard/dashboard.component').then((c) => c.DashboardComponent),
      },
      {
        path: 'customers',
        loadComponent: () => import('./features/customers/customer-list/customer-list.component').then((c) => c.CustomerListComponent),
      },
      {
        path: 'customers/new',
        loadComponent: () => import('./features/customers/customer-form/customer-form.component').then((c) => c.CustomerFormComponent),
      },
      {
        path: 'customers/:id/edit',
        loadComponent: () => import('./features/customers/customer-form/customer-form.component').then((c) => c.CustomerFormComponent),
      },
      {
        path: 'customers/:id',
        loadComponent: () => import('./features/customers/customer-detail/customer-detail.component').then((c) => c.CustomerDetailComponent),
      },
      {
        path: 'products',
        loadComponent: () => import('./features/products/product-list/product-list.component').then((c) => c.ProductListComponent),
      },
      {
        path: 'products/new',
        loadComponent: () => import('./features/products/product-form/product-form.component').then((c) => c.ProductFormComponent),
      },
      {
        path: 'products/:id/edit',
        loadComponent: () => import('./features/products/product-form/product-form.component').then((c) => c.ProductFormComponent),
      },
      {
        path: 'products/:id',
        loadComponent: () => import('./features/products/product-detail/product-detail.component').then((c) => c.ProductDetailComponent),
      },
      {
        path: 'applications',
        loadComponent: () => import('./features/applications/application-list/application-list.component').then((c) => c.ApplicationListComponent),
      },
      {
        path: 'applications/new',
        loadComponent: () => import('./features/applications/application-form/application-form.component').then((c) => c.ApplicationFormComponent),
      },
      {
        path: 'customers/:id/applications/new',
        loadComponent: () => import('./features/applications/application-form/application-form.component').then((c) => c.ApplicationFormComponent),
      },
      {
        path: 'applications/:id/edit',
        loadComponent: () => import('./features/applications/application-form/application-form.component').then((c) => c.ApplicationFormComponent),
      },
      {
        path: 'applications/:id',
        loadComponent: () => import('./features/applications/application-detail/application-detail.component').then((c) => c.ApplicationDetailComponent),
      },
      {
        path: 'invoices',
        loadComponent: () => import('./features/invoices/invoice-list/invoice-list.component').then((c) => c.InvoiceListComponent),
      },
      {
        path: 'invoices/import',
        loadComponent: () => import('./features/invoices/invoice-import/invoice-import.component').then((c) => c.InvoiceImportComponent),
      },
      {
        path: 'invoices/new',
        loadComponent: () => import('./features/invoices/invoice-form/invoice-form.component').then((c) => c.InvoiceFormComponent),
      },
      {
        path: 'invoices/:id/edit',
        loadComponent: () => import('./features/invoices/invoice-form/invoice-form.component').then((c) => c.InvoiceFormComponent),
      },
      {
        path: 'invoices/:id',
        loadComponent: () => import('./features/invoices/invoice-detail/invoice-detail.component').then((c) => c.InvoiceDetailComponent),
      },
      {
        path: 'utils/reminders',
        loadComponent: () => import('./features/utils/reminders/reminders.component').then((c) => c.RemindersComponent),
      },
      {
        path: 'letters/surat-permohonan',
        loadComponent: () => import('./features/letters/surat-permohonan/surat-permohonan.component').then((c) => c.SuratPermohonanComponent),
      },
      {
        path: 'profile',
        loadComponent: () => import('./features/profile/profile.component').then((c) => c.ProfileComponent),
      },
      {
        path: 'reports',
        loadComponent: () => import('./features/reports/reports.component').then((c) => c.ReportsComponent),
        canActivate: [rbacMenuGuard],
        data: { menuId: 'reports' },
      },
      {
        path: 'reports/:slug',
        loadComponent: () => import('./features/reports/reports.component').then((c) => c.ReportsComponent),
        canActivate: [rbacMenuGuard],
        data: { menuId: 'reports' },
      },
      {
        path: 'utils/passport-check',
        loadComponent: () => import('./features/utils/passport-check/passport-check.component').then((c) => c.PassportCheckComponent),
      },
      {
        path: 'admin',
        loadChildren: () => import('./features/admin/admin.routes').then((m) => m.adminRoutes),
      },
      { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
    ],
  },

  { path: '**', redirectTo: '/dashboard' },
];
