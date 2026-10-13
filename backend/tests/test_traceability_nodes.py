"""P3 — the traceability map can say which work item each document came out of.

The map's own question is "what came out of THIS piece of work", and its data could not answer it:
a node carried its phase, type, status and system-of-record link, and nothing tying it to a work
item. So the screen had no way to follow one item's chain, and the filters drawn for it during the
build were left wired to nothing in the component gallery — one of them offering a work item
("WI-492") invented for that gallery and present in no project.

The link already existed on every record: a document names the run that produced it, and a run
always has a work item. These tests pin that it is now followed, and that the one case with no
work item — a document adopted during brownfield onboarding, which no run produced — reports
itself as such rather than being dropped or crashing the endpoint.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.registry.models import AgentSpec, Artifact
from apps.runs.models import Run
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem

PASSWORD = "trace-pass!"


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=t, name="Checkout")
    spec = AgentSpec.objects.create(tenant=t, key="03_prd", body_ref="agents/03_prd/agent.md")
    user = User.objects.create_user(email="po@acme.com", name="Po", tenant=t, password=PASSWORD)
    Membership.objects.create(tenant=t, user=user, project=project, role="product_owner")
    wi = WorkItem.objects.create(tenant=t, project=project, type=WorkItem.Type.STORY,
                                 title="Currency rounding rule")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec)
    from_run = Artifact.objects.create(
        tenant=t, project=project, run=run, phase="03_prd", type="prd",
        title="PRD — Currency rounding", status="draft", version=1,
    )
    # No run: this is how a document adopted during onboarding arrives.
    adopted = Artifact.objects.create(
        tenant=t, project=project, phase="00_onboarding", type="source_document",
        title="Legacy spec.pdf", status="published", version=1,
    )
    return {"t": t, "project": project, "wi": wi, "from_run": from_run, "adopted": adopted}


def _nodes(world):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": "po@acme.com", "password": PASSWORD},
                       format="json").status_code == 200
    r = client.get(f"/api/projects/{world['project'].id}/traceability/")
    assert r.status_code == 200, r.data
    return {n["id"]: n for n in r.data["nodes"]}


def test_a_node_names_the_work_item_it_came_out_of(world):
    node = _nodes(world)[str(world["from_run"].id)]
    assert node["work_item"] == str(world["wi"].id)
    assert node["work_item_key"] == "WI-1"
    assert node["work_item_title"] == "Currency rounding rule"


def test_a_document_no_run_produced_says_so_rather_than_guessing(world):
    """An adopted document genuinely belongs to no work item. It reports empty values, which is
    what lets the screen offer it under "Not tied to a work item" instead of leaving it as the
    one group the filter can never reach."""
    node = _nodes(world)[str(world["adopted"].id)]
    assert node["work_item"] is None
    assert node["work_item_key"] == ""
    assert node["work_item_title"] == ""


def test_the_phase_and_type_the_filters_read_are_still_there(world):
    """Narrowing by phase and type needs no new data — these tests exist so a later change
    cannot quietly drop the fields those two filters are built on."""
    nodes = _nodes(world)
    assert nodes[str(world["from_run"].id)]["phase"] == "03_prd"
    assert nodes[str(world["from_run"].id)]["type"] == "prd"
    assert nodes[str(world["adopted"].id)]["phase"] == "00_onboarding"


def test_another_tenants_lineage_is_not_reachable(world):
    """The new join walks run → work item, so it is worth re-pinning that it stays inside the
    tenant it was asked about."""
    other = Tenant.objects.create(name="Globex")
    other_project = Project.objects.create(tenant=other, name="Theirs")
    other_spec = AgentSpec.objects.create(tenant=other, key="03_prd", body_ref="x")
    other_wi = WorkItem.objects.create(tenant=other, project=other_project,
                                       type=WorkItem.Type.STORY, title="Theirs")
    other_run = Run.objects.create(tenant=other, work_item=other_wi, agent_spec=other_spec)
    theirs = Artifact.objects.create(
        tenant=other, project=other_project, run=other_run, phase="03_prd", type="prd",
        title="Their PRD", status="draft", version=1,
    )
    assert str(theirs.id) not in _nodes(world)
