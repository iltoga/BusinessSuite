from django.db import models
from django.conf import settings
from django.forms import ValidationError
from django.utils import timezone
from products.models import Task
from .doc_application import DocApplication

class DocWorkflowManager(models.Manager):
    def search_doc_workflows(self, query):
        return self.filter(
            models.Q(task__name__icontains=query) |
            models.Q(task__code__icontains=query) |
            models.Q(task__description__icontains=query) |
            models.Q(start_date__icontains=query) |
            models.Q(due_date__icontains=query) |
            models.Q(status__icontains=query) |
            models.Q(notes__icontains=query)
        )

class DocWorkflow(models.Model):
    STATUS_COMPLETED = 'completed'
    STATUS_REJECTED = 'rejected'
    STATUS_PENDING = 'pending'
    STATUS_PROCESSING = 'processing'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Pending'),
        (STATUS_PROCESSING, 'Processing'),
        (STATUS_COMPLETED, 'Completed'),
        (STATUS_REJECTED, 'Rejected')
    ]

    doc_application = models.ForeignKey(DocApplication, related_name='workflows', on_delete=models.CASCADE)
    task = models.OneToOneField(Task, on_delete=models.CASCADE)
    start_date = models.DateField()
    completion_date = models.DateField(blank=True, null=True)
    due_date = models.DateField()
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_workflow')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_workflow', blank=True, null=True)

    class Meta:
        ordering = ['start_date']

    @property
    def is_completed(self):
        return self.status == 'completed'

    def __str__(self):
        return self.task.name

    def save(self, *args, **kwargs):
        if not self.id:
            self.created_at = timezone.now()
        self.updated_at = timezone.now()
        return super(DocWorkflow, self).save(*args, **kwargs)
