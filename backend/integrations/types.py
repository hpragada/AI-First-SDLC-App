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
    # The issue's body. For an imported brownfield backlog this is the specification — the
    # summary is a label, the description is what the work actually is. Defaulted so an older
    # connector that doesn't populate it still constructs.
    description: str = ""


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
    # GitHub computes these asynchronously (may be None right after a mutation). `mergeable_state`
    # is the richer signal: "clean" | "behind" (base moved, no conflict) | "dirty" (conflict) |
    # "blocked" | "unknown". Used by the merge gate to update-then-merge, never merge a conflict.
    mergeable: bool | None = None
    mergeable_state: str = ""

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


@dataclass(frozen=True)
class TestStep:
    """One step of a test case (read-through / authored, not stored as platform state)."""

    __test__ = False  # not a pytest test class
    action: str
    data: str = ""
    expected: str = ""


@dataclass(frozen=True)
class TestCase:
    """A test read through a TestMgmt (read-through, not stored). `key` is the SoR issue
    key (e.g. an Xray Test issue "PROJ-123")."""

    __test__ = False  # not a pytest test class
    key: str
    summary: str
    steps: list[TestStep]
    status: str
    url: str


@dataclass(frozen=True)
class TestResult:
    """A single test's outcome in an execution. `status` is PASS | FAIL | SKIP (the
    vendor-free form; the connector maps it to the SoR's status names)."""

    __test__ = False  # not a pytest test class
    test_ref: str
    status: str
    evidence: str = ""


@dataclass(frozen=True)
class TestExecutionImport:
    """A test execution to import into the TestMgmt SoR. `execution_ref` (when set — a prior
    execution key) makes the import idempotent: re-importing updates that execution rather
    than creating a duplicate (register-don't-recreate)."""

    __test__ = False  # not a pytest test class
    project: str
    work_item_ref: str
    results: list[TestResult]
    summary: str = ""
    execution_ref: str | None = None


@dataclass(frozen=True)
class IntelIndex:
    """Summary of a CodeIntel indexing pass (pointer/summary, never copied source: #1/#3).
    The full layered analysis is registered as code-intel artifacts + Knowledge-Index chunks."""

    repo: str
    indexed_at: str
    file_count: int
    languages: dict          # {".py": 12, ".ts": 5, ...}
    commits: int
    hotspots: int


#: The three outcomes an accessibility judgment can have. `UNCERTAIN` is a first-class
#: result, not an error: a low-confidence judgment routes to human review and must NEVER
#: auto-fail a build (a11y guardrail). Kept as plain strings to match `TestResult.status`.
A11Y_PASS = "pass"
A11Y_FAIL = "fail"
A11Y_UNCERTAIN = "uncertain"
A11Y_VERDICTS = frozenset({A11Y_PASS, A11Y_FAIL, A11Y_UNCERTAIN})

#: checker -> the WCAG 2.2 criteria it judges. The first entry is the criterion a judgment
#: is reported against; `check_semantics` legitimately spans two, which is why this is a
#: tuple per checker rather than a single string.
A11Y_CHECKER_CRITERIA: dict[str, tuple[str, ...]] = {
    "alt": ("1.1.1",),                  # Non-text Content — is the alt text meaningful?
    "semantics": ("1.3.1", "4.1.2"),    # Info and Relationships / Name, Role, Value
    "color": ("1.4.1",),                # Use of Color — is meaning carried by colour alone?
    "label": ("2.5.3",),                # Label in Name — does the visible label match the AN?
}


@dataclass(frozen=True)
class A11yCandidate:
    """One thing to be judged for accessibility: an element as rendered on a screen.

    Pointer-not-body (#1/#3): `screenshot_ref` is an object-store key, never image bytes.
    `html` is the element's own markup (not the page's) and `context` is the surrounding
    text/markup a human would need to answer the same question — an alt text can only be
    judged "meaningful" relative to what the image is doing on the page.
    """

    selector: str = ""          # CSS selector locating the element in the rendered page
    html: str = ""              # the element's outerHTML
    screenshot_ref: str = ""    # object-store key of the element/page image (pointer only)
    context: str = ""           # surrounding text/markup the judge needs
    route: str = ""             # the screen/route the element belongs to

    @property
    def has_input(self) -> bool:
        """Whether there is anything at all to judge. Neither markup nor an image means the
        checker must return `uncertain` with a reason, never a partial or invented result."""
        return bool(self.html.strip() or self.screenshot_ref.strip())


@dataclass(frozen=True)
class A11yJudgment:
    """The single result shape every `A11yAI` check returns — pass/fail/uncertain, with the
    evidence it was based on and a fix to offer.

    Named "judgment", not "finding": a judgment is what the capability *returns*; the
    reviewable, deduplicated row that gets stored is the `A11yFinding` ledger (QA-12a).
    Deliberately validated on construction, so a malformed judgment can never reach a
    reviewer — an AI check that cannot answer must say `uncertain`, not emit a half object.

    **`criteria` is a list, by team decision (2026-08-12).** One broken thing can breach more
    than one WCAG requirement at once: a `div` dressed up as a button breaks both 1.3.1 (the
    structure doesn't say a control is there) and 4.1.2 (assistive tech can't tell what it is
    or what it's called), and ONE fix repairs both. Recording it once against a single
    criterion would leave the conformance report claiming the other criterion is clean when
    we found a breach of it; recording it twice would show a reviewer the same broken button
    twice and give a developer two tickets for one fix. So: one judgment, tagged with every
    criterion it breaches, counted against each in the report. The checker reports which ones
    actually apply — never all of them by default, because a *real* button with no readable
    name breaches only 4.1.2, and a heading that is merely bold text only 1.3.1.
    """

    criteria: tuple[str, ...]   # every WCAG 2.2 criterion this judgment applies to
    verdict: str                # A11Y_PASS | A11Y_FAIL | A11Y_UNCERTAIN
    confidence: float           # 0.0 - 1.0
    evidence: str               # what the judgment was based on (quoted markup / what was seen)
    suggested_fix: str          # what to change; "" is legitimate for a pass
    checker: str = ""           # which check produced it: alt | semantics | color | label

    def __post_init__(self) -> None:
        # Accept any sequence but store a tuple, so a caller passing a list can't produce an
        # unhashable, unequal-to-itself judgment further downstream.
        object.__setattr__(self, "criteria", tuple(self.criteria))
        if self.verdict not in A11Y_VERDICTS:
            raise ValueError(
                f"invalid a11y verdict {self.verdict!r} — expected one of {sorted(A11Y_VERDICTS)}"
            )
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"a11y confidence must be between 0 and 1, got {self.confidence!r}")
        if not self.criteria or not all(self.criteria):
            raise ValueError("an a11y judgment must name the WCAG criteria it judged")
        owned = A11Y_CHECKER_CRITERIA.get(self.checker)
        if owned is not None and not set(self.criteria) <= set(owned):
            # A checker reporting against a criterion it does not own would silently corrupt
            # the conformance report — the one artifact a client or auditor actually reads.
            stray = sorted(set(self.criteria) - set(owned))
            raise ValueError(
                f"checker {self.checker!r} reported against {stray}, which it does not "
                f"judge (it owns {list(owned)})"
            )

    @property
    def criterion(self) -> str:
        """The primary criterion — what a single-criterion caller (and QA-12a's finding
        fingerprint) uses. `criteria` remains the full truth for the conformance report."""
        return self.criteria[0]


def uncertain(criteria: tuple[str, ...], *, checker: str, reason: str) -> A11yJudgment:
    """The well-formed "I could not answer this" judgment.

    Every path that cannot produce a real verdict — missing inputs, an errored judgment run,
    a low-confidence answer — returns THIS rather than raising or returning a partial object,
    because uncertainty is a routing decision (send it to a human) and not a failure. It is
    tagged with ALL the criteria the checker covers: not knowing the answer leaves every
    question the checker was asked open, not just the first one.
    """
    return A11yJudgment(
        criteria=criteria, verdict=A11Y_UNCERTAIN, confidence=0.0,
        evidence=reason, suggested_fix="", checker=checker,
    )


class CapabilityError(Exception):
    """A connector call failed. Carries the upstream status when there was one."""

    def __init__(self, message: str, *, status: int | None = None, detail: object = None):
        super().__init__(message)
        self.status = status
        self.detail = detail


class CapabilityUnavailable(CapabilityError):
    """No connector is configured for this tenant+capability (callers fall back to internal)."""
