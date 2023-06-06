from django_unicorn.components import QuerySetType
from core.components.unicorn_model_view import UnicornModelView
from customer_applications.models import DocApplication, DocWorkflow

class DocapplicationDetailView(UnicornModelView):
    workflows: QuerySetType[DocWorkflow] = DocWorkflow.objects.none()

    def mount(self):
        #FIXME: delete this if unused
        if self.model:
            self.model = DocApplication.objects.get(pk=self.model)
            self.workflows = self.model.workflows.all()

    def complete_workflow(self, docworkflow_pk):
        # get the model instance
        workflow = DocWorkflow.objects.get(pk=docworkflow_pk)
        # update the workflow status to completed
        workflow.status = workflow.STATUS_COMPLETED
        workflow.save()
        # re-fetch the model and let mount() method update the workflows
        self.model = DocApplication.objects.get(pk=self.model.pk)
        self.workflows = self.model.workflows.all()




