from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("products", "0006_documenttype_validation_rule_ai_negative_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="validation_prompt",
            field=models.TextField(blank=True),
        ),
    ]
