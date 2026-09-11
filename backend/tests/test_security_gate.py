"""Security gate — open Critical/High findings block the approval (Bugs S.No 178).

The Security agent's contract says its gate must not be grantable while a Critical or High
finding is open. **No such rule existed**: `conditions_for_phase` contributed conditions for the
design, testing, accessibility and readiness gates and nothing at all for security, so the only
thing between an open Critical and a passed gate was a reviewer reading carefully.

Derived, like the blocking-test rule — the platform evaluates it from live state at decide time,
so a reviewer can never tick past it. It reads the security defect loopback's own reconciliation,
so the gate and the defect board can never disagree.

Also covers the two things that fix had to carry to be complete:
  - a gate that was already open when the rule shipped is topped up, or the rule would guard
    only future gates and leave every pending one approvable with Criticals open;
  - the read path (`current_conditions`, behind `GET /approvals/{id}/criteria/`) agrees with the
    decide path, or Approve is greyed out on a gate the platform would happily let through.
"""
import pytest

from apps.gates.conditions import conditions_for_phase, derived_evaluators
from apps.gates.models import Approval
from apps.gates.securitygate import SECURITY_GATE_KEY
from apps.gates.services import GateConditionsError, current_conditions, decide_gate
from apps.projects.models import Project
from apps.quality.services import record_security_findings
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


# ── seeding (pure) ──────────────────────────────────────────────────
def test_the_security_rule_is_seeded_only_for_the_security_phase():
    keys = {c["key"] for c in conditions_for_phase("security")}
    assert SECURITY_GATE_KEY in keys
    assert SECURITY_GATE_KEY not in {c["key"] for c in conditions_for_phase("testing")}
    assert conditions_for_phase("prd") == []


def test_the_security_rule_has_a_registered_evaluator():
    """A derived condition is seeded unsatisfied and no human may attest it, so one with no
    evaluator is a gate nobody could ever approve."""
    assert SECURITY_GATE_KEY in derived_evaluators()


def test_the_security_rule_is_derived_not_reviewer_attested():
    rule = next(c for c in conditions_for_phase("security") if c["key"] == SECURITY_GATE_KEY)
    assert rule["derived"] is True and rule["required"] is True and rule["satisfied"] is False


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                 title="Checkout")
    spec = AgentSpec.objects.create(tenant=t, key="10_security", body_ref="x",
                                    phase_label="security")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec,
                             temporal_workflow_id="wf-sec-1")
    engineer = User.objects.create_user(email="sec@acme.test", name="Sec", tenant=t,
                                        password="pw")
    Membership.objects.create(tenant=t, user=engineer, project=project,
                              role="security_engineer")
    return {"t": t, "project": project, "wi": wi, "run": run, "user_id": str(engineer.id)}


def _inp(world, phase="security"):
    return AgentRunInput(
        run_id=str(world["run"].id), tenant_id=str(world["t"].id),
        project_id=str(world["project"].id), work_item_id=str(world["wi"].id),
        agent_spec_id=str(world["run"].agent_spec_id), phase=phase,
        required_role="security_engineer",
    )


def _raise_finding(world, *, fid="SEC-001", severity="critical", title="SQL injection in login"):
    return record_security_findings(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        work_item_id=str(world["wi"].id),
        findings=[{"id": fid, "severity": severity, "title": title}],
    )


def _decide(world, approval_id, sender, **over):
    kwargs = dict(tenant_id=str(world["t"].id), approval_id=approval_id,
                  user_id=world["user_id"], decision="approved", signal_sender=sender)
    kwargs.update(over)
    return decide_gate(**kwargs)


# ── the gate itself ─────────────────────────────────────────────────
def test_open_gate_core_seeds_the_security_rule(world):
    approval = Approval.objects.get(id=open_gate_core(_inp(world)))
    assert SECURITY_GATE_KEY in {c["key"] for c in approval.conditions}


def test_the_gate_cannot_be_approved_while_a_critical_is_open(world):
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world)
    sender = _Recorder()

    with pytest.raises(GateConditionsError):
        _decide(world, approval_id, sender)

    assert Approval.objects.get(id=approval_id).decision == Approval.Decision.PENDING
    assert sender.calls == []


def test_a_high_blocks_the_gate_too_and_a_low_does_not(world):
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world, fid="SEC-002", severity="high", title="Missing rate limit on login")
    sender = _Recorder()
    with pytest.raises(GateConditionsError):
        _decide(world, approval_id, sender)

    # A Low never opens a defect at all, so it never reaches this gate.
    _raise_finding(world, fid="SEC-002", severity="high", title="Missing rate limit on login")
    _raise_finding(world, fid="SEC-009", severity="low", title="Verbose error page")
    assert WorkItem.objects.filter(parent_id=world["wi"].id,
                                   type=WorkItem.Type.DEFECT).count() == 1


def test_resolving_the_finding_clears_the_block_with_no_manual_step(world):
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world)
    sender = _Recorder()
    with pytest.raises(GateConditionsError):
        _decide(world, approval_id, sender)

    # A later security run reports the finding gone — the loopback closes its defect.
    record_security_findings(
        tenant_id=str(world["t"].id), project_id=str(world["project"].id),
        work_item_id=str(world["wi"].id), findings=[],
    )

    result = _decide(world, approval_id, sender)
    assert result["decision"] == "approved"
    rule = next(c for c in result["conditions"] if c["key"] == SECURITY_GATE_KEY)
    assert rule["satisfied"] is True and "detail" not in rule
    assert sender.calls and sender.calls[0][1] == "approved"


def test_a_clean_security_run_approves_straight_through(world):
    approval_id = open_gate_core(_inp(world))
    assert _decide(world, approval_id, _Recorder())["decision"] == "approved"


def test_a_cancelled_defect_releases_the_gate(world):
    """S.No 140's rule, inherited: a defect nobody will fix must not hold a story shut for ever.
    The acknowledgement condition on the approval is what makes that safe."""
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world)
    defect = WorkItem.objects.get(parent_id=world["wi"].id, type=WorkItem.Type.DEFECT)
    defect.state = WorkItem.State.CANCELLED
    defect.save(update_fields=["state"])

    assert _decide(world, approval_id, _Recorder())["decision"] == "approved"


# ── what the reviewer is told ───────────────────────────────────────
def test_the_reason_names_the_finding_in_plain_language_never_its_id(world):
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world, fid="SEC-001", severity="critical",
                   title="SQL injection in the login form")

    with pytest.raises(GateConditionsError) as exc:
        _decide(world, approval_id, _Recorder())

    message = str(exc.value)
    assert "SQL injection in the login form" in message
    assert "Critical" in message
    assert "SEC-001" not in message, "a finding id is not something a reviewer can act on"


def test_a_finding_the_review_never_titled_says_so_rather_than_printing_its_id(world):
    approval_id = open_gate_core(_inp(world))
    _raise_finding(world, fid="SEC-007", title="")     # falls back to the id for the item's name

    with pytest.raises(GateConditionsError) as exc:
        _decide(world, approval_id, _Recorder())

    assert "SEC-007" not in str(exc.value)
    assert "recorded no title" in str(exc.value)


# ── gates that predate the rule ─────────────────────────────────────
def test_a_gate_opened_before_the_rule_existed_is_still_guarded(world):
    """Conditions are seeded once, at gate creation. Without the top-up the rule would guard
    every FUTURE security gate and leave every pending one approvable with Criticals open."""
    approval_id = open_gate_core(_inp(world))
    Approval.objects.filter(id=approval_id).update(conditions=[])    # as it was before the fix
    _raise_finding(world)

    with pytest.raises(GateConditionsError):
        _decide(world, approval_id, _Recorder())


def test_the_top_up_never_disturbs_what_a_reviewer_already_attested(world):
    approval_id = open_gate_core(_inp(world))
    Approval.objects.filter(id=approval_id).update(conditions=[
        {"key": "a_reviewer_item", "label": "Checked by hand", "required": True,
         "satisfied": True},
    ])

    approval = Approval.objects.select_related("work_item", "run", "run__agent_spec").get(
        id=approval_id)
    conditions = current_conditions(approval, tenant_id=str(world["t"].id))

    attested = next(c for c in conditions if c["key"] == "a_reviewer_item")
    assert attested["satisfied"] is True
    assert SECURITY_GATE_KEY in {c["key"] for c in conditions}


def test_a_reviewer_attested_checklist_is_never_topped_up(world):
    """Only derived rules are topped up. Adding a human checklist to a gate already pending
    would confront a reviewer with questions they were never shown, and the platform has no
    honest way to answer those for them."""
    spec = AgentSpec.objects.create(tenant=world["t"], key="12_deployment", body_ref="x",
                                    phase_label="deployment")
    run = Run.objects.create(tenant=world["t"], work_item=world["wi"], agent_spec=spec,
                             temporal_workflow_id="wf-dep-1")
    approval = Approval.objects.create(
        tenant=world["t"], run=run, work_item=world["wi"], required_role="devops",
        decision=Approval.Decision.PENDING, conditions=[],
    )
    approval = Approval.objects.select_related("work_item", "run", "run__agent_spec").get(
        id=approval.id)

    assert current_conditions(approval, tenant_id=str(world["t"].id)) == []


# ── the read path agrees with the decide path ───────────────────────
def test_the_checklist_a_reviewer_reads_is_the_one_that_is_enforced(world):
    """Straight off the stored column a derived rule always reads unsatisfied, because it is
    seeded that way and only recomputed at decide time — which greys out Approve on a gate the
    platform would let through."""
    approval_id = open_gate_core(_inp(world))
    approval = Approval.objects.select_related("work_item", "run", "run__agent_spec").get(
        id=approval_id)

    stored = next(c for c in approval.conditions if c["key"] == SECURITY_GATE_KEY)
    live = next(c for c in current_conditions(approval, tenant_id=str(world["t"].id))
                if c["key"] == SECURITY_GATE_KEY)

    assert stored["satisfied"] is False          # nothing has recomputed it yet
    assert live["satisfied"] is True             # …and nothing is actually blocking
