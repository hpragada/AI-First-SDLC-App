"""P0-T5 — Platform-State MCP tool integration tests (spec §2).

Exercises every tool against the real DB through the ORM the server uses, plus
tenant scoping (a tool scoped to tenant A cannot see/affect tenant B) and the
server wiring (all tools registered).
"""
import asyncio
import json

import pytest
from mcp_platform_state import tools

from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    """A tenant with a project, profile, work item, agent spec and run."""
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Platform")
    ProjectProfile.objects.create(
        tenant=t, project=project, important_context="ctx", domain="sdlc", version=2
    )
    wi = WorkItem.objects.create(
        tenant=t, project=project, type=WorkItem.Type.STORY, feature_stream="auth"
    )
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="agents/03_prd/agent.md")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    return {"t": t, "project": project, "wi": wi, "run": run}


# ── body staging / read-through (large HTML wireframes) ─────────────
def test_stage_artifact_body_persists_and_returns_pointer(world):
    """The write-half register_artifact lacks: a large body is staged to the object store and
    only its pointer comes back (#1/#3 — bodies never ride the pointers-only register call)."""
    from storage.object_store import InMemoryObjectStore

    t, project, run = world["t"], world["project"], world["run"]
    store = InMemoryObjectStore()
    html = "<!DOCTYPE html><html><body>login default</body></html>"
    res = tools.stage_artifact_body(
        t.id, project.id, run.id, "ux_design", "SCR-001-login-state-1-default.html",
        html, object_store=store,
    )
    assert res["s3_key"].startswith(f"drafts/{t.id}/{project.id}/{run.id}/ux_design/")
    assert res["bytes"] == len(html.encode())
    assert res["content_hash"].startswith("sha256:")
    # body actually landed in the store, unmodified
    assert store.get(res["s3_key"]).decode() == html


def test_get_artifact_body_returns_one_wireframe_state(world):
    """A per-screen wireframe carries states[] pointers; get_artifact_body reads ONE state's
    HTML back through the store (get_artifact stays pointers-only)."""
    from storage.object_store import InMemoryObjectStore

    t, project, run = world["t"], world["project"], world["run"]
    store = InMemoryObjectStore()
    default = tools.stage_artifact_body(
        t.id, project.id, run.id, "ux_design", "SCR-001-login-state-1-default.html",
        "<html>DEFAULT</html>", object_store=store)
    error = tools.stage_artifact_body(
        t.id, project.id, run.id, "ux_design", "SCR-001-login-state-4-error.html",
        "<html>ERROR</html>", object_store=store)
    art = tools.register_artifact(
        t.id, project.id, run.id, "ux_design", "wireframe", "internal",
        default["content_hash"], s3_key=default["s3_key"],
        external_ref={"screen_id": "SCR-001", "route": "/auth/login", "states": [
            {"name": "state-1-default", "s3_key": default["s3_key"],
             "content_hash": default["content_hash"]},
            {"name": "state-4-error", "s3_key": error["s3_key"],
             "content_hash": error["content_hash"]},
        ]},
    )
    # one specific state
    body = tools.get_artifact_body(t.id, art["id"], state="state-4-error", object_store=store)
    assert "ERROR" in body["body"]
    assert body["available_states"] == ["state-1-default", "state-4-error"]
    assert body["truncated"] is False
    # no state → default/primary body + the menu of states to fetch next
    primary = tools.get_artifact_body(t.id, art["id"], object_store=store)
    assert "DEFAULT" in primary["body"]
    assert primary["available_states"] == ["state-1-default", "state-4-error"]
    # unknown state is reported, not a crash
    missing = tools.get_artifact_body(t.id, art["id"], state="state-9-nope", object_store=store)
    assert missing["body"] == "" and "no such state" in missing["error"]


def test_list_and_context_return_pointer_only_external_ref(world):
    """Bugs.xlsx row 69: list_artifacts / get_context must NOT dump artifact bodies. A wireframe
    with big inline HTML in external_ref must come back with pointers only (states name+s3_key,
    metadata) so a 50-artifact listing stays within the MCP token budget."""
    t, project, run = world["t"], world["project"], world["run"]
    big = "<html>" + "x" * 50_000 + "</html>"
    tools.register_artifact(
        t.id, project.id, run.id, "ux_design", "wireframe", "internal", "h1",
        s3_key="drafts/k/default.html",
        external_ref={"screen_id": "SCR-001", "route": "/login",
                      "layout_notes": big, "raw_html": big,
                      "states": [{"name": "state-1-default", "s3_key": "drafts/k/default.html",
                                  "content_hash": "hh", "html": big}]},
    )
    listed = tools.list_artifacts(t.id, project.id)
    ref = listed[0]["external_ref"]
    assert "layout_notes" not in ref and "raw_html" not in ref  # bodies stripped
    assert ref["screen_id"] == "SCR-001" and ref["route"] == "/login"  # pointers kept
    assert ref["states"][0]["name"] == "state-1-default"
    assert "html" not in ref["states"][0]  # only pointer fields survive in states
    assert len(json.dumps(listed)) < 5_000  # the 50 KB body did not leak into the listing
    ctx = tools.get_context(t.id, project.id, "ux_design")
    assert len(json.dumps(ctx["relevant_artifacts"])) < 5_000


# ── write tools ─────────────────────────────────────────────────────
def test_register_get_and_list_artifacts(world):
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(
        t.id, project.id, run.id, phase="requirements", type="requirements",
        sor="internal", content_hash="h1", s3_key="s3://k/req.md",
    )
    assert a["status"] == "draft" and a["sor"] == "internal" and a["version"] == 1

    fetched = tools.get_artifact(t.id, a["id"])
    assert fetched["id"] == a["id"]

    listed = tools.list_artifacts(t.id, project.id, phase="requirements")
    assert [x["id"] for x in listed] == [a["id"]]
    assert tools.list_artifacts(t.id, project.id, status="published") == []


def test_register_artifact_bumps_version_across_re_registrations(world):
    """Bugs.xlsx row 28.2: re-registering the same (project, phase, type) — e.g. re-running a
    phase — yields v2, v3, … not another v1."""
    t, project, run = world["t"], world["project"], world["run"]
    first = tools.register_artifact(
        t.id, project.id, run.id, "prd", "prd", "internal", "h1", s3_key="k1"
    )
    second = tools.register_artifact(
        t.id, project.id, run.id, "prd", "prd", "internal", "h2", s3_key="k2"
    )
    assert first["version"] == 1
    assert second["version"] == 2
    # a different type on the same project starts its own count at v1
    other = tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h3"
    )
    assert other["version"] == 1


def test_register_artifact_stores_and_returns_title(world):
    """Bugs S.No 120: the human-readable title is stored and echoed back."""
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(
        t.id, project.id, run.id, "05_ux_design", "wireframe", "internal", "h1",
        title="Wireframe — Login Page",
    )
    assert a["title"] == "Wireframe — Login Page"
    assert tools.get_artifact(t.id, a["id"])["title"] == "Wireframe — Login Page"


def test_per_item_titles_get_independent_versions(world):
    """Bugs S.No 120 Part C-1: distinct per-item artifacts that share (phase, type) must NOT be
    numbered as versions of each other. Each titled sibling starts at v1; re-registering the SAME
    title is a genuine new version (v2)."""
    t, project, run = world["t"], world["project"], world["run"]
    login = tools.register_artifact(
        t.id, project.id, run.id, "05_ux_design", "wireframe", "internal", "h1",
        title="Wireframe — Login Page")
    checkout = tools.register_artifact(
        t.id, project.id, run.id, "05_ux_design", "wireframe", "internal", "h2",
        title="Wireframe — Checkout Page")
    login_v2 = tools.register_artifact(
        t.id, project.id, run.id, "05_ux_design", "wireframe", "internal", "h3",
        title="Wireframe — Login Page")
    assert login["version"] == 1
    assert checkout["version"] == 1    # a sibling, NOT a supersession of login
    assert login_v2["version"] == 2    # same title → genuine new version


def test_update_artifact(world):
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(
        t.id, project.id, run.id, "prd", "prd", "internal", "h1"
    )
    updated = tools.update_artifact(
        t.id, a["id"], status="published", content_hash="h2", version=2
    )
    assert updated["status"] == "published"
    assert updated["content_hash"] == "h2" and updated["version"] == 2


def test_add_trace_edge(world):
    t, project, run = world["t"], world["project"], world["run"]
    a1 = tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h1"
    )
    a2 = tools.register_artifact(t.id, project.id, run.id, "prd", "prd", "internal", "h2")
    edge = tools.add_trace_edge(t.id, a1["id"], a2["id"], "derives")
    assert edge["rel"] == "derives"
    assert edge["from_artifact_id"] == a1["id"] and edge["to_artifact_id"] == a2["id"]


def test_log_event(world):
    t, run = world["t"], world["run"]
    e = tools.log_event(
        t.id, actor="system", action="run.completed", target_type="run",
        target_id=str(run.id), payload={"cost": 0.12},
    )
    assert e["action"] == "run.completed" and e["payload"] == {"cost": 0.12}


# ── work item tools ─────────────────────────────────────────────────
def test_list_and_transition_work_items(world):
    t, project, wi = world["t"], world["project"], world["wi"]
    items = tools.list_work_items(t.id, project.id)
    assert [x["id"] for x in items] == [str(wi.id)]

    moved = tools.transition_work_item(t.id, wi.id, "in_progress")
    assert moved["state"] == "in_progress"
    assert tools.list_work_items(t.id, project.id, state="proposed") == []
    assert len(tools.list_work_items(t.id, project.id, state="in_progress")) == 1


def test_create_work_item_proposes_hierarchy(world):
    t, project = world["t"], world["project"]
    epic = tools.create_work_item(t.id, project.id, "epic", "Checkout", "the checkout epic")
    assert epic["type"] == "epic" and epic["state"] == "proposed" and epic["title"] == "Checkout"

    story = tools.create_work_item(
        t.id, project.id, "story", "Add to cart", "as a user…", parent_id=epic["id"]
    )
    assert story["state"] == "proposed" and story["parent_id"] == epic["id"]

    with pytest.raises(ValueError):  # enum-validated
        tools.create_work_item(t.id, project.id, "not_a_type", "x")


# ── multi-repo assignment (Hybrid Option C: agent proposes, human confirms) ──
def test_create_work_item_assigns_repo_with_draft_rationale(world):
    """A2/A5: the agent pins a repo + records a draft rationale/confidence the reviewer sees."""
    from apps.projects.models import Repository
    t, project = world["t"], world["project"]
    repo = Repository.objects.create(tenant=t, project=project, name="acme/api",
                                     role="backend", is_default=True)
    wi = tools.create_work_item(
        t.id, project.id, "task", "Persist webhook log", repo_id=str(repo.id),
        assignment_rationale="new DB table, backend-only", assignment_confidence="high",
    )
    assert wi["repo_id"] == str(repo.id)
    ra = wi["external_ref"]["repo_assignment"]
    assert ra["suggested_repo_id"] == str(repo.id) and ra["confidence"] == "high"
    assert ra["rationale"] == "new DB table, backend-only" and ra["source"] == "agent"


def test_create_work_item_repo_less_is_unchanged(world):
    """Backward-compat: no repo_id → repo stays null and no repo_assignment is written."""
    t, project = world["t"], world["project"]
    wi = tools.create_work_item(t.id, project.id, "task", "Some task")
    assert wi["repo_id"] is None and "repo_assignment" not in (wi["external_ref"] or {})


def test_create_work_item_rejects_repo_from_another_project(world):
    """A repo must belong to the work item's own project (and tenant)."""
    from apps.projects.models import Repository
    t, project = world["t"], world["project"]
    other = Project.objects.create(tenant=t, name="Other")
    foreign = Repository.objects.create(tenant=t, project=other, name="x/y", role="backend")
    with pytest.raises(ValueError):
        tools.create_work_item(t.id, project.id, "task", "x", repo_id=str(foreign.id))


def test_get_context_lists_repositories_as_assignment_options(world):
    """A1: a project-level run gets the repo list (id/name/role/base/is_default), default first."""
    from apps.projects.models import Repository
    t, project = world["t"], world["project"]
    Repository.objects.create(tenant=t, project=project, name="acme/web", role="frontend")
    Repository.objects.create(tenant=t, project=project, name="acme/api", role="backend",
                              is_default=True)
    ctx = tools.get_context(t.id, project.id, phase="task_breakdown")
    repos = ctx["repositories"]
    assert len(repos) == 2
    assert repos[0]["is_default"] is True and repos[0]["role"] == "backend"  # default first
    assert {r["role"] for r in repos} == {"backend", "frontend"}
    assert all({"repo_id", "name", "role", "default_base", "is_default"} <= set(r) for r in repos)


# ── read / context / drift ──────────────────────────────────────────
def test_get_context_shape(world):
    t, project, run = world["t"], world["project"], world["run"]
    tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h1"
    )
    tools.log_event(t.id, "system", "phase.started", "work_item", str(world["wi"].id), {})

    ctx = tools.get_context(t.id, project.id, phase="prd")
    assert set(ctx) == {"profile", "repo", "repositories", "relevant_artifacts",
                        "recent_events", "retrieved_knowledge", "answered_clarifications"}
    assert ctx["repo"] is None  # repo-less run → no per-repo scoping (D5)
    assert ctx["repositories"] == []  # no repos on this project → no assignment options
    assert ctx["profile"]["important_context"] == "ctx" and ctx["profile"]["version"] == 2
    assert len(ctx["relevant_artifacts"]) == 1
    assert len(ctx["recent_events"]) == 1
    assert ctx["retrieved_knowledge"] == []  # Phase 4
    assert ctx["answered_clarifications"] == []  # none asked yet


def test_get_context_replays_answered_clarifications(world):
    """A re-dispatched run sees prior human answers (req #2 durability); pending ones and
    other work items' clarifications are excluded."""
    from apps.clarifications.models import Clarification

    t, project, wi, run = world["t"], world["project"], world["wi"], world["run"]
    Clarification.objects.create(
        tenant=t, run=run, work_item=wi, phase="prd",
        questions=[{"id": "scope", "text": "MVP scope?"}], answers={"scope": "auth only"},
        status=Clarification.Status.ANSWERED,
    )
    Clarification.objects.create(
        tenant=t, run=run, work_item=wi, phase="prd",
        questions=[{"id": "later", "text": "later?"}], status=Clarification.Status.PENDING,
    )

    ctx = tools.get_context(t.id, project.id, phase="prd", work_item_id=str(wi.id))
    answered = ctx["answered_clarifications"]
    assert len(answered) == 1
    assert answered[0]["answers"] == {"scope": "auth only"}


def test_detect_drift_is_stub(world):
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(t.id, project.id, run.id, "prd", "prd", "internal", "h1")
    drift = tools.detect_drift(t.id, a["id"])
    assert drift == {"drift": False, "current_version": 1, "registered_version": 1}


# ── validation + tenant scoping ─────────────────────────────────────
def test_invalid_enums_rejected(world):
    t, project, wi = world["t"], world["project"], world["wi"]
    with pytest.raises(ValueError):
        tools.transition_work_item(t.id, wi.id, "not_a_state")
    with pytest.raises(ValueError):
        tools.register_artifact(t.id, project.id, world["run"].id, "prd", "prd", "bad_sor", "h")


def test_tools_are_tenant_scoped(world):
    """A tool scoped to tenant B must not reach tenant A's rows."""
    t_a, project_a, run_a = world["t"], world["project"], world["run"]
    a = tools.register_artifact(t_a.id, project_a.id, run_a.id, "prd", "prd", "internal", "h1")

    t_b = Tenant.objects.create(name="Beta")
    # B cannot read A's artifact
    with pytest.raises(Artifact.DoesNotExist):
        tools.get_artifact(t_b.id, a["id"])
    # B sees none of A's work items / artifacts
    assert tools.list_work_items(t_b.id, project_a.id) == []
    assert tools.list_artifacts(t_b.id, project_a.id) == []
    # B cannot register against A's project
    with pytest.raises(Project.DoesNotExist):
        tools.register_artifact(t_b.id, project_a.id, run_a.id, "prd", "prd", "internal", "h")


# ── server wiring ───────────────────────────────────────────────────
def test_server_registers_all_tools():
    from mcp_platform_state import server

    registered = {t.name for t in asyncio.run(server.server.list_tools())}
    expected = {
        "get_context", "register_artifact", "stage_artifact_body", "get_artifact_body",
        "update_artifact", "add_trace_edge",
        "log_event", "list_work_items", "create_work_item", "transition_work_item",
        "get_artifact", "list_artifacts", "detect_drift",
    }
    assert registered == expected
