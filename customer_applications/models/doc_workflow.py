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
    #TODO: remove this as it is a duplicate of the DocApplication model
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
    task = models.ForeignKey(Task, related_name='doc_workflows', on_delete=models.CASCADE)
    start_date = models.DateField(db_index=True)
    completion_date = models.DateField(blank=True, null=True, db_index=True)
    due_date = models.DateField(db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default='pending', db_index=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_workflow')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_workflow', blank=True, null=True)

    class Meta:
        ordering = ['created_at']

    @property
    def is_completed(self):
        return self.status == 'completed'

    @property
    def is_current_step(self):
        next_step = self.doc_application.workflows.filter(task__step=self.task.step+1).first()
        return next_step is None

    @property
    def is_workflow_completed(self):
        return self.task.last_step and self.is_completed

    @property
    def is_notification_date_reached(self):
        if not self.due_date:
            return False
        notify_days_before = self.task.notify_days_before or 0
        return self.due_date - timezone.now().date() <= timezone.timedelta(days=notify_days_before)

    @property
    def is_overdue(self):
        if not self.due_date:
            return False
        return self.due_date < timezone.now().date()

    @property
    def updated_or_created_at(self):
        return self.updated_at or self.created_at

    @property
    def updated_or_created_by(self):
        return self.updated_by or self.created_by


    def __str__(self):
        return self.task.name

    def save(self, *args, **kwargs):
        if not self.id:
            self.created_at = timezone.now()
        self.updated_at = timezone.now()
        if self.status == 'completed':
            self.completion_date = timezone.now().date()
        else:
            self.completion_date = None

        updated_doc_workflow = super(DocWorkflow, self).save(*args, **kwargs)
        # save the doc_application model to update the due_date field
        self.doc_application.save()

        return updated_doc_workflow
