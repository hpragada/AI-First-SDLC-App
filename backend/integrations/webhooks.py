"""Signed Git-webhook ingestion + reconciliation (Phase-2 §7).

The **primary collaboration path in companion mode**: a developer works the worktree branch by
hand (or after a takeover) and pushes; GitHub posts a **signed** webhook the platform verifies,
**dedups** (WebhookDelivery), and **reconciles** into platform state — register-don't-recreate:
human commits update the `code` Artifact's `external_ref.sha` pointer and log an Event; they
never overwrite the artifact or duplicate it. Bodies are read-through (#3) — the diff lives in
git, the platform keeps pointers/provenance. (P4 live drift gates build on this; P2 only
reconciles.)

Reconcilers handled: `push` (sha pointer), `pull_request` (merged/closed → WorkItem), `status`
(CI round-trips into the ledger).
"""
from __future__ import annotations

import hashlib
import hmac

from mcp_platform_state import tools

from apps.tenancy.context import tenant_context

PROVIDER = "github"
# The build saga's human merge gate (orchestration.build_types.BuildInput.gate_type default).
# A merged-PR webhook must not transition a WorkItem past a gate of this type while it is still
# PENDING — the control plane, not the webhook, owns that transition.
_MERGE_GATE_TYPE = "merge_gate"


def verify_github_signature(secret: str, body: bytes, signature_header: str | None) -> bool:
    """Constant-time HMAC-SHA256 of GitHub's `X-Hub-Signature-256` over the **raw** body.
    A missing secret or a malformed/absent header is a verification failure (never trusted)."""
    if not secret or not signature_header or not signature_header.startswith("sha256="):
        return False
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"sha256={digest}", signature_header)


def _branch(ref: str) -> str:
    return ref.split("refs/heads/", 1)[-1] if ref else ""


def reconcile_github(*, tenant_id: str, event: str, delivery_id: str, payload: dict) -> dict:
    """Idempotent ingest: dedup by `delivery_id` (a redelivery is a no-op), then reconcile.
    The WebhookDelivery row is the dedup ledger; the Event Ledger records what changed."""
    from apps.integrations.models import WebhookDelivery

    with tenant_context(tenant_id):
        delivery, created = WebhookDelivery.objects.get_or_create(
            tenant_id=tenant_id, provider=PROVIDER, delivery_id=delivery_id or "",
            defaults={"event": event},
        )
    if not created:
        return {"status": "duplicate", "event": delivery.event, "delivery_id": delivery_id}

    handler = _HANDLERS.get(event)
    if handler is None:
        _set_status(tenant_id, delivery.id, WebhookDelivery.Status.IGNORED)
        return {"status": "ignored", "event": event}

    try:
        result = handler(tenant_id, payload or {})
    except Exception:
        try:
            _set_status(tenant_id, delivery.id, WebhookDelivery.Status.FAILED)
        except Exception:  # noqa: BLE001 — never mask the original handler error
            pass
        raise
    _set_status(tenant_id, delivery.id, WebhookDelivery.Status.PROCESSED)
    return {"status": "processed", "event": event, **result}


def _set_status(tenant_id, delivery_id, status) -> None:
    from apps.integrations.models import WebhookDelivery

    with tenant_context(tenant_id):
        WebhookDelivery.objects.filter(id=delivery_id, tenant_id=tenant_id).update(status=status)


def _code_artifacts(tenant_id, *, head=None, number=None, repo=None) -> list:
    """The `code` artifacts (PR pointers) matching a branch head and/or PR number for a repo."""
    from apps.registry.models import Artifact

    with tenant_context(tenant_id):
        qs = Artifact.objects.filter(tenant_id=tenant_id, type="code")
        if head is not None:
            qs = qs.filter(external_ref__head=head)
        if number is not None:
            qs = qs.filter(external_ref__number=number)
        if repo:
            qs = qs.filter(external_ref__repo=repo)
        return list(qs)


def _reconcile_push(tenant_id: str, payload: dict) -> dict:
    """A human commit on the worktree branch → update the `code` pointer's sha (don't recreate)."""
    branch = _branch(payload.get("ref", ""))
    after = payload.get("after", "")
    repo = (payload.get("repository") or {}).get("full_name", "")
    updated = []
    for artifact in _code_artifacts(tenant_id, head=branch, repo=repo):
        ext = dict(artifact.external_ref or {})
        ext["sha"] = after                      # pointer moves; the artifact is not duplicated
        tools.update_artifact(tenant_id, str(artifact.id), external_ref=ext, content_hash=after)
        updated.append(str(artifact.id))
    # Event.target_id is a UUID; the branch/sha live in the payload (git identifiers, #3).
    tools.log_event(
        tenant_id, "webhook", "webhook.push_reconciled", "branch", None,
        {"repo": repo, "branch": branch, "sha": after, "artifacts": updated,
         "commits": len(payload.get("commits") or [])},
    )
    # P4 live drift (D6): a push past a registered contract's source_commit opens a drift gate.
    # Best-effort — a detection hiccup never fails the (already-succeeded) pointer reconcile.
    drifts: list[str] = []
    try:
        from .drift import detect_push_contract_drift

        drifts = [d["drift_id"] for d in detect_push_contract_drift(
            tenant_id=tenant_id, repo=repo, head_sha=after) if d.get("drift")]
    except Exception:  # noqa: BLE001
        drifts = []
    return {"reconciled": len(updated), "branch": branch, "sha": after, "drift_records": drifts}


def _reconcile_pull_request(tenant_id: str, payload: dict) -> dict:
    """A human-merged/closed PR → transition the WorkItem (merge is the gated SoR write; a
    developer merging by hand is reconciled the same way the saga's merge would be)."""
    from apps.gates.models import Approval
    from apps.registry.models import Artifact
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    action = payload.get("action", "")
    pr = payload.get("pull_request") or {}
    number = pr.get("number")
    merged = bool(pr.get("merged") or pr.get("merged_at"))
    repo = (payload.get("repository") or {}).get("full_name", "")
    # WHO merged it, which GitHub sends on every one of these and we threw away (Bugs S.No 88).
    # `merged_by` is the account that pressed the button; `sender` is whoever the delivery is
    # attributed to. They differ for an auto-merge, so keep the first and fall back to the
    # second rather than inventing a single "user".
    merged_by = ((pr.get("merged_by") or {}).get("login")
                 or (payload.get("sender") or {}).get("login") or "")
    merged_at = pr.get("merged_at") or ""

    artifacts = _code_artifacts(tenant_id, number=number, repo=repo)
    if not artifacts:
        # `Event.target_id` is a UUID column and a PR number is not one — passing `str(number)`
        # here raised on save, so the one path that reports an unmatched PR crashed instead of
        # reporting it. Same convention as the branch/commit events above: no target id, and the
        # git identifier travels in the payload (#3).
        tools.log_event(tenant_id, "webhook", "webhook.pr_unmatched", "pull_request",
                        None, {"repo": repo, "action": action, "number": number})
        return {"reconciled": 0, "action": action, "number": number}

    work_items: list[str] = []
    for artifact in artifacts:
        if action == "closed" and merged:
            tools.update_artifact(tenant_id, str(artifact.id), status=Artifact.Status.PUBLISHED)
            with tenant_context(tenant_id):
                run = Run.objects.filter(id=artifact.run_id, tenant_id=tenant_id).first()
                # A merged-PR webhook must NOT bypass an unapproved control-plane gate
                # (non-negotiable #2/#5). If the saga is still holding this run at an un-decided
                # merge gate, the saga owns the WorkItem transition — the webhook only records
                # that the PR merged. Marking the WorkItem done here was the root cause of the
                # "state=done while the run is still awaiting_gate, with no workitem.transitioned
                # event" mislabel: this path set state directly and only logged webhook.pr_merged.
                gate_pending = run is not None and Approval.objects.filter(
                    run_id=run.id, tenant_id=tenant_id,
                    gate_type=_MERGE_GATE_TYPE, decision=Approval.Decision.PENDING).exists()
            if run is not None and gate_pending:
                # The guard above is correct and stays: a webhook must never move the work item
                # past a gate a human has not decided. But saying nothing left the run waiting
                # for ever for an approval of a merge that had already happened, with nothing on
                # the reviewer's screen to explain it (Bugs S.No 88). Leave a NOTE instead.
                #
                # Best-effort on purpose. The dedup row for a delivery is written BEFORE this
                # handler runs, so a failed webhook is never redelivered — if annotating throws,
                # the pointer reconcile above has already succeeded and must not be undone. The
                # sweep in apps/gates/reconcile.py is the real safety net.
                try:
                    from apps.gates.external_merge import note_external_merge

                    note_external_merge(
                        tenant_id, run, repo=repo, number=number,
                        merged_by=merged_by, merged_at=merged_at, detected_by="webhook",
                    )
                except Exception:  # noqa: BLE001 — see above
                    pass
            if run is not None and not gate_pending:
                moved = tools.transition_work_item(
                    tenant_id, str(run.work_item_id), WorkItem.State.DONE)
                # Always emit the canonical transition event so state=done is never orphaned in
                # the audit trail (the missing-event half of the mislabel bug) — but only when
                # the item ACTUALLY moved. A cancelled item is left alone (S.No 140), and
                # logging "transitioned to done" over the top of that would put a merge in the
                # audit trail that never happened.
                if moved.get("state") == WorkItem.State.DONE:
                    tools.log_event(tenant_id, "orchestrator", "workitem.transitioned",
                                    "work_item", str(run.work_item_id),
                                    {"to_state": WorkItem.State.DONE, "via": "webhook_pr_merge"})
                    work_items.append(str(run.work_item_id))

    name = ("webhook.pr_merged" if (action == "closed" and merged)
            else "webhook.pr_closed" if action == "closed" else "webhook.pr_event")
    tools.log_event(tenant_id, "webhook", name, "work_item",
                    work_items[0] if work_items else None,
                    {"repo": repo, "number": number, "action": action, "merged": merged,
                     "work_items": work_items})
    return {"reconciled": len(artifacts), "action": action, "merged": merged,
            "work_items": work_items}


def _reconcile_status(tenant_id: str, payload: dict) -> dict:
    """A CI commit-status round-trips into the Event Ledger (the platform tracks, never runs CI)."""
    sha = payload.get("sha", "")
    state = payload.get("state", "")
    context = payload.get("context", "")
    repo = (payload.get("repository") or {}).get("full_name", "")
    tools.log_event(tenant_id, "webhook", "webhook.ci_status", "commit", None,
                    {"repo": repo, "sha": sha, "state": state, "context": context})
    return {"sha": sha, "state": state, "context": context}


_HANDLERS = {
    "push": _reconcile_push,
    "pull_request": _reconcile_pull_request,
    "status": _reconcile_status,
}
