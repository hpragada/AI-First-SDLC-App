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

    @property
    def configured(self) -> bool:
        return bool(self.site_url and self.email and self.api_token)

    def basic_auth_header(self) -> str:
        raw = f"{self.email}:{self.api_token}".encode()
        return "Basic " + base64.b64encode(raw).decode()
