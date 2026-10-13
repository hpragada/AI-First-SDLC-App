"""G4 — the accessibility judge's plumbing work item stops showing on the user's board.

Every agent run in this platform hangs off a WorkItem, and the judge cannot run on the story:
`_guard_no_active_run` refuses a second run on a work item that already has a live one, and the
build's own run is live for the whole build. So `apps.a11y.aipass` creates a throwaway work item
per test run to host it — internal plumbing, exactly like the onboarding and document-vision
carriers, and hidden by exactly the same filter.

It was hidden by nothing, because it wrote its marker as `external_ref.kind` and every carrier
filter in the platform reads `external_ref.source`. Automate thirty test cases and thirty
"Accessibility judging" tasks appeared on the board, with thirty runs beside them.

**These tests are over HTTP on purpose.** "Excluded from a queryset" is not the claim G4 makes.
The claim is that a person looking at the board does not see it, so the assertions are on the
responses the board, Phases & Runs and the dashboard actually read.

Two things are asserted to STAY visible, and both are load-bearing:

  * the **Accessibility backlog** epic — `apps.a11y.backlog` says in words that it is the
    opposite kind of object: a client is meant to see it, work through it and watch it shrink;
  * a work item whose `external_ref` carries no `source` key at all — the Jira-import shape.
    That is the S3-13 regression: without `carrier_q`'s `has_key` half, Postgres evaluates
    `NULL IN (…)` to NULL and drops the row, and the backlog went empty for every project in the
    product. This file changes the tuple that query reads, so it re-proves the guard.
"""
import pytest
from rest_framework.test import APIClient

from apps.a11y.aipass import judging_work_item
from apps.a11y.backlog import backlog_container
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

PASSWORD = "judging-carrier-pass!"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    user = User.objects.create_user(email="dev@acme.test", name="Dana Ops", tenant=tenant,
                                    password=PASSWORD)
    Membership.objects.create(tenant=tenant, project=project, user=user, role="engineer")
    spec = AgentSpec.objects.create(
        tenant=tenant, key="09c_a11y_judge", semver="1.0.0", prompt_version="a11y-judge-1",
        body_ref="agents/09c_a11y_judge.md", recommended_engine="claude",
        recommended_model="claude-opus-5", phase_label="a11y_judge",
    )
    story = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout",
                                    type=WorkItem.Type.STORY)
    # The Jira-import shape: an `external_ref` with no `source` key at all (S3-13).
    imported = WorkItem.objects.create(
        tenant=tenant, project=project, title="Imported from Jira", type=WorkItem.Type.STORY,
        external_ref={"sor": "jira", "id": "ST-447"},
    )
    epic = backlog_container(tenant_id=str(tenant.id), project_id=str(project.id))
    build_run = Run.objects.create(tenant=tenant, work_item=story, agent_spec=spec,
                                   temporal_workflow_id="build-1", status=Run.Status.RUNNING)
    judging = judging_work_item(tenant_id=str(tenant.id), project_id=str(project.id),
                                run_id=str(build_run.id),
                                parent_work_item_id=str(story.id), title="Checkout")
    judge_run = Run.objects.create(tenant=tenant, work_item=judging, agent_spec=spec,
                                   temporal_workflow_id="judge-1", status=Run.Status.RUNNING)
    return {"tenant": tenant, "project": project, "user": user, "story": story,
            "imported": imported, "epic": epic, "judging": judging,
            "build_run": build_run, "judge_run": judge_run}


def _hdr(tenant_id):
    return {"HTTP_X_TENANT_ID": str(tenant_id)}


def _signed_in(world) -> APIClient:
    """The dashboard is a member-only read, so this one needs a real session."""
    client = APIClient()
    assert client.post("/api/auth/login/",
                       {"email": world["user"].email, "password": PASSWORD},
                       format="json").status_code == 200
    return client


def _board(world) -> dict:
    """The work-item list the board reads, as {id: title}."""
    resp = APIClient().get(f"/api/work-items/?project={world['project'].id}",
                           **_hdr(world["tenant"].id))
    assert resp.status_code == 200
    return {row["id"]: row["title"] for row in resp.data}


def _runs(world) -> set:
    resp = APIClient().get(f"/api/runs/?project={world['project'].id}",
                           **_hdr(world["tenant"].id))
    assert resp.status_code == 200
    return {row["id"] for row in resp.data}


def test_the_judging_task_is_not_on_the_board(world):
    board = _board(world)
    assert str(world["judging"].id) not in board
    assert not [t for t in board.values() if "Accessibility judging" in t]


def test_it_is_the_marker_that_hides_it_and_not_a_coincidence(world):
    """Put `CARRIER_SOURCES` back the way it was and the task returns to the board — so this
    file is testing the fix, not something that was already true for another reason."""
    import integrations.onboarding as onboarding

    before = onboarding.CARRIER_SOURCES
    onboarding.CARRIER_SOURCES = ("onboarding_carrier", "vision_carrier")
    try:
        assert str(world["judging"].id) in _board(world)
    finally:
        onboarding.CARRIER_SOURCES = before


def test_the_work_a_person_authored_is_all_still_there(world):
    board = _board(world)
    assert str(world["story"].id) in board
    assert str(world["imported"].id) in board, \
        "S3-13: a work item with no `source` key must never be hidden"


def test_the_accessibility_backlog_epic_stays_visible(world):
    """The opposite kind of object: a client is meant to see it and watch it shrink."""
    assert str(world["epic"].id) in _board(world)


def test_the_judging_run_is_not_in_phases_and_runs(world):
    runs = _runs(world)
    assert str(world["judge_run"].id) not in runs
    assert str(world["build_run"].id) in runs


def test_the_judging_task_still_resolves_by_id(world):
    """Hidden from the LIST only — a link from a run detail must still open."""
    resp = APIClient().get(f"/api/work-items/{world['judging'].id}/",
                           **_hdr(world["tenant"].id))
    assert resp.status_code == 200
    assert resp.data["id"] == str(world["judging"].id)


def test_the_marker_is_added_and_nothing_else_is_lost(world):
    """`kind` is what the object IS and stays; `source` is what the filters read."""
    ref = WorkItem.objects.get(id=world["judging"].id).external_ref
    assert ref["source"] == "a11y_judging_carrier"
    assert ref["kind"] == "a11y_judging"
    assert ref["run"] == str(world["build_run"].id)


def test_the_judging_tasks_already_on_a_board_are_marked_too(world):
    """`get_or_create` writes the marker on new items only, so without the backfill the fix
    would be invisible on exactly the projects that have the problem. `workitems/0006` is that
    backfill, driven here against a legacy-shaped row."""
    import importlib
    from types import SimpleNamespace

    from django.apps import apps as django_apps
    from django.db import connection

    migration = importlib.import_module(
        "apps.workitems.migrations.0006_a11y_judging_carrier_marker")

    legacy = WorkItem.objects.create(
        tenant=world["tenant"], project=world["project"], type=WorkItem.Type.TASK,
        title="Accessibility judging — an older run", feature_stream="__a11y_judging__old",
        external_ref={"kind": "a11y_judging", "run": "older"},
    )
    assert str(legacy.id) in _board(world), "the row this migration exists for"

    editor = SimpleNamespace(connection=connection)
    migration.mark(django_apps, editor)
    assert str(legacy.id) not in _board(world)
    assert WorkItem.objects.get(id=legacy.id).external_ref == {
        "kind": "a11y_judging", "run": "older", "source": "a11y_judging_carrier"}

    migration.unmark(django_apps, editor)
    assert str(legacy.id) in _board(world), "the reverse leaves the row as it found it"
    assert WorkItem.objects.get(id=legacy.id).external_ref == {
        "kind": "a11y_judging", "run": "older"}


def test_the_dashboard_numbers_agree_with_the_lists_beside_them(world):
    """A count that disagrees with the list it summarises is worse than no count: the board
    showed 30 items while "Work items" said 62, and Phases & Runs showed nothing running while
    "Phases in progress" said 1."""
    resp = _signed_in(world).get(f"/api/projects/{world['project'].id}/dashboard/",
                                 **_hdr(world["tenant"].id))
    assert resp.status_code == 200
    health = resp.data["health"]
    assert health["work_items"] == len(_board(world))
    assert health["phases_in_progress"] == 1, "the build's run, not the judge's"
