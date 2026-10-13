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
import json
from dataclasses import dataclass, field

from integrations.types import (
    A11Y_CHECKER_CRITERIA,
    A11Y_UNCERTAIN,
    A11yCandidate,
    A11yJudgment,
    uncertain,
)

#: The platform-native agent that does the judging. Built in QA-02a — until then this key
#: resolves to no AgentSpec, which is exactly the "judge unavailable" path below, exercised
#: for real rather than with a mock.
JUDGE_AGENT_KEY = "09c_a11y_judge"

#: How many DISTINCT elements one run may judge before it stops and defers the rest. Chosen to
#: sit comfortably above ten ordinary screens (the team's sizing assumption) while still
#: bounding what a single runaway page can cost. Override per tenant with
#: `max_judgments_per_run` in the a11yai connection's scopes.
#:
#: **Distinct, and it has to be** (24 Aug). A site's header, footer and nav are the same markup
#: on every page, so one footer on seventeen pages is seventeen requests and one question. The
#: cap used to be applied to the requests: a 17-page audit selecting 371 elements held only 192
#: different questions, and stopping at 200 requests bought 128 answers — 72 of the 200 places
#: went to questions already asked in the same pass, and nine whole pages were never reached.
#: Counted properly, that site fits in one pass with room to spare. `_distinct` below is what
#: makes the number mean what this comment says.
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
#: A judge is ALREADY judging this work item. **Not a failure, and the difference is the whole
#: reason this constant exists** (31 Aug).
#:
#: `trigger_phase` refuses a second run for a work item that already has a live one, and that
#: refusal used to arrive here as an ordinary exception — so it was reported as "the judge could
#: not be started" and every pending element was filed as `uncertain` for a human. On the 31
#: August audit that wrote off **1,065 elements while 800 of them were being judged at that
#: moment**, replaced the audit's own record of the pass that WAS running, and marked the audit
#: complete with the judge still working.
#:
#: A run already in progress means the work is happening, so nothing is filed, nothing is
#: deferred away, and the caller is told plainly. See `DispatchResult.already_running`.
ALREADY_JUDGING = (
    "A judgment run is already in progress for these elements ({detail}). Nothing was sent "
    "again and nothing was written off — the run that is already going will report on them."
)
#: Said of the DISPATCHER, not of the audit. "Stopped at this run's limit" was read — correctly
#: — as "the audit stopped", on a row for an audit that was still judging.
#:
#: `remaining` is **distinct elements**, never request slots. See `distinct_remainder`.
OVER_CAP = (
    "This run's limit of {cap} was reached, so {remaining} element(s) were left for a second "
    "pass. Run the check again to continue from here; nothing was skipped."
)

#: **How long this pass is allowed to take, sized to what it is being handed.**
#:
#: Every phase used to inherit a flat two hours because nothing ever set the field. On 31 August
#: the deadline fired at 7,200 s to the second on a judging pass that was working perfectly — a
#: verdict had landed seconds before and another landed seconds after — and the pass went on to
#: finish sixteen minutes later. The measured rate on that run was **10.2 s per element** for 800
#: elements; 25 s is ~2.4× that, generous without being open-ended.
#:
#: The floor keeps a small re-judge on the old two hours. The ceiling of eight hours is what stops
#: a runaway waiting for ever — a deadline that can be made arbitrarily long by making the batch
#: arbitrarily large is not a deadline.
JUDGE_SECONDS_PER_ELEMENT = 25
JUDGE_REPORT_FLOOR = 7_200
JUDGE_REPORT_CEILING = 28_800

#: And how long the write-completeness check that follows it may take.
#:
#: That check is not the one-artifact lookup it is for every other phase: it writes a fallback
#: verdict for each unanswered element — one database round trip each, against a remote server —
#: then publishes the merged report and closes the audit. At 60 s it was cancelled part-way and
#: 63 of 144 elements silently got no fallback at all; it was raised to a flat 5 minutes, and at
#: 800 elements 5 minutes is the same mistake one size up.
#:
#: 2 s per element is ~4× the ~0.4 s/element the 31 August close actually measured. The floor is
#: the flat five minutes it replaces, so nothing small gets a shorter budget than it has today.
VERIFY_SECONDS_PER_ELEMENT = 2
VERIFY_FLOOR = 300
VERIFY_CEILING = 1_800


def judging_deadlines(distinct: int) -> dict:
    """The two deadlines for a judging pass of this size, in seconds.

    Kept as one function because they are one decision — "how big is this pass" — asked twice,
    and because a test can then state the sizing rule in one place instead of re-deriving the
    arithmetic on both sides of it.
    """
    count = max(0, int(distinct or 0))
    return {
        "report_timeout_seconds": min(
            JUDGE_REPORT_CEILING, max(JUDGE_REPORT_FLOOR, count * JUDGE_SECONDS_PER_ELEMENT)),
        "verify_timeout_seconds": min(
            VERIFY_CEILING, max(VERIFY_FLOOR, count * VERIFY_SECONDS_PER_ELEMENT)),
    }


@dataclass(frozen=True)
class A11yRequest:
    """One thing to judge, and which check should judge it."""

    checker: str                 # one of `checkers.rules.CHECKERS` — never restated here,
                                 # because this comment had said "four" since `structure` was
                                 # added and would have gone on saying it
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
    #: The requests nothing could be asked about, for human review. Held as *requests* rather
    #: than as bare judgments because the caller has to be able to file them: a judgment on its
    #: own does not say which element it is about, so a result that carried only judgments could
    #: be reported and never recorded — which is exactly what happened (QA-13).
    unjudged_requests: list[A11yRequest] = field(default_factory=list)
    run_id: str | None = None
    unavailable_reason: str = ""
    #: Why the DEFERRED items were deferred, kept apart from `unavailable_reason` so one cannot
    #: overwrite the other. "We stopped at this run's limit" and "the judge could not be reached"
    #: are two different facts about two different sets of elements, and they can both be true of
    #: one dispatch. Held in one string before this, the second to happen erased the first — so a
    #: pass that reached its limit AND then failed to send reported only the failure, and the
    #: elements correctly queued for a second pass were labelled as ones nothing could ask about.
    deferred_reason: str = ""
    #: A judgment run is ALREADY live for this work item, so this dispatch deliberately did
    #: nothing. Distinct from `unavailable_reason` because it is not a failure: the elements are
    #: being judged right now by the run that got there first. Nothing is filed and nothing is
    #: cleared — see `ALREADY_JUDGING`.
    already_running: bool = False

    @property
    def unjudged(self) -> list[A11yJudgment]:
        """Those requests as complete `uncertain` results carrying the reason.

        Derived rather than stored, so the judgments and the requests they belong to can never
        drift apart or be set to different lengths.
        """
        return [
            uncertain(A11Y_CHECKER_CRITERIA[r.checker], checker=r.checker,
                      reason=self.unavailable_reason)
            for r in self.unjudged_requests
        ]

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

    Covers the checker and every input the judge actually looks at. Excludes the selector and
    the route on purpose — see `A11yJudgmentCache`'s docstring for why. The parts are
    length-prefixed so that moving text from one field to another cannot collide.

    **`structure` is in here, and has to be.** A container's markup is bounded, so a table can
    gain three hundred rows while the first eight thousand characters stay identical. Hash only
    the markup and that table keeps its old verdict for ever — the cache would be answering
    about a page that no longer exists. Serialised with sorted keys so two runs over an
    unchanged page produce the same key.

    **`accessible_name` is in here for exactly the same reason** (1 Sep). It is computed from
    the whole page, so it can change while this element's own markup does not: rename the
    `<label for=…>` beside a dropdown and the dropdown's own tag is untouched. Left out of the
    key, a 2.5.3 verdict would outlive the only input it was about.

    Adding it **invalidated every judgment cached before that date**, deliberately and once.
    Those verdicts were reached without the field, and a cache hit is a promise that nothing the
    judge looks at has changed — which was not true of them.
    """
    outline = json.dumps(candidate.structure or {}, sort_keys=True, separators=(",", ":"))
    parent = json.dumps(candidate.parent or {}, sort_keys=True, separators=(",", ":"))
    parts = (checker, candidate.html, candidate.screenshot_ref, candidate.context, outline,
             candidate.accessible_name, parent)
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


def _cached(tenant_id, project_id, request: A11yRequest,
            *, include_uncertain: bool = False) -> A11yJudgment | None:
    """The stored verdict for this input, or None.

    **`uncertain` is not served to a dispatch, and this is load-bearing.** An `uncertain` means
    no answer was reached — the judge was unavailable, the run ended without reporting on it, a
    picture could not be cut. Serving it back would turn a *transient* inability into a
    permanent one: the element would be skipped on every future run, for ever, and the platform
    would go on reporting "sent for human review" long after the reason had gone away. Nothing
    is saved by it either, because no judgment was ever made to reuse.

    The cost of the other direction is bounded and worth paying: an element that genuinely
    cannot be answered is re-asked each run, capped by the per-run limit like everything else.

    `include_uncertain=True` for the *read* path (`stored_judgment`), where the question is
    "what do we know about this element?" and "we could not tell, because …" is a real answer a
    reader needs. Only the dispatch decision excludes them.
    """
    from apps.a11y.models import A11yJudgmentCache

    rows = A11yJudgmentCache.objects.filter(
        tenant_id=tenant_id, checker=request.checker, content_hash=request.content_hash,
    )
    if not include_uncertain:
        rows = rows.exclude(verdict=A11Y_UNCERTAIN)
    if project_id is not None:
        rows = rows.filter(project_id=project_id)
    # Newest wins when the caller did not name a project. Ordered explicitly because an
    # unordered `.first()` over more than one row is whatever the database felt like.
    row = rows.order_by("-updated_at").first()
    if row is None:
        return None
    return A11yJudgment(
        criteria=tuple(row.criteria), verdict=row.verdict, confidence=row.confidence,
        evidence=row.evidence, suggested_fix=row.suggested_fix, checker=row.checker,
    )


def stored_judgment(*, tenant_id, checker: str, candidate: A11yCandidate,
                    project_id=None) -> A11yJudgment | None:
    """The verdict already held for this exact input, or None if it has not been judged.

    This is what the `a11yai` capability's four `check_*` methods answer from (D-A11Y-4). It
    can look across the tenant's projects when `project_id` is not given, and that is sound for
    the same reason the cache is sound at all: the key is a hash of everything the judge
    looked at, so identical input means the same answer whoever asked. It never crosses a
    tenant boundary — the query is tenant-filtered and runs under that tenant's RLS role.
    """
    from apps.tenancy.context import tenant_context

    with tenant_context(tenant_id):
        return _cached(tenant_id, project_id,
                       A11yRequest(checker=checker, candidate=candidate),
                       include_uncertain=True)


def distinct_remainder(dispatched: list, deferred: list) -> int:
    """How many ELEMENTS a stopped dispatch actually left unchecked.

    **The one definition of that number**, used by the sentence the dispatcher records and by
    the count `aipass` stores for the screen. They were computed in two places and one of them
    was the raw slot count, so a single audit could say "12 items still need judging" beside a
    button offering 6 — two numbers for one fact, on one card.

    Duplicates are collapsed by `_distinct` before the cap is applied, so on the ordinary path
    the two lists no longer overlap and this is simply how many are left. The subtraction stays
    because it is the definition rather than an optimisation: a caller holding lists from
    somewhere else — a test, a future path that splits differently — still gets the true answer,
    and a pass whose whole deferred tail was markup already handed over still reports **zero**
    left, which is a pass with nothing outstanding.
    """
    return len({r.content_hash for r in deferred} - {r.content_hash for r in dispatched})


def _distinct(requests: list[A11yRequest]) -> list[A11yRequest]:
    """One request per distinct question, in the order they were first asked.

    A site's furniture — header, footer, nav — is the same markup on every page, and the
    fingerprint is a hash of exactly what the judge is shown, so seventeen copies of one footer
    are seventeen requests carrying ONE question. Asking it seventeen times costs seventeen
    judgments and returns the same answer; `record_verdict` then stores it once, which is why
    the waste was invisible.

    **Dropping a copy loses nothing.** `report.merge_run` walks every request the capture holds
    — not the ones dispatched — and looks each up by fingerprint, so every copy still gets its
    own row on its own page with its own selector. That fan-out already existed; this only stops
    us paying for the same answer more than once.

    First occurrence wins so the order is stable: two runs over an unchanged capture dispatch
    the same list, and the judge reads pages in the order the capture visited them.
    """
    seen: set[str] = set()
    out: list[A11yRequest] = []
    for request in requests:
        if request.content_hash in seen:
            continue
        seen.add(request.content_hash)
        out.append(request)
    return out


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

    **Everything a checker's question turns on has to be in this dict**, and for `label` that
    is `accessible_name` — which the browser computes, the capture stores, and this function
    did not send until 1 September. `tag` and `role` deliberately stay out: the judge reads
    both off `html`, which is the element's own outerHTML, so restating them would add nothing
    and change the cache key for no gain. The name is different in kind — it is computed from
    the whole page and is recoverable from nothing else that travels.
    `test_a11y_dispatch.test_the_batch_carries_every_field_a_check_needs` is what stops this
    list drifting from the questions again.
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
            "accessible_name": request.candidate.accessible_name,
            "parent": dict(request.candidate.parent or {}),
            "markup_truncated": request.candidate.markup_truncated,
            "structure": dict(request.candidate.structure or {}),
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

    # 2) One request per distinct question FIRST, then the cap — in that order, because the
    #    other order is what let a site's footer occupy seventeen of the two hundred places and
    #    push nine whole pages past the end of the pass. The cap is a limit on how much judging
    #    a run may cost, and a repeat costs nothing.
    pending = _distinct(pending)
    #    Stop at the cap rather than truncating silently — the remainder is handed back.
    max_judgments, max_screens = caps_for(tenant_id)
    pending, result.deferred = _split_at_cap(pending, max_judgments, max_screens)
    # Only when something is genuinely left. A pass whose whole deferred tail is markup already
    # handed over has nothing outstanding, and a sentence claiming otherwise put work on a
    # person's list that did not exist. `result.complete` still reads False — requests really
    # were deferred, and a re-run really does continue from here — but nobody is told to act.
    if remaining := distinct_remainder(pending, result.deferred):
        result.deferred_reason = OVER_CAP.format(cap=max_judgments, remaining=remaining)
        result.unavailable_reason = result.deferred_reason
    if not pending:
        return result

    # 3) Is there a judge at all? Answer before starting anything, so the reason we give is
    #    the real one rather than a downstream symptom.
    unavailable = judge_available(tenant_id, project_id, triggered_by)
    if unavailable:
        result.unavailable_reason = unavailable
        # **`pending` only. What was DEFERRED stays deferred** (31 Aug), here and on the failure
        # path below. Both used to file `pending + deferred` and then clear `deferred`, which
        # took elements that had been correctly held back at this run's limit and relabelled
        # them as elements nothing could be asked about. On the 31 August audit that stamped 265
        # correctly-queued elements with "the judge could not be started" and put them, with 800
        # others, on a person's review queue as 1,731 items that were never real.
        #
        # Nothing is lost by leaving them: an element with no verdict row at all is exactly what
        # `aipass.unanswered_for_capture` looks for, and `unanswered_counts` adds
        # `filed_unjudged` to `deferred_distinct`, so the total a screen shows is unchanged.
        # What changes is that each half now carries the reason that is true of it.
        result.unjudged_requests = pending
        return result

    # 4) One run, through the driver seam. Any refusal to start is a reason for human review,
    #    never an exception thrown at the caller mid-scan.
    if trigger is None:
        from orchestration.trigger import trigger_phase as trigger

    from orchestration.trigger import ActiveRunError

    try:
        outcome = trigger(
            tenant_id=tenant_id, project_id=project_id, work_item_id=work_item_id,
            agent_key=JUDGE_AGENT_KEY, triggered_by=triggered_by,
            execution_mode="companion", auto_approve=True,
            # Sized to what is actually being handed over, rather than to the flat constants a
            # planning phase was measured for. `pending` is the distinct question list at this
            # point — after de-duplication and after the cap — so it is exactly the work the
            # companion will do and exactly the work the completeness check will have to walk.
            **judging_deadlines(len(pending)),
        )
    except ActiveRunError as exc:
        # **Caught before the general handler, because it is not a failure.** A run is already
        # live for this work item, which means these elements are already being judged — by a
        # dispatch that got here first, from a caller that was retried, or from a close that was
        # made twice. Reporting it as "the judge could not be started" and filing every pending
        # element as `uncertain` writes off work that is happening at that moment, and that is
        # exactly what it did on the 31 August audit. See `ALREADY_JUDGING`.
        result.already_running = True
        result.unavailable_reason = ALREADY_JUDGING.format(detail=exc)
        return result
    except Exception as exc:  # noqa: BLE001 — every failure mode is "send it to a human"
        result.unavailable_reason = DISPATCH_FAILED.format(detail=exc)
        result.unjudged_requests = pending
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
