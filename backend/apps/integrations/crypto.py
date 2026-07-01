"""Symmetric encryption for `IntegrationConnection.secret_encrypted` (P4.7-T6, DECISION-4).

Secrets are encrypted at rest behind a settings-driven key (`INTEGRATIONS_SECRET_KEY`, falling
back to `SECRET_KEY`) and never decrypted back into an API response — only `configured: bool`
is exposed. A real per-tenant vault/KMS is Phase 5 (the same kind of seam as `token_ref`,
see `integrations/registry.py`); swapping it in means changing only this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    from django.conf import settings

    key = getattr(settings, "INTEGRATIONS_SECRET_KEY", "") or settings.SECRET_KEY
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest()))


def encrypt_secrets(secrets: dict) -> str:
    """Encrypt a secrets dict to a storable blob. An empty/falsy dict stores as "" (unset)."""
    if not secrets:
        return ""
    payload = json.dumps(secrets, sort_keys=True).encode()
    return _fernet().encrypt(payload).decode()


def decrypt_secrets(blob: str) -> dict:
    """Decrypt a stored blob back to its secrets dict. Internal use only (connector building,
    Phase 5) — never exposed over the API."""
    if not blob:
        return {}
    try:
        return json.loads(_fernet().decrypt(blob.encode()).decode())
    except InvalidToken:
        return {}
