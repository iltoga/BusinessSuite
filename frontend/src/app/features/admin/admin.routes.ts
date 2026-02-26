import { adminGroupGuard } from '@/core/guards/admin-group.guard';
import { staffGuard } from '@/core/guards/staff.guard';
import { superuserGuard } from '@/core/guards/superuser.guard';
import { Routes } from '@angular/router';

export const adminRoutes: Routes = [
  {
    path: 'document-types',
    title: 'Document Types',
    canActivate: [staffGuard],
    loadComponent: () =>
      import('./document-types/document-types.component').then((c) => c.DocumentTypesComponent),
  },
  {
    path: 'document-types/:id',
    title: 'Document Type Details',
    canActivate: [staffGuard],
    loadComponent: () =>
      import('./document-types/document-type-detail/document-type-detail.component').then(
        (c) => c.DocumentTypeDetailComponent,
      ),
  },
  {
    path: 'workflow-notifications',
    title: 'Notifications Center',
    canActivate: [staffGuard],
    loadComponent: () =>
      import('./workflow-notifications/workflow-notifications.component').then(
        (c) => c.WorkflowNotificationsComponent,
      ),
  },

  {
    path: 'holidays',
    title: 'National Holidays',
    canActivate: [staffGuard],
    loadComponent: () => import('./holidays/holidays.component').then((c) => c.HolidaysComponent),
  },
  {
    path: 'backups',
    title: 'Backups',
    canActivate: [superuserGuard],
    loadComponent: () => import('./backups/backups.component').then((c) => c.BackupsComponent),
  },
  {
    path: 'server',
    title: 'Server Management',
    canActivate: [adminGroupGuard],
    loadComponent: () =>
      import('./server-management/server-management.component').then(
        (c) => c.ServerManagementComponent,
      ),
  },
  {
    path: 'systemcosts',
    title: 'System Costs',
    canActivate: [adminGroupGuard],
    loadComponent: () =>
      import('./system-costs/system-costs.component').then((c) => c.SystemCostsComponent),
  },

  {
    path: '',
    redirectTo: 'document-types',
    pathMatch: 'full',
  },
];
