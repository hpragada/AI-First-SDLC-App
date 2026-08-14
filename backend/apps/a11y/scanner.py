"""What the rule scanner proved, as platform facts (QA-12).

QA-06 built the safety valve that lets a measurement overrule an opinion, and said plainly at
the time that **nothing in the platform constructed an `A11yRuleFailure`** — the rule was
unit-tested against hand-made objects because structured scanner output did not exist yet. This
module is where it starts existing. Everything here reads what the capture stored and turns it
into the type `triage()` compares AI verdicts against.

**Two sources, and both are needed.**

  * `A11yScreenScan.violations` — the scan of the whole page. Complete, because it does not
    depend on which elements the AI was going to be asked about.
  * `A11yCandidateBundle.axe` — what the scan said about one element the AI *is* being asked
    about. Narrow, but its selector is the same string the candidate carries, which is what
    makes `triage`'s `(route, selector, criterion)` match land.

The element-level entry wins where both describe the same thing, for exactly that reason: the
scan reports axe's own `nodes[].target`, and a selector that is textually different from the
candidate's would not match even when it is the same element on the same page.

**A violation with no WCAG criterion is kept, not dropped.** axe ships best-practice rules with
no `wcag…` tag. They cannot become an `A11yRuleFailure` — that type requires a criterion, and
correctly so, since a conformance report is organised by criterion — but silently discarding
them would make the merged report claim the scan found less than it did. They come back
separately and the report counts them.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from apps.tenancy.context import tenant_context
from integrations.types import A11yRuleFailure

from .selectors import normalise as _norm

#: How the scanner's own severity words read in the report. Kept as a mapping rather than
#: title-cased on the fly so an unexpected value from a future scanner shows up as itself
#: instead of being silently dressed up as one of ours (#9 — the platform is not axe-shaped).
IMPACT_LABELS = {
    "critical": "Critical",
    "serious": "Serious",
    "moderate": "Moderate",
    "minor": "Minor",
}


@dataclass(frozen=True)
class RuleScan:
    """Everything the deterministic scanner said about a run, ready for the merge."""

    #: Every proven failure that names a WCAG criterion, as `triage()` consumes them.
    failures: list[A11yRuleFailure] = field(default_factory=list)
    #: Violations the scanner reported with no WCAG criterion (axe best-practice rules):
    #: [{route, rule, impact, help, elements}]. Reported, never merged.
    without_criterion: list[dict] = field(default_factory=list)
    #: The routes a scan was stored for — which is not the same as the routes that had
    #: candidates, and a screen scanned but never judged has to be visible as exactly that.
    routes: list[str] = field(default_factory=list)


def _evidence(rule: str, impact: str, help_text: str, selector: str) -> str:
    """One sentence a developer can act on, in the scanner's own words."""
    label = IMPACT_LABELS.get(impact, impact or "reported")
    parts = [f"The rule scanner reported `{rule or 'unnamed rule'}` ({label})"]
    if selector:
        parts.append(f"on `{selector}`")
    line = " ".join(parts) + "."
    return f"{line} {help_text}".strip() if help_text else line


def rule_findings_for(tenant_id, project_id, run_id=None) -> RuleScan:
    """Everything the scanner proved for one run, from what the capture stored.

    Never raises on odd data: a scan is machine output that reached us through an agent, and a
    malformed violation must cost that violation rather than the whole merged report.
    """
    from .models import A11yCandidateBundle, A11yScreenScan

    run_key = str(run_id or "")
    with tenant_context(tenant_id):
        scans = list(
            A11yScreenScan.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_key=run_key)
            .order_by("route")
        )
        bundles = list(
            A11yCandidateBundle.objects
            .filter(tenant_id=tenant_id, project_id=project_id, run_key=run_key)
            .exclude(axe={})
            .order_by("route", "position", "selector")
        )

    failures: dict[tuple, A11yRuleFailure] = {}
    without: list[dict] = []

    # Element-level FIRST, so its selector is the one that survives a collision — see the
    # module docstring: the candidate's own spelling is the one `triage` has to match.
    for row in bundles:
        axe = row.axe if isinstance(row.axe, dict) else {}
        rule = str(axe.get("rule") or axe.get("id") or "")
        impact = str(axe.get("impact") or "").lower()
        for criterion in [str(c).strip() for c in (axe.get("criteria") or []) if str(c).strip()]:
            failure = A11yRuleFailure(
                criterion=criterion, selector=_norm(row.selector), route=row.route,
                rule_id=rule, impact=impact,
                evidence=_evidence(rule, impact, str(axe.get("help") or ""), row.selector),
            )
            failures.setdefault(failure.key, failure)

    for scan in scans:
        for raw in scan.violations or []:
            if not isinstance(raw, dict):
                continue
            rule = str(raw.get("rule") or "")
            impact = str(raw.get("impact") or "").lower()
            help_text = str(raw.get("help") or "")
            nodes = [_norm(n) for n in (raw.get("nodes") or []) if _norm(n)]
            criteria = [str(c).strip() for c in (raw.get("criteria") or []) if str(c).strip()]
            if not criteria:
                without.append({
                    "route": scan.route, "rule": rule, "impact": impact,
                    "help": help_text, "elements": nodes,
                })
                continue
            # A violation the scanner reported without naming an element still happened — it
            # becomes a failure against the route itself rather than being dropped for having
            # no selector. `triage` will not match it to any element's judgment, which is
            # correct: nothing was judged there.
            for criterion in criteria:
                for selector in nodes or [""]:
                    failure = A11yRuleFailure(
                        criterion=criterion, selector=selector, route=scan.route,
                        rule_id=rule, impact=impact,
                        evidence=_evidence(rule, impact, help_text, selector),
                    )
                    failures.setdefault(failure.key, failure)

    return RuleScan(
        failures=list(failures.values()),
        without_criterion=without,
        routes=[scan.route for scan in scans],
    )
