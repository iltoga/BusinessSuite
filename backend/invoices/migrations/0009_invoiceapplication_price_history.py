from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


def backfill_invoice_price_history(apps, schema_editor) -> None:
    InvoiceApplication = apps.get_model("invoices", "InvoiceApplication")
    Invoice = apps.get_model("invoices", "Invoice")
    ProductPriceHistory = apps.get_model("products", "ProductPriceHistory")
    db = schema_editor.connection.alias

    histories_by_product: dict[int, list] = {}
    for history in ProductPriceHistory.objects.using(db).order_by("product_id", "-effective_from", "-id"):
        histories_by_product.setdefault(history.product_id, []).append(history)

    for product_id, histories in histories_by_product.items():
        for history in histories:
            start = history.effective_from.date() if history.effective_from else None
            end = history.effective_to.date() if history.effective_to else None
            if not start:
                continue
            qs = InvoiceApplication.objects.using(db).filter(
                price_history__isnull=True,
                product_id=product_id,
                invoice__invoice_date__gte=start,
            )
            if end:
                qs = qs.filter(invoice__invoice_date__lt=end)
            qs.update(price_history_id=history.id)

    remaining = InvoiceApplication.objects.using(db).filter(price_history__isnull=True, product_id__isnull=False)
    remaining_product_ids = list(remaining.values_list("product_id", flat=True).distinct())
    for product_id in remaining_product_ids:
        histories = histories_by_product.get(product_id)
        if not histories:
            continue

        histories_asc = sorted(
            histories,
            key=lambda history: (
                history.effective_from or history.created_at,
                history.id,
            ),
        )
        invoice_dates = dict(
            Invoice.objects.using(db)
            .filter(invoice_applications__product_id=product_id, invoice_applications__price_history__isnull=True)
            .values_list("invoice_applications__id", "invoice_date")
        )

        for invoice_application_id in remaining.filter(product_id=product_id).values_list("id", flat=True):
            invoice_date = invoice_dates.get(invoice_application_id)
            chosen = histories_asc[0]
            if invoice_date:
                for history in histories_asc:
                    start = history.effective_from.date() if history.effective_from else None
                    if start and start <= invoice_date:
                        chosen = history
                        continue
                    break

            InvoiceApplication.objects.using(db).filter(id=invoice_application_id).update(price_history_id=chosen.id)


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0016_product_price_history"),
        ("invoices", "0008_invoicedocumentjob_inv_doc_guard_lookup_idx_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceapplication",
            name="price_history",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoice_applications",
                to="products.productpricehistory",
            ),
        ),
        migrations.RunPython(backfill_invoice_price_history, migrations.RunPython.noop),
    ]
