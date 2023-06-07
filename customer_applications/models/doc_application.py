from django.db import models
from django.conf import settings
from django.utils import timezone
from products.models import Product
from customers.models import Customer

class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query) |
            models.Q(product__code__icontains=query) |
            models.Q(product__product_type__icontains=query) |
            models.Q(customer__full_name__icontains=query) |
            models.Q(doc_date__icontains=query)
        )

    def get_current_workflow(self, docapplication):
        return docapplication.workflows.order_by('-task__step').first()

class DocApplication(models.Model):
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

    application_type = models.CharField(max_length=50, choices=Product.PRODUCT_TYPE_CHOICES, default='other')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    doc_date = models.DateField()
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='created_by_doc_application')
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='updated_by_doc_application', blank=True, null=True)
    objects = DocApplicationManager()

    @property
    def is_document_collection_completed(self):
        """Returns True if all required documents are completed, False otherwise."""
        all_docs_count = self.required_documents.count()
        completed_docs_count = self.required_documents.filter(completed=True).count()
        return all_docs_count == completed_docs_count

    # check if all workflows are completed (workflow status = completed)
    @property
    def all_workflow_completed(self):
        """Returns True if all workflows are completed, False otherwise."""
        all_workflows_count = self.workflows.count()
        completed_workflows_count = self.workflows.filter(status='completed').count()
        return all_workflows_count == completed_workflows_count

    @property
    def current_workflow(self):
        current_workflow = self.__class__.objects.get_current_workflow(self)
        return current_workflow if current_workflow else None

    # get next workflow task
    @property
    def next_task(self):
        tasks = self.product.tasks.order_by('step')

        # Get the last workflow associated with this application.
        current_workflow = self.current_workflow

        if current_workflow and current_workflow.status == self.STATUS_COMPLETED:
            # If there is a last workflow and it's completed, get the next task.
            next_task_step = current_workflow.task.step + 1
            next_task = tasks.filter(step=next_task_step).first()
            return next_task

        else:
            # If there is no last workflow or it's not completed, return the task of the last workflow
            # or the first task if there is no workflow.
            return current_workflow.task if current_workflow else tasks.first()

    @property
    def is_application_completed(self):
        # get last workflow and check if it is completed
        current_workflow = self.current_workflow
        if current_workflow:
            return current_workflow.is_workflow_completed
        return False

    @property
    def has_next_task(self):
        if self.is_application_completed:
            return False
        if not self.is_document_collection_completed:
            return False
        if self.current_workflow and self.current_workflow.status != self.STATUS_COMPLETED:
            return False
        next_task = self.next_task
        if next_task and next_task.step:
            return True
        return False


    class Meta:
        ordering = ['application_type']

    def __str__(self):
        return self.product.name + ' - ' + self.customer.full_name + f' #{self.pk}'

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super(DocApplication, self).save(*args, **kwargs)