"""
FILE_ROLE: URL routing for the payments app.

KEY_COMPONENTS:
- Module body: configuration, helpers, or script entrypoints.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for app routing, model behavior, and service boundaries.
"""

from django.urls import path

from . import views

urlpatterns = [
    path("list/", views.PaymentListView.as_view(), name="payment-list"),
    path("create/", views.CreatePaymentView.as_view(), name="payment-create"),
    path("create/by-customer/<int:customer_pk>/", views.CreatePaymentView.as_view(), name="payment-by-customer-create"),
    path(
        "create/by-invoice-application/<int:invoice_application_pk>/",
        views.CreatePaymentView.as_view(),
        name="payment-by-invoice-application-create",
    ),
    path("update/<int:pk>/", views.UpdatePaymentView.as_view(), name="payment-update"),
    path("delete/<int:pk>/", views.DeletePaymentView.as_view(), name="payment-delete"),
    path("detail/<int:pk>/", views.PaymentDetailView.as_view(), name="payment-detail"),
]
