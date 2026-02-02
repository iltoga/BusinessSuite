from django.db import migrations, models


def check_duplicate_passports(apps, schema_editor):
    Customer = apps.get_model("customers", "Customer")
    from django.db.models import Count

    dupes = (
        Customer.objects.filter(passport_number__isnull=False)
        .exclude(passport_number="")
        .values("passport_number")
        .annotate(ct=Count("id"))
        .filter(ct__gt=1)
    )

    if dupes.exists():
        values = ", ".join([str(d["passport_number"]) for d in dupes])
        raise RuntimeError(
            "Cannot apply migration because duplicate passport_number values exist: %s. "
            "Please remove or reconcile duplicate rows before running migrations." % values
        )


class Migration(migrations.Migration):

    dependencies = [("customers", "0011_alter_customer_email")]

    operations = [
        migrations.RunPython(check_duplicate_passports, reverse_code=migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="customer",
            constraint=models.UniqueConstraint(
                fields=["passport_number"],
                name="unique_customer_passport",
                condition=models.Q(passport_number__isnull=False) & ~models.Q(passport_number=""),
            ),
        ),
    ]
