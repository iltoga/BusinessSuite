import logging

from django.http import FileResponse, HttpResponse
from django.utils.text import slugify
from django.views.generic import View

from core.utils.pdf_converter import PDFConverter, PDFConverterError
from invoices.models import Invoice
from invoices.services.InvoiceService import InvoiceService

logger = logging.getLogger(__name__)


class InvoiceDownloadView(View):
    def get(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        format_type = request.GET.get("format", "docx").lower()

        # Validate format parameter
        if format_type not in ["docx", "pdf"]:
            return HttpResponse("Invalid format. Use 'docx' or 'pdf'.", status=400)

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

        # Build a safe filename containing the invoice display and the customer full name.
        # Use django's slugify to remove/replace special characters then convert hyphens to underscores.
        raw_name = f"{invoice.invoice_no_display}_{invoice.customer.full_name}"
        safe_name = slugify(raw_name, allow_unicode=False).replace("-", "_") or f"Invoice_{pk}"
        # Limit filename length to avoid filesystem issues
        safe_name = safe_name[:200]

        # Return DOCX directly if requested
        if format_type == "docx":
            return FileResponse(buf, as_attachment=True, filename=f"{safe_name}.docx")

        # Convert to PDF using LibreOffice (via PDFConverter utility)
        try:
            pdf_bytes = PDFConverter.docx_buffer_to_pdf(buf)
            response = HttpResponse(pdf_bytes, content_type="application/pdf")
            response["Content-Disposition"] = f'attachment; filename="{safe_name}.pdf"'
            return response

        except PDFConverterError as e:
            logger.error(f"PDF conversion failed for invoice {pk}: {e}")
            return HttpResponse(
                f"PDF conversion failed: {str(e)}. " "Please ensure LibreOffice is installed in the container.",
                status=500,
            )
