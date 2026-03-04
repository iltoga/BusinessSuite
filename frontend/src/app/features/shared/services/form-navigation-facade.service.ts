import { Injectable } from '@angular/core';
import { ActivatedRoute, Router } from '@angular/router';
import { Location } from '@angular/common';

@Injectable({
  providedIn: 'root',
})
export class FormNavigationFacadeService {
  goBackFromApplicationForm(params: {
    router: Router;
    route: ActivatedRoute;
    location: Location;
    applicationId: number | null;
    isEditMode: boolean;
    selectedCustomerId: string | number | null | undefined;
  }): void {
    const { router, route, location, applicationId, isEditMode, selectedCustomerId } = params;
    const nav = router.getCurrentNavigation();
    let st: any = (nav && nav.extras && (nav.extras.state as any)) || {};
    try {
      if (typeof window !== 'undefined' && history && (history as any).state) {
        st = { ...(st || {}), ...((history as any).state || {}) };
      }
    } catch {
      // Ignore history access errors in SSR/hardened contexts.
    }

    const stateFrom = st?.from;
    const focusId = st?.focusId;

    const focusState: Record<string, unknown> = { focusTable: true };
    if (focusId) {
      focusState['focusId'] = focusId;
    } else if (applicationId) {
      focusState['focusId'] = applicationId;
    }

    if (st?.searchQuery) {
      focusState['searchQuery'] = st.searchQuery;
    }
    const page = Number(st?.page);
    if (Number.isFinite(page) && page > 0) {
      focusState['page'] = Math.floor(page);
    }

    if (stateFrom === 'customers') {
      void router.navigate(['/customers'], { state: focusState });
      return;
    }
    if (stateFrom === 'applications') {
      void router.navigate(['/applications'], { state: focusState });
      return;
    }

    try {
      if (window.history.length > 1) {
        location.back();
        return;
      }
    } catch {
      // Ignore and continue fallback routing.
    }

    const customerIdParam = route.snapshot.paramMap.get('id') || selectedCustomerId;
    if (customerIdParam) {
      void router.navigate(['/customers', Number(customerIdParam)]);
      return;
    }

    if (isEditMode && applicationId) {
      void router.navigate(['/applications', applicationId]);
      return;
    }

    void router.navigate(['/applications'], { state: focusState });
  }

  goBackFromInvoiceForm(params: {
    router: Router;
    state: any;
    invoiceId: number | null | undefined;
  }): void {
    const { router, state, invoiceId } = params;
    const st = state || {};

    const focusState: Record<string, unknown> = { focusTable: true };
    if (st?.focusId) {
      focusState['focusId'] = st.focusId;
    } else if (invoiceId) {
      focusState['focusId'] = invoiceId;
    }
    if (st?.searchQuery) {
      focusState['searchQuery'] = st.searchQuery;
    }
    const page = Number(st?.page);
    if (Number.isFinite(page) && page > 0) {
      focusState['page'] = Math.floor(page);
    }

    if (st?.from === 'applications') {
      void router.navigate(['/applications'], { state: focusState });
      return;
    }

    if (typeof st?.returnUrl === 'string' && st.returnUrl.startsWith('/')) {
      void router.navigateByUrl(st.returnUrl, {
        state: {
          searchQuery: st.searchQuery ?? null,
          page: st.page ?? null,
        },
      });
      return;
    }

    if (st?.from === 'customer-detail' && st?.customerId) {
      void router.navigate(['/customers', st.customerId], {
        state: {
          searchQuery: st.searchQuery ?? null,
          page: st.page ?? null,
        },
      });
      return;
    }

    void router.navigate(['/invoices'], { state: focusState });
  }
}
