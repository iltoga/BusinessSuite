from django.shortcuts import redirect, render
from django.views import View
from .models import DocApplication, DocWorkflow, RequiredDocument
from .forms import DocApplicationForm, DocWorkflowForm, RequiredDocumentForm

class NewDocApplicationView(View):
    permission_required = ('customer_applications.add_doc_application',)

    def get(self, request):
        docapplication_form = DocApplicationForm()
        return render(request, 'new_docapplication.html', {'docapplication_form': docapplication_form})

    def post(self, request):
        docapplication_form = DocApplicationForm(request.POST)
        if docapplication_form.is_valid():
            docapplication = docapplication_form.save()

            required_documents = docapplication.product.required_documents.split(',')
            for doc_name in required_documents:
                RequiredDocument.objects.create(doc_application=docapplication, name=doc_name.strip())

            return redirect('docworkflow_create', docapplication_id=docapplication.id)
        return render(request, 'new_docapplication.html', {'docapplication_form': docapplication_form})

class DocWorkflowCreateView(View):
    def get(self, request, docapplication_id):
        docworkflow_form = DocWorkflowForm(initial={'doc_application': docapplication_id})
        return render(request, 'docworkflow_create.html', {'docworkflow_form': docworkflow_form})

    def post(self, request, docapplication_id):
        docworkflow_form = DocWorkflowForm(request.POST)
        if docworkflow_form.is_valid():
            docworkflow = docworkflow_form.save()
            return redirect('docapplication_detail', docapplication_id=docapplication_id)
        return render(request, 'docworkflow_create.html', {'docworkflow_form': docworkflow_form})
