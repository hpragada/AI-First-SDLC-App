"""P4.7-T6 — integrations management REST + secret store (J9, DECISION-4).

Admin CRUD over IntegrationConnection per capability, with a write-only secret store:
POST/PATCH accept `secrets`, no response ever echoes them back (`configured: bool` only).
`test-connection` checks the chosen vendor is wired + configured and flips `health`.
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.crypto import decrypt_secrets
from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant, User
from integrations.types import CapabilityError


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def admin(tenant):
    return User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )


@pytest.fixture
def member(tenant):
    return User.objects.create_user(
        email="dev@acme.com", name="Dev", tenant=tenant, password="dev-pass!"
    )


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


# ── admin-only ───────────────────────────────────────────────────────
def test_non_admin_cannot_list_integrations(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get("/api/integrations/")
    assert resp.status_code == 403


def test_non_admin_cannot_create_integration(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(
        "/api/integrations/",
        {"capability": "docstore", "vendor": "confluence"}, format="json",
    )
    assert resp.status_code == 403


# ── create ───────────────────────────────────────────────────────────
def test_admin_creates_integration_secret_never_returned(client, admin, tenant):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/",
        {
            "capability": "docstore", "vendor": "confluence",
            "binding": {"space_key": "ENG"},
            "secrets": {"api_token": "sekret-abc"},
        },
        format="json",
    )
    assert resp.status_code == 201
    body = resp.data
    assert body["capability"] == "docstore"
    assert body["connector"] == "confluence"   # slug (registry key)
    assert body["vendor"] == "Confluence"       # human label (from the catalog)
    assert body["binding"] == {"space_key": "ENG"}
    assert body["configured"] is True
    assert "secret" not in body and "secrets" not in body and "secret_encrypted" not in body

    conn = IntegrationConnection.objects.get(tenant_id=tenant.id, capability="docstore")
    assert decrypt_secrets(conn.secret_encrypted) == {"api_token": "sekret-abc"}


def test_create_unsupported_capability_400(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/",
        {"capability": "not-a-capability", "vendor": "x"}, format="json",
    )
    assert resp.status_code == 400


def test_create_duplicate_capability_409(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    payload = {"capability": "codehost", "vendor": "github", "secrets": {"token": "t"}}
    assert client.post("/api/integrations/", payload, format="json").status_code == 201
    resp = client.post("/api/integrations/", payload, format="json")
    assert resp.status_code == 409


def test_create_without_secrets_is_unconfigured(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(
        "/api/integrations/", {"capability": "designsource", "vendor": "figma"}, format="json"
    )
    assert resp.status_code == 201
    assert resp.data["configured"] is False


# ── list is tenant-isolated ──────────────────────────────────────────
def test_integrations_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    admin1 = User.objects.create_user(
        email="a1@acme.com", name="A1", tenant=t1, password="pw!", is_tenant_admin=True
    )
    User.objects.create_user(
        email="a2@globex.com", name="A2", tenant=t2, password="pw!", is_tenant_admin=True
    )
    IntegrationConnection.objects.create(tenant=t1, capability="codeintel", connector="builtin")
    IntegrationConnection.objects.create(tenant=t2, capability="codeintel", connector="builtin")

    c = APIClient()
    _login(c, admin1.email, "pw!")
    resp = c.get("/api/integrations/")
    assert resp.status_code == 200
    assert len(resp.data) == 1


# ── update ───────────────────────────────────────────────────────────
def test_patch_updates_binding_without_touching_secret(client, admin, tenant):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {
            "capability": "tasktracker", "vendor": "jira",
            "binding": {"project_key": "OLD"}, "secrets": {"api_token": "orig-secret"},
        },
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.patch(
        f"/api/integrations/{conn_id}/", {"binding": {"project_key": "NEW"}}, format="json"
    )
    assert resp.status_code == 200
    assert resp.data["binding"] == {"project_key": "NEW"}
    assert resp.data["configured"] is True

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert decrypt_secrets(conn.secret_encrypted) == {"api_token": "orig-secret"}


def test_patch_with_an_empty_secrets_object_does_not_wipe_the_stored_token(client, admin):
    """Bugs S.No 156: an EMPTY `secrets` object must not blank out the saved credential. The
    connect drawer sends `secrets: {}` whenever the admin edits a configured connection without
    retyping the token (e.g. changing only the project key) — and `{}` is not None, so it used to
    re-encrypt an empty dict and silently destroy the token."""
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {
            "capability": "tasktracker", "vendor": "jira",
            "binding": {"project_key": "OLD"}, "secrets": {"api_token": "orig-secret"},
        },
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.patch(
        f"/api/integrations/{conn_id}/",
        {"binding": {"project_key": "NEW"}, "secrets": {}}, format="json",
    )

    assert resp.status_code == 200
    assert resp.data["configured"] is True          # still connected, not silently broken
    conn = IntegrationConnection.objects.get(id=conn_id)
    assert decrypt_secrets(conn.secret_encrypted) == {"api_token": "orig-secret"}


def test_patch_replaces_secret_when_supplied(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "testmgmt", "vendor": "xray", "secrets": {"client_secret": "old"}},
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.patch(
        f"/api/integrations/{conn_id}/",
        {"secrets": {"client_secret": "new"}}, format="json",
    )
    assert resp.status_code == 200
    conn = IntegrationConnection.objects.get(id=conn_id)
    assert decrypt_secrets(conn.secret_encrypted) == {"client_secret": "new"}


# ── delete ───────────────────────────────────────────────────────────
def test_delete_integration(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "codeintel", "vendor": "builtin"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.delete(f"/api/integrations/{conn_id}/")
    assert resp.status_code == 204
    assert not IntegrationConnection.objects.filter(id=conn_id).exists()


# ── test-connection ──────────────────────────────────────────────────
def test_test_connection_ok_for_builtin_no_secret_needed(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "codeintel", "vendor": "builtin"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is True

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert conn.health == IntegrationConnection.Health.HEALTHY


def test_test_connection_fails_without_secret(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/", {"capability": "docstore", "vendor": "confluence"}, format="json"
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is False
    assert "fix_hint" in resp.data

    conn = IntegrationConnection.objects.get(id=conn_id)
    assert conn.health == IntegrationConnection.Health.DOWN


# ── catalog + slug round-trip (Bugs #39/#40) ─────────────────────────
# ── S.No 156: live probe + test-before-save ──────────────────────────
class _PingOK:
    def ping(self):
        return "Signed in to Jira as Tarun."


class _PingRejected:
    def ping(self):
        raise CapabilityError("Atlassian GET /rest/api/3/myself -> 401", status=401)


def _use_connector(monkeypatch, connector):
    monkeypatch.setattr("integrations.registry.get_builder", lambda cap, ven: lambda conn:
                        connector)


def test_test_connection_makes_a_real_call_and_fails_a_bad_token(client, admin, monkeypatch):
    """Bugs S.No 156: 'Test connection' only proved the connector was CONSTRUCTIBLE, so a wrong
    or expired token still reported OK — which is precisely what the test exists to catch."""
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "tasktracker", "vendor": "jira", "secrets": {"api_token": "bad"}},
        format="json",
    )
    _use_connector(monkeypatch, _PingRejected())

    resp = client.post(f"/api/integrations/{create.data['id']}/test-connection/", format="json")

    assert resp.status_code == 200 and resp.data["ok"] is False
    assert "not authorized" in resp.data["detail"]      # actionable, not a raw 401 URL
    assert IntegrationConnection.objects.get(id=create.data["id"]).health == \
        IntegrationConnection.Health.DOWN


def test_test_connection_reports_who_we_authenticated_as(client, admin, monkeypatch):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "tasktracker", "vendor": "jira", "secrets": {"api_token": "good"}},
        format="json",
    )
    _use_connector(monkeypatch, _PingOK())

    resp = client.post(f"/api/integrations/{create.data['id']}/test-connection/", format="json")

    assert resp.data["ok"] is True and "Tarun" in resp.data["detail"]
    assert IntegrationConnection.objects.get(id=create.data["id"]).health == \
        IntegrationConnection.Health.HEALTHY


def test_test_credentials_probes_without_saving_anything(client, admin, tenant, monkeypatch):
    """Bugs S.No 156: an admin had to SAVE credentials to the tenant before they could test them
    (test-connection is detail-routed). test-credentials probes an in-memory connection that is
    never persisted."""
    _login(client, "boss@acme.com", "admin-pass!")
    _use_connector(monkeypatch, _PingOK())

    resp = client.post(
        "/api/integrations/test-credentials/",
        {"capability": "tasktracker", "vendor": "jira",
         "binding": {"project_key": "ST"}, "secrets": {"api_token": "good"}},
        format="json",
    )

    assert resp.status_code == 200 and resp.data["ok"] is True and "Tarun" in resp.data["detail"]
    # Nothing was written — the tenant has no tasktracker connection.
    assert not IntegrationConnection.objects.filter(
        tenant=tenant, capability="tasktracker").exists()


def test_test_credentials_rejects_bad_credentials_without_saving(client, admin, tenant,
                                                                  monkeypatch):
    _login(client, "boss@acme.com", "admin-pass!")
    _use_connector(monkeypatch, _PingRejected())

    resp = client.post(
        "/api/integrations/test-credentials/",
        {"capability": "tasktracker", "vendor": "jira", "secrets": {"api_token": "bad"}},
        format="json",
    )

    assert resp.data["ok"] is False and "not authorized" in resp.data["detail"]
    assert not IntegrationConnection.objects.filter(
        tenant=tenant, capability="tasktracker").exists()


def test_test_credentials_requires_admin(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(
        "/api/integrations/test-credentials/",
        {"capability": "tasktracker", "vendor": "jira", "secrets": {"api_token": "x"}},
        format="json",
    )
    assert resp.status_code == 403        # credentials probing is an admin action


def test_probe_is_honest_when_a_vendor_has_no_live_check(client, admin, monkeypatch):
    """A connector with no ping() must not claim we reached the vendor."""
    _login(client, "boss@acme.com", "admin-pass!")
    _use_connector(monkeypatch, object())          # constructible, but no ping()

    resp = client.post(
        "/api/integrations/test-credentials/",
        {"capability": "testmgmt", "vendor": "xray", "secrets": {"client_secret": "s"}},
        format="json",
    )

    assert resp.data["ok"] is True and "no live check" in resp.data["detail"]


def test_catalog_lists_registered_vendors_per_capability(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.get("/api/integrations/catalog/")
    assert resp.status_code == 200
    by_cap = {c["capability"]: c for c in resp.data}
    # every capability the services layer accepts is present in the catalog…
    assert {"docstore", "tasktracker", "codehost", "designsource", "testmgmt",
            "codeintel", "a11yai"} <= set(by_cap)
    # …and every vendor slug it advertises is actually builder-wired (so a saved
    # connection can never hit "No connector registered" — the #39 root cause).
    from integrations.registry import get_builder

    for cap in resp.data:
        assert cap["vendors"], f"{cap['capability']} has no vendors"
        for vendor in cap["vendors"]:
            assert get_builder(cap["capability"], vendor["slug"]) is not None


def test_non_admin_cannot_read_catalog(client, member):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get("/api/integrations/catalog/").status_code == 403


# The #39 tests below check the catalog SLUG resolves to a registered, constructible connector.
# They save placeholder credentials ("x"), so since test-connection became a real live probe
# (Bugs S.No 156) they can no longer expect ok=True — a fake token SHOULD fail. What must still
# hold is that the failure is a reachability/auth one (proving the builder ran and got as far as
# the network), never a registry miss or a build error.
_WIRING_FAILURES = ("No connector registered", "Could not build the connector",
                    "No credentials have been saved")


def _assert_wired(data, ctx=""):
    assert data["ok"] is True or not any(m in data["detail"] for m in _WIRING_FAILURES), \
        (ctx, data)


def test_catalog_slug_saves_and_is_wired(client, admin):
    """The exact #39 flow: the connector slug from the catalog saves and resolves in the registry
    (previously the UI sent the display name 'Confluence' → registry miss)."""
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "docstore", "vendor": "confluence",
         "binding": {"space_key": "PAY"}, "secrets": {"api_token": "t"}},
        format="json",
    )
    assert create.status_code == 201
    assert create.data["status"] == "connected"   # grid now shows Connected
    resp = client.post(f"/api/integrations/{create.data['id']}/test-connection/")
    assert resp.status_code == 200
    _assert_wired(resp.data, "docstore:confluence")


def test_every_catalog_vendor_saves_and_is_wired(client, admin):
    """The #39 fix must hold for EVERY connector, not just docstore: for each vendor the
    catalog advertises, saving with its slug + the fields it declares yields a connection whose
    connector resolves and builds (and the read shape carries the slug + human label)."""
    _login(client, "boss@acme.com", "admin-pass!")
    catalog = client.get("/api/integrations/catalog/").data
    checked = []
    for cap in catalog:
        for vendor in cap["vendors"]:
            binding = {f["name"]: "x" for f in vendor["binding"]}
            secrets = {} if vendor.get("no_secret") else {f["name"]: "x" for f in vendor["secrets"]}
            create = client.post(
                "/api/integrations/",
                {"capability": cap["capability"], "vendor": vendor["slug"],
                 "binding": binding, "secrets": secrets},
                format="json",
            )
            assert create.status_code == 201, (cap["capability"], create.data)
            assert create.data["connector"] == vendor["slug"]
            assert create.data["vendor"] == vendor["label"]
            assert create.data["status"] == "connected"
            test = client.post(f"/api/integrations/{create.data['id']}/test-connection/")
            assert test.status_code == 200
            _assert_wired(test.data, (cap["capability"], vendor["slug"]))
            checked.append((cap["capability"], vendor["slug"]))
    # every capability the services layer accepts was exercised
    assert {c for c, _ in checked} == {
        "docstore", "tasktracker", "codehost", "designsource", "testmgmt", "codeintel",
        "a11yai",
    }


def test_test_connection_fails_for_unregistered_vendor(client, admin):
    _login(client, "boss@acme.com", "admin-pass!")
    create = client.post(
        "/api/integrations/",
        {"capability": "docstore", "vendor": "notion", "secrets": {"token": "t"}},
        format="json",
    )
    conn_id = create.data["id"]

    resp = client.post(f"/api/integrations/{conn_id}/test-connection/")
    assert resp.status_code == 200
    assert resp.data["ok"] is False
    # Screen Words group 5 reworded this ("no connector registered for 'docstore':'notion'" named
    # both internal keys). The test's point is unchanged: an unknown vendor fails the connection
    # test with a reason the admin can act on, and that reason says to reconnect.
    detail = resp.data["detail"].lower()
    assert "isn't supported" in detail and "reconnect" in detail, resp.data
    assert "docstore" not in detail and "'notion'" not in detail, resp.data
