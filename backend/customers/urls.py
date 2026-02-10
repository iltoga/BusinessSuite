from django.urls import path

from .views import (
    CustomerAnalysisView,
    CustomerCreateView,
    CustomerDeleteAllView,
    CustomerDeleteView,
    CustomerDetailView,
    CustomerListView,
    CustomerUpdateView,
)

urlpatterns = [
    # path('', views.home, name='home'),
    path("list/", CustomerListView.as_view(), name="customer-list"),
    path("create/", CustomerCreateView.as_view(), name="customer-create"),
    path("update/<int:pk>/", CustomerUpdateView.as_view(), name="customer-update"),
    path("delete/<int:pk>/", CustomerDeleteView.as_view(), name="customer-delete"),
    path("delete-all/", CustomerDeleteAllView.as_view(), name="customer-delete-all"),
    path("detail/<int:pk>/", CustomerDetailView.as_view(), name="customer-detail"),
    path("chart/analysis/<str:plot_type>/", CustomerAnalysisView.as_view(), name="customer-chart-analysis"),
]
