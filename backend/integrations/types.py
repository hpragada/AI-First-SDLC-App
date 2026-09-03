"""Vendor-free value objects + errors shared across connectors."""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field


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
#:
#: **These five are the POC ELEMENT checkers, and widening the map is a decision** (QA-20). They
#: answer a question about one element of a page standing still, `checkers/rules.py` selects
#: candidates for them, and `test_a11y_ownership` pins them to the criteria the registry marks
#: `owner=ai, tier=in_poc`. The journey checks below are a different shape with a different
#: tier, so they get their own map rather than widening this one — merging them would silently
#: break that drift test, which exists precisely so extending AI coverage is a decision.
#:
#: It said "exactly four" until 25 August, and had done since `structure` was added on the 24th
#: to close the 1.3.1 scope gap — a rule about the map, printed directly above the map, saying
#: something the map itself contradicted. The count is the thing that keeps going stale here, so
#: what is written down now is the RULE (a change is a decision somebody takes) rather than a
#: number that has to be remembered a second time. `test_a11y_wcag` holds the number.
A11Y_CHECKER_CRITERIA: dict[str, tuple[str, ...]] = {
    "alt": ("1.1.1",),                  # Non-text Content — is the alt text meaningful?
    "semantics": ("1.3.1", "4.1.2"),    # Info and Relationships / Name, Role, Value
    "structure": ("1.3.1",),            # Info and Relationships — is the visible structure real?
    "color": ("1.4.1",),                # Use of Color — is meaning carried by colour alone?
    "label": ("2.5.3",),                # Label in Name — does the visible label match the AN?
    "graphics": ("1.4.11",),            # Non-text Contrast — can you SEE the meaningful parts?
}

#: **Why `graphics` exists, and why it is the AI that owns 1.4.11.**
#: 1.4.11 is a criterion in two halves. *Can you see where the controls are?* is colours and a
#: threshold, and `apps.a11y.page_rules` decides it deterministically. *Are the meaningful parts
#: of the icons, charts and diagrams visible enough?* requires knowing which parts of a picture
#: carry meaning before any ratio can be computed, and nothing deterministic knows that.
#:
#: Addendum A gave the criterion to `rule`, and said why it should not have in the same cell —
#: *"computable, but 'which graphics matter' needs some review"*. That is how the second half
#: went unbuilt for four tasks while the criterion was reported as covered. **Correction R14
#: (agreed 27 August) settles it: the rationale is right and the owner is not**, and
#: `ownership.ENGINEERING_OVERRIDES` carries that into the routing table — `ai` decides, with
#: `page_rules` recorded as the rule engine's contribution. Both halves ship together or the
#: criterion is not covered; see QA-25.
#:
#: **The correction was agreed on 27 August and the registry was not changed until 1 September**,
#: and the gap between those two dates is the whole lesson. For five days this map said the AI
#: owned 1.4.11 while the registry said `rule`, and five separate guards reported the
#: disagreement every single day: the ownership drift test, the registry-map equality test, the
#: POC element-check list, the capability-surface check, and both halves of the selection corpus.
#: They were read as background red. A decision recorded only in prose is not a decision the
#: platform can act on.
#:
#: **Its scope is deliberately wider than `alt`'s, and the difference is the point.** `alt` asks
#: what assistive technology is told, so it skips a graphic that is never announced. This asks
#: what a person can SEE, so a decorative-to-a-screen-reader icon carrying visible meaning is
#: still in scope. The two checks look at many of the same elements and are asking genuinely
#: different questions about them.

#: Checks that are BUILT and are deliberately not running, with the criterion each one holds.
#:
#: **Empty today, and kept anyway** — for `A11Y_HELD_BACK_CLAIMS` below, which is the part that
#: has to exist before anything is ever put in here again.
#:
#: A check goes in here when it is not wrong but its claim cannot be supported: the rule, the
#: prompt schema and the style keys stay exactly where they are, and only the permission to say
#: it covers a criterion is withdrawn. `checkers.rules.HELD_BACK_SELECTION_RULES` holds the
#: matching selection rule, `describe_rules()` prints it as **HELD BACK, NOT RUNNING**, and
#: `A11Y_ALL_CHECKER_CRITERIA` keeps validating it so a verdict recorded before the pause still
#: reads back.
#:
#: `graphics` sat here for part of 1 September while the registry was brought into line with
#: R14. What that half-day taught is written below, and it is why this is a mechanism rather
#: than a commented-out line.
A11Y_HELD_BACK_CRITERIA: dict[str, tuple[str, ...]] = {}

#: The criteria a held-back check was answering part of — and NO conformance claim may be made
#: about any of them while it is held.
#:
#: **This is here because holding a check back nearly recreated the bug that built it.** On
#: 1 September `graphics` was held for a few hours, and one test refused to go green: 1.4.11's
#: measurable half is recorded under the `rule` engine, so with the judge paused the conformance
#: guard would have found an entitled engine had looked and answered **Supports 1.4.11** — for a
#: page whose buttons all had visible edges and whose icons nothing had judged. That is QA-25
#: word for word: a narrow pass claiming a criterion it cannot prove.
#:
#: So a hold **withdraws the claim** rather than handing it to whatever else touches the
#: criterion. Failures are untouched in both directions — a control edge under 3:1 is still a
#: proven Level AA defect and is still reported — because only the POSITIVE direction was ever
#: unsafe here. Guarded whether or not anything is currently held, so the next hold is safe on
#: the day it is made rather than after somebody rediscovers this.
A11Y_HELD_BACK_CLAIMS: frozenset[str] = frozenset(
    criterion for criteria in A11Y_HELD_BACK_CRITERIA.values() for criterion in criteria
)

#: **Why `semantics` and `structure` both carry 1.3.1, and are still two checks.**
#: They ask different questions about it. `semantics` looks at ONE element and asks whether it
#: is pretending to be a control or a heading. `structure` looks at a CONTAINER — a table, a
#: list, a group of fields — and asks whether the arrangement a sighted person can see is
#: written into the markup at all. A table with no header cells is not pretending to be
#: anything, so the first question never reaches it; that gap is why every page of the 21
#: August audit was recorded as satisfying 1.3.1 while nothing had looked at its tables
#: (`SCOPE_GAP_INFO_AND_RELATIONSHIPS.md`).
#:
#: Kept apart rather than merged because the accuracy harness scores **per checker**: folded
#: together, a good score on fake buttons would hide a poor one on tables, which is the exact
#: averaging that let this go unnoticed. Two checkers may own one criterion without conflict —
#: coverage takes the worst outcome reported for it, never the most recent.

#: checker -> criteria for the **journey** checks (QA-20, Phase 2). These cannot be answered
#: from a captured page at all: each one is a question about what happens *while you operate
#: the application*, so the only way to answer it is to drive the app and watch.
#:
#: **One checker per criterion, deliberately.** QA-22 promotes or demotes reliability *per
#: checker*, and its stated edge case is that a proven keyboard-trap check may gate while a
#: newer check stays advisory. Grouping all eight under one `journey` checker would make that
#: impossible — one weak check would hold back seven good ones, or worse, ride in on them.
#:
#: The eight are not invented here: `apps/a11y/data/ownership.json` classifies every one as
#: `tier=phase_2`, and five of them carry the rationale "(agentic Phase 2)" in the registry's
#: own words. `test_a11y_journey` pins this map to that registry so the two cannot drift.
A11Y_JOURNEY_CRITERIA: dict[str, tuple[str, ...]] = {
    "keyboard": ("2.1.1",),         # Keyboard — can everything be reached and operated?
    "trap": ("2.1.2",),             # No Keyboard Trap — can you always get back out?
    "focus_order": ("2.4.3",),      # Focus Order — does tab order preserve meaning?
    "focus_visible": ("2.4.7",),    # Focus Visible — is the focus indicator actually drawn?
    "focus_obscured": ("2.4.11",),  # Focus Not Obscured — is focus hidden behind sticky UI?
    "on_focus": ("3.2.1",),         # On Focus — no unexpected context change on focus
    "on_input": ("3.2.2",),         # On Input — no surprise change on input
    "status": ("4.1.3",),           # Status Messages — is a status announced to assistive tech?
}

#: Every checker the platform has, of any shape. This is what *validates* a judgment; the
#: maps above are what each half of the system iterates. Kept as a derived view so a new
#: checker can never be added to one without being validated by the other.
#:
#: **Held-back checks are in here, and that is not a loophole.** Nothing selects or
#: dispatches from this map -- selection reads `checkers.rules.CHECKERS`, which a held-back
#: check is not in. What this map does is answer *is this a real checker?*, and the answer
#: for a check that is built but paused is yes. Leaving it out would mean a verdict recorded
#: before the pause could no longer be validated at all (the check is skipped when the
#: checker is unknown), and a workspace that had tuned its confidence threshold would be
#: told the check `does not exist` -- the same error QA-20 fixed for the journey checks.
A11Y_ALL_CHECKER_CRITERIA: dict[str, tuple[str, ...]] = {
    **A11Y_CHECKER_CRITERIA,
    **A11Y_JOURNEY_CRITERIA,
    **A11Y_HELD_BACK_CRITERIA,
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
    #: True when `html` is only the beginning of the element's markup, because there was more
    #: than the capture sends. Still carried now that `structure` exists, because it is the
    #: backstop rather than the answer: an outline describes a container's shape, and a judge
    #: reading detail out of the markup itself still has to know when that markup stops.
    markup_truncated: bool = False
    #: The container's shape when it is a container, computed in the browser: rows, columns,
    #: which cells are headers and with what scope, whether a group of fields is grouped and
    #: what names it. Empty for anything that is not a container.
    #:
    #: **Bounded by width, not by length**, which is the property that matters: a table's
    #: markup grows with every row and gets cut off; its outline does not. It is also the
    #: better input rather than merely the smaller one — recovering a grid from a wall of tags
    #: is something code does perfectly and a language model does unreliably, so the parsing
    #: happens once, in the browser, and the judge spends itself on the part that needs
    #: judgment.
    structure: Mapping = field(default_factory=dict)
    screenshot_ref: str = ""    # object-store key of the element/page image (pointer only)
    context: str = ""           # surrounding text/markup the judge needs
    route: str = ""             # the screen/route the element belongs to
    #: The name assistive technology announces for this element, as the BROWSER computed it
    #: from the accessibility tree — never approximated from `aria-label` or the text content,
    #: which would make the name and the visible label agree by construction.
    #:
    #: **It was captured, stored, and never sent, from the first day to 1 September.** WCAG
    #: 2.5.3 asks one question — does the announced name contain the visible label — and the
    #: judge was handed the markup, the picture and the surrounding text, and not the name. For
    #: a `<button>` that is survivable, because a button's name is the word printed on it and
    #: the markup carries that word. For a `<select>` it is not: the name comes from a
    #: `<label for=…>` that is a SIBLING, so it is never inside the element's own `html` and
    #: cannot be recovered from anything else that travels. Every `<select>` in the 31 August
    #: Meridian audit — 13 of 13 — came back "cannot determine the accessible name", against a
    #: 1.4% uncertainty rate everywhere else.
    accessible_name: str = ""
    #: What the element sits inside: {tag, role, href, text}. `context` is the parent's WORDS,
    #: and an icon-only control's parent has none — so for the one element on /events/calendar
    #: queued under both 1.1.1 and 1.4.11, the judge was asked what the icon is inside and told
    #: nothing at all. Both criteria hinge on it: a link whose only content is this icon, or an
    #: already-labelled container.
    parent: Mapping = field(default_factory=dict)

    @property
    def has_input(self) -> bool:
        """Whether there is anything at all to judge. Neither markup nor an image means the
        checker must return `uncertain` with a reason, never a partial or invented result."""
        return bool(self.html.strip() or self.screenshot_ref.strip())


#: What became of one step of a journey (QA-20). Deliberately NOT verdicts: a step is not
#: something that passes or fails accessibility — it is the ground a check gets to stand on.
#:
#: `BLOCKED` and `NOT_REACHED` are the sixth silence, and they are two different silences.
#: `BLOCKED` is the agent saying "I got here and could not go on, and here is why".
#: `NOT_REACHED` is the platform's own reconciliation answering for a step the agent never
#: mentioned at all — the same shape as QA-17's `NEVER_REPORTED` routes, and for the same
#: reason: a step that reports nothing is indistinguishable from a clean one unless the
#: platform froze the list beforehand and subtracted.
A11Y_STEP_WALKED = "walked"
A11Y_STEP_BLOCKED = "blocked"
A11Y_STEP_NOT_REACHED = "not_reached"
A11Y_STEP_OUTCOMES = frozenset({A11Y_STEP_WALKED, A11Y_STEP_BLOCKED, A11Y_STEP_NOT_REACHED})


@dataclass(frozen=True)
class A11yJourneyStep:
    """One step of a critical journey, exactly as the test case wrote it (QA-20).

    `text` is the step's own instruction ("Enter a valid email and submit"), not a rewrite of
    it: the agent walks what QA wrote, and a paraphrase here would quietly change what was
    tested. `route` is filled only when the step names one — most do not, and guessing would
    be worse than leaving it empty.
    """

    number: int
    text: str
    route: str = ""


@dataclass(frozen=True)
class A11yJourney:
    """A critical path through the application, to be operated with a keyboard (QA-20).

    Pointer-not-body (#1/#3): `artifact_id` locates the test case whose text this came from;
    the body itself lives in the object store and is read through, never copied here.

    The journey is a **test case the platform already wrote and a human already reviewed**
    (team decision D1). It is not a second definition of "critical path" maintained beside the
    first — which is exactly what a design-document journey or a bare route list would have
    become, and why both were rejected.
    """

    test_ref: str                                   # "TC-031"
    title: str
    steps: tuple[A11yJourneyStep, ...] = ()
    preconditions: tuple[str, ...] = ()
    work_item_id: str = ""
    artifact_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "steps", tuple(self.steps))
        object.__setattr__(self, "preconditions", tuple(self.preconditions))

    @property
    def is_walkable(self) -> bool:
        """Whether there is a journey here at all. A test case with no parsable steps cannot
        be walked, and the honest answer is to say so rather than dispatch an agent to operate
        nothing and report a clean run."""
        return bool(self.steps)


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
        # The union, so a journey checker (QA-20) is held to the same rule as an element one:
        # a check reporting against a criterion it does not own corrupts the conformance
        # report either way, and the report cannot tell which half of the system produced it.
        owned = A11Y_ALL_CHECKER_CRITERIA.get(self.checker)
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


@dataclass(frozen=True)
class A11yRuleFailure:
    """One accessibility failure a **deterministic rule scanner proved** (QA-06).

    Deliberately **not** named after axe (#9). axe-core is what runs today, but the platform
    must never bake a vendor into a type any more than it calls `jira.*` directly — a
    different scanner, or a second one alongside it, must not need this renamed.

    This is the other half of the safety valve. A rule scanner *measures*: it computed the
    contrast ratio, it read the `lang` attribute. An AI *judges*. Where the two disagree the
    measurement wins, and this is what a judgment is compared against to know that.

    **The identity is `(route, selector, criterion)`** — the same key QA-12a's finding
    fingerprint uses, minus the checker, so "the same problem" means the same thing in both
    places by construction rather than by coincidence. A scanner failure on one element does
    not silence an AI judgment about a different element, a different screen, or a different
    criterion.

    Populated for real in QA-11b, which is when structured scanner output first reaches the
    platform; QA-06 builds and unit-tests the rule that consumes it.
    """

    criterion: str              # the WCAG criterion the scanner proved a failure of
    selector: str = ""          # CSS selector of the failing element, as the scanner saw it
    route: str = ""             # the screen/route it was found on
    rule_id: str = ""           # the scanner's own rule id, so the report can cite it
    evidence: str = ""          # what the scanner reported
    # The scanner's OWN severity word ("critical"/"serious"/…), carried verbatim and never
    # conflated with the platform's severity (QA-12a). They measure different things: ours comes
    # from the WCAG conformance level the criterion sits at, and decides whether a defect opens;
    # this one is the scanner's judgement of impact, and is shown so a reader can see both.
    impact: str = ""

    def __post_init__(self) -> None:
        if not self.criterion:
            raise ValueError("a rule failure must name the WCAG criterion it failed")

    @property
    def key(self) -> tuple[str, str, str]:
        """What makes this the *same* thing as an AI judgment about the same element."""
        return (self.route, self.selector, self.criterion)


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
