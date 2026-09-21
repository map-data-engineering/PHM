from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("api/v1/", include("outlets.urls")),
    path("api/v1/", include("siting.urls")),
    path("api/v1/", include("dataquality.urls")),
    path("accounts/", include("accounts.urls")),
]
