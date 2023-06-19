from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.http import Http404
from django.urls import reverse_lazy
from django.utils import timezone
from django.views.generic import CreateView

from core.utils.dateutils import calculate_due_date
from customer_applications.forms import DocWorkflowForm
from customer_applications.models import DocApplication, DocWorkflow
from products.models import Task


class DocWorkflowCreateView(PermissionRequiredMixin, SuccessMessageMixin, CreateView):
    permission_required = ("customer_applications.add_docworkflow",)
    model = DocWorkflow
    form_class = DocWorkflowForm
    template_name = "customer_applications/docworkflow_form.html"
    success_message = "Customer applicaion updated successfully!"

    doc_application = None
    task = None
    action_name = "Create"

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        self.doc_application = DocApplication.objects.get(id=self.kwargs["docapplication_pk"])
        if not self.doc_application.product:
            raise Http404
        self.task = Task.objects.get(step=self.kwargs["step_no"], product=self.doc_application.product)
        if not self.task:
            raise Http404
        # get the current workflow. if there is one, set start_date to the current workflow's completion_date (if any), otherwise set it to now
        # use docapplication relation to get the current workflow
        current_workflow = self.doc_application.current_workflow
        if current_workflow and current_workflow.completion_date:
            start_date = current_workflow.completion_date
        else:
            start_date = timezone.now()

        # calculate_workflow_due_date due date from task duration, using dateutils calculate_due_date
        # Take in account if task duration_is_business_days
        business_days = self.task.duration_is_business_days
        duration = self.task.duration
        default_due_date = calculate_due_date(start_date, duration, business_days)
        kwargs["initial"] = {
            "task": self.task,
            "due_date": default_due_date,
            "doc_application": self.doc_application,
        }
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        # Add some useful data to the context for the template to use
        data["docapplication"] = self.doc_application
        data["task"] = self.task
        data["action_name"] = self.action_name
        return data

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        form.instance.task = self.task
        form.instance.doc_application = self.doc_application
        return super().form_valid(form)
