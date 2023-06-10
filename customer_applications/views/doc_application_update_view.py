from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from customer_applications.forms import DocApplicationFormUpdate, RequiredDocumentUpdateFormSet
from customer_applications.models import DocApplication

class DocApplicationUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('customer_applications.change_docapplication',)
    model = DocApplication
    form_class = DocApplicationFormUpdate
    template_name = 'customer_applications/docapplication_update.html'
    success_url = reverse_lazy('customer-application-list')
    success_message = 'Customer application created successfully!'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['requireddocuments'] = RequiredDocumentUpdateFormSet(self.request.POST, instance=self.object, prefix='requireddocuments')
        else:
            data['requireddocuments'] = RequiredDocumentUpdateFormSet(instance=self.object, prefix='requireddocuments')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        required_documents = context['requireddocuments']
        form.instance.updated_by = self.request.user
        with transaction.atomic():
            self.object = form.save(commit=False)  # Don't save it yet
            if required_documents.is_valid():
                required_documents.instance = self.object
                required_documents.save(commit=False)
                for required_document in required_documents:
                    required_document.instance.updated_by = self.request.user
                    if required_document.cleaned_data and not required_document.cleaned_data.get('DELETE'):
                        if 'file' in required_document.files:
                            required_document.instance.file = required_document.files['file']
                        if 'metadata' in required_document.cleaned_data:
                            required_document.instance.metadata = required_document.cleaned_data['metadata']
                        required_document.instance.save()
                self.object.save()  # Now save the form

        return super().form_valid(form)
