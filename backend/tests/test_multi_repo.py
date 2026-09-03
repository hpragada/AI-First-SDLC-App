"""P4 — multi-repo project model + per-repo manifest scoping (§5 / D5).

One project carries N repos (topology reconciled to single/split/multi); the manifest is
scoped per repo (its artifacts + project-shared + the cross-repo `api_contract`) while the
registry and Knowledge Index stay project-scoped shared memory across repos.
"""
import pytest
from mcp_platform_state import tools

from apps.knowledge.embeddings import NullEmbeddings
from apps.knowledge.index import index_artifact
from apps.projects.models import Project, Repository
from apps.projects.repos import add_repository, repositories_for
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.api_contract import export_api_contract
from manifest.composer import compose_manifest
from storage import InMemoryObjectStore


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    return {"t": str(t.id), "p": str(p.id), "project": p, "store": InMemoryObjectStore()}


# ── multi-repo project model: topology reconciliation ───────────────
def test_add_repository_reconciles_topology(world):
    one = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web",
                         role="frontend")
    assert one["created"] and one["repo_topology"] == Project.RepoTopology.SINGLE

    two = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/api",
                         role="backend")
    assert two["repo_topology"] == Project.RepoTopology.SPLIT

    three = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/jobs",
                           role="service")
    assert three["repo_topology"] == Project.RepoTopology.MULTI
    world["project"].refresh_from_db()
    assert world["project"].repo_topology == Project.RepoTopology.MULTI


def test_add_repository_is_idempotent_by_name(world):
    first = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")
    again = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")
    assert first["created"] is True and again["created"] is False
    assert Repository.objects.filter(project_id=world["p"]).count() == 1
    assert again["repo_topology"] == Project.RepoTopology.SINGLE


def test_repositories_for_lists_project_repos(world):
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web", role="frontend")
    add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/api", role="backend")
    repos = repositories_for(tenant_id=world["t"], project_id=world["p"])
    assert {r["role"] for r in repos} == {"frontend", "backend"}


# ── per-repo manifest scoping (D5) ──────────────────────────────────
def _artifact(world, type_, repo_id=None):
    return tools.register_artifact(world["t"], world["p"], None, "implementation", type_,
                                   "internal", "h", repo_id=repo_id)["id"]


def test_get_context_scopes_artifacts_per_repo_plus_shared_contract(world):
    fe = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web",
                        role="frontend")["repository_id"]
    be = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/api",
                        role="backend")["repository_id"]
    fe_only = _artifact(world, "code", repo_id=fe)
    be_only = _artifact(world, "code", repo_id=be)
    project_level = _artifact(world, "prd", repo_id=None)      # repo-agnostic, shared
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"],
                                   body="GET /users", provider_repo_id=fe,
                                   object_store=world["store"])["artifact_id"]

    be_wi = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"], repo_id=be,
                                    type=WorkItem.Type.STORY, title="orders")
    ctx = tools.get_context(world["t"], world["p"], phase="implementation",
                            work_item_id=str(be_wi.id))

    assert ctx["repo"] and ctx["repo"]["role"] == "backend"
    ids = {a["id"] for a in ctx["relevant_artifacts"]}
    assert be_only in ids                       # this repo's own artifact
    assert project_level in ids                 # repo-agnostic project artifact
    assert contract in ids                      # the shared cross-repo contract (lives on FE)
    assert fe_only not in ids                   # the other repo's artifact is scoped out


def test_get_context_without_repo_is_unscoped(world):
    fe = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")[
        "repository_id"]
    fe_only = _artifact(world, "code", repo_id=fe)
    plain = _artifact(world, "prd", repo_id=None)
    wi = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"],
                                 type=WorkItem.Type.STORY)   # no repo
    ctx = tools.get_context(world["t"], world["p"], phase="implementation",
                            work_item_id=str(wi.id))
    assert ctx["repo"] is None
    ids = {a["id"] for a in ctx["relevant_artifacts"]}
    assert fe_only in ids and plain in ids      # nothing scoped out when no repo is in scope


def test_knowledge_index_is_project_wide_shared_across_repos(world):
    fe = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/web")[
        "repository_id"]
    be = add_repository(tenant_id=world["t"], project_id=world["p"], name="acme/api")[
        "repository_id"]
    fe_art = _artifact(world, "code", repo_id=fe)
    # knowledge authored against the FE repo
    index_artifact(tenant_id=world["t"], project_id=world["p"], artifact_id=fe_art,
                   text="The frontend calls the refund endpoint on checkout.",
                   repo_id=fe, provider=NullEmbeddings())

    be_wi = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"], repo_id=be,
                                    type=WorkItem.Type.STORY, title="refund handling")
    ctx = tools.get_context(world["t"], world["p"], phase="implementation",
                            work_item_id=str(be_wi.id))
    # a BE-scoped run still retrieves the FE repo's knowledge (shared memory, not siloed)
    assert ctx["retrieved_knowledge"]
    assert "refund" in ctx["retrieved_knowledge"][0]["text"].lower()


# ── composer renders the # Repository section only when repo-scoped ──
def _ctx(repo=None):
    return {"profile": {"name": "App", "track": "brownfield", "repo_topology": "split"},
            "repo": repo, "relevant_artifacts": [], "recent_events": [],
            "retrieved_knowledge": []}


def test_composer_renders_repository_section_when_scoped():
    repo = {"repo_id": "r1", "name": "acme/api", "role": "backend",
            "default_base": "main", "connector": "github", "stack_overrides": {"py": "3.12"}}
    out = compose_manifest(context=_ctx(repo), work_item={}, phase="implementation")
    assert "# Repository" in out and "role: backend" in out
    assert "stack_overrides" in out and "project-wide" in out
    # ordering: Repository sits right after Project, before Important Context
    assert out.index("# Project") < out.index("# Repository") < out.index("# Important Context")


def test_composer_omits_repository_section_for_single_repo():
    out = compose_manifest(context=_ctx(repo=None), work_item={}, phase="implementation")
    assert "# Repository" not in out
