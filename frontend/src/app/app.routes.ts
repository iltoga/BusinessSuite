import { authGuard } from '@/core/guards/auth.guard';
import { Routes } from '@angular/router';
import { ApplicationDetailComponent } from './features/applications/application-detail/application-detail.component';
import { ApplicationFormComponent } from './features/applications/application-form/application-form.component';
import { ApplicationListComponent } from './features/applications/application-list/application-list.component';
import { LoginComponent } from './features/auth/login/login.component';
import { CustomerDetailComponent } from './features/customers/customer-detail/customer-detail.component';
import { CustomerFormComponent } from './features/customers/customer-form/customer-form.component';
import { CustomerListComponent } from './features/customers/customer-list/customer-list.component';
import { DashboardComponent } from './features/dashboard/dashboard.component';
import { InvoiceDetailComponent } from './features/invoices/invoice-detail/invoice-detail.component';
import { InvoiceFormComponent } from './features/invoices/invoice-form/invoice-form.component';
import { InvoiceListComponent } from './features/invoices/invoice-list/invoice-list.component';
import { SuratPermohonanComponent } from './features/letters/surat-permohonan/surat-permohonan.component';
import { ProductDetailComponent } from './features/products/product-detail/product-detail.component';
import { ProductFormComponent } from './features/products/product-form/product-form.component';
import { ProductListComponent } from './features/products/product-list/product-list.component';
import { AuthLayoutComponent } from './shared/layouts/auth-layout/auth-layout.component';
import { MainLayoutComponent } from './shared/layouts/main-layout/main-layout.component';

export const routes: Routes = [
  {
    path: 'login',
    component: AuthLayoutComponent,
    children: [{ path: '', component: LoginComponent }],
  },
  {
    path: '',
    component: MainLayoutComponent,
    canActivate: [authGuard],
    children: [
      { path: 'dashboard', component: DashboardComponent },
      { path: 'customers', component: CustomerListComponent },
      { path: 'customers/new', component: CustomerFormComponent },
      { path: 'customers/:id/edit', component: CustomerFormComponent },
      { path: 'customers/:id', component: CustomerDetailComponent },
      { path: 'products', component: ProductListComponent },
      { path: 'products/new', component: ProductFormComponent },
      { path: 'products/:id/edit', component: ProductFormComponent },
      { path: 'products/:id', component: ProductDetailComponent },
      { path: 'applications', component: ApplicationListComponent },
      { path: 'applications/new', component: ApplicationFormComponent },
      { path: 'customers/:id/applications/new', component: ApplicationFormComponent },
      { path: 'applications/:id/edit', component: ApplicationFormComponent },
      { path: 'applications/:id', component: ApplicationDetailComponent },
      { path: 'invoices', component: InvoiceListComponent },
      { path: 'invoices/new', component: InvoiceFormComponent },
      { path: 'invoices/:id/edit', component: InvoiceFormComponent },
      { path: 'invoices/:id', component: InvoiceDetailComponent },
      { path: 'letters/surat-permohonan', component: SuratPermohonanComponent },
      { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
    ],
  },

  { path: '**', redirectTo: '/dashboard' },
];
