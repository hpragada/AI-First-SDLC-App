"""P3 — a11y (WCAG) gate · per-tenant theming · design↔code round-trip.

- The a11y gate is a control-plane checklist on the design Approval (D6): the design
  phase's gate is seeded with the WCAG 2.2 AA criteria (QA-11 — derived from the loaded
  standard), and an APPROVED decision is blocked while any required criterion is unsatisfied.
- Per-tenant theming (PG23/D10): ProjectProfile.theme flows verbatim into the rendered
  manifest (tokens + responsive breakpoints) — no per-tenant code fork.
- design↔code round-trip (PG22): read-as-SoR (05) + Code Connect mapping + the deferred
  generate_figma_design canvas-write seam.
"""
import pytest

from apps.gates.conditions import conditions_for_phase
from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.wcag import wcag_aa_checklist
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from manifest.composer import compose_manifest
from orchestration.activities import open_gate_core
from orchestration.types import AgentRunInput


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


# ── a11y (WCAG) gate: checklist seeding ─────────────────────────────
def test_conditions_for_phase_seeds_wcag_only_for_design(db):
    """Needs the database since QA-11: the checklist is read from the loaded 2.2 standard
    rather than typed into the module, so building it is a query."""
    design = conditions_for_phase("ux_design")
    keys = {c["key"] for c in design}
    assert {"1.1.1", "1.4.3", "2.1.1", "2.4.7"} <= keys      # WCAG 2.2 AA criteria present
    assert all(c["required"] and not c["satisfied"] for c in design)
    assert conditions_for_phase("prd") == []                 # no other phase carries it


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="05_ux_design", body_ref="x")
    run = Run.objects.create(
        tenant=t, work_item=wi, agent_spec=spec, temporal_workflow_id="wf-1"
    )
    designer = User.objects.create_user(
        email="d@acme.test", name="Dee", tenant=t, password="pw"
    )
    Membership.objects.create(tenant=t, user=designer, project=project, role="designer")
    return {"t": t, "project": project, "wi": wi, "run": run,
            "designer_id": str(designer.id)}


def _inp(world, phase):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["wi"].id),
        agent_spec_id="s", phase=phase, required_role="designer",
    )


def test_open_gate_core_seeds_wcag_checklist_for_ux_design(world):
    approval_id = open_gate_core(_inp(world, "ux_design"))
    approval = Approval.objects.get(id=approval_id)
    assert len(approval.conditions) == len(wcag_aa_checklist())
    assert {c["key"] for c in approval.conditions} >= {"1.4.3", "2.4.7", "3.3.2"}
    assert all(not c["satisfied"] for c in approval.conditions)


@pytest.mark.django_db
def test_open_gate_core_no_conditions_for_non_design_phase():
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec,
                             temporal_workflow_id="wf-2")
    inp = AgentRunInput(run_id=str(run.id), tenant_id=str(t.id), project_id=str(project.id),
                        work_item_id=str(wi.id), agent_spec_id="s", phase="prd")
    approval = Approval.objects.get(id=open_gate_core(inp))
    assert approval.conditions == []


# ── a11y (WCAG) gate: enforcement on decide ─────────────────────────
def test_decide_gate_blocks_approve_until_wcag_satisfied(world):
    approval_id = open_gate_core(_inp(world, "ux_design"))
    sender = _Recorder()

    # Approving with the WCAG checklist unmet is blocked — and nothing is signaled.
    with pytest.raises(GateConditionsError):
        decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                    user_id=world["designer_id"], decision="approved", signal_sender=sender)
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.PENDING
    assert sender.calls == []

    # Mark every criterion satisfied → the gate becomes grantable.
    satisfied = [{"key": c["key"], "satisfied": True} for c in wcag_aa_checklist()]
    result = decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                         user_id=world["designer_id"], decision="approved",
                         conditions=satisfied, signal_sender=sender)
    assert result["decision"] == "approved"
    assert all(c["satisfied"] for c in result["conditions"])
    assert sender.calls and sender.calls[0][1] == "approved"


def test_decide_gate_partial_wcag_still_blocks(world):
    approval_id = open_gate_core(_inp(world, "ux_design"))
    partial = [{"key": "1.1.1", "satisfied": True}]            # one of the checklist, not all
    with pytest.raises(GateConditionsError):
        decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                    user_id=world["designer_id"], decision="approved",
                    conditions=partial, signal_sender=_Recorder())


def test_decide_gate_rejection_ignores_conditions(world):
    approval_id = open_gate_core(_inp(world, "ux_design"))
    sender = _Recorder()
    # A rejection is never blocked by unmet conditions.
    decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                user_id=world["designer_id"], decision="rejected", signal_sender=sender)
    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.REJECTED
    assert sender.calls[0][1] == "rejected"


# ── per-tenant theming flows into the manifest (PG23/D10) ───────────
def test_theme_flows_into_manifest_project_section():
    theme = {"brand": "acme", "tokens": {"primary-action": "#2563eb"},
             "breakpoints": [375, 768, 1440]}
    manifest = compose_manifest(
        context={"profile": {"name": "P", "theme": theme}},
        work_item={}, phase="ux_design",
    )
    assert "# Project" in manifest
    assert "theme" in manifest and "#2563eb" in manifest      # tokens verbatim
    assert "1440" in manifest                                 # responsive breakpoints verbatim


@pytest.mark.django_db
def test_get_context_profile_includes_theme():
    from mcp_platform_state import tools

    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, theme={"breakpoints": [375, 1440]}
    )
    ctx = tools.get_context(t.id, project.id, phase="ux_design")
    assert ctx["profile"]["theme"] == {"breakpoints": [375, 1440]}


# ── design↔code round-trip (PG22): the three legs cohere ────────────
def test_design_code_round_trip_seam():
    from pathlib import Path

    from integrations import design
    from integrations.figma.config import FigmaConfig
    from integrations.figma.designsource import FigmaDesignSource
    from integrations.types import ComponentRef, DesignSpec

    # Leg 1 — design→code link: the Code Connect mapping names a code component per design one.
    entries = design.build_code_connect([ComponentRef(key="k", name="doctor card", node_id="3:1")])
    assert entries[0].code_component == "DoctorCard"

    # Leg 2 — code→canvas write is the deferred seam (NotImplementedError until beta write).
    ds = FigmaDesignSource(FigmaConfig(api_url="https://api.figma.com", token="t"),
                           default_file_key="F", transport=lambda *a, **k: (200, {}))
    with pytest.raises(NotImplementedError):
        ds.generate_figma_design(spec=DesignSpec(name="Login", payload={}))

    # Leg 3 — read-as-SoR: the migrated 05 body reads the current design via designsource.
    body = (Path(__file__).resolve().parents[2] / "agents/05_ux_design/agent.md").read_text(
        encoding="utf-8"
    )
    assert "designsource" in body and "get_design_context" in body
