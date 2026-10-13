"""Per-tenant credential resolution for the non-GitHub connectors (Bugs S.No 74/113).

Before this, Atlassian / Figma / Xray authenticated only from the server `.env` — the token a
tenant entered in the connect form was stored but never used at runtime. These tests pin that
`from_connection` now reads the tenant's own stored binding + secrets (mirroring the GitHub fix,
S.No 112), falling back to settings per-field when the tenant hasn't stored one.
"""
from types import SimpleNamespace

import pytest

from apps.integrations.crypto import encrypt_secrets
from integrations.atlassian.config import AtlassianConfig
from integrations.figma.config import FigmaConfig
from integrations.xray.config import XrayConfig


def _conn(scopes, secrets):
    return SimpleNamespace(scopes=scopes, secret_encrypted=encrypt_secrets(secrets))


def test_atlassian_from_connection_uses_tenant_email_token_and_bare_site():
    conn = _conn(
        {"base_url": "https://acme.atlassian.net/wiki", "email": "po@acme.com"},
        {"api_token": "tenant-token"},
    )
    cfg = AtlassianConfig.from_connection(conn)
    assert cfg.email == "po@acme.com"
    assert cfg.api_token == "tenant-token"
    # Confluence's "/wiki" base is normalised to the bare site (connectors append /wiki themselves)
    assert cfg.site_url == "https://acme.atlassian.net"


def test_atlassian_from_connection_falls_back_to_settings(settings):
    settings.ATLASSIAN_EMAIL = "env@acme.com"
    settings.ATLASSIAN_API_TOKEN = "env-token"
    settings.ATLASSIAN_SITE_URL = "https://env.atlassian.net"
    cfg = AtlassianConfig.from_connection(_conn({}, {}))
    assert cfg.email == "env@acme.com"
    assert cfg.api_token == "env-token"
    assert cfg.site_url == "https://env.atlassian.net"


def test_figma_from_connection_uses_tenant_token():
    cfg = FigmaConfig.from_connection(_conn({"file_key": "aBc"}, {"access_token": "tenant-figma"}))
    assert cfg.token == "tenant-figma"


def test_xray_from_connection_uses_tenant_client_creds():
    cfg = XrayConfig.from_connection(
        _conn({"project_key": "PAY"}, {"client_id": "cid", "client_secret": "csecret"})
    )
    assert cfg.client_id == "cid"
    assert cfg.client_secret == "csecret"


@pytest.mark.parametrize("cfg_cls", [FigmaConfig, XrayConfig])
def test_missing_secret_falls_back_without_crashing(cfg_cls):
    # No stored secret → falls back to settings; must not raise.
    cfg = cfg_cls.from_connection(_conn({}, {}))
    assert cfg is not None
