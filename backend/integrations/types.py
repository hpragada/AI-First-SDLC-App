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


@dataclass(frozen=True)
class BranchRef:
    """A branch read through a CodeHost (read-through, not stored)."""

    repo: str            # "owner/name"
    name: str
    sha: str
    url: str = ""


@dataclass(frozen=True)
class PullRequestRef:
    """Pointer to a pull request — persisted into Artifact/WorkItem.external_ref
    (pointer, not body: #1/#3). `pr_ref` is the connector-stable handle "owner/name#N"."""

    sor: str = "git"     # SoR.GIT
    repo: str = ""       # "owner/name"
    number: int = 0
    head: str = ""       # branch
    url: str = ""
    sha: str | None = None

    @property
    def pr_ref(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class PullRequest:
    """A pull request read through a CodeHost (read-through, live)."""

    repo: str
    number: int
    title: str
    state: str           # "open" | "closed"
    head: str
    base: str
    url: str
    sha: str | None = None
    merged: bool = False
    draft: bool = False

    @property
    def pr_ref(self) -> str:
        return f"{self.repo}#{self.number}"


@dataclass(frozen=True)
class DesignToken:
    """A design variable read through a DesignSource (read-through, not stored).
    `kind` is one of color/type/spacing/radius/elevation/flag; `ref` is the source
    variable id, kept for the Code Connect mapping and the deferred canvas round-trip."""

    name: str
    kind: str            # "color" | "type" | "spacing" | "radius" | "elevation" | "flag"
    value: str           # resolved value (hex / px / token expr)
    ref: str | None = None


@dataclass(frozen=True)
class ComponentRef:
    """A design-system component published in a design file (Code Connect source)."""

    key: str             # Figma component key
    name: str
    node_id: str
    url: str = ""


@dataclass(frozen=True)
class DesignContext:
    """The current design read through a DesignSource — structural pointers only,
    never a copied design body (#3). `frames` are {node_id, name, type} summaries."""

    file_key: str
    name: str
    frames: list[dict]
    url: str = ""


@dataclass(frozen=True)
class DesignRef:
    """Pointer to a design object in a DesignSource — persisted into
    `Artifact.external_ref` (pointer, not body: #1/#3)."""

    sor: str = "figma"   # SoR.FIGMA
    file_key: str = ""
    node_id: str | None = None
    url: str = ""
    version: int | None = None


@dataclass(frozen=True)
class DesignSpec:
    """Input to the deferred code-to-canvas write seam (`generate_figma_design`, D2)."""

    name: str
    payload: dict


class CapabilityError(Exception):
    """A connector call failed. Carries the upstream status when there was one."""

    def __init__(self, message: str, *, status: int | None = None, detail: object = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class CapabilityUnavailable(CapabilityError):
    """No connector is configured for this tenant+capability (callers fall back to internal)."""
