from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from customer_applications.forms import RequiredDocumentUpdateForm
from customer_applications.models import RequiredDocument

class RequiredDocumentUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('customer_applications.change_requireddocument',)
    model = RequiredDocument
    form_class = RequiredDocumentUpdateForm
    template_name = 'customer_applications/requireddocument_update.html'
    success_message = 'Required document updated successfully!'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        form_instance = context['form']
        context['product_doc_type'] = form_instance.product_doc_type
        return context

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('customer-application-detail', kwargs={'pk': self.object.doc_application.id})
