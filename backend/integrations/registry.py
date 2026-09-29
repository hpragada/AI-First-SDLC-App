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
from .capabilities import (
    A11yAI,
    CodeHost,
    CodeIntel,
    DesignSource,
    DocStore,
    TaskTracker,
    TestMgmt,
)
from .types import CapabilityError, CapabilityUnavailable


def _atlassian_config(conn) -> AtlassianConfig:
    # Per-tenant Atlassian creds from the tenant's own connection (shared DB), not the server
    # .env — same multi-tenant credential fix as GitHub (Bugs S.No 74/113). Falls back to
    # settings per-field when the tenant hasn't stored one.
    return AtlassianConfig.from_connection(conn)


def _build_confluence(conn) -> DocStore:
    from .rate_governor import governed_transport

    transport = governed_transport(conn.tenant_id, conn.capability)
    return AtlassianDocStore(_atlassian_config(conn), transport=transport)


def _build_jira(conn) -> TaskTracker:
    from django.conf import settings

    from .rate_governor import governed_transport

    project = (conn.scopes or {}).get("project_key") or settings.JIRA_PROJECT_KEY
    transport = governed_transport(conn.tenant_id, conn.capability)
    return AtlassianTaskTracker(
        _atlassian_config(conn), project=project, transport=transport
    )


def _build_github(conn) -> CodeHost:
    from django.conf import settings

    from .github.codehost import GithubCodeHost
    from .github.config import GithubConfig
    from .rate_governor import governed_transport

    repo = (conn.scopes or {}).get("repo") or settings.GITHUB_REPO
    transport = governed_transport(conn.tenant_id, conn.capability)
    # Per-tenant token from the tenant's own connection (shared DB), not the server .env — so a
    # build run for this tenant uses the right credential on ANY worker (Bugs S.No 112 / S.No 74).
    return GithubCodeHost(
        GithubConfig.from_connection(conn), default_repo=repo, transport=transport)


def _build_figma(conn) -> DesignSource:
    from django.conf import settings

    from .figma.config import FigmaConfig
    from .figma.designsource import FigmaDesignSource
    from .rate_governor import governed_transport

    file_key = (conn.scopes or {}).get("file_key") or settings.FIGMA_FILE_KEY
    transport = governed_transport(conn.tenant_id, conn.capability)
    # Per-tenant token from the tenant's own connection (shared DB), not the server .env — same
    # multi-tenant credential fix as GitHub (Bugs S.No 74/113).
    return FigmaDesignSource(
        FigmaConfig.from_connection(conn), default_file_key=file_key, transport=transport
    )


def _build_xray(conn) -> TestMgmt:
    from django.conf import settings

    from .rate_governor import governed_transport
    from .xray.config import XrayConfig
    from .xray.testmgmt import XrayTestMgmt

    project = (conn.scopes or {}).get("project_key") or settings.XRAY_PROJECT_KEY
    transport = governed_transport(conn.tenant_id, conn.capability)
    # Per-tenant client_id/secret from the tenant's own connection (shared DB), not the server
    # .env — same multi-tenant credential fix as GitHub (Bugs S.No 74/113).
    return XrayTestMgmt(XrayConfig.from_connection(conn), project=project, transport=transport)


def _build_builtin_codeintel(conn) -> CodeIntel:
    # The built-in SOTA analyzer (D1) — no creds, local compute (git + filesystem), so no
    # transport/governor. Repowise is the optional connector behind the same capability.
    from .codeintel.builtin import BuiltinCodeIntel

    return BuiltinCodeIntel()


def _build_builtin_a11yai(conn) -> A11yAI:
    # The platform's own accessibility judge — no creds (judgment runs through the
    # ExecutionDriver, not a model API), so no transport/governor. Tenant-bound because
    # every judgment is started on that tenant's behalf and its results are that tenant's.
    from .a11yai.builtin import BuiltinA11yAI

    return BuiltinA11yAI(tenant_id=conn.tenant_id, scopes=conn.scopes or {})


# (capability, connector) -> builder. The single place vendors are wired (#9);
# extend via register_connector for new vendors without touching callers.
_BUILDERS: dict[tuple[str, str], Callable[[object], object]] = {
    ("docstore", "confluence"): _build_confluence,
    ("tasktracker", "jira"): _build_jira,
    ("codehost", "github"): _build_github,
    ("designsource", "figma"): _build_figma,
    ("testmgmt", "xray"): _build_xray,
    ("codeintel", "builtin"): _build_builtin_codeintel,
    ("a11yai", "builtin"): _build_builtin_a11yai,
}


def register_connector(
    capability: str, connector: str, builder: Callable[[object], object]
) -> None:
    _BUILDERS[(capability, connector)] = builder


def get_builder(capability: str, connector: str) -> Callable[[object], object] | None:
    """The registered builder for a (capability, connector) pair, or None if unregistered
    (P4.7-T6 `test-connection` uses this to check a chosen vendor is actually wired)."""
    return _BUILDERS.get((capability, connector))


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


def get_capability(
    tenant_id, capability: str
) -> DocStore | TaskTracker | CodeHost | DesignSource | TestMgmt | CodeIntel | A11yAI:
    """Return the tenant's connector for a capability, or raise CapabilityUnavailable."""
    conn = get_connection(tenant_id, capability)
    if conn is None:
        # B3-2/X-2: never embed the tenant id in a user-facing error — this message can surface
        # in the UI (onboarding register, publish). Say what's wrong + how to fix, no identifiers.
        raise CapabilityUnavailable(
            f"No {capability} connector is configured for this workspace. "
            "Connect one on the Integrations page first."
        )
    builder = _BUILDERS.get((conn.capability, conn.connector))
    if builder is None:
        raise CapabilityError(
            "The platform can't use this connection — its service isn't supported. "
            "Reconnect it from the Integrations screen."
        )
    return builder(conn)
