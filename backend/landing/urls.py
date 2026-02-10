from django.urls import path

from . import views

urlpatterns = [
    # path('', views.home, name='home'),
    path("login/", views.ConditionalLoginView.as_view(), name="login"),
    path("logout/", views.logout_view, name="logout"),
]
