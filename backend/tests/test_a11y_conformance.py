"""QA-24 — the conformance statement, and the positive evidence it is compiled from.

Against the task's acceptance criteria:

  AC1  a per-criterion view with rule/AI/human provenance
  AC2  editing and signing produces a signed artifact, audit-logged with model + prompt versions
  AC3  export without a human signature is refused
  AC4  >= 90% coverage on new code

**The tests that matter most are about what the platform is allowed to SAY.** A conformance
statement is made almost entirely of positive claims, and until this task every engine threw its
positive result away — the scanner returned only `violations`, the ledger recorded only
`failure`/`needs_review`, and the journey path returned early on anything that was not a
problem. So "checked and clean" and "nobody looked" were the same silence, three times over.

  * `test_a_criterion_nothing_looked_at_is_never_folded_into_a_pass` — the failure this whole
    document could die of.
  * `test_all_three_engines_record_what_they_saw` — the fix, asserted for each engine.
  * `test_the_platform_declines_to_suggest_when_a_check_could_not_decide` — the platform does
    not put a word in a reviewer's mouth.
"""
from __future__ import annotations

import pytest

from apps.a11y import coverage
from apps.a11y.capture import CaptureError, parse_capture
from apps.a11y.conformance import (
    DISCLAIMER,
    DOES_NOT,
    NOT_APPLICABLE,
    NOT_EVALUATED,
    PARTIALLY,
    SUPPORTS,
    ConformanceError,
    ConformanceRoleError,
    check_export,
    criterion_rows,
    draft_body,
    evidence_fingerprint,
    provenance,
    save_draft,
    sign,
    state,
    suggest,
    totals,
)
from apps.a11y.findings import record_run_findings
from apps.a11y.models import (
    A11yConformanceStatement,
    A11yCriterionCoverage,
    A11yFinding,
    A11yScreenScan,
    WcagCriterion,
)
from apps.a11y.report import SOURCE_AI, MergedReport, ReportRow
from apps.a11y.review import CONFIRM, adjudicate
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_UNCERTAIN

#: The real standard is already loaded platform-wide by a migration, so these tests run against
#: all 55 Level A and AA criteria rather than a convenient subset. That is the point: a
#: conformance table is only trustworthy if it is complete, and a test on five rows would not
#: notice the fifty it forgot.
ALL_AA = 55

#: The handful the assertions name, with what they are for.
CRITERIA = [
    ("1.1.1", "Non-text Content", "A"),
    ("1.3.1", "Info and Relationships", "A"),
    ("1.4.3", "Contrast (Minimum)", "AA"),
    ("2.1.2", "No Keyboard Trap", "A"),
    ("3.3.7", "Redundant Entry", "A"),
]


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Payment Gateway v2")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    aisha = User.objects.create_user(email="aisha@acme.test", name="Aisha Khan", tenant=tenant)
    dev = User.objects.create_user(email="dev@acme.test", name="Dana Ops", tenant=tenant)
    Membership.objects.create(tenant=tenant, project=project, user=aisha, role="qa_lead")
    Membership.objects.create(tenant=tenant, project=project, user=dev, role="engineer")
    for number, handle, level in CRITERIA:
        WcagCriterion.objects.get_or_create(
            version="2.2", number=number,
            defaults={"handle": handle, "level": level, "slug": number, "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "story": story, "aisha": aisha, "dev": dev}


def _cover(world, criterion, outcome, *, route="/checkout", engine="rule", detail="a-rule"):
    """One engine's observation about one criterion on one page.

    **Name the engine that OWNS the criterion whenever the test wants a positive result.**
    Since 27 August a positive claim also has to come from the engine `ownership.json` gives
    the criterion to, so a `rule` pass on an AI-owned criterion correctly settles nothing --
    axe proving an alt attribute EXISTS is not the AI judging it MEANINGFUL, which is the
    1.2.2 captions bug in miniature. Tests below that are about something else and happen to
    need a pass therefore say `engine="AI"` for 1.1.1. Whether the guard itself is right is
    `test_a11y_conformance_guard.py`'s question, not theirs.
    """
    coverage.record(tenant_id=world["t"], project_id=world["p"], run_key="k1", route=route,
                    engine=engine, observations=[(criterion, outcome, detail)])


def _sign(world, **over):
    kwargs = {"tenant_id": world["t"], "project_id": world["p"], "user_id": world["aisha"].id,
              "name": "Aisha Khan", "acknowledged": True}
    kwargs.update(over)
    return sign(**kwargs)


# ===========================================================================================
# The capture: all four axe channels, and the scanner that produced them
# ===========================================================================================

def _capture_doc(**over) -> str:
    import json

    screen = {
        "route": "/checkout",
        "elements": [],
        "axe_violations": [{"rule": "color-contrast", "criteria": ["1.4.3"], "nodes": ["a"]}],
        "axe_passes": [{"rule": "image-alt", "criteria": ["1.1.1"]}],
        "axe_inapplicable": [{"rule": "video-caption", "criteria": ["1.2.2"]}],
        "axe_incomplete": [{"rule": "aria-hidden-focus", "criteria": ["1.3.1"], "nodes": ["b"]}],
        "scanner_version": "axe-core 4.13.0",
    }
    screen.update(over)
    return json.dumps({"version": 1, "screens": [screen]})


def test_the_capture_carries_all_four_channels_not_just_the_failures():
    """The headline fix. Until QA-24 only `violations` survived the trip."""
    screen = parse_capture(_capture_doc())[0]
    assert [v["rule"] for v in screen["axe_violations"]] == ["color-contrast"]
    assert [p["rule"] for p in screen["axe_passes"]] == ["image-alt"]
    assert [i["rule"] for i in screen["axe_inapplicable"]] == ["video-caption"]
    assert [i["rule"] for i in screen["axe_incomplete"]] == ["aria-hidden-focus"]
    assert screen["scanner_version"] == "axe-core 4.13.0"
    # The two channels a person has to go and look at keep their nodes; the other two do not.
    assert screen["axe_violations"][0]["nodes"] == ["a"]
    assert screen["axe_incomplete"][0]["nodes"] == ["b"]
    assert "nodes" not in screen["axe_passes"][0]


def test_an_old_capture_still_parses_and_claims_nothing():
    """An older companion sends only violations. That must read as "no positive evidence",
    never as "nothing passed" — the difference between an honest gap and a false claim."""
    doc = _capture_doc()
    import json

    payload = json.loads(doc)
    for key in ("axe_passes", "axe_inapplicable", "axe_incomplete", "scanner_version"):
        payload["screens"][0].pop(key)
    screen = parse_capture(json.dumps(payload))[0]
    assert screen["axe_passes"] == [] and screen["axe_inapplicable"] == []
    assert screen["axe_incomplete"] == [] and screen["scanner_version"] == ""
    assert coverage.from_scan(screen) == [("1.4.3", "failed", "color-contrast")]


def test_an_oversized_channel_is_refused_not_truncated():
    """Same discipline as `axe_violations`: a capture that silently lost half its results reads
    as a page with half as much checked."""
    with pytest.raises(CaptureError, match="over the limit"):
        parse_capture(_capture_doc(
            axe_passes=[{"rule": f"r{i}", "criteria": ["1.1.1"]} for i in range(401)]))
    with pytest.raises(CaptureError, match="not a list"):
        parse_capture(_capture_doc(axe_passes="lots"))


def test_a_screen_the_scanner_never_ran_on_produces_no_coverage():
    """`axe_error` means the page was seen but not measured. It must not appear in the coverage
    map as though it had been — that is D-A11Y-3 at the scale of a whole document."""
    screen = parse_capture(_capture_doc(axe_error="axe-core is not installed"))[0]
    assert coverage.from_scan(screen) == []


def test_the_four_channels_change_the_screen_identity():
    """A scanner upgrade that turns an `inapplicable` into a `pass` changes what the statement
    may claim, so it has to change the screen's fingerprint — exactly as a new violation does."""
    from apps.a11y.capture import fingerprint

    base = parse_capture(_capture_doc())[0]
    moved = parse_capture(_capture_doc(
        axe_passes=[{"rule": "image-alt", "criteria": ["1.1.1"]},
                    {"rule": "video-caption", "criteria": ["1.2.2"]}],
        axe_inapplicable=[]))[0]
    assert fingerprint(base) != fingerprint(moved)


# ===========================================================================================
# Coverage: the same fix, in all three engines
# ===========================================================================================

def test_all_three_engines_record_what_they_saw(world):
    """The scanner, the AI and the keyboard agent each used to drop their positive result in a
    different place. Asserted per engine, because fixing only axe would have covered 14 of 55."""
    _cover(world, "1.1.1", "passed", engine="rule", detail="image-alt")
    _cover(world, "1.3.1", "passed", engine="AI", detail="semantics")
    _cover(world, "2.1.2", "passed", engine="agentic", detail="keyboard")

    got = coverage.summary(world["t"], world["p"])
    assert got["1.1.1"]["engines"] == {"rule"}
    assert got["1.3.1"]["engines"] == {"AI"}
    assert got["2.1.2"]["engines"] == {"agentic"}
    assert {c: list(v["routes"].values()) for c, v in got.items()} == {
        "1.1.1": ["passed"], "1.3.1": ["passed"], "2.1.2": ["passed"]}


def test_worst_wins_when_one_criterion_is_seen_twice(world):
    """Several axe rules map to one criterion, so this happens constantly. A page where one rule
    passed and another failed has a failure — reporting the pass because it arrived second would
    be the report claiming conformance it was told it did not have."""
    coverage.record(
        tenant_id=world["t"], project_id=world["p"], run_key="k1", route="/checkout",
        engine="rule",
        observations=[("1.1.1", "passed", "image-alt"), ("1.1.1", "failed", "input-image-alt"),
                      ("1.1.1", "not_applicable", "area-alt")],
    )
    row = A11yCriterionCoverage.objects.get(criterion="1.1.1")
    assert row.outcome == "failed" and row.detail == "input-image-alt"


def test_needs_human_outranks_a_pass(world):
    coverage.record(
        tenant_id=world["t"], project_id=world["p"], run_key="k1", route="/checkout",
        engine="rule",
        observations=[("1.3.1", "passed", "a"), ("1.3.1", "needs_human", "aria-hidden-focus")],
    )
    assert A11yCriterionCoverage.objects.get(criterion="1.3.1").outcome == "needs_human"


def test_a_rule_with_no_wcag_tag_is_not_a_criterion_observation(world):
    """axe ships best-practice rules with no WCAG tag. They are not criteria and must not
    produce a coverage row nothing could ever read."""
    assert coverage.record(tenant_id=world["t"], project_id=world["p"], run_key="k1",
                           route="/x", engine="rule",
                           observations=[("", "passed", "region"), ("1.1.1", "banana", "x")]) == 0
    assert A11yCriterionCoverage.objects.count() == 0


def test_recording_the_same_capture_twice_does_not_stack_rows(world):
    for _ in range(3):
        _cover(world, "1.1.1", "passed")
    assert A11yCriterionCoverage.objects.count() == 1


def test_an_ai_pass_is_recorded_even_though_it_is_not_a_finding(world):
    """`RECORDED_OUTCOMES` deliberately keeps passes out of the findings ledger — a pass has no
    fingerprint, no defect and no reviewer. It is still evidence, and dropping it was what made
    every AI-owned criterion unclaimable."""
    run = Run.objects.create(
        tenant=world["tenant"], work_item=world["story"], temporal_workflow_id="w1",
        agent_spec=_spec(world))
    report = MergedReport(routes=["/checkout"], rows=[
        ReportRow(source=SOURCE_AI, outcome=TRIAGE_PASS, criteria=("1.3.1",), route="/checkout",
                  selector="main", evidence="fine", checker="semantics", verdict="pass",
                  confidence=0.95),
        ReportRow(source=SOURCE_AI, outcome=TRIAGE_FAILURE, criteria=("1.1.1",),
                  route="/checkout", selector="img.hero", evidence="no alt", checker="alt",
                  verdict="fail", confidence=0.95),
    ])
    record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=run.id,
                        report=report)

    assert A11yFinding.objects.count() == 1, "a pass is still not a finding"
    got = coverage.summary(world["t"], world["p"])
    assert got["1.3.1"]["routes"]["/checkout"] == "passed"
    assert got["1.1.1"]["routes"]["/checkout"] == "failed"


def test_a_capture_key_that_names_no_run_still_records_coverage(world):
    """QA-17's baseline audit partitions by its own id rather than manufacturing a `Run` nobody
    executed. Passing that key to a foreign key is how a real audit dies on an integrity error,
    and it is exactly what this build got wrong the first time."""
    import uuid

    audit_key = uuid.uuid4()
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=audit_key,
        report=MergedReport(routes=["/checkout"], rows=[
            ReportRow(source=SOURCE_AI, outcome=TRIAGE_PASS, criteria=("1.3.1",),
                      route="/checkout", selector="main", evidence="fine", checker="semantics",
                      verdict="pass", confidence=0.95)]))

    row = A11yCriterionCoverage.objects.get(criterion="1.3.1")
    assert row.run_id is None, "no run to point at, and none invented"
    assert row.run_key == str(audit_key), "the key still travels"


def _spec(world):
    from apps.registry.models import AgentSpec

    return AgentSpec.objects.create(tenant=world["tenant"], key="09b_test_automation",
                                    body_ref="x", semver="1.0.0")


# ===========================================================================================
# AC1 — the per-criterion view
# ===========================================================================================

def test_every_criterion_in_the_standard_is_listed(world):
    """All of them, not only the interesting ones. A criterion quietly missing from a
    conformance table reads as a criterion that was fine."""
    rows = criterion_rows(world["t"], world["p"])
    assert len(rows) == ALL_AA, "all 55 Level A and AA criteria, not only the interesting ones"
    numbers = [r["criterion"] for r in rows]
    assert numbers == sorted(numbers, key=lambda n: [int(p) for p in n.split(".")]),         "numeric order — sorting text puts 1.4.10 before 1.4.2"
    assert {c[0] for c in CRITERIA} <= set(numbers)
    assert all(r["effective"] == NOT_EVALUATED for r in rows), "nothing has run yet"
    assert {r["level"] for r in rows} == {"A", "AA"}, "AAA is out of scope and stays out"


def test_a_criterion_nothing_looked_at_is_never_folded_into_a_pass(world):
    """The failure this whole document could die of."""
    _cover(world, "1.1.1", "passed", engine="AI", detail="alt judged meaningful")
    rows = {r["criterion"]: r for r in criterion_rows(world["t"], world["p"])}
    assert rows["1.1.1"]["effective"] == SUPPORTS
    assert rows["3.3.7"]["effective"] == NOT_EVALUATED
    assert rows["3.3.7"]["evidence"] == "Nothing checked this."
    assert rows["3.3.7"]["established_by"] == []
    counts = totals(criterion_rows(world["t"], world["p"]))
    assert counts["evaluated"] == 1 and counts[NOT_EVALUATED] == ALL_AA - 1


def test_the_row_says_what_happened_with_no_verdict_in_it(world):
    """*Whatever the platform tests and captures, shown as it was.* The evidence column never
    says "supports" — it says what was checked, where, and what came back."""
    _cover(world, "1.4.3", "passed", route="/checkout")
    _cover(world, "1.4.3", "passed", route="/dashboard")
    _cover(world, "1.4.3", "failed", route="/expenses")
    row = {r["criterion"]: r for r in criterion_rows(world["t"], world["p"])}["1.4.3"]
    assert "Failed on 1 of 3 pages checked" in row["evidence"]
    assert "checked on 2 pages with nothing wrong" in row["evidence"]
    assert row["routes_checked"] == 3


def test_provenance_names_the_engines_that_actually_looked(world):
    """AC1's rule/AI/human column, read from what produced the evidence rather than from what
    the ownership table expects to produce it."""
    _cover(world, "1.1.1", "passed", engine="rule")
    _cover(world, "1.1.1", "failed", engine="AI", route="/dashboard")
    rows = {r["criterion"]: r for r in criterion_rows(world["t"], world["p"])}
    assert rows["1.1.1"]["established_by"] == ["AI", "rule"]


def test_a_human_decision_shows_as_human_provenance(world):
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             temporal_workflow_id="w1", agent_spec=_spec(world))
    record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=run.id,
                        report=MergedReport(routes=["/checkout"], rows=[
                            ReportRow(source=SOURCE_AI, outcome=TRIAGE_REVIEW,
                                      criteria=("1.1.1",), route="/checkout",
                                      selector="img.hero", evidence="unsure",
                                      checker="alt", verdict=A11Y_UNCERTAIN, confidence=0.4,
                                      content_hash="h1")]))
    adjudicate(tenant_id=world["t"], project_id=world["p"],
               finding_id=str(A11yFinding.objects.get().id), user_id=world["aisha"].id,
               decision=CONFIRM)
    row = {r["criterion"]: r for r in criterion_rows(world["t"], world["p"])}["1.1.1"]
    assert "human" in row["established_by"]
    assert row["human_decisions"] == 1
    assert "1 reviewed by a person" in row["evidence"]


# ===========================================================================================
# The suggestion — and where the platform declines to make one
# ===========================================================================================

def test_the_platform_declines_to_suggest_when_a_check_could_not_decide(world):
    """`None` is the platform refusing to put a word in a reviewer's mouth."""
    assert suggest({"routes": {"/a": "needs_human"}}, 0) is None
    assert suggest({"routes": {"/a": "passed", "/b": "needs_human"}}, 0) is None

    _cover(world, "1.3.1", "needs_human")
    row = {r["criterion"]: r for r in criterion_rows(world["t"], world["p"])}["1.3.1"]
    assert row["suggested"] is None
    assert row["needs_a_person"] is True
    assert row["effective"] == NOT_EVALUATED, "unanswered is not a claim"
    assert totals(criterion_rows(world["t"], world["p"]))["awaiting_a_person"] == 1


def test_the_suggestion_follows_the_evidence(world):
    """The evidence-to-verdict mapping, on a criterion whose own decider did the looking.

    `owner` and `engines` are supplied on the positive cases and omitted on the rest, and that
    asymmetry is the point of QA-25's guard: a failure is a fact whoever proved it, while a
    positive claim may only be made by the engine the registry says can settle the criterion.
    See `test_a11y_conformance_guard` for the whole rule.
    """
    rule_looked = {"routes": {"/a": "passed"}, "engines": {"rule"}}
    assert suggest(rule_looked, 0, owner="rule") == SUPPORTS
    assert suggest({"routes": {"/a": "not_applicable"}, "engines": {"rule"}},
                   0, owner="rule") == NOT_APPLICABLE
    assert suggest({"routes": {"/a": "failed"}}, 0) == DOES_NOT
    assert suggest({"routes": {"/a": "failed", "/b": "passed"}}, 0) == PARTIALLY
    assert suggest({}, 0) == NOT_EVALUATED
    assert suggest(None, 0) == NOT_EVALUATED


def test_an_open_failure_outranks_a_clean_coverage_map(world):
    """A failure survives the run that found it; coverage is a fact about one capture. A
    criterion with an open Level A defect must never read as "supports" because the latest run
    happened not to revisit that page."""
    assert suggest({"routes": {"/a": "passed"}}, 3) == PARTIALLY
    assert suggest({"routes": {"/a": "failed"}}, 3) == DOES_NOT
    assert suggest({}, 3) == DOES_NOT


def test_the_reviewers_word_always_wins(world):
    _cover(world, "1.1.1", "passed", engine="AI", detail="alt judged meaningful")
    rows = criterion_rows(world["t"], world["p"],
                          verdicts={"1.1.1": {"level": PARTIALLY, "note": "only on desktop"}})
    row = {r["criterion"]: r for r in rows}["1.1.1"]
    assert row["suggested"] == SUPPORTS
    assert row["verdict"] == PARTIALLY and row["effective"] == PARTIALLY


def test_a_nonsense_level_from_a_client_is_ignored_not_stored(world):
    rows = criterion_rows(world["t"], world["p"], verdicts={"1.1.1": {"level": "totally_fine"}})
    assert {r["criterion"]: r for r in rows}["1.1.1"]["verdict"] is None
    with pytest.raises(ConformanceError, match="isn't a conformance level"):
        save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
                   verdicts={"1.1.1": {"level": "totally_fine"}})


# ===========================================================================================
# The document
# ===========================================================================================

def test_the_draft_keeps_the_risk_reduction_wording(world):
    _cover(world, "1.1.1", "passed")
    rows = criterion_rows(world["t"], world["p"])
    body = draft_body(scope="Payment Gateway v2", rows=rows)
    assert "risk reduction, not certification" in body
    assert DISCLAIMER in body
    assert "were not" in body and "not counted as supported" in body
    for number, handle, _ in CRITERIA:
        assert f"{number} {handle}" in body, "every criterion appears, not only the failures"
    assert "Not evaluated" in body


def test_the_prose_and_the_table_cannot_disagree(world):
    _cover(world, "1.1.1", "passed")
    rows = criterion_rows(world["t"], world["p"])
    counts = totals(rows)
    body = draft_body(scope="x", rows=rows)
    assert f"**{counts['evaluated']} " in body and f"**{counts[NOT_EVALUATED]} were not**" in body


# ===========================================================================================
# AC2 — editing and signing
# ===========================================================================================

def test_only_the_accessibility_reviewer_may_edit_or_sign(world):
    with pytest.raises(ConformanceRoleError, match="QA Lead"):
        save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["dev"].id,
                   scope="mine now")
    with pytest.raises(ConformanceRoleError, match="QA Lead"):
        _sign(world, user_id=world["dev"].id)


def test_signing_records_the_person_the_wording_and_the_evidence(world):
    _cover(world, "1.1.1", "passed")
    out = _sign(world)
    assert out["signed"] is True and out["signed_name"] == "Aisha Khan"
    assert out["signed_role"] == "qa_lead" and out["signed_at"] is not None
    row = A11yConformanceStatement.objects.get()
    assert row.signed_body_hash and row.signed_evidence_hash
    assert row.signed_by_id == world["aisha"].id


def test_signing_needs_a_name_and_an_acknowledgement(world):
    with pytest.raises(ConformanceError, match="Sign with your name"):
        _sign(world, name="   ")
    with pytest.raises(ConformanceError, match="Confirm you have read"):
        _sign(world, acknowledged=False)
    assert A11yConformanceStatement.objects.filter(signed_at__isnull=False).count() == 0


def test_the_audit_entry_carries_the_versions_the_screen_never_shows(world):
    """AC2, and D-A11Y-96 in the same test: recorded, never displayed."""
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             temporal_workflow_id="w1", agent_spec=_spec(world))
    A11yScreenScan.objects.create(tenant=world["tenant"], project=world["project"],
                                  run_key=str(run.id), route="/checkout",
                                  scanner_version="axe-core 4.13.0")
    record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=run.id,
                        report=MergedReport(routes=["/checkout"], rows=[
                            ReportRow(source=SOURCE_AI, outcome=TRIAGE_FAILURE,
                                      criteria=("1.1.1",), route="/checkout", selector="img",
                                      evidence="no alt", checker="alt", verdict="fail",
                                      confidence=0.9, engine="claude", model="opus",
                                      prompt_version="v3")]))
    _sign(world)

    event = Event.objects.get(action="a11y.conformance.signed")
    assert event.actor == str(world["aisha"].id)
    assert event.payload["name"] == "Aisha Khan"
    assert event.payload["provenance"]["scanners"] == ["axe-core 4.13.0"]
    assert event.payload["provenance"]["judges"] == ["claude/opus/v3"]
    assert event.payload["body_hash"] and event.payload["evidence_hash"]
    assert "not_evaluated" in event.payload

    shown = state(tenant_id=world["t"], project_id=world["p"])
    assert "axe-core 4.13.0" not in str(shown), "recorded, never displayed (D-A11Y-96)"
    assert "opus" not in str(shown)
    assert provenance(world["t"], world["p"])["judges"] == ["claude/opus/v3"]


def test_signing_registers_and_approves_the_conformance_artifact(world):
    """B1 — the signature IS the gate. `approved` is the state the publish endpoint demands, so
    nothing reaches a system of record without a named human approval."""
    _cover(world, "1.1.1", "passed")   # something was checked — signing needs evidence (M7)
    _sign(world)
    artifact = Artifact.objects.get(type="conformance")
    assert artifact.status == Artifact.Status.APPROVED
    assert artifact.title == "Accessibility conformance statement"
    assert A11yConformanceStatement.objects.get().artifact_id == artifact.id


def test_editing_after_signing_clears_the_signature(world):
    """A signature on wording nobody signed is worse than no signature."""
    _cover(world, "1.1.1", "passed")   # something was checked — signing needs evidence (M7)
    _sign(world)
    out = save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
                     body="I have rewritten this entirely.")
    assert out["signed"] is False and out["signed_name"] == ""
    assert Event.objects.filter(action="a11y.conformance.signature_cleared").count() == 1
    row = A11yConformanceStatement.objects.get()
    assert row.signed_body_hash == "" and row.signed_evidence_hash == ""


def test_saving_the_same_text_is_not_an_edit(world):
    """Otherwise a screen that saves on blur would destroy a signature by doing nothing."""
    _cover(world, "1.1.1", "passed")   # something was checked — signing needs evidence (M7)
    out = _sign(world)
    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               body=out["body"], scope=out["scope"])
    assert state(tenant_id=world["t"], project_id=world["p"])["signed"] is True


def test_a_verdict_change_also_clears_the_signature(world):
    """It changes what the statement SAYS, which is exactly what was signed."""
    _cover(world, "1.1.1", "passed")
    _sign(world)
    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               verdicts={"1.1.1": {"level": PARTIALLY}})
    assert state(tenant_id=world["t"], project_id=world["p"])["signed"] is False


# ===========================================================================================
# C1 — new evidence after signing
# ===========================================================================================

def test_new_evidence_makes_a_signed_statement_stale_and_stops_the_export(world):
    """The words are unchanged, so the signature stands. The facts underneath moved, so it no
    longer describes what the platform holds — and a signed statement quietly describing last
    month's evidence is the worst thing this document can become."""
    _cover(world, "1.1.1", "passed")
    _sign(world)
    assert state(tenant_id=world["t"], project_id=world["p"])["can_export"] is True

    _cover(world, "1.4.3", "failed", route="/dashboard")
    after = state(tenant_id=world["t"], project_id=world["p"])
    assert after["signed"] is True, "they did sign those words"
    assert after["stale"] is True and after["can_export"] is False
    assert "evidence has changed" in after["export_refused_because"]
    with pytest.raises(ConformanceError, match="evidence has changed"):
        check_export(tenant_id=world["t"], project_id=world["p"])


def test_re_signing_clears_the_staleness(world):
    _cover(world, "1.1.1", "passed")
    _sign(world)
    _cover(world, "1.4.3", "failed")
    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               body="Rewritten for the new findings.")
    _sign(world)
    after = state(tenant_id=world["t"], project_id=world["p"])
    assert after["stale"] is False and after["can_export"] is True


def test_evidence_that_produces_the_same_statement_is_not_a_change(world):
    """Two different sets of findings that compile to an identical statement genuinely are the
    same statement. Re-asking there would train reviewers to click through re-signing."""
    _cover(world, "1.1.1", "passed", route="/checkout")
    before = evidence_fingerprint(world["t"], world["p"])
    _cover(world, "1.1.1", "passed", route="/checkout", detail="a-different-rule")
    assert evidence_fingerprint(world["t"], world["p"]) == before


# ===========================================================================================
# AC3 — no auto-certify
# ===========================================================================================

def test_export_publishes_the_signed_statement_and_records_it(world):
    from apps.a11y.conformance import export_statement

    _cover(world, "1.1.1", "passed")
    _sign(world)
    assert state(tenant_id=world["t"], project_id=world["p"])["exported_at"] is None
    after = export_statement(tenant_id=world["t"], project_id=world["p"],
                             user_id=world["aisha"].id)
    art = Artifact.objects.get(id=after["artifact_id"])
    assert art.status == Artifact.Status.PUBLISHED and art.published_at is not None
    exported = Event.objects.get(tenant_id=world["t"], action="a11y.conformance.exported")
    assert after["exported_at"] == exported.ts
    assert Event.objects.filter(tenant_id=world["t"], action="a11y.conformance.exported").count() == 1


def test_exported_time_is_the_latest_export_of_this_signature(world):
    """Edit, re-sign, re-export: the box must show the new export, not the first publish."""
    from apps.a11y.conformance import export_statement

    _cover(world, "1.1.1", "passed")
    _sign(world)
    first = export_statement(tenant_id=world["t"], project_id=world["p"],
                             user_id=world["aisha"].id)["exported_at"]
    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               body="Edited after the first export.")
    _sign(world)
    assert state(tenant_id=world["t"], project_id=world["p"])["exported_at"] is None
    second = export_statement(tenant_id=world["t"], project_id=world["p"],
                              user_id=world["aisha"].id)["exported_at"]
    assert second > first
    art = Artifact.objects.get(type="conformance")
    assert art.published_at < second, "first publish date is kept for reporting"


def test_export_refuses_an_unsigned_statement(world):
    from apps.a11y.conformance import export_statement

    with pytest.raises(ConformanceError, match="cannot be exported unsigned"):
        export_statement(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id)


def test_an_unsigned_statement_cannot_be_exported(world):
    with pytest.raises(ConformanceError, match="cannot be exported unsigned"):
        check_export(tenant_id=world["t"], project_id=world["p"])
    payload = state(tenant_id=world["t"], project_id=world["p"])
    assert payload["can_export"] is False
    assert "the platform has none to give" in payload["export_refused_because"]


def test_a_project_that_has_never_run_anything_still_answers(world):
    """The empty state is a real state. It must not crash, and it must not imply a clean bill."""
    payload = state(tenant_id=world["t"], project_id=world["p"])
    assert payload["totals"][NOT_EVALUATED] == ALL_AA
    assert payload["totals"]["evaluated"] == 0
    assert payload["signed"] is False and payload["can_export"] is False
    assert payload["drafted"] is True, "the body is the platform's draft, not a stored one"


def test_signing_with_nothing_checked_is_refused_and_says_run_an_audit(world):
    """Team decision 2026-10-10 (recon finding 8, mockup M7), replacing the earlier rule that a
    "we evaluated nothing" statement could be signed: with no evidence of any kind there is
    nothing to sign, and the screen says "Run an audit first". Refused here as well as hidden
    there."""
    assert state(tenant_id=world["t"], project_id=world["p"])["has_evidence"] is False
    with pytest.raises(ConformanceError, match="Run an audit first"):
        _sign(world)
    assert not Event.objects.filter(action="a11y.conformance.signed").exists()


def test_a_reviewers_own_level_is_evidence_enough_to_sign(world):
    """A person who assessed a criterion themselves has evidence, even with no check run."""
    from apps.a11y.conformance import save_draft

    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               verdicts={"1.1.1": {"level": "supports", "note": "checked by hand"}})
    assert _sign(world)["signed"] is True


# ══ Which audit this statement came from, and when ═══════════════════════════════════
#
# The team's ask: a reader — and above all the person signing — has to be able to see which
# run the numbers were compiled from and when somebody ran it. A signed statement that cannot
# say what produced it is a statement nobody can check a year later.
#
# It goes INSIDE the wording rather than beside it, which is the part that matters: the section
# is covered by `signed_body_hash`, so it is signed along with everything else. A label printed
# next to the document would go on looking right after the document was edited.

def _audit(world, **over):
    from apps.a11y.models import A11yBaselineAudit

    base = {
        "tenant": world["tenant"], "project": world["project"],
        "base_url": "http://localhost:4180", "routes": ["/", "/catalogue"],
        "status": A11yBaselineAudit.Status.COMPLETE,
        "summary": {"asked": 12, "opened": 12},
    }
    base.update(over)
    return A11yBaselineAudit.objects.create(**base)


def test_the_statement_names_the_audit_it_was_compiled_from(world):
    from apps.a11y.conformance import evidence_basis

    audit = _audit(world)
    basis = evidence_basis(world["t"], world["p"])
    assert basis["latest"]["id"] == str(audit.id)
    assert basis["latest"]["asked"] == 12
    assert basis["latest"]["opened"] == 12
    assert basis["audits"] == 1

    body = state(tenant_id=world["t"], project_id=world["p"])["body"]
    assert "## What this is based on" in body
    # Named by when it ran, never by its id (recon 2026-10-10, finding 5) — the id is kept with
    # the signature instead (`test_the_provenance_is_part_of_what_gets_signed`).
    assert str(audit.id) not in body and str(audit.id)[:8] not in body
    assert audit.created_at.strftime("%d %B %Y at %H:%M UTC") in body
    assert audit.updated_at.strftime("%d %B %Y") in body
    assert basis["latest"]["label"].startswith("the audit of ")


def test_the_provenance_is_part_of_what_gets_signed(world):
    """The whole reason it is a section and not a caption."""
    from apps.a11y.conformance import _body_hash

    audit = _audit(world)
    _cover(world, "1.1.1", "passed")   # something was checked — signing needs evidence (M7)
    signed = _sign(world)
    assert signed["signed"] is True
    row = A11yConformanceStatement.objects.get(project_id=world["p"])
    # The wording names the audit by when it ran; the audit's id travels with the signature
    # record, so a signed statement can still be traced to exactly what produced it.
    assert audit.created_at.strftime("%d %B %Y at %H:%M UTC") in row.body
    assert row.signed_body_hash == _body_hash(row.body)
    from apps.ledger.models import Event
    event = Event.objects.get(action="a11y.conformance.signed")
    assert event.payload["audit_id"] == str(audit.id)


def test_a_project_that_has_never_been_audited_says_exactly_that(world):
    body = state(tenant_id=world["t"], project_id=world["p"])["body"]
    assert "No completed accessibility audit is recorded for this project" in body


def test_an_audit_that_never_finished_is_not_offered_as_evidence(world):
    """An abandoned audit published nothing. Naming it would credit this statement with
    coverage it never had."""
    from apps.a11y.conformance import evidence_basis
    from apps.a11y.models import A11yBaselineAudit

    _audit(world, status=A11yBaselineAudit.Status.FAILED)
    _audit(world, status=A11yBaselineAudit.Status.CAPTURING)
    assert evidence_basis(world["t"], world["p"])["latest"] is None
    assert evidence_basis(world["t"], world["p"])["audits"] == 0


def test_the_most_recent_audit_is_named_and_the_earlier_ones_are_counted(world):
    """The ledger is cumulative: a statement compiled today rests on every completed pass, not
    only the latest. Saying "this is what was checked" would be untrue the moment a project has
    had two."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.conformance import evidence_basis
    from apps.a11y.models import A11yBaselineAudit

    # Stamped apart deliberately. Three audits created in one test land inside a single
    # timestamp, and a test whose "most recent" depended on that would be asserting the tie
    # rather than the ordering.
    now = timezone.now()
    for index, audit in enumerate([_audit(world), _audit(world)]):
        A11yBaselineAudit.objects.filter(id=audit.id).update(
            updated_at=now - timedelta(days=index + 1))
    latest = _audit(world)
    A11yBaselineAudit.objects.filter(id=latest.id).update(updated_at=now)
    basis = evidence_basis(world["t"], world["p"])
    assert basis["latest"]["id"] == str(latest.id)
    assert basis["audits"] == 3

    body = state(tenant_id=world["t"], project_id=world["p"])["body"]
    latest.refresh_from_db()
    assert latest.created_at.strftime("%d %B %Y at %H:%M UTC") in body
    assert "2 earlier completed audit(s)" in body


def test_the_screen_gets_the_basis_as_data_as_well_as_prose(world):
    """The body is the reviewer's to edit — they may cut the section — and the screen still has
    to be able to say which audit the numbers came from."""
    audit = _audit(world)
    payload = state(tenant_id=world["t"], project_id=world["p"])
    assert payload["basis"]["latest"]["id"] == str(audit.id)


def test_a_reviewers_own_wording_is_never_overwritten_with_ours(world):
    """`draft_body` is a draft. Once a reviewer has written their own, the section is theirs to
    keep or cut, and the platform does not put it back."""
    _audit(world)
    save_draft(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               body="# Our own statement\n\nWe wrote this ourselves.")
    payload = state(tenant_id=world["t"], project_id=world["p"])
    assert payload["body"] == "# Our own statement\n\nWe wrote this ourselves."
    assert payload["basis"]["latest"] is not None


# ── every opened page gets an answer for every AI-owned criterion ─────────────────────────
#
# The live defect, 21 August. Meridian's conformance statement said of 2.5.3 Label in Name:
#
#     Does not support — 7 open failures; failed on 1 of 1 pages checked.
#
# The audit had visited **eleven**. Ten of them announced every control's visible text correctly,
# so the check selected nothing there and wrote nothing — and 2.5.3 is the only criterion in the
# registry that is AI-owned with no rule-scanner counterpart, so nothing else filled the gap in.
# 1.1.1 on the same run reads "failed on 5 of 11 pages checked; checked on 1 with nothing wrong;
# 5 pages had nothing for this rule to apply to" — every page accounted for, because axe covers
# 1.1.1 too.

def test_a_page_a_check_found_nothing_to_ask_about_is_still_a_page_that_was_checked(world):
    """The inverse of the live case, and the dangerous one: an application with NO Label-in-Name
    problems recorded no 2.5.3 coverage at all and read as **not evaluated** — a criterion
    examined on every page, printed in a signed document as one nobody looked at."""
    routes = ["/", "/catalogue", "/loans"]
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        report=MergedReport(routes=routes, rows=[
            ReportRow(source=SOURCE_AI, outcome=TRIAGE_PASS, criteria=("1.1.1",), route=route,
                      selector="img.hero", evidence="the alt text describes it", checker="alt",
                      verdict="pass", confidence=0.95)
            for route in routes
        ]))

    got = coverage.summary(world["t"], world["p"])
    assert set(got["2.5.3"]["routes"]) == set(routes), (
        "every page the browser opened must appear under 2.5.3, not only the ones that "
        "raised a question"
    )
    assert set(got["2.5.3"]["routes"].values()) == {"not_applicable"}
    # …and the criterion is no longer invisible to the statement.
    row = next(r for r in criterion_rows(world["t"], world["p"]) if r["criterion"] == "2.5.3")
    assert row["suggested"] != NOT_EVALUATED, "checked on three pages is not 'nobody looked'"
    assert row["routes_checked"] == 3


def test_a_page_that_never_opened_is_never_recorded_as_checked(world):
    """The guard that matters most. `scanner.rule_findings_for` keeps an unreachable route out of
    `report.routes` deliberately; this must read that list and no other. Claiming a check ran over
    a page the browser could not even reach is the worst failure this capability has."""
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        report=MergedReport(
            routes=["/"],
            unreachable=[{"route": "/admin", "reason": "timed out after 30s"}],
            rows=[ReportRow(source=SOURCE_AI, outcome=TRIAGE_PASS, criteria=("1.1.1",),
                            route="/", selector="img", evidence="fine", checker="alt",
                            verdict="pass", confidence=0.95)]))

    got = coverage.summary(world["t"], world["p"])
    for criterion in ("1.1.1", "1.3.1", "1.4.1", "2.5.3", "4.1.2"):
        assert "/admin" not in got.get(criterion, {}).get("routes", {}), (
            f"{criterion} claims coverage of a page that never opened"
        )


def test_a_page_left_part_checked_is_left_alone_rather_than_filled_in(world):
    """A pass that stopped at its own limit part way through a page. The elements it never reached
    might have raised exactly the question being filled in here, so "we do not know" is the true
    answer — and silence is how this codebase says it."""
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        report=MergedReport(
            routes=["/", "/loans"],
            unjudged=[{"route": "/loans", "selector": "#switch-a", "reason": "never judged"}],
            rows=[ReportRow(source=SOURCE_AI, outcome=TRIAGE_PASS, criteria=("1.1.1",),
                            route="/", selector="img", evidence="fine", checker="alt",
                            verdict="pass", confidence=0.95)]))

    got = coverage.summary(world["t"], world["p"])
    assert "/" in got["2.5.3"]["routes"], "the complete page is filled in"
    assert "/loans" not in got["2.5.3"]["routes"], (
        "the part-checked page must stay silent, not be declared clear of a check that "
        "never finished running over it"
    )


def test_filling_the_gaps_never_speaks_over_a_real_answer(world):
    """`not_applicable` is the weakest thing that can be said. A page where the check genuinely
    failed must keep saying so."""
    record_run_findings(
        tenant_id=world["t"], project_id=world["p"], run_id=None,
        report=MergedReport(routes=["/account"], rows=[
            ReportRow(source=SOURCE_AI, outcome=TRIAGE_FAILURE, criteria=("2.5.3",),
                      route="/account", selector="#card-upgrade",
                      evidence="the button says Upgrade and announces Change plan",
                      checker="label", verdict="fail", confidence=0.95)]))

    got = coverage.summary(world["t"], world["p"])
    assert got["2.5.3"]["routes"]["/account"] == "failed"


# ══ Recon 2026-10-10: an audit in progress, the evidence documents, and the reasons ══════

def test_while_an_audit_runs_the_statement_says_so_and_cannot_be_signed(world):
    """Finding 3 (mockup M2): pages are recorded as they arrive, so mid-audit numbers are
    partial. The screen is told, and signing is refused on the server too."""
    from apps.a11y.models import A11yBaselineAudit

    _cover(world, "1.1.1", "passed", engine="AI")
    _audit(world, status=A11yBaselineAudit.Status.CAPTURING)
    assert state(tenant_id=world["t"], project_id=world["p"])["audit_in_progress"] is True
    with pytest.raises(ConformanceError, match="still running"):
        _sign(world)

    A11yBaselineAudit.objects.update(status=A11yBaselineAudit.Status.COMPLETE)
    assert state(tenant_id=world["t"], project_id=world["p"])["audit_in_progress"] is False
    assert _sign(world)["signed"] is True


def test_signing_publishes_the_audit_documents_and_nothing_else(world):
    """Team decision 2026-10-10 (mockup M10, option A): the Accessibility report and baseline
    stay Draft until the statement is signed, and signing publishes them. A report filed
    against a development run belongs to that run's own gate and is left alone; the statement
    itself stays Approved until it is exported."""
    run = Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                             temporal_workflow_id="w1", agent_spec=_spec(world))
    def art(kind, run_id=None):
        return Artifact.objects.create(tenant=world["tenant"], project=world["project"],
                                       phase="testing", type=kind, sor="internal", title=kind,
                                       status=Artifact.Status.DRAFT, run_id=run_id)
    report, baseline, run_report = art("a11y_report"), art("a11y_baseline"), art(
        "a11y_report", run.id)

    _cover(world, "1.1.1", "passed", engine="AI")
    _sign(world)

    for row in (report, baseline, run_report):
        row.refresh_from_db()
    assert report.status == baseline.status == Artifact.Status.PUBLISHED
    assert report.published_at is not None
    assert run_report.status == Artifact.Status.DRAFT, "a run's report waits for its own gate"
    assert Artifact.objects.get(type="conformance").status == Artifact.Status.APPROVED
    payload = Event.objects.get(action="a11y.conformance.signed").payload
    assert sorted(payload["evidence_published"]) == sorted([str(report.id), str(baseline.id)])


def test_a_row_waiting_on_a_person_says_why(world):
    """Finding 7 (mockup M6): "needs your decision" with no reason told a reviewer nothing."""
    _cover(world, "1.1.1", "not_applicable")       # a rule, on a criterion the AI owns
    rows = {r["criterion"]: r for r in state(tenant_id=world["t"], project_id=world["p"])["rows"]}
    row = rows["1.1.1"]
    assert row["needs_a_person"] is True
    assert row["why"] == ("The automatic rule looked, but can't settle this criterion on its "
                          "own. Pick its result in the Conformance column.")
    assert "nothing for this rule to apply to" in row["evidence"]
    assert all(r["why"] == "" for r in rows.values() if not r["needs_a_person"])


def test_the_evidence_sentence_names_every_check_that_looked(world):
    """Finding 7: a row established by the AI and a rule said "for this rule" only."""
    _cover(world, "1.1.1", "not_applicable", engine="AI")
    _cover(world, "1.1.1", "not_applicable", engine="rule")
    row = next(r for r in state(tenant_id=world["t"], project_id=world["p"])["rows"]
               if r["criterion"] == "1.1.1")
    assert "nothing for these checks to apply to" in row["evidence"]


def test_only_levels_the_evidence_suggested_are_counted_as_suggested(world):
    """Finding 8 (mockup M7): "Not evaluated" is not a suggestion — nothing looked."""
    _cover(world, "1.1.1", "passed", engine="AI")
    totals_ = state(tenant_id=world["t"], project_id=world["p"])["totals"]
    assert totals_["platform_suggested"] == 1
