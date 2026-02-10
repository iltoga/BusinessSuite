from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from django.db import transaction

from customer_applications.models import DocApplication
from invoices.models.invoice import Invoice


@dataclass(frozen=True)
class InvoiceDeletePreview:
    invoice_applications_count: int
    customer_applications_count: int
    payments_count: int


def build_invoice_delete_preview(invoice: Invoice) -> InvoiceDeletePreview:
    invoice_applications_count = invoice.invoice_applications.count()
    customer_applications_count = invoice.invoice_applications.values("customer_application").distinct().count()
    payments_count = sum(inv_app.payments.count() for inv_app in invoice.invoice_applications.all())

    return InvoiceDeletePreview(
        invoice_applications_count=invoice_applications_count,
        customer_applications_count=customer_applications_count,
        payments_count=payments_count,
    )


def force_delete_invoice(invoice: Invoice, delete_customer_apps: bool) -> dict[str, int]:
    invoice_apps_count = invoice.invoice_applications.count()
    customer_apps_count = invoice.invoice_applications.values("customer_application").distinct().count()
    payments_count = sum(inv_app.payments.count() for inv_app in invoice.invoice_applications.all())

    doc_app_ids = _collect_doc_application_ids(invoice) if delete_customer_apps else set()

    with transaction.atomic():
        invoice.delete(force=True)
        if delete_customer_apps and doc_app_ids:
            DocApplication.objects.filter(id__in=doc_app_ids).delete()

    return {
        "invoice_applications_count": invoice_apps_count,
        "customer_applications_count": customer_apps_count,
        "payments_count": payments_count,
        "deleted_customer_applications": len(doc_app_ids),
    }


def bulk_delete_invoices(
    *,
    query: str | None = None,
    hide_paid: bool = False,
    delete_customer_apps: bool = False,
) -> dict[str, int]:
    queryset = Invoice.objects.search_invoices(query) if query else Invoice.objects.all()

    if hide_paid:
        queryset = queryset.exclude(status=Invoice.PAID)

    doc_app_ids: set[int] = set()
    if delete_customer_apps:
        doc_app_ids = _collect_doc_application_ids_for_invoices(queryset)

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()
        if delete_customer_apps and doc_app_ids:
            DocApplication.objects.filter(id__in=doc_app_ids).delete()

    return {"deleted_invoices": count, "deleted_customer_applications": len(doc_app_ids)}


def _collect_doc_application_ids(invoice: Invoice) -> set[int]:
    doc_app_ids: set[int] = set()
    for inv_app in invoice.invoice_applications.all():
        if inv_app.customer_application_id:
            doc_app_ids.add(inv_app.customer_application_id)
    return doc_app_ids


def _collect_doc_application_ids_for_invoices(invoices: Iterable[Invoice]) -> set[int]:
    doc_app_ids: set[int] = set()
    for invoice in invoices:
        for inv_app in invoice.invoice_applications.all():
            if inv_app.customer_application_id:
                doc_app_ids.add(inv_app.customer_application_id)
    return doc_app_ids
