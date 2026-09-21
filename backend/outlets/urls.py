from django.urls import include, path

from . import views

app_name = "outlets"

urlpatterns = [
    path("registry/", views.registry_page, name="registry-page"),
    path("api/v1/", include("outlets.api_urls")),
]
