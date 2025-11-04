import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.http import FileResponse, HttpResponse
from django.utils.text import slugify
from django.views.generic import View

from invoices.models import Invoice
from invoices.services.InvoiceService import InvoiceService


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

        # Convert to PDF if requested
        temp_dir = None
        try:
            # Create a temporary directory for the conversion process
            temp_dir = tempfile.mkdtemp()
            temp_docx_path = Path(temp_dir) / f"{safe_name}.docx"
            temp_pdf_path = Path(temp_dir) / f"{safe_name}.pdf"

            # Write the DOCX buffer to a temporary file
            with open(temp_docx_path, "wb") as f:
                f.write(buf.getvalue())

            # Convert DOCX to PDF using LibreOffice soffice in headless mode
            # Optimized for Linux (Debian/Ubuntu) in Docker containers
            soffice = shutil.which("soffice")

            if not soffice:
                return HttpResponse(
                    "PDF conversion failed: LibreOffice 'soffice' not found. "
                    "Ensure LibreOffice is installed in the container.",
                    status=500,
                )

            # Call soffice to convert docx to pdf
            # --headless: run without GUI
            # --invisible: no splash screen
            # --nodefault: don't start with an empty document
            # --nofirststartwizard: skip first-run wizard
            # --nolockcheck: don't check for lock files (safe in containers)
            # --nologo: no logo on startup
            # --norestore: don't restore previous session
            # --convert-to pdf: output format
            # --outdir: output directory (must come before input file)
            cmd = [
                soffice,
                "--headless",
                "--invisible",
                "--nodefault",
                "--nofirststartwizard",
                "--nolockcheck",
                "--nologo",
                "--norestore",
                "--convert-to",
                "pdf",
                "--outdir",
                str(temp_dir),
                str(temp_docx_path),
            ]

            try:
                result = subprocess.run(
                    cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30
                )
            except subprocess.TimeoutExpired:
                return HttpResponse("PDF conversion timed out after 30 seconds.", status=500)
            except subprocess.CalledProcessError as e:
                error_msg = f"LibreOffice conversion failed: {e.stderr if e.stderr else str(e)}"
                return HttpResponse(error_msg, status=500)

            # Ensure PDF was created
            if not temp_pdf_path.exists():
                return HttpResponse("PDF conversion failed: output file not found.", status=500)

            # Read the PDF and return it (load into memory so we can safely delete temp files afterwards)
            with open(temp_pdf_path, "rb") as pdf_file:
                pdf_bytes = pdf_file.read()
                response = FileResponse(pdf_bytes, as_attachment=True, filename=f"{safe_name}.pdf")
                response["Content-Type"] = "application/pdf"
                return response

        finally:
            # Cleanup: remove temporary directory and all its contents
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
