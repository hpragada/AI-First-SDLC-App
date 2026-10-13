"""P4.7-T1 — server-session auth (login / logout / me) + tenant-from-user.

Exercises the HTTP layer with a real Django session. The test DB connection is
superuser (RLS bypassed), so the explicit `tenant_id` scoping is what's under test
here; RLS itself is covered by test_rls.py.
"""
import pytest
from rest_framework.response import Response
from rest_framework.test import APIClient, APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from datetime import timedelta

from django.utils import timezone

from apps.projects.models import Project
from apps.tenancy.auth import IsTenantAdmin
from apps.tenancy.models import Invitation, Membership, Tenant, User
from apps.tenancy.services import (
    create_invitation,
    request_password_reset,
    resend_invitation,
)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payment Gateway v2")


@pytest.fixture
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


@pytest.fixture
def user(tenant, project):
    u = User.objects.create_user(
        email="sarah@acme.com", name="Sarah Chen", tenant=tenant, password="s3cret-pass!"
    )
    Membership.objects.create(
        tenant=tenant, user=u, project=project, role="product_owner"
    )
    return u


# ── login / me / logout round-trip ──────────────────────────────────
def test_login_success_returns_me_shape(client, user, project):
    resp = client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["user"]["email"] == "sarah@acme.com"
    assert resp.data["user"]["name"] == "Sarah Chen"
    assert resp.data["user"]["is_tenant_admin"] is False  # flag arrives in T2
    assert resp.data["tenant"]["name"] == "Acme"
    assert resp.data["memberships"] == [
        {
            "project_id": str(project.id),
            "project_name": "Payment Gateway v2",
            "role": "product_owner",
            # S.No 221: the sidebar decides whether to offer the brownfield onboarding
            # wizard, and this payload is the only place it learns the project's kind.
            "track": "greenfield",
        }
    ]


def test_login_invalid_credentials(client, user):
    resp = client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "wrong"},
        format="json",
    )
    assert resp.status_code == 401


def test_login_validation_error(client, db):
    resp = client.post("/api/auth/login/", {"email": "not-an-email"}, format="json")
    assert resp.status_code == 400


def test_me_unauthenticated_401(client, db):
    assert client.get("/api/auth/me/").status_code == 401


def test_me_after_login(client, user):
    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["user"]["email"] == "sarah@acme.com"


def test_logout_clears_session(client, user):
    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    assert client.get("/api/auth/me/").status_code == 200
    assert client.post("/api/auth/logout/").status_code == 204
    assert client.get("/api/auth/me/").status_code == 401


# ── tenant is derived from the user, not the header ─────────────────
def test_tenant_scoping_comes_from_the_session_user(client, user, project):
    """An authenticated request with NO X-Tenant-ID still scopes to the user's tenant,
    and never leaks another tenant's rows."""
    other = Tenant.objects.create(name="Globex")
    Project.objects.create(tenant=other, name="Other Co Project")

    client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    )
    resp = client.get("/api/projects/")  # no X-Tenant-ID header
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.data]
    assert ids == [str(project.id)]  # only the user's tenant's project


def test_header_fallback_preserved_without_session(client, tenant, project):
    """Pre-auth / runner path: no session → X-Tenant-ID still scopes existing endpoints."""
    resp = client.get("/api/projects/", HTTP_X_TENANT_ID=str(tenant.id))
    assert resp.status_code == 200
    assert [p["id"] for p in resp.data] == [str(project.id)]


# ── CSRF: app endpoints are protected once session-authenticated ────
def test_session_authed_post_requires_csrf(user, project):
    """After login the SPA must send X-CSRFToken on unsafe requests (login/logout are
    exempt; real app POSTs are not). /me issues the csrftoken cookie."""
    client = APIClient(enforce_csrf_checks=True)
    assert client.post(
        "/api/auth/login/",
        {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    ).status_code == 200  # login is CSRF-exempt

    client.get("/api/auth/me/")  # sets the csrftoken cookie
    token = client.cookies["csrftoken"].value

    # A session-authed create without the token is rejected…
    no_token = client.post(
        "/api/work-items/",
        {"project": str(project.id), "type": "epic"},
        format="json",
    )
    assert no_token.status_code == 403
    # …and accepted with it.
    with_token = client.post(
        "/api/work-items/",
        {"project": str(project.id), "type": "epic"},
        format="json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert with_token.status_code == 201


# ── P4.7-T2: self-serve signup → new tenant + first admin ───────────
def test_signup_creates_tenant_admin_and_session(client, db):
    resp = client.post(
        "/api/auth/signup/",
        {
            "name": "Sarah Chen",
            "email": "founder@newco.com",
            "password": "s3cret-pass!",
            "org_name": "NewCo",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["user"]["is_tenant_admin"] is True
    assert resp.data["tenant"]["name"] == "NewCo"
    # tenant + admin persisted
    user = User.objects.get(email="founder@newco.com")
    assert user.is_tenant_admin is True
    assert user.tenant.name == "NewCo"
    # session is live (me round-trips)
    me = client.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["user"]["is_tenant_admin"] is True


def test_signup_duplicate_email_rejected(client, user):
    resp = client.post(
        "/api/auth/signup/",
        {
            "name": "Imposter",
            "email": "sarah@acme.com",  # already exists (fixture)
            "password": "another-pass!",
            "org_name": "Imposter Inc",
        },
        format="json",
    )
    assert resp.status_code == 409
    # no second tenant created
    assert not Tenant.objects.filter(name="Imposter Inc").exists()


class _AdminOnlyView(APIView):
    permission_classes = [IsTenantAdmin]

    def get(self, request):
        return Response({"ok": True})


def test_is_tenant_admin_permission_gates_admin_endpoints(user, tenant):
    """The is_tenant_admin flag is the gate for admin endpoints: a non-admin gets 403,
    a tenant-admin passes."""
    factory = APIRequestFactory()
    view = _AdminOnlyView.as_view()

    # the fixture user is a normal member → 403
    req = factory.get("/admin-only")
    force_authenticate(req, user=user)
    assert view(req).status_code == 403

    admin = User.objects.create_user(
        email="admin@acme.com", name="Admin", tenant=tenant,
        password="p4ssw0rd!", is_tenant_admin=True,
    )
    req2 = factory.get("/admin-only")
    force_authenticate(req2, user=admin)
    assert view(req2).status_code == 200


# ── P4.7-T3: invitations ────────────────────────────────────────────
def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


def test_admin_creates_invitation(client, admin, project):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/invitations/",
        {
            "email": "invitee@acme.com",
            "name": "Invitee",
            "grants": [{"project_id": str(project.id), "role": "engineer"}],
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["email"] == "invitee@acme.com"
    assert resp.data["status"] == "pending"
    # the token / hash never leak in any payload
    assert "token" not in resp.data
    assert "token_hash" not in resp.data
    assert Invitation.objects.filter(email="invitee@acme.com", status="pending").exists()


def test_non_admin_cannot_invite(client, user):
    _login(client, "sarah@acme.com", "s3cret-pass!")  # a plain member
    resp = client.post(
        "/api/invitations/", {"email": "x@acme.com"}, format="json"
    )
    assert resp.status_code == 403


def test_invitations_are_tenant_isolated(client, admin, tenant, project):
    # an invitation in a different tenant must not show up in this admin's list
    other = Tenant.objects.create(name="Globex")
    create_invitation(tenant=other, invited_by=None, email="alien@globex.com")
    create_invitation(tenant=tenant, invited_by=admin, email="local@acme.com")

    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get("/api/invitations/")
    assert resp.status_code == 200
    emails = {row["email"] for row in resp.data}
    assert emails == {"local@acme.com"}


# ── Bug fix: invitation preview (accept-invite page's pre-submit lookup) ───
def _preview(client, raw):
    """POST the token in the body (never the URL) — the accept-invite page's pre-submit lookup."""
    return client.post("/api/auth/invitations/preview/", {"token": raw}, format="json")


def test_invitation_preview_returns_display_fields(client, admin, project):
    _inv, raw = create_invitation(
        tenant=admin.tenant, invited_by=admin, email="newhire@acme.com", name="New Hire",
        grants=[{"project_id": str(project.id), "role": "engineer"}],
    )
    resp = _preview(client, raw)
    assert resp.status_code == 200
    assert resp.data["tenant_name"] == "Acme"
    assert resp.data["inviter_name"] == "Boss"
    assert resp.data["email"] == "newhire@acme.com"
    assert resp.data["name"] == "New Hire"
    assert resp.data["grants"] == [
        {
            "project_id": str(project.id),
            "project_name": "Payment Gateway v2",
            "role": "engineer",
            "role_label": "Engineer",
        }
    ]
    # never leaks the token/hash
    assert "token" not in resp.data
    assert "token_hash" not in resp.data


def test_invitation_preview_invalid_token_410(client, db):
    resp = _preview(client, "not-a-real-token")
    assert resp.status_code == 410


def test_invitation_preview_accepted_invitation_409(client, admin):
    _inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="used@acme.com")
    assert client.post(
        "/api/auth/accept-invitation/", {"token": raw, "password": "first-pass!"},
        format="json",
    ).status_code == 200
    resp = _preview(client, raw)
    assert resp.status_code == 409


def test_invitation_preview_does_not_mutate_expired_status(client, admin):
    """Unlike accept_invitation(), a mere preview must not transition status —
    it's a read, not an action."""
    inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="stale@acme.com")
    inv.expires_at = timezone.now() - timedelta(days=1)
    inv.save(update_fields=["expires_at"])
    resp = _preview(client, raw)
    assert resp.status_code == 410
    inv.refresh_from_db()
    assert inv.status == "pending"  # not silently flipped to "expired" by the read


# ── P4.7-T3: accept-invitation ──────────────────────────────────────
def test_accept_invitation_creates_user_and_memberships(client, admin, project):
    _inv, raw = create_invitation(
        tenant=admin.tenant, invited_by=admin, email="newhire@acme.com",
        grants=[{"project_id": str(project.id), "role": "engineer"}],
    )
    resp = client.post(
        "/api/auth/accept-invitation/",
        {"token": raw, "password": "brand-new-pass!"},
        format="json",
    )
    assert resp.status_code == 200
    assert resp.data["user"]["email"] == "newhire@acme.com"
    assert resp.data["memberships"] == [
        {
            "project_id": str(project.id),
            "project_name": project.name,
            "role": "engineer",
            "track": "greenfield",
        }
    ]
    # user persisted + membership queued; session live
    new_user = User.objects.get(email="newhire@acme.com")
    assert Membership.objects.filter(user=new_user, project=project, role="engineer").exists()
    assert client.get("/api/auth/me/").status_code == 200
    # invitation is consumed
    _inv.refresh_from_db()
    assert _inv.status == "accepted"


def test_accept_used_invitation_409(client, admin):
    _inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="once@acme.com")
    assert client.post(
        "/api/auth/accept-invitation/", {"token": raw, "password": "first-pass!"},
        format="json",
    ).status_code == 200
    # a second accept with the same token is rejected as used
    second = client.post(
        "/api/auth/accept-invitation/", {"token": raw, "password": "second-pass!"},
        format="json",
    )
    assert second.status_code == 409


def test_accept_revoked_invitation_410(client, admin):
    inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="revoked@acme.com")
    inv.status = "revoked"
    inv.save(update_fields=["status"])
    resp = client.post(
        "/api/auth/accept-invitation/", {"token": raw, "password": "whatever!"},
        format="json",
    )
    assert resp.status_code == 410


def test_accept_expired_invitation_410(client, admin):
    inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="expired@acme.com")
    inv.expires_at = timezone.now() - timedelta(days=1)
    inv.save(update_fields=["expires_at"])
    resp = client.post(
        "/api/auth/accept-invitation/", {"token": raw, "password": "whatever!"},
        format="json",
    )
    assert resp.status_code == 410
    inv.refresh_from_db()
    assert inv.status == "expired"


def test_resend_rotates_the_token(client, admin):
    inv, old_raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="rot@acme.com")
    new_raw = resend_invitation(inv)
    assert new_raw != old_raw
    # the old token no longer works…
    assert client.post(
        "/api/auth/accept-invitation/", {"token": old_raw, "password": "pass-one!"},
        format="json",
    ).status_code == 410
    # …the rotated one does
    assert client.post(
        "/api/auth/accept-invitation/", {"token": new_raw, "password": "pass-two!"},
        format="json",
    ).status_code == 200


# ── P4.7-T3: password reset ─────────────────────────────────────────
def test_request_reset_always_200_no_enumeration(client, user):
    # unknown email → still 200 (no account enumeration)
    assert client.post(
        "/api/auth/request-reset/", {"email": "nobody@nowhere.com"}, format="json"
    ).status_code == 200
    # known email → 200
    assert client.post(
        "/api/auth/request-reset/", {"email": "sarah@acme.com"}, format="json"
    ).status_code == 200


def test_reset_password_roundtrip(client, user):
    raw = request_password_reset(email="sarah@acme.com")
    assert raw is not None
    resp = client.post(
        "/api/auth/reset/", {"token": raw, "password": "totally-new-pass!"}, format="json"
    )
    assert resp.status_code == 200
    # the new password works, the old one no longer does
    assert client.post(
        "/api/auth/login/", {"email": "sarah@acme.com", "password": "totally-new-pass!"},
        format="json",
    ).status_code == 200
    assert client.post(
        "/api/auth/login/", {"email": "sarah@acme.com", "password": "s3cret-pass!"},
        format="json",
    ).status_code == 401
    # token is single-use — replaying it fails
    assert client.post(
        "/api/auth/reset/", {"token": raw, "password": "again-pass!"}, format="json"
    ).status_code == 410


def test_reset_invalid_token_410(client, db):
    resp = client.post(
        "/api/auth/reset/", {"token": "not-a-real-token", "password": "whatever8!"},
        format="json",
    )
    assert resp.status_code == 410


# ── S.No 221: the project's kind travels with the membership ────────
def test_me_carries_the_project_track(client, user, project):
    """A greenfield project was offered the brownfield onboarding wizard because the
    frontend had no way to tell the two apart: `/me` carried the project's id, name and
    the caller's role, and nothing about the project itself. Both values are asserted —
    a field that only ever reports one of them would hide the bug rather than fix it."""
    client.force_login(user)

    assert client.get("/api/auth/me/").data["memberships"][0]["track"] == "greenfield"

    project.track = Project.Track.BROWNFIELD
    project.save(update_fields=["track"])
    assert client.get("/api/auth/me/").data["memberships"][0]["track"] == "brownfield"


# ── 2026-10-09: invite suite — email outcome and honest refusals ────
def test_invite_reports_email_sent_and_mail_goes_out(client, admin, project, mailoutbox):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/invitations/",
        {"email": "mailed@acme.com",
         "grants": [{"project_id": str(project.id), "role": "engineer"}]},
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["email_sent"] is True
    assert len(mailoutbox) == 1
    assert mailoutbox[0].to == ["mailed@acme.com"]
    assert "/accept-invite?token=" in mailoutbox[0].body


def test_a_mail_failure_keeps_the_invite_and_says_so(client, admin, monkeypatch):
    import smtplib

    from apps.tenancy import services

    def boom(*_a, **_k):
        raise smtplib.SMTPAuthenticationError(535, b"bad key")

    monkeypatch.setattr(services, "send_invitation_email", boom)
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post("/api/invitations/", {"email": "kept@acme.com"}, format="json")
    assert resp.status_code == 201
    assert resp.data["email_sent"] is False
    assert Invitation.objects.filter(email="kept@acme.com", status="pending").exists()
    # Resend reports the same way.
    inv = Invitation.objects.get(email="kept@acme.com")
    again = client.post(f"/api/invitations/{inv.id}/resend/", format="json")
    assert again.status_code == 200
    assert again.data["email_sent"] is False


def test_a_reset_mail_failure_is_silent_to_the_person(client, user, monkeypatch):
    from apps.tenancy import services

    def boom(*_a, **_k):
        raise OSError("network unreachable")

    monkeypatch.setattr(services, "send_password_reset_email", boom)
    resp = client.post("/api/auth/request-reset/", {"email": "sarah@acme.com"}, format="json")
    assert resp.status_code == 200


@pytest.mark.parametrize("case", ["invalid", "used", "revoked", "expired", "expired_recorded"])
def test_refusals_carry_the_reason_the_page_words_them_by(client, admin, case):
    if case == "invalid":
        raw = "not-a-real-token"
    else:
        inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin,
                                     email=f"{case}@acme.com")
        if case == "used":
            client.post("/api/auth/accept-invitation/", {"token": raw, "password": "first-pass!"},
                        format="json")
            client.post("/api/auth/logout/")
        elif case == "revoked":
            inv.status = "revoked"
            inv.save(update_fields=["status"])
        else:
            inv.expires_at = timezone.now() - timedelta(days=1)
            inv.save(update_fields=["expires_at"])
            if case == "expired_recorded":  # accept already flipped it to "expired"
                client.post("/api/auth/accept-invitation/", {"token": raw, "password": "x-pass-1!"},
                            format="json")
    want = "expired" if case.startswith("expired") else case
    for resp in (
        _preview(client, raw),
        client.post("/api/auth/accept-invitation/", {"token": raw, "password": "again-pass!"},
                    format="json"),
    ):
        assert resp.data["reason"] == want
        if want in ("expired", "revoked"):
            assert resp.data["inviter_name"] == "Boss"


def test_invite_email_reads_as_agreed(admin, project, mailoutbox):
    create_invitation(tenant=admin.tenant, invited_by=admin, email="words@acme.com",
                      grants=[{"project_id": str(project.id), "role": "engineer"}])
    msg = mailoutbox[0]
    assert msg.subject == "Boss invited you to Acme"
    assert "You'll join Payment Gateway v2 as Engineer." in msg.body
    assert "This invite works until " in msg.body and "UTC" not in msg.body
    html = msg.alternatives[0][0]
    assert "Join the workspace" in html and "/accept-invite?token=" in html


def test_reset_email_links_to_the_page_that_exists(user, mailoutbox):
    request_password_reset(email="sarah@acme.com")
    assert "/reset?token=" in mailoutbox[0].body
    assert "/reset-password" not in mailoutbox[0].body


def test_invite_email_names_every_role(admin, project, tenant, mailoutbox):
    other = Project.objects.create(tenant=tenant, name="Payroll")
    create_invitation(tenant=admin.tenant, invited_by=admin, email="many@acme.com", grants=[
        {"project_id": str(project.id), "role": "engineer"},
        {"project_id": str(project.id), "role": "architect"},
        {"project_id": str(other.id), "role": "designer"},
    ])
    assert ("You'll join as Engineer and Architect on Payment Gateway v2 and as Designer on "
            "Payroll." in mailoutbox[0].body)



def test_a_second_invite_to_someone_already_waiting_is_refused(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    assert client.post("/api/invitations/", {"email": "twice@acme.com"},
                       format="json").status_code == 201
    again = client.post("/api/invitations/", {"email": "Twice@acme.com"}, format="json")
    assert again.status_code == 400
    assert "already has an invite waiting" in str(again.data["email"])


def test_joining_with_an_email_that_already_has_an_account_is_refused_not_a_crash(client, admin):
    inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="late@acme.com")
    User.objects.create_user(email="late@acme.com", name="Late", tenant=admin.tenant,
                             password="whatever-pass!")
    resp = client.post("/api/auth/accept-invitation/", {"token": raw, "password": "pass-pass-1!"},
                       format="json")
    assert resp.status_code == 409
    assert resp.data["reason"] == "used"


def test_short_password_is_refused_in_plain_words(client, admin):
    _inv, raw = create_invitation(tenant=admin.tenant, invited_by=admin, email="short@acme.com")
    resp = client.post("/api/auth/accept-invitation/", {"token": raw, "password": "abc"},
                       format="json")
    assert resp.status_code == 400
    assert resp.data["password"] == ["Use at least 8 characters."]
