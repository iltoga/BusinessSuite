from django.db import models
from django.conf import settings
from django.utils import timezone
from products.models import Product
from customers.models import Customer
from products.models import Product

class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query) |
            models.Q(product__code__icontains=query) |
            models.Q(product__product_type__icontains=query) |
            models.Q(customer__full_name__icontains=query) |
            models.Q(doc_date__icontains=query)
        )

class DocApplication(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('rejected', 'Rejected')
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
        last_workflow = self.workflows.last()
        return last_workflow if last_workflow else None

    # get next workflow task
    @property
    def next_task(self):
        tasks = self.product.tasks
        if self.current_workflow:
            cur_task_step_no = self.current_workflow.task.step
            # if current task is the last task, return None
            if cur_task_step_no == tasks.last().step:
                return None
            return tasks.filter(step=cur_task_step_no+1).first()
        else:
            task = tasks.first()
            return task if task else None

    class Meta:
        ordering = ['application_type']

    def __str__(self):
        return self.product.name + ' - ' + self.customer.full_name + ' - ' + f'appID_{self.pk}'

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        return super(DocApplication, self).save(*args, **kwargs)