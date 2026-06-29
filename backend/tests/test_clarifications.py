"""Clarification — the control-plane interactive Q&A object + answer flow (req #2).

Covers the answer service (membership check, required-answer validation, idempotency,
event log), the REST surface (list/filter + answer, 403/400 paths), and RLS tenant
isolation (mirrors test_rls — proves a tenant only ever sees its own clarifications).
"""
import uuid

import psycopg
import pytest
from django.conf import settings
from django.db import connection
from rest_framework.test import APIClient

from apps.clarifications.models import Clarification
from apps.clarifications.services import (
    ClarificationError,
    ClarificationRoleError,
    answer_clarification,
    create_clarification,
    get_clarification,
    question_signature,
)
from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import AgentSpec
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

_QUESTIONS = [
    {"id": "scope", "text": "What is the MVP scope?", "kind": "text", "required": True},
    {"id": "deadline", "text": "Any hard deadline?", "kind": "text", "required": False},
]


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="x")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec,
                             temporal_workflow_id="wf-x")
    member = User.objects.create_user(
        email="po@acme.test", name="PO", tenant=t, password="pw")
    Membership.objects.create(tenant=t, user=member, project=project, role="product_owner")
    outsider = User.objects.create_user(
        email="nobody@acme.test", name="Out", tenant=t, password="pw")  # no membership
    clar = Clarification.objects.create(
        tenant=t, run=run, work_item=wi, phase="prd",
        questions=_QUESTIONS, context="context gap before drafting the PRD",
    )
    return {
        "tenant_id": str(t.id), "project_id": str(project.id), "clar_id": str(clar.id),
        "wi_id": str(wi.id), "run_id": str(run.id),
        "member_id": str(member.id), "outsider_id": str(outsider.id),
    }


# ── service ─────────────────────────────────────────────────────────
def test_answer_records_and_logs(world):
    result = answer_clarification(
        tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
        user_id=world["member_id"], answers={"scope": "auth + billing", "deadline": "Q3"},
    )
    assert result["status"] == Clarification.Status.ANSWERED
    clar = Clarification.objects.get(id=world["clar_id"])
    assert clar.status == Clarification.Status.ANSWERED
    assert clar.answers == {"scope": "auth + billing", "deadline": "Q3"}
    assert str(clar.answered_by_id) == world["member_id"]
    assert clar.answered_at is not None
    assert Event.objects.filter(
        tenant_id=world["tenant_id"], action="clarification.answered",
        target_id=world["clar_id"],
    ).exists()


def test_optional_question_may_be_omitted(world):
    # Only the required "scope" is supplied; the optional "deadline" is left out.
    answer_clarification(
        tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
        user_id=world["member_id"], answers={"scope": "auth only"},
    )
    assert Clarification.objects.get(id=world["clar_id"]).status == Clarification.Status.ANSWERED


def test_missing_required_answer_is_rejected(world):
    with pytest.raises(ClarificationError):
        answer_clarification(
            tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
            user_id=world["member_id"], answers={"deadline": "Q3"},  # no "scope"
        )
    assert Clarification.objects.get(id=world["clar_id"]).status == Clarification.Status.PENDING


def test_blank_required_answer_is_rejected(world):
    with pytest.raises(ClarificationError):
        answer_clarification(
            tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
            user_id=world["member_id"], answers={"scope": "   "},
        )


def test_non_member_cannot_answer(world):
    with pytest.raises(ClarificationRoleError):
        answer_clarification(
            tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
            user_id=world["outsider_id"], answers={"scope": "x"},
        )
    assert Clarification.objects.get(id=world["clar_id"]).status == Clarification.Status.PENDING


def test_already_answered_is_rejected(world):
    answer_clarification(
        tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
        user_id=world["member_id"], answers={"scope": "first"},
    )
    with pytest.raises(ClarificationError):
        answer_clarification(
            tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
            user_id=world["member_id"], answers={"scope": "second"},
        )
    assert Clarification.objects.get(id=world["clar_id"]).answers == {"scope": "first"}


# ── REST surface ────────────────────────────────────────────────────
def _hdr(tenant_id):
    return {"HTTP_X_TENANT_ID": str(tenant_id)}


def test_list_filters_pending_by_work_item(world):
    client = APIClient()
    resp = client.get(
        f"/api/clarifications/?status=pending&work_item={world['wi_id']}",
        **_hdr(world["tenant_id"]),
    )
    assert resp.status_code == 200
    assert [c["id"] for c in resp.data] == [world["clar_id"]]
    assert resp.data[0]["questions"][0]["id"] == "scope"


def test_answer_endpoint_happy_path(world):
    client = APIClient()
    resp = client.post(
        f"/api/clarifications/{world['clar_id']}/answer/",
        {"user_id": world["member_id"], "answers": {"scope": "auth + billing"}},
        format="json", **_hdr(world["tenant_id"]),
    )
    assert resp.status_code == 200
    assert resp.data["status"] == Clarification.Status.ANSWERED
    assert Clarification.objects.get(id=world["clar_id"]).status == Clarification.Status.ANSWERED


def test_answer_endpoint_non_member_403(world):
    client = APIClient()
    resp = client.post(
        f"/api/clarifications/{world['clar_id']}/answer/",
        {"user_id": world["outsider_id"], "answers": {"scope": "x"}},
        format="json", **_hdr(world["tenant_id"]),
    )
    assert resp.status_code == 403
    assert Clarification.objects.get(id=world["clar_id"]).status == Clarification.Status.PENDING


def test_answer_endpoint_missing_required_400(world):
    client = APIClient()
    resp = client.post(
        f"/api/clarifications/{world['clar_id']}/answer/",
        {"user_id": world["member_id"], "answers": {"deadline": "Q3"}},
        format="json", **_hdr(world["tenant_id"]),
    )
    assert resp.status_code == 400


# ── RLS tenant isolation (mirrors test_rls) ─────────────────────────
def _app_role_connection():
    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    return psycopg.connect(
        host=sd["HOST"], port=sd["PORT"], dbname=dbname,
        user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD, autocommit=True,
    )


def _make_clarification(tenant: Tenant) -> None:
    project = Project.objects.create(tenant=tenant, name=f"{tenant.name}-proj")
    wi = WorkItem.objects.create(tenant=tenant, project=project, type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(
        tenant=tenant, key=f"03_prd_{uuid.uuid4().hex[:8]}", body_ref="x")
    run = Run.objects.create(tenant=tenant, work_item=wi, agent_spec=spec)
    Clarification.objects.create(tenant=tenant, run=run, work_item=wi, questions=_QUESTIONS)


# ── create / get services (the agent's ask channel) ────────────────
_NEW_QS = [{"id": "framework", "text": "React or Vue?", "kind": "choice",
            "options": ["react", "vue"], "required": True}]


def test_create_clarification_opens_pending(world):
    result = create_clarification(
        tenant_id=world["tenant_id"], run_id=world["run_id"], questions=_NEW_QS,
        context="pick the FE framework", phase="architecture",
    )
    assert result["status"] == Clarification.Status.PENDING
    clar = Clarification.objects.get(id=result["id"])
    assert clar.phase == "architecture" and clar.signature == question_signature(_NEW_QS)
    assert str(clar.work_item_id) == world["wi_id"]  # derived from the run


def test_create_clarification_idempotent_by_signature(world):
    a = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                             questions=_NEW_QS)
    b = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                             questions=_NEW_QS)
    assert a["id"] == b["id"]  # same question set -> same clarification, not a duplicate


def test_create_clarification_returns_answer_when_already_answered(world):
    created = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                   questions=_NEW_QS)
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=created["id"],
                         user_id=world["member_id"], answers={"framework": "react"})
    # Re-ask (e.g. a re-dispatched run) -> the answered clarification comes straight back.
    again = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                 questions=_NEW_QS)
    assert again["id"] == created["id"]
    assert again["status"] == Clarification.Status.ANSWERED
    assert again["answers"] == {"framework": "react"}


def test_get_clarification_reports_status_and_answers(world):
    state = get_clarification(tenant_id=world["tenant_id"], clarification_id=world["clar_id"])
    assert state["status"] == Clarification.Status.PENDING and state["answers"] == {}


# ── runner endpoints (companion ask + poll, Runner-token auth) ──────
def _enroll(client, tenant_id, project_id):
    r = client.post("/api/runners/", {"project_id": project_id, "label": "l"},
                    format="json", **_hdr(tenant_id))
    assert r.status_code == 201, r.content
    return r.json()["token"]


def test_runner_create_and_poll_roundtrip(world):
    client = APIClient()
    token = _enroll(client, world["tenant_id"], world["project_id"])
    auth = {"HTTP_AUTHORIZATION": f"Runner {token}", **_hdr(world["tenant_id"])}

    created = client.post("/api/runner/clarifications/",
                          {"run_id": world["run_id"], "questions": _NEW_QS,
                           "context": "pick FE", "phase": "architecture"},
                          format="json", **auth)
    assert created.status_code == 201, created.content
    cid = created.json()["id"]
    assert created.json()["status"] == Clarification.Status.PENDING

    polled = client.get(f"/api/runner/clarifications/{cid}/", **auth)
    assert polled.status_code == 200 and polled.json()["status"] == Clarification.Status.PENDING

    # A human answers in the web app; the companion's next poll sees it.
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=cid,
                         user_id=world["member_id"], answers={"framework": "react"})
    polled2 = client.get(f"/api/runner/clarifications/{cid}/", **auth)
    assert polled2.json()["status"] == Clarification.Status.ANSWERED
    assert polled2.json()["answers"] == {"framework": "react"}


def test_runner_create_requires_token(world):
    client = APIClient()
    r = client.post("/api/runner/clarifications/",
                    {"run_id": world["run_id"], "questions": _NEW_QS},
                    format="json", **_hdr(world["tenant_id"]))  # no Runner token
    assert r.status_code == 401


def test_runner_create_missing_run_id_400(world):
    client = APIClient()
    token = _enroll(client, world["tenant_id"], world["project_id"])
    auth = {"HTTP_AUTHORIZATION": f"Runner {token}", **_hdr(world["tenant_id"])}
    r = client.post("/api/runner/clarifications/", {"questions": _NEW_QS},
                    format="json", **auth)
    assert r.status_code == 400


@pytest.mark.django_db(transaction=True)
def test_rls_isolates_clarifications_by_tenant():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    _make_clarification(a)
    _make_clarification(b)
    _make_clarification(b)

    raw = _app_role_connection()
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT count(*) FROM clarifications_clarification")
            assert cur.fetchone()[0] == 1

            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(b.id)])
            cur.execute("SELECT count(*) FROM clarifications_clarification")
            assert cur.fetchone()[0] == 2

            # No tenant context -> fail closed.
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM clarifications_clarification")
            assert cur.fetchone()[0] == 0
    finally:
        raw.close()
