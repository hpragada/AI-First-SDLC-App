"""Capability interfaces (the integration seam — non-negotiable #9).

Callers depend on these Protocols, never on a vendor. The per-tenant
`get_capability(...)` selection factory arrives in the next Phase-1 task; `DocStore`
(Confluence) and `TaskTracker` (Jira) are defined here for their connectors.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import (
    BranchRef,
    ComponentRef,
    DesignContext,
    DesignRef,
    DesignSpec,
    DesignToken,
    DocHit,
    DocPage,
    ExternalRef,
    Issue,
    IssueHit,
    PullRequest,
    PullRequestRef,
)


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


@runtime_checkable
class TaskTracker(Protocol):
    """Issue tracker system of record (Jira-shaped, vendor-free). `kind` is the issue
    type name (Epic/Story/Task/Subtask); `parent_ref` is the parent issue key (an
    epic for a story, a story for a subtask). The connector is bound to one project."""

    def create_issue(self, *, kind: str, summary: str, description: str,
                     parent_ref: str | None = None, fields: dict | None = None) -> ExternalRef: ...

    def get_issue(self, *, issue_ref: str) -> Issue: ...

    def transition_issue(self, *, issue_ref: str, to_state: str) -> Issue: ...

    def add_comment(self, *, issue_ref: str, body: str) -> None: ...

    def search(self, *, jql: str) -> list[IssueHit]: ...


@runtime_checkable
class CodeHost(Protocol):
    """Code host system of record (GitHub-shaped, vendor-free). Branches are pushed by
    git in the build runner's worktree (Phase-2 D2); this capability owns the
    PR/merge/status/webhook surface. `pr_ref` is the stable handle "owner/name#N".
    Read-through: PR/branch/file bodies are fetched live, never copied into state."""

    def get_branch(self, *, repo: str, name: str) -> BranchRef | None: ...

    def open_pull_request(self, *, repo: str, head: str, base: str, title: str,
                          body: str, draft: bool = True) -> PullRequestRef:
        """Open a PR for `head` (idempotent — an existing open PR for the head is
        returned, never duplicated: register-don't-recreate)."""
        ...

    def get_pull_request(self, *, pr_ref: str) -> PullRequest: ...

    def list_pr_files(self, *, pr_ref: str) -> list[str]: ...

    def set_commit_status(self, *, repo: str, sha: str, state: str, context: str,
                          description: str = "", target_url: str | None = None) -> None: ...

    def add_pr_comment(self, *, pr_ref: str, body: str) -> None: ...

    def merge_pull_request(self, *, pr_ref: str, method: str = "squash") -> PullRequest:
        """Merge a PR — the gated SoR write for code (#5/#8); call only post-approval."""
        ...

    def get_file(self, *, repo: str, path: str, ref: str) -> str: ...


@runtime_checkable
class DesignSource(Protocol):
    """Design system of record (Figma-shaped, vendor-free). Read-as-SoR is the primary
    mode (G3): the platform consumes the client's *current* design at run time and never
    copies design bodies into state — pointers/tokens only (#1/#3). Write (canvas
    round-trip) is a deferred Phase-3 seam (D2)."""

    def get_design_context(self, *, file_key: str,
                           node_id: str | None = None) -> DesignContext:
        """The current design — structural frame pointers, read-through (live)."""
        ...

    def get_variable_defs(self, *, file_key: str) -> list[DesignToken]:
        """The design tokens (color/type/spacing/radius/elevation) from variables."""
        ...

    def list_components(self, *, file_key: str) -> list[ComponentRef]:
        """The published components — the Code Connect mapping source (PG20)."""
        ...

    def generate_figma_design(self, *, file_key: str, spec: DesignSpec) -> DesignRef:
        """Code-to-canvas write (PG22) — DEFERRED SEAM (D2): beta + Full seat, later."""
        ...
