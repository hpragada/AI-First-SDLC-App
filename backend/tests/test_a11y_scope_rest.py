"""Who may change what an audit covers, and who may start one.

These four endpoints — the page list, one page, audits, and the review queue's empty state —
had **no role check of any kind**. They fell through `ProjectViewSet.get_permissions` to the
viewset default — `AllowAny` — so changing the whole page list or spending a machine on an audit
was open to any session in the tenant, while starting a keyboard journey on the very same screen
was refused for anyone but the accessibility reviewer.

Nothing escaped the tenant, so this was never a cross-customer hole. It was an inconsistency
sitting on top of the input every later number depends on: page scope decides what a baseline
covers, so a page quietly taken out of scope makes the next report read as an improvement.

The list is wider than the reviewer's on purpose (`policy.PAGE_MANAGE_ROLES`). Saying which
pages an application has is ordinary project work; deciding a finding and signing a conformance
statement are not.
"""
import json

import pytest
from rest_framework.test import APIClient

from apps.a11y.models import A11yBaselineAudit, A11yFinding, A11yRoute
from apps.projects.models import Project, Repository
from apps.tenancy.models import Membership, Tenant, User

PASSWORD = "scope-pass!"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Meridian")
    Repository.objects.create(tenant=tenant, project=project, name="acme/web",
                              is_default=True, preview_url="http://127.0.0.1:4180")
    A11yRoute.objects.create(tenant=tenant, project=project, path="/", label="Home",
                             enabled=True, source="manual")

    people = {}
    for email, role in (("lead@acme.test", "qa_lead"), ("tech@acme.test", "tech_lead"),
                        ("dev@acme.test", "engineer"), ("po@acme.test", "product_owner")):
        user = User.objects.create_user(email=email, name=email.split("@")[0], tenant=tenant,
                                        password=PASSWORD)
        Membership.objects.create(tenant=tenant, project=project, user=user, role=role)
        people[role] = user

    boss = User.objects.create_user(email="boss@acme.test", name="Boss", tenant=tenant,
                                    password=PASSWORD, is_tenant_admin=True)
    people["tenant_admin"] = boss
    return {"tenant": tenant, "project": project, "people": people,
            "routes": f"/api/projects/{project.id}/a11y-routes/",
            "audits": f"/api/projects/{project.id}/a11y-audits/",
            "review": f"/api/projects/{project.id}/a11y-review/"}


def _client(email):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": email, "password": PASSWORD},
                       format="json").status_code == 200
    return client


def _route_id(world):
    return str(A11yRoute.objects.get(project_id=world["project"].id, path="/").id)


# ── Reading ─────────────────────────────────────────────────────────────────


def test_anyone_on_the_project_can_read_the_page_list(world):
    """Read-only, never hidden. A developer seeing what the QA Lead is checking is the
    transparency this build is for — the same answer the journeys panel already gives."""
    body = _client("dev@acme.test").get(world["routes"]).json()
    assert [r["path"] for r in body["routes"]] == ["/"]
    assert body["can_manage"] is False, "so the screen greys the buttons rather than failing them"


def test_the_payload_tells_an_operator_they_may_operate(world):
    for email in ("lead@acme.test", "tech@acme.test", "boss@acme.test"):
        assert _client(email).get(world["routes"]).json()["can_manage"] is True, email


# ── Writing ─────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("email", ["lead@acme.test", "tech@acme.test", "boss@acme.test"])
def test_the_three_who_may_change_the_page_list_can(world, email):
    resp = _client(email).put(
        world["routes"], {"routes_text": "/\n/catalogue"}, format="json")
    assert resp.status_code == 200, resp.content
    assert A11yRoute.objects.filter(project_id=world["project"].id).count() == 2


@pytest.mark.parametrize("email", ["dev@acme.test", "po@acme.test"])
def test_everyone_else_is_refused_and_nothing_is_written(world, email):
    resp = _client(email).put(world["routes"], {"routes_text": "/\n/catalogue"}, format="json")
    assert resp.status_code == 403
    assert "QA Lead, Tech Lead or Admin" in resp.json()["detail"]
    assert A11yRoute.objects.filter(project_id=world["project"].id).count() == 1


def test_a_preview_is_a_write_in_disguise_and_is_refused_too(world):
    """It writes nothing, but it reads the whole page list back with each page's recorded
    problems. Same door, same lock."""
    resp = _client("dev@acme.test").put(
        world["routes"], {"routes_text": "/", "preview": True}, format="json")
    assert resp.status_code == 403


def test_editing_one_page_is_refused_for_a_reader(world):
    url = f"{world['routes']}{_route_id(world)}/"
    resp = _client("dev@acme.test").patch(url, {"enabled": False}, format="json")
    assert resp.status_code == 403
    assert A11yRoute.objects.get(path="/").enabled is True, "still in scope"


def test_removing_a_page_is_refused_for_a_reader(world):
    """The sharpest of the four. Taking a page out of scope makes the next baseline read as an
    improvement, and nothing in the report says a page stopped being covered by a person who
    was not meant to decide that."""
    url = f"{world['routes']}{_route_id(world)}/"
    assert _client("dev@acme.test").delete(url).status_code == 403
    assert A11yRoute.objects.filter(path="/").exists()


def test_editing_one_page_still_works_for_a_tech_lead(world):
    url = f"{world['routes']}{_route_id(world)}/"
    resp = _client("tech@acme.test").patch(url, {"enabled": False}, format="json")
    assert resp.status_code == 200, resp.content
    assert A11yRoute.objects.get(path="/").enabled is False


# ── Starting an audit ───────────────────────────────────────────────────────


def test_starting_an_audit_is_refused_for_a_reader(world):
    """An audit spends a real browser on a real application for minutes. Same list as the page
    scope it runs over, because they are one decision taken twice."""
    resp = _client("dev@acme.test").post(world["audits"], {}, format="json")
    assert resp.status_code == 403
    assert A11yBaselineAudit.objects.count() == 0


def test_starting_an_audit_works_for_the_qa_lead(world):
    resp = _client("lead@acme.test").post(world["audits"], {}, format="json")
    assert resp.status_code == 201, resp.content
    assert A11yBaselineAudit.objects.count() == 1


def test_anyone_may_read_the_audit_history(world):
    A11yBaselineAudit.objects.create(tenant=world["tenant"], project=world["project"],
                                     base_url="http://127.0.0.1:4180", routes=["/"])
    body = _client("dev@acme.test").get(world["audits"]).json()
    assert len(body["audits"]) == 1


# ── A session at all ────────────────────────────────────────────────────────


def test_reading_now_needs_a_session_at_all(world):
    """These five actions used to fall through to the viewset default — `AllowAny`, which does
    not even require somebody to be logged in.

    `IsAuthenticatedMember` gates exactly that and no more (tenant scoping and RLS do the rest);
    it is not a per-project membership check, and every other project surface uses it the same
    way. So this asserts what actually changed, not what its name suggests.
    """
    from rest_framework.test import APIClient

    anonymous = APIClient()
    assert anonymous.get(world["routes"]).status_code in (401, 403)
    assert anonymous.get(world["audits"]).status_code in (401, 403)


def test_a_signed_in_non_member_reads_but_cannot_write(world):
    """Consistent with the rest of the platform on reading, and locked on writing — which is
    the half that was open."""
    User.objects.create_user(email="stranger@acme.test", name="Stranger",
                             tenant=world["tenant"], password=PASSWORD)
    client = _client("stranger@acme.test")
    assert client.get(world["routes"]).json()["can_manage"] is False
    assert client.put(world["routes"], {"routes_text": "/x"}, format="json").status_code == 403
    assert client.post(world["audits"], {}, format="json").status_code == 403


# ── The review queue's two empty states (#5) ────────────────────────────────


def test_an_untouched_project_says_nothing_has_been_checked(world):
    """Not "every check so far was sure enough to answer on its own", which is vacuously true of
    a project where nothing has run and reads as reassurance to the one reader who most needs
    pointing at the starting line."""
    body = _client("lead@acme.test").get(world["review"]).json()
    assert body["queue"] == []
    assert body["ever_checked"] is False


def test_a_project_that_has_been_scanned_gets_the_other_sentence(world):
    from apps.a11y.models import A11yScreenScan

    A11yScreenScan.objects.create(tenant=world["tenant"], project=world["project"],
                                  route="/", screen_hash="h1")
    body = _client("lead@acme.test").get(world["review"]).json()
    assert body["queue"] == [] and body["ever_checked"] is True


def test_a_journey_finding_counts_as_having_looked_even_with_no_scan(world):
    """A keyboard journey writes findings and never writes a screen scan. Asking only about
    scans would tell a project that has walked every journey that nothing had been checked."""
    A11yFinding.objects.create(
        tenant=world["tenant"], project=world["project"], route="/", criterion="2.1.2",
        checker="trap", severity="Critical", status=A11yFinding.Status.OPEN,
        outcome="failure", fingerprint="f1", selector="button.next", evidence="tab trap",
    )
    body = _client("lead@acme.test").get(world["review"]).json()
    assert body["ever_checked"] is True


def test_the_question_is_only_asked_when_the_queue_is_empty(world, django_assert_num_queries):
    """Two extra `.exists()` on the busiest accessibility screen, every poll, would be a real
    cost for an answer nothing reads. A non-empty queue answers `True` without asking."""
    from apps.a11y import review as review_mod

    asked = []
    real = review_mod.ever_checked
    review_mod.ever_checked = lambda **kw: asked.append(kw) or real(**kw)
    try:
        # Exactly what `findings.review_queue` selects: open, needs_review, nobody has ruled.
        A11yFinding.objects.create(
            tenant=world["tenant"], project=world["project"], route="/", criterion="1.4.3",
            checker="color", severity="High", status=A11yFinding.Status.OPEN,
            outcome="needs_review", adjudication=A11yFinding.Adjudication.PENDING,
            fingerprint="f2", selector="p.muted", evidence="grey on white",
        )
        body = _client("lead@acme.test").get(world["review"]).json()
    finally:
        review_mod.ever_checked = real
    assert len(body["queue"]) == 1
    assert body["ever_checked"] is True
    assert asked == [], "not asked at all when there is something in the queue"


def test_the_registered_list_round_trips_a_pasted_line_list(world):
    """End to end over REST, because the format people actually paste had never reached here."""
    resp = _client("lead@acme.test").put(
        world["routes"], {"routes_text": "/\n/catalogue\n# skip me\n/account"}, format="json")
    assert resp.status_code == 200, resp.content
    assert sorted(r["path"] for r in resp.json()["routes"]) == ["/", "/account", "/catalogue"]


def test_in_scope_survives_the_round_trip_over_rest(world):
    resp = _client("lead@acme.test").put(world["routes"], {"routes_text": json.dumps([
        {"path": "/", "in_scope": True},
        {"path": "/health", "in_scope": False},
    ])}, format="json")
    assert resp.status_code == 200, resp.content
    scope = {r["path"]: r["enabled"] for r in resp.json()["routes"]}
    assert scope["/health"] is False, "the flag our own reference app writes is honoured"


# ── An audit opened from the app has to be one a machine can pick up ────────


def test_an_audit_started_from_the_app_waits_for_a_machine(world):
    """The audit the button opens must be CLAIMABLE, and nothing else asserted this.

    `start_baseline_audit(claimable=...)` decides the opening status: `pending` — waiting for a
    machine — or `capturing`, which means "a machine is already visiting". The REST caller did
    not pass it, so every audit opened from the app was born `capturing`, and
    `RunnerA11yAuditClaimView` only ever offers `pending` (or a `claimed` one past its lease).
    No companion could see it. The audit sat still while the screen read "Visiting pages".

    Every existing claim test passes `claimable=True` by hand, which is exactly why they all
    passed while the only caller that ships was wired the other way. This asserts the wiring.
    """
    resp = _client("lead@acme.test").post(world["audits"], {}, format="json")
    assert resp.status_code == 201, resp.content
    assert resp.json()["status"] == A11yBaselineAudit.Status.PENDING

    audit = A11yBaselineAudit.objects.get(id=resp.json()["audit_id"])
    assert audit.status == A11yBaselineAudit.Status.PENDING
    assert audit.enrollment_id is None, "opened for whichever machine claims it, not a named one"


def test_a_waiting_audit_is_what_the_companion_is_offered(world):
    """The other half of the same fact, from the machine's side.

    The bug lived in the seam between two halves that were each tested alone: the app opened an
    audit, the companion asked for one, and nothing joined them up. So this opens one the way the
    button does — over REST — and then claims it the way the companion does.
    """
    from django.test import RequestFactory

    from api.runner_views import RunnerA11yAuditClaimView, RunnerStateView
    from apps.runs.models import RunnerEnrollment

    started = _client("lead@acme.test").post(world["audits"], {}, format="json").json()

    runner = RunnerEnrollment.objects.create(
        tenant=world["tenant"], project=world["project"], label="laptop",
        enroll_token_hash="hash-laptop")
    original = RunnerStateView._resolve_runner
    RunnerStateView._resolve_runner = staticmethod(lambda _r: runner)
    try:
        claimed = RunnerA11yAuditClaimView().get(
            RequestFactory().get("/api/runner/a11y-audits/"))
    finally:
        RunnerStateView._resolve_runner = original

    assert claimed.status_code == 200, claimed.data
    assert str(claimed.data["audit_id"]) == started["audit_id"]
    assert claimed.data["manifest"]["routes"] == ["/"], "and it carries what to visit"


# ── Asking again about what nothing looked at (task R1) ─────────────────────


def _closed_audit(world, status="complete"):
    return A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"],
        base_url="http://127.0.0.1:4180", routes=["/"], status=status)


def _rejudge_url(world, audit):
    return f"{world['audits']}{audit.id}/rejudge/"


def test_asking_again_is_refused_for_a_reader(world):
    """It spends a real engine run, so it is the same decision as starting an audit — taken
    twice, and gated the same way both times."""
    audit = _closed_audit(world)
    resp = _client("dev@acme.test").post(_rejudge_url(world, audit), {}, format="json")
    assert resp.status_code == 403


def test_asking_again_needs_a_session_at_all(world):
    """The whole a11y surface fell through to `AllowAny` once (§9 #2). A new write on it must
    not reopen that by being left out of the permission list."""
    audit = _closed_audit(world)
    assert APIClient().post(_rejudge_url(world, audit), {}, format="json").status_code in (401, 403)


def test_asking_again_about_an_audit_that_has_not_finished_is_refused_by_name(world):
    """While a pass is running, "what has nothing looked at" is still changing — and offering to
    re-ask about elements the judge is at that moment working through would start a second pass
    over the same work. Refused with the reason, not silently ignored."""
    audit = _closed_audit(world, status="judging")
    resp = _client("lead@acme.test").post(_rejudge_url(world, audit), {}, format="json")
    assert resp.status_code == 409
    assert "hasn't finished yet" in resp.json()["detail"]


def test_asking_again_about_another_projects_audit_is_a_404(world):
    """Scoped to the project in the URL, not just to the tenant."""
    other = Project.objects.create(tenant=world["tenant"], name="Somewhere else")
    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=other, routes=["/"], status="complete")
    resp = _client("lead@acme.test").post(_rejudge_url(world, audit), {}, format="json")
    assert resp.status_code == 404


def test_asking_again_with_nothing_unanswered_says_so_rather_than_starting_a_run(world):
    """A closed audit where every element was looked at has nothing to ask about, and says so in
    words instead of dispatching a judging run that would judge nothing."""
    audit = _closed_audit(world)
    resp = _client("lead@acme.test").post(_rejudge_url(world, audit), {}, format="json")
    assert resp.status_code == 200, resp.content
    body = resp.json()
    assert body["started"] is False and body["asked"] == 0
    assert "has been looked at" in body["reason"]


def test_the_audit_list_says_how_many_were_never_looked_at(world):
    """What the button counts. Read from what the pass recorded about itself — here, the
    elements the dispatch could not ask about at all, because no judge was registered."""
    audit = _closed_audit(world)
    audit.summary = {"ai_pass": {"filed_unjudged": 12}}
    audit.save(update_fields=["summary"])
    [row] = _client("dev@acme.test").get(world["audits"]).json()["audits"]
    assert row["unanswered"] == 12


def test_an_audit_still_running_is_never_offered_a_rejudge_on_the_list(world):
    """The count is only computed for closed audits, so the button cannot appear on one whose
    answer is still moving."""
    audit = _closed_audit(world, status="judging")
    audit.summary = {"ai_pass": {"filed_unjudged": 12}}
    audit.save(update_fields=["summary"])
    [row] = _client("dev@acme.test").get(world["audits"]).json()["audits"]
    assert row["unanswered"] == 0


def test_the_newest_finished_audit_carries_what_the_panel_shows(world):
    """The panel stays after the run ends, so the numbers it shows have to be on the payload —
    and only on the newest, because that is the only audit it shows."""
    from apps.a11y.models import A11yFinding

    older = _closed_audit(world)
    newest = _closed_audit(world)
    A11yFinding.objects.create(
        tenant=world["tenant"], project=world["project"], fingerprint="c" * 64,
        route="/", selector="#a", criterion="1.1.1", source="ai", outcome="failure",
        severity="critical", status=A11yFinding.Status.OPEN)

    rows = {r["id"]: r for r in _client("dev@acme.test").get(world["audits"]).json()["audits"]}
    assert rows[str(newest.id)]["outcome"]["problems"] == 1
    assert rows[str(newest.id)]["outcome"]["critical"] == 1
    assert rows[str(older.id)]["outcome"] is None, "every older audit is a row, not the panel"


def test_an_audit_still_running_carries_no_outcome_yet(world):
    """While it is going, what it came to is not a settled fact."""
    audit = _closed_audit(world, status="judging")
    [row] = _client("dev@acme.test").get(world["audits"]).json()["audits"]
    assert row["id"] == str(audit.id)
    assert row["outcome"] is None
    assert row["progress"] is not None, "…but its live progress is there"

