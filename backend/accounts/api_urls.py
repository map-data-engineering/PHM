from django.urls import path

from . import views

urlpatterns = [
    path("auth/login/", views.ApiTokenLoginView.as_view(), name="api-login"),
    path("auth/logout/", views.ApiTokenLogoutView.as_view(), name="api-logout"),
    path("auth/me/", views.ApiMeView.as_view(), name="api-me"),
]
