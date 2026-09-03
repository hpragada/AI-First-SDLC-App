"""P4 — live drift detection + the drift gate (§6 / D6).

Contract drift (api_contract diverges from consumers) and pointer/hash drift (a SoR artifact's
external content changed) → a DriftRecord + change-impact via traceability → a control-plane
decide_drift gate (architect / tech_lead); accept reconciles, reject flags revert. The signed
GitHub push webhook is the live trigger. RLS isolates drift records per tenant.
"""
import psycopg
import pytest
from django.conf import settings
from django.db import connection
from mcp_platform_state import tools

from apps.integrations.models import DriftRecord
from apps.projects.models import Project, Repository
from apps.tenancy.models import Membership, Tenant, User
from integrations.api_contract import export_api_contract, record_implements
from integrations.drift import (
    DriftRoleError,
    change_impact,
    decide_drift,
    detect_contract_drift,
    detect_pointer_hash_drift,
)
from integrations.webhooks import reconcile_github
from storage import InMemoryObjectStore


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="Split App")
    fe = Repository.objects.create(tenant=t, project=p, name="acme/web", role="frontend")
    be = Repository.objects.create(tenant=t, project=p, name="acme/api", role="backend")
    architect = User.objects.create_user(email="a@acme.test", name="A", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=architect, project=p, role="architect")
    techlead = User.objects.create_user(email="tl@acme.test", name="TL", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=techlead, project=p, role="tech_lead")
    eng = User.objects.create_user(email="e@acme.test", name="E", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=eng, project=p, role="engineer")
    return {"t": str(t.id), "p": str(p.id), "fe": str(fe.id), "be": str(be.id),
            "architect": str(architect.id), "techlead": str(techlead.id), "eng": str(eng.id),
            "store": InMemoryObjectStore()}


def _artifact(world, type_, content_hash="h1", repo_id=None):
    return tools.register_artifact(world["t"], world["p"], None, "onboarding", type_,
                                   "internal", content_hash, repo_id=repo_id)["id"]


# ── pointer/hash drift ──────────────────────────────────────────────
def test_pointer_hash_drift_only_on_mismatch_and_is_idempotent(world):
    art = _artifact(world, "document", content_hash="h1")
    assert detect_pointer_hash_drift(tenant_id=world["t"], artifact_id=art,
                                     observed_hash="h1")["drift"] is False

    first = detect_pointer_hash_drift(tenant_id=world["t"], artifact_id=art, observed_hash="h2")
    assert first["drift"] and first["kind"] == "pointer_hash"
    assert first["required_role"] == "tech_lead" and first["created"] is True
    again = detect_pointer_hash_drift(tenant_id=world["t"], artifact_id=art, observed_hash="h2")
    assert again["created"] is False and again["drift_id"] == first["drift_id"]
    assert DriftRecord.objects.filter(artifact_id=art, status="open").count() == 1


# ── contract drift + cross-repo change-impact ───────────────────────
def test_contract_drift_change_impact_spans_repos(world):
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"],
                                   body="GET /users", provider_repo_id=world["fe"],
                                   object_store=world["store"])["artifact_id"]
    consumer = _artifact(world, "code", repo_id=world["be"])         # backend implements it
    record_implements(tenant_id=world["t"], from_artifact_id=consumer,
                      contract_artifact_id=contract)

    out = detect_contract_drift(tenant_id=world["t"], contract_artifact_id=contract,
                                new_semver="2.0.0")
    assert out["drift"] and out["kind"] == "contract" and out["required_role"] == "architect"
    impacted_ids = {i["artifact_id"] for i in out["impacted"]}
    assert consumer in impacted_ids                                  # the consumer is impacted
    consumer_row = next(i for i in out["impacted"] if i["artifact_id"] == consumer)
    assert consumer_row["repo_id"] == world["be"] and consumer_row["rel"] == "implements"


def test_change_impact_is_transitive(world):
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"], body="c",
                                   provider_repo_id=world["fe"], object_store=world["store"])[
                                       "artifact_id"]
    consumer = _artifact(world, "code", repo_id=world["be"])
    test_art = _artifact(world, "test_case", repo_id=world["be"])
    record_implements(tenant_id=world["t"], from_artifact_id=consumer,
                      contract_artifact_id=contract)
    tools.add_trace_edge(world["t"], test_art, consumer, "tests")    # test → code → contract

    impacted = {i["artifact_id"] for i in change_impact(world["t"], contract)}
    assert {consumer, test_art} <= impacted                          # transitive downstream


# ── the drift gate: accept reconciles, reject flags, role enforced ──
def test_decide_drift_accept_reindexes_pointer_hash(world):
    art = _artifact(world, "document", content_hash="h1")
    drift = detect_pointer_hash_drift(tenant_id=world["t"], artifact_id=art, observed_hash="h2")

    res = decide_drift(tenant_id=world["t"], drift_id=drift["drift_id"],
                       user_id=world["techlead"], decision="accept")
    assert res["status"] == "accepted"
    # reconcile: the artifact pointer is re-indexed to the observed hash (not a silent SoR write)
    from apps.registry.models import Artifact
    assert Artifact.objects.get(id=art).content_hash == "h2"
    # idempotent once decided
    again = decide_drift(tenant_id=world["t"], drift_id=drift["drift_id"],
                         user_id=world["techlead"], decision="reject")
    assert again.get("idempotent") is True and again["status"] == "accepted"


def test_decide_drift_wrong_role_blocked(world):
    art = _artifact(world, "document", content_hash="h1")
    drift = detect_pointer_hash_drift(tenant_id=world["t"], artifact_id=art, observed_hash="h2")
    # contract→architect, pointer/hash→tech_lead; an engineer (or the architect here) is wrong
    with pytest.raises(DriftRoleError):
        decide_drift(tenant_id=world["t"], drift_id=drift["drift_id"],
                     user_id=world["eng"], decision="accept")
    assert DriftRecord.objects.get(id=drift["drift_id"]).status == "open"


def test_decide_drift_reject_flags_revert_without_reconcile(world):
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"], body="c",
                                   provider_repo_id=world["fe"], object_store=world["store"])[
                                       "artifact_id"]
    drift = detect_contract_drift(tenant_id=world["t"], contract_artifact_id=contract)
    res = decide_drift(tenant_id=world["t"], drift_id=drift["drift_id"],
                       user_id=world["architect"], decision="reject", comment="revert it")
    assert res["status"] == "rejected"
    rec = DriftRecord.objects.get(id=drift["drift_id"])
    assert rec.status == "rejected" and rec.comment == "revert it"


# ── webhook → drift (the live path) ─────────────────────────────────
def test_push_webhook_opens_contract_drift(world):
    export_api_contract(tenant_id=world["t"], project_id=world["p"], body="GET /users",
                        provider_repo_id=world["fe"], source_commit="oldsha",
                        object_store=world["store"])
    payload = {"ref": "refs/heads/main", "after": "newsha123",
               "repository": {"full_name": "acme/web"}, "commits": [{"id": "newsha123"}]}
    out = reconcile_github(tenant_id=world["t"], event="push", delivery_id="d1", payload=payload)

    assert out["status"] == "processed" and out["drift_records"]     # a drift gate opened
    rec = DriftRecord.objects.get(id=out["drift_records"][0])
    assert rec.kind == "contract" and rec.required_role == "architect"
    assert rec.detail["source"] == "push:newsha123"


def test_push_webhook_no_drift_when_sha_matches(world):
    export_api_contract(tenant_id=world["t"], project_id=world["p"], body="c",
                        provider_repo_id=world["fe"], source_commit="samesha",
                        object_store=world["store"])
    payload = {"ref": "refs/heads/main", "after": "samesha",
               "repository": {"full_name": "acme/web"}}
    out = reconcile_github(tenant_id=world["t"], event="push", delivery_id="d2", payload=payload)
    assert out["drift_records"] == []                                # HEAD == contract commit


# ── RLS isolation (DB-level, via the app role) ──────────────────────
@pytest.mark.django_db(transaction=True)
def test_rls_isolates_drift_records():
    a = Tenant.objects.create(name="A")
    b = Tenant.objects.create(name="B")
    pa = Project.objects.create(tenant=a, name="A")
    pb = Project.objects.create(tenant=b, name="B")
    aa = tools.register_artifact(str(a.id), str(pa.id), None, "x", "document", "internal",
                                 "h1")["id"]
    ab = tools.register_artifact(str(b.id), str(pb.id), None, "x", "document", "internal",
                                 "h1")["id"]
    detect_pointer_hash_drift(tenant_id=str(a.id), artifact_id=aa, observed_hash="h2")
    detect_pointer_hash_drift(tenant_id=str(b.id), artifact_id=ab, observed_hash="h2")

    sd = connection.settings_dict
    with connection.cursor() as cur:
        cur.execute("SELECT current_database()")
        dbname = cur.fetchone()[0]
    raw = psycopg.connect(host=sd["HOST"], port=sd["PORT"], dbname=dbname,
                          user=settings.APP_DB_USER, password=settings.APP_DB_PASSWORD,
                          autocommit=True)
    try:
        with raw.cursor() as cur:
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(a.id)])
            cur.execute("SELECT count(*) FROM integrations_driftrecord")
            assert cur.fetchone()[0] == 1
            cur.execute("SELECT set_config('app.tenant_id', %s, false)", [""])
            cur.execute("SELECT count(*) FROM integrations_driftrecord")
            assert cur.fetchone()[0] == 0          # no tenant context → fail closed
    finally:
        raw.close()
