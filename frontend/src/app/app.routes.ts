import { authGuard } from '@/core/guards/auth.guard';
import { Routes } from '@angular/router';
import { LoginComponent } from './features/auth/login/login.component';
import { CustomerDetailComponent } from './features/customers/customer-detail/customer-detail.component';
import { CustomerFormComponent } from './features/customers/customer-form/customer-form.component';
import { CustomerListComponent } from './features/customers/customer-list/customer-list.component';
import { DashboardComponent } from './features/dashboard/dashboard.component';
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
      { path: '', redirectTo: '/dashboard', pathMatch: 'full' },
    ],
  },
  { path: '**', redirectTo: '/dashboard' },
];
