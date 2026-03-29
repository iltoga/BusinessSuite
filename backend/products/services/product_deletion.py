"""Service helpers for safely deleting product records and references."""

from __future__ import annotations

from typing import Any

from customer_applications.models import DocApplication, Document, DocWorkflow
from django.db import transaction
from django.db.models import Count
from invoices.models.invoice import Invoice, InvoiceApplication
from payments.models import Payment
from products.models import Product, Task

PREVIEW_RECORD_LIMIT = 25


def build_product_delete_preview(product: Product, *, limit: int = PREVIEW_RECORD_LIMIT) -> dict[str, Any]:
    record_limit = max(1, int(limit or PREVIEW_RECORD_LIMIT))

    tasks_qs = Task.objects.filter(product=product).order_by("step", "id")
    applications_qs = (
        DocApplication.objects.filter(product=product)
        .select_related("customer")
        .annotate(
            workflow_count=Count("workflows", distinct=True),
            document_count=Count("documents", distinct=True),
            invoice_line_count=Count("invoice_applications", distinct=True),
        )
        .order_by("-id")
    )
    invoice_lines_qs = (
        InvoiceApplication.objects.filter(product=product)
        .select_related("invoice__customer", "customer_application__customer")
        .annotate(payment_count=Count("payments", distinct=True))
        .order_by("-id")
    )

    tasks_count = tasks_qs.count()
    applications_count = applications_qs.count()
    workflows_count = DocWorkflow.objects.filter(doc_application__product=product).count()
    documents_count = Document.objects.filter(doc_application__product=product).count()
    invoice_lines_count = invoice_lines_qs.count()
    invoices_count = Invoice.objects.filter(invoice_applications__product=product).distinct().count()
    payments_count = Payment.objects.filter(invoice_application__product=product).count()

    can_delete = invoice_lines_count == 0
    requires_force_delete = (
        invoice_lines_count > 0
        or applications_count > 0
        or workflows_count > 0
        or documents_count > 0
        or tasks_count > 0
    )

    message: str | None = None
    if invoice_lines_count > 0:
        message = "Cannot delete product: related invoices exist."
    elif applications_count > 0 or tasks_count > 0:
        message = "Deleting this product will also delete related applications/workflows/documents and tasks."

    task_records = [
        {
            "id": task.id,
            "step": task.step,
            "name": task.name,
        }
        for task in tasks_qs[:record_limit]
    ]

    application_records = [
        {
            "id": app.id,
            "customer_name": app.customer.full_name if app.customer_id else "—",
            "status": app.status,
            "status_display": app.get_status_display(),
            "doc_date": app.doc_date.isoformat() if app.doc_date else None,
            "due_date": app.due_date.isoformat() if app.due_date else None,
            "workflow_count": app.workflow_count,
            "document_count": app.document_count,
            "invoice_line_count": app.invoice_line_count,
        }
        for app in applications_qs[:record_limit]
    ]

    invoice_line_records = []
    for line in invoice_lines_qs[:record_limit]:
        customer_name = "—"
        if line.customer_application_id and line.customer_application and line.customer_application.customer_id:
            customer_name = line.customer_application.customer.full_name
        elif line.invoice_id and line.invoice and line.invoice.customer_id:
            customer_name = line.invoice.customer.full_name

        invoice_line_records.append(
            {
                "id": line.id,
                "invoice_id": line.invoice_id,
                "invoice_no_display": line.invoice.invoice_no_display if line.invoice_id else "",
                "invoice_status": line.invoice.status if line.invoice_id else "",
                "customer_application_id": line.customer_application_id,
                "customer_name": customer_name,
                "amount": str(line.amount),
                "status": line.status,
                "status_display": line.get_status_display(),
                "payment_count": line.payment_count,
            }
        )

    return {
        "productId": product.id,
        "productCode": product.code,
        "productName": product.name,
        "canDelete": can_delete,
        "requiresForceDelete": requires_force_delete,
        "message": message,
        "relatedCounts": {
            "tasks": tasks_count,
            "applications": applications_count,
            "workflows": workflows_count,
            "documents": documents_count,
            "invoiceApplications": invoice_lines_count,
            "invoices": invoices_count,
            "payments": payments_count,
        },
        "relatedRecords": {
            "tasks": task_records,
            "applications": application_records,
            "invoiceApplications": invoice_line_records,
        },
        "relatedRecordsTruncated": {
            "tasks": tasks_count > len(task_records),
            "applications": applications_count > len(application_records),
            "invoiceApplications": invoice_lines_count > len(invoice_line_records),
        },
        "recordLimit": record_limit,
    }


def force_delete_product(product: Product) -> dict[str, int]:
    tasks_count = Task.objects.filter(product=product).count()
    applications_count = DocApplication.objects.filter(product=product).count()
    workflows_count = DocWorkflow.objects.filter(doc_application__product=product).count()
    documents_count = Document.objects.filter(doc_application__product=product).count()
    invoice_lines_qs = InvoiceApplication.objects.filter(product=product)
    invoice_lines_count = invoice_lines_qs.count()
    payments_count = Payment.objects.filter(invoice_application__product=product).count()
    affected_invoice_ids = set(invoice_lines_qs.values_list("invoice_id", flat=True))

    with transaction.atomic():
        invoice_lines_qs.delete()
        product.delete()
        _refresh_invoice_totals(affected_invoice_ids)

    return {
        "deletedProducts": 1,
        "deletedTasks": tasks_count,
        "deletedApplications": applications_count,
        "deletedWorkflows": workflows_count,
        "deletedDocuments": documents_count,
        "deletedInvoiceApplications": invoice_lines_count,
        "deletedPayments": payments_count,
        "affectedInvoices": len(affected_invoice_ids),
    }


def _refresh_invoice_totals(invoice_ids: set[int]) -> None:
    if not invoice_ids:
        return

    for invoice in Invoice.objects.filter(id__in=invoice_ids):
        invoice.total_amount = invoice.calculate_total_amount()
        invoice.status = invoice.get_invoice_status()
        invoice.save(update_fields=["total_amount", "status"])
