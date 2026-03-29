"""Refactor invoice application product relationships and references."""

import django.db.models.deletion
from django.db import migrations, models


def backfill_invoice_application_product(apps, schema_editor):
    InvoiceApplication = apps.get_model("invoices", "InvoiceApplication")
    missing_ids = []

    queryset = InvoiceApplication.objects.select_related("customer_application").filter(product_id__isnull=True)
    for invoice_application in queryset.iterator():
        if invoice_application.customer_application_id:
            invoice_application.product_id = invoice_application.customer_application.product_id
            invoice_application.save(update_fields=["product"])
        else:
            missing_ids.append(invoice_application.id)

    if missing_ids:
        raise RuntimeError(
            "Cannot backfill invoices.InvoiceApplication.product for rows without customer_application. "
            f"InvoiceApplication ids: {missing_ids[:20]}"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0013_product_uses_customer_app_workflow"),
        ("customer_applications", "0016_document_thumbnail"),
        ("invoices", "0006_invoicedownloadjob"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceapplication",
            name="product",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoice_applications",
                to="products.product",
            ),
        ),
        migrations.AlterField(
            model_name="invoiceapplication",
            name="customer_application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="invoice_applications",
                to="customer_applications.docapplication",
            ),
        ),
        migrations.RunPython(backfill_invoice_application_product, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="invoiceapplication",
            name="product",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="invoice_applications",
                to="products.product",
            ),
        ),
        migrations.AddIndex(
            model_name="invoiceapplication",
            index=models.Index(fields=["invoice", "product"], name="invoiceapp_inv_prod_idx"),
        ),
    ]
