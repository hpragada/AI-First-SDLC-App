"""P3 — TestMgmt capability over Xray Cloud (REST import + GraphQL).

Unit tests drive the connector through a fake transport (auth handshake, bearer header,
GraphQL/REST shaping, status mapping, idempotency) with no network. A registry test proves
per-tenant selection. A live test (skips without creds) does a real auth + read round-trip.
"""
import pytest

from apps.integrations.models import IntegrationConnection
from apps.tenancy.models import Tenant
from integrations.capabilities import TestMgmt
from integrations.registry import get_capability
from integrations.types import (
    CapabilityError,
    TestExecutionImport,
    TestResult,
    TestStep,
)
from integrations.xray.config import XrayConfig
from integrations.xray.testmgmt import XrayTestMgmt


class _Recorder:
    """Transport stub: handles the auth handshake, then routes via handler(method, url, body)."""

    def __init__(self, handler):
        self._handler = handler
        self.calls: list[tuple] = []

    def __call__(self, method, url, headers, body):
        self.calls.append((method, url, headers, body))
        if url.endswith("/api/v2/authenticate"):
            return 200, "fake-bearer-token"
        return self._handler(method, url, body)


def _tm(handler, project="PROJ"):
    rec = _Recorder(handler)
    cfg = XrayConfig(api_url="https://xray.cloud.getxray.app", client_id="ci", client_secret="cs")
    return XrayTestMgmt(cfg, project=project, transport=rec), rec


def _is_graphql(url, body, needle):
    return url.endswith("/api/v2/graphql") and needle in (body or {}).get("query", "")


# ── auth handshake ──────────────────────────────────────────────────
def test_authenticates_once_then_carries_bearer():
    def handler(method, url, body):
        return 200, {"data": {"getTests": {"results": []}}}

    tm, rec = _tm(handler)
    tm.search(jql="project = PROJ")
    assert rec.calls[0][1].endswith("/api/v2/authenticate")     # auth first
    # the follow-up GraphQL call carries the bearer from the handshake
    _m, _u, headers, _b = rec.calls[1]
    assert headers["Authorization"] == "Bearer fake-bearer-token"


# ── create_test (idempotent by summary) ─────────────────────────────
def test_create_test_returns_existing_on_summary_match():
    def handler(method, url, body):
        if _is_graphql(url, body, "getTests"):
            return 200, {"data": {"getTests": {"results": [
                {"jira": {"key": "PROJ-9", "summary": "Login works"}}]}}}
        raise AssertionError(f"must not create: {body}")

    tm, rec = _tm(handler)
    ref = tm.create_test(summary="Login works", steps=[TestStep(action="open")])
    assert ref.id == "PROJ-9" and ref.sor == "xray"
    assert not any(_is_graphql(u, b, "createTest") for _m, u, _h, b in rec.calls)


def test_create_test_creates_when_absent():
    def handler(method, url, body):
        if _is_graphql(url, body, "getTests"):
            return 200, {"data": {"getTests": {"results": []}}}      # none exists
        if _is_graphql(url, body, "createTest"):
            return 200, {"data": {"createTest": {"test": {"jira": {"key": "PROJ-10"}}}}}
        raise AssertionError(url)

    tm, _ = _tm(handler)
    ref = tm.create_test(summary="New test", steps=[TestStep(action="x", expected="y")])
    assert ref.id == "PROJ-10" and ref.url.endswith("/browse/PROJ-10")


# ── import_results (status mapping + idempotency) ───────────────────
def test_import_results_maps_statuses_and_creates_execution():
    captured = {}

    def handler(method, url, body):
        if url.endswith("/api/v2/import/execution"):
            captured["body"] = body
            return 200, {"key": "PROJ-200", "self": "https://x/execution/PROJ-200"}
        raise AssertionError(url)

    tm, _ = _tm(handler)
    ref = tm.import_results(execution=TestExecutionImport(
        project="PROJ", work_item_ref="PROJ-1",
        results=[TestResult("PROJ-2", "PASS"), TestResult("PROJ-3", "FAIL", "boom")],
    ))
    assert ref.id == "PROJ-200"
    statuses = {t["testKey"]: t["status"] for t in captured["body"]["tests"]}
    assert statuses == {"PROJ-2": "PASSED", "PROJ-3": "FAILED"}     # PASS/FAIL → Xray names
    assert "testExecutionKey" not in captured["body"]              # no prior ref → create


def test_import_results_is_idempotent_with_execution_ref():
    captured = {}

    def handler(method, url, body):
        captured["body"] = body
        return 200, {"key": "PROJ-200"}

    tm, _ = _tm(handler)
    tm.import_results(execution=TestExecutionImport(
        project="PROJ", work_item_ref="PROJ-1", execution_ref="PROJ-200",
        results=[TestResult("PROJ-2", "PASS")],
    ))
    assert captured["body"]["testExecutionKey"] == "PROJ-200"      # updates, never duplicates


# ── read-through + linkage ──────────────────────────────────────────
def test_get_test_parses_steps_and_fields():
    def handler(method, url, body):
        return 200, {"data": {"getTests": {"results": [{
            "steps": [{"action": "open", "data": "/", "result": "ok"}],
            "jira": {"key": "PROJ-2", "summary": "S", "status": "PASS"},
        }]}}}

    tm, _ = _tm(handler)
    tc = tm.get_test(test_ref="PROJ-2")
    assert tc.key == "PROJ-2" and tc.summary == "S" and tc.steps[0].action == "open"


def test_search_parses_hits():
    def handler(method, url, body):
        return 200, {"data": {"getTests": {"results": [
            {"jira": {"key": "PROJ-2", "summary": "A"}},
            {"jira": {"key": "PROJ-3", "summary": "B"}}]}}}

    tm, _ = _tm(handler)
    hits = tm.search(jql="project = PROJ")
    assert [h.key for h in hits] == ["PROJ-2", "PROJ-3"]


def test_link_defect_posts_graphql_with_both_refs():
    captured = {}

    def handler(method, url, body):
        captured["body"] = body
        return 200, {"data": {"addDefectsToTest": {"addedDefects": 1}}}

    tm, _ = _tm(handler)
    tm.link_defect(test_ref="PROJ-2", defect_ref="PROJ-50")
    assert captured["body"]["variables"] == {"issueId": "PROJ-2", "defects": ["PROJ-50"]}


def test_rest_error_raises_capability_error():
    tm, _ = _tm(lambda m, u, b: (500, {"error": "boom"}))
    with pytest.raises(CapabilityError) as exc:
        tm.search(jql="x")
    assert exc.value.status == 500


def test_no_project_and_no_default_raises():
    tm, _ = _tm(lambda m, u, b: (200, {}), project="")
    with pytest.raises(CapabilityError):
        tm.create_test(summary="x", steps=[])


# ── per-tenant selection (the #9 seam) ──────────────────────────────
def test_get_capability_resolves_testmgmt_to_xray(db):
    tenant = Tenant.objects.create(name="Acme")
    IntegrationConnection.objects.create(
        tenant=tenant, capability="testmgmt", connector="xray",
        scopes={"project_key": "QA"}, token_ref="settings:xray",
    )
    tm = get_capability(tenant.id, "testmgmt")
    assert isinstance(tm, TestMgmt)
    assert tm._project == "QA"


# ── live auth + read round-trip (runs only with creds) ──────────────
def _live():
    from django.conf import settings

    cfg = XrayConfig.from_settings()
    project = settings.XRAY_PROJECT_KEY
    return (cfg, project) if (cfg.configured and project) else None


@pytest.mark.skipif(_live() is None, reason="Xray creds/project not configured in .env")
def test_xray_testmgmt_live_search_roundtrip():
    cfg, project = _live()
    tm = XrayTestMgmt(cfg, project=project)
    assert isinstance(tm.search(jql=f'project = "{project}"'), list)   # auth + read works
