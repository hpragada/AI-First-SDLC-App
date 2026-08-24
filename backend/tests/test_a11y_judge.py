"""QA-02a — the accessibility judge agent, its tools, and the coverage check.

What these prove, against the task's acceptance criteria:

  AC1  a batch of candidates produces one recorded finding per candidate
  AC2  a malformed call is rejected with a correctable message and never stored malformed
  AC3  fewer findings than candidates fails the run, naming the count
  AC4  the agent body passes the platform reference sweep — no local file paths, all I/O
       through platform capabilities
  AC5  a full batch, a malformed call and the under-reporting case are covered, ≥90%

Beyond the ACs, and deliberately:

  * **the agent never sees a content hash** — it echoes a short handle, because one wrong
    character in a 64-character hash files a verdict against a different element
  * **the checker comes from the batch, not the agent** — so a call cannot mislabel which
    check it was and slip past the criteria guard
  * **an unjudged element is recorded AND the run fails** (team, 2026-08-13): it still
    reaches a person, and a partial pass is never read as a complete one
  * every rejection is a `ValueError`, which the runner surfaces as a correctable 400 rather
    than a 500 an agent would read as "the platform is broken" and retry unchanged
"""
import re
from pathlib import Path

import pytest

from apps.a11y import judge
from apps.a11y.dispatch import element_handle
from apps.a11y.models import A11yJudgmentCache
from integrations.types import A11Y_CHECKER_CRITERIA, A11yCandidate

AGENT_BODY = (Path(__file__).resolve().parents[2] / "agents" / "09c_a11y_judge" / "agent.md")


# ── fixtures: a dispatched run with a real batch on it ───────────────
@pytest.fixture
def project(db):
    from apps.projects.models import Project
    from apps.registry.catalog import seed_agent_specs
    from apps.tenancy.models import Tenant

    tenant = Tenant.objects.create(name="Judge Co")
    proj = Project.objects.create(tenant=tenant, name="Storefront")
    seed_agent_specs(tenant)          # includes 09c_a11y_judge, from the catalog
    return tenant, proj


def _run_for(tenant, proj, agent_key, batches=None):
    """A Run as `trigger_phase` would create it. `Run` carries no phase column — the phase
    travels on `AgentRunInput`, which is what the completeness check reads."""
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    spec = AgentSpec.objects.get(tenant=tenant, key=agent_key)
    item = WorkItem.objects.create(tenant=tenant, project=proj, title="Judge a11y")
    return Run.objects.create(
        tenant=tenant, work_item=item, agent_spec=spec,
        engine="claude", model="claude-sonnet-4-6", prompt_version="v6-migrated",
        inputs={"a11y_batches": batches} if batches is not None else {},
    )


@pytest.fixture
def run(project):
    """A judgment run carrying two screens' worth of dispatched elements."""
    from apps.a11y.dispatch import A11yRequest, _group_by_screen

    tenant, proj = project
    requests = [
        A11yRequest(checker="alt", candidate=A11yCandidate(
            selector="img.hero", html="<img src='h.png' alt='image'>",
            context="hero banner", route="/home", screenshot_ref="s3://shots/hero.png")),
        A11yRequest(checker="semantics", candidate=A11yCandidate(
            selector="div.cta", html="<div class='cta' onclick='buy()'>Buy</div>",
            context="checkout call to action", route="/home")),
        A11yRequest(checker="label", candidate=A11yCandidate(
            selector="button#pay", html="<button aria-label='Purchase'>Buy now</button>",
            context="payment", route="/checkout")),
    ]
    row = _run_for(tenant, proj, "09c_a11y_judge", batches=_group_by_screen(requests))
    return tenant, proj, row, requests


def ids_of(run_fixture) -> list[str]:
    """Every element id in the run — paging through, the way the judge now has to."""
    tenant, _proj, row, _requests = run_fixture
    ids, start = [], 0
    while start is not None:
        batch = judge.batch_for_run(tenant.id, row.id, start=start)
        ids += [e["id"] for screen in batch["screens"] for e in screen["elements"]]
        start = batch["next_start"]
    return ids


def report(run_fixture, element_id, **kwargs):
    tenant, proj, row, _ = run_fixture
    # `suggested_fix` is not decoration here: since QA-03 a failing `alt` finding must propose
    # the replacement text, because "your alt is wrong" does not tell a developer what to
    # write. See `apps.a11y.checkers.schema` and tests/test_a11y_checkers.py.
    payload = {"criteria": ["1.1.1"], "verdict": "fail", "confidence": 0.9,
               "evidence": "alt is 'image', which says nothing about what it shows",
               "suggested_fix": "Sales rose steadily through 2025, peaking in Q4"}
    payload.update(kwargs)
    return judge.record_finding(
        tenant_id=tenant.id, run_id=row.id, project_id=proj.id,
        element_id=element_id, **payload)


# ── the element handle ───────────────────────────────────────────────
def test_the_handle_is_readable_and_a_typo_is_loud():
    """`e1` mistyped is another valid element; this mistyped is almost certainly none."""
    handle = element_handle(3, "a91f0c2e" + "0" * 56)
    assert handle == "3-a91f0c2e"
    assert re.fullmatch(r"\d+-[0-9a-f]{8}", handle)


def test_two_identical_elements_on_one_page_get_different_handles():
    same_hash = "b" * 64
    assert element_handle(1, same_hash) != element_handle(2, same_hash)


# ── what the agent reads ─────────────────────────────────────────────
def test_the_batch_hands_over_one_screen_at_a_time(run):
    """One screen per call, never two — an element's meaning depends on the page around it,
    and a slice spanning two pages would hand the judge half of each."""
    tenant, _proj, row, requests = run
    first = judge.batch_for_run(tenant.id, row.id)
    assert [screen["route"] for screen in first["screens"]] == ["/home"]
    assert len(first["screens"][0]["elements"]) == 2
    assert first["screen"]["index"] == 1 and first["screen"]["of"] == 2
    assert first["screen"]["continues"] is False

    second = judge.batch_for_run(tenant.id, row.id, start=first["next_start"])
    assert [screen["route"] for screen in second["screens"]] == ["/checkout"]
    assert second["next_start"] is None, "the last page says so"


def test_the_contract_is_the_whole_run_on_every_page(run):
    """`total_elements` must never shrink to the size of the page in hand. It is the number the
    judge checks itself against — every dispatched element gets exactly one verdict — and a
    count that tracked the current slice would quietly redefine what 'all of them' means."""
    tenant, _proj, row, requests = run
    start, seen = 0, 0
    while start is not None:
        batch = judge.batch_for_run(tenant.id, row.id, start=start)
        assert batch["total_elements"] == len(requests)
        seen += batch["returned"]
        start = batch["next_start"]
    assert seen == len(requests), "paging must reach every element exactly once"


def test_a_crowded_screen_is_split_and_says_it_continues(run):
    """The home page on our own reference app carried 37 elements to every other page's 12.
    A screen bigger than the cap is split, and the judge is told the page is not finished —
    otherwise it reads a partial screen as the whole of it."""
    tenant, _proj, row, _requests = run
    first = judge.batch_for_run(tenant.id, row.id, max_elements=1)
    assert first["returned"] == 1
    assert first["screen"]["route"] == "/home"
    assert first["screen"]["continues"] is True, "this screen has more to come"
    assert first["screen"]["elements_on_screen"] == 2
    assert first["screen"]["offset"] == 0

    rest = judge.batch_for_run(tenant.id, row.id, start=first["next_start"], max_elements=1)
    assert rest["screen"]["route"] == "/home", "still the same screen, not the next one"
    assert rest["screen"]["offset"] == 1
    assert rest["screen"]["continues"] is False


def test_paging_past_the_end_is_an_empty_page_not_an_error(run):
    tenant, _proj, row, requests = run
    out = judge.batch_for_run(tenant.id, row.id, start=999)
    assert out["screens"] == [] and out["returned"] == 0
    assert out["next_start"] is None
    assert out["total_elements"] == len(requests), "the contract still reads true"


def test_the_agent_never_sees_a_content_hash(run):
    """One wrong character copying a 64-char hash files a verdict against another element."""
    tenant, _proj, row, _ = run
    batch = judge.batch_for_run(tenant.id, row.id)
    for screen in batch["screens"]:
        for element in screen["elements"]:
            assert "content_hash" not in element
            assert {"id", "checker", "criteria", "selector", "html"} <= set(element)


def test_the_batch_carries_the_screenshot_pointer_not_an_image(run):
    """Pointer-not-body (#1/#3). Rendering it is the capture chain's job (QA-11b)."""
    tenant, _proj, row, _ = run
    element = judge.batch_for_run(tenant.id, row.id)["screens"][0]["elements"][0]
    assert element["screenshot_ref"] == "s3://shots/hero.png"


def test_a_run_that_is_not_a_judgment_run_has_no_batch(project):
    tenant, proj = project
    other = _run_for(tenant, proj, "01_ideation")
    assert judge.batch_for_run(tenant.id, other.id)["total_elements"] == 0


def test_an_unknown_run_is_a_correctable_error(project):
    import uuid

    tenant, _proj = project
    with pytest.raises(ValueError, match="no run"):
        judge.batch_for_run(tenant.id, uuid.uuid4())


# ── the rulebook ─────────────────────────────────────────────────────
def test_grounding_returns_the_standards_own_words(db):
    from apps.a11y.wcag import load_wcag

    load_wcag()
    out = judge.grounding_for(["1.1.1"])
    assert out["criteria"] == ["1.1.1"]
    assert "Non-text Content" in out["grounding"]
    # The defined terms the criterion leans on travel with it (QA-04).
    assert "non-text content" in out["grounding"].lower()


def test_grounding_covers_several_criteria_at_once(db):
    from apps.a11y.wcag import load_wcag

    load_wcag()
    out = judge.grounding_for(["1.3.1", "4.1.2"])
    assert "Info and Relationships" in out["grounding"]
    assert "Name, Role, Value" in out["grounding"]


def test_an_unknown_criterion_tells_the_agent_which_one(db):
    from apps.a11y.wcag import load_wcag

    load_wcag()
    with pytest.raises(ValueError, match="9.9.9"):
        judge.grounding_for(["1.1.1", "9.9.9"])


def test_grounding_needs_at_least_one_criterion():
    with pytest.raises(ValueError, match="at least one WCAG criterion"):
        judge.grounding_for([])


# ── AC1: one finding per candidate ───────────────────────────────────
def test_a_full_batch_records_one_finding_per_element(run):
    tenant, proj, row, requests = run
    handles = ids_of(run)
    # Evidence per checker rather than one generic line: since QA-03 a failing `label` finding
    # has to quote both the visible label and the accessible name it disagrees with.
    evidence_for = {
        "alt": "alt is 'image', which says nothing about what it shows",
        "semantics": "<div class='cta' onclick='buy()'>Buy</div> — nothing announces a control",
        "label": "visible label \"Buy now\", accessible name \"Purchase\"",
    }
    for handle, request in zip(handles, requests, strict=True):
        report(run, handle, criteria=[A11Y_CHECKER_CRITERIA[request.checker][0]],
               verdict="fail", confidence=0.9, evidence=evidence_for[request.checker])
    assert A11yJudgmentCache.objects.filter(
        tenant_id=tenant.id, project_id=proj.id, run_id=row.id).count() == len(requests)
    assert judge.verify_judgment_completeness(
        tenant_id=tenant.id, project_id=proj.id, run_id=row.id) == {
            "dispatched": 3, "judged": 3, "unjudged": []}


def test_a_finding_is_stamped_with_what_produced_it(run):
    """The model is read from the run, never from the agent's claim about itself."""
    tenant, proj, row, _ = run
    report(run, ids_of(run)[0])
    stored = A11yJudgmentCache.objects.get(tenant_id=tenant.id, run_id=row.id)
    assert (stored.engine, stored.model, stored.prompt_version) == (
        "claude", "claude-sonnet-4-6", "v6-migrated")


def test_the_checker_comes_from_the_batch_not_the_agent(run):
    """So a mislabelled call cannot slip past the guard on which criteria a checker owns."""
    tenant, _proj, row, _ = run
    semantics_handle = ids_of(run)[1]
    out = report(run, semantics_handle, criteria=["1.3.1", "4.1.2"],
                 evidence="a div with a click handler, no role and no name")
    assert out["checker"] == "semantics"
    assert A11yJudgmentCache.objects.get(
        tenant_id=tenant.id, run_id=row.id, checker="semantics").criteria == ["1.3.1", "4.1.2"]


def test_one_element_can_breach_two_criteria(run):
    """D-A11Y-2: a div dressed as a button breaks 1.3.1 and 4.1.2, and one fix repairs both."""
    out = report(run, ids_of(run)[1], criteria=["1.3.1", "4.1.2"],
                 evidence="<div onclick> with no role")
    assert out["criteria"] == ["1.3.1", "4.1.2"]


def test_reporting_the_same_element_twice_updates_it(run):
    """The retry after a rejection, and a resumed run, must not double-count."""
    tenant, proj, row, _ = run
    handle = ids_of(run)[0]
    report(run, handle, verdict="fail", confidence=0.9, evidence="first")
    report(run, handle, verdict="pass", confidence=0.95, evidence="second, on a better look")
    rows = A11yJudgmentCache.objects.filter(tenant_id=tenant.id, run_id=row.id)
    assert rows.count() == 1
    assert rows.first().verdict == "pass"


# ── AC2: malformed calls are rejected, never stored ──────────────────
def test_an_unknown_element_id_is_refused(run):
    tenant, _proj, row, _ = run
    with pytest.raises(ValueError, match="is not an element in this run"):
        report(run, "9-deadbeef")
    assert not A11yJudgmentCache.objects.filter(tenant_id=tenant.id, run_id=row.id).exists()


def test_reporting_against_a_run_with_no_batch_is_refused(project):
    """An agent pointed at the wrong run must not be able to file verdicts into it."""
    tenant, proj = project
    other = _run_for(tenant, proj, "01_ideation")
    with pytest.raises(ValueError, match="no accessibility elements to judge"):
        judge.record_finding(
            tenant_id=tenant.id, run_id=other.id, project_id=proj.id, element_id="1-abcdef12",
            criteria=["1.1.1"], verdict="fail", confidence=0.9, evidence="x")


def test_finding_the_project_from_an_unknown_run_is_refused(project):
    import uuid

    tenant, _proj = project
    with pytest.raises(ValueError, match="no run"):
        judge._project_for(tenant.id, uuid.uuid4())


def test_an_invalid_verdict_names_the_valid_ones(run):
    with pytest.raises(ValueError, match=r"verdict must be one of \['fail', 'pass'"):
        report(run, ids_of(run)[0], verdict="broken")


def test_a_verdict_is_coerced_for_case_and_whitespace(run):
    assert report(run, ids_of(run)[0], verdict="  FAIL ")["verdict"] == "fail"


def test_confidence_must_be_a_probability_not_a_percentage(run):
    with pytest.raises(ValueError, match="not a percentage"):
        report(run, ids_of(run)[0], confidence=95)


def test_confidence_must_be_a_number(run):
    with pytest.raises(ValueError, match="must be a number"):
        report(run, ids_of(run)[0], confidence="very")


def test_a_numeric_string_confidence_is_coerced(run):
    tenant, _proj, row, _ = run
    report(run, ids_of(run)[0], confidence="0.85")
    assert A11yJudgmentCache.objects.get(tenant_id=tenant.id, run_id=row.id).confidence == 0.85


def test_criteria_outside_what_the_element_was_queued_for_are_refused(run):
    """An alt check cannot report a contrast failure — it never looked at contrast."""
    with pytest.raises(ValueError, match=r"it cannot be judged against \['1.4.3'\]"):
        report(run, ids_of(run)[0], criteria=["1.1.1", "1.4.3"])


def test_naming_no_criteria_is_refused(run):
    with pytest.raises(ValueError, match="name the WCAG criteria"):
        report(run, ids_of(run)[0], criteria=[])


def test_a_failure_without_evidence_is_refused(run):
    """Rejected at the door so the agent supplies it, rather than stored unusable."""
    with pytest.raises(ValueError, match="needs evidence"):
        report(run, ids_of(run)[0], verdict="fail", evidence="   ")


def test_an_uncertain_verdict_also_needs_its_reason(run):
    with pytest.raises(ValueError, match="needs evidence"):
        report(run, ids_of(run)[0], verdict="uncertain", evidence="")


def test_a_pass_may_have_nothing_to_quote(run):
    assert report(run, ids_of(run)[0], verdict="pass", confidence=0.9,
                  evidence="")["verdict"] == "pass"


def test_nothing_malformed_is_ever_stored(run):
    """Every rejection above leaves the table exactly as it found it."""
    tenant, _proj, row, _ = run
    handle = ids_of(run)[0]
    for kwargs in ({"verdict": "broken"}, {"confidence": 42}, {"criteria": ["1.4.3"]},
                   {"verdict": "fail", "evidence": ""}):
        with pytest.raises(ValueError):
            report(run, handle, **kwargs)
    assert not A11yJudgmentCache.objects.filter(tenant_id=tenant.id, run_id=row.id).exists()


# ── AC3: under-reporting fails the run, loudly ───────────────────────
def test_an_unreported_element_fails_the_run_and_names_the_count(run):
    """31 of 40 reads as a clean pass — the worst thing this run could produce."""
    from orchestration.activities import WriteCompletenessError

    tenant, proj, row, _ = run
    report(run, ids_of(run)[0])
    with pytest.raises(WriteCompletenessError, match="judged 1 of 3"):
        judge.verify_judgment_completeness(
            tenant_id=tenant.id, project_id=proj.id, run_id=row.id)


def test_an_unreported_element_still_reaches_a_person(run):
    """Both halves of the team's decision: recorded as uncertain AND the run fails."""
    from orchestration.activities import WriteCompletenessError

    tenant, proj, row, _ = run
    report(run, ids_of(run)[0])
    with pytest.raises(WriteCompletenessError):
        judge.verify_judgment_completeness(
            tenant_id=tenant.id, project_id=proj.id, run_id=row.id)

    stored = A11yJudgmentCache.objects.filter(tenant_id=tenant.id, run_id=row.id)
    assert stored.count() == 3                       # nothing dispatched went missing
    unjudged = stored.filter(verdict="uncertain")
    assert unjudged.count() == 2
    assert all(judge.NOT_JUDGED in row_.evidence for row_ in unjudged)
    # Tagged with every criterion the checker covers: not knowing leaves all of them open.
    assert sorted(unjudged.get(checker="semantics").criteria) == ["1.3.1", "4.1.2"]


def test_the_failure_message_lists_the_elements(run):
    from orchestration.activities import WriteCompletenessError

    tenant, proj, row, _ = run
    with pytest.raises(WriteCompletenessError) as exc:
        judge.verify_judgment_completeness(
            tenant_id=tenant.id, project_id=proj.id, run_id=row.id)
    for handle in ids_of(run):
        assert handle in str(exc.value)


def test_a_run_with_nothing_dispatched_is_not_a_failure(project):
    tenant, proj = project
    other = _run_for(tenant, proj, "01_ideation")
    assert judge.verify_judgment_completeness(
        tenant_id=tenant.id, project_id=proj.id, run_id=other.id)["dispatched"] == 0


def test_completeness_finds_the_project_itself_when_not_given_one(run):
    """Taken from the run, so a verdict can never be filed against another project."""
    tenant, _proj, row, _ = run
    for handle, checker in zip(ids_of(run), ["alt", "semantics", "label"], strict=True):
        report(run, handle, criteria=list(A11Y_CHECKER_CRITERIA[checker]),
               verdict="uncertain", evidence="not enough to go on")
    assert judge.verify_judgment_completeness(
        tenant_id=tenant.id, run_id=row.id)["judged"] == 3


# ── the completeness check is wired to the run's phase ───────────────
def test_the_judge_phase_uses_the_coverage_check_not_the_artifact_check(run):
    """Without this branch every judgment run would fail: it registers no artifacts at all."""
    from orchestration.activities import A11Y_JUDGE_PHASE, verify_write_completeness_core
    from orchestration.types import AgentRunInput

    tenant, proj, row, _ = run
    assert A11Y_JUDGE_PHASE == judge.JUDGE_PHASE == "a11y_judge"
    for handle, checker in zip(ids_of(run), ["alt", "semantics", "label"], strict=True):
        report(run, handle, criteria=list(A11Y_CHECKER_CRITERIA[checker]),
               verdict="pass", confidence=0.95, evidence="looks right")

    out = verify_write_completeness_core(
        AgentRunInput(run_id=str(row.id), tenant_id=str(tenant.id), project_id=str(proj.id),
                      work_item_id=str(row.work_item_id), agent_spec_id=str(row.agent_spec_id),
                      phase=judge.JUDGE_PHASE),
        expected_types=[],
    )
    assert out == {"present": ["3 judged"], "expected": ["3 dispatched"]}


def test_the_judge_phase_check_fails_an_incomplete_run(run):
    from orchestration.activities import WriteCompletenessError, verify_write_completeness_core
    from orchestration.types import AgentRunInput

    tenant, proj, row, _ = run
    with pytest.raises(WriteCompletenessError, match="judged 0 of 3"):
        verify_write_completeness_core(
            AgentRunInput(run_id=str(row.id), tenant_id=str(tenant.id),
                          project_id=str(proj.id), work_item_id=str(row.work_item_id),
                          agent_spec_id=str(row.agent_spec_id), phase=judge.JUDGE_PHASE),
            expected_types=[],
        )


# ── the agent is registered and dispatchable ─────────────────────────
def test_the_judge_is_in_the_catalog_as_a_native_agent():
    from apps.registry.catalog import ACTIVE_AGENT_CATALOG

    entry = next(d for d in ACTIVE_AGENT_CATALOG if d.key == "09c_a11y_judge")
    assert entry.native is True                 # no legacy v6 body to migrate
    assert entry.legacy_body_file == ""
    assert entry.phase_label == judge.JUDGE_PHASE
    assert entry.body_ref == "agents/09c_a11y_judge/agent.md"
    assert entry.rides_build is False           # it judges; it writes no code


def test_dispatch_finds_the_judge_once_it_is_seeded(run):
    """QA-02 reported "no judge registered" until now; this is the path flipping over."""
    from apps.a11y.dispatch import judge_available

    tenant, proj, _row, _ = run
    assert "no 09c_a11y_judge agent" not in judge_available(tenant.id, proj.id)


def test_the_three_tools_are_granted_to_the_companion():
    """A tool the platform exposes but never grants is a tool the agent cannot call."""
    from runner.companion.runner import BUILD_STATE_TOOLS

    assert {"get_a11y_batch", "get_wcag_grounding",
            "record_a11y_finding"} <= set(BUILD_STATE_TOOLS)


def test_the_three_tools_are_reachable_over_the_state_route():
    from api.runner_views import _BUILD_STATE_TOOLS

    assert {"get_a11y_batch", "get_wcag_grounding",
            "record_a11y_finding"} <= set(_BUILD_STATE_TOOLS)


# ── AC4: the agent body passes the reference sweep ───────────────────
def test_the_agent_body_exists_and_is_substantial():
    assert AGENT_BODY.exists()
    assert len(AGENT_BODY.read_text(encoding="utf-8").split()) > 800


def test_the_agent_body_names_no_local_files():
    """§8 reference sweep: a migrated or authored body naming a local path is a failure."""
    body = AGENT_BODY.read_text(encoding="utf-8")
    for forbidden in ("tasks.md", "requirements.md", "CLAUDE.md", "docs/", "./", "../",
                      "legacy_suite", ".claude/"):
        assert forbidden not in body, forbidden


def test_the_agent_body_uses_only_platform_tools():
    body = AGENT_BODY.read_text(encoding="utf-8")
    for tool in ("get_a11y_batch", "get_wcag_grounding", "record_a11y_finding"):
        assert tool in body
    # Its whole job is the checkers and the criteria they own.
    for checker in A11Y_CHECKER_CRITERIA:
        assert checker in body
    for criterion in ("1.1.1", "1.3.1", "4.1.2", "1.4.1", "2.5.3"):
        assert criterion in body


def test_the_agent_body_carries_the_guardrails_that_make_it_safe():
    body = AGENT_BODY.read_text(encoding="utf-8").lower()
    assert "never guess" in body                      # uncertainty is an answer
    assert "uncertain" in body
    assert "evidence" in body
    assert "one call per element" in body             # the coverage contract


# ── the check that finishes the run needs longer than a presence check ──────────


def test_the_long_verify_phases_are_the_real_phase_keys():
    """`LONG_VERIFY_PHASES` lives in the Django-free workflow module, so it holds STRINGS rather
    than importing these constants. That is the right call and it is also how a key silently
    stops matching — rename `JUDGE_PHASE` and the timeout quietly reverts to one minute, with
    the only symptom a run that fails after doing all its work. Asserted here instead."""
    from apps.a11y.journey import JOURNEY_PHASE
    from apps.a11y.judge import JUDGE_PHASE
    from orchestration.build_types import LONG_VERIFY_PHASES

    assert JUDGE_PHASE in LONG_VERIFY_PHASES
    assert JOURNEY_PHASE in LONG_VERIFY_PHASES


def test_the_judge_phase_gets_the_longer_verification_window():
    """One minute was sized for "does the artifact exist"; this branch writes a fallback verdict
    per unanswered element and then publishes a report. Cancelled part-way it wrote 81 of 144
    fallbacks and left 63 elements with none — the exact thing the branch exists to prevent."""
    import inspect

    from orchestration import workflows

    source = inspect.getsource(workflows)
    assert "LONG_VERIFY_PHASES else 1" in source, (
        "verify_writes must take its timeout from the phase, not a flat one minute"
    )


# ── a judging run that DIED still has to account for itself ─────────────────
#
# The workflow returns at its `phase_failed` branch BEFORE `verify_writes`, which is where the
# judge's accounting lives. So everything below is about the path a crashed engine takes: the
# elements it never answered, the report nobody would otherwise see, and the audit that would
# otherwise read "Checking what was found" for ever. Yesterday's live run ended exactly here.


def _judging_audit(tenant, proj, judge_run, routes=("/home", "/checkout")):
    """A baseline audit whose capture this judging run was dispatched about."""
    from apps.a11y.aipass import _remember_source_run
    from apps.a11y.models import A11yBaselineAudit

    audit = A11yBaselineAudit.objects.create(
        tenant=tenant, project=proj, base_url="http://localhost:4180",
        routes=list(routes), status=A11yBaselineAudit.Status.JUDGING,
    )
    _remember_source_run(tenant.id, str(judge_run.id), str(audit.id))
    return audit


def test_a_judging_run_that_died_files_every_element_it_never_answered(run):
    """Nothing dispatched may vanish. One of three was judged before the engine went; the other
    two must reach a person as `uncertain`, not disappear from the record."""
    from apps.a11y.aipass import close_unfinished_ai_pass

    tenant, proj, row, _ = run
    answered = ids_of(run)[0]
    report(run, answered, verdict="pass", confidence=0.95)

    out = close_unfinished_ai_pass(tenant_id=tenant.id, run_id=row.id)

    assert out["accounted"] is False, "it did not finish, and must not claim it did"
    assert "2 were never reported on" in out["reason"]
    stored = {j.content_hash: j for j in A11yJudgmentCache.objects.filter(
        tenant=tenant, project=proj, run_id=row.id)}
    assert len(stored) == 3, "one judged, two filed — none lost"
    assert sum(1 for j in stored.values() if j.verdict == "uncertain") == 2


def test_a_judging_run_that_died_completes_the_audit_it_was_about(run):
    """The audit is CLOSED, not left mid-sentence. `Checking what was found` for ever is the
    same lie as a clean report: it states work that is not happening."""
    from apps.a11y.aipass import close_unfinished_ai_pass
    from apps.a11y.models import A11yBaselineAudit

    tenant, proj, row, _ = run
    audit = _judging_audit(tenant, proj, row)

    close_unfinished_ai_pass(tenant_id=tenant.id, run_id=row.id)

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.COMPLETE


def test_the_failed_run_path_is_what_actually_calls_it(run):
    """The wiring, not the function. `close_unfinished_ai_pass` existing changes nothing unless
    the path a crashed run takes reaches it — and the journey's identical closure had sat one
    line away on that path since G6a without the judge's ever being added beside it."""
    from apps.a11y.models import A11yBaselineAudit
    from orchestration.activities import fail_run_core
    from orchestration.types import AgentRunInput

    tenant, proj, row, _ = run
    audit = _judging_audit(tenant, proj, row)

    fail_run_core(
        AgentRunInput(
            run_id=str(row.id), tenant_id=str(tenant.id), project_id=str(proj.id),
            work_item_id=str(row.work_item_id), agent_spec_id=str(row.agent_spec_id),
            phase="a11y_judge", auto_approve=True,
        ),
        "the engine session ended before the judging finished",
    )

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.COMPLETE
    assert A11yJudgmentCache.objects.filter(
        tenant=tenant, run_id=row.id, verdict="uncertain").count() == 3, (
        "every element it was given, filed for a person")


def test_a_failed_run_that_judged_nothing_is_left_completely_alone(project):
    """A no-op for every other phase in the platform — which is the price of putting it on the
    shared failure path, and has to be paid rather than assumed."""
    from apps.a11y.models import A11yBaselineAudit
    from orchestration.activities import fail_run_core
    from orchestration.types import AgentRunInput

    tenant, proj = project
    row = _run_for(tenant, proj, "02_requirements")
    audit = A11yBaselineAudit.objects.create(
        tenant=tenant, project=proj, routes=["/"],
        status=A11yBaselineAudit.Status.JUDGING)

    fail_run_core(
        AgentRunInput(
            run_id=str(row.id), tenant_id=str(tenant.id), project_id=str(proj.id),
            work_item_id=str(row.work_item_id), agent_spec_id=str(row.agent_spec_id),
            phase="02_requirements",
        ),
        "the branch would not build",
    )

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.JUDGING, (
        "an unrelated phase failing must not close somebody's audit")
    assert A11yJudgmentCache.objects.filter(tenant=tenant).count() == 0
