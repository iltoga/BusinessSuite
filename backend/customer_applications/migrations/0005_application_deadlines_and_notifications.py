from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("customer_applications", "0004_docapplication_customer_status_index"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="docapplication",
            name="add_deadlines_to_calendar",
            field=models.BooleanField(default=True),
        ),
        migrations.CreateModel(
            name="WorkflowNotification",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("status", models.CharField(choices=[("pending", "Pending"), ("sent", "Sent"), ("failed", "Failed"), ("cancelled", "Cancelled")], db_index=True, default="pending", max_length=20)),
                ("channel", models.CharField(db_index=True, default="email", max_length=20)),
                ("subject", models.CharField(max_length=255)),
                ("body", models.TextField()),
                ("recipient", models.EmailField(max_length=254)),
                ("scheduled_for", models.DateField(blank=True, null=True)),
                ("sent_at", models.DateTimeField(blank=True, null=True)),
                ("provider_message", models.TextField(blank=True)),
                ("external_reference", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ("doc_application", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="notifications", to="customer_applications.docapplication")),
                ("doc_workflow", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="notifications", to="customer_applications.docworkflow")),
            ],
            options={"ordering": ["-id"]},
        ),
    ]
