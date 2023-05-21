from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from customers.models import Customer
from .views import NewCustomerView, CustomerListView, UpdateCustomerView

urlpatterns = [
    # path('', views.home, name='home'),
    path('list/', CustomerListView.as_view(), name='list'),
    path('create/', NewCustomerView.as_view(), name='create'),
    path('update/<int:pk>/', UpdateCustomerView.as_view(), name='update'),
    # path('delete/<int:pk>/', DeleteView.as_view(model=Customer, success_url='/customers/list/'), name='delete'),
    # path('detail/<int:pk>/', DetailView.as_view(model=Customer), name='detail'),
]
