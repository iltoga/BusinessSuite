from django import forms
from django.utils import timezone

from customer_applications.models import DocWorkflow


class DocWorkflowForm(forms.ModelForm):
    class Meta:
        model = DocWorkflow
        # fields = ['status', 'comment']
        exclude = ["completion_date", "user", "created_at", "created_by"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 5, "class": "col-md-12"}),
            "start_date": forms.DateInput(
                attrs={"type": "date", "value": timezone.now().strftime("%Y-%m-%d"), "class": "col-md-4"}
            ),
            "due_date": forms.DateInput(attrs={"type": "date", "class": "col-md-4"}),
            "status": forms.Select(attrs={"class": "col-md-4"}),
            "doc_application": forms.HiddenInput(),
            "task": forms.HiddenInput(),
            "updated_by": forms.HiddenInput(),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop("user", None)
        super(DocWorkflowForm, self).__init__(*args, **kwargs)
        self.doc_application = kwargs.pop("doc_application", None)

    def clean_status(self):
        status = self.cleaned_data.get("status")
        if status not in [x[0] for x in DocWorkflow.STATUS_CHOICES]:
            self.add_error("status", "Invalid workflow status.")
        return status

    def clean(self):
        cleaned_data = super().clean()

        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")
        completion_date = cleaned_data.get("completion_date")
        if self.doc_application:
            doc_date = self.instance.doc_application.doc_date
            if start_date and doc_date and start_date < doc_date:
                doc_date_fmt = doc_date.strftime("%d/%m/%Y")
                self.add_error(
                    "start_date", f"Start date must be after document's application date, which is {doc_date_fmt}."
                )

        if start_date and due_date and due_date < start_date:
            self.add_error("due_date", "Due date must be after start date.")

        if completion_date and due_date and completion_date < due_date:
            self.add_error("completion_date", "Completion date must be after due date.")

        return cleaned_data

    def save(self, commit=True):
        doc_workflow = super().save()
        # update the doc_application's updated_by field with the current user
        doc_workflow.doc_application.updated_by = self.user
        doc_workflow.doc_application.save()
        return doc_workflow
