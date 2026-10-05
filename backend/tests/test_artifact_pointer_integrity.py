"""An artifact's pointer must lead somewhere, and one that doesn't must not wedge a phase.

All four failures here were found in one live run on 2026-10-05 (S.No 313-316), from a single
mistyped character. An agent registered a feasibility report against a body path one character
off the real project id. Every screen showed a perfect artifact. The gate was approved by a
human on the strength of that list. Publishing then walked the run's artifacts, hit the hollow
pointer, died mid-loop, and left one artifact published, six stranded, the run unfinished and
the gate gone from the screen — with the only evidence in a worker container's log.

The tests are written so each one fails on its own cause, because the four fixes are
independent and a later reader needs to know which guarantee broke.
"""
import pytest
from mcp_platform_state import tools

from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration.types import AgentRunInput


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="PeopleDesk")
    wi = WorkItem.objects.create(
        tenant=t, project=project, type=WorkItem.Type.STORY, feature_stream="hr")
    spec = AgentSpec.objects.create(
        tenant=t, key="01_ideation", body_ref="agents/01_ideation/agent.md")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    return {"t": t, "project": project, "wi": wi, "spec": spec, "run": run}


def _input(world, phase="ideation"):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["wi"].id),
        agent_spec_id=str(world["spec"].id), phase=phase,
    )


# ── S.No 313 · the platform's own ids are not overridable by the agent ──────
def test_a_project_id_the_agent_passes_cannot_override_the_launch_binding(monkeypatch, world):
    """THE root cause. The binding is the id the control plane launched this run with; an
    agent's argument is a string it copied from a manifest, by hand. The second must never
    win over the first."""
    from mcp_platform_state import server

    real = str(world["project"].id)
    wrong = real[:-7] + "8" + real[-6:]          # one character off, as the live failure was
    assert wrong != real

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.setenv("PLATFORM_PROJECT_ID", real)
    monkeypatch.setenv("PLATFORM_RUN_ID", str(world["run"].id))

    out = server.stage_artifact_body(
        filename="peopledesk-feasibility-report", body="# Feasibility",
        phase="ideation", project_id=wrong,
    )
    assert real in out["s3_key"], "the launch binding must win"
    assert wrong not in out["s3_key"], "the agent's mistyped id reached the body path"


def test_the_agent_argument_is_still_used_when_nothing_is_bound(monkeypatch, world):
    """The argument is a FALLBACK, not dead weight — a context with no binding still works."""
    from mcp_platform_state import server

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.delenv("PLATFORM_PROJECT_ID", raising=False)
    monkeypatch.delenv("PLATFORM_RUN_ID", raising=False)

    out = server.stage_artifact_body(
        filename="body", body="x", phase="ideation", project_id=str(world["project"].id))
    assert str(world["project"].id) in out["s3_key"]


# ── S.No 314 · a registration whose body is not there is refused ────────────
def test_registering_an_artifact_whose_body_is_missing_is_refused(monkeypatch, world):
    """Through the SERVER, because that is the boundary agents come through and where the
    check lives — platform code stages its own bodies a line above registering them."""
    from mcp_platform_state import server

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.setenv("PLATFORM_PROJECT_ID", str(world["project"].id))
    monkeypatch.setenv("PLATFORM_RUN_ID", str(world["run"].id))
    with pytest.raises(ValueError) as exc:
        server.register_artifact(
            phase="ideation", type="feasibility_report", sor="internal",
            content_hash="hash-1", s3_key="drafts/nowhere/at/all",
            title="PeopleDesk - Feasibility Report",
        )
    msg = str(exc.value)
    assert "point at nothing" in msg
    assert "stage_artifact_body" in msg, "the refusal must say how to put it right"
    assert not Artifact.objects.filter(run_id=world["run"].id).exists(), \
        "nothing may be recorded when the body is missing"


def test_a_staged_body_registers_normally(monkeypatch, world):
    """The guard must not stand in the way of the ordinary path: stage, then register."""
    from mcp_platform_state import server

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.setenv("PLATFORM_PROJECT_ID", str(world["project"].id))
    monkeypatch.setenv("PLATFORM_RUN_ID", str(world["run"].id))
    ptr = server.stage_artifact_body(
        filename="peopledesk-project-concept", body="# Concept", phase="ideation")
    out = server.register_artifact(
        phase="ideation", type="ideation", sor="internal",
        content_hash=ptr["content_hash"], s3_key=ptr["s3_key"], title="Project Concept")
    assert out["id"]


def test_a_bodyless_registration_is_still_allowed(monkeypatch, world):
    """`sor=git` artifacts legitimately carry no body — the guard must not catch them."""
    from mcp_platform_state import server

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.setenv("PLATFORM_PROJECT_ID", str(world["project"].id))
    monkeypatch.setenv("PLATFORM_RUN_ID", str(world["run"].id))
    out = server.register_artifact(
        phase="implementation", type="code", sor="git", content_hash="hash-2",
        s3_key=None, title="PR 12")
    assert out["id"]


# ── S.No 315 · one broken artifact must not take the others down ────────────
def _artifact(world, type_, key, store, body="x"):
    store.put(key, body)
    return tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "ideation", type_,
        "internal", f"h-{type_}", s3_key=key, title=f"T {type_}", object_store=store)


def test_one_unsnapshottable_artifact_does_not_strand_the_others(world, object_store):
    """The live failure, reproduced: seven artifacts, one whose body has gone missing between
    registration and the gate. Six must publish, the run must finish, and the broken one must
    be named rather than silently dropped."""
    from orchestration import activities

    for i in range(3):
        _artifact(world, f"type_{i}", f"drafts/ok-{i}", object_store)
    _artifact(world, "feasibility_report", "drafts/vanishes", object_store)
    object_store.delete("drafts/vanishes")          # gone after registration, as in the wild

    out = activities.publish_artifacts_core(_input(world))

    statuses = {a.title: a.status for a in Artifact.objects.filter(run_id=world["run"].id)}
    assert sum(s == Artifact.Status.PUBLISHED for s in statuses.values()) == 3
    assert statuses["T feasibility_report"] != Artifact.Status.PUBLISHED

    world["run"].refresh_from_db()
    assert world["run"].status == Run.Status.COMPLETED, \
        "the human's gate decision was real — the run must not hang on one bad artifact"
    assert world["run"].ended_at is not None
    assert len(out["failed"]) == 1, "the broken artifact must be reported back, not dropped"
    assert out["failed"][0]["title"] == "T feasibility_report"


def test_the_failure_is_recorded_where_people_look(world, object_store):
    """Not only in a worker log. The 2026-10-05 failure was invisible on every screen."""
    from apps.ledger.models import Event
    from orchestration import activities

    _artifact(world, "ideation", "drafts/fine", object_store)
    _artifact(world, "feasibility_report", "drafts/gone", object_store)
    object_store.delete("drafts/gone")

    activities.publish_artifacts_core(_input(world))

    failed = Event.objects.filter(
        tenant_id=world["t"].id, action="artifacts.publish_failed").first()
    assert failed is not None, "a publish that could not finish must say so on the run"
    assert failed.payload["count"] == 1
    only = failed.payload["artifacts"][0]
    assert only["title"] == "T feasibility_report"
    assert only["reason"], "a failure with no reason is not worth recording"


# ── S.No 316 · every artifact keeps its own snapshot ────────────────────────
def test_each_artifact_gets_its_own_audit_snapshot(world, object_store):
    """The snapshot used to be keyed on (phase, version). Every artifact of a phase shares
    both, so a seven-artifact ideation wrote seven snapshots to ONE key and kept the last.
    This is the record that is supposed to prove what a human approved."""
    from orchestration import activities

    for i in range(4):
        _artifact(world, f"kind_{i}", f"drafts/body-{i}", object_store, body=f"body {i}")
    activities.publish_artifacts_core(_input(world))

    snaps = [k for k in object_store._data if k.startswith("snapshots/")]
    assert len(snaps) == 4, f"expected one snapshot per artifact, got {len(snaps)}: {snaps}"
    assert len({object_store._data[k] for k in snaps}) == 4, \
        "the snapshots overwrote each other — their contents are not distinct"


# ── S.No 317 · a borrowed body says so, and cannot be exported ──────────────
def _hollow(world, object_store):
    """An artifact pointing at a body that isn't there, with a run that has a report — the
    exact shape of the live failure."""
    art = Artifact.objects.create(
        tenant=world["t"], project=world["project"], run=world["run"], phase="ideation",
        type="feasibility_report", title="PeopleDesk - Feasibility Report",
        sor="internal", status=Artifact.Status.STAGED, content_hash="h", version=1,
        s3_key="drafts/never-written",
    )
    world["run"].outputs = {"report": {"body": "The ideation phase is complete. Here is a "
                                               "summary of everything produced:"}}
    world["run"].save(update_fields=["outputs"])
    return art


def test_a_body_borrowed_from_the_run_is_declared_as_such(world, object_store):
    from integrations.preview import read_artifact_preview

    art = _hollow(world, object_store)
    out = read_artifact_preview(tenant_id=str(world["t"].id), artifact_id=str(art.id))
    assert out["body"], "the fallback itself stays — the content is worth reading"
    assert out["body_from_run"] is True, \
        "a document showing its RUN's report under its own title must admit it"


def test_a_document_with_its_own_body_claims_nothing(world, object_store):
    from integrations.preview import read_artifact_preview

    object_store.put("drafts/real", "# The actual feasibility report")
    art = Artifact.objects.create(
        tenant=world["t"], project=world["project"], run=world["run"], phase="ideation",
        type="feasibility_report", title="Real", sor="internal",
        status=Artifact.Status.STAGED, content_hash="h", version=1, s3_key="drafts/real")
    out = read_artifact_preview(tenant_id=str(world["t"].id), artifact_id=str(art.id))
    assert out["body_from_run"] is False


# ── S.No 318 · the status stops inviting a decision nobody can give ─────────
def test_gate_decided_is_true_once_the_gate_is_decided_and_it_is_still_unpublished(
        world, object_store):
    from api.serializers import ArtifactSerializer
    from apps.gates.models import Approval

    art = _hollow(world, object_store)
    assert ArtifactSerializer(art).data["gate_decided"] is False   # no gate yet

    Approval.objects.create(
        tenant=world["t"], run=world["run"], work_item=world["wi"],
        required_role="product_owner", decision=Approval.Decision.APPROVED)
    assert ArtifactSerializer(art).data["gate_decided"] is True


def test_a_published_document_makes_no_such_claim(world, object_store):
    from api.serializers import ArtifactSerializer
    from apps.gates.models import Approval

    art = _hollow(world, object_store)
    art.status = Artifact.Status.PUBLISHED
    art.save(update_fields=["status"])
    Approval.objects.create(
        tenant=world["t"], run=world["run"], work_item=world["wi"],
        required_role="product_owner", decision=Approval.Decision.APPROVED)
    assert ArtifactSerializer(art).data["gate_decided"] is False


# ── the path a COMPANION's agent actually comes through ────────────────────
def test_the_runner_state_endpoint_refuses_a_pointer_to_nothing(world, object_store, client):
    """The decisive one. A companion's agent does not load the stdio MCP server — it posts to
    /api/runner/state/register_artifact/. The guard was first written on the other path, which
    this run would never have touched, so this test exists to pin the one that matters."""
    from apps.runs.models import RunnerEnrollment
    from apps.runs.enrollment import _hash

    token = "tok-for-this-test"
    RunnerEnrollment.objects.create(
        tenant=world["t"], project=world["project"], enroll_token_hash=_hash(token),
        status=RunnerEnrollment.Status.ACTIVE, repos=[],
    )
    r = client.post(
        "/api/runner/state/register_artifact/",
        {"project_id": str(world["project"].id), "run_id": str(world["run"].id),
         "phase": "ideation", "type": "feasibility_report", "sor": "internal",
         "content_hash": "h", "title": "Feasibility Report",
         "s3_key": "drafts/composed/by/hand"},
        format="json",
        HTTP_AUTHORIZATION=f"Runner {token}", HTTP_X_TENANT_ID=str(world["t"].id),
    )
    assert r.status_code == 400, r.data
    assert "point at nothing" in str(r.data)
    assert not Artifact.objects.filter(run_id=world["run"].id).exists()
