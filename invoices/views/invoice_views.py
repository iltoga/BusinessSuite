from django.conf import settings
from django.contrib import messages
from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.core import serializers
from django.db import models, transaction
from django.forms import inlineformset_factory
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from core.models import CountryCode
from customer_applications.models import DocApplication, Document, DocWorkflow
from customers.models import Customer
from invoices.forms import (
    BaseInvoiceApplicationFormSet,
    InvoiceApplicationCreateForm,
    InvoiceApplicationUpdateForm,
    InvoiceCreateForm,
    InvoiceUpdateForm,
)
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication
from products.models import DocumentType, Task

InvoiceApplicationCreateFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationCreateForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=1,
    can_delete=True,
)

InvoiceApplicationUpdateFormSet = inlineformset_factory(
    Invoice,
    InvoiceApplication,
    form=InvoiceApplicationUpdateForm,
    formset=BaseInvoiceApplicationFormSet,
    extra=0,
    can_delete=True,
)


class InvoiceListView(PermissionRequiredMixin, ListView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_list.html"

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get("q")
        if query and self.model is not None:
            order_by = self.model._meta.ordering
            if order_by:
                queryset = self.model.objects.search_customers(query).order_by(*order_by)
            else:
                queryset = self.model.objects.search_customers(query)
        return queryset


class InvoiceCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("invoices.add_invoice",)
    model = Invoice
    form_class = InvoiceCreateForm
    template_name = "invoices/invoice_create.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice created successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        customer_applications = DocApplication.objects.none()
        selected_customer_application = self.get_customer_application_from_kwargs()
        if selected_customer_application:
            customer = selected_customer_application.customer
        else:
            customer = self.get_customer_from_kwargs()

        if customer:
            data["customer"] = customer
            data["customer_applications_json"] = customer.doc_applications_to_json()
            data["selected_customer_application_pk"] = (
                selected_customer_application.pk if selected_customer_application else ""
            )

            # Avoid adding already invoiced applications when creating a new invoice
            customer_applications = customer.get_doc_applications_for_invoice()
            data["has_pending_applications"] = customer_applications.exists()
        else:
            data["customer_applications_json"] = serializers.serialize("json", [])
            data["has_pending_applications"] = False

        if self.request.POST:
            data["invoice_applications"] = InvoiceApplicationCreateFormSet(
                self.request.POST,
                form_kwargs={"customer_applications": customer_applications},
            )
        else:
            formset = InvoiceApplicationCreateFormSet(
                form_kwargs={
                    "customer_applications": customer_applications,
                    "selected_customer_application": selected_customer_application,
                }
            )
            data["invoice_applications"] = formset

        # get currency settings
        data["currency"] = settings.CURRENCY
        data["currency_symbol"] = settings.CURRENCY_SYMBOL
        data["currency_decimal_places"] = settings.CURRENCY_DECIMAL_PLACES

        # Add countries for customer modal
        data["countries"] = CountryCode.objects.all().order_by("country")

        # Add document types for product modal
        data["document_types"] = DocumentType.objects.all().order_by("name")

        # Add products for customer application modal
        from products.models import Product

        data["products"] = Product.objects.all().order_by("name")

        return data

    def get_initial(self):
        initial = super().get_initial()
        customer_application = self.get_customer_application_from_kwargs()
        if customer_application:
            customer = customer_application.customer
            initial["selected_customer_application"] = customer_application
        else:
            customer = self.get_customer_from_kwargs()
        if customer:
            initial["customer"] = customer
        return initial

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]

        # Validate invoice applications formset
        if not invoice_applications.is_valid():
            return self.form_invalid(form)

        form.instance.created_by = self.request.user
        self.object = form.save(commit=False)
        self.object.save()

        # Save invoice applications
        invoice_applications.instance = self.object
        invoice_applications.save()

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below and resubmit.")
        return super().form_invalid(form)

    # Custom methods

    def get_customer_from_kwargs(self):
        customer_id = self.kwargs.get("customer_id", None)
        if customer_id:
            try:
                return Customer.objects.get(pk=customer_id)
            except Customer.DoesNotExist:
                messages.error(self.request, "Customer not found!")
        return None

    def get_customer_application_from_kwargs(self):
        doc_application_pk = self.kwargs.get("doc_application_pk", None)
        if doc_application_pk:
            try:
                return DocApplication.objects.get(pk=doc_application_pk)
            except DocApplication.DoesNotExist:
                messages.error(self.request, "Customer application not found!")
        return None

    def _create_new_customer_application(self, form, customer):
        """Helper method to create a new customer application with documents and workflow."""
        from core.utils.dateutils import calculate_due_date

        try:
            # Create the DocApplication
            doc_app = form.save(commit=False)
            doc_app.customer = customer
            doc_app.created_by = self.request.user
            doc_app.save()

            # Create documents based on product requirements
            self._create_documents_for_application(doc_app)

            # Create initial workflow step
            self._create_initial_workflow(doc_app)

            return doc_app
        except Exception as e:
            messages.error(self.request, f"Error creating customer application: {str(e)}")
            return None

    def _create_documents_for_application(self, doc_app):
        """Create documents for a customer application based on product requirements."""
        required_docs_str = doc_app.product.required_documents or ""
        optional_docs_str = doc_app.product.optional_documents or ""

        required_doc_names = [name.strip() for name in required_docs_str.split(",") if name.strip()]
        optional_doc_names = [name.strip() for name in optional_docs_str.split(",") if name.strip()]

        # Create required documents
        for doc_name in required_doc_names:
            try:
                doc_type = DocumentType.objects.get(name=doc_name)
                Document.objects.create(
                    doc_application=doc_app,
                    doc_type=doc_type,
                    required=True,
                    created_by=self.request.user,
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )
            except DocumentType.DoesNotExist:
                pass  # Skip if document type doesn't exist

        # Create optional documents
        for doc_name in optional_doc_names:
            try:
                doc_type = DocumentType.objects.get(name=doc_name)
                Document.objects.create(
                    doc_application=doc_app,
                    doc_type=doc_type,
                    required=False,
                    created_by=self.request.user,
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )
            except DocumentType.DoesNotExist:
                pass  # Skip if document type doesn't exist

    def _create_initial_workflow(self, doc_app):
        """Create the initial workflow step (document collection) for a customer application."""
        from core.utils.dateutils import calculate_due_date

        # Get the first task for this product
        first_task = Task.objects.filter(product=doc_app.product, step=1).first()
        if first_task:
            due_date = calculate_due_date(
                start_date=timezone.now().date(),
                days_to_complete=first_task.duration,
                business_days_only=first_task.duration_is_business_days,
            )
            DocWorkflow.objects.create(
                doc_application=doc_app,
                task=first_task,
                start_date=timezone.now().date(),
                due_date=due_date,
                status=DocWorkflow.STATUS_PENDING,
                created_by=self.request.user,
            )


class InvoiceUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("invoices.change_invoice",)
    model = Invoice
    form_class = InvoiceUpdateForm
    template_name = "invoices/invoice_update.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view
    success_message = "Invoice updated successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)

        customer = self.object.customer
        customer_applications = customer.get_doc_applications_for_invoice(current_invoice_to_include=self.object)

        data["customer_applications_json"] = customer.doc_applications_to_json(current_invoice_to_include=self.object)

        if self.request.POST:
            # can I add the missing data (such as the ones not being posted because the field was disabled) to the POST request?
            data["invoice_applications"] = InvoiceApplicationUpdateFormSet(
                self.request.POST,
                instance=self.object,
                prefix="invoice_applications",
                form_kwargs={"customer_applications": customer_applications},
            )
        else:
            data["invoice_applications"] = InvoiceApplicationUpdateFormSet(
                instance=self.object,
                prefix="invoice_applications",
                form_kwargs={"customer_applications": customer_applications},
            )

        # get currency settings
        data["currency"] = settings.CURRENCY
        data["currency_symbol"] = settings.CURRENCY_SYMBOL
        data["currency_decimal_places"] = settings.CURRENCY_DECIMAL_PLACES

        # Add countries for customer modal
        data["countries"] = CountryCode.objects.all().order_by("country")

        # Add document types for product modal
        data["document_types"] = DocumentType.objects.all().order_by("name")

        # Add products for customer application modal
        from products.models import Product

        data["products"] = Product.objects.all().order_by("name")

        return data

    @transaction.atomic
    def form_valid(self, form):
        context = self.get_context_data()
        invoice_applications = context["invoice_applications"]
        form.instance.updated_by = self.request.user

        if all(form.is_valid() for form in invoice_applications) and invoice_applications.is_valid():
            self.object = form.save()  # Save the Invoice after checking InvoiceApplications
            invoice_applications.instance = self.object
            invoice_applications.save()
        else:
            return self.form_invalid(form)

        return super().form_valid(form)

    def form_invalid(self, form):
        messages.error(self.request, "Please correct the errors below and resubmit.")
        return super().form_invalid(form)


class InvoiceDeleteView(PermissionRequiredMixin, DeleteView):
    permission_required = ("invoices.delete_invoice",)
    model = Invoice
    template_name = "invoices/invoice_delete.html"
    success_url = reverse_lazy("invoice-list")  # URL pattern name for the invoice list view

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        invoice = self.get_object()

        # Check if user is superuser
        context["is_superuser"] = self.request.user.is_superuser
        context["deletion_blocked"] = not self.request.user.is_superuser

        # Get related objects counts for display
        if self.request.user.is_superuser:
            context["invoice_applications_count"] = invoice.invoice_applications.count()
            context["customer_applications_count"] = (
                invoice.invoice_applications.values("customer_application").distinct().count()
            )

            # Count payments across all invoice applications
            total_payments = 0
            for inv_app in invoice.invoice_applications.all():
                total_payments += inv_app.payments.count()
            context["payments_count"] = total_payments

        return context

    @transaction.atomic
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()

        # Only superusers can force delete
        if not request.user.is_superuser:
            messages.error(request, "Invoices cannot be deleted. Only superusers have this permission.")
            return self.render_to_response(self.get_context_data())

        # Check if force delete is confirmed
        force_delete_confirmed = request.POST.get("force_delete_confirmed", "") == "yes"
        delete_customer_apps = request.POST.get("delete_customer_applications") == "yes"

        if not force_delete_confirmed:
            messages.error(request, "Please confirm the force delete action.")
            return self.render_to_response(self.get_context_data())

        try:
            invoice_no = self.object.invoice_no_display
            customer_name = self.object.customer.full_name

            # Get counts before deletion for the success message
            invoice_apps_count = self.object.invoice_applications.count()
            customer_apps_count = self.object.invoice_applications.values("customer_application").distinct().count()
            payments_count = sum(inv_app.payments.count() for inv_app in self.object.invoice_applications.all())

            # Collect DocApplication ids if needed
            doc_app_ids = set()
            if delete_customer_apps:
                for inv_app in self.object.invoice_applications.all():
                    if inv_app.customer_application_id:
                        doc_app_ids.add(inv_app.customer_application_id)

            # Force delete the invoice (cascade will delete related objects)
            self.object.delete(force=True)

            # Delete the customer applications if requested
            if delete_customer_apps and doc_app_ids:
                from customer_applications.models.doc_application import DocApplication

                DocApplication.objects.filter(id__in=doc_app_ids).delete()

            msg = f"Invoice {invoice_no} for {customer_name} has been force deleted. "
            msg += f"Also deleted: {invoice_apps_count} invoice application(s), "
            msg += f"{customer_apps_count} customer application(s), and {payments_count} payment(s)."
            if delete_customer_apps and doc_app_ids:
                msg += f" Deleted {len(doc_app_ids)} corresponding customer application(s)."

            messages.success(request, msg)
            return self.get_success_url()
        except Exception as e:
            messages.error(request, f"Error deleting invoice: {str(e)}")
            return self.render_to_response(self.get_context_data())

    def get_success_url(self):
        from django.shortcuts import redirect

        return redirect(self.success_url)


class InvoiceDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ("invoices.view_invoice",)
    model = Invoice
    template_name = "invoices/invoice_detail.html"

    def get_object(self, queryset=None):
        """
        Returns the object the view is displaying.
        It can be used to call the same view with different arguments of the same type (eg. int:pk and int:doc_application_pk).
        """
        doc_application_pk = self.kwargs.get("doc_application_pk", None)
        if doc_application_pk:
            invoice = get_object_or_404(Invoice, invoice_applications__customer_application__pk=doc_application_pk)
            return invoice
        else:
            return super().get_object()

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["invoice_applications"] = self.object.invoice_applications.all()
        data["today"] = timezone.now().date()
        return data


class InvoiceMarkAsPaidView(PermissionRequiredMixin, View):
    """
    View to mark an invoice as paid by creating payments for all unpaid invoice applications
    """

    permission_required = ("payments.add_payment",)

    def post(self, request, *args, **kwargs):
        invoice_id = kwargs.get("pk")
        invoice = get_object_or_404(Invoice, pk=invoice_id)

        payment_type = request.POST.get("payment_type")
        payment_date_str = request.POST.get("payment_date")

        if not payment_type or not payment_date_str:
            messages.error(request, "Payment type and payment date are required.")
            return redirect("invoice-detail", pk=invoice_id)

        try:
            from datetime import datetime

            payment_date = datetime.strptime(payment_date_str, "%Y-%m-%d").date()
        except ValueError:
            messages.error(request, "Invalid payment date format.")
            return redirect("invoice-detail", pk=invoice_id)

        # Import Payment model
        from payments.models import Payment

        # Get all unpaid invoice applications
        unpaid_applications = [app for app in invoice.invoice_applications.all() if app.due_amount > 0]

        if not unpaid_applications:
            messages.warning(request, "No unpaid invoice applications found.")
            return redirect("invoice-detail", pk=invoice_id)

        # Create payments for each unpaid application
        payments_created = 0
        with transaction.atomic():
            for invoice_app in unpaid_applications:
                Payment.objects.create(
                    invoice_application=invoice_app,
                    from_customer=invoice.customer,
                    payment_date=payment_date,
                    amount=invoice_app.due_amount,
                    payment_type=payment_type,
                    created_by=request.user,
                )
                payments_created += 1

        messages.success(
            request, f"Successfully created {payments_created} payment(s) for invoice {invoice.invoice_no_display}"
        )
        return redirect("invoice-detail", pk=invoice_id)


class InvoiceDeleteAllView(PermissionRequiredMixin, View):
    """
    Superuser-only view to delete all invoices.
    Requires confirmation via POST request.
    """

    permission_required = ("invoices.delete_invoice",)

    def dispatch(self, request, *args, **kwargs):
        # Only superusers can access this view
        if not request.user.is_superuser:
            messages.error(request, "You do not have permission to perform this action.")
            return redirect("invoice-list")
        return super().dispatch(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        """Delete all invoices, and optionally all related customer applications (DocApplication)."""
        from customer_applications.models.doc_application import DocApplication

        delete_customer_apps = request.POST.get("delete_customer_applications") == "yes"
        try:
            count = Invoice.objects.count()
            if delete_customer_apps:
                # Collect all DocApplications linked to any invoice
                doc_app_ids = set()
                for invoice in Invoice.objects.all():
                    for inv_app in invoice.invoice_applications.all():
                        if inv_app.customer_application_id:
                            doc_app_ids.add(inv_app.customer_application_id)
                with transaction.atomic():
                    Invoice.objects.all().delete()
                    # Delete all collected DocApplications
                    DocApplication.objects.filter(id__in=doc_app_ids).delete()
                messages.success(
                    request, f"Successfully deleted {count} invoice(s) and all corresponding customer applications."
                )
            else:
                with transaction.atomic():
                    Invoice.objects.all().delete()
                messages.success(request, f"Successfully deleted {count} invoice(s).")
        except Exception as e:
            messages.error(request, f"Error deleting invoices: {str(e)}")

        return redirect("invoice-list")
