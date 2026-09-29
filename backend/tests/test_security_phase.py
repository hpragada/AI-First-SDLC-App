"""Security phase (10_security) end-to-end wiring (Bugs S.No 176–180).

Covers the four fixes that made the security phase actually run against real code:
- A2  read-only worktree for repo-scoped planning (catalog `reads_code`, trigger repo
      resolution, dispatch payload, driver read-only posture).
- B   the security defect loopback (Critical/High security_finding → defect WorkItem).
- C   verify_writes requires the real `security_review`, not the generic "security" blob.

These are logic/DB tests (no engine, no Temporal); the driver read-only posture is asserted
against a fake query so it avoids the SDK message-parser version skew.
"""
import uuid

import pytest

from apps.projects.models import Project, ProjectProfile, Repository
from apps.registry import catalog
from apps.registry.catalog import seed_agent_specs
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from orchestration import activities, trigger
from orchestration.activities import WriteCompletenessError
from orchestration.types import AgentRunInput
from storage import content_hash


# ── Planning-path failure classification (Bugs S.No 146, no DB) ─────
def test_classify_phase_failure_maps_bare_exit_code():
    """The exact message the security run showed must become a plain, actionable reason."""
    raw = ("Command failed with exit code 1 (exit code: 1)\n"
           "Error output: Check stderr output for details")
    msg = activities.classify_phase_failure(raw, phase="security")
    assert "exit code 1" not in msg and "stderr" not in msg
    # Says what is known and never guesses a cause (S.No 146); names the phase (2026-09-21).
    assert msg == "The Security phase stopped because the AI engine closed before it finished."


def test_classify_phase_failure_names_usage_limit():
    msg = activities.classify_phase_failure("Claude usage limit reached; try again later")
    assert "reached its usage limit" in msg


def test_classify_phase_failure_passes_specific_message_through():
    specific = "no AgentSpec registered for key '10_security'"
    assert activities.classify_phase_failure(specific) == specific


# ── Catalog: the reads_code flag (no DB) ────────────────────────────
def test_reads_code_true_for_security_and_code_intel():
    # reads_code = a repo-scoped planning phase gets a throwaway read-only worktree. 10_security
    # scans source directly; 00c queries the codebase via the CodeIntel MCP bound to that
    # worktree (agent-driven onboarding). Every other planning phase reasons over registered
    # context only — no worktree.
    assert catalog.reads_code("10_security") is True
    assert catalog.reads_code("00c_intelligent_context_extractor") is True
    for key in ("01_ideation", "02_requirements", "07_implementation", "09b_test_automation",
                "11_cicd", "08_code_review", "00_onboarding", "00b_context_bridge"):
        assert catalog.reads_code(key) is False


def test_reads_code_and_rides_build_are_mutually_exclusive():
    # A code-reading planning phase must never also ride the build (it already has a worktree).
    for d in catalog.AGENT_CATALOG:
        assert not (d.reads_code and d.rides_build), d.key


# ── Fixtures ────────────────────────────────────────────────────────
@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="ctx")
    seed_agent_specs(t)  # registers 10_security + 03_prd so trigger_phase resolves specs
    return {"t": t, "p": p}


def _capture_starter(box):
    def _starter(workflow_id, inp):
        box["workflow_id"] = workflow_id
        box["inp"] = inp
    return _starter


# ── A2: trigger repo resolution ─────────────────────────────────────
def test_security_trigger_resolves_the_single_default_repo(world):
    t, p = world["t"], world["p"]
    Repository.objects.create(tenant=t, project=p, name="acme/api", is_default=True,
                              default_base="main")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY)
    box = {}
    trigger.trigger_phase(
        tenant_id=str(t.id), project_id=str(p.id), work_item_id=str(wi.id),
        agent_key="10_security", workflow_starter=_capture_starter(box),
    )
    assert box["inp"].repo == "acme/api"
    assert box["inp"].base == "main"


def test_planning_phase_without_reads_code_resolves_no_repo(world):
    """Leak guard: a normal planning phase must NOT resolve a repo, even on a multi-repo project."""
    t, p = world["t"], world["p"]
    Repository.objects.create(tenant=t, project=p, name="acme/web", default_base="main")
    Repository.objects.create(tenant=t, project=p, name="acme/api", is_default=True,
                              default_base="main")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY)
    box = {}
    trigger.trigger_phase(
        tenant_id=str(t.id), project_id=str(p.id), work_item_id=str(wi.id),
        agent_key="03_prd", workflow_starter=_capture_starter(box),
    )
    assert box["inp"].repo is None
    assert box["inp"].base is None


def test_security_trigger_on_multirepo_unpinned_item_raises(world):
    t, p = world["t"], world["p"]
    Repository.objects.create(tenant=t, project=p, name="acme/web", default_base="main")
    Repository.objects.create(tenant=t, project=p, name="acme/api", is_default=True,
                              default_base="main")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY)
    with pytest.raises(trigger.TriggerError):
        trigger.trigger_phase(
            tenant_id=str(t.id), project_id=str(p.id), work_item_id=str(wi.id),
            agent_key="10_security", workflow_starter=_capture_starter({}),
        )


def test_security_trigger_on_project_with_no_repo_degrades(world):
    """Doc-only project: no repository → repo stays None (manifest-only scan), never raises."""
    t, p = world["t"], world["p"]
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY)
    box = {}
    trigger.trigger_phase(
        tenant_id=str(t.id), project_id=str(p.id), work_item_id=str(wi.id),
        agent_key="10_security", workflow_starter=_capture_starter(box),
    )
    assert box["inp"].repo is None


# ── A2: dispatch payload ────────────────────────────────────────────
def _mk_run_inp(world, *, phase="security", repo=None, base=None):
    t, p = world["t"], world["p"]
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.filter(tenant=t, key="10_security").order_by("-semver").first()
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec, temporal_workflow_id="wf")
    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(p.id),
        work_item_id=str(wi.id), agent_spec_id=str(spec.id), phase=phase,
        required_role="security_engineer", repo=repo, base=base,
    ), run, wi


def test_dispatch_carries_repo_for_reads_code_phase(world):
    inp, run, _ = _mk_run_inp(world, repo="acme/api", base="main")
    activities.dispatch_phase_core(inp, manifest="# Project\nm")
    task = Run.objects.get(id=run.id).inputs["phase_task"]
    assert task["kind"] == "plan"          # NOT build — stays on the planning path
    assert task["repo"] == "acme/api"
    assert task["base"] == "main"
    assert task["reads_code"] is True


def test_dispatch_omits_repo_keys_when_no_repo(world):
    inp, run, _ = _mk_run_inp(world, phase="prd", repo=None)
    activities.dispatch_phase_core(inp, manifest="# Project\nm")
    task = Run.objects.get(id=run.id).inputs["phase_task"]
    assert "repo" not in task and "base" not in task and "reads_code" not in task


# ── C: verify_writes requires the real security_review ──────────────
def _artifact(world, run, wi, *, type_, body=b"real"):
    return Artifact.objects.create(
        tenant=world["t"], project=world["p"], run=run, phase="security", type=type_,
        sor="internal", content_hash=content_hash(body), s3_key=f"k/{uuid.uuid4()}",
    )


def test_verify_writes_fails_when_only_generic_security_blob_present(world):
    inp, run, wi = _mk_run_inp(world)
    _artifact(world, run, wi, type_="security")  # the platform's generic blob, no real review
    with pytest.raises(WriteCompletenessError):
        activities.verify_write_completeness_core(inp, ["security"])


def test_verify_writes_passes_when_security_review_present(world):
    inp, run, wi = _mk_run_inp(world)
    _artifact(world, run, wi, type_="security_review", body=b"# Security Review\nfindings")
    out = activities.verify_write_completeness_core(inp, ["security"])
    assert "security_review" in out["expected"]


def test_verify_writes_fails_on_empty_security_review(world):
    inp, run, wi = _mk_run_inp(world)
    _artifact(world, run, wi, type_="security_review", body=b"")  # staged empty
    with pytest.raises(WriteCompletenessError):
        activities.verify_write_completeness_core(inp, ["security"])


# ── B: the security defect loopback ─────────────────────────────────
def test_security_findings_open_defect_workitems_for_critical_high(world):
    inp, run, wi = _mk_run_inp(world)
    Artifact.objects.create(
        tenant=world["t"], project=world["p"], run=run, phase="security",
        type="security_finding", sor="internal", content_hash=content_hash(b"x"),
        s3_key="k1", title="SQL injection", external_ref={"finding_id": "SEC-001",
                                                          "severity": "critical"})
    Artifact.objects.create(
        tenant=world["t"], project=world["p"], run=run, phase="security",
        type="security_finding", sor="internal", content_hash=content_hash(b"y"),
        s3_key="k2", title="verbose error", external_ref={"finding_id": "SEC-009",
                                                          "severity": "low"})
    out = activities._record_security_findings_from_run(inp)
    assert out["opened"], "a critical finding should open a defect"
    defects = WorkItem.objects.filter(parent_id=wi.id, type=WorkItem.Type.DEFECT)
    assert defects.count() == 1  # only the critical, not the low
    assert defects.first().external_ref.get("finding") == "SEC-001"


def test_security_loopback_noop_without_structured_findings(world):
    """A finding artifact with no structured id+severity is skipped, never guessed."""
    inp, run, wi = _mk_run_inp(world)
    Artifact.objects.create(
        tenant=world["t"], project=world["p"], run=run, phase="security",
        type="security_finding", sor="internal", content_hash=content_hash(b"z"),
        s3_key="k3", title="unstructured", external_ref=None)
    out = activities._record_security_findings_from_run(inp)
    assert out == {"opened": [], "closed": [], "blocking": []}
    assert WorkItem.objects.filter(parent_id=wi.id, type=WorkItem.Type.DEFECT).count() == 0
