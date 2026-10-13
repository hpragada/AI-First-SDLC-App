"""QA-02 — judgment dispatch, cache and audit behind `a11yai`.

What these prove, against the task's acceptance criteria:

  AC1  judgment happens through an ExecutionDriver run — no direct model/API call anywhere
       on the dispatch path (asserted by reading the source, not by trusting the design)
  AC2  the same candidate judged twice is served from the store; no second run is started
  AC3  every stored verdict records the engine, model and prompt version that produced it
  AC4  a refused or errored dispatch returns `uncertain`, never a hard failure
  AC5  a batch over the cap stops at the cap and hands back the remainder
  AC6  (D-A11Y-3) an unavailable judge is reported in plain words and its items go to human
       review, rather than coming back empty and reading as "no problems found"
  AC7  coverage ≥ 90% on the new code

The judge agent (`09c_a11y_judge`) does not exist until QA-02a, so the unavailable-judge path
here is exercised for real rather than with a mock — the fixtures register a stand-in spec
only where a *successful* dispatch is the thing under test.
"""
import psycopg
import pytest
from django.conf import settings
from django.db import connection

from apps.a11y.dispatch import (
    DEFAULT_MAX_JUDGMENTS_PER_RUN,
    JUDGE_AGENT_KEY,
    NO_COMPANION,
    NO_JUDGE_AGENT,
    A11yRequest,
    caps_for,
    content_hash,
    dispatch_judgments,
    judge_available,
    record_verdict,
)
from apps.a11y.models import A11yJudgmentCache
from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_UNCERTAIN, A11yCandidate, A11yJudgment


@pytest.fixture
def world(db):
    """A tenant that can actually dispatch: judge agent registered, machine connected."""
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    user = User.objects.create_user(email="qa@acme.com", name="QA", tenant=tenant, password="pw")
    work_item = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    AgentSpec.objects.create(
        tenant=tenant, key=JUDGE_AGENT_KEY, semver="1.0.0", prompt_version="a11y-judge-1",
        body_ref="agents/09c_a11y_judge.md", recommended_engine="claude",
        recommended_model="claude-opus-5", phase_label="testing",
    )
    enroll_runner(tenant_id=str(tenant.id), project_id=str(project.id),
                  developer_id=str(user.id), label="qa-laptop")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="a11yai", connector="builtin", token_ref="builtin",
    )
    return {"tenant": tenant, "project": project, "user": user, "work_item": work_item}


class FakeTrigger:
    """Stands in for `trigger_phase` — records the call and creates the Run it would create.

    A fake here is right: what QA-02 owns is the *decision* to dispatch and what it records.
    Actually starting a Temporal workflow is `trigger_phase`'s job, and it has its own tests.
    """

    def __init__(self, world, fail: Exception | None = None):
        self._world = world
        self._fail = fail
        self.calls: list[dict] = []

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        if self._fail is not None:
            raise self._fail
        spec = AgentSpec.objects.get(tenant=self._world["tenant"], key=kwargs["agent_key"])
        run = Run.objects.create(
            tenant=self._world["tenant"], work_item=self._world["work_item"], agent_spec=spec,
            engine=spec.recommended_engine, model=spec.recommended_model,
            prompt_version=spec.prompt_version,
        )

        class _Outcome:
            run_id = str(run.id)
            workflow_id = f"agent-run-{run.id}"

        return _Outcome()


def _request(checker="alt", *, route="/checkout", html='<img src="a.png" alt="a">', **kw):
    return A11yRequest(
        checker=checker,
        candidate=A11yCandidate(selector="img", html=html, route=route, **kw),
    )


def _dispatch(world, requests, trigger=None, **kw):
    return dispatch_judgments(
        tenant_id=world["tenant"].id, project_id=world["project"].id,
        work_item_id=world["work_item"].id, requests=requests,
        triggered_by=str(world["user"].id), trigger=trigger, **kw,
    )


# ── AC1: it goes through the driver seam, never a model call ─────────
def test_no_direct_model_or_api_call_exists_on_the_dispatch_path():
    """Non-negotiable #7, asserted rather than assumed. If someone later reaches for an HTTP
    client or an SDK here, this fails and names the line — the design intent stops being a
    comment and becomes a check."""
    import re
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "apps/a11y/dispatch.py").read_text()
    # Imports and calls, not bare words — this module legitimately has a variable named
    # `requests` (the things to be judged), and a guard that cried wolf would get deleted.
    banned = (
        r"^\s*(from|import)\s+(anthropic|openai|httpx|requests|urllib|http\.client|aiohttp)\b",
        r"\brequests\.(get|post|put|patch|delete|request)\s*\(",
        r"\bhttpx\.(get|post|Client|AsyncClient)\b",
        r"\banthropic\b", r"\bopenai\b",
        r"api_key", r"\.messages\.create\s*\(", r"\.chat\.completions\b",
    )
    offenders = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(source.splitlines(), start=1)
        for pattern in banned
        if re.search(pattern, line, re.IGNORECASE)
    ]
    assert not offenders, "direct model/API access on the dispatch path:\n  " + "\n  ".join(
        offenders
    )


def test_dispatch_starts_one_run_through_the_trigger(world):
    trigger = FakeTrigger(world)
    result = _dispatch(world, [_request(), _request(html="<img src='b.png'>")], trigger)

    assert len(trigger.calls) == 1, "one run per dispatch, not one per element"
    assert trigger.calls[0]["agent_key"] == JUDGE_AGENT_KEY
    assert result.run_id and len(result.dispatched) == 2
    assert result.complete is True


def test_the_dispatcher_hands_the_run_its_own_deadlines(world):
    """The two timers that fired on work which was going perfectly well, 31 August.

    The report deadline rang at exactly 7,200 s on a pass that needed 8,193 — on a companion that
    answered seconds either side of it — and the write-completeness check was cancelled at its
    flat five minutes on the same pass. Both were constants sized for a planning phase that takes
    four minutes, and `trigger_phase` never set either field, so every phase inherited them in
    silence. The dispatcher is the only place that knows how big the pass is, so the dispatcher
    says.

    Asserted on the CALL rather than on the numbers: `judging_deadlines` owns the arithmetic and
    is tested against real measurements in `test_a11y_judge.py`. What is at stake here is that
    the answer travels — the whole failure was a value that was computed nowhere and passed
    nowhere.
    """
    from apps.a11y.dispatch import judging_deadlines

    trigger = FakeTrigger(world)
    requests = [_request(), _request(html="<img src='b.png'>"), _request(html="<img src='c'>")]
    _dispatch(world, requests, trigger)

    assert len(trigger.calls) == 1
    call = trigger.calls[0]
    assert call["report_timeout_seconds"] == judging_deadlines(3)["report_timeout_seconds"]
    assert call["verify_timeout_seconds"] == judging_deadlines(3)["verify_timeout_seconds"]
    # A batch this small sits on the floors, which are the budgets it already had — nothing gets
    # LESS time than before, which is what makes this safe for every other size of pass.
    assert call["report_timeout_seconds"] == 7_200
    assert call["verify_timeout_seconds"] == 300


def test_a_big_pass_is_given_more_than_the_two_hours_that_parked_the_real_one(world):
    """The same call, at the size that actually broke: 800 distinct questions."""
    trigger = FakeTrigger(world)
    _dispatch(world, [_request(html=f"<img src='{n}.png'>") for n in range(40)], trigger)

    # 40 distinct questions is still on the floor — the point of the floor. What matters is that
    # the number now comes from the batch at all, so the 800-element case scales instead of
    # inheriting a constant.
    assert trigger.calls[0]["report_timeout_seconds"] >= 7_200

    from apps.a11y.dispatch import judging_deadlines

    assert judging_deadlines(800)["report_timeout_seconds"] > 8_193, (
        "the real pass took 8,193 s and was parked at 7,200"
    )


def test_the_run_carries_the_candidates_grouped_by_screen(world):
    """The judge should read a page at a time, not a shuffled pile of elements."""
    trigger = FakeTrigger(world)
    result = _dispatch(world, [
        _request(route="/cart"),
        _request(route="/checkout", html="<img src='b.png'>"),
        _request(route="/cart", html="<img src='c.png'>"),
    ], trigger)

    batches = Run.objects.get(id=result.run_id).inputs["a11y_batches"]
    assert [b["route"] for b in batches] == ["/cart", "/checkout"]   # first-seen order
    assert len(batches[0]["elements"]) == 2 and len(batches[1]["elements"]) == 1
    assert batches[0]["elements"][0]["criteria"] == ["1.1.1"]
    assert result.screens == ["/cart", "/checkout"]


# ── AC2: judged once, reused thereafter ──────────────────────────────
def test_a_second_dispatch_of_the_same_candidate_starts_no_run(world):
    request = _request()
    first = FakeTrigger(world)
    _dispatch(world, [request], first)
    record_verdict(
        tenant_id=world["tenant"].id, project_id=world["project"].id,
        run_id=first.calls and Run.objects.first().id, content_hash=request.content_hash,
        judgment=A11yJudgment(criteria=("1.1.1",), verdict="pass", confidence=0.95,
                              evidence="alt describes the chart", suggested_fix="",
                              checker="alt"),
    )

    second = FakeTrigger(world)
    result = _dispatch(world, [request], second)

    assert second.calls == [], "a cached candidate must not start a run"
    assert len(result.from_cache) == 1
    assert result.from_cache[0].verdict == "pass"
    assert result.from_cache[0].criteria == ("1.1.1",)


def test_changing_the_element_busts_the_cache(world):
    """The safety argument for caching a model's opinion: the key is the input, so anything
    that could change the answer changes the key."""
    original = _request(html='<img src="a.png" alt="a">')
    edited = _request(html='<img src="a.png" alt="quarterly revenue by region">')
    assert original.content_hash != edited.content_hash


def test_the_selector_and_route_are_deliberately_not_part_of_the_key():
    """Same markup, same context, same answer — re-judging because a selector churned would
    cost money for nothing. (Finding-level dedup is a different key, built in QA-12a.)"""
    a = A11yCandidate(selector="#a", html="<b>x</b>", context="c", route="/one")
    b = A11yCandidate(selector="main .b", html="<b>x</b>", context="c", route="/two")
    assert content_hash("alt", a) == content_hash("alt", b)


def test_the_hash_cannot_collide_by_moving_text_between_fields():
    a = A11yCandidate(html="ab", context="")
    b = A11yCandidate(html="a", context="b")
    assert content_hash("alt", a) != content_hash("alt", b)


def test_the_same_input_under_a_different_checker_is_judged_separately():
    candidate = A11yCandidate(html="<div>Save</div>", route="/x")
    assert content_hash("alt", candidate) != content_hash("semantics", candidate)


def test_a_changed_accessible_name_is_a_different_question():
    """The `<label>` beside a dropdown is renamed. The dropdown's own markup does not move.

    Left out of the key, the old 2.5.3 verdict would outlive the only input it was about — the
    same argument that put `structure` in the key, and for a field that changes far more often.
    """
    before = A11yCandidate(html="<select id='b'></select>", accessible_name="Home branch")
    after = A11yCandidate(html="<select id='b'></select>", accessible_name="Collection point")
    assert content_hash("label", before) != content_hash("label", after)


def test_a_changed_parent_is_a_different_question():
    """The same `<img alt="">` inside a link and inside a figure are not the same question:
    one hides where a link goes, the other is correct."""
    in_link = A11yCandidate(html='<img alt="">', parent={"tag": "a", "href": "/x"})
    in_figure = A11yCandidate(html='<img alt="">', parent={"tag": "figure"})
    assert content_hash("alt", in_link) != content_hash("alt", in_figure)


def test_the_batch_carries_every_field_a_check_needs():
    """The batch handed to the judge must carry every field of the candidate contract.

    **The sibling of `test_a11y_capture.test_every_field_the_contract_reads_is_actually_stored`,
    and it exists for the same reason that one does.** `accessible_name` was captured from the
    browser's accessibility tree, normalised, stored on the bundle — and never put in this dict.
    WCAG 2.5.3 asks one question, *does the announced name contain the visible label*, and the
    judge was handed the markup, the picture and the surrounding text and not the name.

    For a `<button>` that was survivable: its name is the word printed on it, and `html` carries
    that word. For a `<select>` it was not, because the `<label for=…>` that names one is a
    SIBLING and is therefore never inside the element's own markup. Every dropdown in the
    31 August Meridian audit — 13 of 13 — came back "cannot determine the accessible name",
    against 1.4% uncertainty everywhere else.

    Nothing failed, because the two lists had never been compared.

    `route` is the deliberate exception: it is the batch's own key, one level up, so restating
    it on every element would be noise. Naming it here means a second exception has to be argued
    for rather than quietly appearing.
    """
    import dataclasses

    from apps.a11y.dispatch import _group_by_screen

    request = A11yRequest(checker="label", candidate=A11yCandidate(route="/x"))
    sent = set(_group_by_screen([request])[0]["elements"][0])
    contract = {f.name for f in dataclasses.fields(A11yCandidate)}
    keyed_on_the_batch = {"route"}

    assert not (contract - sent - keyed_on_the_batch), (
        "the judge's batch drops candidate fields: "
        f"{sorted(contract - sent - keyed_on_the_batch)}. Add them to `_group_by_screen` — and "
        "if a field genuinely belongs to the screen rather than the element, add it to "
        "`keyed_on_the_batch` here with the reason."
    )


# ── AC3: the audit trail ─────────────────────────────────────────────
def test_a_stored_verdict_records_the_engine_model_and_prompt_version(world):
    trigger = FakeTrigger(world)
    request = _request()
    result = _dispatch(world, [request], trigger)

    row = record_verdict(
        tenant_id=world["tenant"].id, project_id=world["project"].id, run_id=result.run_id,
        content_hash=request.content_hash,
        judgment=A11yJudgment(criteria=("1.1.1",), verdict="fail", confidence=0.88,
                              evidence='alt is "a"', suggested_fix="Describe the image",
                              checker="alt"),
    )

    assert row.engine == "claude"
    assert row.model == "claude-opus-5"
    assert row.prompt_version == "a11y-judge-1"
    assert str(row.run_id) == result.run_id


def test_the_audit_stamp_comes_from_the_run_not_the_agents_own_claim(world):
    """Which model produced a verdict is exactly the fact an agent must not self-declare."""
    trigger = FakeTrigger(world)
    request = _request()
    result = _dispatch(world, [request], trigger)
    run = Run.objects.get(id=result.run_id)
    run.model = "the-real-model"
    run.save(update_fields=["model"])

    row = record_verdict(
        tenant_id=world["tenant"].id, project_id=world["project"].id, run_id=result.run_id,
        content_hash=request.content_hash,
        judgment=A11yJudgment(criteria=("1.1.1",), verdict="pass", confidence=0.9,
                              evidence="e", suggested_fix="", checker="alt"),
    )
    assert row.model == "the-real-model"


def test_re_reporting_the_same_element_updates_rather_than_duplicates(world):
    request = _request()
    args = {"tenant_id": world["tenant"].id, "project_id": world["project"].id,
            "run_id": None, "content_hash": request.content_hash}
    record_verdict(**args, judgment=A11yJudgment(
        criteria=("1.1.1",), verdict="uncertain", confidence=0.3, evidence="e",
        suggested_fix="", checker="alt"))
    record_verdict(**args, judgment=A11yJudgment(
        criteria=("1.1.1",), verdict="fail", confidence=0.9, evidence="e2",
        suggested_fix="f", checker="alt"))

    rows = A11yJudgmentCache.objects.filter(content_hash=request.content_hash)
    assert rows.count() == 1 and rows.first().verdict == "fail"


# ── AC4 + AC6: nothing comes back empty and quiet ────────────────────
def test_a_refused_dispatch_returns_uncertain_not_an_exception(world):
    trigger = FakeTrigger(world, fail=RuntimeError("a run is already in progress"))
    result = _dispatch(world, [_request(), _request(html="<img src='b'>")], trigger)

    assert result.run_id is None
    assert len(result.unjudged) == 2
    assert all(j.verdict == A11Y_UNCERTAIN for j in result.unjudged)
    assert "a run is already in progress" in result.unavailable_reason
    assert result.complete is False


def test_a_run_already_judging_this_work_item_files_nothing_and_writes_nothing_off(world):
    """The 31 August audit, in one test.

    `trigger_phase` refuses a second run for a work item that already has a live one. That
    refusal used to arrive here as an ordinary exception, so it was reported as "the judge could
    not be started" and every pending element was filed as `uncertain` for a human — writing off
    1,065 elements while 800 of them were being judged at that moment.

    A run already in progress is not a failure. Nothing is filed, the deferred tail is left
    alone, and the caller is told which state it is in rather than being handed work to record.
    """
    from orchestration.trigger import ActiveRunError

    trigger = FakeTrigger(world, fail=ActiveRunError(
        "a run is already in progress for this work item (status: running)."))
    result = _dispatch(world, [_request(), _request(html="<img src='b'>")], trigger)

    assert result.already_running is True
    assert result.run_id is None
    assert result.unjudged_requests == [], "nothing may be written off while a judge is judging"
    assert result.unjudged == []
    assert "already in progress" in result.unavailable_reason
    assert "nothing was written off" in result.unavailable_reason
    # Still not a complete pass — this dispatch judged nothing. The run that got there first is
    # what will report, and it is not this call's to claim.
    assert result.complete is False


def test_a_failed_dispatch_leaves_the_deferred_tail_deferred(world):
    """Over-budget and could-not-send are two facts about two different sets of elements.

    Both used to be folded into one list and one sentence: a dispatch that reached its limit and
    THEN failed to start reported everything as unaskable, so the elements correctly queued for a
    second pass were relabelled. On the 31 August audit that stamped 265 correctly-queued
    elements with "the judge could not be started" and put them on a person's review queue.
    """
    _set_caps(world, judgments=2)
    trigger = FakeTrigger(world, fail=RuntimeError("no worker answered"))
    requests = [_request(html=f"<img src='{i}.png'>") for i in range(5)]

    result = _dispatch(world, requests, trigger)

    # The two attempted are filed with the failure's own reason…
    assert len(result.unjudged_requests) == 2
    assert result.unjudged_requests == requests[:2]
    assert "no worker answered" in result.unavailable_reason
    # …and the three held back at the limit stay held back, with the reason that is true of them.
    assert result.deferred == requests[2:]
    assert "3 element(s) were left for a second pass" in result.deferred_reason
    # Nothing is counted twice and nothing is lost: every request is in exactly one of the lists.
    assert len(result.unjudged_requests) + len(result.deferred) == len(requests)


def test_no_judge_agent_is_reported_in_plain_words_and_nothing_is_dispatched(world):
    """The state the platform is genuinely in until QA-02a lands."""
    AgentSpec.objects.filter(tenant=world["tenant"], key=JUDGE_AGENT_KEY).delete()
    trigger = FakeTrigger(world)

    result = _dispatch(world, [_request()], trigger)

    assert trigger.calls == []
    assert result.unavailable_reason == NO_JUDGE_AGENT.format(key=JUDGE_AGENT_KEY)
    assert "human review" in result.unavailable_reason
    assert [j.verdict for j in result.unjudged] == [A11Y_UNCERTAIN]


def test_no_connected_machine_is_reported_and_nothing_is_dispatched(world):
    """Judgment rides the Claude subscription on the developer's own machine, like the
    onboarding and vision agents — so no machine means no judge, said plainly."""
    from apps.runs.models import RunnerEnrollment

    RunnerEnrollment.objects.filter(tenant=world["tenant"]).delete()
    trigger = FakeTrigger(world)

    result = _dispatch(world, [_request()], trigger)

    assert trigger.calls == []
    assert result.unavailable_reason == NO_COMPANION
    assert len(result.unjudged) == 1


def test_an_unjudged_item_carries_every_criterion_its_checker_covers(world):
    AgentSpec.objects.filter(tenant=world["tenant"], key=JUDGE_AGENT_KEY).delete()
    result = _dispatch(world, [_request("semantics", html="<div>Save</div>")], FakeTrigger(world))
    assert result.unjudged[0].criteria == ("1.3.1", "4.1.2")


def test_judge_available_returns_empty_when_everything_is_in_place(world):
    assert judge_available(
        world["tenant"].id, world["project"].id, str(world["user"].id)
    ) == ""


def test_dispatching_nothing_is_a_no_op(world):
    trigger = FakeTrigger(world)
    result = _dispatch(world, [], trigger)
    assert trigger.calls == [] and result.complete is True


# ── AC5: the cap stops, it does not truncate ─────────────────────────
def test_a_batch_over_the_cap_stops_and_hands_back_the_remainder(world):
    _set_caps(world, judgments=2)
    trigger = FakeTrigger(world)
    requests = [_request(html=f"<img src='{i}.png'>") for i in range(5)]

    result = _dispatch(world, requests, trigger)

    assert len(result.dispatched) == 2
    assert len(result.deferred) == 3
    assert result.deferred == requests[2:], "the remainder must resume where this stopped"
    # Five distinct images, so all three deferred really are outstanding.
    assert "3 element(s) were left for a second pass" in result.unavailable_reason
    assert result.complete is False


def test_the_cap_counts_distinct_questions_and_not_request_slots(world):
    """A repeat of a question already in this pass must not occupy a place in the cap.

    **Rewritten 24 Aug, and the old shape is the bug.** Duplicates used to reach the cap
    uncollapsed, so a site's footer — the same markup on every page — took one place per page.
    Measured on a real seventeen-page audit: 371 requests holding 192 different questions, a cap
    of 200, and the pass stopped having bought 128 answers. Seventy-two places went to questions
    already asked in the same pass, and nine whole pages were never reached at all. Counted
    properly that site finishes in one pass with room to spare.

    The concern the old test was written for still holds and is still asserted: the number a
    person is given has to be work that exists. It is now true by construction rather than by
    subtracting afterwards.
    """
    _set_caps(world, judgments=2)
    same = "<img src='chrome.png'>"
    # Three different questions in five requests. The cap is two, so two are asked and the
    # third — genuinely new — is what remains. The repeats cost nothing and wait for nothing.
    requests = [
        _request(html=same), _request(html="<img src='a.png'>"),
        _request(html=same), _request(html=same), _request(html="<img src='new.png'>"),
    ]

    result = _dispatch(world, requests, FakeTrigger(world))

    assert len(result.dispatched) == 2, "two questions asked, not two slots consumed"
    assert [r.candidate.html for r in result.dispatched] == [same, "<img src='a.png'>"]
    assert len(result.deferred) == 1, "only the genuinely new question is outstanding"
    assert "1 element(s) were left for a second pass" in result.unavailable_reason


def test_a_pass_whose_repeats_would_have_overflowed_the_cap_now_finishes(world):
    """The case that used to stop a pass that had nothing left to do.

    Four requests, two questions, a cap of two. Before, the repeats filled the cap and two
    requests were handed back — a pass reported as incomplete with every question answered.
    Now it simply finishes, which is what actually happened.
    """
    _set_caps(world, judgments=2)
    same = "<img src='chrome.png'>"
    requests = [_request(html=same), _request(html="<img src='a.png'>"),
                _request(html=same), _request(html=same)]

    result = _dispatch(world, requests, FakeTrigger(world))

    assert len(result.dispatched) == 2
    assert result.deferred == [], "nothing was left unasked"
    assert result.unavailable_reason == "", "nothing is outstanding, so nothing is claimed"
    assert result.complete is True, "every question in this capture has an answer"


def test_the_remainder_has_one_definition(world):
    """The screen's count and the dispatcher's sentence read the same function. They were two
    expressions of the same idea and one of them was the raw slot count."""
    from apps.a11y.dispatch import distinct_remainder

    same = _request(html="<img src='chrome.png'>")
    other = _request(html="<img src='a.png'>")
    assert distinct_remainder([same], [same, same]) == 0
    assert distinct_remainder([same], [same, other]) == 1
    assert distinct_remainder([], []) == 0


def test_the_cap_can_be_expressed_in_screens_instead_of_elements(world):
    """The team asked to be able to switch to a 10-screens cap without a code change. Both
    limits are read from config; whichever is reached first stops the run.

    **Each route needs its own markup, and that is not test-fixture housekeeping** (24 Aug). A
    fingerprint is a hash of what the judge is shown, and the route is deliberately not part of
    it: identical markup in identical surroundings is one question wherever it appears, which is
    the whole reason a site's footer no longer costs one judgment per page. This test used the
    same default image on `/one`, `/two` and `/three`, so with de-duplication in front of the
    cap they collapse to a single question and the screen cap never gets to bite. Giving each
    page a genuinely different element is what puts the screen cap back under test.
    """
    _set_caps(world, judgments=1000, screens=2)
    trigger = FakeTrigger(world)
    requests = [
        _request(route="/one", html="<img src='one-a.png'>"),
        _request(route="/one", html="<img src='one-b.png'>"),
        _request(route="/two", html="<img src='two.png'>"),
        _request(route="/three", html="<img src='three.png'>"),
    ]

    result = _dispatch(world, requests, trigger)

    assert result.screens == ["/one", "/two"]
    assert len(result.dispatched) == 3 and len(result.deferred) == 1
    assert result.deferred[0].candidate.route == "/three"


def test_resuming_after_the_cap_judges_only_what_was_left(world):
    _set_caps(world, judgments=2)
    requests = [_request(html=f"<img src='{i}.png'>") for i in range(4)]
    first = _dispatch(world, requests, FakeTrigger(world))
    for request in first.dispatched:
        record_verdict(
            tenant_id=world["tenant"].id, project_id=world["project"].id,
            run_id=first.run_id, content_hash=request.content_hash,
            judgment=A11yJudgment(criteria=("1.1.1",), verdict="pass", confidence=0.9,
                                  evidence="e", suggested_fix="", checker="alt"),
        )

    second = _dispatch(world, requests, FakeTrigger(world))

    assert len(second.from_cache) == 2          # the first two are answered
    assert len(second.dispatched) == 2          # the remainder now fits under the cap
    assert second.complete is True


def test_the_default_cap_applies_when_the_tenant_has_configured_nothing(world):
    assert caps_for(world["tenant"].id) == (DEFAULT_MAX_JUDGMENTS_PER_RUN, None)


def test_a_cap_of_zero_is_a_kill_switch_not_a_fallback_to_the_default(world):
    """Someone setting the cap to 0 means "judge nothing for now". Treating that as "unset"
    would start exactly the runs they were trying to stop."""
    _set_caps(world, judgments=0)
    trigger = FakeTrigger(world)

    result = _dispatch(world, [_request(), _request(html="<img src='b'>")], trigger)

    assert caps_for(world["tenant"].id)[0] == 0
    assert trigger.calls == [] and len(result.deferred) == 2 and result.complete is False


def test_dispatch_defaults_to_the_platforms_own_phase_trigger(world, monkeypatch):
    """The production path. Every other test injects a fake, so without this the real wiring —
    dispatch reaching `trigger_phase`, the same seam every agent run goes through — would
    never be exercised at all."""
    import orchestration.trigger as trigger_module

    spy = FakeTrigger(world)
    monkeypatch.setattr(trigger_module, "trigger_phase", spy)

    result = _dispatch(world, [_request()], trigger=None)

    assert len(spy.calls) == 1
    assert spy.calls[0]["agent_key"] == JUDGE_AGENT_KEY
    assert spy.calls[0]["auto_approve"] is True      # headless: findings are reviewed, not runs
    assert spy.calls[0]["execution_mode"] == "companion"
    assert result.run_id


def test_an_unconfigured_capability_is_still_capped(db):
    """A missing connection is not a reason to run uncapped."""
    tenant = Tenant.objects.create(name="NoConn")
    assert caps_for(tenant.id) == (DEFAULT_MAX_JUDGMENTS_PER_RUN, None)


def test_a_cached_row_describes_itself_usefully(world):
    row = record_verdict(
        tenant_id=world["tenant"].id, project_id=world["project"].id, run_id=None,
        content_hash="abcdef0123456789",
        judgment=A11yJudgment(criteria=("1.4.1",), verdict="fail", confidence=0.9,
                              evidence="e", suggested_fix="f", checker="color"),
    )
    assert str(row) == "a11y:color:fail (abcdef012345)"


def _set_caps(world, *, judgments=None, screens=None):
    conn = IntegrationConnection.objects.get(tenant=world["tenant"], capability="a11yai")
    scopes = {}
    if judgments is not None:
        scopes["max_judgments_per_run"] = judgments
    if screens is not None:
        scopes["max_screens_per_run"] = screens
    conn.scopes = scopes
    conn.save(update_fields=["scopes"])


# ── isolation: one tenant's cached verdicts are its own ──────────────
@pytest.mark.django_db(transaction=True)
def test_rls_hides_one_tenants_cached_verdicts_from_another():
    """Proven on a connection opened as the non-superuser app role — the Django test
    connection is the privileged migration role and bypasses RLS entirely."""
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    for tenant, mark in ((a, "A-secret"), (b, "B-secret")):
        project = Project.objects.create(tenant=tenant, name="p")
        A11yJudgmentCache.objects.create(
            tenant=tenant, project=project, checker="alt", content_hash=f"hash-{mark}",
            criteria=["1.1.1"], verdict="fail", confidence=0.9, evidence=mark,
        )

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT evidence FROM a11y_a11yjudgmentcache")
            assert cur.fetchall() == [("A-secret",)]

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM a11y_a11yjudgmentcache")
            assert cur.fetchone()[0] == 0        # no tenant context -> fail closed
    finally:
        raw.close()


def test_a_site_wide_element_is_asked_about_once_however_many_pages_carry_it(world):
    """The measured case, in miniature: one footer, seventeen pages, one question.

    This is the whole of Fix 1 in one assertion. Every page of a real site carries the same
    header, footer and nav, and the fingerprint is a hash of exactly what the judge is shown —
    so seventeen copies are seventeen requests and ONE question. They were all being asked.
    """
    _set_caps(world, judgments=200)
    footer = "<ul><li>Contact</li><li>Opening hours</li></ul>"
    requests = [_request(checker="semantics", route=f"/page-{i}", html=footer)
                for i in range(17)]

    result = _dispatch(world, requests, FakeTrigger(world))

    assert len(result.dispatched) == 1, "one question, asked once"
    assert result.deferred == []
    assert result.complete is True


def test_dropping_a_repeat_still_leaves_every_page_its_own_row(world):
    """Asking once must not mean reporting once — that would be trading one bug for another.

    The verdict is stored against the fingerprint, and `report.merge_run` walks every request
    the CAPTURE holds rather than the ones dispatched, looking each up by fingerprint. So the
    footer on page nine still gets its own row, on page nine, with page nine's selector. This
    pins the property that makes de-duplication safe rather than lossy.
    """
    from apps.a11y.dispatch import _distinct

    footer = "<ul><li>Contact</li></ul>"
    requests = [_request(checker="semantics", route=f"/page-{i}", html=footer)
                for i in range(3)]

    asked = _distinct(requests)

    assert len(asked) == 1
    assert asked[0] is requests[0], "first occurrence wins, so the order is stable"
    # The one answer is keyed on something all three share, which is why it reaches all three.
    assert len({r.content_hash for r in requests}) == 1


def test_two_different_questions_about_one_element_are_both_asked(world):
    """De-duplication is by QUESTION, never by element.

    A `<div role="button">` styled only in colour is both a semantics question and a colour
    question with different answers. The fingerprint includes the checker, so this is already
    true — pinned because a "de-duplicate the elements" refactor would silently halve the
    coverage of every multi-checker element and nothing else would notice.
    """
    from apps.a11y.dispatch import _distinct

    html = '<div role="button" style="color:red">Delete</div>'
    requests = [_request(checker="semantics", html=html), _request(checker="color", html=html)]

    assert len(_distinct(requests)) == 2
