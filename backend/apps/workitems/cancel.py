"""Human state transitions on a WorkItem — Bugs S.No 140.

The platform moves work items constantly: a run starts one, a merged PR finishes one, a failed
build returns one. What it had no way to express was a person's decision that a piece of work
is *not going to happen* — a duplicate, a defect nobody will fix, a task overtaken by a later
decision. The two things a team could do instead were both wrong. Marking it `done` puts a lie
into every delivery report that counts done items. Leaving it open for ever is how a board
stops being read at all.

So `cancelled` is a state alongside `done`, and this module is the only way in — or back out:
cancelling is the platform's only way to close work that will not happen (there is no delete), so
it has to be undoable, and `cancelled -> proposed` returns a mis-cancelled item to the board.

Three rules shape it, and each exists because of a specific way this could go wrong:

**An allowlist, not any-to-any.** `tools.transition_work_item` accepts any state to any state
because the orchestrator drives it and the orchestrator knows what it is doing. A human-facing
endpoint with that power is a way to put a work item into a state no code will ever move it out
of. Only the transitions below are offered.

**A reason is required to cancel.** Six months later, "why is WI-42 cancelled" has exactly one
place to be answered, and an empty string is not an answer. `done` needs no reason — the work
is the reason.

**Cancelling a blocking defect discloses itself.** The gates read "not terminal" to decide
whether a defect still blocks (`apps.gates.testgate`, `apps.gates.a11ygate`), so cancelling one
RELEASES the gate it was holding — which is the team's decision and is the right behaviour, but
released *silently* it would let "we won't fix this" quietly become "this passed". Every gate
still waiting on this item therefore gets a checklist item naming the cancelled defect and its
reason, which a reviewer has to tick before that gate can be approved. The release and the
disclosure ship together; neither is correct on its own.
"""
from __future__ import annotations

from rest_framework.exceptions import ValidationError

from apps.tenancy.context import tenant_context
from apps.workitems.models import WorkItem

#: The transitions a person may drive through the API, as `from_state -> {to_states}`.
#: Deliberately narrow. Anything not listed is refused with the list, so the refusal teaches.
#:
#: Two shapes only:
#:   - anything not already finished may be cancelled;
#:   - work that is genuinely under way may be marked done by hand, for the cases the
#:     automation cannot see (merged outside the platform, delivered another way).
#: `proposed` and `accepted` cannot jump straight to `done`: an item nobody has started is not
#: something anybody can attest is finished, and that is exactly what `cancelled` is for.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    WorkItem.State.PROPOSED: frozenset({WorkItem.State.CANCELLED}),
    WorkItem.State.ACCEPTED: frozenset({WorkItem.State.CANCELLED}),
    WorkItem.State.IN_PROGRESS: frozenset({WorkItem.State.CANCELLED, WorkItem.State.DONE}),
    WorkItem.State.IN_REVIEW: frozenset({WorkItem.State.CANCELLED, WorkItem.State.DONE}),
    WorkItem.State.BLOCKED: frozenset({WorkItem.State.CANCELLED, WorkItem.State.DONE}),
    # `done` stays terminal. Reopening finished work restarts delivery reporting on something a
    # person has already attested is delivered, which is a different decision from the one below.
    WorkItem.State.DONE: frozenset(),
    # Cancelled work can be picked back up (2026-09-30). This was terminal too, on the reasoning
    # that reopening is "a separate decision with separate consequences" — which was true, and
    # those consequences are now HANDLED rather than avoided: the item returns to `proposed`, and
    # a reopened defect's gate disclosure is withdrawn (`_withdraw_gate_disclosure`). It was
    # terminal because Cancel is the platform's only closure — there is no delete — so a
    # mis-click was permanent.
    #
    # `proposed` and nothing else. A cancelled item's run is long finished, so there is no
    # `in_progress` or `in_review` to return to: those states would name a phase with no live run
    # behind it. Back on the board as a draft is the one thing that is honestly true of work
    # somebody has just decided to pick up again.
    WorkItem.State.CANCELLED: frozenset({WorkItem.State.PROPOSED}),
}

#: Condition key prefix for the "I have read what was cancelled" checklist item. One condition
#: per cancelled defect rather than one rolling summary: each is ticked once and stays ticked,
#: and a defect cancelled later arrives as its own unticked item instead of silently clearing
#: an acknowledgement a reviewer already made.
ACK_CONDITION_PREFIX = "cancelled_defect_reviewed"


def _label(item: WorkItem, reason: str, actor_name: str) -> str:
    number = f"WI-{item.number}" if item.number else str(item.id)[:8]
    who = f" by {actor_name}" if actor_name else ""
    return (f"Reviewed the cancelled defect {number} — {item.title or 'untitled'} "
            f"(cancelled{who}: {reason})")


def _actor_name(tenant_id: str, actor_id: str | None) -> str:
    if not actor_id:
        return ""
    from apps.tenancy.models import User

    user = User.objects.filter(id=actor_id, tenant_id=tenant_id).first()
    return (user.name or user.email) if user else ""


def _disclose_to_pending_gates(item: WorkItem, *, tenant_id, reason, actor_id) -> list[str]:
    """Put an acknowledgement on every gate this cancellation just unblocked.

    Scoped to approvals still PENDING on the item's parent — the story a defect hangs off is
    where its gate lives. An already-decided gate is left alone: the decision is history, and
    rewriting its checklist after the fact would misrepresent what the approver saw.

    Best-effort by design. A cancellation must not fail because a gate could not be annotated;
    the ledger event below is written either way, and this returns what it managed to mark so
    the caller can say so.
    """
    if item.type != WorkItem.Type.DEFECT or item.parent_id is None:
        return []
    from apps.gates.models import Approval

    label = _label(item, reason, _actor_name(tenant_id, actor_id))
    key = f"{ACK_CONDITION_PREFIX}:{item.id}"
    marked: list[str] = []
    approvals = Approval.objects.filter(
        tenant_id=tenant_id, work_item_id=item.parent_id,
        decision=Approval.Decision.PENDING,
    )
    for approval in approvals:
        conditions = list(approval.conditions or [])
        if any(c.get("key") == key for c in conditions):
            continue                      # already disclosed — cancelling twice is one fact
        conditions.append({
            "key": key, "label": label, "required": True, "satisfied": False,
            # NOT `derived`: a person attests this, and `_merge_conditions` only accepts a
            # reviewer's `satisfied` on a condition that is not derived.
            "detail": reason,
        })
        approval.conditions = conditions
        approval.save(update_fields=["conditions", "updated_at"])
        marked.append(str(approval.id))
    return marked


def _withdraw_gate_disclosure(item: WorkItem, *, tenant_id) -> list[str]:
    """Take the "I have read what was cancelled" item back off, when a defect is reopened.

    The exact mirror of `_disclose_to_pending_gates`, and it exists for the same reason that one
    does. Cancelling a blocking defect RELEASES the gate it was holding shut and leaves the
    reviewer a required checklist item reading "Reviewed the cancelled defect WI-9 — ...".
    Reopening the defect makes that sentence false twice over: the defect is not cancelled, and
    the gate is blocked again on its own account, because the gates decide what still blocks by
    reading `WorkItem.TERMINAL_STATES`. Left in place the condition would be a SECOND, stale
    block — one no reviewer could honestly tick, on a gate that is already correctly shut.

    The release and its disclosure shipped together because neither is correct alone; the same
    holds in reverse, so the reopen and this withdrawal ship together too.

    Scoped to PENDING approvals on the parent, like its mirror: a decided gate is history and is
    not rewritten after the fact. Best-effort by design — a reopen must not fail because a gate
    could not be tidied. Returns the approvals it changed so the caller can say what moved.
    """
    if item.type != WorkItem.Type.DEFECT or item.parent_id is None:
        return []
    from apps.gates.models import Approval

    key = f"{ACK_CONDITION_PREFIX}:{item.id}"
    cleared: list[str] = []
    approvals = Approval.objects.filter(
        tenant_id=tenant_id, work_item_id=item.parent_id,
        decision=Approval.Decision.PENDING,
    )
    for approval in approvals:
        conditions = list(approval.conditions or [])
        kept = [c for c in conditions if c.get("key") != key]
        if len(kept) == len(conditions):
            continue                      # this gate never carried the disclosure
        approval.conditions = kept
        approval.save(update_fields=["conditions", "updated_at"])
        cleared.append(str(approval.id))
    return cleared


def transition(*, tenant_id, work_item_id, to_state, reason="", actor_id=None) -> dict:
    """Apply a human transition. Raises `ValidationError` (400) on anything not allowed.

    Returns `{work_item, from_state, to_state, gates_notified}`. The caller does the role check;
    this does the rules.
    """
    reason = (reason or "").strip()
    with tenant_context(tenant_id):
        item = WorkItem.objects.get(id=work_item_id, tenant_id=tenant_id)
        from_state = item.state

        if to_state not in WorkItem.State.values:
            raise ValidationError({"to_state": ["That isn't a column on this board."]})
        allowed = ALLOWED_TRANSITIONS.get(from_state, frozenset())
        if to_state not in allowed:
            # Screen Words group 5. Dragging a card on a board someone else has moved on showed
            # "A in_progress work item cannot be moved to done." — three stored words and a
            # broken article. The states are columns the reader can see, so they get the column
            # names, and the list of where it CAN go is the useful half.
            from apps.labels import work_item_state_label

            offer = (
                ", ".join(work_item_state_label(s) for s in sorted(allowed))
                if allowed else ""
            )
            where = (
                f" From here it can go to: {offer}." if offer
                else " It can't be moved anywhere from here."
            )
            raise ValidationError({"to_state": [
                f"This work item is {work_item_state_label(from_state).lower()}, so it can't "
                f"move to {work_item_state_label(to_state).lower()}.{where}"
            ]})
        if to_state == WorkItem.State.CANCELLED and not reason:
            raise ValidationError({"reason": [
                "Say why this is being cancelled — it is the only record of the decision."
            ]})

        item.state = to_state
        item.save(update_fields=["state", "updated_at"])

        gates: list[str] = []
        if to_state == WorkItem.State.CANCELLED:
            gates = _disclose_to_pending_gates(
                item, tenant_id=tenant_id, reason=reason, actor_id=actor_id)
        elif from_state == WorkItem.State.CANCELLED:
            # The only move out of `cancelled` is to `proposed` (see ALLOWED_TRANSITIONS), so
            # this is a reopen and nothing else can reach here.
            gates = _withdraw_gate_disclosure(item, tenant_id=tenant_id)

        from mcp_platform_state import tools

        tools.log_event(
            tenant_id, str(actor_id) if actor_id else "user", "workitem.transitioned",
            "work_item", str(item.id),
            {"to_state": to_state, "from_state": from_state, "via": "api_transition",
             "reason": reason, "gates_notified": gates},
        )
        return {"work_item": item, "from_state": from_state, "to_state": to_state,
                "gates_notified": gates}
