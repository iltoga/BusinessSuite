import time

from django.utils import timezone
from django_unicorn.components import UnicornView

from customer_applications.models import DocApplication
from customers.models import Customer
from invoices.forms import InvoiceForm
from invoices.models import Invoice, InvoiceApplication


class InvoiceCreateView(UnicornView):
    form_class = InvoiceForm
    invoice: Invoice = None

    customer: Customer = None
    customers = Customer.objects.all()
    customer_applications = []
    invoiceapplications = []

    # fields
    invoice_date = None
    due_date = None

    class Meta:
        javascript_exclude = ("customers",)

    def __init__(self, *args, **kwargs):
        super().__init__(**kwargs)
        # here we can set the initial value of the name passed in the template (for update view)
        # self.name = kwargs.get("name")
        # invoice_pk = kwargs.get("invoice_pk")
        # if invoice_pk:
        #     self.invoice = Invoice.objects.get(pk=invoice_pk)

    def mount(self):
        # Populate select field with customers
        # Start with one empty subform
        self.invoice = Invoice()
        # Initial values
        self.invoice_date = timezone.now()
        self.due_date = timezone.now()
        self.invoiceapplications = [InvoiceApplication()]

    def select_customer(self, value, idx):
        if value:
            self.customer = Customer.objects.get(pk=value)
            self.customer_applications = DocApplication.objects.filter(customer=self.customer)

    def updated_customer(self, value):
        if value and isinstance(value, Customer):
            # This should populate the customer_applications select field
            self.customer_applications = DocApplication.objects.filter(customer=self.customer)

    def add_form(self):
        self.invoiceapplications.append(InvoiceApplication())  # Add a new form when the 'Add' button is clicked

    def remove_form(self, index):
        if len(self.invoiceapplications) > 1:  # keep at least one form
            del self.invoiceapplications[index]

    def submit(self):
        # if self.form.is_valid():
        #     invoice = self.form.save()
        #     for invoiceapplication_form in self.invoiceapplications:
        #         if invoiceapplication_form.is_valid():
        #             invoiceapplication = invoiceapplication_form.save(commit=False)
        #             invoiceapplication.invoice = invoice
        #             invoiceapplication.save()
        pass
