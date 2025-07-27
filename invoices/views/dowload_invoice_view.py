from django.http import FileResponse, HttpResponse
from django.views.generic import View

from invoices.models import Invoice
from invoices.services.InvoiceService import InvoiceService


class InvoiceDownloadView(View):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get("pk")

        try:
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return HttpResponse(f"Invoice with ID {pk} not found.", status=404)

        invoice_service = InvoiceService(invoice)

        # if payment is complete, generate the full invoice
        if invoice.total_paid_amount == 0 or invoice.is_payment_complete:
            data, items = invoice_service.generate_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items)
        else:
            data, items, payments = invoice_service.generate_partial_invoice_data()
            buf = invoice_service.generate_invoice_document(data, items, payments)

        return FileResponse(buf, as_attachment=True, filename=f"Invoice_{pk}.docx")
