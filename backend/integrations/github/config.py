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

    @property
    def configured(self) -> bool:
        return bool(self.api_url and self.token)

    def auth_header(self) -> str:
        return f"Bearer {self.token}"
