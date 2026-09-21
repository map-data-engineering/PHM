from django.urls import path

from . import views

urlpatterns = [
    path("data-quality/summary/", views.SummaryView.as_view(), name="summary"),
    path("data-quality/details/", views.DetailsView.as_view(), name="details"),
]
