from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from products.forms import ProductForm, TaskModelFormSet
from products.models import Product, Task


class ProductUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("products.change_product",)
    model = Product
    form_class = ProductForm
    template_name = "products/product_form.html"
    success_url = reverse_lazy("product-list")
    success_message = "Product updated successfully!"

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        data["action_name"] = "Update"
        if self.request.POST:
            data["tasks"] = TaskModelFormSet(self.request.POST, instance=self.object, prefix="tasks")
        else:
            data["tasks"] = TaskModelFormSet(instance=self.object, prefix="tasks")
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        tasks_formset = context["tasks"]

        if tasks_formset.is_valid():
            with transaction.atomic():
                # Get ordered document PKs from POST data (preserves drag-drop order)
                required_pks = self.request.POST.getlist("required_documents_multiselect")
                if not required_pks:
                    self.object.required_documents = ""
                else:
                    # Fetch documents and build ordered string
                    from products.models import DocumentType

                    docs_by_pk = {str(d.pk): d for d in DocumentType.objects.filter(pk__in=required_pks)}
                    ordered_names = [docs_by_pk[pk].name for pk in required_pks if pk in docs_by_pk]
                    self.object.required_documents = ",".join(ordered_names)

                optional_pks = self.request.POST.getlist("optional_documents_multiselect")
                if not optional_pks:
                    self.object.optional_documents = ""
                else:
                    from products.models import DocumentType

                    docs_by_pk = {str(d.pk): d for d in DocumentType.objects.filter(pk__in=optional_pks)}
                    ordered_names = [docs_by_pk[pk].name for pk in optional_pks if pk in docs_by_pk]
                    self.object.optional_documents = ",".join(ordered_names)

                self.object = form.save()

                for form in tasks_formset:
                    # check if form instance already exists in the db or it's a new instance
                    if form.instance.pk is None:
                        form.instance.product = self.object
                    form.save()
                return super().form_valid(form)

        return super().form_invalid(form)
