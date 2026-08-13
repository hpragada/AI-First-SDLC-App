"""Judgment dispatch, cache and audit (QA-02) — the one path every AI accessibility check
goes through.

Judgment costs time and subscription usage, so the platform must decide *what actually needs
judging*, ask for it once, reuse the answer, and be able to prove afterwards which model
produced which verdict. That decision layer is this module:

  1. drop any candidate whose input hash already has a stored verdict;
  2. group what is left by screen, so the judge sees a coherent page at a time;
  3. start ONE `09c_a11y_judge` run through the `ExecutionDriver` (never a direct model call);
  4. store each returned verdict against its input hash (`record_verdict`, called by the MCP
     tool built in QA-02a);
  5. stamp the engine, model and prompt version — read from the `Run` — onto every verdict.

**Why one run per dispatch and not one per screen** (correcting the task text — see
TASK_BACKLOG_QA.md): `orchestration.trigger._guard_no_active_run` refuses to start a second
run while one is live for the same work item, so per-screen runs would collide on the second
screen every time. The screens are still grouped — they arrive as separate batches inside the
one run's inputs — so the judge gets a page at a time without the platform trying to run N
concurrent agents against one work item.

Nothing here ever raises at the caller. An unavailable judge, a refused trigger or a timeout
all come back as `uncertain` verdicts with a reason, because an accessibility scan that
half-worked must route its items to a human, never look like a clean result (D-A11Y-3).
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate, A11yJudgment, uncertain

#: The platform-native agent that does the judging. Built in QA-02a — until then this key
#: resolves to no AgentSpec, which is exactly the "judge unavailable" path below, exercised
#: for real rather than with a mock.
JUDGE_AGENT_KEY = "09c_a11y_judge"

#: How many elements one run may judge before it stops and defers the rest. Chosen to sit
#: comfortably above ten ordinary screens (the team's sizing assumption) while still bounding
#: what a single runaway page can cost. Override per tenant with `max_judgments_per_run` in
#: the a11yai connection's scopes.
DEFAULT_MAX_JUDGMENTS_PER_RUN = 200

#: A screen cap, off by default. Set `max_screens_per_run` in the same scopes to cap by
#: screens instead of (or as well as) elements — whichever limit is reached first stops the
#: run. Present from day one so switching to "10 screens per run" is a config change, never
#: a code change.
DEFAULT_MAX_SCREENS_PER_RUN: int | None = None

#: Reasons a dispatch produced no judgment. Greppable, and each one is a sentence a person
#: can act on rather than a status code.
NO_JUDGE_AGENT = (
    "The accessibility judge is not available in this workspace — no {key} agent is "
    "registered. These items were sent for human review instead of being scored."
)
NO_COMPANION = (
    "The accessibility judge runs on your connected machine, and none is connected. These "
    "items were sent for human review instead of being scored."
)
DISPATCH_FAILED = (
    "The accessibility judge could not be started ({detail}). These items were sent for "
    "human review instead of being scored."
)
OVER_CAP = (
    "Stopped at this run's limit of {cap} — {remaining} item(s) still need judging. Run the "
    "check again to continue from here; nothing was skipped."
)


@dataclass(frozen=True)
class A11yRequest:
    """One thing to judge, and which check should judge it."""

    checker: str                 # alt | semantics | color | label
    candidate: A11yCandidate

    @property
    def content_hash(self) -> str:
        return content_hash(self.checker, self.candidate)


@dataclass
class DispatchResult:
    """What a dispatch did — deliberately explicit about what it did NOT do.

    `deferred` and `unavailable_reason` exist so an incomplete scan can never be mistaken for
    a clean one: the caller has, in its hands, the items that still need judging and the
    sentence explaining why.
    """

    from_cache: list[A11yJudgment] = field(default_factory=list)
    dispatched: list[A11yRequest] = field(default_factory=list)
    deferred: list[A11yRequest] = field(default_factory=list)
    unjudged: list[A11yJudgment] = field(default_factory=list)   # uncertain, for human review
    run_id: str | None = None
    unavailable_reason: str = ""

    @property
    def screens(self) -> list[str]:
        """The distinct screens this dispatch sent for judgment, in order."""
        seen: list[str] = []
        for request in self.dispatched:
            if request.candidate.route not in seen:
                seen.append(request.candidate.route)
        return seen

    @property
    def complete(self) -> bool:
        return not self.deferred and not self.unavailable_reason


def content_hash(checker: str, candidate: A11yCandidate) -> str:
    """The cache key: a hash of everything that could change the answer.

    Covers the checker and the three inputs the judge actually looks at. Excludes the selector
    and the route on purpose — see `A11yJudgmentCache`'s docstring for why. The parts are
    length-prefixed so that moving text from one field to another cannot collide.
    """
    parts = (checker, candidate.html, candidate.screenshot_ref, candidate.context)
    payload = "\x1f".join(f"{len(p)}:{p}" for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def caps_for(tenant_id) -> tuple[int, int | None]:
    """(max judgments, max screens) for a tenant, from the a11yai connection's scopes.

    Falls back to the defaults when the capability isn't configured — a missing connection is
    not a reason to run uncapped.
    """
    from integrations.registry import get_connection

    scopes: dict = {}
    conn = get_connection(tenant_id, "a11yai")
    if conn is not None:
        scopes = conn.scopes or {}
    # `is None`, not `or`: a configured cap of 0 is a deliberate kill-switch ("judge nothing
    # for now"), and `or` would silently turn it back into the default — the opposite of what
    # whoever set it asked for.
    judgments = scopes.get("max_judgments_per_run")
    if judgments is None:
        judgments = DEFAULT_MAX_JUDGMENTS_PER_RUN
    screens = scopes.get("max_screens_per_run")
    if screens is None:
        screens = DEFAULT_MAX_SCREENS_PER_RUN
    return int(judgments), (None if screens is None else int(screens))


def _cached(tenant_id, project_id, request: A11yRequest) -> A11yJudgment | None:
    from apps.a11y.models import A11yJudgmentCache

    row = A11yJudgmentCache.objects.filter(
        tenant_id=tenant_id, project_id=project_id,
        checker=request.checker, content_hash=request.content_hash,
    ).first()
    if row is None:
        return None
    return A11yJudgment(
        criteria=tuple(row.criteria), verdict=row.verdict, confidence=row.confidence,
        evidence=row.evidence, suggested_fix=row.suggested_fix, checker=row.checker,
    )


def _unjudged(requests: list[A11yRequest], reason: str) -> list[A11yJudgment]:
    """Turn requests we could not judge into complete `uncertain` results carrying the reason.

    Never an exception and never an empty list: an outage that produced *nothing* would read
    downstream as "no accessibility problems found", which is the one wrong answer here.
    """
    return [
        uncertain(A11Y_CHECKER_CRITERIA[r.checker], checker=r.checker, reason=reason)
        for r in requests
    ]


def _split_at_cap(
    requests: list[A11yRequest], max_judgments: int, max_screens: int | None
) -> tuple[list[A11yRequest], list[A11yRequest]]:
    """(to dispatch, deferred). Stops at the first limit reached and defers everything after
    it in order, so a re-run continues from exactly where this one stopped."""
    taken: list[A11yRequest] = []
    screens: list[str] = []
    for index, request in enumerate(requests):
        route = request.candidate.route
        if route not in screens:
            if max_screens is not None and len(screens) >= max_screens:
                return taken, requests[index:]
            screens.append(route)
        if len(taken) >= max_judgments:
            return taken, requests[index:]
        taken.append(request)
    return taken, []


def element_handle(index: int, content_hash: str) -> str:
    """The short id the judge echoes back to say which element a finding is about (QA-02a).

    The batch already carries each element's 64-character content hash, but asking a model to
    copy that back exactly is the most error-prone thing we could ask — and a single wrong
    character would file a verdict against a different element. So the agent never sees the
    hash: it sees this, and the platform maps it back.

    Deliberately not a bare counter. `e1` mistyped as `e2` is another *valid* element and the
    verdict lands silently on the wrong one; `3-a91f0c2e` mistyped is almost certainly no
    element at all, which the tool rejects out loud. The index keeps it readable and ordered,
    and disambiguates two identical elements on one page (same markup, same hash).
    """
    return f"{index}-{content_hash[:8]}"


def _group_by_screen(requests: list[A11yRequest]) -> list[dict]:
    """The run's input: one batch per screen, in first-seen order, so the judge reads a page
    at a time instead of a shuffled pile of elements.

    `content_hash` stays here because the platform needs it to store the verdict; it is
    stripped before the agent ever sees the batch (`judge.batch_for_run`).
    """
    batches: dict[str, dict] = {}
    for index, request in enumerate(requests, start=1):
        route = request.candidate.route
        batch = batches.setdefault(route, {"route": route, "elements": []})
        batch["elements"].append({
            "id": element_handle(index, request.content_hash),
            "content_hash": request.content_hash,
            "checker": request.checker,
            "criteria": list(A11Y_CHECKER_CRITERIA[request.checker]),
            "selector": request.candidate.selector,
            "html": request.candidate.html,
            "screenshot_ref": request.candidate.screenshot_ref,
            "context": request.candidate.context,
        })
    return list(batches.values())


def judge_available(tenant_id, project_id, triggered_by=None) -> str:
    """"" if the judge can run, else the sentence explaining why it cannot (D-A11Y-3).

    Two things must hold: the agent is registered for this workspace, and there is a machine
    to run it on — judgment rides the Claude subscription on the user's connected companion,
    exactly as the onboarding and vision agents do, so no companion means no judge.
    """
    from apps.registry.models import AgentSpec
    from apps.tenancy.context import tenant_context
    from orchestration.trigger import _resolve_enrollment

    with tenant_context(tenant_id):
        if not AgentSpec.objects.filter(tenant_id=tenant_id, key=JUDGE_AGENT_KEY).exists():
            return NO_JUDGE_AGENT.format(key=JUDGE_AGENT_KEY)
        if _resolve_enrollment(tenant_id, project_id, triggered_by) is None:
            return NO_COMPANION
    return ""


def dispatch_judgments(
    *,
    tenant_id,
    project_id,
    work_item_id,
    requests: list[A11yRequest],
    triggered_by=None,
    trigger=None,
) -> DispatchResult:
    """Decide what needs judging, ask for it once, and say honestly what was left undone.

    `trigger` is injectable so tests can dispatch without Temporal; it defaults to the same
    `trigger_phase` every other agent run goes through (#7 — no direct model call anywhere on
    this path).
    """
    from apps.tenancy.context import tenant_context

    result = DispatchResult()
    if not requests:
        return result

    # 1) Serve what we already know. A cache hit cannot be stale: the key is the input.
    pending: list[A11yRequest] = []
    with tenant_context(tenant_id):
        for request in requests:
            hit = _cached(tenant_id, project_id, request)
            if hit is not None:
                result.from_cache.append(hit)
            else:
                pending.append(request)
    if not pending:
        return result

    # 2) Stop at the cap rather than truncating silently — the remainder is handed back.
    max_judgments, max_screens = caps_for(tenant_id)
    pending, result.deferred = _split_at_cap(pending, max_judgments, max_screens)
    if result.deferred:
        result.unavailable_reason = OVER_CAP.format(
            cap=max_judgments, remaining=len(result.deferred)
        )
    if not pending:
        return result

    # 3) Is there a judge at all? Answer before starting anything, so the reason we give is
    #    the real one rather than a downstream symptom.
    unavailable = judge_available(tenant_id, project_id, triggered_by)
    if unavailable:
        result.unavailable_reason = unavailable
        result.unjudged = _unjudged(pending + result.deferred, unavailable)
        result.deferred = []
        return result

    # 4) One run, through the driver seam. Any refusal to start is a reason for human review,
    #    never an exception thrown at the caller mid-scan.
    if trigger is None:
        from orchestration.trigger import trigger_phase as trigger

    try:
        outcome = trigger(
            tenant_id=tenant_id, project_id=project_id, work_item_id=work_item_id,
            agent_key=JUDGE_AGENT_KEY, triggered_by=triggered_by,
            execution_mode="companion", auto_approve=True,
        )
    except Exception as exc:  # noqa: BLE001 — every failure mode is "send it to a human"
        reason = DISPATCH_FAILED.format(detail=exc)
        result.unavailable_reason = reason
        result.unjudged = _unjudged(pending + result.deferred, reason)
        result.deferred = []
        return result

    result.run_id = outcome.run_id
    result.dispatched = pending
    _attach_batches(tenant_id, outcome.run_id, _group_by_screen(pending))
    return result


def _attach_batches(tenant_id, run_id, batches: list[dict]) -> None:
    """Put the screen batches on the run's inputs, where the manifest composer and the judge
    agent read them."""
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        run = Run.objects.get(id=run_id, tenant_id=tenant_id)
        run.inputs = {**(run.inputs or {}), "a11y_batches": batches}
        run.save(update_fields=["inputs", "updated_at"])


def record_verdict(
    *,
    tenant_id,
    project_id,
    run_id,
    content_hash: str,
    judgment: A11yJudgment,
):
    """Store one verdict against its input hash, stamped with what produced it.

    The sink the QA-02a MCP tool calls once per element. The engine/model/prompt version are
    read from the `Run` rather than trusted from the agent's own claim — an agent reporting
    which model it was is exactly the fact that must not be self-declared.

    Idempotent: re-reporting the same element updates its row instead of failing on the
    uniqueness constraint, so a retried or resumed run is safe.
    """
    from apps.a11y.models import A11yJudgmentCache
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        run = Run.objects.filter(id=run_id, tenant_id=tenant_id).first() if run_id else None
        row, _ = A11yJudgmentCache.objects.update_or_create(
            tenant_id=tenant_id, project_id=project_id,
            checker=judgment.checker, content_hash=content_hash,
            defaults={
                "criteria": list(judgment.criteria),
                "verdict": judgment.verdict,
                "confidence": judgment.confidence,
                "evidence": judgment.evidence,
                "suggested_fix": judgment.suggested_fix,
                "run": run,
                "engine": run.engine if run else "",
                "model": run.model if run else "",
                "prompt_version": run.prompt_version if run else "",
            },
        )
    return row
