from django.db import migrations

def generate_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    group_names = ['Administrators', 'Editors', 'Viewers', 'Creators', 'Deleters', 'DocumentViewers', 'DocumentUploaders', 'PowerUsers']
    for group_name in group_names:
        Group.objects.create(name=group_name)

class Migration(migrations.Migration):
    dependencies = [
        # Also add any other migrations that introduce new models here
        ('core', '0001_initial'),
        # ('customers', '0001_initial'),
        # ('products', '0001_initial'),
        # ('invoices', '0001_initial'),
        # ('transactions', '0001_initial'),
        # ('customer_applications', '0001_initial'),
    ]
    operations = [
        migrations.RunPython(generate_groups),
    ]
