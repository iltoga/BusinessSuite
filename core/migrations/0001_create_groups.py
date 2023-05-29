from django.db import migrations

def generate_groups(apps, schema_editor):
    Group = apps.get_model('auth', 'Group')
    group_names = ['Administrators', 'Editors', 'Viewers', 'Creators', 'Deleters', 'DocumentViewers', 'DocumentUploaders', 'PowerUsers']
    for group_name in group_names:
        Group.objects.create(name=group_name)

class Migration(migrations.Migration):
    operations = [
        migrations.RunPython(generate_groups),
    ]
