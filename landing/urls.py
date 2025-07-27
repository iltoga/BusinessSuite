from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    # path('', views.home, name='home'),
    path("login/", auth_views.LoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
]
