"""Stand up Django so the MCP server can reuse the platform's ORM + RLS util.

The Platform-State server is part of the backend deployable: it runs in the backend
environment (Django + models already installed) and is launched on-demand over stdio
by the ClaudeDriver (P0-T6). Reusing the ORM keeps a single source of schema truth.
"""
import os
import sys
from pathlib import Path


def setup_django() -> None:
    """Idempotent: a no-op if Django is already configured (e.g. under pytest)."""
    from django.apps import apps

    if apps.ready:
        return
    backend = Path(__file__).resolve().parent.parent / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    import django

    django.setup()
