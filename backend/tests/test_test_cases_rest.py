"""P3-09b — Test cases REST: the coverage endpoint + manual create with priority/steps."""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.tenancy.models import Membership, Tenant, User
from apps.workitems.models import WorkItem


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    story = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Checkout")
    u = User.objects.create_user(email="qa@acme.com", name="QA", tenant=t, password="pw!")
    Membership.objects.create(tenant=t, user=u, project=story.project, role="engineer")
    return {"t": t, "p": p, "story": story}


def _client(world):
    c = APIClient()
    assert c.post("/api/auth/login/", {"email": "qa@acme.com", "password": "pw!"},
                  format="json").status_code == 200
    return c


def test_coverage_endpoint_lists_children_with_status(world):
    WorkItem.objects.create(tenant=world["t"], project=world["p"], parent=world["story"],
                            type=WorkItem.Type.TEST_CASE, title="TC-014 — Expired card",
                            external_ref={"tc_id": "TC-014", "priority": "High"})
    resp = _client(world).get(f"/api/work-items/{world['story'].id}/test-cases/")
    assert resp.status_code == 200
    row = resp.data[0]
    assert row["tc_id"] == "TC-014" and row["priority"] == "High"
    assert row["automation_status"] == "not_automated"      # no 09b run yet


def test_manual_create_stores_priority_and_steps(world):
    resp = _client(world).post("/api/work-items/", {
        "project": str(world["p"].id), "type": "test_case", "parent": str(world["story"].id),
        "title": "Checkout with saved card", "priority": "Medium",
        "description": "1. Sign in\n2. Pay with saved card\nExpected: order confirmed",
    }, format="json")
    assert resp.status_code == 201
    wi = WorkItem.objects.get(id=resp.data["id"])
    assert wi.type == "test_case" and str(wi.parent_id) == str(world["story"].id)
    assert wi.external_ref["priority"] == "Medium"
    assert "saved card" in wi.description       # steps land in description (→ 09b manifest)


def test_the_endpoint_says_what_kind_of_case_each_one_is(world):
    """G2. A QA Lead filtering for the WCAG cases needs the platform to have read the case's own
    `Type:` line, which until now nothing did."""
    WorkItem.objects.create(
        tenant=world["t"], project=world["p"], parent=world["story"],
        type=WorkItem.Type.TEST_CASE, title="TC-031 keyboard",
        external_ref={"tc_id": "TC-031", "priority": "high", "type": "accessibility"})
    WorkItem.objects.create(
        tenant=world["t"], project=world["p"], parent=world["story"],
        type=WorkItem.Type.TEST_CASE, title="TC-032 unclassified",
        external_ref={"tc_id": "TC-032"})

    rows = {r["tc_id"]: r for r in _client(world).get(
        f"/api/work-items/{world['story'].id}/test-cases/").data}
    assert rows["TC-031"]["type"] == "accessibility"
    assert rows["TC-031"]["priority"] == "high"
    blank = rows["TC-032"]
    # A case that never said stays blank — never a default.
    assert blank["type"] == ""
    assert blank["priority"] == ""
