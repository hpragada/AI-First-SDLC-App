"""Xray Cloud connection config — loaded from Django settings (which read .env).

Headless, per-tenant auth (D3): Xray Cloud issues a bearer token from a `client_id` /
`client_secret` pair (resolved via the `IntegrationConnection.token_ref` seam — Phase-5
vault). The platform is a server-side, multi-tenant caller; the Xray MCP stays the optional
agent-side transport, not this path.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class XrayConfig:
    api_url: str           # https://xray.cloud.getxray.app
    client_id: str
    client_secret: str

    @classmethod
    def from_settings(cls) -> XrayConfig:
        from django.conf import settings

        return cls(
            api_url=settings.XRAY_API_URL.rstrip("/"),
            client_id=settings.XRAY_CLIENT_ID,
            client_secret=settings.XRAY_CLIENT_SECRET,
        )

    @classmethod
    def from_connection(cls, conn) -> XrayConfig:
        """Resolve the client_id/client_secret from the tenant's own IntegrationConnection (the
        encrypted secrets the connect form stored), not the server `.env` — so a planning-phase
        Xray import for this tenant uses the right credential on ANY worker (Bugs S.No 74/113,
        same fix as GitHub S.No 112). Each field falls back to settings when the tenant has no
        stored secret, keeping single-dev / CI / tests working unchanged."""
        from django.conf import settings

        from apps.integrations.crypto import decrypt_secrets

        secrets = decrypt_secrets(getattr(conn, "secret_encrypted", "") or "")
        return cls(
            api_url=settings.XRAY_API_URL.rstrip("/"),
            client_id=secrets.get("client_id") or settings.XRAY_CLIENT_ID,
            client_secret=secrets.get("client_secret") or settings.XRAY_CLIENT_SECRET,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.client_id and self.client_secret)
