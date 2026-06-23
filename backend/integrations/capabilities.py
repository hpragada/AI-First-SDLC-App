"""Capability interfaces (the integration seam — non-negotiable #9).

Callers depend on these Protocols, never on a vendor. `TaskTracker` + the per-tenant
`get_capability(...)` selection factory arrive in the next Phase-1 tasks; `DocStore`
is defined here for the Confluence connector to implement.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import DocHit, DocPage, ExternalRef


@runtime_checkable
class DocStore(Protocol):
    """Documentation system of record (Confluence-shaped, vendor-free)."""

    def create_page(self, *, space: str, title: str, body_html: str,
                    parent_ref: str | None = None) -> ExternalRef: ...

    def update_page(self, *, page_ref: str, title: str, body_html: str,
                    base_version: int) -> ExternalRef:
        """Update a page; `base_version` is the version being edited (optimistic lock)."""
        ...

    def get_page(self, *, page_ref: str) -> DocPage: ...

    def search(self, *, query: str, space: str | None = None) -> list[DocHit]: ...
