"""Phase-3 acceptance slice (spec §8) — the Design & Test loops end-to-end.

The headline (`test_acceptance_design_phase_wcag_gate_live`) runs the **real AgentRunWorkflow on
a live Temporal server** (skips if unreachable) for the **ux_design** phase: the engine is stubbed
to register the design artifacts, then the **a11y/WCAG gate** opens — the artifacts stay DRAFT,
an approve with the WCAG checklist unmet is **blocked**, and only an approve with every WCAG
criterion satisfied publishes them (gate-then-publish, D6) and completes the durable run.

The rest of the loop is proven deterministically (no Temporal): implementation reads the **current
design** (designsource read-as-SoR + the wireframe-artifact fallback, G3); **results → Xray** with
idempotent import; a **failing test → a linked/traced defect** (defect loopback → re-run closes,
D5); the **standalone security loop** (findings/SBOM → defect, D8); the **companion-local preview
env**; **test-impact selection** + **flaky quarantine** (D9); tenant isolation; and the §8 sweep.
"""
import asyncio
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from mcp_platform_state import tools

from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.wcag import wcag_aa_checklist
from apps.projects.models import Project, ProjectProfile
from apps.quality import preview, services
from apps.quality.models import PreviewEnv, TestExecution, TestQuarantine
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations import design
from integrations.types import (
    CapabilityUnavailable,
    ComponentRef,
    DesignContext,
    DesignToken,
    ExternalRef,
)

_TEMPORAL = "localhost:7233"
_REPO_ROOT = Path(__file__).resolve().parents[2]


# ── capability fakes (read-as-SoR + Xray + preview link) ────────────
class _FakeDesignSource:
    def get_design_context(self, *, file_key=None, node_id=None):
        return DesignContext(file_key="FILE", name="Acme Design",
                             frames=[{"node_id": "1:2", "name": "Login", "type": "FRAME"}], url="u")

    def get_variable_defs(self, *, file_key=None):
        return [DesignToken(name="primary-action", kind="color", value="#2563eb", ref="v1")]

    def list_components(self, *, file_key=None):
        return [ComponentRef(key="k1", name="Login Button", node_id="1:3", url="cu")]


class _FakeTestMgmt:
    """Records each import's execution_ref so idempotency (update vs create) is observable."""

    def __init__(self):
        self._project = "QA"
        self.imports: list = []

    def import_results(self, *, execution):
        self.imports.append(execution.execution_ref)
        return ExternalRef(sor="xray", id="QA-100", url="https://xray/QA-100")

    def link_defect(self, *, test_ref, defect_ref):
        pass


class _FakeCodeHost:
    def __init__(self):
        self.comments: list = []

    def add_pr_comment(self, *, pr_ref, body):
        self.comments.append((pr_ref, body))


def _cap_router(**caps):
    def get_capability(_tid, cap):
        if cap in caps:
            return caps[cap]
        raise CapabilityUnavailable(f"no {cap}")
    return get_capability


# ── world ───────────────────────────────────────────────────────────
def _seed(name="Acme"):
    t = Tenant.objects.create(name=name)
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.",
                                  theme={"breakpoints": [375, 768, 1440]})
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login",
                                    state=WorkItem.State.ACCEPTED)
    spec = AgentSpec.objects.create(tenant=t, key="05_ux_design", body_ref="x",
                                    phase_label="ux_design")
    run = Run.objects.create(tenant=t, work_item=story, agent_spec=spec,
                             temporal_workflow_id=f"wf-{uuid.uuid4()}")
    return t, p, story, spec, run


def _member(t, p, role):
    u = User.objects.create_user(email=f"{role}@acme.test", name=role, tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=u, project=p, role=role)
    return u


def _input(t, p, story, spec, run, phase, role):
    from orchestration.types import AgentRunInput

    return AgentRunInput(
        run_id=str(run.id), tenant_id=str(t.id), project_id=str(p.id),
        work_item_id=str(story.id), agent_spec_id=str(spec.id), phase=phase, required_role=role,
    )


def _wcag_all_satisfied():
    return [{"key": c["key"], "satisfied": True} for c in wcag_aa_checklist()]


# ── 1. design → WCAG gate → published (gate-then-publish, D6) ────────
@pytest.mark.django_db
def test_acceptance_design_to_published_through_wcag_gate():
    from orchestration.activities import open_gate_core, publish_artifacts_core

    t, p, story, spec, run = _seed()
    designer = _member(t, p, "designer")
    inp = _input(t, p, story, spec, run, "ux_design", "designer")

    # 05 registers its design artifacts as drafts (nothing published pre-gate).
    for art in ["ux_design", "user_journey", "wireframe", "design_system", "accessibility"]:
        tools.register_artifact(t.id, p.id, run.id, "ux_design", art, "internal", f"h-{art}")
    assert {a.status for a in Artifact.objects.filter(run_id=run.id)} == {Artifact.Status.DRAFT}

    # The design gate carries the WCAG 2.2 AA checklist (control-plane, D6).
    approval_id = open_gate_core(inp)
    approval = Approval.objects.get(id=approval_id)
    assert len(approval.conditions) == len(wcag_aa_checklist())

    # Approving with the WCAG checklist unmet is blocked → nothing publishes.
    with pytest.raises(GateConditionsError):
        decide_gate(tenant_id=str(t.id), approval_id=approval_id, user_id=str(designer.id),
                    decision="approved", signal_sender=lambda *a, **k: None)
    assert not Artifact.objects.filter(run_id=run.id, status=Artifact.Status.PUBLISHED).exists()

    # WCAG satisfied → gate grantable → the platform publishes the design set.
    decide_gate(tenant_id=str(t.id), approval_id=approval_id, user_id=str(designer.id),
                decision="approved", conditions=_wcag_all_satisfied(),
                signal_sender=lambda *a, **k: None)
    publish_artifacts_core(inp)
    assert {a.status for a in Artifact.objects.filter(run_id=run.id)} == {Artifact.Status.PUBLISHED}


# ── 2. implementation reads the CURRENT design (read-as-SoR + fallback, G3) ──
@pytest.mark.django_db
def test_acceptance_implementation_reads_current_design(monkeypatch):
    t, p, story, spec, run = _seed()
    # Read-as-SoR: the platform reads the client's current design at run time.
    monkeypatch.setattr(design, "get_capability",
                        _cap_router(designsource=_FakeDesignSource()))
    ds = design.fetch_design_system(t.id)
    assert ds.name == "Acme Design"
    assert any(tok.name == "primary-action" and tok.value == "#2563eb" for tok in ds.tokens)
    assert design.build_code_connect(ds.components)[0].code_component == "LoginButton"

    # Fallback: with no connected design, implementation reads the registered design artifact.
    art = tools.register_artifact(t.id, p.id, run.id, "ux_design", "design_system", "internal", "h")
    monkeypatch.setattr(design, "get_capability", _cap_router())   # designsource unavailable
    with pytest.raises(CapabilityUnavailable):
        design.fetch_design_system(t.id)
    assert tools.get_artifact(t.id, art["id"])["type"] == "design_system"


# ── 3. THE slice: results → Xray; failing test → linked/traced bug; loopback (D5) ──
@pytest.mark.django_db
def test_acceptance_test_results_to_xray_and_traced_defect(monkeypatch):
    t, p, story, spec, run = _seed()
    qa = _member(t, p, "qa_lead")
    tm = _FakeTestMgmt()
    monkeypatch.setattr("integrations.registry.get_capability", _cap_router(testmgmt=tm))

    # A `code` artifact under the story so the test_report can trace to the code under test.
    code_id = tools.register_artifact(t.id, p.id, run.id, "implementation", "code", "git", "h",
                                      external_ref={"repo": "acme/api", "number": 7})["id"]

    # 09/09b run the suite → results imported to Xray; a FAIL opens a traced defect.
    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id, push_to_sor=True,
        results=[{"test_ref": "QA-2", "status": "PASS"},
                 {"test_ref": "QA-9", "status": "FAIL", "evidence": "AssertionError"}],
    )
    assert out["status"] == "failed" and out["external_ref"]["id"] == "QA-100"   # → Xray
    assert tm.imports == [None]                                                  # create

    # The failing test → a linked/traced bug: a defect WorkItem tied to the test + the code.
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)
    assert defect.external_ref["test_ref"] == "QA-9"
    assert defect.external_ref["test_report"] == out["test_report_id"]           # linked to test
    report = Artifact.objects.get(id=out["test_report_id"])
    assert TraceEdge.objects.filter(from_artifact=report, to_artifact_id=code_id,
                                    rel="tests").exists()                        # traced to code

    # Re-run with the test fixed → the defect closes; the Xray import updates the execution.
    out2 = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id, push_to_sor=True,
        results=[{"test_ref": "QA-2", "status": "PASS"}, {"test_ref": "QA-9", "status": "PASS"}],
    )
    assert out2["status"] == "passed" and len(out2["defects_closed"]) == 1
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE
    assert tm.imports == [None, "QA-100"]                                        # idempotent
    assert TestExecution.objects.filter(run_id=run.id, work_item_id=story.id).count() == 1

    # The QA gate then advances the test phase (qa_lead). It carries the blocking-test rule
    # (D9) rather than the design gate's WCAG checklist — and it is grantable here only
    # because the re-run above closed the defect; a still-red suite would have held it shut
    # (see test_test_gate_and_severity.py).
    from apps.gates.testgate import BLOCKING_TESTS_KEY
    from orchestration.activities import open_gate_core

    inp = _input(t, p, story, spec, run, "testing", "qa_lead")
    approval_id = open_gate_core(inp)
    conditions = Approval.objects.get(id=approval_id).conditions
    assert [c["key"] for c in conditions] == [BLOCKING_TESTS_KEY]                # no WCAG here
    res = decide_gate(tenant_id=str(t.id), approval_id=approval_id, user_id=str(qa.id),
                      decision="approved", signal_sender=lambda *a, **k: None)
    assert res["decision"] == "approved"
    assert res["conditions"][0]["satisfied"] is True            # the loopback closed the defect


# ── 4. standalone security loop (findings/SBOM → defect, D8) ─────────
@pytest.mark.django_db
def test_acceptance_security_standalone_loopback():
    t, p, story, spec, run = _seed()
    sec = _member(t, p, "security_engineer")

    # 10 registers a security_review + sbom + a finding, and a critical opens a defect.
    review = tools.register_artifact(t.id, p.id, run.id, "security", "security_review",
                                     "internal", "h")
    tools.register_artifact(t.id, p.id, run.id, "security", "sbom", "internal", "h")
    out = services.record_security_findings(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, review_artifact_id=review["id"],
        findings=[{"id": "SEC-001", "severity": "critical", "title": "SQLi"},
                  {"id": "SEC-007", "severity": "low", "title": "verbose error"}],
    )
    assert out["blocking"] == ["SEC-001"] and len(out["opened"]) == 1
    defect = WorkItem.objects.get(parent_id=story.id, type=WorkItem.Type.DEFECT)
    assert defect.external_ref["kind"] == "security" and defect.external_ref["finding"] == "SEC-001"

    # Resolve the critical → the security defect closes; the standalone gate then advances.
    out2 = services.record_security_findings(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id,
        findings=[{"id": "SEC-007", "severity": "low", "title": "verbose error"}])
    assert len(out2["closed"]) == 1
    defect.refresh_from_db()
    assert defect.state == WorkItem.State.DONE

    from orchestration.activities import open_gate_core

    inp = _input(t, p, story, spec, run, "security", "security_engineer")
    approval_id = open_gate_core(inp)
    res = decide_gate(tenant_id=str(t.id), approval_id=approval_id, user_id=str(sec.id),
                      decision="approved", signal_sender=lambda *a, **k: None)
    assert res["decision"] == "approved"


# ── 5. companion-local preview env (D7) ─────────────────────────────
@pytest.mark.django_db
def test_acceptance_preview_env_lifecycle():
    t, p, story, spec, run = _seed()
    host = _FakeCodeHost()
    out = preview.provision_preview(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        pr_ref="acme/api#7", url="http://localhost:5173",
        get_capability=_cap_router(codehost=host))
    env = PreviewEnv.objects.get(id=out["preview_id"])
    assert env.status == PreviewEnv.Status.READY and env.provider == "companion_local"
    assert host.comments and "http://localhost:5173" in host.comments[0][1]
    assert preview.teardown_preview(tenant_id=t.id, preview_id=out["preview_id"])["status"] == \
        "torn_down"


# ── 6. test-impact selection + flaky quarantine (D9) ────────────────
@pytest.mark.django_db
def test_acceptance_test_impact_and_flaky_quarantine():
    t, p, story, spec, run = _seed()

    def art(type_):
        return tools.register_artifact(t.id, p.id, run.id, "x", type_, "internal", "h")["id"]

    req, code, tc, noise = art("requirement"), art("code"), art("test_case"), art("test_case")
    tools.add_trace_edge(t.id, code, req, "derives")
    tools.add_trace_edge(t.id, tc, req, "tests")
    tools.add_trace_edge(t.id, noise, art("requirement"), "tests")
    assert services.select_impacted_tests(t.id, code_artifact_id=code) == [tc]   # only linked test

    # A test that flips within one execution is quarantined (excluded from the blocking gate).
    out = services.import_test_results(
        tenant_id=t.id, project_id=p.id, work_item_id=story.id, run_id=run.id,
        results=[{"test_ref": "FLK-1", "status": "PASS"}, {"test_ref": "FLK-1", "status": "FAIL"}])
    assert out["flaky"] == ["FLK-1"] and out["status"] == "passed" and out["defects_opened"] == []
    assert TestQuarantine.objects.filter(tenant=t, test_ref="FLK-1", active=True).exists()


# ── 7. tenant isolation (a second tenant sees none of the loop's state) ──
@pytest.mark.django_db
def test_acceptance_tenant_isolation():
    t, p, story, spec, run = _seed("Owner")
    services.import_test_results(tenant_id=t.id, project_id=p.id, work_item_id=story.id,
                                 run_id=run.id, results=[{"test_ref": "X-1", "status": "FAIL"}])
    services.record_security_findings(tenant_id=t.id, project_id=p.id, work_item_id=story.id,
                                      findings=[{"id": "SEC-1", "severity": "critical"}])
    preview.provision_preview(tenant_id=t.id, project_id=p.id, work_item_id=story.id,
                              pr_ref="acme/api#1", url="u", post_comment=False)

    other = Tenant.objects.create(name="Intruder")
    assert TestExecution.objects.filter(tenant_id=other.id).count() == 0
    assert PreviewEnv.objects.filter(tenant_id=other.id).count() == 0
    assert WorkItem.objects.filter(tenant_id=other.id, type=WorkItem.Type.DEFECT).count() == 0
    assert Artifact.objects.filter(tenant_id=other.id).count() == 0
    # The owner's loop did open both a test defect and a security defect under its own tenant.
    assert WorkItem.objects.filter(tenant_id=t.id, type=WorkItem.Type.DEFECT).count() == 2


# ── 8. §8 reference sweep stays clean on the migrated P3 agents ─────
def test_acceptance_p3_agents_reference_sweep_clean():
    forbidden = [".md", "docs/", "claude.md", "tasks.md", "reply approved", "/sdlc:"]
    for key in ["05_ux_design", "09_testing", "09b_test_automation", "10_security"]:
        body = (_REPO_ROOT / "agents" / key / "agent.md").read_text(encoding="utf-8").lower()
        assert not [tok for tok in forbidden if tok in body], f"{key}: §8 sweep dirty"


# ── 9. live headline: durable ux_design run through the WCAG gate ───
def _skip_if_no_temporal(monkeypatch):
    from django.conf import settings
    from temporalio.client import Client

    monkeypatch.setattr(settings, "TEMPORAL_HOST", _TEMPORAL)
    try:
        asyncio.run(Client.connect(_TEMPORAL, namespace="default"))
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"Temporal not reachable at {_TEMPORAL}: {exc}")


def _in_conn(fn):
    from django.db import connection

    try:
        return fn()
    finally:
        connection.close()


async def _poll(fn, *, tries=120, delay=0.2):
    for _ in range(tries):
        if (v := await asyncio.to_thread(fn)):
            return v
        await asyncio.sleep(delay)
    raise AssertionError("condition not met before timeout")


@pytest.mark.usefixtures("real_gate_signal")  # approves a gate on a LOCAL workflow
@pytest.mark.django_db(transaction=True)
def test_acceptance_design_phase_wcag_gate_live(monkeypatch):
    _skip_if_no_temporal(monkeypatch)
    from orchestration import activities
    from orchestration.types import AgentRunInput
    from orchestration.workflows import AgentRunWorkflow

    # Stub the engine: registering the design artifacts is the only thing we fake — the
    # WCAG gate, publish, and transition all run for real.
    def _stub_execute(inp, manifest):
        for art in ["ux_design", "user_journey", "wireframe", "design_system", "accessibility"]:
            tools.register_artifact(inp.tenant_id, inp.project_id, inp.run_id, "ux_design",
                                    art, "internal", f"h-{art}")
        return {"artifact_ids": []}

    monkeypatch.setattr(activities, "execute_agent_core", _stub_execute)

    t, p, story, spec, run = _seed("Live Design Co")
    designer = _member(t, p, "designer")
    wf_id = f"ux-{run.id}"
    run.temporal_workflow_id = wf_id
    _in_conn(lambda: run.save(update_fields=["temporal_workflow_id"]))
    inp = AgentRunInput(run_id=str(run.id), tenant_id=str(t.id), project_id=str(p.id),
                        work_item_id=str(story.id), agent_spec_id=str(spec.id),
                        phase="ux_design", required_role="designer")

    def _pending():
        ap = Approval.objects.filter(run_id=run.id, decision=Approval.Decision.PENDING).first()
        return str(ap.id) if ap else None

    async def _drive():
        from temporalio.client import Client
        from temporalio.worker import Worker

        client = await Client.connect(_TEMPORAL, namespace="default")
        tq = f"p3-accept-{uuid.uuid4()}"
        with ThreadPoolExecutor(max_workers=8) as executor:
            async with Worker(client, task_queue=tq, workflows=[AgentRunWorkflow],
                              activities=activities.ALL_ACTIVITIES, activity_executor=executor):
                h = await client.start_workflow(AgentRunWorkflow.run, inp, id=wf_id, task_queue=tq)
                approval_id = await _poll(_pending)
                # Gate-then-publish: artifacts are still DRAFT while the gate is pending.
                def _none_published():
                    return not Artifact.objects.filter(
                        run_id=run.id, status=Artifact.Status.PUBLISHED).exists()

                assert await asyncio.to_thread(_in_conn, _none_published)
                # WCAG unmet → blocked (no signal sent; the workflow keeps waiting).
                with pytest.raises(GateConditionsError):
                    await asyncio.to_thread(
                        decide_gate, tenant_id=str(t.id), approval_id=approval_id,
                        user_id=str(designer.id), decision="approved")
                # WCAG satisfied → the real gate service signals the workflow to publish.
                # Built in the worker thread with every other database call in this test:
                # since QA-11 the checklist is read from the loaded standard, so listing it is
                # a query, and a query on the event loop is a SynchronousOnlyOperation.
                satisfied = await asyncio.to_thread(_in_conn, _wcag_all_satisfied)
                await asyncio.to_thread(
                    decide_gate, tenant_id=str(t.id), approval_id=approval_id,
                    user_id=str(designer.id), decision="approved", conditions=satisfied)
                return await h.result()

    result = asyncio.run(_drive())
    assert result["status"] == "completed"
    assert _in_conn(lambda: {a.status for a in Artifact.objects.filter(run_id=run.id)}) == \
        {Artifact.Status.PUBLISHED}
    assert _in_conn(lambda: WorkItem.objects.get(id=story.id).state) == WorkItem.State.DONE
