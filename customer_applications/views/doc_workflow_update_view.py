from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView

from customer_applications.forms import DocWorkflowForm
from customer_applications.models import DocWorkflow


class DocWorkflowUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ("customer_applications.change_docworkflow",)
    model = DocWorkflow
    form_class = DocWorkflowForm
    template_name = "customer_applications/docworkflow_form.html"
    success_message = "Customer applicaion updated successfully!"

    doc_application = None
    task = None
    action_name = "Update"

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        # Add some useful data to the context for the template to use
        data["docapplication"] = self.object.doc_application
        data["task"] = self.object.task
        data["action_name"] = self.action_name
        return data

    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)

    # Note that this method is called when valid form data has been POSTed.
    # if we update the status via unicorn view, it will be skipped because `update_status` method saves the model directly
    def save(self, commit=True):
        self.instance = super().save(commit=False)  # Instance of model
        # add the updated_by field to the doc_application
        self.instance.doc_application.updated_by = self.request.user
        # save the doc_application
        self.instance.doc_application.save()
        # save the instance
        if commit:
            self.instance.save()
        return self.instance
