from django.db import models
from django.conf import settings
from django.utils import timezone
from products.models import Task
from .doc_application import DocApplication

class DocWorkflow(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
    ]

    doc_application = models.ForeignKey(DocApplication, related_name='workflows', on_delete=models.CASCADE)
    task = models.OneToOneField(Task, on_delete=models.CASCADE)
    application_date = models.DateField(auto_now_add=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_workflow')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_workflow', blank=True, null=True)

    class Meta:
        ordering = ['application_date']

    def __str__(self):
        return self.task.name

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super(DocWorkflow, self).save(*args, **kwargs)
