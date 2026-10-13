"""What to fix first, and where the list of fixes lives (QA-18).

QA-14 turned accessibility findings into tracked defects that open, close and reopen on their
own. It never said which one to do first — and for a story with three findings that hardly
matters, while for an inherited app with two hundred it is the whole difference between a
backlog and a pile.

**Priority is a query, and also a number on the ticket.** The ordering lives here, computed
from the ledger, exactly as `findings.review_queue` is a query rather than a second table:
being high priority is what "critical, on nine pages" *means*, and storing it as independent
state would let the two disagree the moment a policy changed. But a defect does not stay in
the platform — it reaches a task tracker, where no query of ours can follow it — so the
ordinal is also written onto the defect's own `external_ref`, where it travels with the item.

**The order is severity, then breadth, then the criterion number.**

  * *Severity* first because it is what the project's own policy blocks on (QA-08) — the
    ordering must agree with the gate, or the top of the backlog is not what unblocks a
    release.
  * *Breadth* — how many distinct pages breach the same criterion — second, and this is the
    term that makes it a priority list rather than a sorted-by-severity list. One criterion
    broken on twelve pages is usually one component fixed once; twelve criteria broken on one
    page each are twelve separate pieces of work.
  * *Criterion number* last, purely so two equal items come out in the same order twice. A
    backlog that reshuffles between reads is one nobody can work through.

**What is deliberately NOT in the order: effort.** How long a fix takes is a human's call
about their own codebase, and the platform has no basis for guessing it. A priority list that
silently encodes a guess about effort would be worse than one that admits it only knows
severity and breadth.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

#: Severity → its place in the order. Mirrors `findings.review_queue`'s, deliberately: two
#: different orderings of the same word list is one of them being wrong.
SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}

#: Where a baseline's defects hang. Get-or-created once per PROJECT, never per audit: a
#: finding that is fixed and comes back reuses its own defect (QA-14), and a per-audit
#: container would scatter that one item's history across every pass that ever saw it.
BACKLOG_STREAM = "__a11y_backlog__"
BACKLOG_TITLE = "Accessibility backlog"

#: What this epic IS, for the person who opens it. On an application that was imported rather
#: than built here it is the most important item on their board — every accessibility problem in
#: the application hangs off it — and it used to introduce itself in two sentences.
#:
#: Written here rather than on the screen because it is the work item's own description: it
#: travels to a task tracker with the epic, where no screen of ours can add to it.
BACKLOG_DESCRIPTION = """**Every accessibility problem found in this application, as tracked work.**

Each child is one problem on one element of one page, worst first: what breaks, which WCAG
success criterion it breaches, how sure the platform is, and a suggested fix.

**They close and reopen themselves.** A child closes when a later audit looks at that element
and no longer finds the problem — never because an audit did not visit the page, which would
close problems nobody had fixed. If it comes back it reopens as the same item, keeping its
history rather than arriving as a new ticket.

**What to do with it.** Work down from the top. The order is severity first, then how many pages
share the same breach — one criterion broken on twelve pages is usually one component fixed
once. Nothing here blocks a release on its own; the project's own accessibility policy decides
that, and the Conformance statement is what somebody signs at the end.

Problems the checks could not decide on their own are not here — they are waiting for a person
in the accessibility review queue."""


def open_findings(tenant_id, project_id) -> list:
    """Every accessibility problem this project currently has open, whatever found it.

    Project-scoped, not run-scoped, and that is the point of a baseline: "where do we stand"
    is the state of the whole application, not the slice one pass happened to reach. An audit
    that covered 38 of 50 routes must not produce a standing that quietly drops what is known
    about the other 12.
    """
    from .models import A11yFinding

    with tenant_context(tenant_id):
        return list(
            A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN)
            .order_by("criterion", "route", "selector")
        )


def breadth_by_criterion(findings) -> dict[str, int]:
    """{criterion: how many distinct pages breach it} — the second term of the order.

    Counted over **every open finding**, not only the ones that block. One definition used in
    both places this number appears — the backlog listing and the ticket's own record — because
    a criterion described as affecting nine pages in one view and four in the other is a number
    nobody can act on. A finding awaiting review still says "this page may breach this", which
    is exactly the signal that matters when deciding what to fix first.
    """
    pages: dict[str, set] = {}
    for finding in findings:
        pages.setdefault(finding.criterion, set()).add(finding.route)
    return {criterion: len(routes) for criterion, routes in pages.items()}


def _sort_key(finding, breadth: dict[str, int]):
    """Severity, then breadth (widest first), then the criterion, then the element.

    Breadth is negated rather than reverse-sorted so the whole key stays a single ascending
    sort — mixing directions across a tuple is where this kind of ordering usually goes quietly
    wrong.
    """
    return (
        SEVERITY_ORDER.get((finding.severity or "").strip().lower(), 9),
        -breadth.get(finding.criterion, 0),
        finding.criterion,
        finding.route,
        finding.selector,
    )


def in_fix_order(findings, breadth: dict[str, int]) -> list:
    """These findings, worst first. **The one ordering** — everything else calls this."""
    return sorted(findings, key=lambda f: _sort_key(f, breadth))


def ranks(findings, breadth: dict[str, int]) -> dict[str, dict]:
    """{fingerprint: {priority, pages_affected}} for the given findings, in fix order.

    Takes the findings rather than fetching them, so `defects.record_a11y_findings` can rank
    exactly the set it is about to open tickets for — using its own policy filter, which is the
    only place that decision is made — instead of a second filter here that could drift from it.
    """
    return {
        finding.fingerprint: {"priority": index + 1,
                              "pages_affected": breadth.get(finding.criterion, 0)}
        for index, finding in enumerate(in_fix_order(findings, breadth))
    }


def prioritised(tenant_id, project_id, *, blocking_only: bool = False) -> list[dict]:
    """The project's accessibility backlog, worst first, each item carrying its position.

    `blocking_only` narrows it to what the project's own policy would stop a release for —
    which is exactly the set QA-14 opens defects from, so the backlog a person reads and the
    tickets in their tracker are the same list in the same order.

    **The advisory checks are excluded from it (QA-22).** They are still in the backlog — they
    are real problems and belong in the fix order — but they cannot stop a release, so a list
    whose whole promise is "this is what would stop you" must not name them. Filtered here as
    well as at the gate deliberately: the promise in the paragraph above is that these two
    agree, and a list that quietly disagreed with the gate would be worse than no list.
    """
    from .policy import blocks, is_advisory, policy_or_default

    findings = open_findings(tenant_id, project_id)
    breadth = breadth_by_criterion(findings)
    if blocking_only:
        policy, _ = policy_or_default(tenant_id, project_id)
        findings = [
            finding for finding in findings
            if finding.outcome == "failure"
            and not is_advisory(finding.checker)
            and blocks(policy, severity=finding.severity, confidence=finding.confidence,
                       source=finding.source)
        ]
    return [
        {
            "priority": index + 1,
            "finding": finding,
            "fingerprint": finding.fingerprint,
            "criterion": finding.criterion,
            "wcag_level": finding.wcag_level,
            "severity": finding.severity,
            "route": finding.route,
            "selector": finding.selector,
            "outcome": finding.outcome,
            "source": finding.source,
            "pages_affected": breadth.get(finding.criterion, 0),
            "evidence": finding.evidence,
            "suggested_fix": finding.suggested_fix,
        }
        for index, finding in enumerate(in_fix_order(findings, breadth))
    ]


def backlog_container(tenant_id, project_id):
    """The work item a baseline's defects hang off (get-or-create; idempotent).

    **Why they need one.** A defect from a build hangs off the story whose run first saw it. A
    baseline audit has no story — it is not building anything — so until now its defects landed
    loose in the project, and OP-08's remediation campaign would have had to rediscover them by
    scanning `external_ref` on every work item there is.

    **Not a carrier, and that is load-bearing.** Carrier work items are hidden from every
    user-facing backlog (`integrations.onboarding.carrier_q`). This is the opposite kind of
    thing: a client is meant to see it, work through it and watch it shrink. It is an `EPIC`
    with an ordinary `external_ref`, so it shows up exactly where a person would look for it.
    """
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        item, _ = WorkItem.objects.get_or_create(
            tenant_id=tenant_id, project_id=project_id,
            feature_stream=BACKLOG_STREAM, type=WorkItem.Type.EPIC,
            defaults={
                "title": BACKLOG_TITLE,
                "description": BACKLOG_DESCRIPTION,
                "state": WorkItem.State.IN_PROGRESS,
                "external_ref": {"kind": "a11y_backlog"},
            },
        )
    return item
