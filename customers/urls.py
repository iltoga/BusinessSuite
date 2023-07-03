from django.urls import path
from django.views.generic import DetailView

from customers.models import Customer

from .views import CustomerCreateView, CustomerDeleteView, CustomerListView, CustomerUpdateView

urlpatterns = [
    # path('', views.home, name='home'),
    path("list/", CustomerListView.as_view(), name="customer-list"),
    path("create/", CustomerCreateView.as_view(), name="customer-create"),
    path("update/<int:pk>/", CustomerUpdateView.as_view(), name="customer-update"),
    path("delete/<int:pk>/", CustomerDeleteView.as_view(), name="customer-delete"),
    path("detail/<int:pk>/", DetailView.as_view(model=Customer), name="customer-detail"),
]
