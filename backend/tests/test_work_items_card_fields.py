"""P4.8-T1 bucket-B gaps A/B (screen-audit) — closed while wiring the Phase 4.8 UI to live
data: `PATCH /api/work-items/{id}/` (title/description/type only, S-15/S-16 "Edit"), the
`type`/`parent` list filters (S-14 board level filter, S-23 fan-out), and the
`artifact_count`/`owner`/`needs` card fields the board/detail screens render — none of which
the `WorkItemViewSet` actually served despite the frontend already sending/expecting them.
"""
from datetime import UTC, datetime

import pytest
from rest_framework.test import APIClient

from apps.clarifications.models import Clarification
from apps.gates.models import Approval
from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


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
def dev(tenant, project):
    u = User.objects.create_user(
        email="dev@acme.com", name="Dev Patel", tenant=tenant, password="dev-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


@pytest.fixture
def epic(tenant, project, dev):
    return WorkItem.objects.create(
        tenant=tenant, project=project, type="epic", title="Stripe Webhook Integration",
        feature_stream="payments", assignee=dev,
    )


def _agent_spec(tenant, key="04_architecture"):
    return AgentSpec.objects.create(tenant=tenant, key=key, body_ref=f"agents/{key}.md")


def _run(tenant, work_item, agent_spec, **kwargs):
    return Run.objects.create(
        tenant=tenant, work_item=work_item, agent_spec=agent_spec, **kwargs)


def _created_at(run, when):
    """Stamp a run's creation time.

    `created_at` is `auto_now_add`, so it cannot be passed to `create()` — and on a coarse system
    clock two runs made back to back land on the SAME timestamp, which left "the item's latest
    run" a coin toss and this file's phase assertions intermittently red. Saying when each run
    happened is what makes these tests about recency rather than about luck.
    """
    Run.objects.filter(id=run.id).update(created_at=when)
    return run


def _list(client, tenant, project):
    return client.get(
        "/api/work-items/", {"project": str(project.id)}, HTTP_X_TENANT_ID=str(tenant.id)
    )


def test_patch_updates_title_description_type_only(client, tenant, project, dev, epic):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.patch(
        f"/api/work-items/{epic.id}/",
        {"title": "Renamed", "description": "New desc", "type": "story",
         "state": "done", "takeover_flag": True},
        format="json", HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    epic.refresh_from_db()
    assert epic.title == "Renamed"
    assert epic.description == "New desc"
    assert epic.type == "story"
    # Not patchable via this endpoint — untouched.
    assert epic.state == "proposed"
    assert epic.takeover_flag is False


def test_type_filter(client, tenant, project, dev, epic):
    task = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Sub-task", parent=epic
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(
        "/api/work-items/", {"project": str(project.id), "type": "task"},
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.data}
    assert ids == {str(task.id)}


def test_parent_filter_returns_children(client, tenant, project, dev, epic):
    child1 = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Task 1", parent=epic
    )
    child2 = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Task 2", parent=epic
    )
    WorkItem.objects.create(tenant=tenant, project=project, type="task", title="Unrelated")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(
        "/api/work-items/", {"project": str(project.id), "parent": str(epic.id)},
        HTTP_X_TENANT_ID=str(tenant.id),
    )
    assert resp.status_code == 200
    ids = {row["id"] for row in resp.data}
    assert ids == {str(child1.id), str(child2.id)}


def test_artifact_count_and_owner_on_list_and_retrieve(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Artifact.objects.create(tenant=tenant, project=project, run=run, phase="04_architecture",
                            type="architecture_doc", status="draft", version=1)
    Artifact.objects.create(tenant=tenant, project=project, run=run, phase="04_architecture",
                            type="architecture_doc", status="draft", version=2)
    _login(client, "dev@acme.com", "dev-pass!")

    list_resp = _list(client, tenant, project)
    row = next(r for r in list_resp.data if r["id"] == str(epic.id))
    assert row["artifact_count"] == 2
    assert row["owner"] == "Dev Patel"

    detail_resp = client.get(f"/api/work-items/{epic.id}/", HTTP_X_TENANT_ID=str(tenant.id))
    assert detail_resp.data["artifact_count"] == 2
    assert detail_resp.data["owner"] == "Dev Patel"


def test_current_phase_is_latest_runs_phase(client, tenant, project, dev, epic):
    """Bugs.xlsx rows 49/50: the board/list 'Phase' must be the item's actual lifecycle
    phase (latest run's agent), not the feature stream; empty when nothing has run."""
    spec_arch = _agent_spec(tenant, "04_architecture")
    spec_prd = AgentSpec.objects.create(tenant=tenant, key="03_prd", body_ref="agents/03.md")
    _created_at(_run(tenant, epic, spec_prd), datetime(2026, 9, 1, tzinfo=UTC))    # older
    _created_at(_run(tenant, epic, spec_arch), datetime(2026, 9, 2, tzinfo=UTC))   # newest
    fresh = WorkItem.objects.create(tenant=tenant, project=project, type="task", title="New")
    _login(client, "dev@acme.com", "dev-pass!")

    resp = _list(client, tenant, project)
    by_id = {r["id"]: r for r in resp.data}
    assert by_id[str(epic.id)]["current_phase"] == "04_architecture"
    assert by_id[str(fresh.id)]["current_phase"] == ""   # no runs yet


def test_run_status_travels_with_the_current_phase(client, tenant, project, dev, epic):
    """Bugs S.No 117: the board placed a card by its latest run's phase and then never said what
    that phase was doing, so running, waiting and failed all looked the same. The status comes off
    the SAME run the phase does, so the two can never describe different runs."""
    spec_prd = AgentSpec.objects.create(tenant=tenant, key="03_prd", body_ref="agents/03.md")
    spec_arch = _agent_spec(tenant, "04_architecture")
    _created_at(_run(tenant, epic, spec_prd, status=Run.Status.COMPLETED),
                datetime(2026, 9, 1, tzinfo=UTC))                            # older
    _created_at(_run(tenant, epic, spec_arch, status=Run.Status.FAILED),
                datetime(2026, 9, 2, tzinfo=UTC))                            # newest
    fresh = WorkItem.objects.create(tenant=tenant, project=project, type="task", title="New")
    _login(client, "dev@acme.com", "dev-pass!")

    by_id = {r["id"]: r for r in _list(client, tenant, project).data}
    assert by_id[str(epic.id)]["current_phase"] == "04_architecture"
    assert by_id[str(epic.id)]["run_status"] == "failed"
    # Nothing has run: no phase and no status — the board's Backlog column, "Not started".
    assert by_id[str(fresh.id)]["current_phase"] == ""
    assert by_id[str(fresh.id)]["run_status"] == ""

    detail = client.get(f"/api/work-items/{epic.id}/", HTTP_X_TENANT_ID=str(tenant.id))
    assert detail.data["run_status"] == "failed"


def test_needs_reflects_pending_clarification_over_gate(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Approval.objects.create(tenant=tenant, run=run, work_item=epic, gate_type="architecture",
                            required_role="architect", decision="pending")
    Clarification.objects.create(tenant=tenant, run=run, work_item=epic, phase="04_architecture",
                                 status="pending", questions=[{"id": "q1", "text": "?"}])
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    # `yours` is True because answering a question needs project membership and nothing more —
    # exactly what `answer_clarification` checks. Dev is a member.
    assert row["needs"] == {"clarification": True, "label": "Needs answer", "yours": True}


def test_needs_reflects_pending_gate_when_no_clarification(client, tenant, project, dev, epic):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Approval.objects.create(tenant=tenant, run=run, work_item=epic, gate_type="architecture",
                            required_role="architect", decision="pending")
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    # Humanised gate label (Bugs.xlsx rows 54-58): capitalised, single "gate". `yours` is False:
    # Dev is a tech lead, and this gate needs an architect — the board used to tell them it was
    # "Waiting for you" and the Approve button then refused them.
    assert row["needs"] == {"gate": True, "label": "Architecture gate", "yours": False}


# ── who a waiting card is actually waiting on (S.No 117 follow-up) ──────────────
def _pending_gate(tenant, project, epic, required_role):
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    return Approval.objects.create(
        tenant=tenant, run=run, work_item=epic, gate_type=required_role,
        required_role=required_role, decision="pending",
    )


def test_gate_is_yours_when_you_hold_the_role_it_needs(client, tenant, project, dev, epic):
    _pending_gate(tenant, project, epic, "tech_lead")
    _login(client, "dev@acme.com", "dev-pass!")
    row = next(r for r in _list(client, tenant, project).data if r["id"] == str(epic.id))
    assert row["needs"]["yours"] is True


def test_an_admin_may_decide_any_gate_so_every_gate_is_theirs(client, tenant, project, epic):
    """The platform lets a project admin or a tenant admin decide any gate, so hiding those
    behind the neutral wording would understate work that genuinely is theirs."""
    boss = User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant, password="boss-pass!",
        is_tenant_admin=True,
    )
    Membership.objects.create(tenant=tenant, user=boss, project=project, role="product_owner")
    _pending_gate(tenant, project, epic, "security_engineer")
    _login(client, "boss@acme.com", "boss-pass!")
    row = next(r for r in _list(client, tenant, project).data if r["id"] == str(epic.id))
    assert row["needs"]["yours"] is True


def test_a_question_is_not_yours_without_membership(client, tenant, project, dev, epic):
    """A tenant admin who is not on the project may not answer its questions — that function
    has no admin fallback — so the card must not claim the question is theirs."""
    spec = _agent_spec(tenant)
    run = _run(tenant, epic, spec)
    Clarification.objects.create(tenant=tenant, run=run, work_item=epic, phase="04_architecture",
                                 status="pending", questions=[{"id": "q1", "text": "?"}])
    outsider = User.objects.create_user(
        email="outsider@acme.com", name="Outsider", tenant=tenant, password="out-pass!",
        is_tenant_admin=True,
    )
    assert not Membership.objects.filter(user=outsider, project=project).exists()
    _login(client, "outsider@acme.com", "out-pass!")
    row = next(r for r in _list(client, tenant, project).data if r["id"] == str(epic.id))
    assert row["needs"] == {"clarification": True, "label": "Needs answer", "yours": False}


def test_needs_is_none_when_nothing_pending(client, tenant, project, dev, epic):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = _list(client, tenant, project)
    row = next(r for r in resp.data if r["id"] == str(epic.id))
    assert row["needs"] is None
    assert row["artifact_count"] == 0


def test_card_fields_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    u1 = User.objects.create_user(email="a@acme.com", name="A", tenant=t1, password="pw!")
    Membership.objects.create(tenant=t1, user=u1, project=p1, role="engineer")
    wi1 = WorkItem.objects.create(tenant=t1, project=p1, type="epic", title="E1")
    WorkItem.objects.create(tenant=t2, project=p2, type="epic", title="E2")

    _login(client, "a@acme.com", "pw!")
    resp = client.get("/api/work-items/", {"project": str(p1.id)}, HTTP_X_TENANT_ID=str(t1.id))
    assert resp.status_code == 200
    assert {r["id"] for r in resp.data} == {str(wi1.id)}


# -- parent_key: the UI must never have to draw a UUID (2026-09-30) -------------
#
# `key` has always been on this serializer, with the comment "so the UI never has to show the
# UUID". The PARENT had no such field, so every screen naming the parent had only `parent` - a
# UUID - and drew it: the board card's chip printed all 36 characters, and the task and defect
# breadcrumbs printed the first eight and called it a link.
def test_parent_key_is_the_parents_human_key(client, tenant, project, dev, epic):
    task = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Sub-task", parent=epic
    )
    _login(client, "dev@acme.com", "dev-pass!")

    resp = _list(client, tenant, project)

    assert resp.status_code == 200
    row = next(r for r in resp.data if r["id"] == str(task.id))
    assert row["parent_key"] == epic.key
    assert row["parent_key"].startswith("WI-")
    # The raw parent id is still served - screens navigate by it - but it is not what they draw.
    # `str()` because this is the pre-render payload, where a UUID field is still a UUID object.
    assert str(row["parent"]) == str(epic.id)


def test_parent_key_is_null_without_a_parent(client, tenant, project, dev, epic):
    _login(client, "dev@acme.com", "dev-pass!")

    resp = _list(client, tenant, project)

    row = next(r for r in resp.data if r["id"] == str(epic.id))
    assert row["parent_key"] is None


def test_parent_key_is_served_on_retrieve_too(client, tenant, project, dev, epic):
    """The breadcrumb that showed a UUID is on the DETAIL screen, so the field has to reach it -
    the detail path builds its payload separately from the list one."""
    task = WorkItem.objects.create(
        tenant=tenant, project=project, type="task", title="Sub-task", parent=epic
    )
    _login(client, "dev@acme.com", "dev-pass!")

    resp = client.get(f"/api/work-items/{task.id}/", HTTP_X_TENANT_ID=str(tenant.id))

    assert resp.status_code == 200
    assert resp.data["parent_key"] == epic.key


def test_parent_key_costs_no_query_per_card(client, tenant, project, dev, epic,
                                            django_assert_max_num_queries):
    """The reason `WorkItemViewSet` selects the parent, pinned so it cannot be quietly dropped.

    Reading `obj.parent.key` per row is one extra query per card, and this endpoint returns a
    whole project's backlog in a single response - there is no pagination on the board. Ten
    children here; the ceiling is set well below "a query each" so the test fails loudly if the
    select_related goes but does not break on an unrelated extra query elsewhere."""
    for i in range(10):
        WorkItem.objects.create(
            tenant=tenant, project=project, type="task", title=f"Task {i}", parent=epic
        )
    _login(client, "dev@acme.com", "dev-pass!")

    with django_assert_max_num_queries(15):
        resp = _list(client, tenant, project)

    assert resp.status_code == 200
    assert len(resp.data) == 11
    assert all(r["parent_key"] == epic.key for r in resp.data if r["id"] != str(epic.id))
