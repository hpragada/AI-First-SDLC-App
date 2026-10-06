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


# ── tiered gate: Tier-2/3 suggestion defaults (surface-all-tiers) ───────────
_TIERED_QS = [
    {"id": "billing_model", "text": "Which billing model?", "kind": "choice",
     "options": ["subscription", "usage"], "required": True, "tier": 1},
    {"id": "retention", "text": "Data retention window?", "kind": "text",
     "required": False, "tier": 2, "suggestion": "90 days"},
    {"id": "timestamps", "text": "Timestamp timezone?", "kind": "text",
     "required": False, "tier": 3, "suggestion": "UTC"},
]


def _tiered_clar(world):
    return create_clarification(
        tenant_id=world["tenant_id"], run_id=world["run_id"], questions=_TIERED_QS,
        context="front-loaded gate", phase="prd",
    )["id"]


def test_untouched_tier23_fall_back_to_suggestion(world):
    cid = _tiered_clar(world)
    # Human answers only the required Tier-1; leaves Tier-2/3 untouched.
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=cid,
                         user_id=world["member_id"], answers={"billing_model": "usage"})
    clar = Clarification.objects.get(id=cid)
    assert clar.answers == {
        "billing_model": "usage", "retention": "90 days", "timestamps": "UTC",
    }


def test_human_override_of_tier3_is_kept(world):
    cid = _tiered_clar(world)
    answer_clarification(
        tenant_id=world["tenant_id"], clarification_id=cid, user_id=world["member_id"],
        answers={"billing_model": "usage", "timestamps": "local time"},
    )
    clar = Clarification.objects.get(id=cid)
    # overridden Tier-3 kept; untouched Tier-2 still defaults.
    assert clar.answers["timestamps"] == "local time"
    assert clar.answers["retention"] == "90 days"


def test_blank_tier1_still_rejected_even_with_suggestions(world):
    cid = _tiered_clar(world)
    with pytest.raises(ClarificationError):
        answer_clarification(tenant_id=world["tenant_id"], clarification_id=cid,
                             user_id=world["member_id"], answers={"retention": "30 days"})
    assert Clarification.objects.get(id=cid).status == Clarification.Status.PENDING


def test_signature_differs_when_tier_changes(world):
    q_t3 = [{"id": "x", "text": "?", "kind": "text", "required": False, "tier": 3}]
    q_t1 = [{"id": "x", "text": "?", "kind": "text", "required": False, "tier": 1}]
    assert question_signature(q_t3) != question_signature(q_t1)


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
    # The project name is per-CALL, not per-tenant. This helper is called twice for the same
    # tenant below (two clarifications, one workspace), and `{tenant.name}-proj` made that the
    # second project in a workspace to carry the same name — which `uniq_tenant_project_name`
    # correctly refuses since Bugs S.No 211. The test never wanted a second project; it wanted a
    # second question. Nothing here asserts anything about the name, so making it unique restores
    # what the test meant without weakening the constraint.
    project = Project.objects.create(
        tenant=tenant, name=f"{tenant.name}-proj-{uuid.uuid4().hex[:8]}")
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


def test_a_reworded_question_still_dedupes_onto_the_answered_one(world):
    """Run 75adb0ec, reproduced. The ideation agent emitted two `ask_human` calls in one turn;
    the second fired a second after the human answered the first. All ten ids matched and nine
    of ten texts were byte-identical — one question had merely dropped a parenthetical. The old
    prose-hashing signature saw a different question set and put all ten questions back on the
    human's screen. Ids (+ tier) are the identity, so the re-ask must come back answered."""
    first = [{"id": "announcements", "text":
              "What should announcements support (e.g. acknowledge or comment)?",
              "kind": "text", "required": True, "tier": 1}]
    reworded = [{"id": "announcements", "text":
                 "What should announcements support?",   # same gap, seven words lighter
                 "kind": "text", "required": True, "tier": 1}]
    created = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                   questions=first)
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=created["id"],
                         user_id=world["member_id"], answers={"announcements": "HR only"})
    again = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                 questions=reworded)
    assert again["id"] == created["id"]
    assert again["answers"] == {"announcements": "HR only"}
    # …and the absorbed drift is on the record, not swallowed.
    assert Event.objects.filter(action="clarification.reask_deduped",
                                target_id=str(created["id"])).exists()


def test_a_genuinely_different_question_set_still_opens_a_new_clarification(world):
    """The dedupe must not become a gag. Different ids = a different gap = ask the human."""
    created = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                   questions=_NEW_QS)
    other = create_clarification(
        tenant_id=world["tenant_id"], run_id=world["run_id"],
        questions=[{"id": "hosting", "text": "Cloud or on-prem?", "kind": "text",
                    "required": True, "tier": 1}])
    assert other["id"] != created["id"]


def test_an_identical_reask_logs_no_drift_event(world):
    """A byte-identical re-ask (crash recovery / re-dispatch) is the normal, quiet path."""
    created = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                                   questions=_NEW_QS)
    create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                         questions=_NEW_QS)
    assert not Event.objects.filter(action="clarification.reask_deduped",
                                    target_id=str(created["id"])).exists()


def test_a_tier3_promoted_to_tier1_is_asked_again_not_deduped(world):
    """A Tier-3 question is auto-accepted from the agent's `suggestion` when the human leaves
    it alone. If the agent later promotes that same gap to Tier 1 — a decision it can no longer
    make itself — deduping would hand back the auto-accepted default as though a human had
    chosen it. Tier stays in the signature to stop exactly that."""
    gap_t3 = [{"id": "retention", "text": "How long to retain logs?", "kind": "text",
               "required": False, "tier": 3, "suggestion": "30 days"}]
    gap_t1 = [{"id": "retention", "text": "How long to retain logs?", "kind": "text",
               "required": True, "tier": 1}]
    a = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                             questions=gap_t3)
    b = create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                             questions=gap_t1)
    assert b["id"] != a["id"]


def test_get_clarification_reports_status_and_answers(world):
    state = get_clarification(tenant_id=world["tenant_id"], clarification_id=world["clar_id"])
    assert state["status"] == Clarification.Status.PENDING and state["answers"] == {}


# ── runner endpoints (companion ask + poll, Runner-token auth) ──────
def _enroll(client, tenant_id, project_id):
    # S.No 214 closed `POST /api/runners/` to anonymous callers — minting an enrollment
    # token is a credential operation. This test needs a token, not the endpoint, so it
    # goes through the domain service directly (as test_review_dispatch already does).
    from apps.runs.enrollment import enroll_runner

    _, token = enroll_runner(tenant_id=str(tenant_id), project_id=str(project_id), label="l")
    return token


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


# ── history surface: opt-in pagination + phase/project filters (WP2/WP3) ──
def test_list_without_page_param_returns_a_bare_array(world):
    """The contract every existing caller depends on. Seven call sites read this response as a
    JSON array; if adding pagination ever turns it into {count, next, previous, results} by
    default, they all break at once. No `page` param => no envelope."""
    client = APIClient()
    r = client.get("/api/clarifications/", **_hdr(world["tenant_id"]))
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_list_with_page_param_returns_an_envelope(world):
    client = APIClient()
    r = client.get("/api/clarifications/?page=1", **_hdr(world["tenant_id"]))
    assert r.status_code == 200
    body = r.json()
    assert set(body) >= {"count", "next", "previous", "results"}
    assert isinstance(body["results"], list)


def test_list_filters_by_phase(world):
    create_clarification(tenant_id=world["tenant_id"], run_id=world["run_id"],
                         questions=_NEW_QS, phase="ideation")
    client = APIClient()
    hit = client.get("/api/clarifications/?phase=ideation", **_hdr(world["tenant_id"]))
    miss = client.get("/api/clarifications/?phase=architecture", **_hdr(world["tenant_id"]))
    assert len(hit.json()) == 1
    assert miss.json() == []


def test_list_filters_by_project(world):
    client = APIClient()
    hit = client.get(f"/api/clarifications/?project={world['project_id']}",
                     **_hdr(world["tenant_id"]))
    miss = client.get(f"/api/clarifications/?project={uuid.uuid4()}",
                      **_hdr(world["tenant_id"]))
    assert len(hit.json()) >= 1
    assert miss.json() == []


def test_history_carries_the_answerer_name_and_work_item_title(world):
    WorkItem.objects.filter(id=world["wi_id"]).update(title="Leave balance ledger")
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
                         user_id=world["member_id"], answers={"scope": "MVP"})
    client = APIClient()
    r = client.get("/api/clarifications/?status=answered", **_hdr(world["tenant_id"]))
    row = r.json()[0]
    assert row["answered_by_name"] == "PO"                    # not a raw user id
    assert row["work_item_title"] == "Leave balance ledger"   # no backlog cross-reference


def test_a_clarification_carries_the_readable_work_item_key(world):
    """Found 2026-10-06: the clarifications screen drew eight characters of the work item's
    internal id beside every question, because the key was the one thing the serializer did not
    send. Nobody can use a uuid fragment; "WI-3" is what the key exists to be."""
    client = APIClient()
    row = client.get(f"/api/clarifications/?work_item={world['wi_id']}",
                     **_hdr(world["tenant_id"])).json()[0]
    assert row["work_item_key"].startswith("WI-")


def test_clarifications_can_be_narrowed_to_one_work_item(world):
    """What the "Open clarifications" count on a work item's summary card now links to."""
    client = APIClient()
    hit = client.get(f"/api/clarifications/?status=pending&work_item={world['wi_id']}",
                     **_hdr(world["tenant_id"]))
    miss = client.get(f"/api/clarifications/?status=pending&work_item={uuid.uuid4()}",
                      **_hdr(world["tenant_id"]))
    assert len(hit.json()) >= 1
    assert miss.json() == []


def test_search_matches_question_text_answer_text_and_context(world):
    """Search is server-side because the list is paged: searching in the browser would search
    only the visible page while appearing to search everything. It has to reach the question
    wording, the answer the human gave, and the agent's reason for asking."""
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
                         user_id=world["member_id"], answers={"scope": "billing and invoices"})
    client = APIClient()

    def ids(query):
        r = client.get(f"/api/clarifications/?q={query}", **_hdr(world["tenant_id"]))
        return {row["id"] for row in r.json()}

    assert world["clar_id"] in ids("MVP scope")        # question text
    assert world["clar_id"] in ids("invoices")         # the human's answer
    assert world["clar_id"] in ids("drafting the PRD")  # the agent's context
    assert ids("nothing here matches") == set()


def test_search_is_case_insensitive_and_combines_with_the_other_filters(world):
    answer_clarification(tenant_id=world["tenant_id"], clarification_id=world["clar_id"],
                         user_id=world["member_id"], answers={"scope": "Billing"})
    client = APIClient()
    hit = client.get("/api/clarifications/?q=billing&phase=prd", **_hdr(world["tenant_id"]))
    # Right search, wrong phase — the filters must AND, not OR.
    miss = client.get("/api/clarifications/?q=billing&phase=architecture",
                      **_hdr(world["tenant_id"]))
    assert len(hit.json()) == 1
    assert miss.json() == []
