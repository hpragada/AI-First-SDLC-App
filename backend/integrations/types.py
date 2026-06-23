"""Vendor-free value objects + errors shared across connectors."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExternalRef:
    """Pointer to an object in a system-of-record — what we persist into
    `Artifact.external_ref` / `WorkItem.external_ref` (pointer, not body: #1/#3)."""

    sor: str            # "confluence" | "jira"
    id: str             # page id / issue key (e.g. "PROJ-123")
    url: str
    version: int | None = None


@dataclass(frozen=True)
class DocPage:
    """A documentation page read through a DocStore (read-through, not stored)."""

    id: str
    title: str
    body_html: str       # storage representation (Confluence XHTML)
    version: int
    url: str
    space_key: str | None = None


@dataclass(frozen=True)
class DocHit:
    """A search result from a DocStore."""

    id: str
    title: str
    url: str


@dataclass(frozen=True)
class Issue:
    """An issue read through a TaskTracker (read-through, not stored)."""

    key: str
    summary: str
    status: str
    issue_type: str
    url: str
    parent_ref: str | None = None


@dataclass(frozen=True)
class IssueHit:
    """A search result from a TaskTracker."""

    key: str
    summary: str


class CapabilityError(Exception):
    """A connector call failed. Carries the upstream status when there was one."""

    def __init__(self, message: str, *, status: int | None = None, detail: object = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class CapabilityUnavailable(CapabilityError):
    """No connector is configured for this tenant+capability (callers fall back to internal)."""
