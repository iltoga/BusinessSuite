import { superuserGuard } from '@/core/guards/superuser.guard';
import { Routes } from '@angular/router';

export const adminRoutes: Routes = [
  {
    path: 'document-types',
    title: 'Document Types',
    canActivate: [superuserGuard],
    loadComponent: () =>
      import('./document-types/document-types.component').then((c) => c.DocumentTypesComponent),
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
    canActivate: [superuserGuard],
    loadComponent: () =>
      import('./server-management/server-management.component').then(
        (c) => c.ServerManagementComponent,
      ),
  },
  {
    path: '',
    redirectTo: 'document-types',
    pathMatch: 'full',
  },
];
