"""Pausing a phase run on purpose, and picking it up again.

The crash case (an error parks the run, a human resumes it) has been covered since S.No 157. This
is the *voluntary* case the team asked for: somebody has to stop now and come back later.

The load-bearing test in here is `test_a_paused_run_is_never_handed_to_a_companion`. The companion
is pull-only — it asks us for work and we have no channel to it at all — so withholding the dispatch
from the claim queue is the ONLY control the platform has over a machine it does not own. If that
ever stops working, Pause silently becomes a button that does nothing while the agent carries on.

The second one worth reading before changing anything is
`test_a_paused_run_blocks_a_second_run_of_the_same_phase`. PAUSED exists as its own status, rather
than reusing STALLED, precisely because STALLED is excluded from the re-trigger guard: a pause
recorded as STALLED let the same phase be triggered again, putting two agents on one branch.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration import activities, takeover
from orchestration.takeover import PauseError, ResumeError, pause_run, resume_stalled_run
from orchestration.types import AgentRunInput


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x", phase_label="prd")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec,
                             temporal_workflow_id="wf-pause")
    enrollment, token = enroll_runner(tenant_id=str(t.id), project_id=str(project.id), label="l")
    inp = AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
        required_role="product_owner", execution_mode="companion",
        enrollment_id=str(enrollment.id),
    )
    return {"inp": inp, "tenant_id": str(t.id), "project_id": str(project.id),
            "run_id": str(run.id), "work_item_id": str(wi.id), "spec": spec,
            "enrollment_id": str(enrollment.id), "token": token, "tenant": t,
            "project": project}


def _auth(world):
    return {"HTTP_AUTHORIZATION": f"Runner {world['token']}",
            "HTTP_X_TENANT_ID": world["tenant_id"]}


def _sent(calls):
    """A signal_sender seam that records instead of reaching a real Temporal server."""
    def sender(workflow_id, *args):
        calls.append((workflow_id, args))
    return sender


# ── the state a pause writes ────────────────────────────────────────
def test_pause_marks_the_run_paused_and_holds_the_dispatch_back(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    calls: list = []

    out = pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                    paused_by="Priya", signal_sender=_sent(calls))

    assert out["paused"] is True
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.PAUSED
    assert run.inputs["dispatch"]["status"] == "paused"
    assert run.outputs["paused"]["by"] == "Priya"
    assert run.outputs["resumable"] is True
    # The workflow is told as well, so it stops at its next checkpoint instead of opening the gate.
    assert calls == [("wf-pause", ("Priya",))]


def test_a_pause_records_no_error(world):
    """Nothing went wrong, so nothing may be written to the field the console reads for a failure.

    A paused run that printed an error would be telling the reader their own decision was a fault."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
              signal_sender=_sent([]))
    outputs = Run.objects.get(id=world["run_id"]).outputs
    assert "error" not in outputs and "error_detail" not in outputs


def test_pause_reports_whether_the_companion_had_already_started(world):
    """`was_claimed` is what lets the dialog tell the truth about timing instead of guessing."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    not_started = pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                            signal_sender=_sent([]))
    assert not_started["was_claimed"] is False


def test_pause_knows_when_the_companion_is_already_working(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    assert APIClient().get("/api/runner/work/", **_auth(world)).status_code == 200
    working = pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                        signal_sender=_sent([]))
    assert working["was_claimed"] is True


# ── the lever: a pull-only companion ────────────────────────────────
def test_a_paused_run_is_never_handed_to_a_companion(world):
    """THE test. We cannot tell the companion to stop — so we stop giving it the work.

    If this fails, Pause is a button that changes a status and nothing else: the companion polls
    five seconds later, claims the run and the agent starts anyway."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))

    assert APIClient().get("/api/runner/work/", **_auth(world)).status_code == 204


def test_the_same_work_is_on_offer_when_it_is_not_paused(world):
    """The control for the test above — without it, a 204 for any other reason would read as a pass
    and Pause would look like it worked while doing nothing."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    assert APIClient().get("/api/runner/work/", **_auth(world)).status_code == 200


def test_resume_puts_the_run_back_in_the_claim_queue(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))
    client = APIClient()
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 204

    calls: list = []
    out = resume_stalled_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                            signal_sender=lambda wf: calls.append(wf))
    assert out["resumed"] is True and calls == ["wf-pause"]

    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.RUNNING
    assert run.inputs["dispatch"]["status"] == "pending"
    assert "paused" not in run.outputs
    # And the companion can have it again.
    assert client.get("/api/runner/work/", **_auth(world)).status_code == 200


def test_resume_clears_the_stale_claim_stamp(world):
    """A leftover `claimed_at` would make the lease-reclaim branch think a companion had taken this
    run and died, which is a different recovery with different wording."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    APIClient().get("/api/runner/work/", **_auth(world))     # claim it, stamping claimed_at
    assert Run.objects.get(id=world["run_id"]).inputs["dispatch"].get("claimed_at")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))
    resume_stalled_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                       signal_sender=lambda wf: None)
    assert "claimed_at" not in Run.objects.get(id=world["run_id"]).inputs["dispatch"]


# ── what may and may not be paused ──────────────────────────────────
def test_pause_is_idempotent(world):
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))
    calls: list = []
    again = pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                      signal_sender=_sent(calls))
    # Agreement, not an error — and no second signal.
    assert again["paused"] is True and again["already"] is True
    assert calls == []


def test_a_run_waiting_at_a_gate_cannot_be_paused(world):
    """It is already stopped and costs nothing. Offering to pause it would be offering to stop
    something that is not running."""
    Run.objects.filter(id=world["run_id"]).update(status=Run.Status.AWAITING_GATE)
    with pytest.raises(PauseError) as exc:
        pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))
    said = str(exc.value)
    assert "nothing to pause" in said
    # The reader's words, not the stored status.
    assert "awaiting_gate" not in said and "waiting for approval" in said.lower()


def test_a_finished_run_cannot_be_paused(world):
    Run.objects.filter(id=world["run_id"]).update(status=Run.Status.COMPLETED)
    with pytest.raises(PauseError):
        pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))


def test_a_run_that_finished_mid_pause_is_not_left_looking_paused(world):
    """The companion's report can land between our read and our signal. Undo the hold rather than
    leave a completed run showing as paused with its dispatch held back."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")

    def gone(workflow_id, *args):
        raise RuntimeError("workflow execution already completed")

    with pytest.raises(PauseError) as exc:
        pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=gone)
    assert "finished just now" in str(exc.value)
    run = Run.objects.get(id=world["run_id"])
    assert run.status != Run.Status.PAUSED
    assert run.inputs["dispatch"]["status"] != "paused"


def test_a_pause_survives_temporal_being_unreachable(world):
    """FOUND IN A BROWSER, not in a test. The hold on the dispatch is written first and the workflow
    signalled second; when the signal failed for any reason other than the workflow being gone, the
    exception propagated and the endpoint returned a 500 reading "nothing was saved" — while the run
    sat paused on the screen behind the dialog.

    The hold is the half that actually stops work, because the companion pulls and a paused dispatch
    is never offered to it. Losing the signal costs only the checkpoint stop, which is worth
    recording, not worth refusing the pause over."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")

    def unreachable(workflow_id, *args):
        raise RuntimeError("tonic::transport::Error: error trying to connect")

    out = pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                    signal_sender=unreachable)

    assert out["paused"] is True
    assert out["workflow_notified"] is False       # said plainly, not hidden
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.PAUSED
    # And the lever still works: the companion is not given the run.
    assert APIClient().get("/api/runner/work/", **_auth(world)).status_code == 204


def test_the_failed_signal_never_prints_machinery_on_the_console(world):
    """Also found in the browser. The first fix logged the transport error under `detail`, and
    `EventSerializer.get_message` prints that key straight onto the run console — so the reader got
    a Rust stack dump ("tonic::transport::Error(Transport, ConnectError...)") on their screen.

    Standing rule: no machine words on a client's screen. The raw text goes to the server log our
    team reads; the reader gets a sentence about what it means for them."""
    from api.serializers import EventSerializer
    from apps.ledger.models import Event

    activities.dispatch_phase_core(world["inp"], manifest="# Project")

    def unreachable(workflow_id, *args):
        raise RuntimeError("tonic::transport::Error(Transport, ConnectError(\"tcp connect\"))")

    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=unreachable)

    event = Event.objects.filter(tenant_id=world["tenant_id"],
                                 action="run.pause_signal_failed").first()
    assert event is not None
    said = EventSerializer(event).data["message"]
    assert "tonic" not in said and "ConnectError" not in said and "transport" not in said
    # And it says the thing that is actually true and useful.
    assert "won't be given new work" in said


def test_a_resume_survives_temporal_being_unreachable(world):
    """The resume half of the same browser finding. A PAUSED run is released synchronously before
    the signal, so a lost signal must not fail the request."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))

    def unreachable(workflow_id, *args):
        raise RuntimeError("tonic::transport::Error: error trying to connect")

    out = resume_stalled_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                             signal_sender=unreachable)
    assert out["resumed"] is True and out["workflow_notified"] is False
    run = Run.objects.get(id=world["run_id"])
    assert run.status == Run.Status.RUNNING
    assert APIClient().get("/api/runner/work/", **_auth(world)).status_code == 200


def test_an_error_parked_run_still_refuses_a_resume_it_could_not_deliver(world):
    """The deliberate asymmetry. An error park un-parks INSIDE the workflow, so a signal that never
    lands means nothing happened — telling the user it resumed would be false. Pinned because the
    paused-run tolerance above sits three lines away and is easy to widen by accident."""
    Run.objects.filter(id=world["run_id"]).update(
        status=Run.Status.STALLED,
        outputs={"error": "engine exited", "resumable": True, "resume_from": "dispatch_phase"})

    def gone(workflow_id, *args):
        raise RuntimeError("workflow execution already completed")

    with pytest.raises(ResumeError):
        resume_stalled_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                           signal_sender=gone)


# ── the duplicate-run guard (why PAUSED is its own status) ───────────
def test_a_paused_run_blocks_a_second_run_of_the_same_phase(world, monkeypatch):
    """A pause recorded as STALLED would have allowed this, because STALLED is deliberately
    excluded from the active-run guard — two agents, one branch, no warning."""
    from orchestration import trigger

    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))

    with pytest.raises(trigger.ActiveRunError) as exc:
        trigger._guard_no_active_run(world["tenant_id"], world["work_item_id"])
    said = str(exc.value)
    assert "paused" in said.lower() and "resume" in said.lower()
    # Not the generic sentence: nobody waits for a run that is not running.
    assert "Wait for it to finish" not in said


def test_a_parked_run_still_allows_a_retrigger(world):
    """The other half of the same rule, pinned so the PAUSED change did not quietly take the
    STALLED recourse away: a run parked by an error or an offline machine is a valid thing to
    start again."""
    from orchestration import trigger

    Run.objects.filter(id=world["run_id"]).update(status=Run.Status.STALLED)
    trigger._guard_no_active_run(world["tenant_id"], world["work_item_id"])     # no raise


# ── discarding a paused run ─────────────────────────────────────────
def test_a_paused_run_can_be_discarded(world):
    """Pause blocks a re-trigger, so there has to be a way out other than resuming — otherwise
    somebody who changes their mind is stuck until their companion is back."""
    activities.dispatch_phase_core(world["inp"], manifest="# Project\nm")
    pause_run(tenant_id=world["tenant_id"], run_id=world["run_id"], signal_sender=_sent([]))
    calls: list = []
    out = takeover.abandon_stalled_run(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                       signal_sender=lambda wf: calls.append(wf))
    assert out["abandoned"] is True and calls == ["wf-pause"]


# ── the endpoint ────────────────────────────────────────────────────
def test_pause_endpoint_requires_membership(world, monkeypatch):
    """Parity with resume (S.No 214): both reach into a run somebody else may have started."""
    from api.views import RunViewSet
    from apps.tenancy.auth import IsAuthenticatedMember

    view = RunViewSet()
    view.action = "pause"
    assert any(isinstance(p, IsAuthenticatedMember) for p in view.get_permissions())
