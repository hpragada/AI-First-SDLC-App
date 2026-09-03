"""Figma connection config — loaded from Django settings (which read .env).

Headless, per-tenant auth (D1): a Figma personal-access token (or OAuth bearer) resolved
via the `IntegrationConnection.token_ref` seam (Phase-5 vault). Figma authenticates a PAT
with the `X-Figma-Token` header; the Figma remote MCP stays the optional agent-side
transport, not this path.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FigmaConfig:
    api_url: str           # https://api.figma.com
    token: str             # personal-access token (X-Figma-Token)

    @classmethod
    def from_settings(cls) -> FigmaConfig:
        from django.conf import settings

        return cls(
            api_url=settings.FIGMA_API_URL.rstrip("/"),
            token=settings.FIGMA_TOKEN,
        )

    @classmethod
    def from_connection(cls, conn) -> FigmaConfig:
        """Resolve the token from the tenant's own IntegrationConnection (the encrypted
        `access_token` the connect form stored), not the server `.env` — so a planning-phase
        Figma read for this tenant uses the right credential on ANY worker (Bugs S.No 74/113,
        same fix as GitHub S.No 112). Falls back to `settings.FIGMA_TOKEN` when the tenant has
        no stored secret, keeping single-dev / CI / tests working unchanged."""
        from django.conf import settings

        from apps.integrations.crypto import decrypt_secrets

        secrets = decrypt_secrets(getattr(conn, "secret_encrypted", "") or "")
        return cls(
            api_url=settings.FIGMA_API_URL.rstrip("/"),
            token=secrets.get("access_token") or settings.FIGMA_TOKEN,
        )

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.token)
