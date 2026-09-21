from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsDataTeam

from . import services


@login_required
def dashboard_page(request):
    return render(request, "dataquality/dashboard.html")


class SummaryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(services.summary())


class DetailsView(APIView):
    permission_classes = [IsDataTeam]

    def get(self, request):
        return Response(services.details())
