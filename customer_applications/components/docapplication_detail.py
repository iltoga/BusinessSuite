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

    def reopen_application(self):
        """
        Re-opens a completed application by setting its status back to processing
        and reverting the last completed workflow step if it exists.
        """
        if not self.docapplication_pk:
            return

        # Reload the application to ensure we have the latest state
        self.docapplication = DocApplication.objects.get(pk=self.docapplication_pk)

        if self.docapplication.status == DocApplication.STATUS_COMPLETED:
            # Change status back to processing
            self.docapplication.status = DocApplication.STATUS_PROCESSING
            self.docapplication.updated_by = self.request.user

            # If there are workflows, mark the last completed one as processing
            last_workflow = self.docapplication.workflows.order_by("-task__step").first()
            if last_workflow and last_workflow.status == DocWorkflow.STATUS_COMPLETED:
                last_workflow.status = DocWorkflow.STATUS_PROCESSING
                last_workflow.updated_by = self.request.user
                last_workflow.save()

            # Save the application, skipping automatic status calculation to maintain 'processing'
            self.docapplication.save(skip_status_calculation=True)

            # Re-fetch for template rendering with relations
            self.docapplication = DocApplication.objects.select_related("product", "customer").get(
                pk=self.docapplication_pk
            )
