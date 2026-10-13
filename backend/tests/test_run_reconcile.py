"""The safety net: notice when the platform's story and Temporal's disagree.

Behind these is a real incident. An audit was judged in full and then stopped
dead — the judging run said `completed`, its workflow had closed cleanly, and the
screen said *Checking what was found* for ever. Nothing was inconsistent about
the run itself, which is why the generic check below would not have caught it and
why the accessibility check exists alongside it.

The other half of what these pin down is restraint. A reconciler that repairs
when it is not sure is worse than none at all: it would close healthy runs the
moment Temporal hiccups. Roughly half of these tests assert that nothing
happened.
"""
from __future__ import annotations

import pytest
from django.utils import timezone

from apps.a11y.aipass import SOURCE_RUN_KEY
from apps.a11y.models import A11yBaselineAudit
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.runs.reconcile import WorkflowState, reconcile_tenant
from apps.tenancy.models import Tenant, User
from apps.workitems.models import WorkItem

PASSWORD = "pw-for-tests"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Shop")
    user = User.objects.create_user(
        email="qa@acme.com", name="QA", tenant=tenant, password=PASSWORD
    )
    work_item = WorkItem.objects.create(tenant=tenant, project=project, title="Checkout")
    spec = AgentSpec.objects.create(
        tenant=tenant, key="09c_a11y_judge", semver="1.0.0", prompt_version="p1",
        body_ref="agents/09c_a11y_judge.md", recommended_engine="claude",
    )
    return {
        "tenant": tenant, "project": project, "user": user,
        "work_item": work_item, "spec": spec,
    }


def _run(world, *, status=Run.Status.RUNNING, workflow_id="wf-1", age_minutes=60, inputs=None):
    run = Run.objects.create(
        tenant=world["tenant"], work_item=world["work_item"], agent_spec=world["spec"],
        status=status, temporal_workflow_id=workflow_id, inputs=inputs or {},
    )
    # updated_at is auto_now, so the only way to age a row is to write it directly.
    Run.objects.filter(id=run.id).update(
        updated_at=timezone.now() - timezone.timedelta(minutes=age_minutes)
    )
    run.refresh_from_db()
    return run


def _closed(name="COMPLETED"):
    return lambda _wf: WorkflowState(True, name)


def _still_running(_wf):
    return WorkflowState(False, "RUNNING")


def _unreachable(_wf):
    return None


def _tid(world):
    return str(world["tenant"].id)


# ── the generic invariant ───────────────────────────────────────────


def test_a_run_left_running_by_a_closed_workflow_is_repaired(world):
    run = _run(world)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    run.refresh_from_db()
    assert run.status == Run.Status.FAILED
    assert out["repaired"] and out["repaired"][0]["id"] == str(run.id)


def test_the_repair_says_what_happened_in_words_a_person_can_use(world):
    """The run console shows this text. A status change nobody can interpret is
    only half a repair."""
    run = _run(world)

    reconcile_tenant(tenant_id=_tid(world), describe=_closed("TERMINATED"))

    run.refresh_from_db()
    error = (run.outputs or {}).get("error", "")
    assert "TERMINATED" in error
    assert "Re-trigger" in error


def test_the_repair_leaves_a_trail(world):
    run = _run(world)

    reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    events = Event.objects.filter(
        tenant_id=_tid(world), action="run.reconciled", target_id=str(run.id)
    )
    assert events.count() == 1
    assert events.first().payload["workflow_status"] == "COMPLETED"


def test_a_workflow_temporal_has_forgotten_is_still_a_dead_end(world):
    run = _run(world)

    reconcile_tenant(tenant_id=_tid(world), describe=_closed("NOT_FOUND"))

    run.refresh_from_db()
    assert run.status == Run.Status.FAILED
    assert "no longer exists" in (run.outputs or {}).get("error", "")


# ── restraint: the cases that must NOT be touched ───────────────────


def test_a_run_that_is_genuinely_still_going_is_left_alone(world):
    run = _run(world)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_still_running)

    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    assert out["repaired"] == []


def test_a_run_that_just_started_is_left_alone(world):
    """A run is written to several times as it starts and its workflow is not
    instantly describable — without the age guard this would race normal startup."""
    run = _run(world, age_minutes=0)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    assert out["checked"] == 0


def test_a_temporal_outage_repairs_nothing(world):
    """The failure mode that would make this net worse than useless: closing
    healthy runs every time Temporal is briefly unreachable."""
    run = _run(world)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_unreachable)

    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    assert out["undetermined"] == 1
    assert out["repaired"] == []


def test_a_run_with_no_workflow_behind_it_is_not_our_business(world):
    run = _run(world, workflow_id="")

    out = reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    run.refresh_from_db()
    assert run.status == Run.Status.RUNNING
    assert out["checked"] == 0


def test_a_parked_run_is_left_for_its_human(world):
    """STALLED is non-terminal on purpose: a companion that only slept can still
    come back and reconcile itself. Repairing it here would take that away."""
    run = _run(world, status=Run.Status.STALLED)

    reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    run.refresh_from_db()
    assert run.status == Run.Status.STALLED


def test_a_finished_run_is_not_reopened(world):
    run = _run(world, status=Run.Status.COMPLETED)

    reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    run.refresh_from_db()
    assert run.status == Run.Status.COMPLETED


def test_it_never_examines_more_than_its_cap(world):
    """This rides a page load; an unbounded sweep would be a new problem."""
    for i in range(8):
        _run(world, workflow_id=f"wf-{i}")

    out = reconcile_tenant(tenant_id=_tid(world), describe=_still_running, limit=3)

    assert out["checked"] == 3


def test_one_tenant_never_repairs_another_tenants_run(db, world):
    other = Tenant.objects.create(name="Globex")
    other_project = Project.objects.create(tenant=other, name="Other")
    other_item = WorkItem.objects.create(tenant=other, project=other_project, title="X")
    other_spec = AgentSpec.objects.create(
        tenant=other, key="09c_a11y_judge", semver="1.0.0", prompt_version="p1",
        body_ref="agents/09c_a11y_judge.md", recommended_engine="claude",
    )
    stranded = Run.objects.create(
        tenant=other, work_item=other_item, agent_spec=other_spec,
        status=Run.Status.RUNNING, temporal_workflow_id="wf-other",
    )
    Run.objects.filter(id=stranded.id).update(
        updated_at=timezone.now() - timezone.timedelta(hours=2)
    )

    reconcile_tenant(tenant_id=_tid(world), describe=_closed())

    stranded.refresh_from_db()
    assert stranded.status == Run.Status.RUNNING


def test_a_fault_inside_the_reconciler_cannot_break_the_page_it_rides_on(world):
    _run(world)

    def _explode(_wf):
        raise RuntimeError("temporal client blew up")

    out = reconcile_tenant(tenant_id=_tid(world), describe=_explode)

    assert "error" in out or out["undetermined"] >= 0  # returned, did not raise


# ── the capability check: the failure that actually happened ────────


def _stranded_audit(world):
    """An audit judged in full whose closing step never ran — the real incident."""
    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"],
        status=A11yBaselineAudit.Status.JUDGING, routes=["/"],
    )
    judge = _run(
        world, status=Run.Status.COMPLETED, workflow_id="wf-judge",
        inputs={SOURCE_RUN_KEY: str(audit.id)},
    )
    audit.summary = {"ai_pass": {"judge_run_id": str(judge.id)}}
    audit.save(update_fields=["summary"])
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        updated_at=timezone.now() - timezone.timedelta(hours=2)
    )
    return audit, judge


def test_an_audit_stuck_behind_a_finished_judging_run_is_closed(world):
    """The generic run check cannot see this one: the run's status was
    `completed` and its workflow had closed. Nothing about the RUN was wrong."""
    audit, _judge = _stranded_audit(world)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_still_running)

    audit.refresh_from_db()
    assert audit.status != A11yBaselineAudit.Status.JUDGING
    assert any(r["kind"] == "a11y_audit" for r in out["repaired"])


def test_an_audit_still_being_judged_is_left_alone(world):
    audit, judge = _stranded_audit(world)
    Run.objects.filter(id=judge.id).update(status=Run.Status.RUNNING)

    reconcile_tenant(tenant_id=_tid(world), describe=_still_running)

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.JUDGING


def test_an_audit_whose_judging_never_started_is_left_alone(world):
    """No judging run recorded is a different problem; closing the audit here
    would report on a check that never ran."""
    audit = A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"],
        status=A11yBaselineAudit.Status.JUDGING, routes=["/"],
    )
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        updated_at=timezone.now() - timezone.timedelta(hours=2)
    )

    reconcile_tenant(tenant_id=_tid(world), describe=_still_running)

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.JUDGING


# ── the seam it hangs off ───────────────────────────────────────────


def test_listing_runs_triggers_the_check(world, monkeypatch):
    from rest_framework.test import APIClient

    called: list = []
    import apps.runs.reconcile as reconcile_mod

    def _spy(**kwargs):
        called.append(kwargs)
        return {"checked": 0, "repaired": [], "undetermined": 0}

    monkeypatch.setattr(reconcile_mod, "reconcile_tenant", _spy)

    client = APIClient()
    assert client.post(
        "/api/auth/login/", {"email": "qa@acme.com", "password": PASSWORD}, format="json"
    ).status_code == 200
    resp = client.get("/api/runs/", HTTP_X_TENANT_ID=_tid(world))

    assert resp.status_code == 200
    assert called and called[0]["tenant_id"] == _tid(world)


# ── S.No 246: a RUNNING workflow nobody is serving ──────────────────
#
# The failure that hid for 46 days. Temporal pins a workflow to the code version that started
# it, for life, and says nothing when no worker carries that version any more. So the workflow
# reports RUNNING, the worker reports healthy, the queue reports healthy, and the screen shows
# an ordinary waiting state — while the task is dead. Every test here is about TELLING somebody:
# nothing below repairs anything, because which recovery is right (take over, merge the
# versions, re-trigger) has different consequences each way and is a person's call.


def _pinned(build, *, versioned=True, name="RUNNING"):
    return lambda _wf: WorkflowState(False, name, build_id=build, versioned=versioned)


def _serving(*builds, sets=1):
    return lambda _queue: (frozenset(builds), sets)


def _stall(run):
    run.refresh_from_db()
    return (run.outputs or {}).get("worker_stalled")


def test_a_run_whose_code_version_nobody_serves_is_reported(world, monkeypatch):
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world, status=Run.Status.AWAITING_GATE)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))

    note = _stall(run)
    assert note and note["pinned_build"] == "v-old" and note["newest_served"] == "v-new"
    assert out["stalled"] == [str(run.id)]
    # Reported, NOT repaired — the run keeps the status it had.
    assert run.status == Run.Status.AWAITING_GATE
    assert out["repaired"] == []
    assert Event.objects.filter(tenant=world["tenant"], action="run.worker_stalled").count() == 1


def test_the_report_disappears_by_itself_once_somebody_serves_it_again(world, monkeypatch):
    """The team's rule: a notice must close itself when the thing it describes is over.

    This is the merge-the-versions recovery, seen from the run's side — the code version comes
    back into service and the screen must stop saying anything, with nobody dismissing it.
    """
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world)
    reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))
    assert _stall(run)

    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-old", "v-new"))
    out = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))

    assert _stall(run) is None
    assert out["recovered"] == [str(run.id)]
    assert Event.objects.filter(tenant=world["tenant"], action="run.worker_recovered").count() == 1


def test_looking_twice_at_the_same_stall_says_it_once(world, monkeypatch):
    """This rides on a page load. A run that is still stuck must not write a fresh ledger event
    every time somebody opens the screen."""
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world)

    first = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))
    second = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))

    assert first["stalled"] == [str(run.id)]
    assert second["stalled"] == []          # nothing changed, so nothing was said
    assert Event.objects.filter(tenant=world["tenant"], action="run.worker_stalled").count() == 1


def test_an_unversioned_workflow_is_never_reported(world, monkeypatch):
    """An unversioned workflow belongs to no version set, so its stamp is a bare code
    fingerprint that means nothing here. Reading it as a mismatch would flag every run that
    predates worker versioning — ten of the twelve found on 2026-09-08."""
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world)

    reconcile_tenant(
        tenant_id=_tid(world), describe=_pinned("bare-fingerprint", versioned=False)
    )

    assert _stall(run) is None


def test_a_temporal_outage_reports_nothing(world, monkeypatch):
    """"Could not tell" is never "gone" — the same rule that stops the Jira pointer check
    wiping every pointer in a project during an auth outage (S.No 236). Without this, one
    unreachable moment would mark every run the tenant has."""
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", lambda _q: None)
    run = _run(world)

    reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))

    assert _stall(run) is None


def test_a_parked_run_is_reported_but_still_never_repaired(world, monkeypatch):
    """TASK-039's exact shape: parked AND orphaned, indistinguishable from a companion that
    merely went quiet. Watching it is how somebody finds out; repairing it would undo S.No 89,
    which is why detection looks wider than repair rather than `LIVE_STATUSES` being widened.
    """
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world, status=Run.Status.STALLED)

    out = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))

    assert _stall(run)
    run.refresh_from_db()
    assert run.status == Run.Status.STALLED
    assert out["repaired"] == []


def test_an_outage_never_ERASES_a_report_either(world, monkeypatch):
    """The other half of "could not tell is never gone", and the one that was missing.

    Found in a browser: `_stall_note` returns None both for "this run is fine" and for "no
    idea", and `_remember_stall` reads None as "take the note off". So a queue that answered
    with nothing — briefly unreachable, or simply no versions registered — wiped a live warning
    about a genuinely dead task, and the screen went quiet with nothing fixed.
    """
    monkeypatch.setattr("apps.runs.reconcile._queue_versions", _serving("v-new"))
    run = _run(world)
    reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))
    assert _stall(run)

    for blind in (lambda _q: None, lambda _q: (frozenset(), 0)):
        monkeypatch.setattr("apps.runs.reconcile._queue_versions", blind)
        out = reconcile_tenant(tenant_id=_tid(world), describe=_pinned("v-old"))
        assert _stall(run), "a blind pass erased a real warning"
        assert out["recovered"] == [] and out["stalled"] == []
        assert out["undetermined"] == 1
