from django import forms
from django.utils import timezone

from customer_applications.models import DocWorkflow


class DocWorkflowForm(forms.ModelForm):
    class Meta:
        model = DocWorkflow
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
        self.doc_application = kwargs.pop("doc_application", None)
        super(DocWorkflowForm, self).__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        self.clean_dates(cleaned_data)
        return cleaned_data

    def save(self, commit=True):
        doc_workflow = super().save()
        self.update_doc_application(doc_workflow)
        return doc_workflow

    # Custom methods
    def clean_dates(self, cleaned_data):
        start_date = cleaned_data.get("start_date")
        due_date = cleaned_data.get("due_date")
        completion_date = cleaned_data.get("completion_date")

        if self.doc_application:
            self.check_start_date_after_doc_date(start_date)
        self.check_due_date_after_start_date(start_date, due_date)
        self.check_completion_date_after_due_date(completion_date, due_date)

    def check_start_date_after_doc_date(self, start_date):
        doc_date = None
        if self.doc_application:
            doc_date = self.doc_application.doc_date
        if start_date and doc_date and start_date < doc_date:
            doc_date_fmt = doc_date.strftime("%d/%m/%Y")
            self.add_error(
                "start_date", f"Start date must be after document's application date, which is {doc_date_fmt}."
            )

    def check_due_date_after_start_date(self, start_date, due_date):
        if start_date and due_date and due_date < start_date:
            self.add_error("due_date", "Due date must be after start date.")

    def check_completion_date_after_due_date(self, completion_date, due_date):
        if completion_date and due_date and completion_date < due_date:
            self.add_error("completion_date", "Completion date must be after due date.")

    def update_doc_application(self, doc_workflow):
        doc_workflow.doc_application.updated_by = self.user
        doc_workflow.doc_application.save()
