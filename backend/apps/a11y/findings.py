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
applies here in three ways at once. A finding on a screen this run never visited is untouched.
A finding on an element that WAS captured this run but never actually judged is untouched too —
"we did not get an answer" is not "the problem is gone", and treating it as such would close a
real accessibility defect on the strength of a judgment run that fell over. **And since QA-21
(D-A11Y-79), a finding from a check this kind of run cannot make is untouched:** the journey
checks judge what happens while the application is *operated*, which a captured page cannot
answer either way, so their absence from a scan means nothing and closed them all. Coverage is
by screen and by kind.

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
from integrations.types import A11Y_CHECKER_CRITERIA, A11Y_JOURNEY_CRITERIA

from . import coverage
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


def ids_by_fingerprint(tenant_id, project_id) -> dict[str, str]:
    """{fingerprint: finding id} for every open finding on this project.

    What it is for: linking a **merge** row to the ledger row it is. A baseline audit records
    its findings against no `Run` (`record_run_findings` resolves its key to `None` on purpose),
    so `open_findings_for_run` matches nothing for it and the per-run report renders from the
    merge — where the rows have no id, and so nothing to link to.

    Keyed on the fingerprint rather than on route+selector because the fingerprint is what
    "the same problem" means here, and a second, weaker rule for the same question is exactly
    the drift this module warns against everywhere else.
    """
    from .models import A11yFinding

    with tenant_context(tenant_id):
        return {
            row["fingerprint"]: str(row["id"])
            for row in A11yFinding.objects.filter(
                tenant_id=tenant_id, project_id=project_id,
                status=A11yFinding.Status.OPEN,
            ).values("fingerprint", "id")
        }


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
        "content_hash": row.content_hash,
    }


#: The columns a human decision OWNS. When a reviewer's ruling still applies, a fresh run may
#: refresh everything about a finding except these — they are the ruling.
#:
#: `status` is in the list and that is the point of including it: a rejected finding is closed,
#: and without this the next run's blanket `status=OPEN` would quietly reopen something a person
#: had already dealt with.
HUMAN_OWNED_FIELDS = ("outcome", "verdict", "confidence", "source", "status")


def _ruling_still_applies(existing, incoming_hash: str) -> bool:
    """Does the reviewer's answer still describe the element in front of us? (QA-23, B1.)

    True only when a person actually ruled AND the judge's inputs are byte-identical to what
    they ruled on. Both halves are load-bearing:

    * no ruling → nothing to protect, the run writes what it found;
    * a ruling on *different* markup → the answer is about an element that no longer exists,
      and letting a stale "this is fine" sit over edited code is the failure this whole build
      is against. It goes back to the queue instead.

    An empty hash on either side is treated as "cannot prove they match", so it does NOT hold
    the ruling. That is the conservative direction: re-asking a person is a cost, while keeping
    a verdict we cannot justify is a lie.
    """
    from .models import A11yFinding

    if existing.adjudication == A11yFinding.Adjudication.PENDING:
        return False
    return bool(incoming_hash) and incoming_hash == existing.adjudicated_content_hash


#: What a page gets recorded as when an AI check ran over it and had nothing to ask about.
#: Deliberately the same outcome axe reports as `inapplicable` — the rule ran, and found
#: nothing in its scope — because that is exactly what happened and the two halves of this
#: report must mean the same thing by the same words.
NOTHING_IN_SCOPE = "no element on this page was in scope for this check"

#: What a page gets recorded as for an element that was selected and never asked about. The
#: wording is the whole distinction: it says nobody looked, not that somebody looked and could
#: not decide.
NOT_YET_CHECKED = "selected for this check; the pass has not asked about it yet"

#: Every criterion the AI checks own, flattened. Read once here rather than per route.
AI_OWNED_CRITERIA: frozenset[str] = frozenset(
    criterion for criteria in A11Y_CHECKER_CRITERIA.values() for criterion in criteria
)


def _record_unchecked(report, by_route: dict[str, list]) -> None:
    """Every element selected for a check that never ran, as coverage on its own page.

    **The hole this closes.** Coverage was written from the merged report's rows, and an element
    nothing answered produces no row — so a page the platform stopped short of was described
    entirely by the elements it *had* reached. That was survivable while every page got some
    attention. It stopped being survivable the moment a pass ran out of budget part way down the
    route list: the pages it never opened still collected passing verdicts, because a site's
    header and footer are the same markup everywhere and one verdict is written back against
    every page that markup appears on. Nine pages of a seventeen-page audit were recorded as
    satisfying 1.3.1 with not one of their own elements ever sent to the judge — one of them
    holding a table whose column headings are ordinary cells, which is exactly what 1.3.1 is.

    Eight borrowed passes and no failures is indistinguishable from a clean page. This is what
    makes it distinguishable.

    `report.unjudged` already holds precisely the right set and has since it was written —
    `merge_run` walks every request the capture holds and files the ones with no verdict, so a
    request deferred at the cap, a run that ended early and a judge that never started all
    arrive here the same way. Each one is recorded against the criteria ITS OWN check covers,
    on ITS OWN page, so an unasked colour question never clouds a structural one.

    `coverage.record` collapses these with everything else the page said, worst-first, so a
    genuine failure still wins and a page with nothing outstanding is untouched.
    """
    for item in report.unjudged:
        route = str(item.get("route") or "")
        if not route:
            # A missing route cannot be attributed to a page, and attributing it to the empty
            # one would invent a screen. The element is still in `unjudged` and still keeps its
            # finding from being resolved by silence; only the coverage line is skipped.
            continue
        for criterion in A11Y_CHECKER_CRITERIA.get(str(item.get("checker") or ""), ()):
            by_route.setdefault(route, []).append((criterion, "not_checked", NOT_YET_CHECKED))


def _fill_in_scope_gaps(report, by_route: dict[str, list]) -> None:
    """Record "checked, nothing in scope" for AI criteria a page raised no question about.

    **The gap this closes, in one line:** a conformance statement said *"Does not support — failed
    on 1 of 1 pages checked"* about an eleven-page audit.

    An AI check writes coverage from the elements it *judged*, so a page where the check selected
    nothing wrote nothing. For three of the five AI-owned criteria that is invisible, because the
    rule scanner also covers them and reports its own `inapplicable` for every page. **2.5.3 is
    the only criterion in the registry that is AI-owned with no scanner counterpart**, so it is
    the only one where the silence reaches the document — and Label in Name is *satisfied* on a
    page whose controls all announce their visible text, which is the strongest positive result
    there is. Recording nothing for it turned eleven examined pages into one.

    The dangerous direction is the inverse of what Meridian showed us: an application with **no**
    Label-in-Name problems produced no coverage at all and read as **not evaluated** — a criterion
    checked on every page, printed as one nobody looked at, in the document a client signs.

    **Two guards, and both are the point:**

    * **`report.routes` only, which is the pages that OPENED** (`scanner.rule_findings_for` keeps
      an unreachable route out of it deliberately). A page the browser never reached must never
      appear here as one a check ran over.
    * **A page with anything unjudged is skipped entirely.** If a pass stopped at its limit part
      way through a page, the elements it never reached might have raised exactly the question
      being filled in here. "We do not know" is the true answer and silence is how this codebase
      says it.

    Existing observations always win: `coverage.record` ranks `not_applicable` last, and nothing
    already answered is overwritten here anyway.
    """
    incomplete = {str(item.get("route") or "") for item in report.unjudged}
    for route in report.routes:
        if route in incomplete:
            continue
        answered = {criterion for criterion, _outcome, _detail in by_route.get(route, ())}
        by_route.setdefault(route, []).extend(
            (criterion, "not_applicable", NOTHING_IN_SCOPE)
            for criterion in sorted(AI_OWNED_CRITERIA - answered)
        )


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
    #
    # **And a third half, added by QA-21: coverage is by screen AND by kind.** A journey check
    # is never in this report, because a captured page cannot answer "does tabbing ever reach
    # this region". Left alone, absence would close every keyboard finding on every screen this
    # run captured — D-A11Y-71 in the opposite direction, and the more dangerous direction,
    # because a static run happens far more often than a journey does. The journey checkers are
    # excluded from the resolution below; only a journey pass that actually walked the route
    # may close one (`journey._resolve_walked`).
    # ...and this is the other half: an element captured this run but never judged. We have no
    # answer for it, and "no answer" must never resolve a finding.
    unanswered = {(item["route"], normalise(item["selector"])) for item in report.unjudged}

    seen: set[str] = set()
    opened, again = [], []
    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first() if run_id else None

        # **Every row, not just the recorded ones** (QA-24). `RECORDED_OUTCOMES` deliberately
        # keeps passes out of the findings ledger — a pass is not a problem and has no
        # fingerprint, no defect and no reviewer. But it IS evidence, and dropping it here was
        # what made "checked and clean" indistinguishable from "nobody looked" for every
        # criterion the AI owns.
        #
        # Written with the RESOLVED run, not the raw id. `run_id` here is a capture *key* and
        # may name no run at all — a baseline audit partitions by its own id rather than
        # manufacturing a `Run` nobody executed (QA-17) — so passing it to a foreign key is how
        # a real audit dies on an integrity error. The key still travels, as `run_key`.
        by_route: dict[str, list] = {}
        for row in report.rows:
            by_route.setdefault(row.route, []).extend(coverage.observations_for_row(row))
        # Before the gap-filling below, and it matters which order: that step declines to touch
        # a page with anything unjudged, so it must not be the only thing that knows. This one
        # says what the unjudged elements mean for the criteria they belong to.
        _record_unchecked(report, by_route)
        _fill_in_scope_gaps(report, by_route)
        for route, observations in by_route.items():
            coverage.record(
                tenant_id=tenant_id, project_id=project_id, run_key=str(run_id or ""),
                run_id=run.id if run is not None else None,
                route=route, engine="AI", observations=observations,
            )
        for row in recorded:
            criterion = row.criteria[0] if row.criteria else ""
            key = fingerprint(route=row.route, selector=row.selector,
                              criterion=criterion, checker=row.checker)
            seen.add(key)
            fields = _row_fields(row, levels.get(criterion, ""))
            defaults = {
                **fields,
                "last_seen_run": run,
                # Reopened rather than replaced: a problem that went away and came back is
                # the SAME problem, and QA-14 depends on that being one defect.
                "status": A11yFinding.Status.OPEN,
            }
            # A reviewer's decision is not just another opinion to be overwritten by the next
            # run (QA-23). Read the row BEFORE writing it, because `update_or_create` decides
            # everything in one statement and this needs to know what was already there.
            existing = A11yFinding.objects.filter(
                tenant_id=tenant_id, project_id=project_id, fingerprint=key,
            ).first()
            if existing is not None:
                if _ruling_still_applies(existing, fields["content_hash"]):
                    for field in HUMAN_OWNED_FIELDS:
                        defaults.pop(field, None)
                elif existing.adjudication != A11yFinding.Adjudication.PENDING:
                    # The element changed under a decision that was made about the old one. The
                    # decision does not transfer, and pretending it does would be the worst of
                    # both worlds — so it is cleared, by name, and the item returns to the queue.
                    defaults |= {
                        "adjudication": A11yFinding.Adjudication.PENDING,
                        "adjudicated_by": None,
                        "adjudication_note": "",
                        "adjudicated_at": None,
                        "adjudicated_content_hash": "",
                    }
            finding, created = A11yFinding.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, fingerprint=key,
                defaults=defaults,
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
        ).exclude(fingerprint__in=seen or [""]).exclude(
            checker__in=sorted(A11Y_JOURNEY_CRITERIA)
        ):
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
        # The console shows each finding's source run and the work item it was for (G3). Without
        # this the queue fires two extra queries PER ROW, on a list that is deliberately long.
        found = list(rows.select_related(
            "last_seen_run__work_item", "first_seen_run__work_item"))
    found.sort(key=lambda f: (order.get(f.severity, 9), f.route, f.criterion, f.selector))
    return found[:limit] if limit else found
