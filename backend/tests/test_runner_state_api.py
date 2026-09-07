"""P2 — remote Platform-State serving (§3): build agent → HTTP → platform-state tools.

The tenant is bound server-side from the authenticated enrollment (never the body), so RLS
scoping stays on the platform; only the build-phase tool subset is reachable.
"""
import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Tenant


@pytest.fixture
def client():
    return APIClient()


def _enroll(client, tenant, project):
    # S.No 214 closed `POST /api/runners/` to anonymous callers — minting an enrollment
    # token is a credential operation. This test needs a token, not the endpoint, so it
    # goes through the domain service directly (as test_review_dispatch already does).
    from apps.runs.enrollment import enroll_runner

    _, token = enroll_runner(tenant_id=str(tenant.id), project_id=str(project.id), label="l")
    return token


def _state(client, tenant, token, tool, **args):
    return client.post(f"/api/runner/state/{tool}/", args, format="json",
                       HTTP_X_TENANT_ID=str(tenant.id), HTTP_AUTHORIZATION=f"Runner {token}")


def test_enroll_then_register_artifact_binds_tenant_server_side(db, client):
    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)

    r = _state(client, t, token, "register_artifact", project_id=str(p.id), run_id=None,
               phase="implementation", type="code", sor="internal", content_hash="h")
    assert r.status_code == 200, r.content
    art = r.json()["result"]
    assert Artifact.objects.filter(id=art["id"], tenant=t, type="code").exists()


def test_unauthenticated_call_is_401(db, client):
    t = Tenant.objects.create(name="A")
    r = client.post("/api/runner/state/log_event/",
                    {"actor": "x", "action": "y", "target_type": "run"},
                    format="json", HTTP_X_TENANT_ID=str(t.id))   # no Runner token
    assert r.status_code == 401


def test_tool_outside_build_allowlist_is_403(db, client):
    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    r = _state(client, t, token, "detect_drift", artifact_id="x")  # planning-only tool
    assert r.status_code == 403


def test_rejected_value_is_400_and_explains_itself(db, client):
    """A rejected VALUE is a caller error, not a platform fault (B2).

    Only TypeError was mapped to 400, so every ValueError the state tools raise — an unknown
    `rel`, `status` or `sor` — reached the agent as a **500**. An agent reading 500 concludes
    the platform is broken and retries the same call; reading "400: invalid rel … valid values"
    it corrects itself immediately. Live in run 98ab9a8c that cost nine wasted round trips and
    left every trace edge labelled with the one value that happened to stick."""
    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    a1 = Artifact.objects.create(tenant=t, project=p, phase="p", type="requirements",
                                 sor="internal", content_hash="h1")
    a2 = Artifact.objects.create(tenant=t, project=p, phase="p", type="prd",
                                 sor="internal", content_hash="h2")
    r = _state(client, t, token, "add_trace_edge",
               from_artifact_id=str(a1.id), to_artifact_id=str(a2.id), rel="documents")
    assert r.status_code == 400, r.content
    detail = r.json()["detail"]
    assert "derives" in detail and "implements" in detail    # the vocabulary, not just "invalid"


def test_agent_cannot_transition_work_item_to_done(db, client):
    """The build agent must not mark a WorkItem done — that is the control plane's job after an
    approved merge gate (#2/#5). Blocking it here prevents the state=done-while-awaiting_gate
    mislabel where the engine self-transitioned past the gate with no transition event."""
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.TASK, title="X",
                                 state=WorkItem.State.IN_PROGRESS)
    r = _state(client, t, token, "transition_work_item", work_item_id=str(wi.id), to_state="done")
    assert r.status_code == 403, r.content
    wi.refresh_from_db()
    assert wi.state == WorkItem.State.IN_PROGRESS               # unchanged — gate not bypassed


def test_agent_cannot_set_any_state_but_in_progress(db, client):
    """Bugs S.No 87: blocking `done` alone left every other state open. An agent could still
    call an item `accepted` — the reconciler's word for "this is in the tracker", which would be
    a lie — push it back to `proposed`, erasing the fact that work had started, or park it in
    `blocked`/`in_review`, states no control-plane code writes, so nothing would move it out
    again. Only `in_progress` is an agent's to set."""
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    # `cancelled` is in this list from the moment the state exists (S.No 140). The tool
    # validates only that a value is a member of the enum, so a new state is reachable by an
    # agent the instant it is added unless the allowlist says otherwise — which is precisely
    # what `test_a_state_added_later_is_refused_by_default` predicted.
    for target in ("proposed", "accepted", "in_review", "blocked", "done", "cancelled"):
        wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.TASK, title=target,
                                     state=WorkItem.State.IN_PROGRESS)
        r = _state(client, t, token, "transition_work_item", work_item_id=str(wi.id),
                   to_state=target)
        assert r.status_code == 403, f"{target} was allowed: {r.content!r}"
        assert "in_progress" in r.json()["detail"]      # says what IS allowed, not just "no"
        wi.refresh_from_db()
        assert wi.state == WorkItem.State.IN_PROGRESS, f"{target} was written anyway"


def test_a_state_added_later_is_refused_by_default(db, client):
    """The allowlist is the point. A blocklist has to be remembered every time a state is added
    — and the state most likely to be added next is another terminal one."""
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.TASK, title="X",
                                 state=WorkItem.State.IN_PROGRESS)
    r = _state(client, t, token, "transition_work_item", work_item_id=str(wi.id),
               to_state="some_future_state")
    assert r.status_code == 403, r.content


def test_agent_may_transition_work_item_to_in_progress(db, client):
    """The guard is scoped to gate-owned terminal states — the agent's legitimate
    -> in_progress transition at build start still works."""
    from apps.workitems.models import WorkItem

    t = Tenant.objects.create(name="A")
    p = Project.objects.create(tenant=t, name="App")
    token = _enroll(client, t, p)
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.TASK, title="X",
                                 state=WorkItem.State.PROPOSED)
    r = _state(client, t, token, "transition_work_item", work_item_id=str(wi.id),
               to_state="in_progress")
    assert r.status_code == 200, r.content
    wi.refresh_from_db()
    assert wi.state == WorkItem.State.IN_PROGRESS


def test_token_with_mismatched_tenant_is_401(db, client):
    a = Tenant.objects.create(name="A")
    pa = Project.objects.create(tenant=a, name="A")
    b = Tenant.objects.create(name="B")
    token_a = _enroll(client, a, pa)
    # Present A's token but claim tenant B → cannot authenticate.
    r = _state(client, b, token_a, "log_event", actor="x", action="y", target_type="run")
    assert r.status_code == 401


def test_runner_cannot_read_another_tenants_artifacts(db, client):
    a = Tenant.objects.create(name="A")
    pa = Project.objects.create(tenant=a, name="A")
    token_a = _enroll(client, a, pa)
    _state(client, a, token_a, "register_artifact", project_id=str(pa.id), run_id=None,
           phase="implementation", type="code", sor="internal", content_hash="h")

    b = Tenant.objects.create(name="B")
    pb = Project.objects.create(tenant=b, name="B")
    token_b = _enroll(client, b, pb)
    # B asks for A's project — its enrollment binds tenant=B, so it sees nothing.
    r = _state(client, b, token_b, "list_artifacts", project_id=str(pa.id))
    assert r.status_code == 200 and r.json()["result"] == []
