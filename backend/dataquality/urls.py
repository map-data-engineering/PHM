from django.urls import include, path

from . import views

app_name = "dataquality"

urlpatterns = [
    path("data-quality/", views.dashboard_page, name="dashboard-page"),
    path("api/v1/", include("dataquality.api_urls")),
]
