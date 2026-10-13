"""Bugs S.No 230 — the agent briefing must show a run its OWN project's history.

The briefing's recent-events list took the last 20 events for the whole TENANT, muting one noisy
action and nothing else. The event row carried no link to a project or a work item, so there was
nothing to scope on — and the ledger is append-only, so events outlive the runs that wrote them.

What that looked like in practice, on a brand-new work item: two clarification questions in its
history, with no answers beside them, belonging to earlier runs on DIFFERENT work items that had
since been deleted. At best noise. At worst an agent reasons from another work item's decisions,
or believes something has already been asked and answered when it has not.

The scope is resolved once, at write time, from the event's target — rather than threaded through
the hundred-odd `log_event` call sites, half of which sit in the build and orchestration paths.
"""
import pytest
from mcp_platform_state import tools

from apps.clarifications.models import Clarification
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile, Repository
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    alpha = Project.objects.create(tenant=t, name="Alpha")
    beta = Project.objects.create(tenant=t, name="Beta")
    for p in (alpha, beta):
        ProjectProfile.objects.create(tenant=t, project=p, important_context="ctx")
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    wi_a = WorkItem.objects.create(tenant=t, project=alpha, type=WorkItem.Type.STORY,
                                   title="Checkout")
    wi_a2 = WorkItem.objects.create(tenant=t, project=alpha, type=WorkItem.Type.STORY,
                                    title="Search")
    wi_b = WorkItem.objects.create(tenant=t, project=beta, type=WorkItem.Type.STORY,
                                   title="Billing")
    return {"t": t, "alpha": alpha, "beta": beta, "spec": spec,
            "wi_a": wi_a, "wi_a2": wi_a2, "wi_b": wi_b}


def _run(world, wi):
    return Run.objects.create(tenant=world["t"], work_item=wi, agent_spec=world["spec"])


def _context(world, project, wi=None):
    return tools.get_context(
        str(world["t"].id), str(project.id), "03_prd",
        work_item_id=str(wi.id) if wi else None,
    )


def _actions(ctx):
    return [e["action"] for e in ctx["recent_events"]]


# ── the scope is resolved from the target ───────────────────────────
def test_a_run_event_is_scoped_to_its_work_items_project(world):
    run = _run(world, world["wi_a"])

    tools.log_event(str(world["t"].id), "orchestrator", "phase.dispatched", "run", str(run.id))

    event = Event.objects.get(action="phase.dispatched")
    assert str(event.project_id) == str(world["alpha"].id)
    assert str(event.work_item_id) == str(world["wi_a"].id)


def test_a_work_item_event_is_scoped_to_itself(world):
    tools.log_event(str(world["t"].id), "platform", "workitem.transitioned", "work_item",
                    str(world["wi_b"].id))

    event = Event.objects.get(action="workitem.transitioned")
    assert str(event.project_id) == str(world["beta"].id)
    assert str(event.work_item_id) == str(world["wi_b"].id)


def test_a_target_that_belongs_to_a_project_but_no_work_item_scopes_to_the_project(world):
    repo = Repository.objects.create(tenant=world["t"], project=world["alpha"], name="acme/api",
                                     default_base="main")

    tools.log_event(str(world["t"].id), "platform", "repository.registered", "repository",
                    str(repo.id))

    event = Event.objects.get(action="repository.registered")
    assert str(event.project_id) == str(world["alpha"].id)
    assert event.work_item_id is None


def test_an_artifact_with_no_run_still_scopes_to_its_project(world):
    art = Artifact.objects.create(tenant=world["t"], project=world["alpha"], phase="03_prd",
                                  type="prd", sor="internal", content_hash="h", s3_key="k")

    tools.log_event(str(world["t"].id), "platform", "artifacts.published", "artifact",
                    str(art.id))

    event = Event.objects.get(action="artifacts.published")
    assert str(event.project_id) == str(world["alpha"].id)
    assert event.work_item_id is None


def test_a_caller_that_knows_the_scope_can_say_so(world):
    tools.log_event(str(world["t"].id), "platform", "a11y.routes.registered", "project",
                    str(world["beta"].id), project_id=str(world["beta"].id))

    assert str(Event.objects.get(action="a11y.routes.registered").project_id) == \
        str(world["beta"].id)


# ── it must never become a new way for a write to fail ──────────────
@pytest.mark.parametrize("target_type,target_id", [
    ("branch", None),               # the ref lives in the payload; there is no UUID
    ("commit", None),
    ("pull_request", None),         # a PR number is not a UUID — this used to raise on save
    ("run", "00000000-0000-0000-0000-000000000009"),   # a target that no longer exists
    ("something_nobody_mapped", "00000000-0000-0000-0000-000000000009"),
])
def test_an_unresolvable_target_records_the_event_anyway(world, target_type, target_id):
    out = tools.log_event(str(world["t"].id), "webhook", "webhook.pr_unmatched", target_type,
                          target_id, {"repo": "acme/api", "number": 42})

    assert out["action"] == "webhook.pr_unmatched"
    event = Event.objects.get(id=out["id"])
    assert event.project_id is None and event.work_item_id is None


# ── what a briefing now sees ────────────────────────────────────────
def test_another_projects_events_never_reach_this_briefing(world):
    tools.log_event(str(world["t"].id), "orchestrator", "phase.dispatched", "run",
                    str(_run(world, world["wi_a"]).id))
    tools.log_event(str(world["t"].id), "orchestrator", "build.merged", "run",
                    str(_run(world, world["wi_b"]).id))

    ctx = _context(world, world["alpha"], world["wi_a"])

    assert "phase.dispatched" in _actions(ctx)
    assert "build.merged" not in _actions(ctx), "that belongs to a different project"


def test_a_question_asked_on_another_work_item_never_reaches_this_briefing(world):
    """The observed failure: a brand-new work item was shown two unanswered questions that
    belonged to earlier runs on other work items, from runs since deleted."""
    other_run = _run(world, world["wi_a2"])
    clar = Clarification.objects.create(tenant=world["t"], run=other_run,
                                        work_item=world["wi_a2"], phase="03_prd",
                                        questions=[{"id": "q1", "text": "Which currency?"}])
    tools.log_event(str(world["t"].id), "agent", "clarification.asked", "clarification",
                    str(clar.id))
    other_run.delete()      # the run is gone; the append-only event survives it

    ctx = _context(world, world["alpha"], world["wi_a"])

    assert "clarification.asked" not in _actions(ctx)


def test_this_work_items_own_question_is_still_shown(world):
    run = _run(world, world["wi_a"])
    clar = Clarification.objects.create(tenant=world["t"], run=run, work_item=world["wi_a"],
                                        phase="03_prd",
                                        questions=[{"id": "q1", "text": "Which currency?"}])
    tools.log_event(str(world["t"].id), "agent", "clarification.asked", "clarification",
                    str(clar.id))

    ctx = _context(world, world["alpha"], world["wi_a"])

    assert "clarification.asked" in _actions(ctx)


def test_a_question_always_arrives_with_its_answer(world):
    """A question shown without what was decided is misleading even when it IS this work
    item's — the answered-clarifications channel is what carries both."""
    run = _run(world, world["wi_a"])
    Clarification.objects.create(
        tenant=world["t"], run=run, work_item=world["wi_a"], phase="03_prd",
        status=Clarification.Status.ANSWERED,
        questions=[{"id": "q1", "text": "Which currency?"}],
        answers={"q1": "GBP"},
    )

    ctx = _context(world, world["alpha"], world["wi_a"])

    replayed = ctx["answered_clarifications"]
    assert replayed and replayed[0]["questions"][0]["text"] == "Which currency?"
    assert replayed[0]["answers"] == {"q1": "GBP"}


def test_a_run_with_no_work_item_gets_the_projects_history(world):
    """Onboarding and code-indexing runs have no work item. The project-scoped list is the
    right answer for them — and no clarification from any work item leaks in."""
    tools.log_event(str(world["t"].id), "orchestrator", "phase.dispatched", "run",
                    str(_run(world, world["wi_a"]).id))
    clar = Clarification.objects.create(tenant=world["t"], run=_run(world, world["wi_a"]),
                                        work_item=world["wi_a"], phase="03_prd",
                                        questions=[{"id": "q1", "text": "Which currency?"}])
    tools.log_event(str(world["t"].id), "agent", "clarification.asked", "clarification",
                    str(clar.id))

    ctx = _context(world, world["alpha"])

    assert "phase.dispatched" in _actions(ctx)
    assert "clarification.asked" not in _actions(ctx)


def test_events_written_before_the_columns_existed_fall_out(world):
    """They carry no project, and that is the intent: stale noise from runs nobody can trace.
    They stay readable through the events API — this only changes what an agent is handed."""
    Event.objects.create(tenant=world["t"], actor="orchestrator", action="run.triggered",
                         target_type="run", target_id=None)

    ctx = _context(world, world["alpha"], world["wi_a"])

    assert "run.triggered" not in _actions(ctx)
    assert Event.objects.filter(action="run.triggered").count() == 1
