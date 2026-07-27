"""Phase-4 acceptance slice (spec §7) — Brownfield-Full & Multi-Repo end-to-end.

Onboard a **split FE/BE** project (two repos): register-don't-recreate against Atlassian
(fakes) + the **built-in code-intel running for real in a companion worktree** (a temp git
repo) → Knowledge-Index chunks → reconcile → a **`gap_report`** with a resume phase. The
backend repo exports a versioned **`api_contract`**; the frontend reads it **read-through** and
records a cross-repo **`implements`** edge. Onboarding **hands off to the same pipeline**
(resume mid-pipeline triggers the next phase to its gate). A **contract change opens a drift
gate** whose change-impact **spans both repos**; the architect decides (accept re-indexes).

Deterministic + self-cleaning (temp git repos); external SoRs are faked so it runs offline.
Proves the invariants: register-don't-recreate idempotency, source never copied into state,
per-repo manifest scoping, tenant isolation, and the §8 sweep on the migrated 00/00b/00c.
"""
import subprocess
from pathlib import Path

import pytest
from mcp_platform_state import tools

from apps.knowledge.embeddings import NullEmbeddings
from apps.knowledge.index import index_artifact, retrieve
from apps.projects.models import Project, Repository
from apps.projects.repos import add_repository
from apps.registry.catalog import AGENT_CATALOG, seed_agent_specs
from apps.registry.models import Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem
from integrations.api_contract import export_api_contract, read_api_contract, record_implements
from integrations.codeintel.builtin import BuiltinCodeIntel
from integrations.drift import decide_drift, detect_contract_drift
from integrations.onboarding import build_gap_report, register_atlassian
from integrations.types import Issue, IssueHit
from integrations.webhooks import reconcile_github
from orchestration.trigger import trigger_phase
from storage import InMemoryObjectStore

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _git(path, *args):
    subprocess.run(["git", "-C", str(path), *args], check=True, capture_output=True)


def _be_repo(tmp_path):
    """A tiny real BE git repo (companion worktree) for the built-in analyzer."""
    ws = tmp_path / "acme-api"
    (ws / "pkg").mkdir(parents=True)
    (ws / "main.py").write_text("import pkg.a\n\nprint('go')\n")
    (ws / "pkg" / "__init__.py").write_text("")
    (ws / "pkg" / "a.py").write_text("from pkg import b\n\ndef run():\n    return b.value()\n")
    (ws / "pkg" / "b.py").write_text("def value():\n    return 1\n")
    _git(ws, "init", "-b", "main")
    _git(ws, "config", "user.email", "dev@acme.test")
    _git(ws, "config", "user.name", "Dev")
    _git(ws, "add", "-A")
    _git(ws, "commit", "-m", "init")
    return ws


class _FakeTaskTracker:
    def search(self, *, jql):
        return [IssueHit(key="ST-1", summary="Login")]

    def get_issue(self, *, issue_ref):
        return Issue(key="ST-1", summary="Login", status="To Do", issue_type="Story",
                     url="https://x/browse/ST-1")


@pytest.fixture
def world(db, tmp_path):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Split App", track=Project.Track.BROWNFIELD)
    fe = add_repository(tenant_id=str(t.id), project_id=str(project.id), name="acme/web",
                        role="frontend")["repository_id"]
    be = add_repository(tenant_id=str(t.id), project_id=str(project.id), name="acme/api",
                        role="backend")["repository_id"]
    architect = User.objects.create_user(email="ar@acme.test", name="Ar", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=architect, project=project, role="architect")
    po = User.objects.create_user(email="po@acme.test", name="PO", tenant=t, password="p")
    Membership.objects.create(tenant=t, user=po, project=project, role="product_owner")
    return {"t": str(t.id), "p": str(project.id), "fe": fe, "be": be,
            "architect": str(architect.id), "po": str(po.id),
            "store": InMemoryObjectStore(), "be_ws": _be_repo(tmp_path)}


def _published(world, type_, repo_id=None):
    a = tools.register_artifact(world["t"], world["p"], None, "onboarding", type_, "internal",
                                "h", repo_id=repo_id)["id"]
    tools.update_artifact(world["t"], a, status="published")
    return a


# ── 1. Onboard split FE/BE: discover → code-intel → reconcile → gap report ──
def test_onboard_split_fe_be_registers_intel_and_gap_report(world):
    # split topology from the two repos
    assert Project.objects.get(id=world["p"]).repo_topology == Project.RepoTopology.SPLIT

    # register-don't-recreate: bulk-import the Jira backlog (fake). B3-4: Confluence is no longer
    # crawled here — pages are linked + typed individually (covered in test_onboarding.py).
    out = register_atlassian(tenant_id=world["t"], project_id=world["p"],
                             tasktracker=_FakeTaskTracker(), project_key="ST")
    assert len(out["registered_issues"]) == 1
    again = register_atlassian(tenant_id=world["t"], project_id=world["p"],
                               tasktracker=_FakeTaskTracker(), project_key="ST")
    assert again["registered_issues"] == []   # idempotent

    # built-in code-intel runs for real in the companion worktree (temp git repo)
    idx = BuiltinCodeIntel().index(workspace=world["be_ws"], repo="acme/api")
    assert idx.file_count == 4 and idx.commits == 1
    intel = tools.register_artifact(world["t"], world["p"], None, "context_extraction",
                                    "codebase_intelligence", "internal", "h",
                                    repo_id=world["be"])["id"]
    index_artifact(tenant_id=world["t"], project_id=world["p"], artifact_id=intel,
                   text="The backend exposes GET /users and POST /orders.",
                   repo_id=world["be"], provider=NullEmbeddings())

    # some lifecycle exists (ideation/requirements/prd published); architecture is missing
    _published(world, "ideation")
    _published(world, "requirements")
    _published(world, "prd")

    report = build_gap_report(tenant_id=world["t"], project_id=world["p"],
                              object_store=world["store"])
    assert report["intel_present"] is True
    assert report["resume_phase"] == "architecture"        # first non-complete phase
    status = {p["phase"]: p["status"] for p in report["phases"]}
    assert status["prd"] == "complete" and status["architecture"] == "missing"
    assert Artifact.objects.get(id=report["gap_report_id"]).status == Artifact.Status.DRAFT

    # source is never copied into state — only the intel artifact + chunks, no `code` bodies
    assert Artifact.objects.filter(project_id=world["p"], type="code").count() == 0
    assert "users" in retrieve(world["t"], project_id=world["p"], query="users endpoint")[0][
        "text"].lower()


# ── 2. API-Contract: BE export → FE read-through → cross-repo implements ──
def test_api_contract_read_through_and_cross_repo_edge(world):
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"],
                                   body="GET /users", provider_repo_id=world["be"],
                                   source_commit="be-sha", object_store=world["store"])
    assert contract["semver"] == "1.0.0"

    # the FE repo reads it read-through (no copied file) and implements it (cross-repo edge)
    cur = read_api_contract(tenant_id=world["t"], project_id=world["p"])
    assert cur["id"] == contract["artifact_id"] and cur["external_ref"]["semver"] == "1.0.0"
    fe_code = tools.register_artifact(world["t"], world["p"], None, "implementation", "code",
                                      "internal", "h", repo_id=world["fe"])["id"]
    record_implements(tenant_id=world["t"], from_artifact_id=fe_code,
                      contract_artifact_id=contract["artifact_id"])
    edge = TraceEdge.objects.get(from_artifact_id=fe_code,
                                 to_artifact_id=contract["artifact_id"], rel="implements")
    assert str(edge.from_artifact.repo_id) == world["fe"]     # consumer in FE
    assert str(Artifact.objects.get(id=contract["artifact_id"]).repo_id) == world["be"]  # in BE

    # idempotent on an unchanged body (no spurious version bump)
    assert export_api_contract(tenant_id=world["t"], project_id=world["p"], body="GET /users",
                               object_store=world["store"])["bumped"] is False


# ── 3. Resume mid-pipeline: onboarding hands to the same pipeline (B3) ──
def test_resume_mid_pipeline_triggers_next_phase(world):
    _published(world, "ideation")
    _published(world, "requirements")
    _published(world, "prd")
    report = build_gap_report(tenant_id=world["t"], project_id=world["p"],
                              object_store=world["store"])
    resume = report["resume_phase"]
    assert resume == "architecture"

    seed_agent_specs(Tenant.objects.get(id=world["t"]))
    agent_key = next(d.key for d in AGENT_CATALOG if d.phase_label == resume)
    wi = WorkItem.objects.create(tenant_id=world["t"], project_id=world["p"],
                                 type=WorkItem.Type.STORY)
    calls = []
    result = trigger_phase(tenant_id=world["t"], project_id=world["p"], work_item_id=str(wi.id),
                           agent_key=agent_key, workflow_starter=lambda wf, inp: calls.append(inp))
    run = Run.objects.get(id=result.run_id)
    assert run.status == Run.Status.PENDING and len(calls) == 1
    assert calls[0].phase == "architecture" and calls[0].required_role == "architect"


# ── 4. Contract change → drift gate, change-impact spanning both repos ──
def test_contract_change_opens_drift_gate_across_repos(world):
    contract = export_api_contract(tenant_id=world["t"], project_id=world["p"],
                                   body="GET /users", provider_repo_id=world["be"],
                                   source_commit="be-sha", object_store=world["store"])[
                                       "artifact_id"]
    fe_code = tools.register_artifact(world["t"], world["p"], None, "implementation", "code",
                                      "internal", "h", repo_id=world["fe"])["id"]
    record_implements(tenant_id=world["t"], from_artifact_id=fe_code,
                      contract_artifact_id=contract)

    # a breaking bump → contract drift with change-impact reaching the FE consumer
    bump = export_api_contract(tenant_id=world["t"], project_id=world["p"],
                               body="GET /users (v2 breaking)", change="major",
                               object_store=world["store"])
    assert bump["semver"] == "2.0.0"
    drift = detect_contract_drift(tenant_id=world["t"], contract_artifact_id=contract,
                                  new_semver="2.0.0")
    assert drift["required_role"] == "architect"
    impacted = {i["artifact_id"]: i for i in drift["impacted"]}
    assert fe_code in impacted and impacted[fe_code]["repo_id"] == world["fe"]   # spans repos

    # the architect decides the drift gate (accept)
    decided = decide_drift(tenant_id=world["t"], drift_id=drift["drift_id"],
                           user_id=world["architect"], decision="accept")
    assert decided["status"] == "accepted"


def test_contract_drift_via_push_webhook(world):
    export_api_contract(tenant_id=world["t"], project_id=world["p"], body="GET /users",
                        provider_repo_id=world["be"], source_commit="oldsha",
                        object_store=world["store"])
    payload = {"ref": "refs/heads/main", "after": "newsha",
               "repository": {"full_name": "acme/api"}}
    out = reconcile_github(tenant_id=world["t"], event="push", delivery_id="p4-1", payload=payload)
    assert out["status"] == "processed" and out["drift_records"]    # webhook → drift gate


# ── 5. Invariants: tenant isolation + the §8 sweep on migrated agents ──
def test_phase4_tenant_isolation(world):
    # tenant A's slice state
    export_api_contract(tenant_id=world["t"], project_id=world["p"], body="c",
                        provider_repo_id=world["be"], object_store=world["store"])
    other = Tenant.objects.create(name="Other")
    op = Project.objects.create(tenant=other, name="Other App")
    assert Repository.objects.filter(tenant_id=other.id).count() == 0
    assert Artifact.objects.filter(tenant_id=other.id, type="api_contract").count() == 0
    from apps.integrations.models import DriftRecord
    assert DriftRecord.objects.filter(tenant_id=other.id).count() == 0
    # tenant B's own gap report sees none of A's lifecycle
    rep = build_gap_report(tenant_id=str(other.id), project_id=str(op.id),
                           object_store=InMemoryObjectStore())
    assert rep["resume_phase"] == "ideation" and rep["intel_present"] is False


_FORBIDDEN = [".md", "docs/", "claude.md", "tasks.md", "reply approved", "/sdlc:",
              "context-bridge.md"]


@pytest.mark.parametrize("key", ["00_onboarding", "00b_context_bridge",
                                 "00c_intelligent_context_extractor"])
def test_phase4_reference_sweep_clean(key):
    body = (_REPO_ROOT / "agents" / key / "agent.md").read_text(encoding="utf-8").lower()
    hits = [tok for tok in _FORBIDDEN if tok in body]
    assert not hits, f"{key}: forbidden references survived: {hits}"
