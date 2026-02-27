import { Injectable, computed, inject, signal } from '@angular/core';

import { AuthService } from '@/core/services/auth.service';
import { MenuItem } from '@/shared/models/menu-item.model';

@Injectable({ providedIn: 'root' })
export class MenuService {
  private readonly authService = inject(AuthService);
  private readonly collapsed = signal<Record<string, boolean>>({
    utilities: true,
    reports: true,
    letters: true,
    admin: true,
  });

  readonly menuItems = computed<MenuItem[]>(() => [
    { id: 'dashboard', label: 'Dashboard', icon: 'layout-dashboard', route: '/dashboard' },
    { id: 'customers', label: 'Customers', icon: 'users', route: '/customers' },
    { id: 'applications', label: 'Applications', icon: 'folder', route: '/applications' },
    { id: 'invoices', label: 'Invoices', icon: 'file-text', route: '/invoices' },
    {
      id: 'letters',
      label: 'Letters',
      icon: 'file-text',
      collapsible: true,
      accessibility: { ariaHasPopup: 'menu' },
      children: [
        {
          id: 'letters-surat-permohonan',
          label: 'Surat Permohonan',
          route: '/letters/surat-permohonan',
        },
      ],
    },
    {
      id: 'utilities',
      label: 'Utils',
      icon: 'sparkles',
      collapsible: true,
      accessibility: { ariaHasPopup: 'menu' },
      children: [
        { id: 'utils-reminders', label: 'Reminders', route: '/utils/reminders' },
        { id: 'utils-passport-check', label: 'Passport Check', route: '/utils/passport-check' },
      ],
    },
    {
      id: 'reports',
      label: 'Reports',
      icon: 'file-text',
      collapsible: true,
      visible: () => this.authService.isAdminOrManager(),
      accessibility: { ariaHasPopup: 'menu' },
      children: [
        { id: 'reports-all', label: 'All Reports', route: '/reports' },
        { id: 'reports-kpi', label: 'KPI Dashboard', route: '/reports/kpi-dashboard' },
        { id: 'reports-revenue', label: 'Revenue Report', route: '/reports/revenue' },
        { id: 'reports-invoice-status', label: 'Invoice Status', route: '/reports/invoice-status' },
        { id: 'reports-monthly', label: 'Monthly Invoices', route: '/reports/monthly-invoices' },
        { id: 'reports-cash-flow', label: 'Cash Flow', route: '/reports/cash-flow' },
        { id: 'reports-ltv', label: 'Customer LTV', route: '/reports/customer-ltv' },
        {
          id: 'reports-pipeline',
          label: 'Application Pipeline',
          route: '/reports/application-pipeline',
        },
        {
          id: 'reports-product-revenue',
          label: 'Product Revenue',
          route: '/reports/product-revenue',
        },
        { id: 'reports-product-demand', label: 'Product Demand', route: '/reports/product-demand' },
        { id: 'reports-ai-costing', label: 'AI Costing', route: '/reports/ai-costing' },
      ],
    },
    {
      id: 'admin',
      label: 'Admin',
      icon: 'settings',
      collapsible: true,
      visible: () => this.canAccessAdminSection(),
      accessibility: { ariaHasPopup: 'menu' },
      children: [
        {
          id: 'admin-document-types',
          label: 'Document Types',
          route: '/admin/document-types',
          visible: () => this.canAccessStaffAdminItems(),
        },
        {
          id: 'admin-holidays',
          label: 'National Holidays',
          route: '/admin/holidays',
          visible: () => this.canAccessStaffAdminItems(),
        },
        {
          id: 'admin-notifications',
          label: 'Notifications Center',
          route: '/admin/workflow-notifications',
          visible: () => this.canAccessStaffAdminItems(),
        },
        {
          id: 'admin-backups',
          label: 'Backups',
          route: '/admin/backups',
          visible: () => this.canAccessBackups(),
        },
        {
          id: 'admin-server',
          label: 'Server Management',
          route: '/admin/server',
          visible: () => this.authService.isInAdminGroup(),
        },
        {
          id: 'admin-system-costs',
          label: 'System Costs',
          route: '/admin/systemcosts',
          visible: () => this.authService.isInAdminGroup(),
        },
      ],
    },
  ]);

  readonly visibleMenuItems = computed(() => this.filterVisible(this.menuItems()));

  isCollapsed(id: string): boolean {
    return !!this.collapsed()[id];
  }

  toggleCollapse(id: string): void {
    this.collapsed.update((state) => ({ ...state, [id]: !state[id] }));
  }

  toggleOverlayRootCollapse(id: string): void {
    const rootCollapsibleIds = this.getRootCollapsibleIds();
    this.collapsed.update((state) => {
      const next = { ...state };
      const willExpand = !!state[id];

      for (const rootId of rootCollapsibleIds) {
        next[rootId] = true;
      }

      next[id] = willExpand ? false : true;
      return next;
    });
  }

  collapseOverlayRootMenus(): void {
    const rootCollapsibleIds = this.getRootCollapsibleIds();
    this.collapsed.update((state) => {
      const next = { ...state };
      for (const rootId of rootCollapsibleIds) {
        next[rootId] = true;
      }
      return next;
    });
  }

  isVisible(item: MenuItem): boolean {
    return this.resolveCondition(item.visible, true);
  }

  isDisabled(item: MenuItem): boolean {
    return this.resolveCondition(item.disabled, false);
  }

  private resolveCondition(condition: MenuItem['visible'], fallback: boolean): boolean {
    if (typeof condition === 'function') {
      return condition();
    }
    return condition ?? fallback;
  }

  private filterVisible(items: MenuItem[]): MenuItem[] {
    return items
      .filter((item) => this.isVisible(item))
      .map((item) => ({
        ...item,
        children: item.children ? this.filterVisible(item.children) : undefined,
      }));
  }

  private getRootCollapsibleIds(): string[] {
    return this.menuItems()
      .filter((item) => item.collapsible)
      .map((item) => item.id);
  }

  private canAccessStaffAdminItems(): boolean {
    return this.authService.isStaff() || this.authService.isInAdminGroup();
  }

  private canAccessBackups(): boolean {
    return this.authService.isSuperuser() || this.authService.isInAdminGroup();
  }

  private canAccessAdminSection(): boolean {
    return (
      this.canAccessStaffAdminItems() ||
      this.canAccessBackups() ||
      this.authService.isInAdminGroup()
    );
  }
}
