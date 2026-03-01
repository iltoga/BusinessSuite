# models.py
from customer_applications.models.doc_application import DocApplication
from customers.models import Customer
from django.conf import settings
from django.contrib.postgres.search import SearchVector, TrigramSimilarity
from django.core.cache import cache
from django.db import models
from django.db.models import Q, Sum
from django.db.models.functions import Cast
from django.utils import timezone


class InvoiceQuerySet(models.QuerySet):
    """
    Custom queryset for Invoice model.
    """

    pass


class InvoiceManager(models.Manager):
    """
    Invoice Manager to enhance the default manager and
    add a search functionality.
    """

    def get_queryset(self):
        return InvoiceQuerySet(self.model, using=self._db)

    def search_invoices(self, query):
        """
        Search Invoices by customer, invoice number (partial match), invoice date, due date, status, invoice date year (this one exact match).
        Use the SearchVector to search across multiple fields.
        """
        return self.annotate(
            search=SearchVector(
                "invoice_no",
                "invoice_date",
                "due_date",
                "status",
                "invoice_date__year",
            ),
            first_name_similarity=TrigramSimilarity("customer__first_name", query),
            last_name_similarity=TrigramSimilarity("customer__last_name", query),
        ).filter(
            Q(search=query)
            | Q(first_name_similarity__gt=0.3)
            | Q(last_name_similarity__gt=0.3)
            | Q(invoice_no__icontains=query)
        )

        # return self.filter(
        #     models.Q(customer__first_name__icontains=query)
        #     | models.Q(customer__last_name__icontains=query)
        #     | models.Q(invoice_no__icontains=query)
        #     | models.Q(invoice_date__icontains=query)
        #     | models.Q(due_date__icontains=query)
        #     | models.Q(status__icontains=query)
        #     | (models.Q(invoice_date__year=year_query) if year_query is not None else models.Q())
        # )


class Invoice(models.Model):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PARTIAL_PAYMENT = "partial_payment"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    WRITE_OFF = "write_off"

    INVOICE_STATUS_CHOICES = [
        (CREATED, "Created"),
        (PENDING_PAYMENT, "Pending Payment"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
        (DISPUTED, "Disputed"),
        (CANCELLED, "Cancelled"),
        (PARTIALLY_REFUNDED, "Partially Refunded"),
        (REFUNDED, "Refunded"),
        (WRITE_OFF, "Write Off"),
    ]

    customer: models.ForeignKey[Customer] = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="invoices"
    )
    invoice_no = models.PositiveIntegerField(unique=True, db_index=True)
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    sent = models.BooleanField(default=False)
    status = models.CharField(choices=INVOICE_STATUS_CHOICES, default=CREATED, max_length=20, db_index=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default="0")
    # Import-related fields
    imported = models.BooleanField(default=False, db_index=True)
    imported_from_file = models.CharField(max_length=255, blank=True, null=True)
    raw_extracted_data = models.JSONField(blank=True, null=True)
    mobile_phone = models.CharField(max_length=50, blank=True, null=True)
    bank_details = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_by_invoice",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_invoice",
        null=True,
        blank=True,
    )
    objects = InvoiceManager()

    INVOICE_SEQ_CACHE_PREFIX = "invoices:invoice_seq"
    INVOICE_SEQ_CACHE_TIMEOUT = 60 * 60 * 24 * 30  # 30 days

    class Meta:
        ordering = ("-invoice_date", "-invoice_no")

    @property
    def invoice_no_display(self):
        if not self.invoice_no:
            return ""

        year = self.get_invoice_year()
        year_str = str(year)
        invoice_no_str = str(self.invoice_no)

        if invoice_no_str.startswith(year_str):
            return invoice_no_str.zfill(8)

        return f"{year_str}{invoice_no_str}".zfill(8)

    @property
    def total_paid_amount(self):
        # Use annotated field if available, otherwise calculate
        if hasattr(self, "total_paid"):
            return self.total_paid or 0

        if self.pk:  # Check if the Invoice instance has been saved
            return (
                self.invoice_applications.annotate(total_payment=Sum("payments__amount")).aggregate(
                    total_paid=Sum("total_payment")
                )["total_paid"]
                or 0
            )
        return 0

    @property
    def total_due_amount(self):
        # Use annotated field if available, otherwise calculate
        if hasattr(self, "total_due"):
            return self.total_due or 0

        tot = self.total_amount - self.total_paid_amount
        return tot

    @property
    def is_payment_complete(self):
        return self.invoice_applications.payment_complete().exists()

    @property
    def is_fully_paid(self):
        return self.status == Invoice.PAID or self.status == Invoice.REFUNDED or self.status == Invoice.WRITE_OFF

    @property
    def is_expired(self):
        """Check if invoice is expired (overdue)"""
        from django.utils import timezone

        # Use annotated field if available, otherwise fall back to property
        due_amount = getattr(self, "total_due", None)
        if due_amount is None:
            due_amount = self.total_due_amount

        return due_amount > 0 and self.due_date < timezone.now().date()

    def delete(self, force=False, *args, **kwargs):
        """
        Delete an invoice. By default, invoices cannot be deleted.
        Only superusers can force delete invoices, which will cascade delete
        related InvoiceApplications, CustomerApplications, and Payments.
        """
        if not force:
            raise Exception("You can't delete an invoice.")

        # Collect customer applications before deleting invoice
        customer_applications = set()
        for inv_app in self.invoice_applications.all():
            customer_applications.add(inv_app.customer_application)

        # Delete the invoice (cascade will delete InvoiceApplications and Payments)
        super().delete(*args, **kwargs)

        # Delete the customer applications
        for customer_app in customer_applications:
            try:
                customer_app.delete()
            except Exception:
                # Customer application might be linked to other invoices or protected
                # Continue deleting others if one fails
                pass

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            self.invoice_no = self.get_next_invoice_no()
        self.total_amount = self.calculate_total_amount()
        self.status = self.get_invoice_status()
        # Save first to ensure status is up to date and pk is set
        super().save(*args, **kwargs)

        self._sync_invoice_sequence_cache()

        # If invoice is paid, set all related DocApplications to completed
        from customer_applications.models.doc_application import DocApplication

        if self.status == Invoice.PAID:
            invoice_apps = self.invoice_applications.select_related("customer_application").all()
            for inv_app in invoice_apps:
                doc_app = inv_app.customer_application
                if doc_app.status != DocApplication.STATUS_COMPLETED:
                    doc_app.status = DocApplication.STATUS_COMPLETED
                    doc_app.save(skip_status_calculation=True)

    def __str__(self):
        inv_no = f"{self.invoice_no_display}" if self.invoice_no else "New"
        customer = self.customer
        return f"{inv_no} - {customer}"

    # Custom methods

    def calculate_total_amount(self):
        total = 0
        try:
            if self.invoice_applications.exists():
                total += self.invoice_applications.aggregate(models.Sum("amount"))["amount__sum"] or 0
        except ValueError:
            # Invoice hasn't been saved yet, so it can't have any InvoiceApplications
            pass

        return total

    def get_next_invoice_no(self):
        return Invoice.get_next_invoice_no_for_year(self.get_invoice_year())

    @staticmethod
    def _build_year_invoice_no(year: int, sequence: int) -> int:
        return int(f"{year}{sequence:04d}")

    @staticmethod
    def _extract_sequence(invoice_no: int, year: int) -> int:
        invoice_no_str = str(invoice_no)
        year_str = str(year)
        if invoice_no_str.startswith(year_str):
            sequence_str = invoice_no_str[len(year_str) :] or "0"
            return int(sequence_str)
        return int(invoice_no)

    @classmethod
    def _get_invoice_seq_cache_key(cls, year: int) -> str:
        return f"{cls.INVOICE_SEQ_CACHE_PREFIX}:{year}"

    @classmethod
    def _get_last_sequence_for_year(cls, year: int) -> int:
        year_str = str(year)
        last_invoice = (
            cls.objects.annotate(invoice_no_str=Cast("invoice_no", models.CharField()))
            .filter(invoice_no_str__startswith=year_str)
            .order_by("-invoice_no")
            .first()
        )
        if last_invoice:
            return cls._extract_sequence(last_invoice.invoice_no, year)
        return 0

    @classmethod
    def _prime_invoice_sequence_cache(cls, year: int) -> int:
        last_sequence = cls._get_last_sequence_for_year(year)
        try:
            cache.add(
                cls._get_invoice_seq_cache_key(year),
                last_sequence,
                timeout=cls.INVOICE_SEQ_CACHE_TIMEOUT,
            )
        except Exception:
            pass
        return last_sequence

    def _sync_invoice_sequence_cache(self) -> None:
        if not self.invoice_no:
            return
        try:
            year = self.get_invoice_year()
            sequence = self._extract_sequence(self.invoice_no, year)
            cache_key = self._get_invoice_seq_cache_key(year)
            cached_value = cache.get(cache_key)
            if cached_value is None or sequence > cached_value:
                cache.set(cache_key, sequence, timeout=self.INVOICE_SEQ_CACHE_TIMEOUT)
        except Exception:
            # Never block invoice saves on cache failures
            pass

    @classmethod
    def get_next_invoice_no_for_year(cls, year: int) -> int:
        cache_key = cls._get_invoice_seq_cache_key(year)

        try:
            next_sequence = cache.incr(cache_key)
            return cls._build_year_invoice_no(year, next_sequence)
        except Exception:
            last_sequence = cls._prime_invoice_sequence_cache(year)

        try:
            next_sequence = cache.incr(cache_key)
            return cls._build_year_invoice_no(year, next_sequence)
        except Exception:
            next_sequence = last_sequence + 1
            return cls._build_year_invoice_no(year, next_sequence)

    def get_invoice_year(self) -> int:
        try:
            return self.invoice_date.year if self.invoice_date else timezone.now().year
        except Exception:
            return timezone.now().year

    def get_invoice_status(self):
        if self.total_due_amount < 0:
            raise ValueError("Overpayment detected on invoice")

        if self.total_due_amount == 0:
            return Invoice.PAID

        if self.total_due_amount > 0 and self.due_date < timezone.now().date():
            return Invoice.OVERDUE

        if self.total_due_amount == self.total_amount:
            if self.sent:
                return Invoice.PENDING_PAYMENT
            return Invoice.CREATED

        if self.total_due_amount < self.total_amount:
            return Invoice.PARTIAL_PAYMENT

        raise ValueError("Unable to determine invoice status")


class InvoiceApplicationQuerySet(models.QuerySet):
    def not_fully_paid(self):
        return self.filter(
            status__in=[
                InvoiceApplication.PENDING,
                InvoiceApplication.PARTIAL_PAYMENT,
                InvoiceApplication.OVERDUE,
                InvoiceApplication.DISPUTED,
            ]
        )

    def fully_paid(self):
        return self.filter(status=InvoiceApplication.PAID)

    def payment_complete(self):
        return self.filter(
            status__in=[
                InvoiceApplication.PAID,
                InvoiceApplication.REFUNDED,
                InvoiceApplication.WRITE_OFF,
                InvoiceApplication.CANCELLED,
            ]
        )


class InvoiceApplicationManager(models.Manager):
    def get_queryset(self):
        return InvoiceApplicationQuerySet(self.model, using=self._db)

    def not_fully_paid(self):
        return self.get_queryset().not_fully_paid()

    def fully_paid(self):
        return self.get_queryset().fully_paid()

    def payment_complete(self):
        return self.get_queryset().payment_complete()


class InvoiceApplication(models.Model):
    PENDING = "pending"
    PARTIAL_PAYMENT = "partial_payment"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    WRITE_OFF = "write_off"

    PAYMENT_STATUS_CHOICES = [
        (PENDING, "Pending"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
        (DISPUTED, "Disputed"),
        (CANCELLED, "Cancelled"),
        (REFUNDED, "Refunded"),
        (WRITE_OFF, "Write Off"),
    ]

    invoice = models.ForeignKey(Invoice, related_name="invoice_applications", on_delete=models.CASCADE)
    customer_application = models.ForeignKey(
        DocApplication, related_name="invoice_applications", on_delete=models.CASCADE
    )
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(choices=PAYMENT_STATUS_CHOICES, default=PENDING, max_length=20, db_index=True)
    objects = InvoiceApplicationManager()

    class Meta:
        ordering = ("-id",)
        constraints = [
            models.UniqueConstraint(fields=["customer_application", "invoice"], name="unique_invoice_application")
        ]

    @property
    def paid_amount(self):
        # Use annotated field if available (from optimized querysets)
        if hasattr(self, "annotated_paid_amount"):
            return self.annotated_paid_amount or 0

        try:
            # Check if payments are prefetched to avoid extra queries
            if hasattr(self, "_prefetched_objects_cache") and "payments" in self._prefetched_objects_cache:
                # Use prefetched payments
                return sum(payment.amount for payment in self.payments.all()) or 0

            if self.payments.exists():
                return self.payments.aggregate(models.Sum("amount"))["amount__sum"] or 0
        except ValueError:
            # InvoiceApplication hasn't been saved yet, so it can't have any Payments
            pass
        return 0

    @property
    def due_amount(self):
        # Use annotated field if available (from optimized querysets)
        if hasattr(self, "annotated_due_amount"):
            return self.annotated_due_amount or 0

        return self.amount - self.paid_amount

    @property
    def is_payment_complete(self):
        completed_statuses = [
            InvoiceApplication.PAID,
            InvoiceApplication.REFUNDED,
            InvoiceApplication.WRITE_OFF,
            InvoiceApplication.CANCELLED,
        ]
        return self.status in completed_statuses

    def calculate_payment_status(self):
        if self.amount == self.paid_amount:
            return InvoiceApplication.PAID
        if self.paid_amount > 0:
            return InvoiceApplication.PARTIAL_PAYMENT
        if self.paid_amount == 0 and self.invoice.due_date < timezone.now().date():
            return InvoiceApplication.OVERDUE
        # set self.status to this status
        return InvoiceApplication.PENDING

    def __str__(self):
        return f"{self.invoice.invoice_no_display} - {self.customer_application}"

    def save(self, *args, **kwargs):
        self.status = self.calculate_payment_status()
        super().save(*args, **kwargs)
