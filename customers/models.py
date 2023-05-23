from django.db import models

from django.db import models, connection
from django.db.models.signals import post_migrate, pre_save, post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from django import forms
from core.utils.form_validators import validate_phone_number, validate_birthdate, validate_document_id, validateEmail, validateDocumentType, validateExpirationDate

DOCUMENT_TYPE_CHOICES = [
    ('', '---------'),
    ('Passport', 'Passport'),
    ('KTP', 'KTP'),
    ('SIM', 'SIM'),
]

TITLES_CHOICES = [
    ('', '---------'),
    ('Mr', 'Mr'),
    ('Mrs', 'Mrs'),
    ('Ms', 'Ms'),
    ('Miss', 'Miss'),
    ('Dr', 'Dr'),
    ('Prof', 'Prof'),
]

NOTIFY_BY_CHOICES = [
    ('', '---------'),
    ('Email', 'Email'),
    ('SMS', 'SMS'),
    ('WhatsApp', 'WhatsApp'),
    ('Telegram', 'Telegram'),
    ('Telephone', 'Telephone'),
]

class CustomerManager(models.Manager):
    def search_customers(self, query):
        return self.filter(
            models.Q(full_name__icontains=query) |
            models.Q(document_id__icontains=query) |
            models.Q(email__icontains=query)
        )
    def fulltext_search_customers(self, query):
        with connection.cursor() as cursor:
            cursor.execute(f'''
                SELECT id, full_name, document_id
                FROM customer_fts
                WHERE customer_fts MATCH '{query}*'
                ORDER BY rank;
            ''')
            return [Customer.objects.get(id=row[0]) for row in cursor.fetchall()]

class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=50)
    email = models.EmailField(max_length=50, unique=True, blank=True, null=True, validators=[validateEmail])
    telephone = models.CharField(max_length=50, unique=True, blank=True, null=True, validators=[validate_phone_number])
    title = models.CharField(choices=TITLES_CHOICES, max_length=50)
    citizenship = models.CharField(max_length=100)
    birthdate = models.DateField(validators=[validate_birthdate])
    address_bali = models.TextField(blank=True, null=True)
    address_abroad = models.TextField(blank=True, null=True)
    document_type = models.CharField(choices=DOCUMENT_TYPE_CHOICES, max_length=50)
    document_id = models.CharField(max_length=50, unique=True, validators=[validate_document_id])
    expiration_date = models.DateField(validators=[validateExpirationDate])
    notify_expiration = models.BooleanField(default=True)
    notify_by = models.CharField(choices=NOTIFY_BY_CHOICES, max_length=50, blank=True, null=True)
    notification_sent = models.BooleanField(default=False)
    objects = CustomerManager()

    class Meta:
        ordering = ['full_name']
        unique_together = ('full_name', 'birthdate',)

    def __str__(self):
        return self.full_name

    # clean method is where you can add custom validations for your model
    # note: it can be used here or in the form class
    def clean(self):
        if self.notify_expiration and not self.notify_by:
            raise ValidationError('If notify expiration is true, notify by is mandatory.')

    def delete(self, *args, **kwargs):
        with connection.cursor() as cursor:
            cursor.execute('''
                DELETE FROM customer_fts WHERE id = %s;
            ''', [self.id])
        super().delete(*args, **kwargs)

# Create an FTS table for Customers after each migration
@receiver(post_migrate)
def create_fts_table(sender, **kwargs):
    with connection.cursor() as cursor:
        cursor.execute('''
            CREATE VIRTUAL TABLE IF NOT EXISTS customer_fts
            USING fts5(id UNINDEXED, full_name, document_id);
        ''')

# Before a customer is saved into the Customers table,
# delete the old matching entry in the FTS table
@receiver(pre_save, sender=Customer)
def customer_before_save(sender, instance, **kwargs):
    with connection.cursor() as cursor:
        cursor.execute('''
            DELETE FROM customer_fts WHERE id = %s;
        ''', [instance.id])

# After a customer is saved into the Customers table,
# insert a matching entry into the FTS table
@receiver(post_save, sender=Customer)
def customer_after_save(sender, instance, **kwargs):
    with connection.cursor() as cursor:
        cursor.execute('''
            INSERT INTO customer_fts (id, full_name, document_id)
            VALUES (%s, %s, %s);
        ''', [instance.id, instance.full_name, instance.document_id])