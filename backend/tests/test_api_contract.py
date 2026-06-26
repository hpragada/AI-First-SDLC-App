"""P4 — API-Contract artifact + cross-repo DAG edges (§5 / D4-D5).

The versioned, read-through `api_contract` that replaces the copied CONTEXT-BRIDGE: export
registers/version-bumps it (semver, idempotent on unchanged body, draft for the architect
gate), consumers read it read-through and record cross-repo `implements` edges, and cross-repo
WorkItem dependencies use `depends_on` across repo_id.
"""
import pytest
from mcp_platform_state import tools

from apps.projects.models import Project, Repository
from apps.registry.models import Artifact, TraceEdge
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.api_contract import (
    ApiContractError,
    add_work_item_dependency,
    cross_repo_dependents,
    export_api_contract,
    read_api_contract,
    record_implements,
)
from storage import InMemoryObjectStore


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="Split App",
                               repo_topology=Project.RepoTopology.SPLIT)
    provider = Repository.objects.create(tenant=t, project=p, name="acme/web", role="frontend")
    consumer = Repository.objects.create(tenant=t, project=p, name="acme/api", role="backend")
    return {"t": str(t.id), "p": str(p.id), "provider": str(provider.id),
            "consumer": str(consumer.id), "store": InMemoryObjectStore()}


def _kw(world, **extra):
    return dict(tenant_id=world["t"], project_id=world["p"], object_store=world["store"], **extra)


# ── export: register + version-bump ─────────────────────────────────
def test_export_registers_contract_at_v1_draft(world):
    src = tools.register_artifact(world["t"], world["p"], None, "context_bridge",
                                  "api_spec", "internal", "h")["id"]
    out = export_api_contract(**_kw(world, body="# Contract v1\nGET /users", change="minor",
                                    provider_repo_id=world["provider"], source_commit="abc123",
                                    target="backend", source_artifact_ids=[src]))
    assert out["created"] and out["bumped"] and out["semver"] == "1.0.0" and out["version"] == 1

    art = Artifact.objects.get(id=out["artifact_id"])
    assert art.type == "api_contract" and art.sor == "internal"
    assert art.status == Artifact.Status.DRAFT          # publishes only on the architect gate
    assert str(art.repo_id) == world["provider"]
    assert art.external_ref["semver"] == "1.0.0" and art.external_ref["target"] == "backend"
    assert world["store"].get(art.s3_key).decode() == "# Contract v1\nGET /users"
    # derived from the source artifact it was extracted from
    assert TraceEdge.objects.filter(from_artifact_id=art.id, to_artifact_id=src,
                                    rel="derives").exists()


def test_export_is_idempotent_on_unchanged_body(world):
    body = "# Contract\nGET /users"
    first = export_api_contract(**_kw(world, body=body))
    again = export_api_contract(**_kw(world, body=body))
    assert again["idempotent"] is True and again["bumped"] is False
    assert again["artifact_id"] == first["artifact_id"] and again["version"] == 1
    assert Artifact.objects.filter(project_id=world["p"], type="api_contract").count() == 1


def test_export_bumps_semver_and_resets_to_draft(world):
    out1 = export_api_contract(**_kw(world, body="v1"))
    tools.update_artifact(world["t"], out1["artifact_id"], status="published")  # gate approves

    minor = export_api_contract(**_kw(world, body="v1 + new optional field", change="minor"))
    assert minor["semver"] == "1.1.0" and minor["version"] == 2 and minor["bumped"]
    assert minor["artifact_id"] == out1["artifact_id"]   # one canonical, version-bumped
    art = Artifact.objects.get(id=minor["artifact_id"])
    assert art.status == Artifact.Status.DRAFT           # new version needs re-approval (#5)

    major = export_api_contract(**_kw(world, body="v2 breaking", change="major"))
    assert major["semver"] == "2.0.0" and major["version"] == 3
    assert Artifact.objects.get(id=major["artifact_id"]).external_ref["supersedes"] == "1.1.0"


def test_export_rejects_bad_change_kind(world):
    with pytest.raises(ApiContractError):
        export_api_contract(**_kw(world, body="x", change="huge"))


# ── read-through ────────────────────────────────────────────────────
def test_read_api_contract_returns_current_or_none(world):
    assert read_api_contract(tenant_id=world["t"], project_id=world["p"]) is None
    out = export_api_contract(**_kw(world, body="c"))
    cur = read_api_contract(tenant_id=world["t"], project_id=world["p"])
    assert cur and cur["id"] == out["artifact_id"] and cur["external_ref"]["semver"] == "1.0.0"


# ── cross-repo DAG edges ────────────────────────────────────────────
def test_record_implements_is_cross_repo_and_idempotent(world):
    contract = export_api_contract(**_kw(world, body="c", provider_repo_id=world["provider"]))
    consumer_art = tools.register_artifact(world["t"], world["p"], None, "implementation",
                                           "code", "internal", "h", repo_id=world["consumer"])["id"]

    res = record_implements(tenant_id=world["t"], from_artifact_id=consumer_art,
                            project_id=world["p"])
    assert res["created"] and res["contract_artifact_id"] == contract["artifact_id"]
    # idempotent — re-recording adds no duplicate edge
    again = record_implements(tenant_id=world["t"], from_artifact_id=consumer_art,
                              project_id=world["p"])
    assert again["created"] is False
    assert TraceEdge.objects.filter(to_artifact_id=contract["artifact_id"],
                                    rel="implements").count() == 1

    # change-impact: the dependent is the consumer repo's artifact (a true cross-repo edge)
    dependents = cross_repo_dependents(tenant_id=world["t"],
                                       contract_artifact_id=contract["artifact_id"])
    assert len(dependents) == 1 and dependents[0]["repo_id"] == world["consumer"]
    assert dependents[0]["artifact_id"] == consumer_art


def test_record_implements_without_contract_raises(world):
    art = tools.register_artifact(world["t"], world["p"], None, "implementation",
                                  "code", "internal", "h")["id"]
    with pytest.raises(ApiContractError):
        record_implements(tenant_id=world["t"], from_artifact_id=art, project_id=world["p"])


def test_add_work_item_dependency_across_repos(world):
    fe = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"],
                                 repo_id=world["provider"], type=WorkItem.Type.STORY)
    be = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"],
                                 repo_id=world["consumer"], type=WorkItem.Type.STORY)
    out = add_work_item_dependency(tenant_id=world["t"], work_item_id=str(be.id),
                                   depends_on_id=str(fe.id))
    assert out["added"] is True
    be.refresh_from_db()
    assert fe.id in be.depends_on
    # idempotent
    again = add_work_item_dependency(tenant_id=world["t"], work_item_id=str(be.id),
                                     depends_on_id=str(fe.id))
    assert again["added"] is False
    be.refresh_from_db()
    assert be.depends_on.count(fe.id) == 1
