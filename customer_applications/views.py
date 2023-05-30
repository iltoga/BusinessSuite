from django.urls import reverse_lazy
from django.db import transaction
from django.views.generic import ListView, CreateView, UpdateView, DetailView, DeleteView
from .models import DocApplication, RequiredDocument
from .forms import DocApplicationFormCreate, RequiredDocumentCreateFormSet, RequiredDocumentUpdateFormSet, RequiredDocumentUpdateForm, DocApplicationFormUpdate
from django.contrib.messages.views import SuccessMessageMixin
from django.contrib.auth.mixins import PermissionRequiredMixin

class DocApplicationListView(PermissionRequiredMixin, ListView):
    permission_required = ('customer_applications.view_docapplication',)
    model = DocApplication
    paginate_by = 15
    template_name = 'customer_applications/docapplication_list.html'

    def get_queryset(self):
        queryset = super().get_queryset()
        query = self.request.GET.get('q')
        if query:
            queryset = self.model.objects.search_doc_applications(query)
        return queryset

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
                        required_document.instance.save()
            else:
                return super().form_invalid(form)  # If formset is invalid, don't save the form either
        return super().form_valid(form)


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
                        required_document.instance.save()
                self.object.save()  # Now save the form

        return super().form_valid(form)

# detail view
class DocApplicationDetailView(PermissionRequiredMixin, DetailView):
    permission_required = ('customer_applications.view_docapplication',)
    model = DocApplication
    template_name = 'customer_applications/docapplication_detail.html'
    field_permissions = {
        'created_by': ['customer_applications.can_audit'],
        'created_at': ['customer_applications.can_audit'],
        'updated_at': ['customer_applications.can_audit'],
    }


#delete confirmation view
class DocApplicationDeleteView(PermissionRequiredMixin, SuccessMessageMixin, DeleteView):
    permission_required = ('customer_applications.delete_docapplication',)
    model = DocApplication
    template_name = 'customer_applications/docapplication_delete.html'
    success_url = reverse_lazy('customer-application-list')
    success_message = 'Customer application deleted successfully!'

# update required document
class RequiredDocumentUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('customer_applications.change_requireddocument',)
    model = RequiredDocument
    form_class = RequiredDocumentUpdateForm
    template_name = 'customer_applications/requireddocument_update.html'
    success_message = 'Required document updated successfully!'

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('customer-application-detail', kwargs={'pk': self.object.doc_application.id})
