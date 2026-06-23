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


def test_register_connector_extends_the_seam(tenant):
    sentinel = object()
    register_connector("docstore", "notion", lambda conn: sentinel)
    _connect(tenant, "docstore", "notion")
    try:
        assert get_capability(tenant.id, "docstore") is sentinel
    finally:
        from integrations.registry import _BUILDERS
        _BUILDERS.pop(("docstore", "notion"), None)
