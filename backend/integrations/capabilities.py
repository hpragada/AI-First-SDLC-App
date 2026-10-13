"""Capability interfaces (the integration seam — non-negotiable #9).

Callers depend on these Protocols, never on a vendor. The per-tenant
`get_capability(...)` selection factory arrives in the next Phase-1 task; `DocStore`
(Confluence) and `TaskTracker` (Jira) are defined here for their connectors.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from .types import (
    A11yCandidate,
    A11yJourney,
    A11yJudgment,
    BranchRef,
    ComponentRef,
    DesignContext,
    DesignRef,
    DesignSpec,
    DesignToken,
    DocHit,
    DocPage,
    ExternalRef,
    IntelIndex,
    Issue,
    IssueHit,
    PullRequest,
    PullRequestRef,
    TestCase,
    TestExecutionImport,
    TestStep,
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

    def mark_ready_for_review(self, *, pr_ref: str) -> None:
        """Take a draft PR out of draft (idempotent — a ready PR is unchanged). Required before
        merge: hosts refuse to merge a draft PR. Call at the gated merge, not during review."""
        ...

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


@runtime_checkable
class TestMgmt(Protocol):
    # NB: no `__test__ = False` here — on a runtime_checkable Protocol it becomes a required
    # member and breaks isinstance(). pytest's "cannot collect" note on this class is benign.
    """Test-management system of record (Xray-shaped, vendor-free). Tests + executions live
    in the SoR; the platform persists only pointers + a `test_report` artifact (#1/#3)."""

    def create_test(self, *, project: str, summary: str, steps: list[TestStep],
                    fields: dict | None = None) -> ExternalRef:
        """Author a test case (idempotent by summary — an existing test is returned)."""
        ...

    def get_test(self, *, test_ref: str) -> TestCase: ...                          # read-through

    def import_results(self, *, execution: TestExecutionImport) -> ExternalRef:
        """Import an execution's results (idempotent: `execution.execution_ref` updates the
        same execution rather than duplicating — register-don't-recreate)."""
        ...

    def link_defect(self, *, test_ref: str, defect_ref: str) -> None: ...          # test↔defect

    def search(self, *, jql: str) -> list[IssueHit]: ...


@runtime_checkable
class CodeIntel(Protocol):
    """Code-intelligence system (engine-agnostic, vendor-free). The built-in SOTA analyzer
    is the default; Repowise (or another engine) plugs in behind this same 8-tool surface, so
    downstream agents never change (D1). Runs in the companion worktree; the platform persists
    only the index + artifacts + Knowledge-Index chunks, never the source (#1/#3, D2).
    `index()` analyses a workspace; the get_* tools read the computed analysis."""

    def index(self, *, workspace, repo: str, scope: dict | None = None) -> IntelIndex: ...
    def get_overview(self, *, repo: str) -> dict: ...
    def get_context(self, *, repo: str, targets: list[str]) -> dict: ...
    def get_risk(self, *, repo: str, targets: list[str]) -> dict: ...
    def get_why(self, *, repo: str, query: str = "") -> list[dict]: ...
    def search_codebase(self, *, repo: str, query: str) -> list[dict]: ...
    def get_dependency_path(self, *, repo: str, frm: str, to: str) -> list[str]: ...
    def get_dead_code(self, *, repo: str) -> list[dict]: ...
    def get_architecture_diagram(self, *, repo: str, module: str | None = None) -> str: ...


@runtime_checkable
class A11yAI(Protocol):
    """AI accessibility judgment (model-agnostic, vendor-free) — the WCAG questions a rule
    scanner like axe genuinely cannot answer: is the alt text *meaningful*, is this really a
    button, is the arrangement of this table written into the markup, is meaning carried by
    colour *alone*, does the visible label match the accessible name.

    A capability for its **shape** (#9): callers ask `get_capability(tenant, "a11yai")` and
    never name a model or vendor, so the judge underneath can be swapped without touching
    them. It is NOT a model client — the implementation dispatches a constrained agent run
    through the `ExecutionDriver` (#7); no connector anywhere makes a direct model call, and
    no API credential is involved (QA-02/QA-02a build the dispatch and the judge agent).

    Two rules bind every implementation:
      - An AI judgment NEVER overrides a deterministic axe failure — it adds what axe cannot
        see, it does not overrule what axe proved.
      - A check that cannot answer returns `uncertain` (see `types.uncertain`) so the item
        goes to human review. It never guesses, raises, or returns a partial result.

    **These are per-element questions, not a way to start work** (D-A11Y-4, QA-03). The
    platform's own implementation judges in batches — one agent run per dispatch, so ten
    screens cost one run and not four hundred — so asking it about a single element answers
    from what has already been judged, and says `uncertain` ("not judged yet") when nothing
    has. An outside accessibility-AI service is free to answer synchronously here instead;
    that is why the shape stays per-element, and why no caller has to care which it is
    talking to. `project_id` narrows the answer to one project's judgments; without it the
    answer comes from anything the tenant has judged with the same input.
    """

    def check_alt(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 1.1.1 — is the alt text meaningful *for what this image does here*?"""
        ...

    def check_semantics(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 1.3.1 / 4.1.2 — is a thing that looks and behaves like a control actually
        exposed as one (real role/name/state), or a styled `div` faking it?"""
        ...

    def check_structure(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 1.3.1 — is the arrangement a sighted person can see written into the markup?

        The container question, and the counterpart to `check_semantics`'s element question: a
        table whose top row is obviously headings, a list of items, a set of fields that
        clearly belong together. None of those is *pretending* to be anything, so nothing else
        here reaches them.
        """
        ...

    def check_color(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 1.4.1 — is meaning conveyed by colour alone, with no text/shape/icon backup?"""
        ...

    def check_label(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 2.5.3 — does the visible label match the accessible name a screen reader and a
        voice-control user would say?"""
        ...

    def check_graphics(self, *, candidate: A11yCandidate, project_id=None) -> A11yJudgment:
        """WCAG 1.4.11 — can a person actually make out the parts of this icon, chart or
        diagram that carry the meaning?

        **The half of Non-text Contrast that arithmetic cannot reach.** Whether a control's
        edge clears 3:1 is a measurement and `apps.a11y.page_rules` makes it. Which parts of a
        picture *matter* has to be known before any ratio means anything, and nothing
        deterministic knows that — so the two halves ship together, and neither is the
        criterion alone (correction R14, QA-25).

        **Its scope is wider than `check_alt`'s on purpose.** That one asks what assistive
        technology is TOLD, so it skips a graphic that is never announced. This asks what a
        person can SEE, so a bare `<svg>` with no name, and an icon painted as a CSS background
        image, are both in scope here and in neither of them there. The same element is
        routinely judged by both, and an accurate alt text on an invisible icon passes one and
        fails the other.

        **This method was missing from 27 August to 1 September** while the checker itself ran
        normally, because an audit reads its checker list from the rules rather than from here.
        `test_a11yai_capability` said so every day. What could not be done in that window was
        asking the capability about one element — which is how anything outside an audit run
        reaches this criterion.
        """
        ...

    def check_journey(self, *, journey: A11yJourney, project_id=None) -> list[A11yJudgment]:
        """WCAG 2.1.1 / 2.1.2 / 2.4.3 / 2.4.7 / 2.4.11 / 3.2.1 / 3.2.2 / 4.1.3 — the eight
        questions that can only be answered by **operating** the application (QA-20).

        The checks above ask about a page standing still. This one asks what happens while
        someone uses it: does tabbing ever trap you, does focus stay visible and unobscured,
        does anything change under you when an element takes focus or a field is typed in, is a
        status message announced at all. None of it is visible in a captured page, which is why
        this is the one check whose input is a *journey* rather than an element.

        Returns a list, not one judgment: eight checkers report separately so QA-22 can promote
        a proven one while a newer one stays advisory. A journey step the agent could not reach
        produces **no judgment for that step** — it is recorded as a blocked step instead. Never
        a pass: "I never got there" and "I got there and it was fine" are different answers, and
        collapsing them is how an untested journey comes back clean.
        """
        ...
