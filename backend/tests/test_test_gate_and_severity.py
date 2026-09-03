"""P3 — the test gate's blocking-test rule (§5/D9) + defect severity from TC priority.

- **Blocking-test rule:** "a failing blocking test cannot be gated past until its defect is
  resolved or quarantined" (§5) — a **derived** condition on the qa_lead Approval. The
  platform evaluates it from the defect loopback's own open/close state, so (unlike the
  reviewer-attested WCAG checklist) a reviewer cannot tick past a red suite.
- **Severity:** a failing test's defect inherits the test case's Priority (09 Step 10),
  instead of every failure — however trivial — opening a Critical.
"""
import pytest
from mcp_platform_state import tools

from apps.gates.conditions import conditions_for_phase
from apps.gates.models import Approval
from apps.gates.services import GateConditionsError, decide_gate
from apps.gates.testgate import BLOCKING_TESTS_KEY
from apps.projects.models import Project
from apps.quality import services
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from orchestration.activities import open_gate_core
from orchestration.types import AgentRunInput


class _Recorder:
    def __init__(self):
        self.calls = []

    def __call__(self, workflow_id, decision, approver_id, comment, revise=False):
        self.calls.append((workflow_id, decision, approver_id, comment))


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                    feature_stream="ST-1", title="Login")
    spec = AgentSpec.objects.create(tenant=t, key="09_testing", body_ref="x",
                                    phase_label="testing")
    run = Run.objects.create(tenant=t, work_item=story, agent_spec=spec,
                             temporal_workflow_id="wf-t")
    qa = User.objects.create_user(email="qa@acme.test", name="Carlos", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=qa, project=project, role="qa_lead")
    return {"t": t, "project": project, "story": story, "run": run, "qa_id": str(qa.id)}


def _inp(world, phase="testing"):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["story"].id),
        agent_spec_id="s", phase=phase, required_role="qa_lead",
    )


def _import(world, results):
    return services.import_test_results(
        tenant_id=world["t"].id, project_id=world["project"].id,
        work_item_id=world["story"].id, run_id=world["run"].id, results=results,
    )


def _approve(world, approval_id, sender, **kw):
    return decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                       user_id=world["qa_id"], decision="approved",
                       signal_sender=sender, **kw)


# ── seeding ─────────────────────────────────────────────────────────
def test_conditions_for_phase_seeds_blocking_test_rule_only_for_testing(db):
    """`db` since QA-11: the design phase's WCAG checklist is now read from the loaded
    standard, so the last assertion below touches the database."""
    testing = conditions_for_phase("testing")
    # QA-15 added a second derived condition here (the accessibility rule), so this asserts the
    # blocking-test rule is present and correctly shaped rather than that it is the only one.
    rule = next(c for c in testing if c["key"] == BLOCKING_TESTS_KEY)
    assert rule["required"] and rule["derived"] and not rule["satisfied"]
    assert conditions_for_phase("prd") == []
    # The design gate keeps its reviewer-attested WCAG checklist and gains no test rule.
    assert BLOCKING_TESTS_KEY not in {c["key"] for c in conditions_for_phase("ux_design")}


def test_open_gate_core_seeds_the_blocking_test_condition(world):
    approval = Approval.objects.get(id=open_gate_core(_inp(world)))
    # Since QA-15 the testing gate also carries the accessibility rule; this test owns the
    # blocking-test one, and `test_a11y_gate.py` owns the other.
    assert BLOCKING_TESTS_KEY in {c["key"] for c in approval.conditions}


def test_a_non_test_phase_gate_carries_no_test_condition(world):
    """An open test defect must never hold a different phase's gate shut."""
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    approval = Approval.objects.get(id=open_gate_core(_inp(world, phase="prd")))
    assert approval.conditions == []


# ── enforcement ─────────────────────────────────────────────────────
def test_open_test_defect_blocks_the_qa_gate(world):
    _import(world, [{"test_ref": "TC-9", "status": "FAIL", "evidence": "boom"}])
    approval_id = open_gate_core(_inp(world))
    sender = _Recorder()

    # The error names the test holding the gate shut — a blocked approve persists nothing,
    # so this message is the reviewer's only account of why.
    with pytest.raises(GateConditionsError, match="TC-9"):
        _approve(world, approval_id, sender)
    approval = Approval.objects.get(id=approval_id)
    assert approval.decision == Approval.Decision.PENDING
    assert approval.conditions[0]["satisfied"] is False
    assert sender.calls == []                       # the workflow is never resumed


def test_gate_opens_once_the_failing_test_passes(world):
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    approval_id = open_gate_core(_inp(world))
    sender = _Recorder()
    with pytest.raises(GateConditionsError):
        _approve(world, approval_id, sender)

    _import(world, [{"test_ref": "TC-9", "status": "PASS"}])   # the loopback closes the defect
    result = _approve(world, approval_id, sender)
    assert result["decision"] == "approved"
    assert result["conditions"][0]["satisfied"] is True
    assert "detail" not in result["conditions"][0]
    assert sender.calls and sender.calls[0][1] == "approved"


def test_reviewer_cannot_attest_the_derived_condition(world):
    """The whole point of a derived condition: a qa_lead ticking "no failing tests" while a
    test is failing must NOT open the gate. The platform's finding beats the reviewer's claim."""
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    approval_id = open_gate_core(_inp(world))
    sender = _Recorder()

    with pytest.raises(GateConditionsError):
        _approve(world, approval_id, sender,
                 conditions=[{"key": BLOCKING_TESTS_KEY, "satisfied": True}])
    approval = Approval.objects.get(id=approval_id)
    assert approval.decision == Approval.Decision.PENDING
    assert approval.conditions[0]["satisfied"] is False       # the tick did not stick
    assert sender.calls == []


def test_rejecting_is_never_blocked_by_the_condition(world):
    """A red suite must not trap the gate: the reviewer can always reject."""
    _import(world, [{"test_ref": "TC-9", "status": "FAIL"}])
    approval_id = open_gate_core(_inp(world))
    result = decide_gate(tenant_id=str(world["t"].id), approval_id=approval_id,
                         user_id=world["qa_id"], decision="rejected",
                         signal_sender=_Recorder())
    assert result["decision"] == "rejected"


def test_quarantined_flaky_test_does_not_block_the_gate(world):
    """D9's escape hatch: a test that flips within one execution is quarantined, opens no
    defect, and so never holds the gate shut."""
    out = _import(world, [{"test_ref": "T1", "status": "PASS"},
                          {"test_ref": "T1", "status": "FAIL"}])
    assert out["flaky"] == ["T1"] and out["defects_opened"] == []
    approval_id = open_gate_core(_inp(world))
    assert _approve(world, approval_id, _Recorder())["decision"] == "approved"


def test_security_defects_do_not_block_the_test_gate(world):
    """Security findings gate the security phase (D8), not this one — they carry `finding`,
    not `test_ref`."""
    services.record_security_findings(
        tenant_id=world["t"].id, project_id=world["project"].id,
        work_item_id=world["story"].id,
        findings=[{"id": "SEC-1", "severity": "critical", "title": "SQLi"}],
    )
    approval_id = open_gate_core(_inp(world))
    assert _approve(world, approval_id, _Recorder())["decision"] == "approved"


# ── defect severity = the test case's Priority (09 Step 10) ─────────
def _register_case(world, *, title, external_ref):
    return tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "testing", "test_case",
        "internal", "h", external_ref=external_ref, title=title,
    )


def _severity_of(world, test_ref):
    defect = WorkItem.objects.get(parent_id=world["story"].id, type=WorkItem.Type.DEFECT,
                                  external_ref__test_ref=test_ref)
    return defect.external_ref["severity"]


def test_defect_severity_comes_from_structured_test_case_priority(world):
    _register_case(world, title="TC-7 — Footer copyright year",
                   external_ref={"tc_id": "TC-7", "priority": "Low"})
    _import(world, [{"test_ref": "TC-7", "status": "FAIL"}])
    assert _severity_of(world, "TC-7") == "low"      # was: every failure opened a Critical


def test_defect_severity_read_from_the_test_case_body(world):
    _register_case(world, title="TC-8 — Checkout totals",
                   external_ref={"tc_id": "TC-8",
                                 "body": "## TC-8\n**Priority:** Medium\n**Type:** E2E\n"})
    _import(world, [{"test_ref": "TC-8", "status": "FAIL"}])
    assert _severity_of(world, "TC-8") == "medium"


def test_defect_severity_matches_the_sor_key_after_export(world):
    """Once the test case is exported, results come back keyed by the SoR issue key."""
    _register_case(world, title="TC-9 — Login rejects a bad password",
                   external_ref={"tc_id": "TC-9", "priority": "critical",
                                 "export": {"sor": "xray", "id": "PROJ-42"}})
    _import(world, [{"test_ref": "PROJ-42", "status": "FAIL"}])
    assert _severity_of(world, "PROJ-42") == "critical"


def test_unknown_test_case_stays_critical_fail_safe(world):
    """A result naming no registered case is never silently downgraded."""
    _import(world, [{"test_ref": "TC-404", "status": "FAIL"}])
    assert _severity_of(world, "TC-404") == "critical"


def test_title_match_is_word_bounded(world):
    """TC-1 must not inherit TC-14's priority."""
    _register_case(world, title="TC-14 — Bulk import", external_ref={"priority": "low"})
    _import(world, [{"test_ref": "TC-1", "status": "FAIL"}])
    assert _severity_of(world, "TC-1") == "critical"   # no match → fail-safe, not TC-14's low
