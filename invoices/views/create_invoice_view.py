from django.shortcuts import redirect, render
from django.views import View
from invoices.models.invoice import Invoice
from invoices.forms import InvoiceForm


class CreateInvoiceView(View):
    def get(self, request, *args, **kwargs):
        form = InvoiceForm(initial={'invoice_no': Invoice.objects.next_invoice_no()})
        return render(request, 'invoices/create_invoice.html', {'form': form})

    def post(self, request, *args, **kwargs):
        form = InvoiceForm(request.POST)
        if form.is_valid():
            form.save()
            return redirect('invoices:index')
        return render(request, 'invoices/create_invoice.html', {'form': form})
