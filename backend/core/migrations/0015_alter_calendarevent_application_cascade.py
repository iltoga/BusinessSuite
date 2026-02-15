from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0014_calendarevent"),
    ]

    operations = [
        migrations.AlterField(
            model_name="calendarevent",
            name="application",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="calendar_events",
                to="customer_applications.docapplication",
            ),
        ),
    ]
