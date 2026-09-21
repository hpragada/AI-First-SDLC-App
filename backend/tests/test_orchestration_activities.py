"""P0-T8 — activity-core tests (spec §5).

Each core is exercised against the real DB with a fake driver + in-memory object store,
covering the happy path, idempotency by run_id, and the approve/reject branches.
"""
import dataclasses
from types import SimpleNamespace

import pytest

from apps.gates.models import Approval
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from drivers import RunResult
from orchestration import activities
from orchestration.types import AgentRunInput
from storage import InMemoryObjectStore


class _FakeDriver:
    def __init__(self, body="# PRD\nThe PRD body.", cost=0.0731):
        self.body = body
        self.cost = cost

    async def run_planning_task(
        self, *, manifest, agent_spec, mcp_servers, allowed_tools, work_item
    ):
        assert "# Project" in manifest  # got the composed manifest
        return RunResult(
            outputs={"result": self.body, "text": self.body},
            artifacts=[], cost_usd=self.cost, raw_messages=[],
        )


@pytest.fixture
def store():
    return InMemoryObjectStore()


@pytest.fixture
def wired(monkeypatch, store):
    monkeypatch.setattr(activities, "get_driver", lambda: _FakeDriver())
    monkeypatch.setattr(activities, "get_object_store", lambda: store)
    return store


@pytest.fixture
def run_input(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=project, important_context="ctx")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x", phase_label="prd")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase="prd",
        required_role="product_owner",
    )


def test_compose_manifest_core(run_input):
    md = activities.compose_manifest_core(run_input)
    assert "# Project" in md and "# Current Work Item" in md and "- phase: prd" in md


def test_execute_agent_core_drafts_and_registers(wired, store, run_input):
    out = activities.execute_agent_core(run_input, manifest="# Project\nx")
    assert out["cost_usd"] == 0.0731

    artifact = Artifact.objects.get(id=out["artifact_ids"][0])
    assert artifact.status == Artifact.Status.DRAFT  # not published yet (#5)
    assert artifact.sor == Artifact.SoR.INTERNAL
    assert artifact.content_hash.startswith("sha256:")
    # Body is in the object store, only the pointer is in the registry (#1/#3).
    assert store.get(artifact.s3_key) == b"# PRD\nThe PRD body."

    run = Run.objects.get(id=run_input.run_id)
    assert run.status == Run.Status.AWAITING_GATE
    assert float(run.cost_usd) == 0.0731


def test_execute_agent_core_is_idempotent(wired, run_input):
    first = activities.execute_agent_core(run_input, manifest="# Project\nx")
    second = activities.execute_agent_core(run_input, manifest="# Project\nx")
    assert second.get("idempotent") is True
    assert second["artifact_ids"] == first["artifact_ids"]
    assert Artifact.objects.filter(run_id=run_input.run_id).count() == 1  # no duplicate


def test_execute_agent_core_marks_run_failed_on_engine_error(monkeypatch, run_input):
    class BrokenDriver:
        async def run_planning_task(self, **kwargs):
            raise RuntimeError("Claude Code not found")

    monkeypatch.setattr(activities, "get_driver", lambda: BrokenDriver())

    with pytest.raises(RuntimeError, match="Claude Code not found"):
        activities.execute_agent_core(run_input, manifest="# Project\nx")

    run = Run.objects.get(id=run_input.run_id)
    assert run.status == Run.Status.FAILED
    # The run console stores a plain-language, classified reason (Bugs S.No 146, planning path),
    # not the raw engine string. The raised exception itself is unchanged (asserted above).
    assert "couldn't start" in run.outputs["error"]
    # The raw engine text is kept beside the sentence, for "Technical details" (2026-09-21).
    assert "Claude Code not found" in run.outputs["error_detail"]


def test_open_gate_core_creates_pending_and_is_idempotent(wired, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    approval_id = activities.open_gate_core(run_input)
    again = activities.open_gate_core(run_input)
    assert approval_id == again
    approval = Approval.objects.get(id=approval_id)
    assert approval.decision == Approval.Decision.PENDING
    assert approval.required_role == "product_owner"
    assert Approval.objects.filter(run_id=run_input.run_id).count() == 1


# ── Bugs S.No 218: a document at an open gate is waiting on a person, not a draft ──────────
def _extra_artifact(run_input, status):
    return Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id,
        run_id=run_input.run_id, phase="prd", type=f"note-{status}", sor="internal",
        status=status, version=1,
    )


def test_open_gate_core_marks_the_runs_drafts_as_waiting(wired, run_input):
    """Opening a gate used to leave the run's documents reading "Draft", indistinguishable from
    work nobody had asked anyone to look at. They move to `staged` — shown as "Waiting for
    approval" — the moment a person is being asked to decide on them."""
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    assert set(Artifact.objects.filter(run_id=run_input.run_id)
               .values_list("status", flat=True)) == {Artifact.Status.DRAFT}

    activities.open_gate_core(run_input)

    assert set(Artifact.objects.filter(run_id=run_input.run_id)
               .values_list("status", flat=True)) == {Artifact.Status.STAGED}


def test_open_gate_core_never_moves_a_decided_artifact_backwards(wired, run_input):
    published = _extra_artifact(run_input, Artifact.Status.PUBLISHED)
    approved = _extra_artifact(run_input, Artifact.Status.APPROVED)
    superseded = _extra_artifact(run_input, Artifact.Status.SUPERSEDED)

    activities.open_gate_core(run_input)
    activities.open_gate_core(run_input)          # Temporal retries activities — still harmless

    for art, expected in ((published, Artifact.Status.PUBLISHED),
                          (approved, Artifact.Status.APPROVED),
                          (superseded, Artifact.Status.SUPERSEDED)):
        art.refresh_from_db()
        assert art.status == expected


def test_open_gate_core_only_touches_its_own_run(wired, run_input):
    other_run = Run.objects.create(
        tenant_id=run_input.tenant_id,
        work_item_id=run_input.work_item_id,
        agent_spec_id=run_input.agent_spec_id,
    )
    other = Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id, run=other_run,
        phase="prd", type="prd", sor="internal", status=Artifact.Status.DRAFT, version=1,
    )

    activities.open_gate_core(run_input)

    other.refresh_from_db()
    assert other.status == Artifact.Status.DRAFT


def test_a_waiting_document_still_publishes_when_the_gate_is_approved(wired, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)

    result = activities.publish_artifacts_core(run_input)

    assert Artifact.objects.get(id=result["published"][0]).status == Artifact.Status.PUBLISHED


def test_a_waiting_document_is_superseded_when_the_gate_is_rejected(wired, run_input):
    """Otherwise it would say "Waiting for approval" about work a person had already turned
    down — the relabel would state something false."""
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)

    activities.reject_run_core(run_input, "Not what we asked for.")

    assert set(Artifact.objects.filter(run_id=run_input.run_id)
               .values_list("status", flat=True)) == {Artifact.Status.SUPERSEDED}


def test_publish_artifacts_core(wired, store, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)
    result = activities.publish_artifacts_core(run_input)

    artifact = Artifact.objects.get(id=result["published"][0])
    # No connector configured for this tenant → internal SoR fallback (#B3).
    assert artifact.status == Artifact.Status.PUBLISHED and artifact.sor == Artifact.SoR.INTERNAL
    # Snapshot copied in the store.
    snap = next(k for k in store._data if k.startswith("snapshots/"))
    assert store.get(snap) == store.get(artifact.s3_key)
    assert Run.objects.get(id=run_input.run_id).status == Run.Status.COMPLETED
    # The Approval decision is recorded by the gate service (T9), not publish.


# ══ what a run may NOT publish on its own ══════════════════════════════════════
#
# Published means a named human approved this and it is the project's answer. A run started with
# `auto_approve` has no gate and this activity runs anyway — right for document vision, where the
# human had already adopted the source document, and wrong for the accessibility runs, which set
# the same flag for an unrelated reason (nobody watches their carrier work item, so a gate there
# would hang the audit for ever). They inherited the publishing without the justification.
#
# Measured 25 August across two tenants before this was fixed: every artifact of every judging
# run, published, approved by nobody.

def test_accessibility_run_artifacts_are_left_as_drafts(wired, store, run_input):
    a11y = Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id, run_id=run_input.run_id,
        phase="a11y_judge", type="a11y_judge", sor=Artifact.SoR.INTERNAL,
        status=Artifact.Status.DRAFT, title="Accessibility judging", content_hash="h1",
    )
    notes = Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id, run_id=run_input.run_id,
        phase="a11y_judge", type="assumption", sor=Artifact.SoR.INTERNAL,
        status=Artifact.Status.DRAFT, title="Assumptions", content_hash="h2",
    )

    result = activities.publish_artifacts_core(run_input)

    a11y.refresh_from_db()
    notes.refresh_from_db()
    assert a11y.status == Artifact.Status.DRAFT
    # The `assumption` row is the one a person notices in the registry; the judging document is
    # shown as run output and so wore a disguise. Both were published, and both are covered.
    assert notes.status == Artifact.Status.DRAFT
    assert {str(a11y.id), str(notes.id)} <= set(result["left_draft"])
    assert str(a11y.id) not in result["published"]


def test_it_says_what_it_left_rather_than_passing_over_it_in_silence(wired, run_input):
    """A run that quietly did less than its name says is the shape of failure this codebase
    keeps meeting — most recently a cleanup migration that deleted nothing and recorded itself
    as applied. What was skipped is returned AND put on the event."""
    Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id, run_id=run_input.run_id,
        phase="a11y_journey", type="a11y_judge", sor=Artifact.SoR.INTERNAL,
        status=Artifact.Status.DRAFT, title="Keyboard journey", content_hash="h3",
    )
    result = activities.publish_artifacts_core(run_input)

    assert len(result["left_draft"]) == 1
    event = Event.objects.filter(tenant_id=run_input.tenant_id,
                                 action="artifacts.published").latest("ts")
    assert event.payload["left_draft"] == result["left_draft"]


def test_every_other_phase_publishes_exactly_as_before(wired, store, run_input):
    """The whole platform runs through this activity. Nothing but the two accessibility phases
    may change behaviour — including `assumption`, which is a real deliverable everywhere else
    and IS published on the build path."""
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    assumption = Artifact.objects.create(
        tenant_id=run_input.tenant_id, project_id=run_input.project_id, run_id=run_input.run_id,
        phase="implementation", type="assumption", sor=Artifact.SoR.INTERNAL,
        status=Artifact.Status.DRAFT, title="Assumptions", content_hash="h4",
    )
    result = activities.publish_artifacts_core(run_input)

    assumption.refresh_from_db()
    assert assumption.status == Artifact.Status.PUBLISHED
    assert result["left_draft"] == []
    assert Run.objects.get(id=run_input.run_id).status == Run.Status.COMPLETED


class _FakeDocStore:
    def __init__(self):
        self.created: list[dict] = []

    def create_page(self, *, space, title, body_html, parent_ref=None):
        self.created.append({"space": space, "title": title, "body_html": body_html})
        from integrations.types import ExternalRef
        return ExternalRef(sor="confluence", id="PAGE-1",
                           url="https://x.atlassian.net/wiki/PAGE-1", version=1)


def test_publish_artifacts_core_never_auto_exports(wired, store, run_input, monkeypatch):
    """Team flow decision 2026-07-07: gate approval publishes INTERNAL only — even with a
    docstore connector configured, nothing is pushed. Export is user-triggered via the
    manual publish endpoint, governed by the phase-scoped export policy."""
    from integrations import publish

    fake = _FakeDocStore()
    monkeypatch.setattr(publish, "get_capability", lambda t, c: fake)
    monkeypatch.setattr(publish, "get_connection",
                        lambda t, c: SimpleNamespace(scopes={"space_key": "SDLC"}))

    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)
    result = activities.publish_artifacts_core(run_input)

    artifact = Artifact.objects.get(id=result["published"][0])
    assert artifact.status == Artifact.Status.PUBLISHED
    assert artifact.sor == Artifact.SoR.INTERNAL      # never confluence on approval
    assert fake.created == []                          # no page was pushed
    # The audit snapshot still lands in the store.
    assert any(k.startswith("snapshots/") for k in store._data)


def test_register_phase_result_core_merges_outputs_keeping_report(wired, run_input):
    """The companion's raw report (stored under outputs["report"] by report_phase, just
    before this activity) is preview's documented last fallback — result registration must
    MERGE into run.outputs, never overwrite it away."""
    run = Run.objects.get(id=run_input.run_id)
    run.outputs = {"report": {"status": "ok", "body": "# Ideation\nfull phase output"}}
    run.save(update_fields=["outputs"])

    report = SimpleNamespace(body="# Ideation\nfull phase output", cost_usd=0.02)
    activities.register_phase_result_core(run_input, report)

    outputs = Run.objects.get(id=run_input.run_id).outputs
    assert outputs["report"]["body"] == "# Ideation\nfull phase output"  # survived
    assert outputs["artifact_s3_key"]                                    # and staged


def test_register_phase_result_core_flags_empty_body(wired, run_input):
    """An "ok" report with no text must not silently open a gate on a blank deliverable —
    a phase.empty_result event makes it visible in the run's stream."""
    from apps.ledger.models import Event

    report = SimpleNamespace(body="", cost_usd=0.0, message="")
    activities.register_phase_result_core(run_input, report)

    assert Event.objects.filter(action="phase.empty_result",
                                target_id=run_input.run_id).exists()


def test_transition_work_item_core(wired, run_input):
    activities.transition_work_item_core(run_input, "done")
    assert WorkItem.objects.get(id=run_input.work_item_id).state == WorkItem.State.DONE


def test_reject_run_core(wired, run_input):
    activities.execute_agent_core(run_input, manifest="# Project\nx")
    activities.open_gate_core(run_input)
    activities.reject_run_core(run_input, comment="needs more detail")

    assert Run.objects.get(id=run_input.run_id).status == Run.Status.REJECTED
    assert WorkItem.objects.get(id=run_input.work_item_id).state == WorkItem.State.IN_PROGRESS
    # Approval decision recorded by the gate service (T9), verified there.


# ── "Request changes": reject → revise ──────────────────────────────


def _reject_with_drafts(run_input, direction="Use a single column."):
    """Put a run in the state the revise path actually starts from: an artifact registered, a
    decided (rejected) approval, and reject_run_core already applied."""
    tenant_id, run_id = run_input.tenant_id, run_input.run_id
    Artifact.objects.create(
        tenant_id=tenant_id, project_id=run_input.project_id, run_id=run_id,
        phase="prd", type="prd", title="PRD", status=Artifact.Status.DRAFT, version=1,
    )
    Approval.objects.create(
        tenant_id=tenant_id, run_id=run_id, work_item_id=run_input.work_item_id,
        required_role="product_owner", decision=Approval.Decision.REJECTED, comment=direction,
    )
    activities.reject_run_core(run_input, direction)


def test_rejecting_stamps_when_the_run_ended(run_input):
    """Every other terminal path records this; rejection was the last one that did not, so a
    rejected run's duration was permanently unknowable."""
    _reject_with_drafts(run_input)
    run = Run.objects.get(id=run_input.run_id)
    assert run.status == Run.Status.REJECTED
    assert run.ended_at is not None


def test_rejecting_supersedes_the_drafts_so_they_stop_being_served_downstream(run_input):
    """The reviewer said no. Without this the draft stayed the newest artifact of its type and
    get_context kept handing it to every later phase as the authoritative one."""
    from mcp_platform_state import tools

    _reject_with_drafts(run_input)
    art = Artifact.objects.get(run_id=run_input.run_id)
    assert art.status == Artifact.Status.SUPERSEDED
    ctx = tools.get_context(run_input.tenant_id, run_input.project_id, phase="architecture")
    served = [a["id"] for a in ctx["relevant_artifacts"]]
    assert str(art.id) not in served
    # It is NOT deleted — the revision's manifest cites it by id and the run console lists it.
    assert Artifact.objects.filter(id=art.id).exists()


def test_retrigger_starts_one_revision_carrying_the_note_and_what_was_produced(run_input):
    _reject_with_drafts(run_input)
    out = activities.retrigger_revision_core(run_input, "Use a single column.")
    assert out["revision_run_id"] and out["revision"] == 1

    new_run = Run.objects.get(id=out["revision_run_id"])
    history = new_run.inputs["review_history"]
    assert new_run.inputs["revision_of"] == run_input.run_id
    assert len(history) == 1
    assert history[0]["direction"] == "Use a single column."
    # The superseded draft is NAMED (not inlined) so the agent can re-read it on demand.
    assert history[0]["artifacts"][0]["type"] == "prd"


def test_retrigger_is_idempotent_when_temporal_replays_it(run_input):
    """Temporal retries an activity whose completion was lost. A second pass must NOT create a
    second run — and must not blow up on _guard_no_active_run against the run it just made."""
    _reject_with_drafts(run_input)
    first = activities.retrigger_revision_core(run_input, "Use a single column.")
    second = activities.retrigger_revision_core(run_input, "Use a single column.")
    assert second["revision_run_id"] == first["revision_run_id"]
    assert second.get("reused") is True
    assert Run.objects.filter(work_item_id=run_input.work_item_id).count() == 2


def test_the_revision_is_not_blocked_by_the_run_it_revises(run_input):
    """The 409 race this design exists to avoid: from the REST layer the old run is still
    AWAITING_GATE (an ACTIVE status) when the response returns, so the new run is refused. Doing
    it after reject_run means the old run is REJECTED, which is not an active status."""
    from orchestration.trigger import _ACTIVE_RUN_STATUSES

    _reject_with_drafts(run_input)
    assert Run.objects.get(id=run_input.run_id).status not in _ACTIVE_RUN_STATUSES
    assert activities.retrigger_revision_core(run_input, "go again")["revision_run_id"]


def test_the_conversation_accumulates_over_three_rounds(run_input):
    """The team's decision: the agent sees every earlier round, not just the last note. If this
    is ever trimmed back to one round, round 3 starts undoing what round 1 asked for."""
    _reject_with_drafts(run_input, "Round one: drop the hero image.")
    r2_id = activities.retrigger_revision_core(run_input, "Round one: drop the hero image.")[
        "revision_run_id"]

    r2_input = dataclasses.replace(run_input, run_id=r2_id)
    _reject_with_drafts(r2_input, "Round two: merge the forms.")
    r3_id = activities.retrigger_revision_core(r2_input, "Round two: merge the forms.")[
        "revision_run_id"]

    history = Run.objects.get(id=r3_id).inputs["review_history"]
    assert [h["direction"] for h in history] == [
        "Round one: drop the hero image.", "Round two: merge the forms."]
    assert [h["revision"] for h in history] == [1, 2]


def test_compose_manifest_survives_a_build_shaped_input(run_input, wired):
    """compose_manifest_core is duck-typed — BuildInput flows through it from dispatch_build,
    dispatch_remediation and the code-review provider. Reading a new field straight off `inp`
    would AttributeError on every build dispatch, so the review history comes off the Run row."""
    build_shaped = SimpleNamespace(
        run_id=run_input.run_id, tenant_id=run_input.tenant_id,
        project_id=run_input.project_id, work_item_id=run_input.work_item_id,
        phase="implementation",
    )
    assert "# Project" in activities.compose_manifest_core(build_shaped)


def test_a_revision_run_gets_the_direction_in_its_manifest(run_input, wired):
    _reject_with_drafts(run_input)
    revision_id = activities.retrigger_revision_core(run_input, "Use a single column.")[
        "revision_run_id"]
    revision_input = dataclasses.replace(run_input, run_id=revision_id)
    md = activities.compose_manifest_core(revision_input)
    assert "# Reviewer Direction" in md
    assert "Use a single column." in md
    assert md.find("# Reviewer Direction") < md.find("# Current Work Item")
