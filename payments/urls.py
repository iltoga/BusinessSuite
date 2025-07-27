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
