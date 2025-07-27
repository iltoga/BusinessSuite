import os
from io import BytesIO

from django.conf import settings
from django.utils.timezone import now as datetime_now
from mailmerge import MailMerge

import core.utils.formatutils as formatutils


class InvoiceService:
    def __init__(self, invoice):
        self.invoice = invoice

    def generate_invoice_data(self):
        cur_date = formatutils.as_date_str(datetime_now())
        data = {
            "document_date": cur_date,
            "invoice_no": self.invoice.invoice_no_display,
            "customer_name": str(self.invoice.customer),
            "invoice_date": formatutils.as_date_str(self.invoice.invoice_date),
            "total_amount": formatutils.as_currency(self.invoice.total_amount),
            "total_paid": formatutils.as_currency(self.invoice.total_paid_amount),
            "total_due": formatutils.as_currency(self.invoice.total_due_amount),
        }

        items = []
        qty = 1
        for item in self.invoice.invoice_applications.all():
            items.append(
                {
                    "invoice_item": str(item.customer_application.product.code),
                    "description": item.customer_application.product.name,
                    "quantity": str(qty),
                    "unit_price": formatutils.as_currency(item.amount),
                    "amount": formatutils.as_currency(item.amount * qty),
                    "paid_amount": formatutils.as_currency(item.paid_amount),
                    "due_amount": formatutils.as_currency(item.amount - item.paid_amount),
                }
            )

        return data, items

    def generate_partial_invoice_data(self):
        data, items = self.generate_invoice_data()

        payments = []
        for item in self.invoice.invoice_applications.all():
            for payment in item.payments.all():
                payments.append(
                    {
                        "payment_invoice_application": str(payment.invoice_application.customer_application.product),
                        "payment_date": formatutils.as_date_str(payment.payment_date),
                        "payment_type": payment.get_payment_type_display(),
                        "payment_amount": formatutils.as_currency(payment.amount),
                    }
                )

        return data, items, payments

    def generate_invoice_document(self, data, items, payments=None):
        template_name = "partial_invoice_template_with_footer.docx" if payments else "invoice_template_with_footer.docx"
        template_path = os.path.join(settings.STATIC_SOURCE_ROOT, "reporting", template_name)
        with open(template_path, "rb") as template:
            doc = MailMerge(template)
            doc.merge(**data)
            doc.merge_rows("invoice_item", items)

            if payments:
                doc.merge_rows("payment_invoice_application", payments)

            buf = BytesIO()
            doc.write(buf)

        buf.seek(0)
        return buf
