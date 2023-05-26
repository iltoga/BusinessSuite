from django.urls import path
from . import views

urlpatterns = [
    path('customers/', views.get_customers),
    path('products/', views.get_products),
    path('products/get_required_documents/<int:product_id>/', views.get_required_documents),
    path('products/get_products_by_product_type/<str:product_type>/', views.get_products_by_product_type),
]