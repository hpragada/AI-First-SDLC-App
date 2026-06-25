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

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.client_id and self.client_secret)
