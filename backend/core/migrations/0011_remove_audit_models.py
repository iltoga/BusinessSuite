# Generated migration to remove legacy audit models (CRUDEvent, LoginEvent, RequestEvent)
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0010_alter_usersettings_options_crudevent_loginevent_and_more"),
    ]

    operations = [
        migrations.DeleteModel(name="CRUDEvent"),
        migrations.DeleteModel(name="LoginEvent"),
        migrations.DeleteModel(name="RequestEvent"),
    ]
