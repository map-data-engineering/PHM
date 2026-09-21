from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from common.permissions import IsDataTeam

from . import services


class SummaryView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(services.summary())


class DetailsView(APIView):
    permission_classes = [IsDataTeam]

    def get(self, request):
        return Response(services.details())
