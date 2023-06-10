from django.contrib.auth.mixins import PermissionRequiredMixin
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.views.generic import UpdateView
from customer_applications.forms import DocWorkflowForm
from customer_applications.models import DocWorkflow

class DocWorkflowUpdateView(PermissionRequiredMixin, SuccessMessageMixin, UpdateView):
    permission_required = ('customer_applications.change_docworkflow',)
    model = DocWorkflow
    form_class = DocWorkflowForm
    template_name = 'customer_applications/docworkflow_form.html'
    success_message = 'Customer applicaion updated successfully!'

    doc_application = None
    task = None
    action_name = 'Update'

    def get_success_url(self):
        return reverse_lazy('customer-application-detail', kwargs={'pk': self.object.doc_application.id})

    # def get_form_kwargs(self):
    #     kwargs = super().get_form_kwargs()
    #     self.doc_application = DocApplication.objects.get(id=self.kwargs['pk'])
    #     if not self.doc_application.product:
    #         raise Http404
    #     self.task = Task.objects.get(step=self.kwargs['step_no'], product=self.doc_application.product)
    #     if not self.task:
    #         raise Http404
    #     kwargs['initial'] = {
    #         'task': self.task,
    #         'due_date': timezone.now() + timezone.timedelta(days=self.task.duration),
    #     }
    #     return kwargs

    def get_context_data(self, **kwargs):
        data = super().get_context_data(**kwargs)
        # Add some useful data to the context for the template to use
        data['docapplication'] = self.object.doc_application
        data['task'] = self.object.task
        data['action_name'] = self.action_name
        return data


    def form_valid(self, form):
        form.instance.updated_by = self.request.user
        return super().form_valid(form)
