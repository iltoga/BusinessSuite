from django.db import models

class Customer(models.Model):
    id = models.AutoField(primary_key=True)
    full_name = models.CharField(max_length=200)
    email = models.EmailField(max_length=200, unique=True)
    telephone = models.CharField(max_length=50)
    title = models.CharField(max_length=50)
    citizenship = models.CharField(max_length=100)
    birthdate = models.DateField()
    address_bali = models.TextField()
    address_abroad = models.TextField()
    document_type = models.CharField(max_length=50)
    document_id = models.CharField(max_length=200)
    expiration_date = models.DateField()
    notify_expiration = models.BooleanField(default=True)
    notify_by = models.CharField(max_length=50)
    notification_sent = models.BooleanField(default=False)

    def __str__(self):
        return self.full_name
