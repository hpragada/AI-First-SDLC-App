"""Bugs S.No 222 — the dashboard's "needs you" tiles must be about the person reading them.

"Gates need your approval" and "Questions awaiting you" counted every pending gate and question on
the project, whoever they were for, while "My runs in flight" beside them was correctly filtered to
the reader. The first tile's subtitle then named the FIRST gate's role — one the reader might not
hold — and both counts stopped at 20, so a busy project under-reported.

The filters are the platform's own rules for who may act, deliberately not a second copy of them:
  * gates — `gate_roles_decidable_by`, the same function `decide_gate` enforces with;
  * questions — project membership, exactly what `answer_clarification` checks. No admin
    fallback, because that function has none.
The last test in each section pins the parity, because a queue that disagrees with the check
behind its own buttons is the bug in a different place.
"""
import pytest
from rest_framework.test import APIClient

from apps.clarifications.models import Clarification
from apps.clarifications.services import ClarificationRoleError, answer_clarification
from apps.gates.models import Approval
from apps.gates.services import GateRoleError, decide_gate, gate_roles_decidable_by
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

PASSWORD = "s3cret-pass!"


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Checkout")
    other = Project.objects.create(tenant=t, name="Billing")
    spec = AgentSpec.objects.create(tenant=t, key="09_testing", body_ref="x")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                 title="Basket totals")
    other_wi = WorkItem.objects.create(tenant=t, project=other, type=WorkItem.Type.STORY,
                                       title="Invoices")

    def user(email, *, role=None, on=project, tenant_admin=False):
        u = User.objects.create_user(email=email, name=email.split("@")[0], tenant=t,
                                     password=PASSWORD, is_tenant_admin=tenant_admin)
        if role:
            Membership.objects.create(tenant=t, user=u, project=on, role=role)
        return u

    def gate(role, *, work_item=wi):
        # One run per gate: a run carries at most one gate of a given type.
        run = Run.objects.create(tenant=t, work_item=work_item, agent_spec=spec,
                                 status=Run.Status.AWAITING_GATE)
        return Approval.objects.create(tenant=t, run=run, work_item=work_item,
                                       gate_type="phase_gate", required_role=role,
                                       decision="pending")

    def question(*, work_item=wi):
        run = Run.objects.create(tenant=t, work_item=work_item, agent_spec=spec,
                                 status=Run.Status.RUNNING)
        return Clarification.objects.create(
            tenant=t, run=run, work_item=work_item, phase="testing", status="pending",
            questions=[{"id": "q1", "text": "Which currency for refunds?", "required": True}])

    w = {
        "t": t, "project": project, "other": other, "spec": spec, "wi": wi,
        "gate": gate, "question": question,
        "qa": user("qa@acme.com", role="qa_lead"),
        "po": user("po@acme.com", role="product_owner"),
        "padmin": user("padmin@acme.com", role="admin"),
        "tadmin": user("tadmin@acme.com", tenant_admin=True),     # a member of nothing
        "outsider": user("out@acme.com", role="qa_lead", on=other),
    }
    w["qa_gate"] = gate("qa_lead")
    w["po_gate"] = gate("product_owner")
    w["arch_gate"] = gate("architect")
    w["elsewhere_gate"] = gate("qa_lead", work_item=other_wi)
    w["q"] = question()
    w["elsewhere_q"] = question(work_item=other_wi)
    return w


def _needs(world, who):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": world[who].email, "password": PASSWORD},
                       format="json").status_code == 200
    r = client.get(f"/api/projects/{world['project'].id}/dashboard/")
    assert r.status_code == 200, r.data
    return r.data["needs_me"]


def _gate_ids(needs):
    return {g["approval_id"] for g in needs["gates"]}


# ── gates ────────────────────────────────────────────────────────────
def test_a_gate_is_listed_only_for_someone_who_may_decide_it(world):
    qa = _needs(world, "qa")
    assert _gate_ids(qa) == {str(world["qa_gate"].id)}
    assert qa["counts"]["gates"] == 1

    po = _needs(world, "po")
    assert _gate_ids(po) == {str(world["po_gate"].id)}
    assert po["counts"]["gates"] == 1


def test_admins_see_every_gate_because_they_may_decide_any(world):
    everything = {str(world[k].id) for k in ("qa_gate", "po_gate", "arch_gate")}
    for who in ("padmin", "tadmin"):
        needs = _needs(world, who)
        assert _gate_ids(needs) == everything, who
        assert needs["counts"]["gates"] == 3, who


def test_another_projects_gate_never_appears(world):
    """`outsider` holds the very role the other project's gate needs — on the other project."""
    needs = _needs(world, "outsider")
    assert needs["gates"] == [] and needs["counts"]["gates"] == 0
    assert str(world["elsewhere_gate"].id) not in _gate_ids(_needs(world, "qa"))


def test_the_queue_offers_exactly_the_gates_decide_gate_would_accept(world):
    """The parity that makes this fix hold: every gate listed is one the Approve button will
    accept from this person, and every gate they could decide is listed."""
    pending = list(Approval.objects.filter(work_item__project=world["project"],
                                           decision="pending"))
    for who in ("qa", "po", "padmin", "tadmin", "outsider"):
        roles = gate_roles_decidable_by(tenant_id=world["t"].id, user_id=world[who].id,
                                        project_id=world["project"].id)
        decidable = {str(a.id) for a in pending if roles is None or a.required_role in roles}
        assert _gate_ids(_needs(world, who)) == decidable, who


def test_the_gate_service_still_refuses_the_gates_the_queue_hides(world):
    with pytest.raises(GateRoleError):
        decide_gate(tenant_id=str(world["t"].id), approval_id=str(world["qa_gate"].id),
                    user_id=str(world["po"].id), decision="approved",
                    signal_sender=lambda *a, **k: None)


def test_decidable_roles(world):
    def roles(who):
        return gate_roles_decidable_by(tenant_id=world["t"].id, user_id=world[who].id,
                                       project_id=world["project"].id)

    assert roles("qa") == frozenset({"qa_lead"})
    assert roles("padmin") is None        # project admin: any gate
    assert roles("tadmin") is None        # tenant admin: any gate, member or not
    assert roles("outsider") == frozenset()


# ── questions ────────────────────────────────────────────────────────
def test_questions_are_listed_for_the_projects_members(world):
    for who in ("qa", "po", "padmin"):
        needs = _needs(world, who)
        assert [c["id"] for c in needs["clarifications"]] == [str(world["q"].id)], who
        assert needs["counts"]["clarifications"] == 1, who


def test_a_non_member_is_not_shown_a_question_they_would_be_refused_on(world):
    """A tenant admin may decide any GATE, but `answer_clarification` has no admin fallback — so
    listing a question for them would invite an answer the platform then refuses."""
    needs = _needs(world, "tadmin")
    assert needs["clarifications"] == [] and needs["counts"]["clarifications"] == 0
    with pytest.raises(ClarificationRoleError):
        answer_clarification(tenant_id=str(world["t"].id), clarification_id=str(world["q"].id),
                             user_id=str(world["tadmin"].id), answers={"q1": "EUR"})


def test_another_projects_question_never_appears(world):
    ids = [c["id"] for c in _needs(world, "qa")["clarifications"]]
    assert str(world["elsewhere_q"].id) not in ids
    assert _needs(world, "outsider")["clarifications"] == []


# ── the numbers ──────────────────────────────────────────────────────
def test_the_counts_are_true_when_the_lists_are_trimmed(world):
    for _ in range(24):
        world["gate"]("qa_lead")
    for _ in range(22):
        world["question"]()

    needs = _needs(world, "qa")
    assert len(needs["gates"]) == 20 and needs["counts"]["gates"] == 25
    assert len(needs["clarifications"]) == 20 and needs["counts"]["clarifications"] == 23


def test_my_runs_count_is_true_too(world):
    for _ in range(12):
        Run.objects.create(tenant=world["t"], work_item=world["wi"], agent_spec=world["spec"],
                           status=Run.Status.RUNNING, triggered_by=world["qa"])

    needs = _needs(world, "qa")
    assert len(needs["my_runs"]) == 10 and needs["counts"]["my_runs"] == 12
    assert _needs(world, "po")["counts"]["my_runs"] == 0


def test_the_queue_is_worked_oldest_first(world):
    later = world["gate"]("qa_lead")
    ids = [g["approval_id"] for g in _needs(world, "qa")["gates"]]
    assert ids == [str(world["qa_gate"].id), str(later.id)]


# ── what each row CALLS its work item (P2) ───────────────────────────
# Every row named its work item by the first eight characters of an internal id — "Merge gate ·
# 3f2a9c1b" — on the first screen a client reads each morning. That string matches nothing they
# can search for, quote in a meeting, or recognise anywhere else in the product, and the run rows
# printed one twice. The number and title now travel with each row.
def test_every_row_carries_its_work_items_number_and_title(world):
    Run.objects.create(tenant=world["t"], work_item=world["wi"], agent_spec=world["spec"],
                       status=Run.Status.RUNNING, triggered_by=world["qa"])
    needs = _needs(world, "qa")
    wi = world["wi"]
    assert wi.key == "WI-1" and wi.title == "Basket totals"

    rows = needs["gates"] + needs["clarifications"] + needs["my_runs"]
    assert len(rows) == 3
    for row in rows:
        assert row["work_item_key"] == wi.key
        assert row["work_item_title"] == wi.title
        # The id is still there for links; it is simply no longer what the row is CALLED.
        assert row["work_item"] == str(wi.id)


def test_a_run_row_says_how_long_it_has_been_going(world):
    """In place of reprinting an id: "started 6m ago" is what the reader wanted from that space."""
    Run.objects.create(tenant=world["t"], work_item=world["wi"], agent_spec=world["spec"],
                       status=Run.Status.RUNNING, triggered_by=world["qa"])
    row = _needs(world, "qa")["my_runs"][0]
    assert row["started_s"] >= 0
    assert row["phase"] == "09_testing"
