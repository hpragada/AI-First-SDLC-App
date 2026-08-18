"""QA-23 — the SME review console: a person answers what the checks could not settle.

Against the task's acceptance criteria:

  AC1  an uncertain finding shows its element, screenshot, criterion and the AI's draft verdict
  AC2  confirm/reject updates the finding's status and records the decision
  AC3  two reviewers on one item produce an unambiguous, audit-logged outcome
  AC4  ≥ 90% coverage on the new code

**The three tests that matter most are not in the acceptance criteria**, because they are the
problems found by reading the code this console plugs into rather than by reading the task:

  * `test_the_next_run_does_not_erase_a_reviewers_decision` — `record_run_findings` rewrites
    `outcome`/`verdict`/`confidence` on every run, so without the content-hash rule a reviewer
    confirms a real problem, a defect opens, the next run re-judges, the AI is still unsure, and
    the defect loop closes the ticket the reviewer just raised. The console would silently undo
    itself while looking like it worked.
  * `test_the_gate_stops_citing_a_finding_a_person_has_answered` — `unanswered_checks` means
    "nobody answered". Once a person has, that sentence is false, and leaving it would have the
    gate blocking forever at the people who answered it.
  * `test_a_confirmed_finding_is_not_suppressed_by_the_confidence_dial` — `policy.blocks` holds
    a finding back under the project's confidence bar. A confirmed finding still carries the
    AI's 41%, so a human says "yes, this is real" and a number silently overrules them.
"""
from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from apps.a11y.defects import DEFECT_KIND, record_a11y_findings
from apps.a11y.findings import record_run_findings, review_queue
from apps.a11y.models import A11yCandidateBundle, A11yFinding, A11yScreenScan, WcagCriterion
from apps.a11y.report import SOURCE_AI, MergedReport, ReportRow
from apps.a11y.review import (
    CONFIRM,
    ELEMENT,
    LOCK_MINUTES,
    PAGE,
    REJECT,
    ReviewError,
    ReviewLockError,
    ReviewRoleError,
    adjudicate,
    can_review,
    claim,
    evidence_for,
    lock_holder,
    lock_state,
    open_item,
    queue,
    release,
    screenshot,
)
from apps.a11y.triage import TRIAGE_FAILURE, TRIAGE_PASS, TRIAGE_REVIEW
from apps.gates.a11ygate import unanswered_checks
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_UNCERTAIN
from storage.object_store import InMemoryObjectStore

PAGE_PNG = b"\x89PNG\r\n\x1a\n-page-bytes"
CROP_PNG = b"\x89PNG\r\n\x1a\n-crop-bytes"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0")
    aisha = User.objects.create_user(email="aisha@acme.test", name="Aisha Khan", tenant=tenant)
    tom = User.objects.create_user(email="tom@acme.test", name="Tom Reyes", tenant=tenant)
    dev = User.objects.create_user(email="dev@acme.test", name="Dana Ops", tenant=tenant)
    for user in (aisha, tom):
        Membership.objects.create(tenant=tenant, project=project, user=user, role="qa_lead")
    Membership.objects.create(tenant=tenant, project=project, user=dev, role="engineer")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.4.3",
        defaults={"handle": "Contrast (Minimum)", "level": "AA", "slug": "c", "text": "…"})
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project,
            "story": story, "spec": spec, "aisha": aisha, "tom": tom, "dev": dev}


def _run(world, workflow_id="w1") -> Run:
    return Run.objects.create(tenant=world["tenant"], work_item=world["story"],
                              agent_spec=world["spec"], temporal_workflow_id=workflow_id)


def _row(*, outcome=TRIAGE_REVIEW, criterion="1.1.1", route="/checkout", selector="img.hero",
         verdict=A11Y_UNCERTAIN, confidence=0.41, content_hash="hash-a", checker="alt",
         evidence="alt reads like a filename"):
    return ReportRow(
        source=SOURCE_AI, outcome=outcome, criteria=(criterion,), route=route, selector=selector,
        evidence=evidence, confidence=confidence, checker=checker, verdict=verdict,
        suggested_fix="describe it, or mark it decorative", screenshot_ref="",
        content_hash=content_hash, engine="claude", model="opus", prompt_version="v3",
    )


def _record(world, run, *rows, routes=("/checkout",)):
    report = MergedReport(rows=list(rows), routes=list(routes))
    return record_run_findings(tenant_id=world["t"], project_id=world["p"], run_id=run.id,
                               report=report)


def _capture(world, run, *, box=None, page_ref="", element_ref="", reason="",
             route="/checkout", selector="img.hero"):
    """The evidence rows a real ingest would have written for this finding."""
    if page_ref:
        A11yScreenScan.objects.create(
            tenant=world["tenant"], project=world["project"], run_key=str(run.id), route=route,
            url="http://localhost:3000/checkout", screen_hash="sh1", violations=[],
            page_image_ref=page_ref)
    A11yCandidateBundle.objects.create(
        tenant=world["tenant"], project=world["project"], run_key=str(run.id), route=route,
        selector=selector, url="http://localhost:3000/checkout", checkers=["alt"],
        element={"selector": selector, "box": box or {}}, screenshot_ref=element_ref,
        uncapturable_reason=reason, screen_hash="sh1")


def _finding(world) -> A11yFinding:
    return A11yFinding.objects.get(tenant_id=world["t"], project_id=world["p"])


# ===========================================================================================
# AC1 — the reviewer sees what they need to judge it
# ===========================================================================================

def test_the_queue_carries_the_element_criterion_verdict_and_picture(world):
    """AC1. Everything the console draws comes from one call, and it is all really there."""
    run = _run(world)
    _record(world, run, _row())
    _capture(world, run, box={"x": 40, "y": 92, "width": 210, "height": 88},
             page_ref=f"a11y/{world['t']}/{world['p']}/pages/abc.png",
             element_ref=f"a11y/{world['t']}/{world['p']}/elements/def.png")

    items = queue(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id)
    assert len(items) == 1
    item = items[0]
    assert item["criterion"] == "1.1.1"
    assert item["criterion_handle"] == "Non-text Content", "the name, not just the number"
    assert item["wcag_level"] == "A"
    assert item["route"] == "/checkout" and item["selector"] == "img.hero"
    assert item["checker"] == "alt"
    assert item["verdict"] == A11Y_UNCERTAIN and item["confidence"] == pytest.approx(0.41)
    assert item["evidence"] == "alt reads like a filename"
    assert item["suggested_fix"]
    assert item["severity_if_confirmed"] == "critical", "Level A, from the standard"
    assert item["page_image"] is True and item["element_image"] is True
    assert item["box"] == {"x": 40.0, "y": 92.0, "width": 210.0, "height": 88.0}


def test_the_queue_is_worst_first_and_only_holds_undecided_items(world):
    run = _run(world)
    _record(world, run,
            _row(criterion="1.4.3", selector="span.delta", content_hash="h-aa"),
            _row(criterion="1.1.1", selector="img.hero", content_hash="h-a"))
    items = queue(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id)
    assert [i["criterion"] for i in items] == ["1.1.1", "1.4.3"], "critical before high"

    adjudicate(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id,
               finding_id=str(A11yFinding.objects.get(criterion="1.1.1").id), decision=CONFIRM)
    left = queue(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id)
    assert [i["criterion"] for i in left] == ["1.4.3"], "an answered item leaves the queue"


def test_a_finding_with_no_picture_says_why_rather_than_showing_an_empty_frame(world):
    """The silence rule. 'No image' with no reason is exactly the gap this build is against."""
    run = _run(world)
    _record(world, run, _row())
    _capture(world, run, reason="the capture recorded no on-screen rectangle for this element")

    item = queue(tenant_id=world["t"], project_id=world["p"])[0]
    assert item["page_image"] is False and item["element_image"] is False
    assert item["box"] is None
    assert "no on-screen rectangle" in item["capture_reason"]


def test_evidence_survives_the_run_that_found_it(world):
    """A finding outlives its run, so its evidence is looked up, not carried."""
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, _row())
    _capture(world, first, box={"x": 1, "y": 2, "width": 3, "height": 4},
             page_ref=f"a11y/{world['t']}/{world['p']}/pages/old.png")
    _record(world, second, _row())
    _capture(world, second, box={"x": 9, "y": 9, "width": 9, "height": 9},
             page_ref=f"a11y/{world['t']}/{world['p']}/pages/new.png")

    ev = evidence_for(_finding(world))
    assert ev["page_ref"].endswith("new.png"), "the run that last saw it, not the first"
    assert ev["box"] == {"x": 9.0, "y": 9.0, "width": 9.0, "height": 9.0}


def test_a_page_that_failed_to_screenshot_does_not_hide_one_that_worked(world):
    first, second = _run(world, "w1"), _run(world, "w2")
    _record(world, first, _row())
    _capture(world, first, page_ref=f"a11y/{world['t']}/{world['p']}/pages/good.png")
    _record(world, second, _row())
    _capture(world, second)  # this run took no page image at all

    assert evidence_for(_finding(world))["page_ref"].endswith("good.png")


# ===========================================================================================
# The picture — a reviewer cannot judge what they cannot see
# ===========================================================================================

def test_the_screenshot_is_read_through_and_never_copied_onto_a_row(world):
    run = _run(world)
    _record(world, run, _row())
    page_key = f"a11y/{world['t']}/{world['p']}/pages/abc.png"
    crop_key = f"a11y/{world['t']}/{world['p']}/elements/def.png"
    _capture(world, run, page_ref=page_key, element_ref=crop_key)
    store = InMemoryObjectStore()
    store.put(page_key, PAGE_PNG, content_type="image/png")
    store.put(crop_key, CROP_PNG, content_type="image/png")

    finding = _finding(world)
    body, mime = screenshot(tenant_id=world["t"], project_id=world["p"],
                            finding_id=str(finding.id), kind=PAGE, object_store=store)
    assert body == PAGE_PNG and mime == "image/png"
    body, _ = screenshot(tenant_id=world["t"], project_id=world["p"],
                         finding_id=str(finding.id), kind=ELEMENT, object_store=store)
    assert body == CROP_PNG

    finding.refresh_from_db()
    assert PAGE_PNG not in finding.evidence.encode(), "the body never lands on the row (#1/#3)"


def test_a_key_outside_this_project_is_refused(world):
    """The key comes out of a row and is handed to the object store. It is checked, not trusted."""
    run = _run(world)
    _record(world, run, _row())
    _capture(world, run, page_ref="a11y/some-other-tenant/some-other-project/pages/x.png")
    store = InMemoryObjectStore()
    store.put("a11y/some-other-tenant/some-other-project/pages/x.png", b"secret")

    with pytest.raises(ReviewError, match="does not belong to this project"):
        screenshot(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), object_store=store)


def test_a_missing_picture_is_a_sentence_not_a_crash(world):
    run = _run(world)
    _record(world, run, _row())
    _capture(world, run, reason="the page screenshot was over the size limit")
    with pytest.raises(ReviewError, match="over the size limit"):
        screenshot(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), object_store=InMemoryObjectStore())


def test_an_unreadable_object_is_reported_not_swallowed(world):
    run = _run(world)
    _record(world, run, _row())
    key = f"a11y/{world['t']}/{world['p']}/pages/gone.png"
    _capture(world, run, page_ref=key)
    with pytest.raises(ReviewError, match="could not be read from storage"):
        screenshot(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), object_store=InMemoryObjectStore())


def test_screenshot_rejects_an_unknown_kind_and_an_unknown_finding(world):
    with pytest.raises(ReviewError, match="kind must be"):
        screenshot(tenant_id=world["t"], project_id=world["p"], finding_id="x", kind="thumbnail")
    run = _run(world)
    _record(world, run, _row())
    with pytest.raises(ReviewError, match="no such finding"):
        screenshot(tenant_id=world["t"], project_id=world["p"],
                   finding_id="00000000-0000-0000-0000-000000000000")


# ===========================================================================================
# AC2 — the decision updates the finding and is recorded
# ===========================================================================================

def test_confirming_makes_the_finding_a_real_failure(world):
    """D-A11Y-98(3). The defect loop only tickets `failure`, so without this the screen's
    "a defect has been opened" is a lie."""
    run = _run(world)
    _record(world, run, _row())
    finding = _finding(world)
    assert finding.outcome == "needs_review"

    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(finding.id),
               user_id=world["aisha"].id, decision=CONFIRM, note="the alt is a filename")
    finding.refresh_from_db()
    assert finding.outcome == "failure"
    assert finding.status == A11yFinding.Status.OPEN
    assert finding.adjudication == A11yFinding.Adjudication.CONFIRMED
    assert finding.adjudicated_by_id == world["aisha"].id
    assert finding.adjudication_note == "the alt is a filename"
    assert finding.adjudicated_at is not None
    assert finding.source == A11yFinding.Source.HUMAN
    assert finding.confidence is None, "a human judgement has no percentage"


def test_a_confirmed_finding_actually_raises_a_ticket(world):
    """The whole point of flipping the outcome — asserted end to end, not by proxy."""
    run = _run(world)
    _record(world, run, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)

    out = record_a11y_findings(tenant_id=world["t"], project_id=world["p"], run_id=run.id)
    assert len(out["opened"]) == 1
    defect = WorkItem.objects.get(type=WorkItem.Type.DEFECT)
    assert defect.external_ref.get("kind") == DEFECT_KIND
    assert "1.1.1" in defect.title


def test_rejecting_closes_the_finding_and_raises_nothing(world):
    run = _run(world)
    _record(world, run, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=REJECT, note="decorative, the heading says it")
    finding = _finding(world)
    assert finding.adjudication == A11yFinding.Adjudication.REJECTED
    assert finding.status == A11yFinding.Status.RESOLVED
    assert finding.outcome == "needs_review", "rejected is not a pass — nothing was measured"
    assert record_a11y_findings(tenant_id=world["t"], project_id=world["p"],
                                run_id=run.id)["opened"] == []


def test_rejecting_demands_a_reason_and_confirming_does_not(world):
    """Asymmetric on purpose: rejecting overrules the evidence, and the note is the only record."""
    run = _run(world)
    _record(world, run, _row())
    with pytest.raises(ReviewError, match="say why this is fine"):
        adjudicate(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), user_id=world["aisha"].id,
                   decision=REJECT, note="   ")
    assert _finding(world).adjudication == A11yFinding.Adjudication.PENDING, "nothing changed"

    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)
    assert _finding(world).adjudication == A11yFinding.Adjudication.CONFIRMED


def test_an_unknown_decision_word_is_refused(world):
    run = _run(world)
    _record(world, run, _row())
    with pytest.raises(ReviewError, match="decision must be one of"):
        adjudicate(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), user_id=world["aisha"].id,
                   decision="maybe")


def test_a_decision_is_not_a_draft(world):
    run = _run(world)
    _record(world, run, _row())
    fid = str(_finding(world).id)
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
               user_id=world["aisha"].id, decision=CONFIRM)
    with pytest.raises(ReviewError, match="already confirmed"):
        adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
                   user_id=world["tom"].id, decision=REJECT, note="I disagree")
    assert _finding(world).adjudication == A11yFinding.Adjudication.CONFIRMED


def test_only_the_accessibility_reviewer_may_answer(world):
    run = _run(world)
    _record(world, run, _row())
    with pytest.raises(ReviewRoleError, match="QA Lead"):
        adjudicate(tenant_id=world["t"], project_id=world["p"],
                   finding_id=str(_finding(world).id), user_id=world["dev"].id,
                   decision=CONFIRM)
    assert _finding(world).adjudication == A11yFinding.Adjudication.PENDING


def test_who_may_review_matches_the_gate_role_and_its_two_admin_carve_outs(world):
    assert can_review(tenant_id=world["t"], project_id=world["p"], user_id=world["aisha"].id)
    assert not can_review(tenant_id=world["t"], project_id=world["p"], user_id=world["dev"].id)
    assert not can_review(tenant_id=world["t"], project_id=world["p"], user_id=None)

    Membership.objects.filter(user=world["dev"]).update(role="admin")
    assert can_review(tenant_id=world["t"], project_id=world["p"], user_id=world["dev"].id)

    outsider = User.objects.create_user(email="boss@acme.test", name="Boss",
                                        tenant=world["tenant"], is_tenant_admin=True)
    assert can_review(tenant_id=world["t"], project_id=world["p"], user_id=outsider.id)


def test_a_reader_without_the_role_sees_everything_and_can_answer_nothing(world):
    """S-36's ninth state. Read-only, not hidden — a developer seeing what a reviewer sees is
    the transparency this build is for."""
    run = _run(world)
    _record(world, run, _row())
    item = open_item(tenant_id=world["t"], project_id=world["p"],
                     finding_id=str(_finding(world).id), user_id=world["dev"].id)
    assert item["can_review"] is False
    assert item["evidence"] and item["criterion"] == "1.1.1"
    assert item["lock"]["held"] is False, "a reader takes no claim"


# ===========================================================================================
# AC3 — two reviewers, one item
# ===========================================================================================

def test_opening_an_item_claims_it_and_the_second_reviewer_is_locked_out(world):
    run = _run(world)
    _record(world, run, _row())
    fid = str(_finding(world).id)

    mine = open_item(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
                     user_id=world["aisha"].id)
    assert mine["lock"]["held"] is True and mine["lock"]["by_me"] is True
    assert mine["locked_out"] == ""

    theirs = open_item(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
                       user_id=world["tom"].id)
    assert theirs["lock"]["held"] is True and theirs["lock"]["by_me"] is False
    assert theirs["lock"]["held_by_name"] == "Aisha Khan"
    assert "Aisha Khan is reviewing this one" in theirs["locked_out"]
    assert theirs["evidence"], "locked out is read-only, not blind"


def test_the_second_reviewers_answer_is_refused_and_overwrites_nothing(world):
    """AC3. The outcome is unambiguous: one decision stands and the other is told so."""
    run = _run(world)
    _record(world, run, _row())
    fid = str(_finding(world).id)
    open_item(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
              user_id=world["aisha"].id)

    with pytest.raises(ReviewLockError, match="your answer was not saved"):
        adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
                   user_id=world["tom"].id, decision=REJECT, note="looks fine to me")
    assert _finding(world).adjudication == A11yFinding.Adjudication.PENDING

    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
               user_id=world["aisha"].id, decision=CONFIRM)
    assert _finding(world).adjudicated_by_id == world["aisha"].id


def test_a_claim_lapses_on_its_own_so_nobody_has_to_remember_to_release_it(world):
    """C1. A reviewer who closes their laptop must not park the item forever."""
    run = _run(world)
    _record(world, run, _row())
    finding = _finding(world)
    claim(finding, user_id=world["aisha"].id)
    assert lock_holder(finding) == world["aisha"].id

    later = timezone.now() + timedelta(minutes=LOCK_MINUTES + 1)
    assert lock_holder(finding, now=later) is None, "lapsed, with no sweeper involved"
    assert claim(finding, user_id=world["tom"].id, now=later) is True
    assert lock_holder(finding, now=later) == world["tom"].id


def test_reopening_renews_the_claim_rather_than_taking_a_new_one(world):
    """Renewal is what "extended while they are on it" means, and it must not spam the ledger."""
    run = _run(world)
    _record(world, run, _row())
    finding = _finding(world)
    assert claim(finding, user_id=world["aisha"].id) is True
    assert claim(finding, user_id=world["aisha"].id) is False, "the same person, still holding"
    assert Event.objects.filter(action="a11y.review.claimed").count() == 0, "no event yet"

    open_item(tenant_id=world["t"], project_id=world["p"], finding_id=str(finding.id),
              user_id=world["aisha"].id)
    open_item(tenant_id=world["t"], project_id=world["p"], finding_id=str(finding.id),
              user_id=world["aisha"].id)
    assert Event.objects.filter(action="a11y.review.claimed").count() == 0, \
        "already held by them — renewals are not new claims"


def test_a_decision_hands_the_item_back(world):
    run = _run(world)
    _record(world, run, _row())
    fid = str(_finding(world).id)
    open_item(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
              user_id=world["aisha"].id)
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
               user_id=world["aisha"].id, decision=CONFIRM)
    finding = _finding(world)
    assert finding.review_locked_by_id is None and finding.review_locked_at is None


def test_a_reviewer_can_step_away_deliberately(world):
    run = _run(world)
    _record(world, run, _row())
    finding = _finding(world)
    claim(finding, user_id=world["aisha"].id)
    release(finding)
    assert lock_holder(finding) is None
    assert lock_state(finding, user_id=world["tom"].id) == {
        "held": False, "by_me": False, "held_by": None, "held_by_name": "", "expires_at": None}


def test_every_decision_is_audit_logged(world):
    """AC3's other half. This app had never written a ledger event — a decision nobody can
    reconstruct is not a decision."""
    run = _run(world)
    _record(world, run, _row())
    fid = str(_finding(world).id)
    open_item(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
              user_id=world["aisha"].id)
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=fid,
               user_id=world["aisha"].id, decision=CONFIRM, note="filename, not a description")

    claimed = Event.objects.get(action="a11y.review.claimed")
    assert claimed.actor == str(world["aisha"].id)
    decided = Event.objects.get(action="a11y.finding.adjudicated")
    assert decided.actor == str(world["aisha"].id)
    assert decided.target_type == "a11y_finding"
    assert decided.payload["decision"] == CONFIRM
    assert decided.payload["note"] == "filename, not a description"
    assert decided.payload["outcome"] == "failure"
    assert decided.payload["route"] == "/checkout"
    assert decided.payload["criterion"] == "1.1.1"
    assert decided.payload["was_verdict"] == A11Y_UNCERTAIN
    assert decided.payload["content_hash"] == "hash-a"


def test_an_unknown_item_is_refused_by_both_doors(world):
    ghost = "00000000-0000-0000-0000-000000000000"
    with pytest.raises(ReviewError, match="no such finding"):
        open_item(tenant_id=world["t"], project_id=world["p"], finding_id=ghost,
                  user_id=world["aisha"].id)
    with pytest.raises(ReviewError, match="no such finding"):
        adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=ghost,
                   user_id=world["aisha"].id, decision=CONFIRM)


# ===========================================================================================
# The three problems the acceptance criteria do not mention
# ===========================================================================================

def test_the_next_run_does_not_erase_a_reviewers_decision(world):
    """B1, and the most important test in this file.

    Without it: confirm → defect opens → next run re-judges → AI still unsure → outcome falls
    back to `needs_review` → the defect loop closes the ticket the reviewer just raised.
    """
    first = _run(world, "w1")
    _record(world, first, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)
    record_a11y_findings(tenant_id=world["t"], project_id=world["p"], run_id=first.id)
    assert WorkItem.objects.filter(type=WorkItem.Type.DEFECT).count() == 1

    second = _run(world, "w2")
    _record(world, second, _row())  # same element, same content hash, AI still unsure

    finding = _finding(world)
    assert finding.outcome == "failure", "the human's answer stands"
    assert finding.adjudication == A11yFinding.Adjudication.CONFIRMED
    assert finding.confidence is None and finding.source == A11yFinding.Source.HUMAN
    assert finding.last_seen_run_id == second.id, "still refreshed where it should be"

    out = record_a11y_findings(tenant_id=world["t"], project_id=world["p"], run_id=second.id)
    assert out["closed"] == [], "and the ticket the reviewer raised survives"
    assert WorkItem.objects.filter(type=WorkItem.Type.DEFECT).count() == 1


def test_a_rejected_finding_stays_closed_across_runs(world):
    """The other direction: without this, the blanket `status=OPEN` reopens it every run."""
    first = _run(world, "w1")
    _record(world, first, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=REJECT, note="decorative")

    _record(world, _run(world, "w2"), _row())
    finding = _finding(world)
    assert finding.status == A11yFinding.Status.RESOLVED
    assert finding.adjudication == A11yFinding.Adjudication.REJECTED
    assert review_queue(world["t"], world["p"]) == []


def test_an_edited_element_comes_back_to_the_queue(world):
    """B1's other half. A ruling is about the element it was made on, and a stale "this is fine"
    sitting over changed markup is the failure this whole build is against."""
    _record(world, _run(world, "w1"), _row(content_hash="hash-a"))
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=REJECT, note="decorative")

    _record(world, _run(world, "w2"), _row(content_hash="hash-b-edited"))
    finding = _finding(world)
    assert finding.adjudication == A11yFinding.Adjudication.PENDING
    assert finding.adjudicated_by_id is None and finding.adjudication_note == ""
    assert finding.adjudicated_at is None and finding.adjudicated_content_hash == ""
    assert finding.status == A11yFinding.Status.OPEN and finding.outcome == "needs_review"
    assert len(review_queue(world["t"], world["p"])) == 1, "asked again, honestly"


def test_a_ruling_with_no_provable_hash_does_not_survive(world):
    """Conservative on purpose: re-asking a person is a cost, keeping a verdict we cannot
    justify is a lie. Findings written before the column exists land here."""
    _record(world, _run(world, "w1"), _row(content_hash=""))
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)
    assert _finding(world).adjudicated_content_hash == ""

    _record(world, _run(world, "w2"), _row(content_hash=""))
    assert _finding(world).adjudication == A11yFinding.Adjudication.PENDING


def test_a_confirmed_finding_that_disappears_still_resolves_by_absence(world):
    """The human's answer outranks the machine's opinion, NOT the evidence of the element
    being gone. A fixed problem is still a fixed problem."""
    first = _run(world, "w1")
    _record(world, first, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)

    _record(world, _run(world, "w2"), _row(outcome=TRIAGE_PASS, selector="other.thing",
                                           content_hash="h2"))
    assert _finding(world).status == A11yFinding.Status.RESOLVED


def test_the_gate_stops_citing_a_finding_a_person_has_answered(world):
    """`unanswered_checks` means "nobody answered". Once somebody has, it is not true."""
    run = _run(world)
    _record(world, run, _row())
    assert len(unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                                 work_item_id=world["story"].id)) == 1

    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=CONFIRM)
    assert unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                             work_item_id=world["story"].id) == []


def test_a_rejected_finding_also_stops_blocking_the_gate(world):
    run = _run(world)
    _record(world, run, _row())
    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(_finding(world).id),
               user_id=world["aisha"].id, decision=REJECT, note="decorative")
    assert unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                             work_item_id=world["story"].id) == []


def test_an_unanswered_finding_still_blocks(world):
    """Asserted in both directions — the fix must not have quietly opened the gate."""
    run = _run(world)
    _record(world, run, _row())
    assert len(unanswered_checks(tenant_id=world["t"], project_id=world["p"],
                                 work_item_id=world["story"].id)) == 1


def test_a_confirmed_finding_is_not_suppressed_by_the_confidence_dial(world):
    """`policy.blocks` holds a finding under the project's confidence bar. A confirmed finding
    still carries the AI's 41%, so a person says "this is real" and a number overrules them.

    The bar defaults to 0.0, so nothing is suppressed out of the box — this only bites a project
    that raised it, which is a supported and reasonable thing to do (QA-08). Raised here rather
    than assumed, because a test that passed because the dial was off would prove nothing.
    """
    from apps.a11y.policy import DEFAULT_TARGET, blocks, default_policy
    from apps.projects.models import ProjectProfile

    run = _run(world)
    _record(world, run, _row(confidence=0.41))
    ProjectProfile.objects.update_or_create(
        tenant=world["tenant"], project=world["project"],
        defaults={"a11y": {"gate": {"min_confidence": 0.8}}})

    policy = default_policy(DEFAULT_TARGET)
    policy["gate"] = {**policy["gate"], "min_confidence": 0.8}
    finding = _finding(world)
    assert not blocks(policy, severity=finding.severity, confidence=0.41, source="AI"), \
        "41% is under this project's 80% bar — this is the trap"

    adjudicate(tenant_id=world["t"], project_id=world["p"], finding_id=str(finding.id),
               user_id=world["aisha"].id, decision=CONFIRM)
    finding.refresh_from_db()
    assert blocks(policy, severity=finding.severity, confidence=finding.confidence,
                  source=finding.source), "a human judgement has no percentage to doubt"
    assert record_a11y_findings(tenant_id=world["t"], project_id=world["p"],
                                run_id=run.id)["opened"], \
        "so it really does raise a ticket, through the project's own raised bar"


# ===========================================================================================
# What this does NOT touch
# ===========================================================================================

def test_a_scanner_failure_never_reaches_the_console(world):
    """The queue is `needs_review` only. A measurement is not a question for a person, and a
    console that offered to overturn axe would be a different and much worse product."""
    run = _run(world)
    _record(world, run, _row(outcome=TRIAGE_FAILURE, verdict="fail", confidence=None))
    assert queue(tenant_id=world["t"], project_id=world["p"]) == []


def test_an_empty_queue_is_not_a_clean_bill_of_health(world):
    """D-A11Y-93 in code: nothing here says anything about how accessible the app is."""
    run = _run(world)
    _record(world, run, _row(outcome=TRIAGE_FAILURE, verdict="fail", confidence=None))
    assert queue(tenant_id=world["t"], project_id=world["p"]) == []
    assert A11yFinding.objects.filter(status=A11yFinding.Status.OPEN,
                                      outcome="failure").count() == 1, \
        "an empty queue with an open failure sitting right there"
