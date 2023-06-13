from django.conf import settings
from django.db import models
from django.utils import timezone

from core.utils.dateutils import calculate_due_date
from customers.models import Customer
from products.models import Product


class DocApplicationManager(models.Manager):
    def search_doc_applications(self, query):
        return self.filter(
            models.Q(product__name__icontains=query)
            | models.Q(product__code__icontains=query)
            | models.Q(product__product_type__icontains=query)
            | models.Q(customer__full_name__icontains=query)
            | models.Q(doc_date__icontains=query)
        )


class DocApplication(models.Model):
    STATUS_COMPLETED = "completed"
    STATUS_REJECTED = "rejected"
    STATUS_PENDING = "pending"
    STATUS_PROCESSING = "processing"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PROCESSING, "Processing"),
        (STATUS_COMPLETED, "Completed"),
        (STATUS_REJECTED, "Rejected"),
    ]

    application_type = models.CharField(
        max_length=50,
        choices=Product.PRODUCT_TYPE_CHOICES,
        default="other",
        db_index=True,
    )

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    doc_date = models.DateField(db_index=True)
    due_date = models.DateField(blank=True, null=True, db_index=True)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_by_doc_application",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_doc_application",
        blank=True,
        null=True,
    )
    objects = DocApplicationManager()

    class Meta:
        ordering = ["-id"]

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
        completed_workflows_count = self.workflows.filter(status="completed").count()
        return all_workflows_count == completed_workflows_count

    @property
    def current_workflow(self):
        current_workflow = self.workflows.order_by("-task__step").first()
        return current_workflow if current_workflow else None

    # get next workflow task
    @property
    def next_task(self):
        tasks = self.product.tasks.order_by("step")

        # Get the last workflow associated with this application.
        current_workflow = self.current_workflow

        if current_workflow and current_workflow.status == self.STATUS_COMPLETED:
            # If there is a last workflow and it's completed, get the next task.
            next_task_step = current_workflow.task.step + 1
            next_task = tasks.filter(step=next_task_step).first()
            return next_task

        else:
            # If there is no last workflow or it's not completed, return the task of
            # the last workflow or the first task if there is no workflow.
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

    def __str__(self):
        return self.product.name + " - " + self.customer.full_name + f" #{self.pk}"

    def save(self, *args, **kwargs):
        self.updated_at = timezone.now()
        self.due_date = self.calculate_application_due_date()
        return super(DocApplication, self).save(*args, **kwargs)

    def calculate_application_due_date(self):
        """
        Calculates the due date of a DocApplication based on its associated DocWorkflows and tasks.

        If the DocApplication has a current workflow, the calculation starts
        from the due date of the current workflow.
        Otherwise, the calculation starts from the DocApplication's doc_date.

        For every task, it checks if task.duration_is_business_days is True then uses
        `due_date = calculate_due_date(start_date, task.duration, business_days_only=True)`,
        otherwise, `due_date = calculate_due_date(start_date, task.duration,
        business_days_only=False)`, to calculate the due_date for that task.
        """
        if self.pk and self.current_workflow:
            start_date = self.current_workflow.due_date
            remaining_tasks = self.product.tasks.filter(step__gt=self.current_workflow.task.step)
        else:
            start_date = self.doc_date
            remaining_tasks = self.product.tasks.all()

        due_date = start_date
        for task in remaining_tasks:
            due_date = calculate_due_date(
                due_date, task.duration, business_days_only=task.duration_is_business_days
            )

        return due_date
