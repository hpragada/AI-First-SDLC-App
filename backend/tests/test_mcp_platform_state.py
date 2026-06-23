"""P0-T5 — Platform-State MCP tool integration tests (spec §2).

Exercises every tool against the real DB through the ORM the server uses, plus
tenant scoping (a tool scoped to tenant A cannot see/affect tenant B) and the
server wiring (all tools registered).
"""
import asyncio

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


# ── read / context / drift ──────────────────────────────────────────
def test_get_context_shape(world):
    t, project, run = world["t"], world["project"], world["run"]
    tools.register_artifact(
        t.id, project.id, run.id, "requirements", "requirements", "internal", "h1"
    )
    tools.log_event(t.id, "system", "phase.started", "work_item", str(world["wi"].id), {})

    ctx = tools.get_context(t.id, project.id, phase="prd")
    assert set(ctx) == {"profile", "relevant_artifacts", "recent_events", "retrieved_knowledge"}
    assert ctx["profile"]["important_context"] == "ctx" and ctx["profile"]["version"] == 2
    assert len(ctx["relevant_artifacts"]) == 1
    assert len(ctx["recent_events"]) == 1
    assert ctx["retrieved_knowledge"] == []  # Phase 4


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
        "get_context", "register_artifact", "update_artifact", "add_trace_edge",
        "log_event", "list_work_items", "create_work_item", "transition_work_item",
        "get_artifact", "list_artifacts", "detect_drift",
    }
    assert registered == expected
