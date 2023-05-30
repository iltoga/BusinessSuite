from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType


class Command(BaseCommand):
    help = 'Create custom groups and permissions'

    def handle(self, *args, **options):
        self.create_groups_and_permissions()

    def create_groups_and_permissions(self):
        self.generate_administrators()
        self.generate_editors()
        self.generate_viewers()
        self.generate_creators()
        self.generate_deleters()
        self.generate_open_document()
        self.generate_upload_document()
        self.generate_power_users()
        self.generate_auditors()
        self.generate_administration_office()

    def generate_administrators(self):
        group, created = Group.objects.get_or_create(name='Administrators')
        if created:
            permissions = Permission.objects.all()
            group.permissions.set(permissions)
            print('Administrators group created')

    def generate_administration_office(self):
        """
        This group is for the Administration Office staff:
        they can view and edit customers, invoices, and documents, but not products or transactions.
        """
        group, created = Group.objects.get_or_create(name='Administration Office')
        if created:
            permissions = Permission.objects.filter(codename__in=['view_customer', 'change_customer', 'add_customer' 'view_invoice', 'change_invoice', 'add_invoice', 'view_docapplication', 'change_docapplication', 'add_docapplication', 'view_docworkflow', 'change_docworkflow', 'add_docworkflow', 'view_requireddocument', 'change_requireddocument', 'add_requireddocument'])
            group.permissions.set(permissions)
            print('Administration Office group created')

    def generate_editors(self):
        group, created = Group.objects.get_or_create(name='Editors')
        if created:
            permissions = Permission.objects.filter(codename__in=['view_customer', 'change_customer', 'view_product', 'change_product', 'view_invoice', 'change_invoice', 'view_transaction', 'change_transaction', 'view_docworkflow', 'change_docworkflow', 'change_requireddocument'])
            group.permissions.set(permissions)
            print('Editors group created')

    def generate_viewers(self):
        group, created = Group.objects.get_or_create(name='Viewers')
        if created:
            permissions = Permission.objects.filter(codename__in=['view_customer', 'view_product', 'view_invoice', 'view_transaction', 'view_docapplication', 'view_docworkflow', 'view_requireddocument'])
            group.permissions.set(permissions)
            print('Viewers group created')

    def generate_creators(self):
        group, created = Group.objects.get_or_create(name='Creators')
        if created:
            permissions = Permission.objects.filter(codename__in=['add_customer', 'add_product', 'add_invoice', 'add_transaction', 'add_docapplication', 'add_docworkflow', 'add_requireddocument'])
            group.permissions.set(permissions)
            print('Creators group created')

    def generate_deleters(self):
        group, created = Group.objects.get_or_create(name='Deleters')
        if created:
            permissions = Permission.objects.filter(codename__in=['delete_customer', 'delete_product', 'delete_invoice', 'delete_transaction', 'delete_docapplication', 'delete_docworkflow', 'delete_requireddocument'])
            group.permissions.set(permissions)
            print('Deleters group created')

    def generate_open_document(self):
        required_document_ct = ContentType.objects.get(app_label='customer_applications', model='requireddocument')
        permission, _ = Permission.objects.get_or_create(
            codename='open_document',
            name='Can open or download a document',
            content_type=required_document_ct
        )
        group, created = Group.objects.get_or_create(name='DocumentViewers')
        if created:
            group.permissions.add(permission)
            print('DocumentViewers group created')

    def generate_upload_document(self):
        required_document_ct = ContentType.objects.get(app_label='customer_applications', model='requireddocument')
        permission, _ = Permission.objects.get_or_create(
            codename='upload_document',
            name='Can upload a document to the server',
            content_type=required_document_ct
        )
        group, created = Group.objects.get_or_create(name='DocumentUploaders')
        if created:
            group.permissions.add(permission)
            print('DocumentUploaders group created')

    def generate_auditors(self):
        group, group_created = Group.objects.get_or_create(name='Auditors')
        for app_label in (
            'customers',
            'customer_applications',
            'products',
            'invoices',
            'transactions',
            ):
            for model in ContentType.objects.filter(app_label=app_label):
                permission, perm_created = Permission.objects.get_or_create(
                    codename='can_audit',
                    name=f'Can audit {model}',
                    content_type=model,
                )
                if perm_created:
                    group.permissions.add(permission)
        if group_created:
            print('Auditors group created')

    def generate_power_users(self):
        group, created = Group.objects.get_or_create(name='PowerUsers')
        if created:
            other_group_names = ['Editors', 'Viewers', 'Creators', 'Deleters', 'DocumentViewers', 'DocumentUploaders']
            permissions = Permission.objects.none()

            for other_group_name in other_group_names:
                other_group = Group.objects.get(name=other_group_name)
                permissions = permissions | other_group.permissions.all()

            group.permissions.set(permissions)
            print('PowerUsers group created')

