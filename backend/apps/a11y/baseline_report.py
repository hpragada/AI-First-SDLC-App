"""Where this application stands against WCAG 2.2 (QA-18).

QA-12's merged report answers *"what did this run find?"* — a list of findings from one pass,
row by row. That is the right document for a build, and the wrong one for a client who has just
had their inherited application audited. They are asking something else: **how bad is it, by
rule, and are we better than last time?**

**Rendered from the ledger, and scoped to the PROJECT.** Both halves of that matter.

  * From the ledger, not from a second merge, for the reason QA-13 established: the document
    and the stored record are then the same data by construction rather than two renderings
    that have to be kept in step.
  * Project-scoped, not audit-scoped, because "where we stand" is a statement about the
    application. An audit that reached 38 of 50 routes must not produce a standing that
    silently drops what is already known about the other 12 — that is D-A11Y-3's failure at the
    scale of a whole report. What the audit *did* cover is stated in the document instead, so a
    reader can see how much of the picture this pass refreshed.

**One criterion, one line.** Twenty findings of 1.4.3 across six pages is one row saying
Level AA, High, 6 pages, 20 items — because the question a conformance report answers is "where
do we stand on 1.4.3?", and twenty rows of the same answer is not it. The individual findings
are in the per-run report and in the backlog, which is where a developer works.

**Movement is the point of doing it twice.** Every baseline records its per-criterion counts,
so the next one can say what was fixed, what is new, and what is still open. Without that, a
second audit is just another opinion; with it, it is progress a client can see. This is also
what OP-08's remediation campaign tracks against.
"""
from __future__ import annotations

import hashlib

from apps.tenancy.context import tenant_context

from .backlog import SEVERITY_ORDER, breadth_by_criterion, open_findings, prioritised

#: The artifact this renders to. Deliberately NOT `a11y_report` (QA-12's per-run document):
#: one is "what this pass found", the other is "where the application stands", and collapsing
#: them would make the second inherit the first's run-shaped identity and versioning.
BASELINE_TYPE = "a11y_baseline"
BASELINE_FILENAME = "a11y-baseline.md"
BASELINE_TITLE = "Accessibility baseline"

#: How many backlog items the document lists before it stops and points at the full list. A
#: baseline for a badly broken app can hold hundreds; a document nobody scrolls to the end of
#: is a document nobody reads. Truncation is ALWAYS stated (never silent) — see `_backlog_table`.
MAX_BACKLOG_ROWS = 40


def criterion_rows(tenant_id, project_id) -> list[dict]:
    """One row per breached criterion: severity, level, how many pages, how many items.

    Ordered worst first on the same terms the backlog is (severity, then breadth), so the top
    of this table and the top of the fix list are the same criteria in the same order. Two
    orderings of one truth is one of them being wrong.
    """
    findings = open_findings(tenant_id, project_id)
    breadth = breadth_by_criterion(findings)

    rows: dict[str, dict] = {}
    for finding in findings:
        row = rows.setdefault(finding.criterion, {
            "criterion": finding.criterion,
            "wcag_level": finding.wcag_level,
            "severity": finding.severity,
            "pages": breadth.get(finding.criterion, 0),
            "failures": 0,
            "needs_review": 0,
            "routes": set(),
        })
        row["routes"].add(finding.route)
        if finding.outcome == "failure":
            row["failures"] += 1
        else:
            row["needs_review"] += 1
        # Worst severity wins the row. A criterion whose level we could not read falls back to
        # High per `findings.DEFAULT_SEVERITY`, and one row of it must not drag a genuinely
        # Critical criterion down to look milder than it is.
        if (SEVERITY_ORDER.get(finding.severity, 9)
                < SEVERITY_ORDER.get(row["severity"], 9)):
            row["severity"] = finding.severity
        if finding.wcag_level and not row["wcag_level"]:
            row["wcag_level"] = finding.wcag_level

    out = []
    for row in rows.values():
        out.append({**row, "routes": sorted(row["routes"])})
    out.sort(key=lambda r: (SEVERITY_ORDER.get(r["severity"], 9), -r["pages"], r["criterion"]))
    return out


def previous_counts(tenant_id, project_id) -> dict[str, int]:
    """What the last baseline recorded per criterion, or `{}` when this is the first.

    Read off the previous artifact's `external_ref` rather than recomputed from history: a
    baseline is a statement made at a moment, and re-deriving it later from a ledger that has
    since moved would quietly rewrite what was said.
    """
    from apps.registry.models import Artifact

    with tenant_context(tenant_id):
        previous = (
            Artifact.objects
            .filter(tenant_id=tenant_id, project_id=project_id, type=BASELINE_TYPE)
            .order_by("-version", "-created_at").first()
        )
    if previous is None:
        return {}
    counts = (previous.external_ref or {}).get("open_by_criterion")
    return {str(k): int(v) for k, v in counts.items()} if isinstance(counts, dict) else {}


def movement(current: list[dict], previous: dict[str, int]) -> dict:
    """What changed since the last baseline: fixed, new, still open — per criterion and total.

    "Fixed" here means *no longer open*, which is the ledger's own word for it and is only ever
    set where a later check actually looked (QA-12a). A criterion that disappeared because
    nobody audited its pages this time does not appear as fixed, because the ledger never
    resolved it.
    """
    now = {row["criterion"]: row["failures"] + row["needs_review"] for row in current}
    fixed = sorted(set(previous) - set(now))
    fresh = sorted(set(now) - set(previous))
    return {
        "first_baseline": not previous,
        "fixed_criteria": fixed,
        "new_criteria": fresh,
        "open_now": sum(now.values()),
        "open_before": sum(previous.values()),
        "by_criterion": now,
    }


def _cell(text, limit: int = 120) -> str:
    from .report import _cell as _report_cell

    return _report_cell(text, limit)


def _criterion_table(rows: list[dict], headings: dict) -> list[str]:
    lines = [
        "| Criterion | Level | Severity | Pages affected | Failures | Needs review |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        detail = headings.get(row["criterion"]) or {}
        name = f"{row['criterion']} {detail.get('handle') or ''}".strip()
        level = row["wcag_level"] or detail.get("level") or "—"
        lines.append(
            f"| {_cell(name, 60)} | {level} | {row['severity'].title()} "
            f"| {row['pages']} | {row['failures']} | {row['needs_review']} |"
        )
    lines.append("")
    return lines


def _backlog_table(items: list[dict]) -> list[str]:
    lines = [
        "| # | Severity | Criterion | Page | Element | What to change |",
        "|---|---|---|---|---|---|",
    ]
    for item in items[:MAX_BACKLOG_ROWS]:
        lines.append(
            f"| {item['priority']} | {item['severity'].title()} | {item['criterion']} "
            f"| {_cell(item['route'], 50)} | `{_cell(item['selector'], 50)}` "
            f"| {_cell(item['suggested_fix'] or item['evidence'], 160)} |"
        )
    lines.append("")
    if len(items) > MAX_BACKLOG_ROWS:
        # Said out loud. A truncated list that does not admit it is a list someone will work to
        # the end of and believe they are finished.
        lines.extend([
            f"…and {len(items) - MAX_BACKLOG_ROWS} more. This document shows the first "
            f"{MAX_BACKLOG_ROWS}; every item is tracked as its own work item under "
            f"“{_cell('Accessibility backlog', 60)}”.",
            "",
        ])
    return lines


def baseline_body(*, tenant_id, project_id, audit=None) -> str:
    """The baseline as a document a person reads. Markdown, like every other report here."""
    from .findings import describe_criteria
    from .policy import describe_policy, enforces_baseline, policy_or_default
    from .routes import describe_routes, scope_change_since

    rows = criterion_rows(tenant_id, project_id)
    items = prioritised(tenant_id, project_id, blocking_only=True)
    change = movement(rows, previous_counts(tenant_id, project_id))
    headings = describe_criteria([row["criterion"] for row in rows])
    policy, policy_error = policy_or_default(tenant_id, project_id)

    total_items = sum(row["failures"] + row["needs_review"] for row in rows)
    pages = sorted({route for row in rows for route in row["routes"]})

    lines = [f"# {BASELINE_TITLE}", ""]
    if not rows:
        lines.extend([
            "No accessibility problems are open for this application.",
            "",
            "That is only good news if something has actually looked. Check the coverage note "
            "below before reading this as a clean bill of health.",
            "",
        ])
    else:
        lines.extend([
            f"**{len(rows)} WCAG 2.2 criteria** are currently breached, across "
            f"**{len(pages)} page(s)**, in **{total_items} item(s)**.",
            "",
        ])

    # Where the bar is, before any number is read. A reader comparing two projects' baselines
    # has to know they were held to the same standard — and if they were not, why.
    lines.extend(["## What this is measured against", "", describe_policy(policy), ""])
    if policy_error:
        lines.extend([
            f"> **This project's accessibility settings could not be read** ({policy_error}), "
            "so the standard default above was used. The numbers here are correct for that "
            "default and may not be the bar this project intended.",
            "",
        ])

    # Coverage, and it comes before the findings on purpose (D-A11Y-3): a reader has to know
    # how much of the application this standing is actually about before they read it.
    lines.extend(["## What has been looked at", "", describe_routes(tenant_id, project_id)])
    # What MOVED in the scope, next to what moved in the findings. The Movement section below
    # compares this audit's findings with the last one's and calls the difference progress —
    # which is only true if both audits looked at the same application. Take twelve failing
    # pages out of scope and the numbers improve on their own, and a reader of the document
    # alone would have no way to know. So the document says it, not only the screen.
    if moved := scope_change_since(tenant_id, project_id):
        parts = []
        if moved["added"]:
            parts.append(f"{len(moved['added'])} page(s) added")
        if moved["removed"]:
            parts.append(f"{len(moved['removed'])} page(s) taken out of scope")
        lines.extend([
            "",
            f"> **The page list changed since the previous audit** — {' and '.join(parts)}. "
            f"This standing covers {moved['now']} page(s) where the previous one covered "
            f"{moved['before']}, so the two are not directly comparable.",
        ])
        if moved["removed"]:
            lines.append(f"> Taken out of scope: {_cell(', '.join(moved['removed']), 300)}.")
    if audit is not None:
        summary = audit.summary or {}
        lines.append("")
        lines.append(
            f"The most recent audit asked for {summary.get('asked', 0)} page(s) and opened "
            f"{summary.get('opened', 0)}."
        )
        if unreachable := list(summary.get("unreachable") or []):
            lines.extend([
                "",
                f"> **{len(unreachable)} page(s) could not be opened**, so nothing here says "
                f"anything about them: {_cell(', '.join(unreachable), 300)}.",
            ])
    lines.append("")

    if change["first_baseline"]:
        lines.extend([
            "## Movement", "",
            "This is the first baseline for this application, so there is nothing to compare "
            "it against yet. Re-run the audit after some fixes and this section will show what "
            "closed and what is new.", "",
        ])
    else:
        lines.extend([
            "## Movement since the last baseline", "",
            f"{change['open_before']} item(s) were open then; {change['open_now']} are open "
            f"now.", "",
        ])
        if change["fixed_criteria"]:
            lines.append(
                f"- **Fully fixed:** {', '.join(change['fixed_criteria'])} — no page still "
                f"breaches these."
            )
        if change["new_criteria"]:
            lines.append(
                f"- **Newly breached:** {', '.join(change['new_criteria'])} — these were not "
                f"open at the last baseline."
            )
        if not change["fixed_criteria"] and not change["new_criteria"]:
            lines.append("- The same criteria are breached as last time.")
        lines.append("")

    if rows:
        lines.extend(["## Where we stand, by criterion", ""])
        lines.extend(_criterion_table(rows, headings))

    lines.extend(["## What to fix first", ""])
    if items:
        lines.extend([
            "In order. Every item below is tracked as its own work item, closes itself when a "
            "later check no longer finds it, and reopens as the same item if it comes back.",
            "",
            # QA-19. A client reading "47 problems" has to be able to see whether those
            # currently stop anything — a list of forty-seven items means something very
            # different depending on the answer, and leaving them to guess is not an option.
            (
                "**These currently stop work.** Until they are fixed, this project's gates "
                "will not pass."
                if enforces_baseline(policy) else
                "**These do not currently stop any work.** They are reported so the team can "
                "plan; turn baseline enforcement on in this project's accessibility settings "
                "when you are ready to be held to them. Problems introduced by *new* work "
                "still stop that work either way."
            ),
            "",
        ])
        lines.extend(_backlog_table(items))
    else:
        lines.extend([
            "Nothing in this project currently clears the bar for a tracked fix. Anything "
            "awaiting a reviewer's decision is in the review queue rather than here.", "",
        ])
    return "\n".join(lines)


def publish_baseline(*, tenant_id, project_id, audit=None) -> dict:
    """Render the baseline and register it as the project's `a11y_baseline` artifact.

    Register-don't-recreate, like every artifact on this path: a re-audit produces the next
    *version* of one document rather than a second one, so "the baseline" stays a thing a
    client can point at while its history stays readable.

    The per-criterion counts ride on `external_ref` so the next baseline can say what moved.
    Best-effort on the body, matching `publish_report` — a baseline registered from its hash
    alone is worse than one with a body, and far better than none because the object store
    blinked.
    """
    from mcp_platform_state import tools

    from apps.registry.models import Artifact

    rows = criterion_rows(tenant_id, project_id)
    body = baseline_body(tenant_id=tenant_id, project_id=project_id, audit=audit)
    digest = hashlib.sha256(body.encode("utf-8")).hexdigest()
    open_by_criterion: dict[str, int] = {
        row["criterion"]: row["failures"] + row["needs_review"] for row in rows
    }
    external_ref = {
        "kind": "a11y_baseline",
        "audit": str(audit.id) if audit is not None else "",
        "open_by_criterion": open_by_criterion,
    }

    try:
        # Named for its own content, NOT for the fixed filename. `stage_artifact_body` keys on
        # the run, and a baseline has none — so every version would write to the same object
        # and each new baseline would overwrite the body of the one before it. Comparing this
        # baseline against the last one is the entire reason for taking a second one.
        staged = tools.stage_artifact_body(
            tenant_id, project_id, None, "testing",
            BASELINE_FILENAME.replace(".md", f"-{digest[:12]}.md"), body,
            content_type="text/markdown",
        )
    except Exception:  # noqa: BLE001 — see the docstring
        staged = None

    with tenant_context(tenant_id):
        existing = (
            Artifact.objects
            .filter(tenant_id=tenant_id, project_id=project_id, type=BASELINE_TYPE)
            .order_by("-version", "-created_at").first()
        )
    created = tools.register_artifact(
        tenant_id, project_id, None, "testing", BASELINE_TYPE, "internal",
        content_hash=(staged or {}).get("content_hash") or digest,
        s3_key=(staged or {}).get("s3_key"),
        external_ref=external_ref,
        title=BASELINE_TITLE,
        supersedes=str(existing.id) if existing is not None else None,
    )
    with tenant_context(tenant_id):
        tools.log_event(
            tenant_id, "a11y", "a11y.baseline_published", "artifact", created["id"],
            {"criteria": len(rows), "version": created.get("version"),
             "audit": external_ref["audit"]},
        )
    return {"artifact_id": created["id"], "version": created.get("version"),
            "criteria": len(rows), "open": sum(open_by_criterion.values())}
