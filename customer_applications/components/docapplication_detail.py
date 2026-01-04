from core.components.unicorn_model_view import UnicornModelView
from customer_applications.models import DocApplication, DocWorkflow


class DocapplicationDetailView(UnicornModelView):
    docapplication_pk: int | None = None
    docapplication: DocApplication | None = None

    class Meta:
        # Keep the model instance available to the template, but do not serialize it
        # into Unicorn's frontend JSON (orjson in production will raise TypeError).
        javascript_exclude = ("docapplication",)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.docapplication_pk = kwargs.get("docapplication_pk")
        # get the model instance
        if self.docapplication_pk:
            self.docapplication = DocApplication.objects.select_related("product", "customer").get(
                pk=self.docapplication_pk
            )

    def update_status(self, docworkflow_pk, new_status):
        if not self.docapplication_pk:
            return
        # get the model instance
        workflow = DocWorkflow.objects.get(pk=docworkflow_pk)
        # update the workflow status based on dropdown selection
        workflow.status = new_status
        # update the updated by and updated_at field
        workflow.updated_by = self.request.user
        workflow.save()
        # update the docapplication updated_by field
        DocApplication.objects.filter(pk=self.docapplication_pk).update(updated_by=self.request.user)
