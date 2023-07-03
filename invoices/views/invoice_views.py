from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.forms import inlineformset_factory
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from invoices.forms import BaseInvoiceApplicationFormSet, InvoiceApplicationForm, InvoiceForm
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication

InvoiceApplicationFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=1,
    can_delete=True,
)


class InvoiceListView(PermissionRequiredMixin, ListView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            order_by = self.model._meta.ordering
            queryset = self.model.objects.search_customers(query).order_by(*order_by)
        return queryset


class InvoiceCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("invoices.add_invoice",)
    model = Invoice
    form_class = InvoiceForm
    template_name = "invoices/invoice_create.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice created successfully!"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["invoiceapplications"] = InvoiceApplicationFormSet(self.request.POST)
        else:
            data["invoiceapplications"] = InvoiceApplicationFormSet()
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        invoiceapplications = context["invoiceapplications"]

        self.object = form.save()
        if invoiceapplications.is_valid():
            invoiceapplications.instance = self.object
            invoiceapplications.save()

        return super().form_valid(form)


class InvoiceUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("invoices.change_invoice",)
    model = Invoice
    form_class = InvoiceForm
    template_name = "invoices/invoice_update.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice updated successfully!"

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data["invoiceapplications"] = InvoiceApplicationFormSet(self.request.POST, instance=self.object)
        else:
            data["invoiceapplications"] = InvoiceApplicationFormSet(instance=self.object)
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        invoiceapplications = context["invoiceapplications"]

        self.object = form.save()
        if invoiceapplications.is_valid():
            invoiceapplications.instance = self.object
            invoiceapplications.save()

        return super().form_valid(form)


class InvoiceDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = ("invoices.delete_invoice",)
    model = Invoice
    template_name = "invoices/invoice_delete.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view

    def delete(self, request, *args, **kwargs):
        self.object = self.get_object()
        # Add any extra steps here before deleting
        return super().delete(request, *args, **kwargs)


class InvoiceDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_detail.html"
