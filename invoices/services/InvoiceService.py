import os
from io import BytesIO

from django.conf import settings
from django.utils.timezone import now as datetime_now
from mailmerge import MailMerge

import core.utils.formatutils as formatutils
from invoices.models.invoice import Invoice


class InvoiceService:
    def __init__(self, invoice: Invoice):
        self.invoice = invoice

    @staticmethod
    def _normalize_multiline_text(value: str) -> str:
        normalized = value.replace("\r\n", "\n").replace("\r", "\n")
        lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        return ", ".join(lines)

    def generate_invoice_data(self):
        cur_date = formatutils.as_date_str(datetime_now())
        data = {
            "document_date": cur_date,
            "invoice_no": self.invoice.invoice_no_display,
            "customer_name": (
                str(self.invoice.customer.company_name)
                if self.invoice.customer.customer_type == "company"
                else str(self.invoice.customer.full_name)
            ),
            "customer_company_name": (
                str(self.invoice.customer.company_name) if self.invoice.customer.customer_type == "person" else ""
            ),
            "customer_address_bali": self.invoice.customer.address_bali or "",
            "customer_telephone": (
                f"Mobile Ph:     {self.invoice.customer.telephone}" if self.invoice.customer.telephone else ""
            ),
            "customer_npwp": f"NPWP:     {self.invoice.customer.npwp}" if self.invoice.customer.npwp else "",
            "invoice_date": formatutils.as_date_str(self.invoice.invoice_date),
            "invoice_due_date": formatutils.as_date_str(self.invoice.due_date),
            "total_amount": formatutils.as_currency(self.invoice.total_amount),
            "total_paid": formatutils.as_currency(self.invoice.total_paid_amount),
            "total_due": formatutils.as_currency(self.invoice.total_due_amount),
        }

        items = []
        qty = 1
        for item in self.invoice.invoice_applications.all():
            # Match the 'Items' column from the Invoice List view:
            # "<product.code> - <customer_application.notes or customer.full_name>"
            prod_code = str(item.customer_application.product.code)
            prod_description = self._normalize_multiline_text(str(item.customer_application.product.description))
            notes = item.customer_application.notes
            customer_name = str(item.customer_application.customer.full_name)
            if notes:
                notes_text = self._normalize_multiline_text(str(notes))
                description = f"{prod_description} - {notes_text}"
            else:
                description = f"{prod_description} for {customer_name}"

            items.append(
                {
                    "invoice_item": prod_code,
                    "description": description,
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
        template_name = (
            getattr(settings, "DOCX_PARTIAL_INVOICE_TEMPLATE_NAME", "partial_invoice_template_with_footer.docx")
            if payments
            else getattr(settings, "DOCX_INVOICE_TEMPLATE_NAME", "invoice_template_with_footer.docx")
        )
        static_source_root = getattr(settings, "STATIC_SOURCE_ROOT", "static")
        template_path = os.path.join(static_source_root, "reporting", template_name)
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
