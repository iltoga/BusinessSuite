import logging
import os
import shutil

from django.conf import settings
from django.db import models
from django.db.models import Count, F, Q
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone

from core.utils.dateutils import calculate_due_date
from customers.models import Customer
from products.models import Product

# Get an instance of a logger
logger = logging.getLogger(__name__)


class DocApplicationQuerySet(models.QuerySet):
    """
    Custom queryset for DocApplication model.
    """

    def filter_by_document_collection_completed(self):
        # First, we annotate each DocApplication with the count of required documents
        # and the count of required, completed documents
        doc_applications_with_counts = self.annotate(
            total_required_documents=Count("documents", filter=Q(documents__required=True)),
            completed_required_documents=Count(
                "documents", filter=Q(documents__required=True, documents__completed=True)
            ),
        )

        # Then, we filter to only include DocApplications where the counts are equal
        return doc_applications_with_counts.filter(total_required_documents=F("completed_required_documents"))

    def exclude_already_invoiced(self, current_invoice_to_include=None):
        """
        Excludes DocApplications that are already invoiced.
        In case of updating an invoice, we need to include all DocApplications tha are part of the current invoice.
        """
        qs = self.exclude(invoice_applications__isnull=False)
        if current_invoice_to_include:
            # use logical or on queryset to add the current invoice's DocApplications
            qs = qs | self.filter(invoice_applications__invoice=current_invoice_to_include)

        return qs


class DocApplicationManager(models.Manager):
    """
    DocApplication Manager to enhance the default manager and
    add a search functionality.
    """

    def get_queryset(self):
        return DocApplicationQuerySet(self.model, using=self._db)

    # So we can use the custom queryset methods on the manager too
    def filter_by_document_collection_completed(self):
        return self.get_queryset().filter_by_document_collection_completed()

    def exclude_already_invoiced(self, current_invoice_to_include=None):
        return self.get_queryset().exclude_already_invoiced(current_invoice_to_include)

    def search_doc_applications(self, query):
        """
        Search DocApplications by product name, product code, product type,
        customer first name, customer last name, and doc date.
        """
        return self.filter(
            models.Q(product__name__icontains=query)
            | models.Q(product__code__icontains=query)
            | models.Q(product__product_type__icontains=query)
            | models.Q(customer__first_name__icontains=query)
            | models.Q(customer__last_name__icontains=query)
            | models.Q(doc_date__icontains=query)
        )


class DocApplication(models.Model):
    """
    The DocApplication model which represents a document application in the system.
    """

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
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="doc_applications")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="doc_applications")
    doc_date = models.DateField(db_index=True)
    due_date = models.DateField(blank=True, null=True, db_index=True)
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
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

    def __str__(self):
        return self.product.name + " - " + self.customer.full_name + f" #{self.pk}"

    @property
    def is_document_collection_completed(self):
        """
        Checks whether all required documents are completed.
        """
        return (
            self.documents.filter(required=True).count() == self.documents.filter(completed=True, required=True).count()
        )

    @property
    def all_workflow_completed(self):
        """
        Checks whether all workflows are completed.
        """
        return self.workflows.count() == self.workflows.filter(status=self.STATUS_COMPLETED).count()

    @property
    def current_workflow(self):
        """
        Gets the current workflow.
        """
        return self.workflows.order_by("-task__step").first()

    @property
    def is_application_completed(self):
        """
        Checks whether the application is completed.
        """
        current_workflow = self.current_workflow
        return current_workflow.is_workflow_completed if current_workflow else False

    @property
    def has_next_task(self):
        """
        Checks whether there is a next task.
        """
        if not self.is_document_collection_completed or self.is_application_completed:
            return False
        current_workflow = self.current_workflow
        if current_workflow and current_workflow.status != self.STATUS_COMPLETED:
            return False
        next_task = self.next_task
        return bool(next_task and next_task.step)

    @property
    def next_task(self):
        """
        Gets the next task.
        """
        tasks = self.product.tasks.order_by("step")
        current_workflow = self.current_workflow

        if current_workflow and current_workflow.status == self.STATUS_COMPLETED:
            return tasks.filter(step=current_workflow.task.step + 1).first()
        elif current_workflow:
            return current_workflow.task
        else:
            return tasks.first()

    @property
    def upload_folder(self):
        customer_folder = self.customer.upload_folder
        return f"{customer_folder}/application_{self.pk}"

    def save(self, *args, **kwargs):
        """
        Overrides the default save method.
        Updates the due date and status before saving.
        """
        self.updated_at = timezone.now()
        self.due_date = self.calculate_application_due_date()
        if self.pk:
            self.status = self._get_application_status()
        super().save(*args, **kwargs)

    def _get_application_status(self):
        """
        Gets the application status based on the workflows and documents.
        """
        if self.is_application_completed:
            return self.STATUS_COMPLETED
        elif self.is_document_collection_completed:
            return self.STATUS_PROCESSING
        elif self.workflows.filter(status=self.STATUS_REJECTED).exists():
            return self.STATUS_REJECTED
        else:
            return self.status

    def calculate_application_due_date(self):
        """
        Calculates the due date of the application.
        """
        if self.pk and self.current_workflow:
            start_date = self.current_workflow.due_date
            tasks = self.product.tasks.filter(step__gt=self.current_workflow.task.step)
        else:
            start_date = self.doc_date
            tasks = self.product.tasks.all()

        due_date = start_date
        for task in tasks:
            due_date = calculate_due_date(
                start_date=due_date, days_to_complete=task.duration, business_days_only=task.duration_is_business_days
            )
        return due_date

    def get_completed_documents(self, type="all"):
        """
        Gets completed documents by type.
        """
        filters = {"completed": True}
        if type != "all":
            filters["required"] = True if type == "required" else False
        return self.documents.filter(**filters)

    def get_incomplete_documents(self, type="all"):
        """
        Gets incomplete documents by type.
        """
        filters = {"completed": False}
        if type != "all":
            filters["required"] = True if type == "required" else False
        return self.documents.filter(**filters)

    def has_invoice(self):
        """
        Checks whether the application has an invoice.
        """
        return self.invoice_applications.exists()

    def get_invoice(self):
        """
        Gets the application's invoice.
        """
        return self.invoice_applications.first().invoice if self.has_invoice() else None


@receiver(pre_delete, sender=DocApplication)
def pre_delete_doc_application_signal(sender, instance, **kwargs):
    # retain the folder path before deleting the doc application
    instance.folder_path = instance.upload_folder


@receiver(post_delete, sender=DocApplication)
def post_delete_doc_application_signal(sender, instance, **kwargs):
    logger.info("Deleted: %s", instance)
    # get media root path from settings
    media_root = settings.MEDIA_ROOT
    # delete the folder containing the documents' files
    try:
        shutil.rmtree(os.path.join(media_root, instance.folder_path))
    except FileNotFoundError:
        logger.info("Folder not found: %s", instance.folder_path)
