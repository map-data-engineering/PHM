from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("api/v1/", include("accounts.api_urls")),
    path("api/v1/", include("outlets.api_urls")),
    path("api/v1/", include("siting.api_urls")),
    path("api/v1/", include("dataquality.api_urls")),
]
