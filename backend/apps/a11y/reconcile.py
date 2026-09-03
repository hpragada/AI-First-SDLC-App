"""Accessibility's own answer to "is anything of mine stranded?".

This exists because of a specific failure the generic run check cannot see. An
audit was judged in full — every element answered — and then stopped dead. The
judging run's own status was `completed` and its workflow had closed cleanly, so
nothing about the *run* was inconsistent. What never happened was the step after
the judging: filing the answers, publishing the merged report, marking the audit
finished. The audit sat in `judging` for good, and the screen said *Checking what
was found* while nothing was checking anything.

So the invariant here is not about runs at all:

    an audit still in `judging`, whose judging run has already finished,
    is an audit nothing is going to move.

The repair is the one the platform already has for the crash path —
`close_unfinished_ai_pass` — which files every unanswered element as `uncertain`,
publishes the merged report and completes the audit. It is idempotent and never
raises, which is exactly what a recovery path needs to be.
"""
from __future__ import annotations

from typing import Any

from apps.runs.models import Run
from apps.tenancy.context import tenant_context

#: A judging run in one of these has finished, whatever the outcome. If the audit
#: is still `judging` while its run is here, the closing step never landed.
_FINISHED_RUN_STATUSES = (
    Run.Status.COMPLETED,
    Run.Status.FAILED,
    Run.Status.REJECTED,
)


def find_stranded(tenant_id: str, cutoff: Any) -> list:
    """Audits stuck in `judging` behind a run that has already finished."""
    from apps.runs.reconcile import Stranded

    from .aipass import _judge_run_for
    from .models import A11yBaselineAudit

    stranded: list = []
    with tenant_context(tenant_id):
        audits = list(
            A11yBaselineAudit.objects.filter(
                tenant_id=tenant_id,
                status=A11yBaselineAudit.Status.JUDGING,
                updated_at__lt=cutoff,
            ).order_by("updated_at")[:5]
        )
        for audit in audits:
            judge_run_id = _judge_run_for(tenant_id, str(audit.id))
            if not judge_run_id:
                # No judging run recorded yet. That is a different problem and
                # guessing at it here would close an audit that never started.
                continue
            run = Run.objects.filter(id=judge_run_id, tenant_id=tenant_id).first()
            if run is None or run.status not in _FINISHED_RUN_STATUSES:
                continue
            stranded.append(
                Stranded(
                    kind="a11y_audit",
                    target_id=str(audit.id),
                    detail=f"judging run finished as {run.status} but the audit was never closed",
                    repair=_closer(tenant_id, judge_run_id),
                )
            )
    return stranded


def _closer(tenant_id: str, judge_run_id: str):
    from .aipass import close_unfinished_ai_pass

    def _repair():
        return close_unfinished_ai_pass(tenant_id=tenant_id, run_id=judge_run_id)

    return _repair
