"""GitHub connection config — loaded from Django settings (which read .env).

Headless, per-tenant auth (D1): a GitHub App-installation token or PAT resolved via the
`IntegrationConnection.token_ref` seam (Phase-5 vault). The platform is a server-side,
multi-tenant caller — not a local `gh` CLI.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GithubConfig:
    api_url: str           # https://api.github.com  (or GHES base)
    token: str             # App-installation token or PAT

    @classmethod
    def from_settings(cls) -> GithubConfig:
        from django.conf import settings

        return cls(
            api_url=settings.GITHUB_API_URL.rstrip("/"),
            token=settings.GITHUB_TOKEN,
        )

    @classmethod
    def from_connection(cls, conn) -> GithubConfig:
        """Resolve the token from the tenant's own IntegrationConnection (the encrypted
        `access_token` the connect form stored), NOT the server `.env`. This is what makes the
        platform truly multi-tenant/multi-user: the credential lives in the shared DB and travels
        with the tenant, so any worker that runs a build for that tenant uses the correct token —
        the shared-Temporal-queue cross-worker token mismatch (Bugs S.No 112) becomes impossible.

        Falls back to `settings.GITHUB_TOKEN` only when the tenant has no stored secret, so
        single-dev / local / CI setups (and tests) keep working unchanged."""
        from django.conf import settings

        from apps.integrations.crypto import decrypt_secrets

        secrets = decrypt_secrets(getattr(conn, "secret_encrypted", "") or "")
        token = secrets.get("access_token") or settings.GITHUB_TOKEN
        return cls(api_url=settings.GITHUB_API_URL.rstrip("/"), token=token)

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.token)

    def auth_header(self) -> str:
        return f"Bearer {self.token}"
