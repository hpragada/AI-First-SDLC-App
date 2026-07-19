"""P3-09bX-3/4/5 — CI results ingestion: endpoint auth + parse + Regression-container loopback.

The client's CI posts JUnit; the platform authenticates the per-project CI token, parses with the
shared parser, and drives the existing defect loopback against a per-project Regression container.
Idempotent per CI run (`execution_ref`); a failing test opens a defect, a later pass closes it.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.ci_tokens import issue_ci_token
from apps.projects.models import Project
from apps.quality.ci_ingest import ingest_ci_results, regression_container
from apps.quality.models import TestExecution
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem

_FAIL = """<testsuite name="e2e" tests="2">
  <testcase classname="TC001LoginTests" name="rejects bad password"/>
  <testcase classname="TC009Checkout" name="completes an order">
    <failure message="AssertionError: expected 200">boom</failure>
  </testcase>
</testsuite>"""

_PASS = """<testsuite name="e2e" tests="2">
  <testcase classname="TC001LoginTests" name="rejects bad password"/>
  <testcase classname="TC009Checkout" name="completes an order"/>
</testsuite>"""


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    _, token = issue_ci_token(tenant_id=str(t.id), project_id=str(p.id), label="CI")
    return {"t": t, "p": p, "token": token}


def _defects(container):
    return WorkItem.objects.filter(parent_id=container.id, type=WorkItem.Type.DEFECT)


# ── service: correlation + loopback (X-4/X-5) ───────────────────────
def test_ingest_opens_a_defect_on_the_regression_container(world):
    out = ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                            xml_text=_FAIL, execution_ref="ci-1")
    assert out["imported"] and out["status"] == "failed"
    assert out["defects_opened"] and out["unmapped"] == []      # both cases carry a TC-ID

    container = regression_container(str(world["t"].id), str(world["p"].id))
    defect = _defects(container).get()
    assert defect.external_ref["test_ref"] == "TC-009"      # digits preserved from TC009Checkout
    assert TestExecution.objects.filter(work_item_id=container.id).count() == 1


def test_reposting_the_same_execution_ref_is_idempotent(world):
    for _ in range(2):
        ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                          xml_text=_FAIL, execution_ref="ci-1")
    container = regression_container(str(world["t"].id), str(world["p"].id))
    # One execution (updated in place), one defect — never duplicated.
    assert TestExecution.objects.filter(work_item_id=container.id).count() == 1
    assert _defects(container).count() == 1


def test_a_later_passing_run_closes_the_defect(world):
    ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                      xml_text=_FAIL, execution_ref="ci-1")
    out = ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                            xml_text=_PASS, execution_ref="ci-2")
    assert out["status"] == "passed" and out["defects_closed"]
    container = regression_container(str(world["t"].id), str(world["p"].id))
    assert _defects(container).get().state == WorkItem.State.DONE


def test_unmapped_cases_are_reported_not_defected(world):
    xml = ('<testsuite name="unit"><testcase classname="tests.test_login" '
           'name="test_ok"><failure message="x">y</failure></testcase></testsuite>')
    out = ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                            xml_text=xml, execution_ref="ci-1")
    # A non-TC failing test still records an execution + opens a defect on the container, but is
    # reported as unmapped so a human knows it isn't tied to a TC.
    assert out["unmapped"] == ["tests.test_login.test_ok"]


def test_malformed_or_empty_body_imports_nothing(world):
    out = ingest_ci_results(tenant_id=str(world["t"].id), project_id=str(world["p"].id),
                            xml_text="<broken", execution_ref="ci-1")
    assert out["imported"] is False and out["status"] == "skipped"
    assert not TestExecution.objects.filter(project_id=world["p"].id).exists()


# ── endpoint: auth + provenance (X-3) ───────────────────────────────
def _post(client, world, *, xml=_FAIL, token=None, tenant=None, qs="execution_ref=ci-1"):
    return client.post(
        f"/api/projects/{world['p'].id}/test-results/?{qs}",
        data=xml, content_type="application/xml",
        HTTP_AUTHORIZATION=f"CI {token if token is not None else world['token']}",
        HTTP_X_TENANT_ID=str(tenant if tenant is not None else world["t"].id),
    )


def test_endpoint_ingests_with_a_valid_token(world):
    resp = _post(APIClient(), world)
    assert resp.status_code == 200
    body = resp.json()
    assert body["imported"] and body["defects_opened"]


def test_endpoint_rejects_a_bad_or_missing_token(world):
    assert _post(APIClient(), world, token="nope").status_code == 401
    # A token for a different project cannot post here.
    other = Project.objects.create(tenant=world["t"], name="Other")
    _, other_token = issue_ci_token(tenant_id=str(world["t"].id), project_id=str(other.id))
    assert _post(APIClient(), world, token=other_token).status_code == 401


def test_endpoint_requires_execution_ref_and_a_body(world):
    assert _post(APIClient(), world, qs="").status_code == 400          # no execution_ref
    assert _post(APIClient(), world, xml="  ").status_code == 400       # empty body


def test_endpoint_422_on_unparseable_report(world):
    assert _post(APIClient(), world, xml="<broken").status_code == 422
