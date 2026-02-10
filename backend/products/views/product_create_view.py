from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView

from products.forms import ProductForm, TaskModelFormSet
from products.models import Product


class ProductCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("products.add_product",)
    model = Product
    form_class = ProductForm
    template_name = "products/product_form.html"
    success_url = reverse_lazy("product-list")
    success_message = "Product created successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["action_name"] = "Create"

        if self.request.POST:
            data["tasks"] = TaskModelFormSet(self.request.POST, prefix="tasks")
        else:
            data["tasks"] = TaskModelFormSet(prefix="tasks")
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks = context["tasks"]

        # Check if tasks formset and required_documents formset are valid
        if tasks.is_valid():
            with transaction.atomic():
                # Get ordered document PKs from POST data (preserves drag-drop order)
                required_pks = self.request.POST.getlist("required_documents_multiselect")
                if not required_pks:
                    form.instance.required_documents = ""
                else:
                    # Fetch documents and build ordered string
                    from products.models import DocumentType

                    docs_by_pk = {str(d.pk): d for d in DocumentType.objects.filter(pk__in=required_pks)}
                    ordered_names = [docs_by_pk[pk].name for pk in required_pks if pk in docs_by_pk]
                    form.instance.required_documents = ",".join(ordered_names)

                optional_pks = self.request.POST.getlist("optional_documents_multiselect")
                if not optional_pks:
                    form.instance.optional_documents = ""
                else:
                    from products.models import DocumentType

                    docs_by_pk = {str(d.pk): d for d in DocumentType.objects.filter(pk__in=optional_pks)}
                    ordered_names = [docs_by_pk[pk].name for pk in optional_pks if pk in docs_by_pk]
                    form.instance.optional_documents = ",".join(ordered_names)

                self.object = form.save()
                tasks.instance = self.object
                # Save the tasks formset
                tasks.save()
                return super().form_valid(form)

        # If either formset is not valid, don't save anything
        return super().form_invalid(form)
