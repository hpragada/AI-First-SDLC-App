"""Auth endpoints (P4.7-T1): server-session login / logout / me (DECISION-3).

Login establishes a Django session (cookie); thereafter `request.user` is set by
`AuthenticationMiddleware` and the tenant is resolved from the user. The runner-token
path is untouched (those views set their own `authentication_classes`). `/me` sets the
CSRF cookie so the SPA can send `X-CSRFToken` on subsequent unsafe requests.
"""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.auth import serialize_me

from .serializers import LoginSerializer


class LoginView(APIView):
    """POST /api/auth/login — {email,password} → session + the `/me` payload."""

    # No session needed to log in; being auth-exempt also keeps the login POST itself
    # off the CSRF path (the SPA has no token yet — it gets one from /me afterwards).
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = authenticate(
            request,
            username=ser.validated_data["email"],
            password=ser.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "Invalid email or password."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        login(request, user)
        return Response(serialize_me(user))


class LogoutView(APIView):
    """POST /api/auth/logout — clears the session."""

    # CSRF-exempt: logging a user out via CSRF is low-risk, and it must work even if the
    # SPA's token has gone stale. `request.user` is still set by AuthenticationMiddleware.
    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        logout(request)
        return Response(status=status.HTTP_204_NO_CONTENT)


@method_decorator(ensure_csrf_cookie, name="get")
class MeView(APIView):
    """GET /api/auth/me — current user + tenant + memberships (401 if no session).
    Sets the CSRF cookie so the browser can send X-CSRFToken on unsafe requests."""

    permission_classes: list = []

    def get(self, request):
        user = request.user
        if not getattr(user, "is_authenticated", False):
            return Response(
                {"detail": "Authentication required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        return Response(serialize_me(user))
