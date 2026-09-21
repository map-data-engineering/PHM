from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz, name="healthz"),
    path("accounts/", include("accounts.urls")),
    path("", include("outlets.urls")),
    path("", include("siting.urls")),
    path("", include("dataquality.urls")),
    path("", include("common.urls")),
]
