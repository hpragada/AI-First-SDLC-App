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

**Silence is reported, never inferred.** Five things could quietly make a report look clean:
an element that was captured but never judged (the run hit its cap, or the judge was
unavailable), a screen that was scanned but had nothing worth judging, a scanner violation
that names no WCAG criterion, a screen the rule scanner never ran on at all — whose empty
violation list is the same shape as a clean page (QA-16, when capture stopped being limited to
dedicated accessibility cases) — and, since QA-17's baseline audit, a route that never opened
at all. All five are counted and stated at the top (D-A11Y-3), because an incomplete
accessibility check that reads as a clean one is the single worst outcome available to this
feature.

**The document is rendered from the ledger, not alongside it** (QA-13). `publish_report` merges,
records the findings, then reads the rows back and renders those — so the report and the stored
record are the same data by construction rather than two renderings that have to be kept in
step. What the ledger does not hold comes from the merge and only from it: the passes (not
findings), the elements that were never judged, and the scanner's best-practice violations that
map to no criterion. Those are facts about *this run*, and they are exactly the facts that stop
an incomplete report reading as a clean one.

Nothing here decides whether a finding is "the same" as one from a previous run. That question
belongs to QA-12a's fingerprint, and answering it here with a second, weaker rule would be
exactly the kind of drift the two-keys note in `A11yJudgmentCache` warns about.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from apps.tenancy.context import tenant_context
from integrations.types import A11Y_UNCERTAIN, A11yJudgment, A11yRuleFailure

from .dispatch import content_hash
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

#: Where a finding can be looked at — the picture, the element's rectangle on it, and the whole
#: of what the check saw (S-39). Every AI finding in this document says "screenshot shows…", and
#: until there was a screen holding that screenshot the sentence pointed at nothing a reader
#: could reach. Rendered only for a finding the ledger holds, because only then is there an id
#: to be reached *by* — see `finding_link`.
FINDING_PATH = "/a11y/finding/"


def finding_link(row, identity: dict | None = None) -> str:
    """`[…](/a11y/finding/<id>)`, or "" for a row nothing can be reached by.

    A **stored** finding carries its own id. A **merge** row does not, and that is not an edge
    case here: a baseline audit manufactures no `Run`, so `open_findings_for_run` matches
    nothing for it and the per-run report renders from the merge — which is exactly the document
    the team was reading when they went looking for the screenshot.

    So `identity` maps fingerprint → id, built once by `publish_report` from the ledger it has
    just written. The fingerprint is what makes two sightings the same problem, so this resolves
    to the same row the ledger holds rather than to a guess.
    """
    identifier = str(getattr(row, "id", "") or "")
    if not identifier and identity:
        identifier = identity.get(_fingerprint_of(row), "")
    return "" if not identifier else f"[See the capture]({FINDING_PATH}{identifier})"


def _fingerprint_of(row) -> str:
    from .findings import fingerprint

    stored = str(getattr(row, "fingerprint", "") or "")
    return stored or fingerprint(
        route=getattr(row, "route", ""), selector=getattr(row, "selector", ""),
        criterion=_primary(row), checker=str(getattr(row, "checker", "") or ""),
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
    #: What the AI actually said (`pass`/`fail`/`uncertain`), which is NOT `outcome` — a `pass`
    #: on an element the scanner failed comes out of triage as a failure, and the ledger has to
    #: be able to show a reviewer both halves of that.
    verdict: str = ""
    impact: str = ""                  # the scanner's own severity word, never conflated with ours
    screenshot_ref: str = ""          # pointer to the element's picture, never the image
    # Which engine, model and prompt version produced the verdict — read from the `Run` when it
    # was stored (QA-02), never from the agent's own claim. Blank on a rule finding: a
    # measurement has no model.
    engine: str = ""
    model: str = ""
    prompt_version: str = ""
    #: `dispatch.content_hash` for this row — the fingerprint of exactly what the judge looked
    #: at. Blank on a rule finding, which has no judge and never reaches the review console.
    #: Carried here so `findings.record_run_findings` can tell "the same element, judged again"
    #: from "a different element now", which is what makes a human ruling durable (QA-23).
    content_hash: str = ""

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
    #: Screens the rule scanner never ran on, with the reason: [{route, reason}] (QA-16).
    #: Distinct from `unjudged`, which is the AI half — a screen can have every element judged
    #: and still have had no scan, and vice versa. Both are "we did not look", and neither may
    #: be inferred from a quiet result.
    unscanned: list[dict] = field(default_factory=list)
    #: Routes that never opened, with the reason: [{route, reason}] (QA-17). The strongest of
    #: the silences — nothing at all was seen — and the only one that also has to be kept out
    #: of `routes`, so an unreachable page cannot resolve its own findings by absence.
    unreachable: list[dict] = field(default_factory=list)
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


def _row_from_triage(finding: TriagedFinding, audit: dict | None = None) -> ReportRow:
    """One triaged judgment as a report row.

    The source is the **scanner** whenever a scanner failure decided the row — including the
    case where the AI agreed. A reader deciding whether to trust a finding needs to know it was
    measured rather than judged, and the AI's agreement does not make it an AI finding.
    """
    failure = finding.rule_failure
    audit = audit or {}
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
        verdict=finding.judgment.verdict,
        impact=(failure.impact if failure is not None else ""),
        screenshot_ref=finding.candidate.screenshot_ref,
        engine=str(audit.get("engine") or ""),
        model=str(audit.get("model") or ""),
        prompt_version=str(audit.get("prompt_version") or ""),
        content_hash=content_hash(finding.judgment.checker, finding.candidate),
    )


def _row_from_rule(failure: A11yRuleFailure) -> ReportRow:
    """A scanner failure on something the AI was never asked about.

    Most of the scan lands here — the AI checks apply to a minority of what axe flags —
    and it is the half that would have been missing if the merge only walked the judgments.
    """
    return ReportRow(
        source=SOURCE_RULE, outcome=TRIAGE_FAILURE, criteria=(failure.criterion,),
        route=failure.route, selector=failure.selector, evidence=failure.evidence,
        reason="The rule scanner proved this failure. No AI check was asked about this element.",
        confidence=None, rule_id=failure.rule_id, impact=failure.impact,
    )


def _judgments_for(tenant_id, project_id,
                   hashes: list[str]) -> dict[str, tuple[A11yJudgment, dict]]:
    """Every stored verdict for these inputs, with what produced it — one query, not one each.

    The audit half travels with the judgment rather than being looked up again later, because
    the pair has to stay together: a verdict and the model that produced it are one fact, and
    two queries could disagree about it if a run re-judged in between.
    """
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
        row.content_hash: (
            A11yJudgment(
                criteria=tuple(row.criteria), verdict=row.verdict, confidence=row.confidence,
                evidence=row.evidence, suggested_fix=row.suggested_fix, checker=row.checker,
            ),
            {"engine": row.engine, "model": row.model, "prompt_version": row.prompt_version},
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
                          without_criterion=list(scan.without_criterion),
                          unscanned=list(scan.unscanned),
                          unreachable=list(scan.unreachable))
    matched: set = set()
    for request in requests:
        judgment, audit = judgments.get(request.content_hash, (None, {}))
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
        report.rows.append(_row_from_triage(finding, audit))

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
    """One table cell: no pipes, no newlines, bounded — a markdown table is line-oriented.

    Keep this for the things a cell can genuinely hold — a route, a selector, a rule id, an
    enumeration. **It is no longer used for a finding's own words.** A markdown cell cannot
    hold a line break, so bounding it was never a formatting choice: prose in a table gets cut
    wherever the limit lands, which on this run was mid-sentence inside the alt text the
    document was telling somebody to write. Raising the limit does not fix that — it moves it.
    A table is the wrong container for a paragraph, so the paragraphs left (`_details`).
    """
    flat = " ".join(str(text or "").split()).replace("|", "\\|")
    return flat if len(flat) <= limit else flat[: limit - 1].rstrip() + "…"


def _prose(text) -> str:
    """A finding's own words, whole, for printing outside a table.

    Only the line structure is flattened, and only because a blank line would end the paragraph
    early — every character of the text itself survives. Nothing is escaped: a pipe outside a
    table is a pipe.
    """
    return " ".join(str(text or "").split())


#: How long the scanning column may run before it is summarised. A gist by design and not a
#: truncation: whatever this shortens is printed in full immediately below the same table, so
#: the reader who wants the whole sentence has it on the same screen.
GIST_LIMIT = 150


def _gist(text, limit: int = GIST_LIMIT) -> str:
    """The opening of a finding, for scanning down a column.

    Prefers a whole sentence, then a whole word, and never a half one. It ends in `…` only when
    it actually stopped early, so a short finding reads as complete because it is.
    """
    flat = _prose(text).replace("|", "\\|")
    if len(flat) <= limit:
        return flat
    stop = flat.rfind(". ", 0, limit + 1)
    if stop > limit // 3:                      # a sentence, if there is a real one to end on
        return flat[: stop + 1]
    space = flat.rfind(" ", 0, limit)
    return flat[: space if space > 0 else limit].rstrip(" ,;:") + "…"


def severity_of(row, headings: dict | None = None) -> str:
    """What this row's breach is worth — Critical, High or Medium (QA-18).

    Reads a stored `A11yFinding` and an in-memory `ReportRow` the same way `_primary` does,
    and for the same reason. The ledger row already holds the severity QA-12a derived from the
    standard; a merge row has not been through the ledger yet, so it is derived here from the
    criterion's conformance level using the one mapping there is (`findings.severity_for`).

    **Why this function exists at all.** Severity has been computed since QA-12a, blocks the
    gate since QA-15 and decides whether a defect opens since QA-14 — and until now it appeared
    nowhere in the document a person actually reads. A reviewer could see twenty findings and
    have no way to tell which four stop the release.
    """
    from .findings import severity_for

    stored = str(getattr(row, "severity", "") or "")
    if stored:
        return stored
    level = ((headings or {}).get(_primary(row)) or {}).get("level", "")
    return severity_for(level)


def _rows_table(rows: list, headings: dict | None = None, *,
                severity: bool = True, start: int = 1) -> list[str]:
    """One table of findings, numbered, for scanning.

    `severity` is off for the passes table on purpose — a row that passed has nothing to weigh,
    and a severity beside it reads as something left to fix.

    **Two columns became one, and gained a number.** *Suggested fix* is gone from here entirely
    and *What was found* is now a gist: both are paragraphs, and both are written out under
    `_details` immediately below this table. The leading number is what joins the two halves,
    which is why it is rendered here rather than left to the markdown — a reader scanning the
    table has to be able to name the row they want to read in full.
    """
    head = "| # | Source |" + (" Severity |" if severity else "") + \
           " Criteria | Route | Element | Confidence | What was found |"
    lines = [head, "|---|---|" + ("---|" if severity else "") + "---|---|---|---|---|"]
    for index, row in enumerate(rows, start=start):
        confidence = "measured" if row.confidence is None else f"{row.confidence:.0%}"
        weight = f" {severity_of(row, headings).title()} |" if severity else ""
        lines.append(
            f"| {index} | {row.source} |{weight} {', '.join(row.criteria)} "
            f"| {_cell(row.route, 80)} | `{_cell(row.selector, 80)}` | {confidence} "
            f"| {_gist(row.evidence)} |"
        )
    lines.append("")
    return lines


def _details(rows: list, headings: dict | None = None, *,
             severity: bool = True, start: int = 1,
             identity: dict | None = None) -> list[str]:
    """Each row of the table above, written out with nothing removed.

    This is the half of the fix that matters. The report has always *had* the whole finding —
    the ledger holds it, the judge wrote it — and the document has never printed it, because
    the only place it appeared was a table cell that had to be bounded. Here there is no cell
    and no bound: the evidence and the fix are paragraphs in a document, which is what they
    always were.

    A row with neither is skipped rather than given an empty heading. That happens for a
    scanner finding whose rule carries no remediation text, and a numbered heading with nothing
    under it reads as text that failed to render.
    """
    lines: list[str] = []
    for index, row in enumerate(rows, start=start):
        evidence = _prose(getattr(row, "evidence", ""))
        fix = _prose(getattr(row, "suggested_fix", ""))
        if not evidence and not fix:
            continue
        checker = str(getattr(row, "checker", "") or "")
        facts = [f"{row.source} check" + (f" `{checker}`" if checker else "")]
        if row.confidence is not None:
            facts.append(f"{row.confidence:.0%} confident")
        if severity:
            facts.append(severity_of(row, headings).title())
        link = finding_link(row, identity)
        if not lines:
            lines.extend(["#### Details", ""])
        lines.extend([
            f"**{index}. `{_prose(row.selector)}` on `{_prose(row.route)}`** — "
            f"{_primary(row)}, {', '.join(facts)}." + (f" {link}" if link else ""),
            "",
        ])
        if evidence:
            lines.extend([f"**What was found.** {evidence}", ""])
        if fix:
            lines.extend([f"**What to change.** {fix}", ""])
    return lines


def _primary(row) -> str:
    """The criterion a row is filed under.

    Reads a stored `A11yFinding` and an in-memory `ReportRow` the same way, deliberately: a
    finding and the row it was built from are the same thing seen twice, and a renderer that
    needed to know which one it had would be a second place for them to disagree.
    """
    stored = getattr(row, "criterion", "")
    if stored:
        return stored
    criteria = getattr(row, "criteria", ()) or ()
    return criteria[0] if criteria else ""


def _grouped(rows: list, headings: dict, *, severity: bool = True,
             start: int = 1, identity: dict | None = None) -> list[str]:
    """Rows under one heading per WCAG criterion, worst-numbered first within the group.

    Grouping by criterion is what makes the document answer a conformance question — "where do
    we stand on 1.1.1?" — instead of only an engineering one. The failure / needs-review / pass
    split is kept ABOVE it, because a reader's first question is what is broken and the second
    is which rule it breaks; folding both into one axis would put a blocking failure and a
    low-confidence question side by side in the same block.
    """
    by_criterion: dict[str, list] = {}
    for row in rows:
        by_criterion.setdefault(_primary(row), []).append(row)

    lines: list[str] = []
    number = start
    for criterion in sorted(by_criterion):
        detail = headings.get(criterion) or {}
        handle = detail.get("handle") or ""
        level = detail.get("level") or ""
        name = f"{criterion} {handle}".strip() or "(no criterion named)"
        group = by_criterion[criterion]
        lines.append(f"### {name}{f' — Level {level}' if level else ''}")
        lines.append("")
        lines.extend(_rows_table(group, headings, severity=severity, start=number))
        # Under this criterion's own table rather than collected at the end of the document:
        # the reader who wants row 3 in full is looking at row 3 right now.
        lines.extend(_details(group, headings, severity=severity, start=number,
                              identity=identity))
        number += len(group)
    return lines


def _could_not_answer(rows: list) -> list:
    """Rows a person has to look at because the check reached no verdict — not because it was
    unsure.

    Told apart **structurally**, not by reading the text: an item the judge could not be asked
    about carries the `uncertain` verdict, while a low-confidence one carries a real `fail` or
    `pass` that the confidence gate held back. Matching on the reason's wording would break the
    moment someone improved a sentence.
    """
    return [row for row in rows if getattr(row, "verdict", "") == A11Y_UNCERTAIN]


def report_body(report: MergedReport, *, findings: list | None = None, title: str = "",
                resolved: int = 0, identity: dict | None = None) -> str:
    """The merged report as a document a person reads.

    Markdown, because the platform's artifact preview renders it generically by content type —
    an `a11y_report` registered as markdown displays with no frontend work at all.

    `findings` are the ledger rows this run left open (QA-13). When given, they are what the
    failure and needs-review sections render from, so the document and the stored record are
    the same data rather than two renderings of it. Left out, it falls back to the merge — which
    is what a caller wants when there is no run to key a ledger on.
    """
    from .findings import describe_criteria

    rows = list(findings) if findings is not None else [
        row for row in report.rows if row.outcome != TRIAGE_PASS
    ]
    failures = [row for row in rows if row.outcome == TRIAGE_FAILURE]
    review = [row for row in rows if row.outcome == TRIAGE_REVIEW]
    unanswered = _could_not_answer(review)
    headings = describe_criteria(
        [_primary(row) for row in rows] + [_primary(row) for row in report.passes])

    lines = [f"# Accessibility report{f' — {title}' if title else ''}", ""]
    lines.append(
        f"{len(failures)} failure(s), {len(review)} needing human review, "
        f"{len(report.passes)} passed — across {len(report.routes) or 'no'} screen(s)."
    )
    lines.append("")
    lines.append(
        f"{report.judged} element(s) were judged by the AI checks and {report.from_rules} "
        f"further finding(s) came from the rule scanner alone."
    )
    if resolved:
        lines.append("")
        lines.append(f"{resolved} finding(s) open before this run were not found again.")
    lines.append("")

    # D-A11Y-3, and it is the first thing after the totals on purpose — before anyone reaches a
    # table and starts counting rows. Two different silences, said separately because they mean
    # different things to whoever has to act on them.
    if unanswered:
        reasons = sorted({(getattr(row, "evidence", "") or "").strip() for row in unanswered})
        lines.extend([
            "> **The AI checks did not fully run for this report.** "
            f"{len(unanswered)} item(s) were sent for human review because no verdict could be "
            "reached, not because the check was unsure. Nothing about them here says whether "
            "they are accessible.",
            "",
        ])
        # A reason is a sentence, and a blockquote line has room for one. It was bounded here
        # only because `_cell` was the tool at hand; there is no table to fit.
        lines.extend([f"> - {_prose(reason)}" for reason in reasons if reason])
        lines.append("")
    if report.unjudged:
        lines.extend([
            "> **This check is incomplete.** "
            f"{len(report.unjudged)} element(s) were selected for an AI check and no verdict "
            "was recorded for them, so nothing here says whether they are accessible. They are "
            "listed at the end and need a person to look at them.",
            "",
        ])
    if report.unscanned:
        # The third silence (QA-16). The rule half and the AI half fail independently: a screen
        # can have every element judged and still never have been scanned, and an empty
        # violation list looks exactly like a clean page. Naming the routes matters — "some
        # screens were not scanned" is not something a reader can act on.
        routes = sorted({str(item.get("route") or "").strip() for item in report.unscanned})
        reasons = sorted({str(item.get("reason") or "").strip() for item in report.unscanned})
        lines.extend([
            "> **The rule scanner did not run on every screen.** "
            f"{len(routes)} screen(s) were captured without a scan, so the measurable checks "
            "(contrast, missing names, landmarks) say nothing about them — only the AI checks "
            f"did. Screens: {_cell(', '.join(r for r in routes if r), 400)}.",
            "",
        ])
        # A reason is a sentence, and a blockquote line has room for one. It was bounded here
        # only because `_cell` was the tool at hand; there is no table to fit.
        lines.extend([f"> - {_prose(reason)}" for reason in reasons if reason])
        lines.append("")
    if report.unreachable:
        # The strongest silence (QA-17), and the one a reader is most likely to mistake for
        # good news: a route that 404s or sits behind a login produces no findings at all.
        # Named, with the reason, because "some pages were not reached" tells nobody which
        # part of their application is still unaudited.
        routes = sorted({str(item.get("route") or "").strip() for item in report.unreachable})
        reasons = sorted({str(item.get("reason") or "").strip() for item in report.unreachable})
        lines.extend([
            "> **Some screens could not be opened at all.** "
            f"{len(routes)} route(s) never loaded, so neither the rule scanner nor the AI "
            "checks saw them and nothing here says anything about whether they are "
            f"accessible. Routes: {_cell(', '.join(r for r in routes if r), 400)}.",
            "",
        ])
        # A reason is a sentence, and a blockquote line has room for one. It was bounded here
        # only because `_cell` was the tool at hand; there is no table to fit.
        lines.extend([f"> - {_prose(reason)}" for reason in reasons if reason])
        lines.append("")

    # One counter across the whole document, so a number names exactly one finding. Numbering
    # per section would give this report three number 1s, and "have a look at 4" would be a
    # question rather than a reference.
    number = 1
    if failures:
        lines.extend(["## Failures", ""])
        lines.append(
            "The table is for scanning. Every row is written out in full underneath it, "
            "numbered to match — nothing here is shortened except to fit the column."
        )
        if any(finding_link(row, identity) for row in rows):
            # Said once, at the top, rather than left for a reader to work out from a link they
            # may not click. Almost every AI finding in this document opens with "Screenshot
            # shows…", and until S-39 that sentence pointed at a picture nothing could open.
            lines.append("")
            lines.append(
                "Where a finding describes a screenshot, **See the capture** opens the picture "
                "it was describing, with the element marked on it."
            )
        lines.append("")
        lines.extend(_grouped(failures, headings, start=number, identity=identity))
        number += len(failures)
    if review:
        lines.extend([
            "## Needs human review", "",
            "Nothing here is a failure and nothing here blocks. Each one is a question the "
            "check could not answer confidently enough to state.", "",
        ])
        lines.extend(_grouped(review, headings, start=number, identity=identity))
        number += len(review)
    if report.passes:
        lines.extend(["## Passed", ""])
        lines.extend(_grouped(report.passes, headings, severity=False, start=number,
                              identity=identity))
        number += len(report.passes)

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

    if not rows and not report.passes and not report.unjudged:
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

    **The ledger is written from this same merge** (QA-12a), not from a second pass over the
    data. One merge, two destinations: a document a person reads now, and rows that outlive the
    run. Recording them separately would let the report and the ledger drift into disagreeing
    about what was found, which is the one thing a conformance record may not do.

    **`run_id` is a capture key, and it may name no run at all** (QA-17). A baseline audit
    partitions its capture by its own id rather than manufacturing a `Run` no agent executed,
    so the run is *resolved* here rather than assumed: found, the report hangs off it as it
    always has; not found, the artifact is registered against the project with the key in its
    `external_ref`, which is what keeps two audits of one project from overwriting each other.
    """
    from mcp_platform_state import tools

    from apps.registry.models import Artifact
    from apps.runs.models import Run

    from .findings import ids_by_fingerprint, open_findings_for_run, record_run_findings

    report = merge_run(tenant_id=tenant_id, project_id=project_id, run_id=run_id)
    ledger: dict = {"opened": [], "seen_again": [], "resolved": []}
    try:
        ledger = record_run_findings(tenant_id=tenant_id, project_id=project_id,
                                     run_id=run_id, report=report)
    except Exception as exc:  # noqa: BLE001
        # Best-effort for the same reason the body is: the report is what a person reads NOW,
        # and losing it because the ledger write failed is the worse trade. The failure is
        # returned and logged rather than swallowed, because a silent ledger failure would mean
        # QA-14 opening no defects with nothing anywhere saying why.
        ledger["error"] = str(exc)

    # Read the rows back rather than rendering what we just handed over (QA-13): the document
    # then says exactly what the ledger holds, including a problem first seen three runs ago
    # and still open. If the write above failed there is nothing to read, so the merge is used
    # — a report from slightly different data beats no report at all.
    stored = [] if ledger.get("error") else open_findings_for_run(tenant_id, project_id, run_id)
    # Fingerprint → ledger id, so a row that did NOT come back from `open_findings_for_run` can
    # still point at the finding it is. That is the ordinary case on a brownfield audit, which
    # has no `Run` for those rows to hang off — and it is the report a client actually reads.
    identity = {} if ledger.get("error") else ids_by_fingerprint(tenant_id, project_id)
    body = report_body(report, findings=stored or None, title=title,
                       resolved=len(ledger["resolved"]), identity=identity)
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
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first() if run_id else None
        if run is not None:
            existing = Artifact.objects.filter(
                tenant_id=tenant_id, run_id=run_id, type=REPORT_TYPE).first()
        else:
            # No run behind this key. Scoped to the key rather than to "any run-less a11y
            # report in this project", which would make every audit overwrite the previous
            # one's report — and a baseline you cannot compare against is not a baseline.
            existing = Artifact.objects.filter(
                tenant_id=tenant_id, project_id=project_id, run__isnull=True,
                type=REPORT_TYPE, external_ref__a11y_capture=str(run_id or ""),
            ).first() if run_id else None
    if existing is not None:
        tools.update_artifact(
            tenant_id, str(existing.id),
            content_hash=(staged or {}).get("content_hash") or digest,
        )
        artifact_id = str(existing.id)
    else:
        created = tools.register_artifact(
            tenant_id, project_id, str(run.id) if run is not None else None,
            "testing", REPORT_TYPE, "internal",
            content_hash=(staged or {}).get("content_hash") or digest,
            s3_key=(staged or {}).get("s3_key"),
            external_ref=None if run is not None else {"a11y_capture": str(run_id or "")},
            title=f"Accessibility report{f' — {title}' if title else ''}",
        )
        artifact_id = created["id"]

    with tenant_context(tenant_id):
        tools.log_event(
            tenant_id, "a11y", "a11y.report_merged", "artifact", artifact_id,
            {"failures": len(report.failures), "needs_review": len(report.needs_review),
             "passed": len(report.passes), "unjudged": len(report.unjudged),
             "from_rules": report.from_rules, "complete": report.complete,
             "unscanned": len(report.unscanned),
             "unreachable": len(report.unreachable),
             "findings_opened": len(ledger["opened"]),
             "findings_seen_again": len(ledger["seen_again"]),
             "findings_resolved": len(ledger["resolved"]),
             "findings_error": ledger.get("error", "")},
        )
    return {
        "artifact_id": artifact_id,
        "failures": len(report.failures),
        "needs_review": len(report.needs_review),
        "passed": len(report.passes),
        "unjudged": len(report.unjudged),
        "from_rules": report.from_rules,
        "complete": report.complete,
        "unscanned": len(report.unscanned),
        "unreachable": len(report.unreachable),
        "ledger": ledger,
        "summary": _summary_line(report),
    }


def _summary_line(report: MergedReport) -> str:
    """One line for the run console. Never says "clean" when something was left unanswered."""
    line = (f"{len(report.failures)} accessibility failure(s), "
            f"{len(report.needs_review)} for human review")
    if report.unjudged:
        line += f", {len(report.unjudged)} not judged"
    if report.unreachable:
        line += f", {len(report.unreachable)} screen(s) never opened"
    return line
