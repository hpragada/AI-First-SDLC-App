"""QA-23 — the review console's three endpoints, over HTTP.

`apps.a11y.review` is tested directly in `test_a11y_review.py`. This file is about the seam the
screen actually talks to: does the queue come back, does a claim survive a request boundary,
does a refusal arrive as a status code the UI can branch on, and does an image really stream.

**The status codes are the contract, and they are deliberately three different ones.** Wrong
role is `403` (you may never do this), someone else holds it is `409` (you may, but not now),
and a malformed decision is `400` (fix your request). A console that got one code for all three
could only ever show one message, and "something went wrong" is exactly the sort of silence
this build exists to remove.
"""
import pytest
from rest_framework.test import APIClient

from apps.a11y.findings import record_run_findings
from apps.a11y.models import A11yCandidateBundle, A11yFinding, A11yScreenScan, WcagCriterion
from apps.a11y.report import SOURCE_AI, MergedReport, ReportRow
from apps.a11y.triage import TRIAGE_REVIEW
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11Y_UNCERTAIN
from storage import s3_from_settings

PASSWORD = "review-pass!"
PNG = b"\x89PNG\r\n\x1a\n-a-page"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Payments")
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(tenant=tenant, key="09b_test_automation", body_ref="x",
                                    semver="1.0.0")
    run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                             temporal_workflow_id="w1")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})

    aisha = User.objects.create_user(email="aisha@acme.test", name="Aisha Khan", tenant=tenant,
                                     password=PASSWORD)
    tom = User.objects.create_user(email="tom@acme.test", name="Tom Reyes", tenant=tenant,
                                   password=PASSWORD)
    dev = User.objects.create_user(email="dev@acme.test", name="Dana Ops", tenant=tenant,
                                   password=PASSWORD)
    for user in (aisha, tom):
        Membership.objects.create(tenant=tenant, project=project, user=user, role="qa_lead")
    Membership.objects.create(tenant=tenant, project=project, user=dev, role="engineer")

    record_run_findings(tenant_id=str(tenant.id), project_id=str(project.id), run_id=run.id,
                        report=MergedReport(rows=[ReportRow(
                            source=SOURCE_AI, outcome=TRIAGE_REVIEW, criteria=("1.1.1",),
                            route="/checkout", selector="img.hero", verdict=A11Y_UNCERTAIN,
                            evidence="alt reads like a filename", confidence=0.41,
                            checker="alt", content_hash="hash-a",
                        )], routes=["/checkout"]))

    key = f"a11y/{tenant.id}/{project.id}/pages/abc.png"
    A11yScreenScan.objects.create(tenant=tenant, project=project, run_key=str(run.id),
                                  route="/checkout", screen_hash="s1", violations=[],
                                  page_image_ref=key)
    A11yCandidateBundle.objects.create(
        tenant=tenant, project=project, run_key=str(run.id), route="/checkout",
        selector="img.hero", checkers=["alt"], screen_hash="s1",
        element={"selector": "img.hero", "box": {"x": 8, "y": 92, "width": 210, "height": 88}})
    s3_from_settings().put(key, PNG, content_type="image/png")

    finding = A11yFinding.objects.get(tenant_id=tenant.id)
    return {"project": project, "finding": finding, "aisha": aisha, "tom": tom, "dev": dev,
            "base": f"/api/projects/{project.id}/a11y-review"}


def _client(email):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": email, "password": PASSWORD},
                       format="json").status_code == 200
    return client


def test_the_queue_endpoint_returns_the_work_and_who_may_do_it(world):
    body = _client("aisha@acme.test").get(f"{world['base']}/").json()
    assert body["can_review"] is True
    assert body["lock_minutes"] == 15
    assert len(body["queue"]) == 1
    item = body["queue"][0]
    assert item["criterion"] == "1.1.1" and item["criterion_handle"] == "Non-text Content"
    assert item["route"] == "/checkout" and item["selector"] == "img.hero"
    assert item["verdict"] == A11Y_UNCERTAIN
    # The capture is NOT here (G3b) — the rail draws no picture, so the list does not go and
    # find one. It arrives with the item, which is the next test.
    assert "page_image" not in item and "box" not in item


def test_opening_an_item_over_rest_brings_the_capture_with_it(world):
    body = _client("aisha@acme.test").get(f"{world['base']}/{world['finding'].id}/").json()
    assert body["page_image"] is True
    assert body["box"] == {"x": 8.0, "y": 92.0, "width": 210.0, "height": 88.0}


def test_a_member_without_the_role_sees_the_queue_read_only(world):
    body = _client("dev@acme.test").get(f"{world['base']}/").json()
    assert body["can_review"] is False
    assert len(body["queue"]) == 1, "read-only, not hidden"


def test_opening_an_item_claims_it_across_the_request_boundary(world):
    url = f"{world['base']}/{world['finding'].id}/"
    mine = _client("aisha@acme.test").get(url).json()
    assert mine["lock"]["by_me"] is True and mine["locked_out"] == ""

    theirs = _client("tom@acme.test").get(url).json()
    assert theirs["lock"]["held"] is True and theirs["lock"]["by_me"] is False
    assert theirs["lock"]["held_by_name"] == "Aisha Khan"
    assert "Aisha Khan is reviewing this one" in theirs["locked_out"]


def test_confirming_returns_what_the_screen_promises(world):
    url = f"{world['base']}/{world['finding'].id}/"
    client = _client("aisha@acme.test")
    client.get(url)
    resp = client.post(url, {"decision": "confirm", "note": "filename, not a description"},
                       format="json")
    assert resp.status_code == 200
    body = resp.json()
    assert body["adjudication"] == "confirmed"
    assert body["outcome"] == "failure"
    assert body["severity"] == "critical"
    assert body["opens_defect"] is True, "so the screen may say a defect has been opened"


def test_the_screen_is_not_promised_a_defect_the_policy_will_never_raise(world):
    """`opens_defect` is asked of the project's own policy, not assumed. A project that blocks
    on nothing at all is a supported choice since QA-08, and telling its reviewer a ticket was
    raised would be the console lying about its own consequence."""
    from apps.projects.models import ProjectProfile

    ProjectProfile.objects.update_or_create(
        tenant=world["project"].tenant, project=world["project"],
        defaults={"a11y": {"gate": {"block_severities": []}}})
    url = f"{world['base']}/{world['finding'].id}/"
    client = _client("aisha@acme.test")
    client.get(url)
    body = client.post(url, {"decision": "confirm"}, format="json").json()
    assert body["adjudication"] == "confirmed", "the decision is still recorded"
    assert body["opens_defect"] is False, "and no ticket is promised"


def test_the_three_refusals_arrive_as_three_different_status_codes(world):
    url = f"{world['base']}/{world['finding'].id}/"

    wrong_role = _client("dev@acme.test").post(url, {"decision": "confirm"}, format="json")
    assert wrong_role.status_code == 403
    assert "QA Lead" in wrong_role.json()["detail"]

    _client("aisha@acme.test").get(url)
    held = _client("tom@acme.test").post(url, {"decision": "reject", "note": "fine"},
                                         format="json")
    assert held.status_code == 409
    assert "not saved" in held.json()["detail"]

    bad = _client("aisha@acme.test").post(url, {"decision": "reject"}, format="json")
    assert bad.status_code == 400
    assert 'Say why this is fine' in bad.json()["detail"]

    world["finding"].refresh_from_db()
    assert world["finding"].adjudication == "pending", "three refusals, nothing changed"


def test_the_screenshot_streams_as_an_image(world):
    resp = _client("aisha@acme.test").get(
        f"{world['base']}/{world['finding'].id}/screenshot/?kind=page")
    assert resp.status_code == 200
    assert resp["Content-Type"] == "image/png"
    assert resp.content == PNG, "the real bytes, not a pointer or a redirect"
    assert "inline" in resp["Content-Disposition"], "shown in the page, not downloaded"


def test_a_missing_picture_is_a_404_with_a_sentence(world):
    resp = _client("aisha@acme.test").get(
        f"{world['base']}/{world['finding'].id}/screenshot/?kind=element")
    assert resp.status_code == 404
    assert "no picture of this element was cut" in resp.json()["detail"]


def test_an_unknown_finding_is_a_404(world):
    ghost = "00000000-0000-0000-0000-000000000000"
    assert _client("aisha@acme.test").get(f"{world['base']}/{ghost}/").status_code == 404


def test_the_console_needs_a_signed_in_member(world):
    assert APIClient().get(f"{world['base']}/").status_code in (401, 403)


# ══ Reading a finding without reviewing it (S-39) ═════════════════════════════════════
#
# Every AI finding in an audit's report opens with "Screenshot shows…", and the team could
# not find that screenshot anywhere. The pictures existed and an endpoint already served
# them — but the only screen that drew one was the review console, which holds nothing
# except items awaiting a person. All twenty-six findings on the run that prompted this were
# confirmed failures. There was nowhere to look at any of them.
#
# The one genuinely new thing is opening a finding WITHOUT claiming it. `GET a11y-review/<id>`
# takes the review claim as a side effect, which is right for a reviewer working the queue and
# wrong for anyone following a link out of a document.

def _finding_url(world) -> str:
    return f"/api/projects/{world['project'].id}/a11y-finding/{world['finding'].id}/"


def test_a_finding_can_be_opened_to_be_read(world):
    body = _client("aisha@acme.test").get(_finding_url(world)).json()
    assert body["id"] == str(world["finding"].id)
    assert body["criterion"] == "1.1.1"
    assert body["criterion_handle"] == "Non-text Content"
    assert body["evidence"] == "alt reads like a filename"
    assert body["route"] == "/checkout"
    assert body["selector"] == "img.hero"
    # The picture, and where the element sits on it.
    assert body["page_image"] is True
    assert body["box"] == {"x": 8.0, "y": 92.0, "width": 210.0, "height": 88.0}


def test_reading_a_finding_takes_no_claim(world):
    """The whole reason this is not the review endpoint. A failure nobody is reviewing must not
    acquire a reviewer's name because somebody followed a link to look at it."""
    _client("aisha@acme.test").get(_finding_url(world))
    world["finding"].refresh_from_db()
    assert world["finding"].review_locked_by_id is None
    assert world["finding"].review_locked_at is None

    # And the next reviewer to open it properly is not locked out by the reader.
    opened = _client("tom@acme.test").get(
        f"{world['base']}/{world['finding'].id}/").json()
    assert opened["locked_out"] == ""
    assert opened["lock"]["by_me"] is True


def test_reading_says_whether_this_person_could_answer_it(world):
    """The screen offers a way through to the console, and must not offer it to someone who
    cannot answer."""
    assert _client("aisha@acme.test").get(_finding_url(world)).json()["can_review"] is True
    assert _client("dev@acme.test").get(_finding_url(world)).json()["can_review"] is False


def test_the_finding_says_what_it_is_not_only_what_the_ai_thought(world):
    """A report is mostly confirmed failures, and a screen reached from one has to be able to
    say so. The queue's own rows never needed this — everything in it is `needs_review`."""
    body = _client("aisha@acme.test").get(_finding_url(world)).json()
    assert body["outcome"] == "needs_review"
    assert body["status"] == "open"


def test_a_finding_on_another_project_is_not_found(world):
    other = Project.objects.create(tenant=world["project"].tenant, name="Elsewhere")
    resp = _client("aisha@acme.test").get(
        f"/api/projects/{other.id}/a11y-finding/{world['finding'].id}/")
    assert resp.status_code == 404


def test_reading_a_finding_needs_a_session(world):
    assert APIClient().get(_finding_url(world)).status_code in (401, 403)


def test_the_capture_this_came_from_is_named_when_it_was_an_audit(world):
    """"Found by audit 4850688e, 21 August" — resolved from the picture's own capture key, not
    stored on the finding, because a finding outlives every pass that saw it."""
    from apps.a11y.models import A11yBaselineAudit, A11yCandidateBundle

    audit = A11yBaselineAudit.objects.create(
        tenant=world["project"].tenant, project=world["project"],
        base_url="http://localhost:4180", routes=["/checkout"],
        status=A11yBaselineAudit.Status.COMPLETE, summary={"asked": 12, "opened": 12})
    A11yCandidateBundle.objects.filter(tenant=world["project"].tenant).update(
        run_key=str(audit.id))

    body = _client("aisha@acme.test").get(_finding_url(world)).json()
    assert body["captured_by"]["id"] == str(audit.id)
    assert body["captured_by"]["label"] == f"audit {str(audit.id)[:8]}"
    assert body["captured_by"]["opened"] == 12
    assert body["captured_by"]["finished_at"]


def test_a_greenfield_finding_names_no_audit_rather_than_an_empty_one(world):
    """The capture key is a `Run` there. Null is the right answer and must stay one — the same
    rule the work-item provenance follows."""
    assert _client("aisha@acme.test").get(_finding_url(world)).json()["captured_by"] is None


def test_the_report_points_at_the_finding_it_is_describing(world):
    """The other half of the observation: a document that says "screenshot shows" and gives no
    way to reach the screenshot."""
    from apps.a11y.findings import open_findings_for_run
    from apps.a11y.report import report_body

    run_id = world["finding"].last_seen_run_id
    stored = open_findings_for_run(str(world["project"].tenant_id), str(world["project"].id),
                                   run_id)
    body = report_body(MergedReport(rows=[], routes=["/checkout"]), findings=stored)
    assert f"(/a11y/finding/{world['finding'].id})" in body


def test_a_row_that_has_not_reached_the_ledger_is_linked_to_nothing(world):
    """A merge row has no identity yet, so there is nothing to link to — and a link to nowhere
    is worse than none."""
    from apps.a11y.report import report_body

    body = report_body(MergedReport(rows=[ReportRow(
        source=SOURCE_AI, outcome=TRIAGE_REVIEW, criteria=("1.1.1",), route="/checkout",
        selector="img.hero", evidence="e", verdict=A11Y_UNCERTAIN, confidence=0.4,
    )], routes=["/checkout"]))
    assert "/a11y/finding/" not in body


def test_a_merge_row_is_linked_through_the_ledger_it_matches(world):
    """The path the real report takes, and the one that would have silently produced no links.

    A baseline audit manufactures no `Run`, so `open_findings_for_run` matches nothing for it
    and the per-run report renders from the merge — where rows have no id. Resolving them by
    fingerprint is what puts a link on the document a client actually reads.
    """
    from apps.a11y.findings import ids_by_fingerprint
    from apps.a11y.report import report_body

    identity = ids_by_fingerprint(str(world["project"].tenant_id), str(world["project"].id))
    body = report_body(
        MergedReport(rows=[ReportRow(
            source=SOURCE_AI, outcome=TRIAGE_REVIEW, criteria=("1.1.1",), route="/checkout",
            selector="img.hero", evidence="e", verdict=A11Y_UNCERTAIN, confidence=0.4,
            checker="alt",
        )], routes=["/checkout"]),
        identity=identity,
    )
    assert f"(/a11y/finding/{world['finding'].id})" in body


def test_a_merge_row_matching_nothing_in_the_ledger_is_linked_to_nothing(world):
    """A different element on a different screen. The fingerprint is what "the same problem"
    means, so a near miss must not borrow another finding's picture."""
    from apps.a11y.findings import ids_by_fingerprint
    from apps.a11y.report import report_body

    body = report_body(
        MergedReport(rows=[ReportRow(
            source=SOURCE_AI, outcome=TRIAGE_REVIEW, criteria=("1.1.1",), route="/basket",
            selector="img.other", evidence="e", verdict=A11Y_UNCERTAIN, confidence=0.4,
            checker="alt",
        )], routes=["/basket"]),
        identity=ids_by_fingerprint(str(world["project"].tenant_id), str(world["project"].id)),
    )
    assert "/a11y/finding/" not in body
