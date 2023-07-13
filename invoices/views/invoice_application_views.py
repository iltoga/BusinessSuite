from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from invoices.forms import InvoiceApplicationCreateForm
from invoices.models import InvoiceApplication
from invoices.models.invoice import InvoiceApplication
from invoices.views.invoice_views import InvoiceApplicationCreateFormSet


class InvoiceApplicationUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("invoices.change_invoice",)
    model = InvoiceApplication
    form_class = InvoiceApplicationCreateForm
    template_name = "invoices/invoice_application_update.html"
    success_url = reverse_lazy("invoiceapplication-list")
    success_message = "Invoice Application updated successfully!"


class InvoiceApplicationDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("invoices.view_invoice",)
    model = InvoiceApplication
    template_name = "invoices/invoice_application_detail.html"
