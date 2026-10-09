"""Auth endpoints (P4.7-T1): server-session login / logout / me (DECISION-3).

Login establishes a Django session (cookie) and stashes `tenant_id` in the session data;
`TenantContextMiddleware` reads that on every later request to scope RLS, and only then
does `AuthenticationMiddleware` resolve `request.user` (see that middleware's docstring
for why the ordering matters). The runner-token path is untouched (those views set their
own `authentication_classes`). `/me` sets the CSRF cookie so the SPA can send
`X-CSRFToken` on subsequent unsafe requests.
"""
from __future__ import annotations

from django.contrib.auth import authenticate, login, logout
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import ensure_csrf_cookie
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.tenancy.auth import serialize_me
from apps.tenancy.context import tenant_context
from apps.tenancy.services import (
    InvitationError,
    ResetError,
    SignupError,
    accept_invitation,
    get_invitation_preview,
    request_password_reset,
    reset_password,
    signup,
)

from .serializers import (
    AcceptInvitationSerializer,
    LoginSerializer,
    RequestResetSerializer,
    ResetSerializer,
    SignupSerializer,
)

# The user created by signup wasn't returned by authenticate(), so login() needs the
# backend named explicitly.
_MODEL_BACKEND = "django.contrib.auth.backends.ModelBackend"


class SignupView(APIView):
    """POST /api/auth/signup — {name,email,password,org_name} → new tenant + first admin
    (is_tenant_admin=True) + session (DECISIONS 1 & 2). CSRF-exempt (no session yet)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = SignupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = signup(**ser.validated_data)
        except SignupError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        # login() writes last_login via a signal, and serialize_me() reads memberships —
        # both need the tenant RLS context, which signup()'s own tenant_context block has
        # already exited by this point.
        with tenant_context(user.tenant_id):
            login(request, user, backend=_MODEL_BACKEND)
            # TenantContextMiddleware reads this on every later request — see its docstring.
            request.session["tenant_id"] = str(user.tenant_id)
            body = serialize_me(user)
        return Response(body, status=status.HTTP_201_CREATED)


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
        # login() writes last_login via a signal, and serialize_me() reads memberships —
        # the pre-auth request has no tenant RLS context yet, so establish it explicitly.
        with tenant_context(user.tenant_id):
            login(request, user)
            # TenantContextMiddleware reads this on every later request — see its docstring.
            request.session["tenant_id"] = str(user.tenant_id)
            body = serialize_me(user)
        return Response(body)


def _invitation_refusal(exc) -> Response:
    """A refused invite, with what the accept page needs to word it (2026-10-09)."""
    return Response(
        {"detail": str(exc), "reason": exc.reason, "inviter_name": exc.inviter_name},
        status=exc.status,
    )


class InvitationPreviewView(APIView):
    """POST /api/auth/invitations/preview — {token} → the org/inviter/role/project display
    fields the accept-invite page needs before the user submits anything. Public + no session
    (the whole point is to work pre-auth). The token rides the request body (like accept), not
    the URL, so it never lands in access/proxy logs. Never returns the token/hash/id — just what
    the page displays. 409 used / 410 expired-revoked-invalid, same as accept."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        token = request.data.get("token") or ""
        try:
            preview = get_invitation_preview(token)
        except InvitationError as exc:
            return _invitation_refusal(exc)
        return Response(preview)


class AcceptInvitationView(APIView):
    """POST /api/auth/accept-invitation — {token,password,name?} → creates the tenant User +
    queued memberships + session. Public + CSRF-exempt (no session yet). 409 used / 410
    expired-or-revoked / invalid."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = AcceptInvitationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            user = accept_invitation(
                token=ser.validated_data["token"],
                password=ser.validated_data["password"],
                name=ser.validated_data.get("name") or None,
            )
        except InvitationError as exc:
            return _invitation_refusal(exc)
        # Same tenant-context requirement as SignupView — see comment there.
        with tenant_context(user.tenant_id):
            login(request, user, backend=_MODEL_BACKEND)
            request.session["tenant_id"] = str(user.tenant_id)
            body = serialize_me(user)
        return Response(body)


class RequestResetView(APIView):
    """POST /api/auth/request-reset — {email} → always 200 (no account enumeration)."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = RequestResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        request_password_reset(email=ser.validated_data["email"])
        return Response(status=status.HTTP_200_OK)


class ResetView(APIView):
    """POST /api/auth/reset — {token,password} → sets the new password. 410 invalid/expired."""

    authentication_classes: list = []
    permission_classes: list = []

    def post(self, request):
        ser = ResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            reset_password(
                token=ser.validated_data["token"],
                password=ser.validated_data["password"],
            )
        except ResetError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_410_GONE)
        return Response(status=status.HTTP_200_OK)


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
