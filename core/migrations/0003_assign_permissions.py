from django.db import migrations
from django.contrib.auth.models import Group, Permission

def generate_administrators(apps, schema_editor):
    # Create a new group
    group = Group.objects.get(name='Administrators')

    # Add permissions to the group
    permissions = Permission.objects.all()
    for permission in permissions:
        group.permissions.add(permission)

# generate a group to edit all models
def generate_editors(apps, schema_editor):
    # Create a new group
    group = Group.objects.get(name='Editors')

    # Add permissions to the group
    permissions = Permission.objects.filter(codename__in=['view_customer', 'change_customer', 'view_product', 'change_product', 'view_invoice', 'change_invoice', 'view_transaction', 'change_transaction', 'view_docworkflow', 'change_docworkflow', 'change_requireddocument'])
    for permission in permissions:
        group.permissions.add(permission)

# generate a group to view all models
def generate_viewers(apps, schema_editor):
    # Create a new group
    group = Group.objects.get(name='Viewers')

    # Add permissions to the group
    permissions = Permission.objects.filter(codename__in=['view_customer', 'view_product', 'view_invoice', 'view_transaction', 'view_docapplication', 'view_docworkflow', 'view_requireddocument'])
    for permission in permissions:
        group.permissions.add(permission)

# generate a group to create all models
def generate_creators(apps, schema_editor):
    # Create a new group
    group = Group.objects.get(name='Creators')

    # Add permissions to the group
    permissions = Permission.objects.filter(codename__in=['add_customer', 'add_product', 'add_invoice', 'add_transaction', 'add_docapplication', 'add_docworkflow', 'add_requireddocument'])
    for permission in permissions:
        group.permissions.add(permission)

# generate a group to delete all models
def generate_deleters(apps, schema_editor):
    # Create a new group
    group = Group.objects.get(name='Deleters')

    # Add permissions to the group
    permissions = Permission.objects.filter(codename__in=['delete_customer', 'delete_product', 'delete_invoice', 'delete_transaction', 'delete_docapplication', 'delete_docworkflow', 'delete_requireddocument'])
    for permission in permissions:
        group.permissions.add(permission)

# create a new permission to open or download a document
def generate_open_document(apps, schema_editor):
    # Get the content type for the RequiredDocument model
    ContentType = apps.get_model('contenttypes', 'ContentType')
    required_document_ct = ContentType.objects.get(app_label='customer_applications', model='requireddocument')

    # Create a new permission
    permission = Permission.objects.create(
        codename='open_document',
        name='Can open or download a document',
        content_type=required_document_ct
    )
    group = Group.objects.create(name='DocumentViewers')
    group.permissions.add(permission)

# create a new permission to open or download a document
def generate_upload_document(apps, schema_editor):
    # Get the content type for the RequiredDocument model
    ContentType = apps.get_model('contenttypes', 'ContentType')
    required_document_ct = ContentType.objects.get(app_label='customer_applications', model='requireddocument')

    # Create a new permission
    permission = Permission.objects.create(
        codename='upload_document',
        name='Can upload a document to the server',
        content_type=required_document_ct
    )
    group = Group.objects.create(name='DocumentUploaders')
    group.permissions.add(permission)

def generate_power_users(apps, schema_editor):
    group = Group.objects.get(name='PowerUsers')
    # Get the other groups
    editors = Group.objects.get(name='Editors')
    viewers = Group.objects.get(name='Viewers')
    creators = Group.objects.get(name='Creators')
    deleters = Group.objects.get(name='Deleters')
    document_viewers = Group.objects.get(name='DocumentViewers')
    document_uploaders = Group.objects.get(name='DocumentUploaders')

    # Add all the permissions from those groups to PowerUsers
    for other_group in [editors, viewers, creators, deleters, document_viewers, document_uploaders]:
        for permission in other_group.permissions.all():
            group.permissions.add(permission)

class Migration(migrations.Migration):
    dependencies = [
        # Add the previous migration here
        ('core', '0002_create_groups'),
    ]

    operations = [
        migrations.RunPython(generate_administrators),
        migrations.RunPython(generate_editors),
        migrations.RunPython(generate_viewers),
        migrations.RunPython(generate_creators),
        migrations.RunPython(generate_deleters),
        migrations.RunPython(generate_open_document),
        migrations.RunPython(generate_upload_document),
        migrations.RunPython(generate_power_users),
    ]
