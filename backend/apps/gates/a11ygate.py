"""Accessibility gate condition — the test gate's WCAG 2.2 rule (QA-15).

Everything the accessibility build has produced so far *observes*: a failure is scanned, judged,
recorded in the ledger, written into the report and turned into a tracked defect — and the work
carries on regardless. This is the piece that stops it.

**Derived, never reviewer-attested (R3).** `testgate.py` says why in one line: *"a reviewer can
never tick past a red suite."* The WCAG checklist on the **design** gate is reviewer-attested and
that is right — "does the focus order follow the reading order?" is a judgement call. "There are
three Level A failures on /checkout" is not. So this is computed at decide time and
`services._merge_conditions` refuses any attestation of it.

**It reads the defects, not the ledger.** `testgate.py`'s own reasoning applies unchanged: *"the
defect loopback already computes this set precisely … we read that reconciliation rather than
recompute a parallel (and driftable) notion of failing."* QA-14 already reconciles accessibility
findings into defects using the QA-08 policy, so reading those defects gives one definition of
"failing" and honours the policy for free. Scoping follows from it too — a defect hangs off the
work item where the problem was **first seen**, so a story's gate blocks on that story's
problems rather than on every open accessibility failure in the project.

**Silence is not a pass, and it is not a block either.** Three states that all look like "no
failures" are deliberately told apart:

  - findings were judged and none block            ⇒ satisfied, no detail (as the test gate does)
  - elements were captured but never got a verdict ⇒ **blocked**, "the check did not complete"
    (the judge was unavailable, or the run hit its cap) — the policy's `block_on_incomplete_run`
    is the switch and this is the only thing that reads it
  - no accessibility check ever ran for this item  ⇒ satisfied, **but the condition says so**

That last one is a deliberate decision rather than an oversight. Blocking it would make the gate
unusable on work with no UI at all; staying quiet about it is the exact failure D-A11Y-3 exists
to prevent — an incomplete check that reads as a clean one. So it passes and says why, and the
sentence travels on the approval where a reviewer sees it.

**Inherited debt is a fourth state, and it was silent until QA-19.** An audit of an application
the platform never built (QA-17) produces problems that belong to no piece of work — nobody was
building anything — so they hang off the project's accessibility backlog rather than a story,
and the scoping above looked straight past them. That is the RIGHT default: a team should not
have their pipeline stopped on day one by two hundred problems they inherited. But it was true
by accident of a filter rather than by decision, nothing said so, and nothing tested it — so the
next widening of that filter would have turned a health check into a pipeline stop for every
brownfield client with no warning. It is now a decision (`policy.block_on_baseline_debt`, off by
default), it is asserted, and — crucially — while it is off the gate **passes and says the debt
is there**. A green gate on an application with 47 known problems must not look identical to a
green gate on one with none.

**And a fifth: findings that are tracked but may never block (QA-22).** The eight journey checks
operate the application with a keyboard rather than reading a still page, and that agent has not
yet been proven against a real one — so its findings are recorded, reported, ranked and ticketed
like any other, and are barred from failing this gate. Two paths had to be closed for that to be
true, and only one of them was obvious; the second is `unanswered_checks`, where the word
`uncertain` meant two different things on either side of the seam (D-A11Y-84). As with debt, the
gate **passes and says they are there** — the reviewer approving the story is the person who
most needs to know, and nothing else puts it in front of them. There is no setting: see
`policy.ADVISORY_CHECKERS` for why not.
"""
from __future__ import annotations

A11Y_GATE_KEY = "no_blocking_a11y_failures"

#: Phases whose gate carries the accessibility rule. The testing gate is where the test report
#: is accepted (§5) and where the blocking-test rule already binds, so accessibility binds
#: there too. Whether the **merge** gate should also carry it is a product decision —
#: `testgate.py` explicitly declined to make that call for itself, and neither does this.
_A11Y_GATED_PHASES = {"testing"}

#: How many findings the `detail` line names before it summarises the rest. A reviewer needs to
#: know what to fix, not to read the whole ledger through a gate error.
_MAX_NAMED = 5

NOT_CHECKED_DETAIL = (
    "no accessibility check has run for this work item yet, so this says nothing about whether "
    "it is accessible"
)


def a11y_condition() -> dict:
    """A fresh (unsatisfied) accessibility condition.

    `derived` marks it platform-evaluated: `conditions.refresh_derived` routes it here by key
    and `services._merge_conditions` refuses a reviewer's `satisfied` update on it. Seeded
    unsatisfied like every derived condition, which is safe only because it has a registered
    evaluator — see the QA-15a note in `conditions.py`.
    """
    return {
        "key": A11Y_GATE_KEY,
        "label": (
            "No unresolved accessibility failure — every WCAG 2.2 finding that blocks under "
            "this project's accessibility policy is fixed"
        ),
        "required": True,
        "satisfied": False,
        "derived": True,
    }


def conditions_for_a11y_phase(phase: str) -> list[dict]:
    """The accessibility condition for the test gate, empty for every other phase."""
    return [a11y_condition()] if phase in _A11Y_GATED_PHASES else []


def _a11y_refs(*, tenant_id, work_item_id) -> list[dict]:
    """Every still-open accessibility defect on this work item, advisory ones included.

    Scoped on `a11y_finding`, which is QA-14's own key. Test defects carry `test_ref` and
    security defects carry `finding`; three families share this table and each reconciliation
    stays inside its own key (D-A11Y-29), so this can never be held shut by a failing test or
    an open security finding — those have their own gates.
    """
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        defects = WorkItem.objects.filter(
            tenant_id=tenant_id, parent_id=work_item_id, type=WorkItem.Type.DEFECT,
        # `TERMINAL_STATES`, not `DONE` alone (S.No 140). Team decision: cancelling a defect
        # RELEASES the gate it was blocking — a defect nobody will fix must not hold a story
        # shut for ever. The disclosure that makes that safe is the acknowledgement condition
        # `apps.workitems.cancel` puts on the pending approval: the gate opens, but a reviewer
        # has to read what was cancelled and say so before it does.
        ).exclude(state__in=WorkItem.TERMINAL_STATES)
        refs = [
            dict(item.external_ref or {})
            for item in defects
            if (item.external_ref or {}).get("a11y_finding")
        ]
    return sorted(refs, key=lambda r: (r.get("route", ""), r.get("criterion", ""),
                                       r.get("selector", "")))


def open_a11y_defects(*, tenant_id, work_item_id) -> list[dict]:
    """The ones that may fail this gate — everything above except the advisory ones (QA-22).

    Read from the ticket's own `advisory` stamp rather than recomputed here, so the gate and the
    tracker cannot come to different conclusions about the same defect.
    """
    return [ref for ref in _a11y_refs(tenant_id=tenant_id, work_item_id=work_item_id)
            if not ref.get("advisory")]


def advisory_a11y_defects(*, tenant_id, work_item_id) -> list[dict]:
    """The tracked-but-never-blocking ones, so the gate can say they are there.

    A green gate on a story whose keyboard journey found a focus trap must not look identical
    to a green gate on one that found nothing — the same rule QA-19 applies to inherited debt,
    and the same rule D-A11Y-3 states for every other silence in this build.
    """
    return [ref for ref in _a11y_refs(tenant_id=tenant_id, work_item_id=work_item_id)
            if ref.get("advisory")]


def baseline_debt(*, tenant_id, project_id) -> list[dict]:
    """The `external_ref`s of this project's still-open **inherited** accessibility defects.

    "Inherited" means exactly one thing here, and it needs no new data to say it: the defect
    hangs off the project's accessibility backlog rather than a story (QA-18). A defect lands
    there precisely when no run could be attributed to it — an audit of an already-built
    application, or a CI post — which is the same set as "this was not caused by a piece of
    work we can point at".

    Project-wide on purpose. A story's own failures are `open_a11y_defects`' business and stay
    scoped to that story; this is the debt the project carries, and enforcing it is a decision
    about the project rather than about any one story.
    """
    from apps.a11y.backlog import BACKLOG_STREAM
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        defects = WorkItem.objects.filter(
            tenant_id=tenant_id, project_id=project_id, type=WorkItem.Type.DEFECT,
            parent__feature_stream=BACKLOG_STREAM,
        # `TERMINAL_STATES`, not `DONE` alone (S.No 140). Team decision: cancelling a defect
        # RELEASES the gate it was blocking — a defect nobody will fix must not hold a story
        # shut for ever. The disclosure that makes that safe is the acknowledgement condition
        # `apps.workitems.cancel` puts on the pending approval: the gate opens, but a reviewer
        # has to read what was cancelled and say so before it does.
        ).exclude(state__in=WorkItem.TERMINAL_STATES)
        refs = [
            dict(item.external_ref or {})
            for item in defects
            if (item.external_ref or {}).get("a11y_finding")
        ]
    return sorted(refs, key=lambda r: (r.get("priority") or 10**6, r.get("route", ""),
                                       r.get("criterion", "")))


def unanswered_checks(*, tenant_id, project_id, work_item_id) -> list:
    """Open findings where the judge gave **no answer at all**.

    The discriminator is `verdict`, and it matters: a judgment the platform decided was too
    unsure to act on still has a verdict of `pass`/`fail` and belongs in the review queue, never
    at a gate (QA-06's guardrail, and the backlog's "low-confidence findings never block"). A
    verdict of `uncertain` is the other thing entirely — nobody answered, because the judge was
    unavailable or the run hit its cap — and treating that as "no problems found" is exactly how
    an incomplete check comes to read as a clean one.

    **The journey checks are excluded, and this was a live bug (QA-22, D-A11Y-84).** For them
    `uncertain` means the opposite of what this function reads it as. Their agent body is
    explicit — *"If you could not tell, say `uncertain`: it routes to a person and is a
    first-class answer here, not a failure to answer"* — because several of these criteria turn
    on judgement calls specialists genuinely dispute. So one word carried two meanings across
    the seam between QA-20 and this gate, and the consequence ran backwards: an agent that was
    **sure** about a trap blocked through the defect above, and an agent that was **honest about
    not being sure** blocked through here. This one defaulted to on, and the message it produced
    — "no verdict was recorded" — was not even true. Silence and "I looked and cannot tell" are
    different facts, and this function is only ever about the first.
    """
    from apps.a11y.models import A11yFinding
    from apps.a11y.policy import ADVISORY_CHECKERS
    from apps.tenancy.context import tenant_context
    from integrations.types import A11Y_UNCERTAIN

    with tenant_context(tenant_id):
        return list(
            A11yFinding.objects.filter(
                tenant_id=tenant_id, project_id=project_id,
                status=A11yFinding.Status.OPEN, verdict=A11Y_UNCERTAIN,
                last_seen_run__work_item_id=work_item_id,
            )
            .exclude(checker__in=sorted(ADVISORY_CHECKERS))
            # **A finding a person has ruled on has been answered** (QA-23). This function is
            # only ever about "nobody answered", and once a reviewer has looked at the element
            # and said yes or no, that sentence is no longer true — leaving it here would have
            # the gate quoting an unanswered check forever, at the exact people who answered
            # it. What the answer WAS still counts, through the ordinary path: a confirmed
            # finding becomes a `failure` and blocks as an open a11y defect if its severity
            # clears the project's bar. Only the "we never got an answer" claim is dropped.
            .exclude(adjudication__in=[A11yFinding.Adjudication.CONFIRMED,
                                       A11yFinding.Adjudication.REJECTED])
        )


def has_been_checked(*, tenant_id, project_id, work_item_id) -> bool:
    """Whether any screen was ever scanned for this work item.

    Reads `A11yScreenScan` rather than the findings, because a screen that was scanned and came
    back clean produces no findings — and "checked, nothing found" must not be indistinguishable
    from "never checked". The scan row is written on every ingest, before any judging, so it is
    the earliest and most reliable evidence that the platform actually looked.
    """
    from apps.a11y.models import A11yScreenScan
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return A11yScreenScan.objects.filter(
            tenant_id=tenant_id, project_id=project_id,
            run__work_item_id=work_item_id,
        ).exists()


def _project_of(tenant_id, work_item_id, given):
    """The project this gate belongs to — from the context, or from the work item itself.

    `decide_gate` always supplies it. The fallback is for any caller that does not (a unit test,
    a future gate opened outside a run): looking it up beats evaluating half the rule.
    """
    if given:
        return str(given)
    from apps.tenancy.context import tenant_context
    from apps.workitems.models import WorkItem

    with tenant_context(tenant_id):
        item = (WorkItem.objects
                .filter(id=work_item_id, tenant_id=tenant_id).only("project_id").first())
    return str(item.project_id) if item else None


def _describe(ref: dict) -> str:
    where = ref.get("selector") or ref.get("route") or "this page"
    return f"{ref.get('criterion') or 'WCAG'} on {ref.get('route') or 'unknown screen'} ({where})"


def _named(items: list[str]) -> str:
    """The first few, then a count — a gate error is not a place to print a ledger."""
    if len(items) <= _MAX_NAMED:
        return "; ".join(items)
    rest = len(items) - _MAX_NAMED
    return "; ".join(items[:_MAX_NAMED]) + f"; and {rest} more"


def _result(condition: dict, satisfied: bool, detail: str) -> dict:
    updated = {**condition, "satisfied": satisfied}
    if detail:
        updated["detail"] = detail
    else:
        # Drop a stale reason when the gate has since gone green, exactly as the test gate does —
        # otherwise a reviewer reads last week's failures on a clean gate.
        updated.pop("detail", None)
    return updated


def evaluate(condition: dict, context) -> dict:
    """Re-evaluate the accessibility condition from live state; returns an updated copy.

    `detail` names the findings holding the gate shut, so the reviewer is told *why* rather than
    just "no" — `decide_gate` puts it in the error, because a blocked approval persists nothing
    and the reason would otherwise be lost.

    Never raises. A gate must be decidable: if the project's policy cannot be read, the
    documented default applies and the reason is logged (QA-08's `policy_or_default` rule).
    """
    if condition.get("key") != A11Y_GATE_KEY:
        return condition

    from apps.a11y.policy import default_policy, policy_or_default

    tenant_id, work_item_id = context.tenant_id, context.work_item_id
    project_id = _project_of(tenant_id, work_item_id, context.project_id)

    # 1. A real, still-open failure. Read from QA-14's reconciliation so there is exactly one
    #    definition of "blocking", already filtered by the project's policy.
    if blocking := open_a11y_defects(tenant_id=tenant_id, work_item_id=work_item_id):
        return _result(condition, False, (
            f"{len(blocking)} accessibility failure(s) still open: "
            f"{_named([_describe(ref) for ref in blocking])}"
        ))

    if project_id is None:                                   # pragma: no cover - guarded below
        return _result(condition, True, NOT_CHECKED_DETAIL)

    policy, error = policy_or_default(tenant_id, project_id)
    if error:
        from mcp_platform_state import tools

        policy = default_policy()
        tools.log_event(tenant_id, "gates", "a11y.policy.unreadable", "project",
                        str(project_id), {"error": error, "gate": A11Y_GATE_KEY})

    # 2. Nothing is blocking — but was everything actually answered? An element captured and
    #    never judged is not a pass, and the project says whether that stops the gate.
    unanswered = unanswered_checks(tenant_id=tenant_id, project_id=project_id,
                                   work_item_id=work_item_id)
    if unanswered and policy["gate"]["block_on_incomplete_run"]:
        return _result(condition, False, (
            f"the accessibility check did not complete: {len(unanswered)} element(s) were "
            f"selected for a check and no verdict was recorded, so nothing says whether they "
            f"are accessible — "
            f"{_named([f'{f.route} ({f.selector or f.criterion})' for f in unanswered])}"
        ))

    # 3. The problems this application came with (QA-19). Blocking only where the project has
    #    said they should — and never silent when they have not, because a green gate on an
    #    application with known problems must not read like a green gate on a clean one.
    from apps.a11y.policy import enforces_baseline

    debt = baseline_debt(tenant_id=tenant_id, project_id=project_id)
    if debt and enforces_baseline(policy):
        return _result(condition, False, (
            f"{len(debt)} accessibility problem(s) from this application's baseline are still "
            f"open, and this project has chosen to be held to them: "
            f"{_named([_describe(ref) for ref in debt])}. Fix them, or turn baseline "
            f"enforcement off in the project's accessibility settings to go back to reporting "
            f"them only."
        ))

    # 4. Clean — or one of the things that only LOOKS clean. Both notes can be true at once (a
    #    story with no UI, in a project carrying inherited debt), so they are joined rather than
    #    ranked: dropping either would leave a reviewer approving over something unsaid.
    notes = []
    if advisory := advisory_a11y_defects(tenant_id=tenant_id, work_item_id=work_item_id):
        # QA-22. The same rule as the debt note below, for the same reason: a green gate on a
        # story whose keyboard journey found a focus trap must not read like a green gate on a
        # story that found nothing. The reviewer approving this is the person who most needs to
        # know, and the report they would otherwise have to go and read is not in front of them.
        notes.append(
            f"the keyboard journey found {len(advisory)} accessibility problem(s) on this "
            f"story; they are tracked as defects and do not block, because findings from that "
            f"agent never stop work: {_named([_describe(ref) for ref in advisory])}"
        )
    if debt:
        notes.append(
            f"this project has {len(debt)} open accessibility problem(s) inherited from its "
            f"baseline audit; they are reported and do not block, because baseline enforcement "
            f"is off for this project"
        )
    if not has_been_checked(tenant_id=tenant_id, project_id=project_id,
                            work_item_id=work_item_id):
        notes.append(NOT_CHECKED_DETAIL)
    return _result(condition, True, " — ".join(notes))
