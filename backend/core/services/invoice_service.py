from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Iterable

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from customer_applications.models import DocApplication
from invoices.models.invoice import Invoice, InvoiceApplication
from payments.models import Payment


@dataclass(frozen=True)
class InvoiceApplicationPayload:
    customer_application_id: int
    amount: Decimal
    invoice_application_id: int | None = None


def _build_payloads(raw_items: Iterable[dict]) -> list[InvoiceApplicationPayload]:
    payloads: list[InvoiceApplicationPayload] = []
    for item in raw_items:
        customer_application = item.get("customer_application")
        customer_application_id = (
            customer_application.id if hasattr(customer_application, "id") else customer_application
        )
        payloads.append(
            InvoiceApplicationPayload(
                invoice_application_id=item.get("id"),
                customer_application_id=customer_application_id,
                amount=Decimal(str(item.get("amount"))),
            )
        )
    return payloads


def _validate_application_ids(payloads: list[InvoiceApplicationPayload]) -> None:
    ids = [payload.customer_application_id for payload in payloads]
    if len(ids) != len(set(ids)):
        raise ValidationError("Each customer application can only appear once in an invoice.")


def _validate_application_availability(
    *,
    payloads: list[InvoiceApplicationPayload],
    current_invoice: Invoice | None = None,
) -> None:
    application_ids = [payload.customer_application_id for payload in payloads]
    existing = InvoiceApplication.objects.filter(customer_application_id__in=application_ids)
    if current_invoice:
        existing = existing.exclude(invoice=current_invoice)
    if existing.exists():
        raise ValidationError({"invoice_applications": ["One or more customer applications are already invoiced."]})


def create_invoice(*, data: dict, user) -> Invoice:
    payloads = _build_payloads(data.pop("invoice_applications", []))
    _validate_application_ids(payloads)
    _validate_application_availability(payloads=payloads)

    invoice_date = data.get("invoice_date")
    if isinstance(invoice_date, str):
        try:
            invoice_date = timezone.datetime.fromisoformat(invoice_date).date()
        except Exception:
            invoice_date = None
    year = invoice_date.year if invoice_date else timezone.now().year

    # Always assign the next available invoice number for the year
    data["invoice_no"] = Invoice.get_next_invoice_no_for_year(year)

    # Attempt creation; handle possible race conditions on invoice_no uniqueness by retrying
    attempts = 0
    max_attempts = 3
    while True:
        try:
            with transaction.atomic():
                invoice = Invoice.objects.create(created_by=user, **data)
                _sync_invoice_applications(invoice=invoice, payloads=payloads, user=user)
                invoice.save()
                return invoice
        except Exception as exc:
            # Handle duplicate invoice_no integrity errors specifically
            from django.db import IntegrityError

            # detect unique constraint violation on invoice_no
            if isinstance(exc, IntegrityError) and "invoices_invoice_invoice_no_key" in str(exc):
                attempts += 1
                if attempts >= max_attempts:
                    raise ValidationError({"invoice_no": ["Invoice number already exists."]})

                # Remove provided invoice_no (if any) so Invoice.save() will generate next available
                data.pop("invoice_no", None)

                # If invoice_date present, compute next invoice number for that year and set it explicitly
                try:
                    invoice_date = data.get("invoice_date")
                    if isinstance(invoice_date, str):
                        invoice_date = timezone.datetime.fromisoformat(invoice_date).date()
                    year = invoice_date.year if invoice_date else timezone.now().year
                except Exception:
                    year = timezone.now().year

                data["invoice_no"] = Invoice.get_next_invoice_no_for_year(year)
                # Try again
                continue
            # re-raise other exceptions
            raise


def update_invoice(*, invoice: Invoice, data: dict, user) -> Invoice:
    payloads = _build_payloads(data.pop("invoice_applications", []))
    _validate_application_ids(payloads)
    _validate_application_availability(payloads=payloads, current_invoice=invoice)

    if data.get("customer") and data["customer"].id != invoice.customer_id:
        raise ValidationError("Customer cannot be changed for an existing invoice.")

    with transaction.atomic():
        for attr, value in data.items():
            setattr(invoice, attr, value)
        invoice.updated_by = user
        invoice.save()

        _sync_invoice_applications(invoice=invoice, payloads=payloads, user=user)
        invoice.save()
        return invoice


def _sync_invoice_applications(*, invoice: Invoice, payloads: list[InvoiceApplicationPayload], user) -> None:
    existing = {item.id: item for item in invoice.invoice_applications.all()}
    seen_ids: set[int] = set()

    for payload in payloads:
        if payload.invoice_application_id and payload.invoice_application_id in existing:
            invoice_app = existing[payload.invoice_application_id]
            invoice_app.customer_application_id = payload.customer_application_id
            invoice_app.amount = payload.amount
            invoice_app.save()
            seen_ids.add(invoice_app.id)
        else:
            invoice_app = InvoiceApplication.objects.create(
                invoice=invoice,
                customer_application_id=payload.customer_application_id,
                amount=payload.amount,
            )
            seen_ids.add(invoice_app.id)

    to_delete = [item_id for item_id in existing.keys() if item_id not in seen_ids]
    if to_delete:
        InvoiceApplication.objects.filter(id__in=to_delete, invoice=invoice).delete()


def mark_invoice_as_paid(*, invoice: Invoice, payment_type: str, payment_date: date | None, user) -> list[Payment]:
    payment_date = payment_date or timezone.now().date()
    created: list[Payment] = []

    with transaction.atomic():
        unpaid_apps = [app for app in invoice.invoice_applications.all() if app.due_amount > 0]
        if not unpaid_apps:
            return created

        for invoice_app in unpaid_apps:
            payment = create_payment(
                invoice_application=invoice_app,
                amount=Decimal(str(invoice_app.due_amount)),
                payment_type=payment_type,
                payment_date=payment_date,
                user=user,
            )
            created.append(payment)
    return created


def validate_payment_amount(invoice_application: InvoiceApplication, amount: Decimal, payment: Payment | None = None):
    available = Decimal(str(invoice_application.due_amount))
    if payment:
        available += Decimal(str(payment.amount))

    if amount > available:
        raise ValidationError("The payment amount exceeds the due amount.")


def create_payment(
    *,
    invoice_application: InvoiceApplication,
    amount: Decimal,
    payment_type: str,
    payment_date: date | None,
    user,
    notes: str | None = None,
) -> Payment:
    validate_payment_amount(invoice_application, amount)
    payment_date = payment_date or timezone.now().date()

    return Payment.objects.create(
        invoice_application=invoice_application,
        from_customer=invoice_application.invoice.customer,
        payment_date=payment_date,
        payment_type=payment_type,
        amount=amount,
        notes=notes or "",
        created_by=user,
    )


def update_payment(
    *, payment: Payment, amount: Decimal, payment_type: str, payment_date: date | None, user, notes=None
):
    validate_payment_amount(payment.invoice_application, amount, payment)
    payment.amount = amount
    payment.payment_type = payment_type
    payment.payment_date = payment_date or payment.payment_date
    payment.notes = notes or payment.notes
    payment.updated_by = user
    payment.save()
    return payment
