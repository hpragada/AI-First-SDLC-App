"""Integrations management services (P4.7-T6, DECISION-4) — admin CRUD over the tenant's
per-capability connections + a secret store. `create_integration`/`update_integration` accept
secrets and hand them to `apps.integrations.crypto.encrypt_secrets`; nothing here (or in the
serializer/view layer) ever decrypts them back into a response — `IntegrationConnection.
is_configured` is the only signal exposed. `test_integration_connection` checks the chosen
vendor is wired and (if it needs one) a secret has been stored: building a connector makes no
network call today (see `integrations/registry.py`), so this is a wiring check, not a live
probe — a real reachability check is Phase 5 (vault-backed connectors).
"""
from __future__ import annotations

from apps.integrations.crypto import encrypt_secrets
from apps.integrations.models import IntegrationConnection

# The fixed capability set (DECISION-4 / spec §3 T6) — independent of which vendors are
# builder-wired yet, so an admin can record a connection ahead of `register_connector` support.
CAPABILITIES = {"docstore", "tasktracker", "codehost", "designsource", "testmgmt", "codeintel"}


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
        raise IntegrationError(f"Unsupported capability {capability!r}.")
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
    supplied it (not None) — omitting it leaves the stored credential untouched (DECISION-4)."""
    fields = []
    if vendor is not None:
        conn.connector = vendor
        fields.append("connector")
    if binding is not None:
        conn.scopes = binding
        fields.append("scopes")
    if secrets is not None:
        conn.secret_encrypted = encrypt_secrets(secrets)
        fields.append("secret_encrypted")
    if fields:
        conn.save(update_fields=[*fields, "updated_at"])
    return conn


def test_integration_connection(conn: IntegrationConnection) -> dict:
    """Validate the connection is wired + configured, and flip `health` accordingly. Building
    a connector makes no network call (see `integrations/registry.py`) — this proves the
    capability+vendor pair is constructible and a secret has been stored, not that the
    upstream API is currently reachable (that check lands with the Phase-5 vault)."""
    from integrations.registry import get_builder

    builder = get_builder(conn.capability, conn.connector)
    if builder is None:
        conn.health = IntegrationConnection.Health.DOWN
        conn.save(update_fields=["health", "updated_at"])
        return {
            "ok": False,
            "detail": f"No connector registered for {conn.capability}:{conn.connector}.",
            "fix_hint": "Choose a supported vendor for this capability.",
        }
    if not conn.is_configured:
        conn.health = IntegrationConnection.Health.DOWN
        conn.save(update_fields=["health", "updated_at"])
        return {
            "ok": False,
            "detail": "No credentials have been saved for this connection.",
            "fix_hint": "Add the required secret(s) and try again.",
        }
    try:
        builder(conn)  # constructs the connector object — no network call
    except Exception as exc:  # this endpoint always returns {ok, detail}, never a 500
        conn.health = IntegrationConnection.Health.DOWN
        conn.save(update_fields=["health", "updated_at"])
        return {"ok": False, "detail": f"Could not build the connector: {exc}"}
    conn.health = IntegrationConnection.Health.HEALTHY
    conn.save(update_fields=["health", "updated_at"])
    return {"ok": True, "detail": "Connector is configured and ready."}
