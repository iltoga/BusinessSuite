from django_unicorn.components import QuerySetType

from core.components.unicorn_model_view import UnicornModelView
from customer_applications.models import DocApplication, DocWorkflow


class DocapplicationDetailView(UnicornModelView):
    docapplication: QuerySetType[DocApplication] = DocApplication.objects.none()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docapplication_pk = kwargs.get("docapplication_pk")
        # get the model instance
        self.docapplication = DocApplication.objects.get(pk=self.docapplication_pk)

    def update_status(self, docworkflow_pk, new_status):
        # get the model instance
        workflow = DocWorkflow.objects.get(pk=docworkflow_pk)
        # update the workflow status based on dropdown selection
        workflow.status = new_status
        # update the updated by and updated_at field
        workflow.updated_by = self.request.user
        workflow.save()
        # update the docapplication updated_by field
        self.docapplication.updated_by = self.request.user
        self.docapplication.save()
