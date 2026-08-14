"""The merged accessibility report — rules and AI, side by side (QA-12).

This is the join. Until now the two halves of the accessibility check have never met: the rule
scanner runs on the developer's machine and its findings go into the test report, while the AI
judgments sit in a cache that nothing reads. Here they become one document, in which every
finding says where it came from, how sure it is, and which WCAG 2.2 criteria it breaches.

**Everything routed through `triage`.** Not one verdict reaches this report directly from the
judge. A confident failure is a failure; a low-confidence one is *needs review*; a failure with
no evidence is *needs review*; and where the scanner proved a failure on the same element and
criterion, the scanner's verdict stands whatever the AI said. That is QA-06's safety valve, and
this module is its first real caller.

**Silence is reported, never inferred.** Three things could quietly make a report look clean:
an element that was captured but never judged (the run hit its cap, or the judge was
unavailable), a screen that was scanned but had nothing worth judging, and a scanner violation
that names no WCAG criterion. All three are counted and stated at the top (D-A11Y-3), because
an incomplete accessibility check that reads as a clean one is the single worst outcome
available to this feature.

**No ledger yet.** QA-12a gives findings a stable identity and a home; until then this renders
from the judgment cache and the stored capture each time it is asked to. That is why nothing
here tries to decide whether a finding is "the same" as one from a previous run — that question
belongs to the fingerprint QA-12a builds, and answering it here with a second, weaker rule would
be exactly the kind of drift the two-keys note in `A11yJudgmentCache` warns about.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from apps.tenancy.context import tenant_context
from integrations.types import A11yJudgment, A11yRuleFailure

from .triage import (
    TRIAGE_FAILURE,
    TRIAGE_PASS,
    TRIAGE_REVIEW,
    TriagedFinding,
    thresholds_for,
    triage,
)

#: What a row of the report says about where it came from. `rule` and `ai` are the two engines;
#: a row the scanner proved and the AI also judged is `rule` — the measurement is what stands.
SOURCE_RULE = "rule"
SOURCE_AI = "AI"

#: The artifact this renders to. QA-13 enriches this same artifact rather than adding another.
REPORT_TYPE = "a11y_report"
REPORT_FILENAME = "a11y-report.md"

NOT_JUDGED = (
    "This element was captured and selected for checking, but no verdict was recorded for it."
)


@dataclass(frozen=True)
class ReportRow:
    """One line of the merged report, whichever engine produced it."""

    source: str                       # SOURCE_RULE | SOURCE_AI
    outcome: str                      # TRIAGE_FAILURE | TRIAGE_REVIEW | TRIAGE_PASS
    criteria: tuple[str, ...]
    route: str
    selector: str
    evidence: str
    reason: str = ""
    confidence: float | None = None   # None for a rule finding — a measurement is not a guess
    suggested_fix: str = ""
    checker: str = ""
    rule_id: str = ""

    @property
    def blocks(self) -> bool:
        return self.outcome == TRIAGE_FAILURE


@dataclass
class MergedReport:
    """The whole merged view of one run's accessibility check."""

    rows: list[ReportRow] = field(default_factory=list)
    #: Elements selected for checking that no verdict exists for, with why they matter.
    unjudged: list[dict] = field(default_factory=list)
    #: Scanner violations carrying no WCAG criterion (axe best-practice rules).
    without_criterion: list[dict] = field(default_factory=list)
    routes: list[str] = field(default_factory=list)
    judged: int = 0
    from_rules: int = 0

    @property
    def failures(self) -> list[ReportRow]:
        return [row for row in self.rows if row.outcome == TRIAGE_FAILURE]

    @property
    def needs_review(self) -> list[ReportRow]:
        return [row for row in self.rows if row.outcome == TRIAGE_REVIEW]

    @property
    def passes(self) -> list[ReportRow]:
        return [row for row in self.rows if row.outcome == TRIAGE_PASS]

    @property
    def complete(self) -> bool:
        """Whether every element selected for checking actually got an answer."""
        return not self.unjudged


def _row_from_triage(finding: TriagedFinding) -> ReportRow:
    """One triaged judgment as a report row.

    The source is the **scanner** whenever a scanner failure decided the row — including the
    case where the AI agreed. A reader deciding whether to trust a finding needs to know it was
    measured rather than judged, and the AI's agreement does not make it an AI finding.
    """
    failure = finding.rule_failure
    return ReportRow(
        source=SOURCE_RULE if failure is not None else SOURCE_AI,
        outcome=finding.outcome,
        criteria=finding.judgment.criteria,
        route=finding.candidate.route,
        selector=finding.candidate.selector,
        evidence=(failure.evidence if failure is not None else finding.judgment.evidence),
        reason=finding.reason,
        confidence=finding.judgment.confidence,
        suggested_fix=finding.judgment.suggested_fix,
        checker=finding.judgment.checker,
        rule_id=(failure.rule_id if failure is not None else ""),
    )


def _row_from_rule(failure: A11yRuleFailure) -> ReportRow:
    """A scanner failure on something the AI was never asked about.

    Most of the scan lands here — the four AI checks apply to a minority of what axe flags —
    and it is the half that would have been missing if the merge only walked the judgments.
    """
    return ReportRow(
        source=SOURCE_RULE, outcome=TRIAGE_FAILURE, criteria=(failure.criterion,),
        route=failure.route, selector=failure.selector, evidence=failure.evidence,
        reason="The rule scanner proved this failure. No AI check was asked about this element.",
        confidence=None, rule_id=failure.rule_id,
    )


def _judgments_for(tenant_id, project_id, hashes: list[str]) -> dict[str, A11yJudgment]:
    """Every stored verdict for these inputs, by content hash — one query, not one per element."""
    from .models import A11yJudgmentCache

    if not hashes:
        return {}
    with tenant_context(tenant_id):
        rows = list(
            A11yJudgmentCache.objects
            .filter(tenant_id=tenant_id, project_id=project_id, content_hash__in=hashes)
            .order_by("updated_at")
        )
    return {
        row.content_hash: A11yJudgment(
            criteria=tuple(row.criteria), verdict=row.verdict, confidence=row.confidence,
            evidence=row.evidence, suggested_fix=row.suggested_fix, checker=row.checker,
        )
        for row in rows
    }


def merge_run(*, tenant_id, project_id, run_id) -> MergedReport:
    """Everything one run's accessibility check found, from both engines, already triaged."""
    from .ingest import requests_for
    from .scanner import rule_findings_for

    requests = requests_for(tenant_id, project_id, run_id)
    scan = rule_findings_for(tenant_id, project_id, run_id)
    thresholds = thresholds_for(tenant_id)
    judgments = _judgments_for(tenant_id, project_id, [r.content_hash for r in requests])

    report = MergedReport(routes=list(scan.routes),
                          without_criterion=list(scan.without_criterion))
    matched: set = set()
    for request in requests:
        judgment = judgments.get(request.content_hash)
        if judgment is None:
            report.unjudged.append({
                "route": request.candidate.route,
                "selector": request.candidate.selector,
                "checker": request.checker,
                "reason": NOT_JUDGED,
            })
            continue
        report.judged += 1
        finding = triage(judgment, request.candidate,
                         rule_failures=scan.failures, thresholds=thresholds)
        if finding.rule_failure is not None:
            matched.add(finding.rule_failure.key)
        report.rows.append(_row_from_triage(finding))

    for failure in scan.failures:
        if failure.key not in matched:
            report.rows.append(_row_from_rule(failure))
            report.from_rules += 1

    # Failures first, then what a person has to look at, then the passes — the order someone
    # reads a report in. Stable within each group so two renders of one run are identical.
    order = {TRIAGE_FAILURE: 0, TRIAGE_REVIEW: 1, TRIAGE_PASS: 2}
    report.rows.sort(key=lambda r: (order[r.outcome], r.route, r.criteria, r.selector))
    return report


def _cell(text: str, limit: int = 300) -> str:
    """One table cell: no pipes, no newlines, bounded — a markdown table is line-oriented."""
    flat = " ".join(str(text or "").split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _rows_table(rows: list[ReportRow]) -> list[str]:
    lines = [
        "| Source | Criteria | Route | Element | Confidence | What was found | Suggested fix |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in rows:
        confidence = "measured" if row.confidence is None else f"{row.confidence:.0%}"
        lines.append(
            f"| {row.source} | {', '.join(row.criteria)} | {_cell(row.route, 80)} "
            f"| `{_cell(row.selector, 80)}` | {confidence} | {_cell(row.evidence)} "
            f"| {_cell(row.suggested_fix)} |"
        )
    lines.append("")
    return lines


def report_body(report: MergedReport, *, title: str = "") -> str:
    """The merged report as a document a person reads.

    Markdown, because the platform's artifact preview renders it generically by content type —
    an `a11y_report` registered as markdown displays with no frontend work at all.
    """
    lines = [f"# Accessibility report{f' — {title}' if title else ''}", ""]
    lines.append(
        f"{len(report.failures)} failure(s), {len(report.needs_review)} needing human review, "
        f"{len(report.passes)} passed — across {len(report.routes) or 'no'} screen(s)."
    )
    lines.append("")
    lines.append(
        f"{report.judged} element(s) were judged by the AI checks and {report.from_rules} "
        f"further finding(s) came from the rule scanner alone."
    )
    lines.append("")

    # D-A11Y-3: an incomplete check must never be readable as a clean one. This is the first
    # thing after the totals, before anyone reaches the tables.
    if report.unjudged:
        lines.extend([
            "> **This check is incomplete.** "
            f"{len(report.unjudged)} element(s) were selected for an AI check and no verdict "
            "was recorded for them, so nothing here says whether they are accessible. They are "
            "listed at the end and need a person to look at them.",
            "",
        ])

    if report.failures:
        lines.extend(["## Failures", ""])
        lines.extend(_rows_table(report.failures))
    if report.needs_review:
        lines.extend([
            "## Needs human review", "",
            "Nothing here is a failure and nothing here blocks. Each one is a question the "
            "check could not answer confidently enough to state.", "",
        ])
        lines.extend(_rows_table(report.needs_review))
    if report.passes:
        lines.extend(["## Passed", ""])
        lines.extend(_rows_table(report.passes))

    if report.without_criterion:
        lines.extend([
            "## Scanner findings with no WCAG criterion", "",
            "Best-practice rules the scanner reports that map to no WCAG 2.2 success "
            "criterion. Listed because they were found, not counted against conformance.", "",
            "| Route | Rule | Impact | Elements |", "|---|---|---|---|",
        ])
        for item in report.without_criterion:
            lines.append(
                f"| {_cell(item['route'], 80)} | {_cell(item['rule'], 60)} "
                f"| {_cell(item['impact'], 20)} | {len(item['elements'])} |"
            )
        lines.append("")

    if report.unjudged:
        lines.extend([
            "## Selected but not judged", "",
            "| Route | Element | Check | Why |", "|---|---|---|---|",
        ])
        for item in report.unjudged:
            lines.append(
                f"| {_cell(item['route'], 80)} | `{_cell(item['selector'], 80)}` "
                f"| {item['checker']} | {_cell(item['reason'])} |"
            )
        lines.append("")

    if not report.rows and not report.unjudged:
        lines.extend([
            "No accessibility findings were produced for this run. That is only a clean result "
            "if a scan actually ran — check this run's test report for the accessibility "
            "cases.", "",
        ])
    return "\n".join(lines)


def publish_report(*, tenant_id, project_id, run_id, title: str = "") -> dict:
    """Merge one run's accessibility check and register the report against that run.

    Register-don't-recreate, like every other artifact on this path: re-running the merge for a
    run updates its report rather than stacking a second one. Best-effort on the body, matching
    `_register_test_report` — a report registered from its hash alone is worse than one with a
    body, and far better than no report because the object store blinked.
    """
    from mcp_platform_state import tools

    from apps.registry.models import Artifact

    report = merge_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id)
    body = report_body(report, title=title)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    staged = None
    try:
        staged = tools.stage_artifact_body(
            tenant_id, project_id, run_id, "testing", REPORT_FILENAME, body,
            content_type="text/markdown",
        )
    except Exception:  # noqa: BLE001 — see the docstring
        staged = None

    with tenant_context(tenant_id):
        existing = Artifact.objects.filter(
            tenant_id=tenant_id, run_id=run_id, type=REPORT_TYPE).first()
    if existing is not None:
        tools.update_artifact(
            tenant_id, str(existing.id),
            content_hash=(staged or {}).get("content_hash") or digest,
        )
        artifact_id = str(existing.id)
    else:
        created = tools.register_artifact(
            tenant_id, project_id, run_id, "testing", REPORT_TYPE, "internal",
            content_hash=(staged or {}).get("content_hash") or digest,
            s3_key=(staged or {}).get("s3_key"),
            title=f"Accessibility report{f' — {title}' if title else ''}",
        )
        artifact_id = created["id"]

    with tenant_context(tenant_id):
        tools.log_event(
            tenant_id, "a11y", "a11y.report_merged", "artifact", artifact_id,
            {"failures": len(report.failures), "needs_review": len(report.needs_review),
             "passed": len(report.passes), "unjudged": len(report.unjudged),
             "from_rules": report.from_rules, "complete": report.complete},
        )
    return {
        "artifact_id": artifact_id,
        "failures": len(report.failures),
        "needs_review": len(report.needs_review),
        "passed": len(report.passes),
        "unjudged": len(report.unjudged),
        "from_rules": report.from_rules,
        "complete": report.complete,
        "summary": _summary_line(report),
    }


def _summary_line(report: MergedReport) -> str:
    """One line for the run console. Never says "clean" when something was left unanswered."""
    line = (f"{len(report.failures)} accessibility failure(s), "
            f"{len(report.needs_review)} for human review")
    if report.unjudged:
        line += f", {len(report.unjudged)} not judged"
    return line
