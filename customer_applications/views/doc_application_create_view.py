from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.db import transaction
from django.urls import reverse_lazy
from django.views.generic import CreateView
from customer_applications.forms import DocApplicationFormCreate, RequiredDocumentCreateFormSet
from customer_applications.models import DocApplication

class DocApplicationCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ('customer_applications.add_docapplication',)
    model = DocApplication
    form_class = DocApplicationFormCreate
    template_name = 'customer_applications/docapplication_create.html'
    success_url = reverse_lazy('customer-application-list')
    success_message = 'Customer application created successfully!'
    action_name = 'Create'

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        if self.request.POST:
            data['requireddocuments'] = RequiredDocumentCreateFormSet(self.request.POST, prefix='requireddocuments')
        else:
            data['requireddocuments'] = RequiredDocumentCreateFormSet(prefix='requireddocuments')
        return data

    def form_valid(self, form):
        context = self.get_context_data()
        required_documents = context['requireddocuments']
        form.instance.created_by = self.request.user
        with transaction.atomic():
            self.object = form.save()
            if required_documents.is_valid():
                required_documents.instance = self.object
                required_documents.save(commit=False)
                for required_document in required_documents:
                    required_document.instance.created_by = self.request.user
                    if required_document.cleaned_data and not required_document.cleaned_data.get('DELETE'):
                        if 'file' in required_document.files:
                            required_document.instance.file = required_document.files['file']
                        if 'metadata' in required_document.cleaned_data:
                            required_document.instance.metadata = required_document.cleaned_data['metadata']
                        required_document.instance.save()
            else:
                return super().form_invalid(form)  # If formset is invalid, don't save the form either
        return super().form_valid(form)