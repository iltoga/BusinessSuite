from django.urls import path

from . import views

urlpatterns = [
    path("list/", views.InvoiceListView.as_view(), name="invoice-list"),
    path("create/<int:customer_id>/", views.InvoiceCreateView.as_view(), name="invoice-create-by-customer"),
    path("create/", views.InvoiceCreateView.as_view(), name="invoice-create"),
    path(
        "create-by-app/<int:doc_application_pk>",
        views.InvoiceCreateView.as_view(),
        name="invoice-create-by-doc-application",
    ),
    path("update/<int:pk>/", views.InvoiceUpdateView.as_view(), name="invoice-update"),
    path("delete/<int:pk>/", views.InvoiceDeleteView.as_view(), name="invoice-delete"),
    path("detail/<int:pk>/", views.InvoiceDetailView.as_view(), name="invoice-detail"),
    path(
        "detail-by-app/<int:doc_application_pk>/",
        views.InvoiceDetailView.as_view(),
        name="invoice-detail-by-doc-application",
    ),
    path("download/<int:pk>", views.InvoiceDownloadView.as_view(), name="invoice-download"),
    # Add paths for InvoiceApplication and Payment views here
    path(
        "invoiceapplication/<int:pk>/update/",
        views.InvoiceApplicationUpdateView.as_view(),
        name="invoiceapplication-update",
    ),
    path(
        "invoiceapplication/<int:pk>/", views.InvoiceApplicationDetailView.as_view(), name="invoiceapplication-detail"
    ),
]
