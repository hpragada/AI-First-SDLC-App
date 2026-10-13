"""P0-T5 — Platform-State MCP tool integration tests (spec §2).

Exercises every tool against the real DB through the ORM the server uses, plus
tenant scoping (a tool scoped to tenant A cannot see/affect tenant B) and the
server wiring (all tools registered).
"""
import asyncio
import json
from pathlib import Path

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


# ── progress events: the run console streams the agent's work (bug 3) ──
def test_register_artifact_streams_a_progress_event_to_the_run_console(world):
    """Testing-phase bug 3: a 25-minute run registering 90 artifacts showed NOTHING between
    phase.dispatched and phase.reported, so a healthy run was indistinguishable from a dead
    one. The event must target the RUN — that is what the console queries
    (?target_type=run&target_id=…); an artifact-targeted event would still be invisible."""
    from apps.ledger.models import Event

    created = tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "testing", "test_case",
        "internal", "h", title="TC-014 — Login rejects a bad password",
    )
    event = Event.objects.get(tenant_id=world["t"].id, action="artifact.registered")
    # target_id is a UUIDField — the console filters ?target_id=<run uuid> against it.
    assert event.target_type == "run" and str(event.target_id) == str(world["run"].id)
    assert event.payload["artifact_id"] == created["id"]
    assert event.payload["type"] == "test_case"
    assert event.payload["title"] == "TC-014 — Login rejects a bad password"


def test_the_console_line_names_the_artifact(world):
    """The serializer renders `payload["message"]` (it checks `message` first and has no
    type/title key), so without it every line would read a bare "Artifact registered"."""
    from api.serializers import EventSerializer
    from apps.ledger.models import Event

    tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "testing", "test_case",
        "internal", "h", title="TC-014 — Login rejects a bad password",
    )
    event = Event.objects.get(tenant_id=world["t"].id, action="artifact.registered")
    data = EventSerializer(event).data
    assert data["message"] == (
        "Artifact registered — test_case — TC-014 — Login rejects a bad password"
    )
    assert data["kind"] == "ok"


def test_the_console_endpoint_returns_the_progress_events(world):
    """End-to-end on the path the console actually uses:
    GET /api/events/?target_type=run&target_id=<run>. This is the acceptance criterion — the
    gap between phase.dispatched and phase.reported now carries progress."""
    from rest_framework.test import APIClient

    tools.log_event(world["t"].id, "orchestrator", "phase.dispatched", "run",
                    str(world["run"].id), {"phase": "testing"})
    for i in range(3):
        tools.register_artifact(
            world["t"].id, world["project"].id, world["run"].id, "testing", "test_case",
            "internal", "h", title=f"TC-{i:03d} — case",
        )
    tools.log_event(world["t"].id, "orchestrator", "phase.reported", "run",
                    str(world["run"].id), {})

    resp = APIClient().get("/api/events/", {"target_type": "run",
                                            "target_id": str(world["run"].id)},
                           HTTP_X_TENANT_ID=str(world["t"].id))
    assert resp.status_code == 200, resp.content
    rows = resp.json()
    rows = rows["results"] if isinstance(rows, dict) else rows
    progress = [r for r in rows if r["action"] == "artifact.registered"]
    assert len(progress) == 3                       # no longer silent between the two events
    assert progress[0]["message"].startswith("Artifact registered — test_case — TC-")


def test_an_untitled_artifact_still_streams_its_type(world):
    from apps.ledger.models import Event

    tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "prd", "prd", "internal", "h",
    )
    event = Event.objects.get(tenant_id=world["t"].id, action="artifact.registered")
    assert event.payload["message"] == "prd"


def test_a_run_less_registration_logs_no_progress_event(world):
    """No run ⇒ no console to stream to; the artifact row carries its own provenance."""
    from apps.ledger.models import Event

    tools.register_artifact(
        world["t"].id, world["project"].id, None, "prd", "prd", "internal", "h", title="X",
    )
    assert not Event.objects.filter(tenant_id=world["t"].id,
                                    action="artifact.registered").exists()


def test_progress_events_are_muted_in_the_agent_manifest(world):
    """The console wants all 90; an agent's `# Recent Events` must not be flooded by them —
    the window is 20 tenant-wide, and `# Relevant Artifacts` already lists every artifact."""
    for i in range(25):
        tools.register_artifact(
            world["t"].id, world["project"].id, world["run"].id, "testing", "test_case",
            "internal", "h", title=f"TC-{i:03d} — case",
        )
    tools.log_event(world["t"].id, "system", "gate.opened", "run", str(world["run"].id), {})

    ctx = tools.get_context(world["t"].id, world["project"].id, phase="testing")
    actions = [e["action"] for e in ctx["recent_events"]]
    assert "artifact.registered" not in actions          # not one of them crowds the window
    assert "gate.opened" in actions                      # the decision-grade event survives


# ── one body per test_case: no batching (Testing-phase bug 1) ───────
def _tc(world, *, title, s3_key, type="test_case"):
    return tools.register_artifact(
        world["t"].id, world["project"].id, world["run"].id, "testing", type, "internal",
        "sha256:x", s3_key=s3_key, title=title,
    )


def test_a_second_test_case_cannot_claim_another_test_cases_body(world):
    """Run b0e6557b registered 90 test cases against 4 batch bodies. Because the TestMgmt
    export derives an issue's summary FROM THE BODY and `create_test` is idempotent by summary,
    all 23 cases in a batch resolved to one summary and would have collapsed into a single Xray
    issue — 22 test cases silently lost. Registering the batch must fail loudly instead."""
    _tc(world, title="TC-001 — Register new account", s3_key="drafts/t/p/r/testing/tc-batch.md")
    with pytest.raises(ValueError, match="already claimed"):
        _tc(world, title="TC-002 — Duplicate email rejected",
            s3_key="drafts/t/p/r/testing/tc-batch.md")
    assert Artifact.objects.filter(run_id=world["run"].id, type="test_case").count() == 1


def test_the_error_tells_the_agent_what_to_do_instead(world):
    """The agent only recovers if the message names the offending body, the sibling holding it,
    and the fix — it is the sole feedback channel from a rejected MCP call."""
    _tc(world, title="TC-001 — Register new account", s3_key="drafts/t/p/r/testing/tc-batch.md")
    with pytest.raises(ValueError) as exc:
        _tc(world, title="TC-002 — Duplicate email rejected",
            s3_key="drafts/t/p/r/testing/tc-batch.md")
    message = str(exc.value)
    assert "tc-batch.md" in message                       # which body
    assert "TC-001 — Register new account" in message     # who already owns it
    assert "stage_artifact_body" in message               # what to do instead


def test_re_registering_the_same_test_case_reuses_its_own_body(world):
    """A retry/re-register of the SAME test case legitimately points at its own body — the
    version counter is title-scoped for exactly this. The guard must not block v2."""
    first = _tc(world, title="TC-001 — Register new account",
                s3_key="drafts/t/p/r/testing/tc-001.md")
    second = _tc(world, title="TC-001 — Register new account",
                 s3_key="drafts/t/p/r/testing/tc-001.md")
    assert first["version"] == 1 and second["version"] == 2


def test_each_test_case_with_its_own_body_is_accepted(world):
    """The intended shape: one staged body per test case."""
    _tc(world, title="TC-001 — Register new account", s3_key="drafts/t/p/r/testing/tc-001.md")
    _tc(world, title="TC-002 — Duplicate email rejected", s3_key="drafts/t/p/r/testing/tc-002.md")
    tcs = Artifact.objects.filter(run_id=world["run"].id, type="test_case")
    assert tcs.count() == 2
    assert tcs.values("s3_key").distinct().count() == 2      # the acceptance criterion


def test_the_guard_is_scoped_to_its_run(world):
    """A later run legitimately re-stages the same draft key (run-scoped paths collide only
    across runs when a caller passes an explicit key) — a different run must not be blocked."""
    from apps.runs.models import Run

    _tc(world, title="TC-001 — Register new account", s3_key="drafts/t/p/r/testing/tc-001.md")
    other = Run.objects.create(tenant=world["t"], work_item=world["wi"],
                               agent_spec=world["run"].agent_spec)
    created = tools.register_artifact(
        world["t"].id, world["project"].id, other.id, "testing", "test_case", "internal",
        "sha256:x", s3_key="drafts/t/p/r/testing/tc-001.md", title="TC-002 — Other run",
    )
    assert created["id"]


def test_other_types_may_still_share_a_body(world):
    """Deliberately narrow: only `test_case` is exported one-issue-per-artifact from its body,
    so only it carries this constraint. Nothing else changes behaviour."""
    _tc(world, title="Wireframe — Login", s3_key="drafts/t/p/r/ux/shared.html", type="wireframe")
    _tc(world, title="Wireframe — Signup", s3_key="drafts/t/p/r/ux/shared.html", type="wireframe")
    assert Artifact.objects.filter(run_id=world["run"].id, type="wireframe").count() == 2


def test_a_test_case_without_a_body_is_unaffected(world):
    """Pointer-only registrations (no s3_key) never trip the guard."""
    _tc(world, title="TC-001 — a", s3_key=None)
    _tc(world, title="TC-002 — b", s3_key=None)
    assert Artifact.objects.filter(run_id=world["run"].id, type="test_case").count() == 2


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


# ── S.No 183: identity is the stable id on the pointer, not the agent's title text ───────────
#
# Versioning keyed on (phase, type, title) where the title is free text the agent wrote. A
# retried phase that re-worded a title by one character forked a second artifact at v1 beside
# the first, instead of superseding it — while a stable id sat on the very same row, already
# read by the security defect loop, saying plainly it was the same finding.
def _finding(world, *, fid, title, content_hash="h"):
    t, project, run = world["t"], world["project"], world["run"]
    return tools.register_artifact(
        t.id, project.id, run.id, "security", "security_finding", "internal", content_hash,
        title=title, external_ref={"finding_id": fid, "severity": "critical"},
    )


def test_a_retry_whose_title_drifted_makes_a_new_version_not_a_duplicate(world):
    first = _finding(world, fid="SEC-001", title="SQL injection in login")
    retry = _finding(world, fid="SEC-001", title="SQL injection in the login form")

    assert first["version"] == 1
    assert retry["version"] == 2, "same finding, re-worded title — a version, not a duplicate"
    assert Artifact.objects.filter(type="security_finding").count() == 2   # v1 and v2 of ONE


def test_two_different_findings_in_one_run_each_start_at_v1(world):
    a = _finding(world, fid="SEC-001", title="SQL injection in login")
    b = _finding(world, fid="SEC-002", title="Missing rate limit on login")

    assert a["version"] == 1 and b["version"] == 1


def test_a_type_with_no_identity_key_still_versions_by_title(world):
    """Nothing that works today changes: a phase document has no stable id on its pointer and
    keeps versioning exactly as before."""
    t, project, run = world["t"], world["project"], world["run"]
    first = tools.register_artifact(t.id, project.id, run.id, "03_prd", "prd", "internal", "h1",
                                    title="PRD — Checkout")
    second = tools.register_artifact(t.id, project.id, run.id, "03_prd", "prd", "internal", "h2",
                                     title="PRD — Checkout")
    other = tools.register_artifact(t.id, project.id, run.id, "03_prd", "prd", "internal", "h3",
                                    title="PRD — Login")

    assert first["version"] == 1 and second["version"] == 2 and other["version"] == 1


def test_test_cases_version_on_their_tc_id(world):
    t, project, run = world["t"], world["project"], world["run"]
    first = tools.register_artifact(
        t.id, project.id, run.id, "testing", "test_case", "internal", "h1",
        title="TC-014 — Sign in with a valid password",
        external_ref={"tc_id": "TC-014"})
    retry = tools.register_artifact(
        t.id, project.id, run.id, "testing", "test_case", "internal", "h2",
        title="TC-014 — Signing in with a valid password",
        external_ref={"tc_id": "TC-014"})

    assert first["version"] == 1 and retry["version"] == 2


def test_a_caller_can_declare_its_own_identity_for_any_type(world):
    t, project, run = world["t"], world["project"], world["run"]
    first = tools.register_artifact(t.id, project.id, run.id, "04_architecture", "adr",
                                    "internal", "h1", title="ADR-003 — Use Postgres",
                                    external_ref={"identity": "ADR-003"})
    retry = tools.register_artifact(t.id, project.id, run.id, "04_architecture", "adr",
                                    "internal", "h2", title="ADR-003 — Postgres it is",
                                    external_ref={"identity": "ADR-003"})

    assert first["version"] == 1 and retry["version"] == 2


def test_code_pointers_are_deliberately_left_on_title_versioning(world):
    """The build registers several `code` pointers per run on purpose (the remediation cycles)
    and distinguishes them by PR ref, not by version. That path is not disturbed."""
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(t.id, project.id, run.id, "implementation", "code", "git", "h1",
                                title="Code — Add login",
                                external_ref={"repo": "acme/api", "number": 7, "id": "x"})
    b = tools.register_artifact(t.id, project.id, run.id, "implementation", "code", "git", "h2",
                                title="Code — Add login",
                                external_ref={"branch": "feature/ST-1"})

    assert a["version"] == 1 and b["version"] == 2   # title-scoped, exactly as before


def test_supersedes_reads_the_identity_off_its_target_and_carries_it_forward(world):
    """Naming the target explicitly must version it, whatever pointer the new registration
    happens to carry — and the new row keeps the identity so v3 does not start over."""
    t, project, run = world["t"], world["project"], world["run"]
    first = _finding(world, fid="SEC-001", title="SQL injection in login")

    second = tools.register_artifact(
        t.id, project.id, run.id, "security", "security_finding", "internal", "h2",
        external_ref={"severity": "critical"}, supersedes=first["id"])
    third = tools.register_artifact(
        t.id, project.id, run.id, "security", "security_finding", "internal", "h3",
        external_ref={"finding_id": "SEC-001", "severity": "critical"})

    assert second["version"] == 2
    assert second["external_ref"]["finding_id"] == "SEC-001"
    assert third["version"] == 3


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


def test_invalid_trace_rel_error_names_the_valid_values(world):
    """The valid set lived only in the model enum — not in the signature, not in a docstring,
    not in the error. Live in run 98ab9a8c the agent guessed NINE values before one stuck, then
    used that single value for every edge because it had no way to learn the others (B2)."""
    t, project, run = world["t"], world["project"], world["run"]
    a1 = tools.register_artifact(t.id, project.id, run.id, "p", "requirements", "internal", "h1")
    a2 = tools.register_artifact(t.id, project.id, run.id, "p", "prd", "internal", "h2")
    with pytest.raises(ValueError) as exc:
        tools.add_trace_edge(t.id, a1["id"], a2["id"], "documents")
    msg = str(exc.value)
    for valid in ("derives", "implements", "tests", "deploys"):
        assert valid in msg
    assert "documents" in msg          # says what was rejected, not just that something was


def test_add_trace_edge_tool_documents_its_vocabulary():
    """A docstring is the only place the agent can learn the four values before guessing."""
    from mcp_platform_state import server as state_server

    doc = state_server.add_trace_edge.__doc__ or ""
    for valid in ("derives", "implements", "tests", "deploys"):
        assert valid in doc


# ── B1: registration populates the Knowledge Index ──────────────────
def test_register_artifact_indexes_the_body_for_retrieval(world, monkeypatch):
    """Registration and retrieval were two steps and only ONE had a tool.

    Agent bodies say "index each artifact into the Knowledge Index"; no such tool is exposed,
    so no agent ever could. Measured after run 98ab9a8c published seven code-intelligence
    artifacts: KnowledgeChunk rows = 0 — every later phase would re-read the codebase instead
    of retrieving what this phase computed."""
    from apps.knowledge.models import KnowledgeChunk
    from storage.object_store import InMemoryObjectStore

    t, project, run = world["t"], world["project"], world["run"]
    store = InMemoryObjectStore()
    monkeypatch.setattr(tools, "_obj_store", lambda injected=None: store)
    ptr = tools.stage_artifact_body(
        t.id, project.id, run.id, "context_extraction", "intel",
        "Hotspot analysis found pkg/b.py churning fastest.", object_store=store)
    art = tools.register_artifact(
        t.id, project.id, run.id, "context_extraction", "codebase_intelligence",
        "internal", ptr["content_hash"], s3_key=ptr["s3_key"], title="Codebase Intelligence")

    chunks = KnowledgeChunk.objects.filter(tenant_id=t.id, artifact_id=art["id"])
    assert chunks.count() >= 1
    assert "hotspot" in chunks.first().text.lower()


def test_register_artifact_survives_a_knowledge_indexing_failure(world, monkeypatch):
    """Retrieval is an accelerator, never a correctness gate: an object-store hiccup must not
    fail a registration the agent already did the work for."""
    class Broken:
        def get(self, key):
            raise OSError("object store unavailable")

    t, project, run = world["t"], world["project"], world["run"]
    monkeypatch.setattr(tools, "_obj_store", lambda injected=None: Broken())
    art = tools.register_artifact(
        t.id, project.id, run.id, "p", "dependency_graph", "internal", "h",
        s3_key="drafts/whatever", title="Dependency Graph")
    assert art["id"]                     # registered anyway
    assert art["status"] == "draft"


def test_pointer_only_artifact_is_not_indexed(world, monkeypatch):
    """An artifact whose body lives in an external system-of-record has nothing local to chunk
    — and must not trigger an object-store read for a key it does not have."""
    from apps.knowledge.models import KnowledgeChunk

    def explode(injected=None):
        raise AssertionError("must not touch the object store for a pointer-only artifact")

    t, project, run = world["t"], world["project"], world["run"]
    monkeypatch.setattr(tools, "_obj_store", explode)
    art = tools.register_artifact(
        t.id, project.id, run.id, "p", "requirements", "confluence", "h", title="Reqs")
    assert KnowledgeChunk.objects.filter(tenant_id=t.id, artifact_id=art["id"]).count() == 0


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


def test_create_work_item_is_idempotent_on_rerun(world):
    """Bugs S.No 77: re-running Task Breakdown must REPLACE the proposed backlog, not duplicate
    it. Same (project, type, title, parent) among proposed items → update in place, one row."""
    t, project = world["t"], world["project"]
    first = tools.create_work_item(t.id, project.id, "task", "Set up CI", "initial description")
    again = tools.create_work_item(t.id, project.id, "task", "Set up CI", "revised description")

    assert again["id"] == first["id"], "re-run must reuse the existing proposed work item"
    assert again["description"] == "revised description"  # updated in place
    assert (
        WorkItem.objects.filter(
            tenant=t, project=project, type="task", title="Set up CI"
        ).count()
        == 1
    ), "no duplicate row created on re-run"


def test_create_work_item_does_not_touch_non_proposed(world):
    """The dedupe is scoped to PROPOSED items — an item already advanced (accepted/in-progress)
    is locked work and must not be overwritten; a same-title create makes a fresh proposed row."""
    t, project = world["t"], world["project"]
    made = tools.create_work_item(t.id, project.id, "task", "Locked task")
    tools.transition_work_item(t.id, made["id"], WorkItem.State.ACCEPTED)

    again = tools.create_work_item(t.id, project.id, "task", "Locked task")
    assert again["id"] != made["id"], "must not clobber a non-proposed (locked) work item"


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
                        "missing_required_artifacts", "recent_events", "retrieved_knowledge",
                        "answered_clarifications"}
    assert ctx["repo"] is None  # repo-less run → no per-repo scoping (D5)
    assert ctx["repositories"] == []  # no repos on this project → no assignment options
    assert ctx["profile"]["important_context"] == "ctx" and ctx["profile"]["version"] == 2
    assert len(ctx["relevant_artifacts"]) == 1
    # Dependency-driven provisioning (Bugs S.No 190): prd declares needs (requirements,
    # user_stories, ideation). The one registered `requirements` artifact is pinned as a
    # required input; the two undelivered types are surfaced as a named gap.
    assert ctx["relevant_artifacts"][0]["type"] == "requirements"
    assert ctx["relevant_artifacts"][0]["required"] is True
    assert set(ctx["missing_required_artifacts"]) == {"user_stories", "ideation"}
    assert len(ctx["recent_events"]) == 1
    assert ctx["retrieved_knowledge"] == []  # Phase 4
    assert ctx["answered_clarifications"] == []  # none asked yet


def test_get_context_pins_required_input_past_the_recency_tail(world):
    """Bugs S.No 190: a declared upstream input is guaranteed in the manifest even when many
    newer artifacts would push it out of a recency-capped window. cicd declares
    architecture/adr/security_review/test_report — only architecture is registered here, buried
    under 20 newer `code` artifacts."""
    t, project, run = world["t"], world["project"], world["run"]
    arch = tools.register_artifact(
        t.id, project.id, run.id, phase="architecture", type="architecture",
        sor="internal", content_hash="h", s3_key="k/arch",
    )
    for i in range(20):  # more than the situational-tail cap (12)
        tools.register_artifact(
            t.id, project.id, run.id, phase="implementation", type="code",
            sor="git", content_hash=f"h{i}", s3_key=f"k/c{i}",
        )
    ctx = tools.get_context(t.id, project.id, phase="cicd")
    arts = {a["id"]: a for a in ctx["relevant_artifacts"]}
    # the old architecture input is present and flagged required, despite 20 newer artifacts
    assert arch["id"] in arts and arts[arch["id"]]["required"] is True
    # its declared-but-absent siblings are surfaced as a named gap
    assert set(ctx["missing_required_artifacts"]) == {"adr", "security_review", "test_report"}
    # the situational tail is capped — the required input is never one of the capped-away items
    tail = [a for a in ctx["relevant_artifacts"] if not a["required"]]
    assert len(tail) <= 12


# ── G5: the Testing phase's declared inputs ─────────────────────────

def test_the_testing_phase_is_guaranteed_the_screen_inventory(world):
    """G5. Step 9 of the Testing agent writes one accessibility case PER SCREEN, and it reads the
    screen list from the UX phase. Neither `ux_design` nor `wireframe` was declared, so on a
    project with more than a dozen newer documents the list fell out of the recency tail and the
    agent wrote no accessibility cases at all — and a screen with no accessibility case is a
    screen nobody scans, for the rest of the lifecycle, silently.

    `ux_design` is the load-bearing one: 05 registers the Screen Inventory there, and registers
    `wireframe` one per SCREEN — so the required tier (latest of each type) pins exactly one
    wireframe. That is a pointer to enumerate from, never the list itself, which is why the
    agent body now says to enumerate with `list_artifacts(type="wireframe")`."""
    t, project, run = world["t"], world["project"], world["run"]
    ux = tools.register_artifact(
        t.id, project.id, run.id, phase="ux_design", type="ux_design",
        sor="internal", content_hash="h-ux", s3_key="k/ux",
    )
    wire = tools.register_artifact(
        t.id, project.id, run.id, phase="ux_design", type="wireframe",
        sor="internal", content_hash="h-w", s3_key="k/w",
    )
    for i in range(20):  # well past the situational-tail cap (12)
        tools.register_artifact(
            t.id, project.id, run.id, phase="implementation", type="code",
            sor="git", content_hash=f"h{i}", s3_key=f"k/c{i}",
        )
    ctx = tools.get_context(t.id, project.id, phase="testing")
    arts = {a["id"]: a for a in ctx["relevant_artifacts"]}
    assert arts[ux["id"]]["required"] is True
    assert arts[wire["id"]]["required"] is True
    tail = [a for a in ctx["relevant_artifacts"] if not a["required"]]
    assert len(tail) <= 12


def test_the_testing_phase_declares_every_input_its_body_reads(world):
    """The four that were also missing, folded in with G5 (team decision 2026-08-19): the body's
    own "Relevant Artifacts" header names user stories, the backlog, the definition of done and
    the security architecture, and each was subject to exactly the same eviction. Every type
    here has a producing agent — 02 registers `user_stories`, 04 `security_architecture`, 05
    `ux_design`/`wireframe`, 06 `backlog`/`definition_of_done`."""
    from apps.registry.catalog import needs_artifacts_for

    assert set(needs_artifacts_for("testing")) == {
        "prd", "requirements", "user_stories", "architecture", "security_architecture",
        "api_spec", "ux_design", "wireframe", "backlog", "definition_of_done"}


def test_a_project_with_no_ux_phase_names_the_gap_and_does_not_fail(world):
    """A backend service, or a brownfield project that has not run UX, has neither artifact. A
    declared type with no artifact is reported as a gap — never an error, never silence."""
    t, project = world["t"], world["project"]
    ctx = tools.get_context(t.id, project.id, phase="testing")
    assert {"ux_design", "wireframe"} <= set(ctx["missing_required_artifacts"])
    assert ctx["relevant_artifacts"] == []


def test_the_testing_body_says_where_the_screen_inventory_is(world):
    """Change 2. Two agent bodies disagreed: 05 puts the Screen Inventory in `ux_design` and
    registers wireframes one per screen, while 09's Step 9 called it "the `wireframe` artifacts'
    screen inventory" — so an agent handed a single wireframe pointer could reasonably write one
    case and stop."""
    body = (Path(__file__).resolve().parents[2] / "agents" / "09_testing" / "agent.md").read_text(
        encoding="utf-8")
    step9 = body.split("### Step 9: Accessibility Testing")[1].split("### Step 10")[0]
    assert "The **Screen Inventory** lives in the `ux_design` artifact" in step9
    assert 'list_artifacts(type="wireframe")' in step9
    assert "wireframe` artifacts' screen inventory" not in step9


def test_list_artifacts_filters_by_type(world):
    """Bugs S.No 191: an agent pulls a specific upstream input accurately by type."""
    t, project, run = world["t"], world["project"], world["run"]
    a = tools.register_artifact(t.id, project.id, run.id, phase="architecture",
                                type="architecture", sor="internal", content_hash="h1")
    tools.register_artifact(t.id, project.id, run.id, phase="implementation",
                            type="code", sor="git", content_hash="h2")
    listed = tools.list_artifacts(t.id, project.id, type="architecture")
    assert [x["id"] for x in listed] == [a["id"]]
    assert tools.list_artifacts(t.id, project.id, type="nonexistent") == []


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


def test_answered_clarifications_come_newest_first(world):
    """Truncation T13: the section is cut from the tail, so oldest-first threw away the latest
    human decision. Newest first means an overflow loses old context instead."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.clarifications.models import Clarification

    t, project, wi, run = world["t"], world["project"], world["wi"], world["run"]
    now = timezone.now()
    for qid, answered_at in (("old", now - timedelta(hours=4)), ("new", now)):
        Clarification.objects.create(
            tenant=t, run=run, work_item=wi, phase="prd",
            questions=[{"id": qid, "text": f"{qid}?"}], answers={qid: "yes"},
            status=Clarification.Status.ANSWERED, answered_at=answered_at,
        )

    ctx = tools.get_context(t.id, project.id, phase="prd", work_item_id=str(wi.id))
    assert [c["questions"][0]["id"] for c in ctx["answered_clarifications"]] == ["new", "old"]


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
    # B cannot read A's artifact. `get_artifact` answers a miss with a readable error rather
    # than raising — an agent that passed a shortened id needs telling, not a stack trace — so
    # what is asserted here is that B gets the ERROR and none of A's fields, not that it throws.
    denied = tools.get_artifact(t_b.id, a["id"])
    assert set(denied) == {"error"}          # the refusal, and none of A's artifact with it
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
        # State: context, artifacts, work items, trace, events.
        "get_context", "register_artifact", "stage_artifact_body", "get_artifact_body",
        "update_artifact", "add_trace_edge",
        "log_event", "list_work_items", "create_work_item", "transition_work_item",
        "get_artifact", "list_artifacts", "detect_drift",
        # Document vision (Part B): 00e reads a document's stored page images and the text
        # already extracted from it.
        "get_source_extraction", "get_page_images",
        # Code review (truncation register T4): read one file of the PR under review, a window
        # at a time, so a file too long to inline whole is still reviewable whole.
        "get_pr_file",
        # Accessibility judging (QA-02a / QA-11b): 09c reads its dispatched elements, the exact
        # WCAG wording and the captured crops, and answers one verdict per element.
        "get_a11y_batch", "get_a11y_screenshots", "get_wcag_grounding", "record_a11y_finding",
    }
    assert registered == expected


def test_a_declared_format_survives_the_tool_an_agent_actually_calls(world, monkeypatch):
    """The AGENT-facing surface must accept `format`, not merely the function behind it.

    Bugs S.No 187 gave `tools.register_artifact` a `format` parameter and told two agent bodies
    (04_architecture, 10_security) to pass it — but the MCP wrapper never declared it. FastMCP
    builds each tool's schema from the wrapper's signature and DISCARDS any argument missing
    from it, silently: no error, no warning, the declaration simply gone. A test that calls
    `tools.register_artifact(format=...)` passes either way, which is exactly why that one did
    while the agents' declarations were being dropped. This goes through the tool they call.

    It matters most for YAML and CSV: the platform recognises JSON and XML unaided, but refuses
    to guess at those two, so a declaration is the ONLY way they render as anything but prose.
    """
    from mcp_platform_state import server

    tool = next(t for t in asyncio.run(server.server.list_tools())
                if t.name == "register_artifact")
    assert "format" in tool.inputSchema["properties"]

    monkeypatch.setenv("PLATFORM_TENANT_ID", str(world["t"].id))
    monkeypatch.setenv("PLATFORM_PROJECT_ID", str(world["project"].id))
    monkeypatch.setenv("PLATFORM_RUN_ID", str(world["run"].id))
    out = server.register_artifact(
        phase="04_architecture", type="api_spec", sor="internal",
        content_hash="sha256:fmt", title="Orders API", format="yaml",
    )
    assert (Artifact.objects.get(id=out["id"]).external_ref or {}).get("format") == "yaml"
