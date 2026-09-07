"""Bugs S.No 140 — a human way to close work that cannot be built.

Three groups, and the middle one is the reason this file exists:

1. **The endpoint** — who may call it, which moves are legal, and that cancelling without a
   reason is refused.
2. **Nothing automated un-cancels an item.** `cancelled` is only worth having if it sticks.
   Every one of these targets a specific place that forces a state without asking what the
   item's current state is; before this wave each of them would have silently resurrected a
   cancelled item, and each test is written so that removing its guard fails loudly.
3. **A cancelled defect releases its gate, and says so.** The release without the disclosure
   would let "we won't fix this" quietly become "this passed", so they are tested together.
"""
import pytest
from mcp_platform_state import tools
from rest_framework.test import APIClient

from apps.gates.models import Approval
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.cancel import ACK_CONDITION_PREFIX
from apps.workitems.cancel import transition as human_transition
from apps.workitems.models import WorkItem


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payments")


@pytest.fixture
def lead(tenant, project):
    u = User.objects.create_user(email="lead@acme.test", name="Lee", tenant=tenant,
                                 password="lead-pass!")
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


@pytest.fixture
def engineer(tenant, project):
    u = User.objects.create_user(email="eng@acme.test", name="Eng", tenant=tenant,
                                 password="eng-pass!")
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    return u


def _item(project, state=WorkItem.State.IN_PROGRESS, type_=WorkItem.Type.TASK, parent=None):
    return WorkItem.objects.create(tenant=project.tenant, project=project, type=type_,
                                   title="A task", state=state, parent=parent)


def _login(client, email, password):
    assert client.post("/api/auth/login/", {"email": email, "password": password},
                       format="json").status_code == 200


def _hdr(project):
    return {"HTTP_X_TENANT_ID": str(project.tenant_id)}


def _post(client, project, item, **body):
    return client.post(f"/api/work-items/{item.id}/transition/", body, format="json",
                       **_hdr(project))


# ── 1. the endpoint ─────────────────────────────────────────────────
def test_a_tech_lead_can_cancel_with_a_reason(client, project, lead):
    item = _item(project)
    _login(client, "lead@acme.test", "lead-pass!")

    resp = _post(client, project, item, to_state="cancelled", reason="Duplicate of WI-12")

    assert resp.status_code == 200, resp.content
    item.refresh_from_db()
    assert item.state == WorkItem.State.CANCELLED
    # The decision, and the person who made it, are in the ledger — six months from now this
    # is the only place "why is WI-42 cancelled" can be answered.
    event = Event.objects.get(tenant_id=project.tenant_id, action="workitem.transitioned",
                              target_id=str(item.id))
    assert event.payload["reason"] == "Duplicate of WI-12"
    assert event.payload["from_state"] == "in_progress"
    assert event.actor == str(lead.id)


def test_an_engineer_cannot_cancel(client, project, engineer):
    """Team decision: tech_lead or admin. Cancelling takes work off the board and can release
    a gate — it is not an everyday edit."""
    item = _item(project)
    _login(client, "eng@acme.test", "eng-pass!")

    resp = _post(client, project, item, to_state="cancelled", reason="nope")

    assert resp.status_code == 403
    item.refresh_from_db()
    assert item.state == WorkItem.State.IN_PROGRESS


def test_signed_out_callers_are_refused(client, project, lead):
    """S.No 214's lesson: an action missing from `get_permissions` inherits the project-wide
    AllowAny default. Without the registration this returns 200 to a total stranger."""
    item = _item(project)

    resp = _post(client, project, item, to_state="cancelled", reason="anyone?")

    assert resp.status_code in (401, 403), resp.content
    item.refresh_from_db()
    assert item.state == WorkItem.State.IN_PROGRESS


def test_cancelling_without_a_reason_is_refused(client, project, lead):
    item = _item(project)
    _login(client, "lead@acme.test", "lead-pass!")

    resp = _post(client, project, item, to_state="cancelled", reason="   ")

    assert resp.status_code == 400
    assert "reason" in resp.data
    item.refresh_from_db()
    assert item.state == WorkItem.State.IN_PROGRESS


def test_marking_done_needs_no_reason(client, project, lead):
    item = _item(project, WorkItem.State.IN_REVIEW)
    _login(client, "lead@acme.test", "lead-pass!")

    assert _post(client, project, item, to_state="done").status_code == 200
    item.refresh_from_db()
    assert item.state == WorkItem.State.DONE


@pytest.mark.parametrize("from_state,to_state", [
    # Nothing leaves a terminal state through this endpoint. Reopening finished or abandoned
    # work restarts gates and reporting; that is a separate decision, not this one.
    (WorkItem.State.CANCELLED, WorkItem.State.IN_PROGRESS),
    (WorkItem.State.CANCELLED, WorkItem.State.DONE),
    (WorkItem.State.DONE, WorkItem.State.IN_PROGRESS),
    # An item nobody has started is not something anybody can attest is finished — that is
    # what `cancelled` is for.
    (WorkItem.State.PROPOSED, WorkItem.State.DONE),
])
def test_the_allowlist_refuses_everything_else(client, project, lead, from_state, to_state):
    item = _item(project, from_state)
    _login(client, "lead@acme.test", "lead-pass!")

    resp = _post(client, project, item, to_state=to_state, reason="because")

    assert resp.status_code == 400, resp.content
    # The refusal says what IS possible from here, so a person is not left guessing.
    assert "From here you can move it to" in str(resp.data)
    item.refresh_from_db()
    assert item.state == from_state


# ── 2. nothing automated un-cancels an item ─────────────────────────
def test_the_state_tool_skips_a_cancelled_item(project):
    """The choke point. `tools.transition_work_item` is what the merged-PR webhook, a rejected
    gate and a failed build all call, and every one of them forces a state without reading the
    item's current one. Skipped rather than raised: these run inside Temporal activities, and
    failing a workflow over a state change it did not care about is the worse outcome."""
    item = _item(project, WorkItem.State.CANCELLED)

    out = tools.transition_work_item(str(project.tenant_id), str(item.id),
                                     WorkItem.State.DONE)

    item.refresh_from_db()
    assert item.state == WorkItem.State.CANCELLED, "an automated path un-cancelled the item"
    assert out["state"] == WorkItem.State.CANCELLED   # the caller can tell nothing moved
    assert Event.objects.filter(tenant_id=project.tenant_id,
                                action="workitem.transition_skipped",
                                target_id=str(item.id)).exists()


def test_a_live_item_still_transitions_normally(project):
    """The guard is scoped to cancelled items. If this fails, the fix above broke every build."""
    item = _item(project, WorkItem.State.IN_PROGRESS)
    tools.transition_work_item(str(project.tenant_id), str(item.id), WorkItem.State.DONE)
    item.refresh_from_db()
    assert item.state == WorkItem.State.DONE


def test_the_test_defect_loop_does_not_close_a_cancelled_defect(project):
    """`import_test_results` closes a defect when its test passes. A cancelled defect is not an
    open defect waiting to be closed — flipping it to `done` would rewrite "we decided not to
    fix this" as "fixed", and the delivery report would then count it as delivered work."""
    from apps.quality.services import _reconcile_defects

    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="Failing test t1", state=WorkItem.State.CANCELLED,
        external_ref={"test_ref": "t1"},
    )

    _reconcile_defects(str(project.tenant_id), str(project.id), str(story.id),
                       failing=set(), passing={"t1"}, report_id="r1")

    defect.refresh_from_db()
    assert defect.state == WorkItem.State.CANCELLED


def test_the_a11y_defect_loop_does_not_close_a_cancelled_defect(project):
    """Same shape in the accessibility reconciliation: "no longer blocking" would close a
    cancelled ticket as *resolved*, which is a different statement about the same defect than
    the one the person who cancelled it made."""
    from apps.a11y import defects as a11y_defects

    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="Contrast on /pricing", state=WorkItem.State.CANCELLED,
        external_ref={"a11y_finding": "fp1"},
    )

    # No open findings at all, so every existing a11y defect is "no longer blocking" —
    # the close loop is exactly what this exercises.
    a11y_defects.record_a11y_findings(tenant_id=str(project.tenant_id),
                                      project_id=str(project.id))

    defect.refresh_from_db()
    assert defect.state == WorkItem.State.CANCELLED


# ── 3. releasing a gate, and saying so ──────────────────────────────
def _pending_gate(project, story):
    from apps.registry.models import AgentSpec

    spec, _ = AgentSpec.objects.get_or_create(
        tenant=project.tenant, key="09_testing",
        defaults={"body_ref": "agents/09_testing", "phase_label": "Testing"},
    )
    run = Run.objects.create(tenant=project.tenant, work_item=story, agent_spec=spec,
                             status=Run.Status.AWAITING_GATE)
    return Approval.objects.create(
        tenant=project.tenant, run=run, work_item=story, required_role="tech_lead",
        decision=Approval.Decision.PENDING, conditions=[],
    )


def test_cancelling_a_blocking_defect_releases_the_gate(project):
    """The team's decision. The test gate blocks on open test defects; a defect nobody will
    ever fix must not hold a story shut for ever."""
    from apps.gates.testgate import open_test_defect_refs

    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="Flaky login test", state=WorkItem.State.IN_PROGRESS,
        external_ref={"test_ref": "t1"},
    )
    assert open_test_defect_refs(tenant_id=str(project.tenant_id),
                                 work_item_id=str(story.id)) == ["t1"]

    human_transition(tenant_id=str(project.tenant_id), work_item_id=str(defect.id),
                     to_state=WorkItem.State.CANCELLED, reason="Test removed in v3")

    assert open_test_defect_refs(tenant_id=str(project.tenant_id),
                                 work_item_id=str(story.id)) == []


def test_the_release_is_disclosed_on_the_pending_gate(project, lead):
    """...and this is what makes that safe. The reviewer has to read what was cancelled, and
    why, and tick it — otherwise the gate opens with nobody having been told."""
    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    approval = _pending_gate(project, story)
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="Flaky login test", state=WorkItem.State.IN_PROGRESS,
        external_ref={"test_ref": "t1"},
    )

    out = human_transition(tenant_id=str(project.tenant_id), work_item_id=str(defect.id),
                           to_state=WorkItem.State.CANCELLED, reason="Test removed in v3",
                           actor_id=str(lead.id))

    assert out["gates_notified"] == [str(approval.id)]
    approval.refresh_from_db()
    condition = next(c for c in approval.conditions
                     if str(c["key"]).startswith(ACK_CONDITION_PREFIX))
    assert condition["required"] is True
    assert condition["satisfied"] is False            # it BLOCKS until a person ticks it
    assert not condition.get("derived")               # ...and a person is allowed to tick it
    assert "Test removed in v3" in condition["label"]
    assert "Lee" in condition["label"]                # who made the call, by name


def test_the_disclosure_is_written_once(project, lead):
    """Cancelling is one fact however many times it is applied — a duplicate condition would
    ask the reviewer to acknowledge the same defect twice."""
    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    approval = _pending_gate(project, story)
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="D", state=WorkItem.State.IN_PROGRESS, external_ref={"test_ref": "t1"},
    )
    for _ in range(2):
        try:
            human_transition(tenant_id=str(project.tenant_id), work_item_id=str(defect.id),
                             to_state=WorkItem.State.CANCELLED, reason="r",
                             actor_id=str(lead.id))
        except Exception:                              # the second is refused by the allowlist
            pass

    approval.refresh_from_db()
    keys = [c["key"] for c in approval.conditions
            if str(c["key"]).startswith(ACK_CONDITION_PREFIX)]
    assert len(keys) == 1


def test_an_already_decided_gate_is_left_alone(project, lead):
    """Its checklist is the record of what that approver actually saw. Rewriting it after the
    decision would misrepresent the decision."""
    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    approval = _pending_gate(project, story)
    approval.decision = Approval.Decision.APPROVED
    approval.save(update_fields=["decision"])
    defect = WorkItem.objects.create(
        tenant=project.tenant, project=project, type=WorkItem.Type.DEFECT, parent=story,
        title="D", state=WorkItem.State.IN_PROGRESS, external_ref={"test_ref": "t1"},
    )

    out = human_transition(tenant_id=str(project.tenant_id), work_item_id=str(defect.id),
                           to_state=WorkItem.State.CANCELLED, reason="r", actor_id=str(lead.id))

    assert out["gates_notified"] == []
    approval.refresh_from_db()
    assert approval.conditions == []


def test_cancelling_an_ordinary_task_touches_no_gate(project, lead):
    """Only a DEFECT can be holding a gate shut. A cancelled task must not put an
    acknowledgement in front of a reviewer for something that was never blocking them."""
    story = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.STORY)
    approval = _pending_gate(project, story)
    task = _item(project, WorkItem.State.IN_PROGRESS, WorkItem.Type.TASK, parent=story)

    out = human_transition(tenant_id=str(project.tenant_id), work_item_id=str(task.id),
                           to_state=WorkItem.State.CANCELLED, reason="r", actor_id=str(lead.id))

    assert out["gates_notified"] == []
    approval.refresh_from_db()
    assert approval.conditions == []
