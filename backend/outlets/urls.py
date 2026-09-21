from django.urls import path
from rest_framework.routers import SimpleRouter

from . import views

app_name = "outlets"

router = SimpleRouter()
router.register("outlets", views.OutletViewSet, basename="outlet")
router.register("edit-proposals", views.EditProposalViewSet, basename="edit-proposal")

urlpatterns = router.urls + [
    path("boundaries/<str:level>/", views.BoundaryView.as_view(), name="boundaries"),
]
