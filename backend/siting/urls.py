from django.urls import include, path

from . import views

app_name = "siting"

urlpatterns = [
    path("find-pharmacy/", views.find_pharmacy_page, name="find-pharmacy-page"),
    path("site-check/", views.site_check_page, name="site-check-page"),
    path("api/v1/", include("siting.api_urls")),
]
