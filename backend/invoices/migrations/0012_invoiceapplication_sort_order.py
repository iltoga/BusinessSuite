from django.db import migrations, models


def backfill_invoice_application_sort_order(apps, schema_editor):
    InvoiceApplication = apps.get_model("invoices", "InvoiceApplication")
    invoice_ids = (
        InvoiceApplication.objects.order_by()
        .values_list("invoice_id", flat=True)
        .distinct()
    )

    for invoice_id in invoice_ids:
        rows = list(
            InvoiceApplication.objects.filter(invoice_id=invoice_id)
            .order_by("-id")
            .only("id", "sort_order")
        )
        for index, row in enumerate(rows):
            row.sort_order = index
        if rows:
            InvoiceApplication.objects.bulk_update(rows, ["sort_order"])


class Migration(migrations.Migration):
    dependencies = [
        ("invoices", "0011_invoiceapplication_quantity_notes"),
    ]

    operations = [
        migrations.AddField(
            model_name="invoiceapplication",
            name="sort_order",
            field=models.PositiveIntegerField(db_index=True, default=0),
        ),
        migrations.RunPython(
            backfill_invoice_application_sort_order,
            migrations.RunPython.noop,
        ),
        migrations.AlterModelOptions(
            name="invoiceapplication",
            options={"ordering": ("sort_order", "id")},
        ),
        migrations.AddIndex(
            model_name="invoiceapplication",
            index=models.Index(fields=["invoice", "sort_order"], name="invoiceapp_inv_sort_idx"),
        ),
    ]
