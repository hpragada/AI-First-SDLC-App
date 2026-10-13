"""G6b — the two endpoints the keyboard-journeys panel talks to.

`apps.a11y.journey` is tested directly in `test_a11y_journey.py`. This file is about the seam
the screen will call: does the list come back with the address pre-filled, does starting one
actually start it, and does a refusal arrive as a status code a screen can branch on.

**403 is the one that matters here.** Anyone on the project may LOOK at this list — a developer
wanting to see what the QA Lead is checking is exactly the transparency this build is for. Only
the accessibility reviewer may spend a real browser on it. Two different answers, so the panel
can show the list read-only rather than an error page.
"""
import pytest
from rest_framework.test import APIClient

from apps.a11y.models import A11yBaselineAudit, A11yJourneyRun
from apps.projects.models import Project, Repository
from apps.registry.models import AgentSpec
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.types import A11yJourney

PASSWORD = "journey-pass!"


@pytest.fixture
def world(db, monkeypatch):
    from apps.a11y import journey as journey_mod
    from apps.a11y import journeys as journeys_mod
    from apps.a11y.journeys import parse_steps

    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="SpendLog")
    WorkItem.objects.create(tenant=tenant, project=project, title="Log an expense")
    AgentSpec.objects.create(tenant=tenant, key="09d_a11y_journey", semver="1.0.0", body_ref="x")
    Repository.objects.create(tenant=tenant, project=project, name="acme/web",
                              is_default=True, preview_url="http://127.0.0.1:5173")

    body = """### Test Steps
1. Open /basket
2. Pay
"""
    walkable = [A11yJourney(test_ref="TC-031", title="Checkout", artifact_id="a-1",
                            steps=tuple(parse_steps(body)))]
    monkeypatch.setattr(journeys_mod, "journeys_for_project",
                        lambda *a, **k: {"journeys": walkable, "skipped": [
                            {"artifact_id": "a-2", "title": "TC-077", "test_ref": "TC-077",
                             "reason": "declares Type: E2E but no steps could be read"}],
                            "over_cap": []})
    monkeypatch.setattr(journey_mod, "journey_available", lambda *a, **k: "")

    # A trigger that never reaches Temporal. An unpatched one here would start a REAL workflow
    # on the team's shared server.
    import uuid

    from apps.runs.models import Run

    def _trigger(**kwargs):
        run = Run.objects.create(tenant=tenant, agent_spec=AgentSpec.objects.get(tenant=tenant),
                                 work_item_id=kwargs["work_item_id"], status="running")
        return type("Outcome", (), {"run_id": str(run.id), "workflow_id": str(uuid.uuid4())})()

    real_queue = journey_mod.queue_journeys
    monkeypatch.setattr(
        journey_mod, "queue_journeys",
        lambda **kw: real_queue(**{**kw, "trigger": _trigger}))

    lead = User.objects.create_user(email="lead@acme.test", name="Aisha", tenant=tenant,
                                    password=PASSWORD)
    dev = User.objects.create_user(email="dev@acme.test", name="Dana", tenant=tenant,
                                   password=PASSWORD)
    Membership.objects.create(tenant=tenant, project=project, user=lead, role="qa_lead")
    Membership.objects.create(tenant=tenant, project=project, user=dev, role="engineer")
    return {"tenant": tenant, "project": project,
            "url": f"/api/projects/{project.id}/a11y-journeys/"}


def _client(email):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": email, "password": PASSWORD},
                       format="json").status_code == 200
    return client


def test_the_list_carries_the_journeys_the_address_and_what_cannot_be_walked(world):
    body = _client("lead@acme.test").get(world["url"]).json()

    (row,) = body["journeys"]
    assert row["test_ref"] == "TC-031" and row["steps"] == 2
    assert row["last_walked"] is None
    # The address the panel pre-fills, and where it came from — one payload, not two calls.
    assert body["base_url"] == "http://127.0.0.1:5173"
    assert "acme/web" in body["base_url_source"]
    assert body["max_journeys"] == 10
    assert body["can_start"] is True
    # And the E2E case nobody can walk, with its reason, rather than quietly absent.
    (blocked,) = body["unwalkable"]
    assert blocked["test_ref"] == "TC-077" and "no steps could be read" in blocked["reason"]


def test_the_address_prefers_the_last_audit_over_the_repository(world):
    A11yBaselineAudit.objects.create(tenant=world["tenant"], project=world["project"],
                                     base_url="http://localhost:4180", routes=["/"],
                                     status=A11yBaselineAudit.Status.COMPLETE)
    body = _client("lead@acme.test").get(world["url"]).json()
    assert body["base_url"] == "http://localhost:4180"
    assert body["base_url_source"] == "your last audit"


def test_starting_a_journey_over_rest_really_starts_it(world):
    resp = _client("lead@acme.test").post(
        world["url"], {"base_url": "http://127.0.0.1:5173"}, format="json")

    assert resp.status_code == 200, resp.content
    (started,) = resp.json()["started"]
    assert started["name"] == "TC-031" and started["steps"] == 2
    row = A11yJourneyRun.objects.get(tenant_id=world["tenant"].id)
    assert row.base_url == "http://127.0.0.1:5173"
    assert row.status == A11yJourneyRun.Status.WALKING


def test_a_reader_sees_the_list_and_is_refused_the_button(world):
    client = _client("dev@acme.test")
    listed = client.get(world["url"])
    assert listed.status_code == 200
    assert len(listed.json()["journeys"]) == 1, "read-only, not hidden"
    assert listed.json()["can_start"] is False, "so the screen can grey the button, not fail it"

    refused = client.post(world["url"], {"base_url": "http://127.0.0.1:5173"}, format="json")
    assert refused.status_code == 403
    assert "accessibility reviewer" in refused.json()["detail"]
    assert A11yJourneyRun.objects.count() == 0


def test_starting_with_no_address_starts_nothing_and_says_why(world):
    resp = _client("lead@acme.test").post(world["url"], {}, format="json")
    assert resp.status_code == 200
    assert resp.json()["started"] == []
    assert "start the application" in resp.json()["reason"]
    assert A11yJourneyRun.objects.count() == 0


def test_a_malformed_selection_is_a_400_not_a_crash(world):
    resp = _client("lead@acme.test").post(
        world["url"], {"base_url": "http://x", "test_refs": "TC-031"}, format="json")
    assert resp.status_code == 400
    assert "list" in resp.json()["detail"]


# ── Dispatched is not the same as walking (#4) ──────────────────────────────
#
# `_dispatch_journey` marks the row WALKING the moment the run is triggered, which is right: the
# platform has handed the work over and will not hand it to anyone else. But the panel rendered
# that as "Walking now", so a journey dispatched with no companion online read as a browser
# stepping through the application — for ever. The audit strip directly above it has told those
# two states apart since task 8a, and one screen should not hold itself to two standards.


def _dispatch_state(run_id, state):
    from apps.runs.models import Run

    run = Run.objects.get(id=run_id)
    inputs = dict(run.inputs or {})
    inputs["dispatch"] = {**(inputs.get("dispatch") or {}), "status": state}
    run.inputs = inputs
    run.save(update_fields=["inputs"])


def test_a_dispatched_journey_no_machine_has_taken_reads_as_waiting(world):
    started = _client("lead@acme.test").post(
        world["url"], {"base_url": "http://127.0.0.1:5173"}, format="json").json()
    _dispatch_state(started["started"][0]["run_id"], "pending")

    (row,) = _client("lead@acme.test").get(world["url"]).json()["journeys"]
    assert row["status"] == "queued", "dispatched, and nothing has picked it up"
    # The stored row is untouched — this is a reading of it, not a second state to keep in step.
    assert A11yJourneyRun.objects.get().status == A11yJourneyRun.Status.WALKING


def test_once_a_machine_claims_it_the_row_says_walking(world):
    started = _client("lead@acme.test").post(
        world["url"], {"base_url": "http://127.0.0.1:5173"}, format="json").json()
    _dispatch_state(started["started"][0]["run_id"], "claimed")

    (row,) = _client("lead@acme.test").get(world["url"]).json()["journeys"]
    assert row["status"] == "walking"


def test_a_finished_walk_is_finished_however_it_was_dispatched(world):
    """Only the ones claiming to be in flight are worth asking about — a completed walk must not
    be re-described by the state of the run that produced it."""
    started = _client("lead@acme.test").post(
        world["url"], {"base_url": "http://127.0.0.1:5173"}, format="json").json()
    _dispatch_state(started["started"][0]["run_id"], "pending")
    A11yJourneyRun.objects.update(status=A11yJourneyRun.Status.COMPLETE)

    (row,) = _client("lead@acme.test").get(world["url"]).json()["journeys"]
    assert row["status"] == A11yJourneyRun.Status.COMPLETE
