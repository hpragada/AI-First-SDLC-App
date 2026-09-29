"""Integrations management services (P4.7-T6, DECISION-4) — admin CRUD over the tenant's
per-capability connections + a secret store. `create_integration`/`update_integration` accept
secrets and hand them to `apps.integrations.crypto.encrypt_secrets`; nothing here (or in the
serializer/view layer) ever decrypts them back into a response — `IntegrationConnection.
is_configured` is the only signal exposed.

`probe_connection` is the pure check (no DB writes) shared by two entry points (Bugs S.No 156):
`test_integration_connection` probes a SAVED row and records `health`, while `test_credentials`
probes an UNSAVED in-memory row so an admin can verify credentials **before** committing them.
Where a connector implements `ping()` the probe makes a real authenticated read-only call, so a
mistyped token or host now fails the test instead of passing a constructible-only wiring check.
"""
from __future__ import annotations

import logging

from apps.integrations.crypto import encrypt_secrets
from apps.integrations.models import IntegrationConnection

logger = logging.getLogger(__name__)

# The fixed capability set (DECISION-4 / spec §3 T6) — independent of which vendors are
# builder-wired yet, so an admin can record a connection ahead of `register_connector` support.
CAPABILITIES = {"docstore", "tasktracker", "codehost", "designsource", "testmgmt", "codeintel",
                "a11yai"}


# Capabilities the platform provides itself and auto-provisions for every tenant, as
# (capability, connector). They take no credentials and offer no vendor choice, so there is
# nothing a human could usefully fill in — presenting them on the "connect your tools" screen
# would be a control that only looks like a control (team decision, 2026-08-12).
#
# `codeintel` joined them on 2026-09-10 (Bugs S.No N1), which is the change this comment used to
# describe as "adding the pair here plus a backfill migration is the whole change". Three things
# settled it:
#   - Nothing in the platform resolves code intelligence through this registry. There is no
#     `get_capability(..., "codeintel")` anywhere: the analyser is constructed directly, with no
#     credentials, on the developer's own machine — as an MCP subprocess for the agent path
#     (`runner/companion/codeintel_mcp.py`) or in the daemon for the mechanical one.
#   - The Integrations page hardcoded the card as permanently "Connected / Built-in", so it was
#     never a control a user could act on in the first place.
#   - Real workspaces were only ever auto-provisioned `a11yai`; the codeintel row came from the
#     demo seed. So a real tenant could have no row at all while its card claimed Connected —
#     the screen was stating something untrue.
AUTO_PROVISIONED = (("a11yai", "builtin"), ("codeintel", "builtin"))


def provision_builtin_capabilities(tenant) -> list[IntegrationConnection]:
    """Give a tenant the platform's own credential-free capabilities.

    Called from `create_tenant` (alongside `seed_agent_specs`, for the same reason: a new
    workspace must be able to run the lifecycle immediately, not after a setup step nobody
    could complete). Idempotent — safe to call again on an existing tenant, which is what
    lets the backfill migration and this share one behaviour.
    """
    provisioned = []
    for capability, connector in AUTO_PROVISIONED:
        conn, _ = IntegrationConnection.objects.get_or_create(
            tenant=tenant, capability=capability,
            defaults={"connector": connector, "scopes": {}, "token_ref": "builtin"},
        )
        provisioned.append(conn)
    return provisioned


class IntegrationError(Exception):
    """An integrations-management operation was rejected. `status` maps to the HTTP code
    (400 unsupported capability, 409 already connected)."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def create_integration(
    *, tenant, capability: str, vendor: str, binding: dict | None = None,
    secrets: dict | None = None,
) -> IntegrationConnection:
    """Connect a capability (S-12 drawer submit). One connection per (tenant, capability) —
    reconnecting to a different vendor is a PATCH, not a second POST."""
    if capability not in CAPABILITIES:
        raise IntegrationError("That kind of connection isn't supported.")
    if IntegrationConnection.objects.filter(
        tenant_id=tenant.id, capability=capability
    ).exists():
        raise IntegrationError(
            f"{capability} is already connected — edit or disconnect it first.", status=409
        )
    return IntegrationConnection.objects.create(
        tenant=tenant, capability=capability, connector=vendor,
        scopes=binding or {}, token_ref="secret_store",
        secret_encrypted=encrypt_secrets(secrets or {}),
    )


def update_integration(
    *, conn: IntegrationConnection, vendor: str | None = None,
    binding: dict | None = None, secrets: dict | None = None,
) -> IntegrationConnection:
    """Partial update (S-12 edit). `secrets` is only re-encrypted when the caller actually
    supplied one — omitting it (or sending an empty object) leaves the stored credential
    untouched (DECISION-4).

    An EMPTY `secrets` object is treated as "no change", NOT as "erase" (Bugs S.No 156): the
    connect drawer sends `secrets: {}` whenever an admin edits a configured connection without
    retyping the token, and `{}` is not None — so it used to re-encrypt an empty dict and destroy
    the credential silently. There is deliberately no way to blank a secret through this path;
    disconnect the integration to remove it."""
    fields = []
    if vendor is not None:
        conn.connector = vendor
        fields.append("connector")
    if binding is not None:
        conn.scopes = binding
        fields.append("scopes")
    if secrets:
        conn.secret_encrypted = encrypt_secrets(secrets)
        fields.append("secret_encrypted")
    if fields:
        conn.save(update_fields=[*fields, "updated_at"])
    return conn


def probe_connection(conn: IntegrationConnection) -> dict:
    """Check a connection WITHOUT touching the database — returns `{ok, detail, fix_hint?}`.

    Pure on purpose (Bugs S.No 156): `conn` may be an unsaved, in-memory row, which is what lets
    an admin test credentials BEFORE saving them. `test_integration_connection` wraps this and
    persists `health`; `test_credentials` uses it on a throwaway object that is never saved.

    Where the connector supports it, this now makes a REAL authenticated call (`ping()` — a cheap,
    read-only "who am I") instead of only proving the connector is constructible. That old check
    reported OK for a mistyped token or site URL, which is exactly what a connection test exists to
    catch. A connector with no `ping()` keeps the wiring-only check and says so honestly."""
    from integrations.registry import get_builder

    builder = get_builder(conn.capability, conn.connector)
    if builder is None:
        # Screen Words group 5: "No connector registered for docstore:notion." printed two stored
        # keys at an admin. Same words as the registry's refusal for the same situation.
        return {
            "ok": False,
            "detail": "The platform can't use this connection — its service isn't supported. "
                      "Reconnect it and choose a supported service.",
            "fix_hint": "Choose a supported vendor for this capability.",
        }
    if not conn.is_configured:
        return {
            "ok": False,
            "detail": "No credentials have been saved for this connection.",
            "fix_hint": "Add the required secret(s) and try again.",
        }
    try:
        connector = builder(conn)  # constructs the connector object — no network call
    except Exception as exc:  # this endpoint always returns {ok, detail}, never a 500
        # Screen Words group 5: the exception text went straight to the admin's screen. It goes
        # to the log, where a developer will look; the admin gets what to check.
        logger.warning("Building the %s:%s connector failed: %s",
                       conn.capability, conn.connector, exc)
        return {"ok": False,
                "detail": "The connection settings couldn't be used. Check each field, "
                          "then test again.",
                "fix_hint": "Check the credentials and the site/host you entered, then re-test."}

    ping = getattr(connector, "ping", None)
    if not callable(ping):
        # No live probe for this vendor yet — don't imply we reached it.
        return {"ok": True,
                "detail": "Connector is configured and ready (no live check for this vendor)."}
    try:
        return {"ok": True, "detail": ping()}
    except Exception as exc:  # noqa: BLE001 — any transport/auth error is a failed test, not a 500
        return {"ok": False, "detail": _probe_failure_detail(exc),
                "fix_hint": "Check the credentials and the site/host you entered, then re-test."}


def _probe_failure_detail(exc: Exception) -> str:
    """Turn a probe error into something an admin can act on (Bugs S.No 156) — the raw
    "Atlassian GET /rest/api/3/myself -> 401" tells them nothing about what to change."""
    status = getattr(exc, "status", None)
    if status in (401, 403):
        return ("The credentials were rejected (not authorized). Check the API token is current "
                "and belongs to the account/email you entered, and that it has access.")
    if status == 404:
        return ("Authenticated, but that address isn't right — check the site URL / host for "
                "typos.")
    if status == 429:
        return "The vendor is rate-limiting us right now. Wait a moment and re-test."
    if status is not None and status >= 500:
        return f"The vendor's API returned an error ({status}). It may be down — re-test shortly."
    return f"Could not reach the vendor: {exc}"


def test_integration_connection(conn: IntegrationConnection) -> dict:
    """Probe a SAVED connection and record the outcome on `health`."""
    result = probe_connection(conn)
    conn.health = (IntegrationConnection.Health.HEALTHY if result["ok"]
                   else IntegrationConnection.Health.DOWN)
    conn.save(update_fields=["health", "updated_at"])
    return result


def test_credentials(*, tenant, capability: str, vendor: str, binding: dict | None = None,
                     secrets: dict | None = None) -> dict:
    """Test credentials BEFORE saving them (Bugs S.No 156).

    Previously "Test connection" needed a saved row (the endpoint was detail-routed and did
    `get_object()`), so an admin had to commit credentials to the tenant before finding out they
    were wrong. This builds a throwaway in-memory connection and probes it — **it is never
    saved**, and nothing here writes to the database."""
    if capability not in CAPABILITIES:
        raise IntegrationError("That kind of connection isn't supported.")
    scratch = IntegrationConnection(
        tenant=tenant, capability=capability, connector=vendor,
        scopes=binding or {}, token_ref="secret_store",
        secret_encrypted=encrypt_secrets(secrets or {}),
    )
    return probe_connection(scratch)
