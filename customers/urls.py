from django.urls import path
from django.contrib.auth import views as auth_views
from django.views.generic import TemplateView, ListView, CreateView, UpdateView, DeleteView, DetailView
from customers.models import Customer
from .views import CustomerCreateView, CustomerListView, CustomerUpdateView, CustomerSearchApiView

urlpatterns = [
    # path('', views.home, name='home'),
    path('list/', CustomerListView.as_view(), name='list'),
    path('create/', CustomerCreateView.as_view(), name='create'),
    path('update/<int:pk>/', CustomerUpdateView.as_view(), name='update'),
    path('delete/<int:pk>/', DeleteView.as_view(model=Customer, success_url='/customers/list/'), name='delete'),
    path('api/search/', CustomerSearchApiView.as_view(), name='api_search'),
    path('detail/<int:pk>/', DetailView.as_view(model=Customer), name='detail'),
]
