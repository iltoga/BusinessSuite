import logging
import os
import shutil

# Get an instance of a logger
from core.services.logger_service import Logger
from core.utils.dateutils import calculate_due_date
from customers.models import Customer
from django.conf import settings
from django.db import models, transaction
from django.db.models import Count, F, Q
from django.db.models.signals import post_delete, pre_delete
from django.dispatch import receiver
from django.utils import timezone
from products.models import Product

logger = Logger.get_logger(__name__)


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

    NOTIFY_CHANNEL_EMAIL = "email"
    NOTIFY_CHANNEL_WHATSAPP = "whatsapp"
    NOTIFY_CHANNEL_CHOICES = [
        (NOTIFY_CHANNEL_EMAIL, "Email"),
        (NOTIFY_CHANNEL_WHATSAPP, "WhatsApp"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="doc_applications")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="doc_applications")
    doc_date = models.DateField(db_index=True)
    due_date = models.DateField(blank=True, null=True, db_index=True)
    add_deadlines_to_calendar = models.BooleanField(default=True)
    calendar_event_id = models.CharField(max_length=255, blank=True, null=True, db_index=True)
    notify_customer_too = models.BooleanField(default=False)
    notify_customer_channel = models.CharField(
        max_length=20,
        choices=NOTIFY_CHANNEL_CHOICES,
        blank=True,
        null=True,
    )
    status = models.CharField(max_length=50, choices=STATUS_CHOICES, default=STATUS_PENDING, db_index=True)
    notes = models.TextField(blank=True, null=True)  # Person-specific details from invoice import
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
        indexes = [
            models.Index(fields=["customer", "status"], name="docapp_customer_status_idx"),
        ]

    def __str__(self):
        return self.product.name + " - " + self.customer.full_name + f" #{self.pk}"

    @property
    def application_type(self):
        """Returns the product type for backward compatibility."""
        return self.product.product_type if self.product else None

    def get_application_type_display(self):
        """Returns the display name of the product type."""
        return self.product.get_product_type_display() if self.product else ""

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
        return self.workflows.order_by("-task__step", "-created_at", "-id").first()

    @property
    def is_application_completed(self):
        """
        Checks whether the application is completed.
        """
        current_workflow = self.current_workflow
        if self.status == self.STATUS_COMPLETED:
            return True
        return bool(current_workflow and current_workflow.is_workflow_completed)

    @property
    def has_next_task(self):
        """
        Checks whether there is a next task.
        """
        if self.status in (self.STATUS_COMPLETED, self.STATUS_REJECTED) or self.is_application_completed:
            return False
        current_workflow = self.current_workflow
        if current_workflow and current_workflow.status not in (self.STATUS_COMPLETED,):
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
        elif current_workflow and current_workflow.status == self.STATUS_REJECTED:
            return None
        elif current_workflow:
            return current_workflow.task
        else:
            return tasks.first()

    def get_next_calendar_task(self):
        """Return next workflow task configured for calendar reminders."""
        tasks = self.product.tasks.order_by("step")
        current_workflow = self.current_workflow

        if current_workflow and current_workflow.status == self.STATUS_COMPLETED:
            tasks = tasks.filter(step__gt=current_workflow.task.step)
        elif current_workflow and current_workflow.status == self.STATUS_REJECTED:
            return None
        elif current_workflow:
            tasks = tasks.filter(step__gte=current_workflow.task.step)

        return tasks.filter(add_task_to_calendar=True).first()

    def calculate_next_calendar_due_date(self, start_date=None):
        task = self.get_next_calendar_task()
        if not task:
            return self.doc_date
        base_date = start_date or timezone.localdate()
        return calculate_due_date(base_date, task.duration, task.duration_is_business_days)

    @property
    def upload_folder(self):
        customer_folder = self.customer.upload_folder
        return f"{customer_folder}/application_{self.pk}"

    def save(self, *args, skip_status_calculation=False, **kwargs):
        """
        Overrides the default save method.
        Updates the due date and status before saving.

        Args:
            skip_status_calculation: If True, skip automatic status calculation.
                                   Useful when status is set explicitly (e.g., from invoice payment or re-open).
        """
        self.updated_at = timezone.now()
        if not self.due_date:
            self.due_date = self.calculate_application_due_date()

        # Skip all automatic status calculation when explicitly requested
        if not skip_status_calculation:
            if self.pk:
                self.status = self._get_application_status()
            # For brand-new applications, keep legacy behavior when no required documents exist yet.
            elif self.product and (not self.product.required_documents or not self.product.required_documents.strip()):
                self.status = self.STATUS_COMPLETED
        super().save(*args, **kwargs)

    def _get_application_status(self):
        """
        Gets the application status based on the workflows and documents.
        """
        if self.workflows.filter(status=self.STATUS_REJECTED).exists():
            return self.STATUS_REJECTED

        current_workflow = self.current_workflow
        if current_workflow and current_workflow.status == self.STATUS_COMPLETED and current_workflow.is_workflow_completed:
            return self.STATUS_COMPLETED

        if self.is_document_collection_completed:
            # If there are no workflows configured, treat a fully collected document set as completed.
            if not self.workflows.exists():
                return self.STATUS_COMPLETED
            return self.STATUS_PROCESSING

        if self.workflows.filter(status=self.STATUS_PROCESSING).exists():
            return self.STATUS_PROCESSING
        if self.workflows.filter(status=self.STATUS_PENDING).exists():
            return self.STATUS_PENDING

        return self.STATUS_PENDING

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

    def get_document_order_list(self, required=None):
        """
        Get ordered list of document type names from product configuration.
        Returns list of document type names in the order they should appear.
        """
        order_list = []
        if required is None or required is True:
            required_docs = self.product.required_documents or ""
            order_list.extend([name.strip() for name in required_docs.split(",") if name.strip()])
        if required is None or required is False:
            optional_docs = self.product.optional_documents or ""
            order_list.extend([name.strip() for name in optional_docs.split(",") if name.strip()])
        return order_list

    def order_documents_by_product(self, documents, required=None):
        """
        Order documents based on the product's document list order.
        Documents not in the order list will appear at the end.
        """
        order_list = self.get_document_order_list(required)
        if not order_list:
            return documents

        # Create order mapping: doc_type_name -> position
        order_map = {name: idx for idx, name in enumerate(order_list)}

        # Sort documents: first by order_map position, then by doc_type name for any not in list
        docs_list = list(documents)
        docs_list.sort(key=lambda d: (order_map.get(d.doc_type.name, 9999), d.doc_type.name))
        return docs_list

    @property
    def ordered_documents(self):
        """
        Returns all documents for this application, ordered by the product's document list.
        """
        return self.order_documents_by_product(self.documents.all())

    def get_completed_documents(self, type="all"):
        """
        Gets completed documents by type, ordered by product's document list.
        """
        filters = {"completed": True}
        required = None
        if type != "all":
            required = True if type == "required" else False
            filters["required"] = required
        documents = self.documents.filter(**filters).select_related("doc_type")
        return self.order_documents_by_product(documents, required)

    def get_incomplete_documents(self, type="all"):
        """
        Gets incomplete documents by type, ordered by product's document list.
        """
        filters = {"completed": False}
        required = None
        if type != "all":
            required = True if type == "required" else False
            filters["required"] = required
        documents = self.documents.filter(**filters).select_related("doc_type")
        return self.order_documents_by_product(documents, required)

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

    def reopen(self, user) -> bool:
        """
        Re-open a completed application and reset the last workflow step to processing.
        """
        if self.status != self.STATUS_COMPLETED:
            return False

        self.status = self.STATUS_PROCESSING
        self.updated_by = user

        try:
            from customer_applications.models.doc_workflow import DocWorkflow

            last_workflow = self.workflows.order_by("-task__step").first()
            if last_workflow and last_workflow.status == DocWorkflow.STATUS_COMPLETED:
                last_workflow.status = DocWorkflow.STATUS_PROCESSING
                last_workflow.updated_by = user
                last_workflow.save()
        except Exception:
            # Allow application status change even if workflow update fails
            pass

        self.save(skip_status_calculation=True)
        return True

    def can_be_deleted(self, user=None, delete_invoices=False):
        """
        Check whether this application can be deleted.

        Args:
            user: optional user performing the deletion - used to check superuser permission
            delete_invoices: whether the caller requests to also delete linked invoices

        Returns:
            (bool, str|None) -> (can_delete, message)
        """
        # Block deletion if related invoices exist
        if self.invoice_applications.exists():
            # If the caller asked to delete related invoices, only superusers may do that
            if delete_invoices:
                if not user or not getattr(user, "is_superuser", False):
                    return (
                        False,
                        "Only superusers can delete linked invoices. Please delete the invoices first or ask a superuser.",
                    )
                # Superuser confirmed cascade delete is allowed
                return True, None

            return False, "Related invoices exist. You must delete the invoices first."

        return True, None

    def delete(self, force_delete_invoices=False, user=None, *args, **kwargs):
        """Allow callers to force deletion when a superuser explicitly requests invoice cascade.

        Usage:
            delete()  # normal behaviour: will block if related invoices exist
            delete(force_delete_invoices=True, user=some_superuser)  # allow deletion and let caller cleanup invoices
        """
        # If caller explicitly requested invoice deletion and is superuser, allow deletion
        if force_delete_invoices and user and getattr(user, "is_superuser", False):
            return super().delete(*args, **kwargs)

        # Default behaviour: enforce can_be_deleted rules
        can_delete, msg = self.can_be_deleted()
        if not can_delete:
            from django.db.models import ProtectedError

            raise ProtectedError(msg, self)
        super().delete(*args, **kwargs)


@receiver(pre_delete, sender=DocApplication)
def pre_delete_doc_application_signal(sender, instance, **kwargs):
    # retain the folder path before deleting the doc application
    instance.folder_path = instance.upload_folder

    # Queue Google Calendar cleanup asynchronously after the DB transaction commits.
    known_event_ids = set()
    if instance.calendar_event_id:
        known_event_ids.add(instance.calendar_event_id)
    try:
        from customer_applications.models.workflow_notification import WorkflowNotification

        refs = (
            WorkflowNotification.objects.filter(doc_application=instance, external_reference__isnull=False)
            .exclude(external_reference="")
            .values_list("external_reference", flat=True)
        )
        known_event_ids.update(refs)
    except Exception as exc:
        logger.warning("Failed to collect known calendar event references for application #%s: %s", instance.id, exc)

    application_id = instance.id
    actor_user_id = instance.updated_by_id or instance.created_by_id

    def _queue_calendar_cleanup():
        try:
            from customer_applications.tasks import SYNC_ACTION_DELETE, sync_application_calendar_task

            sync_application_calendar_task(
                application_id=application_id,
                user_id=actor_user_id,
                action=SYNC_ACTION_DELETE,
                known_event_ids=list(known_event_ids),
            )
        except Exception as exc:
            logger.warning("Failed to queue calendar cleanup for application #%s: %s", application_id, exc)

    transaction.on_commit(_queue_calendar_cleanup)


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
