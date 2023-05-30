from django.shortcuts import redirect, render
from django.views.generic import CreateView
from invoices.models.invoice import Invoice
from invoices.forms import InvoiceForm
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin


class CreateInvoiceView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ('invoices.add_invoice',)
    model = Invoice
    form_class = InvoiceForm
    template_name = 'invoices/create_invoice.html'
    success_url = 'invoices:index'
    success_message = "Invoice created successfully!"

    def get(self, request, *args, **kwargs):
        form = InvoiceForm(initial={'invoice_no': Invoice.objects.next_invoice_no()})
        return render(request, 'invoices/create_invoice.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = InvoiceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('invoices:index')
        return render(request, 'invoices/create_invoice.html', {'form': form})
