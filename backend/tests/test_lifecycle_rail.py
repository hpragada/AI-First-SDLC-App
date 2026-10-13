"""A work item's rail shows the phases that kind of work item actually runs.

Found 2026-10-06 when the team opened a task and a defect screen for the first time: an epic, a
task and a defect all rendered the same 19-phase rail while each caption claimed something
different ("one pass through plan phases", "build phases only", "minimal rail").

The cause was one unused variable. `WorkItemViewSet.lifecycle` worked out a tier from the work
item's type and then never used it, so the loop below walked every agent spec. Nothing failed
loudly, so it went unnoticed.

Two things these tests pin that are easy to get wrong later:

* **A defect's rail must not be empty.** Its phases (07-10) belong to tasks too, so remediation
  is a SELECTION over the build set, never a partition of it — carving them out would empty the
  task rail instead.
* **The phase catalog endpoint must be unchanged.** Moving UX Design and Task Breakdown from
  build to plan corrects a misclassification, and the team's instruction was that correctly
  working behaviour must not be disturbed. Phases & Runs reads that endpoint.
"""
import pytest

from apps.projects.models import Project
from apps.registry.catalog import (
    ACTIVE_AGENT_CATALOG,
    BUILD_PHASE_KEYS,
    ONBOARDING_PHASE_KEYS,
    PLAN_PHASE_KEYS,
    REMEDIATION_PHASE_KEYS,
)
from apps.registry.models import AgentSpec
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="PeopleDesk")
    for d in ACTIVE_AGENT_CATALOG:
        AgentSpec.objects.create(
            tenant=t, key=d.key, phase_label=d.phase_label, body_ref=d.body_ref)
    return {"t": t, "project": project}


def _rail(client, world, item_type):
    item = WorkItem.objects.create(
        tenant=world["t"], project=world["project"], type=item_type, feature_stream="hr")
    r = client.get(f"/api/work-items/{item.id}/lifecycle/",
                   HTTP_X_TENANT_ID=str(world["t"].id))
    assert r.status_code == 200, r.data
    return [n["phase"] for n in r.data["nodes"]]


# ── the sets themselves ────────────────────────────────────────────────────
def test_every_active_agent_belongs_to_exactly_one_of_plan_or_build():
    """A phase missing from both would silently vanish from every rail."""
    keys = {d.key for d in ACTIVE_AGENT_CATALOG}
    assert keys - (PLAN_PHASE_KEYS | BUILD_PHASE_KEYS) == set(), "a phase belongs nowhere"
    assert (PLAN_PHASE_KEYS | BUILD_PHASE_KEYS) - keys == set(), "a key names no agent"
    assert PLAN_PHASE_KEYS & BUILD_PHASE_KEYS == set(), "a phase is in two tiers"


def test_remediation_is_a_selection_over_build_never_a_partition_of_it():
    """The trap this decision exists to avoid: carving these out would empty the task rail."""
    assert REMEDIATION_PHASE_KEYS < BUILD_PHASE_KEYS
    assert REMEDIATION_PHASE_KEYS, "a defect with no phases has no rail at all"


def test_build_begins_at_implementation():
    """UX Design and Task Breakdown are planning work. 06 CREATES tasks — its body calls
    create_work_item for every epic, story and task it emits — so it cannot run ON a task."""
    assert "05_ux_design" in PLAN_PHASE_KEYS
    assert "06_task_breakdown" in PLAN_PHASE_KEYS
    assert min(BUILD_PHASE_KEYS) == "07_implementation"


# ── the rails themselves ───────────────────────────────────────────────────
def test_an_epic_plans_and_does_not_build(client, world):
    rail = _rail(client, world, WorkItem.Type.EPIC)
    assert "01_ideation" in rail
    assert "05_ux_design" in rail and "06_task_breakdown" in rail
    assert "07_implementation" not in rail
    assert "12_deployment" not in rail


def test_a_story_plans_like_an_epic(client, world):
    assert _rail(client, world, WorkItem.Type.STORY) == _rail(client, world, WorkItem.Type.EPIC)


def test_a_task_builds_and_does_not_plan(client, world):
    rail = _rail(client, world, WorkItem.Type.TASK)
    assert "07_implementation" in rail
    assert "01_ideation" not in rail
    assert "05_ux_design" not in rail, "a task does not design the product"
    assert "06_task_breakdown" not in rail, "a task is the OUTPUT of task breakdown"


def test_a_defect_shows_the_repair_path_and_is_never_empty(client, world):
    rail = _rail(client, world, WorkItem.Type.DEFECT)
    assert set(rail) == set(REMEDIATION_PHASE_KEYS)
    assert rail, "an empty rail is the failure mode this decision exists to prevent"
    assert "05_ux_design" not in rail, "fixing a bug is not redesigning the product"


def test_no_work_item_rail_offers_project_onboarding(client, world):
    """Onboarding reads an existing codebase — it belongs to a project, not a work item.
    `00e_document_vision` is the one that leaked: it was added after the filter was written."""
    for t in (WorkItem.Type.EPIC, WorkItem.Type.TASK, WorkItem.Type.DEFECT):
        rail = _rail(client, world, t)
        assert not [p for p in rail if p.startswith("00")], f"{t}: {rail}"


# ── the guard on everything that already worked ────────────────────────────
def test_the_phase_catalog_endpoint_still_offers_every_phase(client, world):
    """Phases & Runs reads this. Moving 05/06 between buckets must not drop or reorder a
    single phase — all three consumers concatenate plan + build + remediation."""
    r = client.get("/api/phases/", HTTP_X_TENANT_ID=str(world["t"].id))
    assert r.status_code == 200
    got = [e["key"] for e in r.data["plan"] + r.data["build"] + r.data["remediation"]]
    # Set equality, not list equality: the endpoint orders by the DATABASE's collation, which
    # sorts "00_onboarding" and "00b_context_bridge" the other way round from Python. That
    # ordering is the endpoint's own and is not what this guard is about.
    assert set(got) == {d.key for d in ACTIVE_AGENT_CATALOG}, "a phase was dropped or added"
    assert len(got) == len(ACTIVE_AGENT_CATALOG), "a phase was duplicated across buckets"
    assert {e["key"] for e in r.data["plan"]} >= ONBOARDING_PHASE_KEYS, \
        "brownfield lost the onboarding phases it triggers from this screen"
