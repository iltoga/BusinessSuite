from django.urls import path
from django.views.generic import DetailView

from customer_applications.models.doc_workflow import DocWorkflow

from .views import (
    DocApplicationCreateView,
    DocApplicationDeleteView,
    DocApplicationDetailView,
    DocApplicationListView,
    DocApplicationUpdateView,
    DocWorkflowCreateView,
    DocWorkflowUpdateView,
    RequiredDocumentDetailView,
    RequiredDocumentUpdateView,
)

urlpatterns = [
    path(
        "list/",
        DocApplicationListView.as_view(),
        name="customer-application-list",
    ),
    path(
        "create/",
        DocApplicationCreateView.as_view(),
        name="customer-application-create",
    ),
    path(
        "detail/<int:pk>/",
        DocApplicationDetailView.as_view(),
        name="customer-application-detail",
    ),
    path(
        "update/<int:pk>/",
        DocApplicationUpdateView.as_view(),
        name="customer-application-update",
    ),
    path(
        "update_required_document/<int:pk>/",
        RequiredDocumentUpdateView.as_view(),
        name="customer-application-requireddocument-update",
    ),
    path(
        "required_document_detail/<int:pk>/",
        RequiredDocumentDetailView.as_view(),
        name="customer-application-requireddocument-detail",
    ),
    path(
        "create_doc_workflow/<int:docapplication_pk>/<int:step_no>",
        DocWorkflowCreateView.as_view(),
        name="customer-application-docworkflow-create",
    ),
    path(
        "update_doc_workflow/<int:pk>",
        DocWorkflowUpdateView.as_view(),
        name="customer-application-docworkflow-update",
    ),
    path(
        "doc_workflow_detail/<int:pk>/",
        DetailView.as_view(model=DocWorkflow, template_name="customer_applications/docworkflow_detail.html"),
        name="customer-application-docworkflow-detail",
    ),
    path(
        "delete/<int:pk>/",
        DocApplicationDeleteView.as_view(),
        name="customer-application-delete",
    ),
]
