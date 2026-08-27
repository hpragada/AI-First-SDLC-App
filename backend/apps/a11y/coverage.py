"""What was actually looked at, per criterion, per page (QA-24).

The findings ledger records what is **wrong**. Until this module, that was all the platform
recorded — every engine threw its positive result away, in three separate places:

  * the scanner returned `violations` and dropped axe's `passes`, `inapplicable` and
    `incomplete` (`runner/companion/assets/a11y_audit.mjs`);
  * the ledger's `RECORDED_OUTCOMES` dropped every AI verdict of "this is fine"
    (`findings.record_run_findings`);
  * the journey path returned early on anything that was not a failure or a review
    (`journey.record_journey_finding`).

So a criterion with nothing against it could equally be one that was checked and found clean,
one nothing has a check for, or one where nothing on the page was applicable. Three different
facts and one silence — and a conformance statement is made almost entirely of the positive
ones. This is where all three engines now write what they saw.

**Nothing here decides what a criterion's conformance level is.** That is `conformance.py`, and
it is a separate step on purpose: this module records observations, that one turns observations
into a claim a person signs.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

#: Which observation wins when one criterion is observed more than once on one page by one
#: engine — and it happens constantly, because several axe rules map to the same criterion.
#:
#: **Worst wins, and the order is not a matter of taste.** A page where `image-alt` passed and
#: `input-image-alt` failed has a 1.1.1 failure; reporting the pass because it arrived second
#: would be the report claiming conformance it was told it did not have. `needs_human` outranks
#: `passed` for the same reason: an unanswered question is not a clean result. `not_applicable`
#: ranks last because it is the weakest thing that can be said — the rule ran and found nothing
#: to judge.
#:
#: **`not_checked` sits between a failure and a person's question, and the position is the
#: point** (24 Aug). It means the platform selected an element and never asked about it — a
#: pass that stopped at its cap, or a judge run that ended without reporting. Ranking it above
#: `passed` is what stops a page we broke off halfway through being written down as clean:
#: before this, an audit that reached eight of seventeen pages recorded the other nine as
#: satisfying 1.3.1, because those pages picked up passing verdicts from shared markup — the
#: same footer, judged elsewhere — while the elements that were actually theirs said nothing.
#:
#: Ranking it above `needs_human` too is a choice about **what the reader is asked to do**. A
#: `needs_human` is settled work waiting for a person. A `not_checked` is our own unfinished
#: work, it is cheap to finish, and finishing it may well answer the question outright. So the
#: page says "not checked yet" until the checking is done, and only then does it hand anybody a
#: judgement to make. Handing a person an element nobody looked at, labelled as though a check
#: had considered it and hesitated, is the one wording this table must not produce.
_RANK = {"failed": 0, "not_checked": 1, "needs_human": 2, "passed": 3, "not_applicable": 4}


def _worse(a: str, b: str) -> str:
    return a if _RANK.get(a, 9) <= _RANK.get(b, 9) else b


def _audited_criteria(version: str = "2.2") -> frozenset[str]:
    """The criterion numbers this platform audits — Level A and AA, from the loaded standard.

    Read rather than listed. A hardcoded set of 55 numbers here would be a second copy of the
    standard, in the layer least likely to be revisited when a version changes.

    **An empty answer disables the filter rather than dropping everything.** A database where the
    standard has not been loaded yet must not silently discard every observation an audit makes;
    a stray AAA row is a tidiness problem, and losing a real one is not.
    """
    from .models import WcagCriterion

    return frozenset(
        WcagCriterion.objects
        .filter(version=version, level__in=["A", "AA"])
        .values_list("number", flat=True)
    )


def record(*, tenant_id, project_id, run_key, route, engine, observations, run_id=None) -> int:
    """Write one engine's observations for one page. Returns how many criterion rows resulted.

    `observations` is an iterable of `(criterion, outcome, detail)`. Rows are collapsed to one
    per criterion by `_worse` **before** touching the database, so the precedence rule lives in
    one place and cannot be half-applied by a caller that happens to write in a different order.

    Idempotent per (run_key, route, criterion, engine): re-posting a capture updates its rows
    rather than stacking duplicates, exactly as the candidate bundles do.
    """
    from .models import A11yCriterionCoverage

    best: dict[str, tuple[str, str]] = {}
    for criterion, outcome, detail in observations:
        key = str(criterion or "").strip()
        if not key or outcome not in _RANK:
            # A rule with no WCAG tag is a real thing axe ships (best-practice rules) and it is
            # not a criterion observation. Dropped here rather than stored against an empty
            # criterion, which would produce a coverage row nothing could ever read.
            continue
        previous = best.get(key)
        if previous is None:
            best[key] = (outcome, str(detail or ""))
        elif _worse(outcome, previous[0]) == outcome and outcome != previous[0]:
            best[key] = (outcome, str(detail or ""))

    if not best:
        return 0
    # Only criteria this audit is actually about (#9). axe tags `scrollable-region-focusable` to
    # **2.1.3**, which is Level AAA and not one of the 55 — so every scanned page was writing a
    # coverage row for a criterion no report reads, no registry owns and nobody could explain.
    #
    # Filtered HERE rather than in `from_scan`, and the layer is the point: what axe said is
    # axe's statement and is kept whole where it is read (`capture`, `scanner_coverage`), while
    # what the audit is *about* is a fact only the platform knows. Narrowing a vendor's statement
    # inside the reader of it is how a difference between two lists stops being visible — which
    # is the same mistake that hid 1.4.10 for four tasks.
    known = _audited_criteria()
    if known:
        best = {number: value for number, value in best.items() if number in known}
        if not best:
            return 0
    with tenant_context(tenant_id):
        for criterion, (outcome, detail) in best.items():
            A11yCriterionCoverage.objects.update_or_create(
                tenant_id=tenant_id, project_id=project_id, run_key=str(run_key or ""),
                route=route[:512], criterion=criterion[:16], engine=engine,
                defaults={"outcome": outcome, "detail": detail[:2_000],
                          "run_id": run_id or None},
            )
    return len(best)


def from_scan(screen: dict) -> list[tuple[str, str, str]]:
    """One parsed capture screen's axe channels as criterion observations.

    Reads all four, which is the whole point. A screen the scanner never ran on produces
    **nothing** — `axe_error` says why, and a page that was not measured must not appear in the
    coverage map as though it had been.
    """
    if str(screen.get("axe_error") or "").strip():
        return []
    out: list[tuple[str, str, str]] = []
    for key, outcome in (("axe_violations", "failed"), ("axe_incomplete", "needs_human"),
                         ("axe_passes", "passed"), ("axe_inapplicable", "not_applicable")):
        for entry in screen.get(key) or []:
            rule = str((entry or {}).get("rule") or "")
            for criterion in (entry or {}).get("criteria") or []:
                out.append((criterion, outcome, rule))
    return out


def observations_for_row(row) -> list[tuple[str, str, str]]:
    """One merged report row as criterion observations — the AI and agentic half.

    A `pass` is the row this whole module exists for: the judge looked at the element and said
    it was fine, and that was thrown away. `needs_review` becomes `needs_human`, which is the
    same fact axe's `incomplete` carries and is reported in the same words.
    """
    from .triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW

    outcome = {TRIAGE_FAILURE: "failed", TRIAGE_REVIEW: "needs_human",
               TRIAGE_PASS: "passed"}.get(row.outcome)
    if outcome is None:
        return []
    detail = row.checker or row.rule_id or ""
    return [(criterion, outcome, detail) for criterion in row.criteria]


def summary(tenant_id, project_id) -> dict[str, dict]:
    """{criterion: {outcome: {engines}, routes: {...}}} for the whole project.

    Project-scoped and route-aware, because "supports" is never a fact about a product — it is a
    fact about the pages that were checked. `conformance.py` turns this into per-criterion rows;
    keeping the shaping there means this stays a straight read of what was observed.
    """
    from .models import A11yCriterionCoverage

    with tenant_context(tenant_id):
        rows = list(
            A11yCriterionCoverage.objects
            .filter(tenant_id=tenant_id, project_id=project_id)
            .values("criterion", "route", "engine", "outcome", "detail")
        )
    out: dict[str, dict] = {}
    for row in rows:
        entry = out.setdefault(row["criterion"], {
            "routes": {}, "engines": set(), "outcomes": set(), "details": set(),
        })
        # Worst per route across engines: a criterion the scanner passed and the AI failed on
        # one page is a failure on that page, whichever engine spoke first.
        current = entry["routes"].get(row["route"])
        entry["routes"][row["route"]] = (
            row["outcome"] if current is None else _worse(row["outcome"], current)
        )
        entry["engines"].add(row["engine"])
        entry["outcomes"].add(row["outcome"])
        if row["detail"]:
            entry["details"].add(row["detail"])
    return out
