"""P1 — capability abstraction + per-tenant connector selection.

get_capability resolves a tenant's IntegrationConnection to a connector behind the
capability Protocol; callers never name a vendor (#9). Selection is tenant-scoped.
"""
import pytest

from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant
from integrations.capabilities import DocStore, TaskTracker
from integrations.registry import get_capability, register_connector
from integrations.types import CapabilityError, CapabilityUnavailable


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


def _connect(tenant, capability, connector, scopes=None):
    return IntegrationConnection.objects.create(
        tenant=tenant, capability=capability, connector=connector,
        scopes=scopes or {}, token_ref="settings:atlassian",
    )


def test_resolves_docstore_to_confluence_connector(tenant):
    _connect(tenant, "docstore", "confluence", {"space_key": "SDLC"})
    ds = get_capability(tenant.id, "docstore")
    assert isinstance(ds, DocStore)  # behind the vendor-free Protocol


def test_resolves_tasktracker_bound_to_project(tenant):
    _connect(tenant, "tasktracker", "jira", {"project_key": "ST"})
    tt = get_capability(tenant.id, "tasktracker")
    assert isinstance(tt, TaskTracker)
    assert tt._project == "ST"  # bound from the connection's scopes


def test_no_connection_raises_capability_unavailable(tenant):
    with pytest.raises(CapabilityUnavailable):
        get_capability(tenant.id, "docstore")


def test_unknown_connector_raises_capability_error(tenant):
    _connect(tenant, "docstore", "sharepoint")  # no builder registered
    with pytest.raises(CapabilityError):
        get_capability(tenant.id, "docstore")


def test_selection_is_tenant_scoped(tenant):
    other = Tenant.objects.create(name="Other")
    _connect(tenant, "docstore", "confluence")
    # The other tenant has no connection of its own → unavailable.
    with pytest.raises(CapabilityUnavailable):
        get_capability(other.id, "docstore")


# ── per-tenant codehost credentials (Bugs S.No 112 / S.No 74): the token travels with the
#    tenant in the shared DB, so any worker builds with the RIGHT token — multi-user safe ──
def _connect_github(tenant, *, repo, access_token=None):
    from apps.integrations.crypto import encrypt_secrets
    return IntegrationConnection.objects.create(
        tenant=tenant, capability="codehost", connector="github", scopes={"repo": repo},
        secret_encrypted=encrypt_secrets({"access_token": access_token} if access_token else {}),
    )


def test_codehost_uses_the_tenants_own_stored_token(tenant, settings):
    settings.GITHUB_TOKEN = "server-env-token"
    _connect_github(tenant, repo="acme/api", access_token="tenant-A-pat")
    ch = get_capability(tenant.id, "codehost")
    assert ch._cfg.token == "tenant-A-pat"   # the tenant's stored token, NOT the server .env
    assert ch._default_repo == "acme/api"


def test_codehost_falls_back_to_settings_when_no_secret_stored(tenant, settings):
    settings.GITHUB_TOKEN = "server-env-token"
    _connect_github(tenant, repo="acme/api", access_token=None)   # no stored secret
    ch = get_capability(tenant.id, "codehost")
    assert ch._cfg.token == "server-env-token"   # backward-compat: local/CI still work


def test_two_tenants_build_with_their_own_tokens(tenant, settings):
    """The multi-user case: on a shared worker/DB, each tenant's build resolves ITS token, so a
    build never runs with another tenant's credentials (the shared-queue 404 that blocked us)."""
    settings.GITHUB_TOKEN = "server-env-token"
    other = Tenant.objects.create(name="Other")
    _connect_github(tenant, repo="acme/api", access_token="tenant-A-pat")
    _connect_github(other, repo="beta/web", access_token="tenant-B-pat")
    assert get_capability(tenant.id, "codehost")._cfg.token == "tenant-A-pat"
    assert get_capability(other.id, "codehost")._cfg.token == "tenant-B-pat"


def test_register_connector_extends_the_seam(tenant):
    sentinel = object()
    register_connector("docstore", "notion", lambda conn: sentinel)
    _connect(tenant, "docstore", "notion")
    try:
        assert get_capability(tenant.id, "docstore") is sentinel
    finally:
        from integrations.registry import _BUILDERS
        _BUILDERS.pop(("docstore", "notion"), None)
