"""Create the web push subscription table for browser notification delivery.

The migration adds the subscription storage used by the push notification
workflow to persist endpoint and key material.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0012_asyncjob"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="WebPushSubscription",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(max_length=512, unique=True)),
                ("device_label", models.CharField(blank=True, default="", max_length=255)),
                ("user_agent", models.TextField(blank=True, default="")),
                ("is_active", models.BooleanField(default=True)),
                ("last_error", models.TextField(blank=True, default="")),
                ("last_seen_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="web_push_subscriptions",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-updated_at"],
            },
        ),
        migrations.AddIndex(
            model_name="webpushsubscription",
            index=models.Index(fields=["user", "is_active"], name="pushsub_user_active_idx"),
        ),
    ]
