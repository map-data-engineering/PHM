from django.contrib.auth import authenticate
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


def _roles(user):
    if user.is_superuser:
        return ["admin"]
    return [g.lower().replace(" ", "-") for g in user.groups.values_list("name", flat=True)]


class ApiTokenLoginView(APIView):
    """Token auth for the separately-hosted static frontend (Vercel). Public
    Registry/Find Pharmacy work without any of this — only Site Check and
    the Data Quality/edit-review tools need a signed-in Regulator/Data Team
    user, and cross-origin session cookies aren't reliable, hence a token."""

    permission_classes = [AllowAny]

    def post(self, request):
        username = request.data.get("username", "")
        password = request.data.get("password", "")
        user = authenticate(request, username=username, password=password)
        if user is None:
            return Response({"detail": "Invalid credentials."}, status=status.HTTP_401_UNAUTHORIZED)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username, "roles": _roles(user)})


class ApiTokenLogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        Token.objects.filter(user=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ApiMeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"username": request.user.username, "roles": _roles(request.user)})
