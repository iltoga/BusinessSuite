from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("products", "0002_product_created_at_product_created_by_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="task",
            name="add_task_to_calendar",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
