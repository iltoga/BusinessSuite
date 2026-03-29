"""View helpers for invoice status dashboard report responses."""

from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView
from reports.services import build_invoice_status_dashboard_context


class InvoiceStatusDashboardView(LoginRequiredMixin, TemplateView):
    """Invoice status tracking and aging analysis."""

    template_name = "reports/invoice_status_dashboard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(build_invoice_status_dashboard_context())
        return context
