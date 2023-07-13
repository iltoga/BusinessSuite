import os
from io import BytesIO

from django.conf import settings
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.http import FileResponse, HttpResponse
from django.utils.timezone import now as datetime_now
from django.views.generic import View
from mailmerge import MailMerge

import core.utils.formatutils as formatutils
from invoices.models import Invoice


class InvoiceDownloadView(View):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get("pk")

        try:
            # Get invoice data from the database
            invoice = Invoice.objects.get(pk=pk)
        except Invoice.DoesNotExist:
            return HttpResponse(f"Invoice with ID {pk} not found.", status=404)

        # Prepare the data to be passed to the Word template
        cur_date = formatutils.as_date_str(datetime_now())
        data = {
            "document_date": cur_date,
            "invoice_no": invoice.invoice_no_display,
            "customer_name": str(invoice.customer),
            "invoice_date": formatutils.as_date_str(invoice.invoice_date),
            "total_amount": formatutils.as_currency(invoice.total_amount),
        }

        # Prepare invoice items
        items = []
        # TODO: for now is always 1, but in the future we might have multiple items
        qty = 1
        for item in invoice.invoice_applications.all():
            items.append(
                {
                    "invoice_item": str(item.customer_application.product.code),
                    "description": item.customer_application.product.name,
                    "quantity": str(qty),
                    "unit_price": formatutils.as_currency(item.customer_application.price),
                    "amount": formatutils.as_currency(item.customer_application.price * qty),
                }
            )

        # Generate invoice from the Word template
        template_path = os.path.join(settings.STATIC_SOURCE_ROOT, "reporting/invoice_template_with_footer.docx")
        with open(template_path, "rb") as template:
            doc = MailMerge(template)
            doc.merge(**data)
            doc.merge_rows("invoice_item", items)
            buf = BytesIO()
            doc.write(buf)

        # Send the docx file as a response
        buf.seek(0)
        return FileResponse(buf, as_attachment=True, filename=f"Invoice_{pk}.docx")
