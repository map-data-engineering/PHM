from django.urls import path

from . import views

app_name = "siting"

urlpatterns = [
    path("nearest-outlets/", views.NearestOutletsView.as_view(), name="nearest-outlets"),
    path("site-check/", views.SiteCheckView.as_view(), name="site-check"),
]
