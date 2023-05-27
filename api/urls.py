from django.urls import path, include
from rest_framework.authtoken import views as auth_views
from . import views

urlpatterns = [
    path('api-token-auth/', auth_views.obtain_auth_token),
    path('session-auth/', include('rest_framework.urls', namespace='rest_framework')),
    path('customers/', views.CustomersView.as_view()),
    # the view requires a 'q' parameter with the query string
    path('customers/search/', views.SearchCustomers.as_view(), name='api-customer-search'),
    path('products/', views.ProductsView.as_view()),
    path('products/get_required_documents/<int:product_id>/', views.RequiredDocumentsView.as_view()),
    path('products/get_products_by_product_type/<str:product_type>/', views.ProductsByTypeView.as_view()),
]
