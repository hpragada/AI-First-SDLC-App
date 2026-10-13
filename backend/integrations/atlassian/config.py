"""Atlassian connection config — loaded from Django settings (which read .env)."""
from __future__ import annotations

import base64
from dataclasses import dataclass


@dataclass(frozen=True)
class AtlassianConfig:
    site_url: str          # https://<site>.atlassian.net  (no trailing slash)
    email: str
    api_token: str
    cloud_id: str = ""

    @classmethod
    def from_settings(cls) -> AtlassianConfig:
        from django.conf import settings

        return cls(
            site_url=settings.ATLASSIAN_SITE_URL.rstrip("/"),
            email=settings.ATLASSIAN_EMAIL,
            api_token=settings.ATLASSIAN_API_TOKEN,
            cloud_id=settings.ATLASSIAN_CLOUD_ID,
        )

    @classmethod
    def from_connection(cls, conn) -> AtlassianConfig:
        """Resolve per-tenant Atlassian creds from the tenant's own IntegrationConnection, not the
        server `.env` (Bugs S.No 74/113, same fix as GitHub S.No 112). Basic auth is
        `email:api_token`: the email + site come from the connection's binding `scopes`, the token
        from its encrypted secrets. Each field falls back to settings when unset, so single-tenant
        / CI / tests keep working.

        `site_url` must be the BARE site (e.g. https://acme.atlassian.net) — the connectors append
        `/wiki/...` and `/rest/api/...` themselves — but the Confluence connect form asks for the
        `.../wiki` base, so a trailing `/wiki` is stripped here."""
        from django.conf import settings

        from apps.integrations.crypto import decrypt_secrets

        scopes = getattr(conn, "scopes", None) or {}
        secrets = decrypt_secrets(getattr(conn, "secret_encrypted", "") or "")
        site_url = (scopes.get("base_url") or settings.ATLASSIAN_SITE_URL).rstrip("/")
        if site_url.endswith("/wiki"):
            site_url = site_url[: -len("/wiki")]
        return cls(
            site_url=site_url,
            email=scopes.get("email") or settings.ATLASSIAN_EMAIL,
            api_token=secrets.get("api_token") or settings.ATLASSIAN_API_TOKEN,
            cloud_id=scopes.get("cloud_id") or settings.ATLASSIAN_CLOUD_ID,
        )

    @property
    def configured(self) -> bool:
        return bool(self.site_url and self.email and self.api_token)

    def basic_auth_header(self) -> str:
        raw = f"{self.email}:{self.api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode()
