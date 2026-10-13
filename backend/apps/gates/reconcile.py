"""Find merge gates whose pull request was already merged elsewhere (Bugs S.No 88).

The webhook is the fast path, and it is not a guarantee: a delivery can be missed, the
endpoint can be unreachable, the secret can be wrong, and a webhook that fails is never
redelivered because the platform writes its dedup row *before* the handler runs. So the
webhook cannot be the only way this is ever noticed.

It is also the only thing that will recover a run stranded before any of this existed — no
webhook fires retroactively for a merge that happened last week.

**This annotates. It never decides.** See apps/gates/external_merge for why that distinction
carries real security weight rather than being process for its own sake.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.runs.models import Run

from .external_merge import MERGE_GATE_TYPE, note_external_merge

#: Every candidate costs one network call to the code host, unlike the other reconciler checks
#: which are local queries. So: leave a gate alone for a good while first (a reviewer who is
#: simply thinking about it is not stranded), and look at very few per pass.
DEFAULT_MIN_AGE_SECONDS = 3600
DEFAULT_MAX_PER_PASS = 3


def find_stranded(tenant_id: str, cutoff: Any) -> list:
    """Pending merge gates on runs still awaiting a gate whose PR is already merged.

    Same shape as the other capability checks (`apps.runs.reconcile.Stranded`), so it can be
    registered in `_CAPABILITY_CHECKS` if that ever becomes the right home. It deliberately is
    NOT registered today: those checks run on the run-list read, and this one makes a network
    call per candidate — the cost belongs on the screen that wants the answer, so the Gates
    read calls `sweep` below instead.
    """
    from apps.gates.models import Approval
    from apps.runs.reconcile import Stranded
    from apps.tenancy.context import tenant_context

    stranded: list = []
    with tenant_context(tenant_id):
        approvals = list(
            Approval.objects.filter(
                tenant_id=tenant_id,
                gate_type=MERGE_GATE_TYPE,
                decision=Approval.Decision.PENDING,
                external_merge__isnull=True,          # already noted → nothing to do
                updated_at__lt=cutoff,
                run__status=Run.Status.AWAITING_GATE,
            )
            .select_related("run")
            .order_by("updated_at")[:DEFAULT_MAX_PER_PASS]
        )
        for approval in approvals:
            merged = _merged_pull_request(tenant_id, approval.run)
            if merged is None:
                # Could not tell — no PR pointer, no connector, or the code host did not
                # answer. Never treat that as "merged"; the gate is left exactly as it is.
                continue
            stranded.append(
                Stranded(
                    kind="merge_gate",
                    target_id=str(approval.id),
                    detail=f"pull request {merged['pr_ref']} was merged outside the platform",
                    repair=_annotator(tenant_id, approval.run, merged),
                )
            )
    return stranded


def _merged_pull_request(tenant_id: str, run) -> dict | None:
    """Ask the code host whether this run's PR is merged. None means "could not tell"."""
    from apps.registry.models import Artifact
    from orchestration.build_activities import _is_pr_ref

    artifact = next(
        (a for a in Artifact.objects.filter(run_id=run.id, tenant_id=tenant_id, type="code")
           .order_by("created_at")
         if _is_pr_ref(a.external_ref)),
        None,
    )
    if artifact is None:
        return None
    ref = artifact.external_ref or {}
    pr_ref = f"{ref.get('repo')}#{ref.get('number')}"
    try:
        from integrations.registry import get_capability

        pull = get_capability(tenant_id, "codehost").get_pull_request(pr_ref=pr_ref)
    except Exception:  # noqa: BLE001 — a safety net that raises is not a safety net
        return None
    if not getattr(pull, "merged", False):
        return None
    return {
        "pr_ref": pr_ref,
        "merged_by": getattr(pull, "merged_by", "") or "",
        "merged_at": str(getattr(pull, "merged_at", "") or ""),
    }


def _annotator(tenant_id: str, run, merged: dict):
    repo, _, number = merged["pr_ref"].partition("#")

    def _repair():
        return note_external_merge(
            tenant_id, run, repo=repo, number=number,
            merged_by=merged["merged_by"], merged_at=merged["merged_at"],
            detected_by="reconciler",
        )

    return _repair


def sweep(tenant_id: str, *, min_age_seconds: int = DEFAULT_MIN_AGE_SECONDS) -> dict:
    """Run the check and write the notes. Never raises — it rides on a page load."""
    out: dict = {"checked": 0, "noted": []}
    try:
        cutoff = timezone.now() - timedelta(seconds=min_age_seconds)
        for item in find_stranded(tenant_id, cutoff):
            out["checked"] += 1
            if item.repair():
                out["noted"].append(item.target_id)
    except Exception as exc:  # noqa: BLE001 — see the docstring
        out["error"] = str(exc)[:300]
    return out
