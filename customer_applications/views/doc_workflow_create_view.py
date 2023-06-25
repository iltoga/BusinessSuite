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
    success_message = "Customer application updated successfully!"

    action_name = "Create"

    def get_success_url(self):
        return reverse_lazy("customer-application-detail", kwargs={"pk": self.object.doc_application.id})

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs.update({"user": self.request.user})
        doc_application = self.get_doc_application()
        task = self.get_task(doc_application)
        start_date = self.get_workflow_start_date(doc_application)
        default_due_date = self.get_default_due_date(start_date, task)
        kwargs["initial"] = {
            "task": task,
            "due_date": default_due_date,
            "doc_application": doc_application,
        }
        return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        doc_application = self.get_doc_application()
        task = self.get_task(doc_application)
        data.update({"docapplication": doc_application, "task": task, "action_name": self.action_name})
        return data

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        doc_application = self.get_doc_application()
        task = self.get_task(doc_application)
        form.instance.task = task
        form.instance.doc_application = doc_application
        return super().form_valid(form)

    def get_doc_application(self):
        doc_application = DocApplication.objects.filter(id=self.kwargs["docapplication_pk"]).first()
        if doc_application and doc_application.product:
            return doc_application
        raise Http404

    def get_task(self, doc_application):
        task = Task.objects.filter(step=self.kwargs["step_no"], product=doc_application.product).first()
        if task:
            return task
        raise Http404

    def get_workflow_start_date(self, doc_application):
        current_workflow = getattr(doc_application, "current_workflow", None)
        if current_workflow and getattr(current_workflow, "completion_date", None):
            return current_workflow.completion_date
        return timezone.now()

    def get_default_due_date(self, start_date, task):
        business_days = getattr(task, "duration_is_business_days", None)
        duration = getattr(task, "duration", None)
        if business_days is not None and duration is not None:
            return calculate_due_date(start_date, duration, business_days)
        raise Http404
