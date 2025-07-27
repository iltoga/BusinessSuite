import random
from re import I

from django.contrib import messages
from django.db import transaction
from django.shortcuts import redirect
from django.utils import timezone
from django_unicorn.components import UnicornView

from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.forms import InvoiceCreateForm
from invoices.models import Invoice, InvoiceApplication


class InvoiceCreateView(UnicornView):
    # form_class = InvoiceForm
    invoice: Invoice = None

    customer: Customer = None
    customers = Customer.objects.all().active()
    payment_status_choices = InvoiceApplication.PAYMENT_STATUS_CHOICES
    invoice_status_choices = Invoice.INVOICE_STATUS_CHOICES
    customer_applications = []
    invoiceapplications = []
    inv_app_pk = 0

    invoice_date = None
    due_date = None
    status = None
    notes = None
    total_amount = 0

    class Meta:
        javascript_exclude = ("customers", "customer_applications", "invoiceapplications")

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        self.reset()
        self.load_data()

    def load_data(self):
        self.invoice = Invoice()
        self.invoice_date = timezone.now().strftime("%Y-%m-%d")
        self.due_date = timezone.now().strftime("%Y-%m-%d")

    def select_customer(self, value, idx):
        if value:
            self.customer = Customer.objects.get(pk=value)
            self.customer_applications = DocApplication.objects.filter(customer=self.customer)

    def select_customer_application(self, value, idx):
        if value:
            customer_application = DocApplication.objects.get(pk=value)
            # generate a unique pk (random number) for the invoice application
            self.invoiceapplications[idx].customer_application = customer_application

    def add_form(self):
        self.invoiceapplications.append(self.create_invoice_application())

    def remove_form(self, index):
        if len(self.invoiceapplications) > 1:
            del self.invoiceapplications[index]
            # self.invoiceapplications = list(self.invoiceapplications)

    def create_invoice_application(self):
        invoice_application = InvoiceApplication()
        # this is only for the frontend, to be able to add and remove forms
        invoice_application.pk = self.inv_app_pk + 1
        invoice_application.id = self.inv_app_pk
        return invoice_application

    def submit(self):
        pass

    def calculate_total_amount(self):
        # TODO: Implement the calculation logic
        pass

    def calculate_due_amount(self):
        # TODO: Implement the calculation logic
        pass

    def calculate_status(self):
        # TODO: Implement the calculation logic
        pass

    def save(self):
        with transaction.atomic():
            if self.invoice.pk:
                self.invoice.updated_by = self.request.user
            else:
                self.invoice.created_by = self.request.user
            self.invoice.save()
            for invoiceapplication in self.invoiceapplications:
                invoiceapplication.invoice = self.invoice
                invoiceapplication.save()
        messages.success(self.request, "Invoice saved successfully.")
        self.reset()

        return redirect(f"/invoices/detail/{self.invoice.pk}/")
