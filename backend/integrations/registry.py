"""Connector registry + per-tenant capability selection (the swap point for #9).

`get_capability(tenant_id, capability)` reads the tenant's `IntegrationConnection`
row and returns the configured connector behind the capability Protocol — callers
never name a vendor. Connectors are keyed by `(capability, connector)` so a tenant can
be moved to a different vendor by editing one row, no caller change.

Credential resolution goes through `token_ref` indirection: Phase 1 resolves to the
`.env`-backed settings; a real per-tenant vault/token-broker is Phase 5 (token_ref is
that seam). Building a connector makes no network call — creds are used lazily on use.
"""
from __future__ import annotations

from collections.abc import Callable

from .atlassian.config import AtlassianConfig
from .atlassian.docstore import AtlassianDocStore
from .atlassian.tasktracker import AtlassianTaskTracker
from .capabilities import DocStore, TaskTracker
from .types import CapabilityError, CapabilityUnavailable


def _atlassian_config(token_ref: str) -> AtlassianConfig:
    # token_ref indirection — Phase 1 resolves to the .env-backed settings creds.
    # (Real per-tenant vault lookup is Phase 5; this is the seam.)
    return AtlassianConfig.from_settings()


def _build_confluence(conn) -> DocStore:
    return AtlassianDocStore(_atlassian_config(conn.token_ref))


def _build_jira(conn) -> TaskTracker:
    from django.conf import settings

    project = (conn.scopes or {}).get("project_key") or settings.JIRA_PROJECT_KEY
    return AtlassianTaskTracker(_atlassian_config(conn.token_ref), project=project)


# (capability, connector) -> builder. The single place vendors are wired (#9);
# extend via register_connector for new vendors without touching callers.
_BUILDERS: dict[tuple[str, str], Callable[[object], object]] = {
    ("docstore", "confluence"): _build_confluence,
    ("tasktracker", "jira"): _build_jira,
}


def register_connector(
    capability: str, connector: str, builder: Callable[[object], object]
) -> None:
    _BUILDERS[(capability, connector)] = builder


def get_connection(tenant_id, capability: str):
    """The tenant's IntegrationConnection row for a capability (or None) — exposes
    `scopes`/`token_ref`/`health` to callers that need config (e.g. the publish path)."""
    from apps.integrations.models import IntegrationConnection
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return (
            IntegrationConnection.objects
            .filter(tenant_id=tenant_id, capability=capability)
            .order_by("-updated_at")
            .first()
        )


def get_capability(tenant_id, capability: str) -> DocStore | TaskTracker:
    """Return the tenant's connector for a capability, or raise CapabilityUnavailable."""
    conn = get_connection(tenant_id, capability)
    if conn is None:
        raise CapabilityUnavailable(
            f"no {capability!r} connector configured for tenant {tenant_id}"
        )
    builder = _BUILDERS.get((conn.capability, conn.connector))
    if builder is None:
        raise CapabilityError(
            f"no connector registered for {conn.capability!r}:{conn.connector!r}"
        )
    return builder(conn)
