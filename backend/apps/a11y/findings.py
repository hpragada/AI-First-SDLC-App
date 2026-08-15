"""Giving an accessibility finding an identity, and keeping it (QA-12a).

QA-12 produced a merged report that was rebuilt from scratch every time anyone asked for it —
a snapshot, not a record. This module is the record. It takes the same merged view and writes
each finding to the ledger, recognising the ones it has seen before.

**One key, and everything turns on it.** `fingerprint()` hashes *(route + normalised selector +
primary criterion + checker)*. Same fingerprint means same problem: the row is updated and its
`last_seen_run` moves, rather than a second row appearing. That is what later lets a defect
close itself, reopen instead of twinning, and never be raised twice.

**Resolution is by absence — but only where we actually looked.** This is the rule that is easy
to get wrong and expensive to get wrong, and `import_test_results` already learned it: it closes
a defect only for a test *reported passing*, never for a test that simply did not run. The same
applies here in two ways at once. A finding on a screen this run never visited is untouched. And
a finding on an element that WAS captured this run but never actually judged is untouched too —
"we did not get an answer" is not "the problem is gone", and treating it as such would close a
real accessibility defect on the strength of a judgment run that fell over.

**Severity comes from the standard.** `WcagCriterion.level` is loaded from W3C, so Level A is
Critical and Level AA is High without anything restating the mapping in prose. A criterion whose
level we cannot read falls back to High **deliberately**: severity is what decides whether QA-14
opens a defect, and the safe direction for an unknown is to surface it, not to bury it at
Medium. `wcag_level` is stored blank in that case, so a reader can see the level was not known
rather than believing it was AA.
"""
from __future__ import annotations

from hashlib import sha256

from apps.tenancy.context import tenant_context

from .selectors import is_positional, normalise

#: Conformance level → the severity a defect would inherit. The same mapping agent 09 states in
#: prose for the test report; taken from the loaded standard here so there is one source of it.
SEVERITY_BY_LEVEL = {"A": "critical", "AA": "high", "AAA": "medium"}

#: What an unreadable criterion level gets. See the module docstring — this errs toward
#: surfacing, because the alternative errs toward a real breach never opening a defect.
DEFAULT_SEVERITY = "high"

#: The outcomes that are worth a row. A `pass` is not a finding; its absence from a later run
#: is how a fixed problem resolves.
RECORDED_OUTCOMES = ("failure", "needs_review")


def fingerprint(*, route, selector, criterion, checker="") -> str:
    """What makes two sightings the same problem.

    Length-prefixed so moving text from one part to another cannot collide — the same guard
    `dispatch.content_hash` uses, and for the same reason.

    **The primary criterion only, not the whole list.** A judgment can breach several criteria
    at once (D-A11Y-2) and they are all stored on the row, but the *identity* has to be one
    thing: a later run whose judge names 4.1.2 alone, where an earlier one named 1.3.1 and
    4.1.2, is reporting the same broken button and must find the same row.
    """
    parts = (normalise(route), normalise(selector), str(criterion or "").strip(),
             str(checker or "").strip())
    payload = "\x1f".join(f"{len(p)}:{p}" for p in parts)
    return sha256(payload.encode("utf-8")).hexdigest()


def levels_for(criteria) -> dict[str, str]:
    """{criterion number: conformance level} from the loaded standard, for the ones we hold.

    Platform-wide table (QA-04's carve-out), so no tenant filter and none wanted. A criterion
    that is not loaded is simply absent from the result and gets `DEFAULT_SEVERITY`.
    """
    from .models import WcagCriterion
    from .wcag import DEFAULT_VERSION

    numbers = sorted({str(c).strip() for c in (criteria or []) if str(c).strip()})
    if not numbers:
        return {}
    return dict(
        WcagCriterion.objects
        .filter(version=DEFAULT_VERSION, number__in=numbers)
        .values_list("number", "level")
    )


def describe_criteria(criteria) -> dict[str, dict]:
    """{number: {handle, level}} from the loaded standard — for headings a person can read.

    "1.1.1 Non-text Content (Level A)" tells a reviewer what the rule *is*; a bare number tells
    them to go and look it up. Same platform-wide table, same absence rule as `levels_for`.
    """
    from .models import WcagCriterion
    from .wcag import DEFAULT_VERSION

    numbers = sorted({str(c).strip() for c in (criteria or []) if str(c).strip()})
    if not numbers:
        return {}
    return {
        number: {"handle": handle, "level": level}
        for number, handle, level in WcagCriterion.objects
        .filter(version=DEFAULT_VERSION, number__in=numbers)
        .values_list("number", "handle", "level")
    }


def open_findings_for_run(tenant_id, project_id, run_id) -> list:
    """The ledger rows this run left open — what the report renders from (QA-13).

    Read back after recording rather than rendered from the merge, so the document and the rows
    are the same data by construction. `last_seen_run` is the filter because that is exactly
    "what this run found", including a problem first seen three runs ago and still open.
    """
    from .models import A11yFinding

    if not run_id:
        return []
    with tenant_context(tenant_id):
        return list(
            A11yFinding.objects.filter(
                tenant_id=tenant_id, project_id=project_id, last_seen_run_id=run_id,
                status=A11yFinding.Status.OPEN,
            )
        )


def severity_for(level: str) -> str:
    return SEVERITY_BY_LEVEL.get((level or "").strip().upper(), DEFAULT_SEVERITY)


def _row_fields(row, level: str) -> dict:
    """One merged report row as ledger columns."""
    return {
        "route": row.route,
        "selector": row.selector[:512],
        "stable": not is_positional(row.selector, row.route),
        "criterion": row.criteria[0] if row.criteria else "",
        "criteria": list(row.criteria),
        "wcag_level": level,
        "checker": row.checker,
        "source": row.source,
        "verdict": row.verdict,
        "outcome": row.outcome,
        "confidence": row.confidence,
        "severity": severity_for(level),
        "impact": row.impact,
        "evidence": row.evidence,
        "suggested_fix": row.suggested_fix,
        "screenshot_ref": row.screenshot_ref[:512],
        "rule_id": row.rule_id,
        "engine": row.engine,
        "model": row.model,
        "prompt_version": row.prompt_version,
    }


def record_run_findings(*, tenant_id, project_id, run_id, report) -> dict:
    """Write one run's merged findings to the ledger, recognising what it has seen before.

    Returns counts a person can check — opened, seen again, resolved — because "did the ledger
    actually recognise anything?" is otherwise unanswerable, and a fingerprint that silently
    fails to match would look exactly like a busy first run.
    """
    from apps.runs.models import Run

    from .models import A11yFinding

    recorded = [row for row in report.rows if row.outcome in RECORDED_OUTCOMES]
    levels = levels_for([c for row in recorded for c in row.criteria])

    # A run reports on the screens it captured. Everything outside that is untouched — see the
    # module docstring; this is the half of the rule that stops a finding on an unvisited page
    # being declared fixed.
    covered = {row.route for row in report.rows} | set(report.routes)
    # ...and this is the other half: an element captured this run but never judged. We have no
    # answer for it, and "no answer" must never resolve a finding.
    unanswered = {(item["route"], normalise(item["selector"])) for item in report.unjudged}

    seen: set[str] = set()
    opened, again = [], []
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first() if run_id else None
        for row in recorded:
            criterion = row.criteria[0] if row.criteria else ""
            key = fingerprint(route=row.route, selector=row.selector,
                              criterion=criterion, checker=row.checker)
            seen.add(key)
            fields = _row_fields(row, levels.get(criterion, ""))
            finding, created = A11yFinding.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, fingerprint=key,
                defaults={
                    **fields,
                    "last_seen_run": run,
                    # Reopened rather than replaced: a problem that went away and came back is
                    # the SAME problem, and QA-14 depends on that being one defect.
                    "status": A11yFinding.Status.OPEN,
                },
            )
            if created:
                finding.first_seen_run = run
                finding.save(update_fields=["first_seen_run", "updated_at"])
                opened.append(str(finding.id))
            else:
                again.append(str(finding.id))

        resolved = []
        for finding in A11yFinding.objects.filter(
            tenant_id=tenant_id, project_id=project_id, status=A11yFinding.Status.OPEN,
        ).exclude(fingerprint__in=seen or [""]):
            if finding.route not in covered:
                continue
            if (finding.route, normalise(finding.selector)) in unanswered:
                continue
            finding.status = A11yFinding.Status.RESOLVED
            finding.last_seen_run = run
            finding.save(update_fields=["status", "last_seen_run", "updated_at"])
            resolved.append(str(finding.id))

    return {"opened": opened, "seen_again": again, "resolved": resolved,
            "open_total": len(opened) + len(again)}


def review_queue(tenant_id, project_id=None, *, limit=None) -> list:
    """The findings waiting on a person: open, needing review, nobody has decided yet.

    The queue is a *query*, not a second table — being in it is what "needs review and nobody
    has ruled on it" means, so there is no state to keep in step. QA-23 builds the console on
    top of this and owns what happens when a reviewer decides (including two reviewers opening
    one item), which is why nothing here writes `adjudication`.

    Worst first, so a reviewer with ten minutes spends them on the ten minutes that matter.
    """
    from .models import A11yFinding

    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    with tenant_context(tenant_id):
        rows = A11yFinding.objects.filter(
            tenant_id=tenant_id, status=A11yFinding.Status.OPEN,
            outcome="needs_review", adjudication=A11yFinding.Adjudication.PENDING,
        )
        if project_id is not None:
            rows = rows.filter(project_id=project_id)
        found = list(rows)
    found.sort(key=lambda f: (order.get(f.severity, 9), f.route, f.criterion, f.selector))
    return found[:limit] if limit else found
