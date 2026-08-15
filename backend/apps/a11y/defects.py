"""Accessibility findings → tracked defects that close themselves (QA-14).

The platform already runs this loop twice: a failing test opens a `defect` child WorkItem and a
now-passing one closes it (`quality.services._reconcile_defects`), and a Critical/High security
finding does the same (`record_security_findings`). This is the third, and it is deliberately a
copy of the second — right down to the `external_ref` shape — because a reviewer who has read
one should not have to learn another.

**Where this lives, and why not next to its twin.** The task text says "copy
`record_security_findings`" in `apps/quality/services.py`. The pattern is copied; the file is
not, because that would make `quality` depend on `a11y` models, and every other piece of
accessibility logic (capture, ingest, scanner, triage, report, findings) already lives here.
Nothing about the loop changes by sitting in the app that owns the data it reads.

**One thing from security that must NOT be copied, and it is the whole risk of this task.**
Security closes a defect when its finding is *absent from the current list*. Copying that
literally would be a serious bug: a run covers the screens it captured, so a run that tested
`/checkout` and not `/cart` would close every accessibility defect on `/cart` as though it had
been fixed. That is the exact trap QA-12a exists to avoid. So this reconciles against the
**ledger's own status**, which already encodes "resolve by absence, but only where we looked" —
a defect closes when its finding was seen to be gone, never because a run did not visit it.

**The other difference the backlog names.** Security *drops* its non-blocking findings; only
Critical/High become work items and the rest are discarded. Accessibility cannot do that — the
uncertain ones have to stay for the SME queue. They already do, because QA-12a stores every
finding. All this module does is not open a defect for them:

    blocking      ⇒ defect + ledger row
    non-blocking  ⇒ ledger row only, and it stays in the review queue

**Its own `external_ref` key.** Test defects are keyed on `test_ref`, security on `finding`,
and these on `a11y_finding`. Three distinct keys means three reconciliations that cannot reach
into each other's rows — the test gate already scopes itself this way, and a shared key would
have let a security run quietly close every accessibility defect on the same story.
"""
from __future__ import annotations

from apps.tenancy.context import tenant_context

#: The severities that open a defect. The same bar security uses, and the bar QA-08's policy
#: will state. QA-12a derives severity from the WCAG conformance level, so in practice every
#: Level A breach (Critical) and every Level AA breach (High) opens one — which is exactly the
#: AA conformance target the design phase commits a project to.
A11Y_BLOCKING = {"critical", "high"}

#: Marks these rows as ours in `external_ref`, alongside the key. Not load-bearing on its own —
#: `a11y_finding` is what scopes the query — but it is what a person reads on the work item.
DEFECT_KIND = "a11y"


def _title(finding) -> str:
    """A defect title a developer can triage without opening anything else."""
    where = finding.selector or finding.route or "this page"
    return f"Accessibility: {finding.criterion} on {finding.route} — {where}"[:512]


def _description(finding) -> str:
    """What was found, what to change, and how sure we are — in that order.

    The suggested fix is included because a checker only produces one for a *failure* (QA-03's
    schema requires it), so on a defect it is always there and always the most useful line.
    """
    level = f" (Level {finding.wcag_level})" if finding.wcag_level else ""
    lines = [
        f"**WCAG 2.2 {finding.criterion}{level}** — found by "
        f"{'the rule scanner' if finding.source == 'rule' else 'the AI accessibility check'}.",
        "",
        f"- Screen: `{finding.route}`",
        f"- Element: `{finding.selector}`",
    ]
    if finding.confidence is not None:
        lines.append(f"- Confidence: {finding.confidence:.0%}")
    if finding.rule_id:
        lines.append(f"- Scanner rule: `{finding.rule_id}`")
    if len(finding.criteria or []) > 1:
        lines.append(f"- Also breaches: {', '.join(finding.criteria[1:])}")
    if not finding.stable:
        lines.append(
            "- This element had no selector of its own, so it is identified by its position "
            "on the page. If the page is reordered this may be reported again."
        )
    lines.extend(["", "**What was found**", "", finding.evidence or "_No evidence recorded._"])
    if finding.suggested_fix:
        lines.extend(["", "**Suggested fix**", "", finding.suggested_fix])
    return "\n".join(lines)


def _external_ref(finding) -> dict:
    return {
        "defect": f"DEF-A11Y-{finding.fingerprint[:12]}",
        # The key this reconciliation scopes on. Deliberately NOT `finding`, which is security's
        # — see the module docstring.
        "a11y_finding": finding.fingerprint,
        "kind": DEFECT_KIND,
        "severity": finding.severity,
        "criterion": finding.criterion,
        "route": finding.route,
        "selector": finding.selector[:512],
        "ledger_id": str(finding.id),
    }


def _parent_for(finding):
    """The work item a defect hangs off — where the problem was **first** seen.

    First rather than last on purpose. A finding that is still open when a second story's test
    run sees it again would otherwise migrate between stories run by run, and a developer would
    lose track of a bug that kept moving. `None` when the finding has no run behind it (a CI
    post, or a direct ledger write): a parentless defect in the right project is still a
    trackable defect, and dropping the finding to avoid one would be much worse.
    """
    run = finding.first_seen_run
    return run.work_item if run is not None else None


def record_a11y_findings(*, tenant_id, project_id, run_id=None) -> dict:
    """Open, close and reopen accessibility defects from the ledger. Never raises at the caller.

    Reconciles the **whole project's** ledger rather than one run's findings, and that is what
    makes the closing rule safe: a finding on a screen this run never visited is still `open` in
    the ledger, so its defect stays open. `run_id` is provenance for the event log only.

    Idempotent. Running it twice changes nothing the second time, and a finding that flips
    between runs reuses its own defect rather than spawning a duplicate — the fingerprint is the
    key, so "the same problem" means the same thing here as everywhere else.
    """
    from mcp_platform_state import tools

    from apps.workitems.models import WorkItem

    from .models import A11yFinding

    opened: list[str] = []
    closed: list[str] = []
    reopened: list[str] = []
    with tenant_context(tenant_id):
        blocking = {
            finding.fingerprint: finding
            for finding in A11yFinding.objects
            .filter(tenant_id=tenant_id, project_id=project_id,
                    status=A11yFinding.Status.OPEN, outcome="failure",
                    severity__in=sorted(A11Y_BLOCKING))
            .select_related("first_seen_run", "first_seen_run__work_item")
        }
        existing = {
            (item.external_ref or {}).get("a11y_finding"): item
            for item in WorkItem.objects.filter(
                tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT)
            if (item.external_ref or {}).get("a11y_finding")
        }

        # Close what is no longer blocking. "No longer blocking" is a statement about the
        # LEDGER — resolved, or downgraded to needs-review by a later run — never about this
        # run's coverage.
        for fingerprint, item in existing.items():
            if fingerprint not in blocking and item.state != WorkItem.State.DONE:
                item.state = WorkItem.State.DONE
                item.save(update_fields=["state", "updated_at"])
                tools.log_event(tenant_id, "a11y", "a11y.defect.resolved", "work_item",
                                str(item.id), {"finding": fingerprint, "run": str(run_id or "")})
                closed.append(str(item.id))

        for fingerprint in sorted(blocking):
            finding = blocking[fingerprint]
            open_item = existing.get(fingerprint)
            if open_item is None:
                created = WorkItem.objects.create(
                    tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT,
                    parent=_parent_for(finding), title=_title(finding),
                    description=_description(finding), state=WorkItem.State.IN_PROGRESS,
                    external_ref=_external_ref(finding),
                )
                tools.log_event(tenant_id, "a11y", "a11y.defect.opened", "work_item",
                                str(created.id), {"finding": fingerprint,
                                                  "severity": finding.severity,
                                                  "criterion": finding.criterion})
                opened.append(str(created.id))
            elif open_item.state == WorkItem.State.DONE:
                # The same problem came back. The SAME defect reopens — a second one would give
                # a developer two tickets for one fix and lose the history of the first.
                open_item.state = WorkItem.State.IN_PROGRESS
                open_item.description = _description(finding)
                open_item.save(update_fields=["state", "description", "updated_at"])
                tools.log_event(tenant_id, "a11y", "a11y.defect.reopened", "work_item",
                                str(open_item.id), {"finding": fingerprint})
                reopened.append(str(open_item.id))

    return {"opened": opened, "closed": closed, "reopened": reopened,
            "blocking": sorted(blocking)}
