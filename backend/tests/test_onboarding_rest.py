"""P4.7-T8 — brownfield onboarding REST (J17): wraps the existing onboarding services behind
`/api/projects/{id}/{onboarding,code-intel,gap-report}/`, backing S-24/S-25/S-26.

`code-intel` persists an **already-computed** analysis result (real companion-side dispatch is
deferred — see PHASE_4.7_BUILD_SPEC.md T8 notes) as a `codebase_intelligence` artifact +
Knowledge-Index chunk; `gap-report` POST (re)builds via `build_gap_report`, GET reads through the
latest one without recomputing; `onboarding` is the hub-state rollup.
"""
import pytest
from rest_framework.test import APIClient

from apps.integrations.models import SourceDocument
from apps.knowledge.models import KnowledgeChunk
from apps.projects.models import Project, Repository
from apps.registry.models import Artifact
from apps.runs.models import CodeIntelJob
from apps.tenancy.models import Membership, Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Legacy Billing",
                                  track=Project.Track.BROWNFIELD)


@pytest.fixture
def repo(project):
    return Repository.objects.create(tenant=project.tenant, project=project, name="acme/legacy")


@pytest.fixture
def tech_lead(tenant, project):
    u = User.objects.create_user(
        email="lead@acme.com", name="Lead", tenant=tenant, password="lead-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="tech_lead")
    return u


@pytest.fixture
def member(tenant, project):
    u = User.objects.create_user(
        email="dev@acme.com", name="Dev", tenant=tenant, password="dev-pass!"
    )
    Membership.objects.create(tenant=tenant, user=u, project=project, role="engineer")
    return u


def _login(client, email, password):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


def _hub_url(project):
    return f"/api/projects/{project.id}/onboarding/"


def _ci_url(project):
    return f"/api/projects/{project.id}/code-intel/"


def _gap_url(project):
    return f"/api/projects/{project.id}/gap-report/"


def _publish(project, type_):
    Artifact.objects.create(tenant=project.tenant, project=project, phase="onboarding",
                            type=type_, sor="internal", status="published")


def _index_code(project, repo, index=None, summary=""):
    """Create a codebase_intelligence artifact the way the COMPANION report sink does (B4). The
    web code-intel endpoint only *dispatches* now, so tests that need the artifact to already
    exist go through the sink directly (an InMemory store keeps them off MinIO)."""
    from integrations.onboarding import record_code_intel_index
    from storage import InMemoryObjectStore

    return record_code_intel_index(
        tenant_id=str(project.tenant_id), project_id=str(project.id), repo_id=str(repo.id),
        index=index or {"file_count": 1284, "commits": 412}, summary=summary,
        object_store=InMemoryObjectStore(),
    )


# ── code-intel (B4: the endpoint DISPATCHES; the companion report sink PERSISTS) ──
def test_code_intel_endpoint_dispatches_a_job_and_never_fabricates(client, project, repo,
                                                                   tech_lead):
    """B4-1/B4-2: the web endpoint dispatches a job (202) — it does NOT persist an artifact, and
    a client-supplied index is ignored (the fabrication path is closed)."""
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _ci_url(project),
        {"repo_id": str(repo.id), "index": {"file_count": 99999}},  # fabricated — must be ignored
        format="json",
    )
    assert resp.status_code == 202
    assert resp.data["status"] == "dispatched"
    # A pending job was created for the repo …
    job = CodeIntelJob.objects.get(id=resp.data["job_id"])
    assert job.status == CodeIntelJob.Status.PENDING and job.repo_id == repo.id
    # … and NOTHING was persisted from the client index.
    assert not Artifact.objects.filter(project=project, type="codebase_intelligence").exists()


def test_code_intel_report_sink_persists_artifact_and_chunk(client, project, repo):
    """The real artifact + Knowledge-Index chunk are created only via the companion report sink."""
    out = _index_code(project, repo,
                      summary="A legacy billing service exposing invoice + payment endpoints.")
    assert out["status"] == "indexed"
    artifact = Artifact.objects.get(id=out["artifact_id"])
    assert artifact.type == "codebase_intelligence"   # never "code" (no source copied)
    assert artifact.repo_id == repo.id
    chunks = KnowledgeChunk.objects.filter(artifact_id=artifact.id)
    assert chunks.exists() and chunks.first().source == "code_intel"


def test_code_intel_report_sink_without_summary_still_indexes_a_chunk(client, project, repo):
    out = _index_code(project, repo, index={"file_count": 12}, summary="")
    assert KnowledgeChunk.objects.filter(artifact_id=out["artifact_id"]).exists()


def test_admin_can_index_code(client, project, repo, tenant):
    User.objects.create_user(
        email="boss@acme.com", name="Boss", tenant=tenant,
        password="admin-pass!", is_tenant_admin=True,
    )
    _login(client, "boss@acme.com", "admin-pass!")
    resp = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert resp.status_code == 202


def test_member_cannot_index_code(client, project, repo, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.post(_ci_url(project), {"repo_id": str(repo.id)}, format="json")
    assert resp.status_code == 403


def test_code_intel_unknown_repo_is_404(client, project, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(
        _ci_url(project),
        {"repo_id": "00000000-0000-0000-0000-000000000000"}, format="json",
    )
    assert resp.status_code == 404


# ── gap report ───────────────────────────────────────────────────────
def test_gap_report_get_404_before_any_build(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get(_gap_url(project)).status_code == 404


def test_gap_report_post_dispatches_the_agent_when_a_companion_is_enrolled(
        client, project, tech_lead, monkeypatch):
    """S5-16 — the AGENT path had zero REST coverage. Every test here enrolled no companion, so
    every POST fell through `NoCompanionError` to the deterministic builder and the primary path
    was never exercised: nothing asserted 202, nothing asserted `mode == "agent"`.

    That matters beyond coverage — the deterministic fallback returns the whole report inline
    while the agent path returns a run id and finishes minutes later. A client that assumes the
    200 shape breaks the moment a companion is connected, which is the normal case."""
    from apps.registry.catalog import seed_agent_specs
    from apps.runs.enrollment import enroll_runner

    seed_agent_specs(project.tenant)
    enroll_runner(tenant_id=str(project.tenant_id), project_id=str(project.id),
                  developer_id=str(tech_lead.id), label="lead-laptop")
    # No Temporal in a REST test — capture the dispatch instead of starting a workflow.
    started = {}
    import orchestration.trigger as trigger_mod

    real = trigger_mod.trigger_phase
    monkeypatch.setattr(
        trigger_mod, "trigger_phase",
        lambda **kw: real(**{**kw, "workflow_starter": lambda wf, inp: started.update(inp=inp)}))

    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.post(_gap_url(project))
    assert resp.status_code == 202
    assert resp.data["mode"] == "agent" and resp.data["run_id"]
    # gated, not headless — a Product Owner owns the assessment (team decision 2026-08-03)
    assert started["inp"].auto_approve is False

    # A second click while that run is live is a 409, not a duplicate dispatch (S5-16). Two
    # concurrent assessments would race to write the same report and the loser would silently
    # overwrite the winner.
    second = client.post(_gap_url(project))
    assert second.status_code == 409
    assert "detail" in second.data


def test_a_carrier_gate_is_reachable_on_the_gates_screen(client, project, tech_lead):
    """Found LIVE on run 448b8d21, after I had reasoned it was safe. The gap report's gate opened
    correctly — and the Gates page said "No gates need you" while the sidebar badge said 1.

    Cause: the screen fetched every approval and kept only those whose work item appeared in the
    work-item LIST, which hides carriers by design. So the one gate hosted on a carrier was
    filtered out client-side. I checked `ApprovalViewSet` had no carrier exclusion and concluded
    the gate was reachable; I never checked what the CLIENT did with the response. A gate nobody
    can reach is worse than no gate — the run waits forever.

    The fix moves project scoping server-side (`?project=`) and ships the work item's title on the
    approval, so the screen never needs the backlog list to decide what a gate IS."""
    from apps.gates.models import Approval
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from integrations.onboarding import ensure_onboarding_work_item

    seed_agent_specs(project.tenant)
    wi = ensure_onboarding_work_item(tenant_id=str(project.tenant_id), project_id=str(project.id))
    run = Run.objects.create(
        tenant=project.tenant, work_item=wi, status=Run.Status.AWAITING_GATE,
        agent_spec=AgentSpec.objects.get(tenant=project.tenant, key="00_onboarding"))
    approval = Approval.objects.create(
        tenant=project.tenant, run=run, work_item=wi, gate_type="phase_gate",
        required_role="product_owner", decision="pending")

    _login(client, "lead@acme.com", "lead-pass!")
    resp = client.get(f"/api/approvals/?project={project.id}&decision=pending")
    assert resp.status_code == 200
    ids = [a["id"] for a in resp.data]
    assert str(approval.id) in ids, "the onboarding gate is invisible on the Gates screen"

    # …and it can name itself without the work-item list, which never contains a carrier
    row = next(a for a in resp.data if a["id"] == str(approval.id))
    assert row["work_item_title"] == "Onboarding — project assessment"

    # the project filter is a real filter, not a no-op
    other = client.get("/api/approvals/?project=00000000-0000-0000-0000-000000000000")
    assert other.status_code == 200 and other.data == []


def test_submit_gap_report_reaches_the_writer_through_the_runner_endpoint(
        client, project, tech_lead):
    """S5-16 — the whole agent write path end to end: the companion's MCP tool posts to
    `/api/runner/state/submit_gap_report/` with its Runner token, the view dispatches through
    `_BUILD_STATE_TOOLS` to `tools.submit_gap_report`, and the shared writer stores a report the
    UI can read. Every link in that chain was untested; only the innermost function had coverage,
    so a break at the allowlist, the view or the argument names would have surfaced live.

    This also pins the S5-3 run binding at the layer the agent actually calls from."""
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec, Artifact
    from apps.runs.enrollment import enroll_runner
    from apps.runs.models import Run
    from integrations.onboarding import ensure_onboarding_work_item, read_gap_report

    seed_agent_specs(project.tenant)
    _enrollment, token = enroll_runner(
        tenant_id=str(project.tenant_id), project_id=str(project.id),
        developer_id=str(tech_lead.id), label="lead-laptop")
    wi = ensure_onboarding_work_item(tenant_id=str(project.tenant_id), project_id=str(project.id))
    run = Run.objects.create(
        tenant=project.tenant, work_item=wi, status=Run.Status.RUNNING,
        agent_spec=AgentSpec.objects.get(tenant=project.tenant, key="00_onboarding"))

    resp = client.post(
        "/api/runner/state/submit_gap_report/",
        data={
            "project_id": str(project.id),
            "run_id": str(run.id),
            "phases": [
                {"phase": "ideation", "status": "complete",
                 "evidence": [{"artifact_id": "not-a-real-id", "type": "ideation"}]},
                {"phase": "requirements", "status": "partial"},
            ],
            "resume_phase": "requirements",
            "blockers": [],
        },
        format="json",
        HTTP_AUTHORIZATION=f"Runner {token}",
        HTTP_X_TENANT_ID=str(project.tenant_id),
    )
    assert resp.status_code in (200, 201), resp.data

    read = read_gap_report(tenant_id=str(project.tenant_id), project_id=str(project.id))
    by = {p["phase"]: p["assessment"] for p in read["phases"]}
    assert by["ideation"] == "complete" and by["requirements"] == "partial"
    assert by["prd"] == "missing"                       # omitted → missing, all 12 present
    assert read["resume_phase"] == "requirements"
    # bound to the run, which is what lets verify_writes see it and the gate publish it (S5-3)
    assert str(Artifact.objects.get(id=read["gap_report_id"]).run_id) == str(run.id)


def test_gap_report_resume_point_moves_as_evidence_is_added(client, project, repo, tech_lead):
    _login(client, "lead@acme.com", "lead-pass!")

    # nothing registered -> resume at the very first phase
    build0 = client.post(_gap_url(project))
    assert build0.status_code == 200
    assert build0.data["resume_phase"] == "ideation"
    get0 = client.get(_gap_url(project))
    assert get0.status_code == 200
    assert get0.data["resume_phase"] == "ideation"
    assert get0.data["phases"][0]["assessment"] == "missing"
    assert get0.data["intel_present"] is False

    # +requirements (ideation still missing) -> resume unchanged
    _publish(project, "ideation")
    _publish(project, "requirements")
    build1 = client.post(_gap_url(project))
    assert build1.data["resume_phase"] == "prd"
    by_phase = {p["phase"]: p["assessment"] for p in build1.data["phases"]}
    assert by_phase["ideation"] == "complete" and by_phase["requirements"] == "complete"

    # +prd -> resume moves to architecture
    _publish(project, "prd")
    build2 = client.post(_gap_url(project))
    assert build2.data["resume_phase"] == "architecture"
    assert "architecture" in build2.data["blocking"]

    # +intel (via the companion report sink; B4 endpoint only dispatches) -> intel_present flips
    _index_code(project, repo)
    build3 = client.post(_gap_url(project))
    assert build3.data["intel_present"] is True

    get3 = client.get(_gap_url(project))
    assert get3.data["resume_phase"] == build3.data["resume_phase"]
    assert get3.data["intel_present"] is True


def test_gap_report_evidence_carries_artifact_refs(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    _publish(project, "ideation")
    client.post(_gap_url(project))
    resp = client.get(_gap_url(project))
    ideation = next(p for p in resp.data["phases"] if p["phase"] == "ideation")
    assert ideation["assessment"] == "complete"
    assert ideation["evidence"] and ideation["evidence"][0]["type"] == "ideation"


# ── onboarding hub ───────────────────────────────────────────────────
def test_onboarding_hub_shape_before_anything(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_hub_url(project))
    assert resp.status_code == 200
    assert set(resp.data.keys()) == {"upload", "adopt", "register", "index", "gap",
                                     "adopt_types", "a11y"}
    # A brownfield project has pages the platform cannot discover — it has no access to the
    # running application, deliberately — so the accessibility step starts at "nobody has told
    # us yet" rather than at "nothing found" (task 8a).
    a11y = resp.data["a11y"]
    assert a11y["routes_registered"] == 0 and a11y["audits_run"] == 0
    assert a11y["running"] is False and a11y["status"] == "not_started"
    assert resp.data["upload"] == [] and resp.data["adopt"] == []
    # Assert the MEANING, not the exact dict (S5-18): both steps grew keys after this test was
    # written — `index.repos` for the per-repo cards, and `running`/`run_id`/`question` so the hub
    # can show a live agent run. A strict `==` here failed on additions that were correct, which is
    # the same trap the S4-9 rewrite hit.
    assert resp.data["index"]["status"] == "not_started"
    assert resp.data["index"]["artifact_id"] is None
    assert resp.data["index"]["repos"] == []
    assert resp.data["gap"]["ready"] is False
    assert resp.data["gap"]["running"] is False
    assert resp.data["gap"]["run_id"] is None and resp.data["gap"]["question"] is None
    assert resp.data["register"]["pages_registered"] == 0
    # Nothing connected yet, so there is no vendor to name. The onboarding step used to say
    # "Connect Jira" here while the pop-up behind it asked which vendor to use — the button was
    # offering a choice the user had not made. None is what keeps the screen honest.
    assert resp.data["register"]["tasktracker_vendor"] is None
    assert resp.data["register"]["docstore_vendor"] is None
    assert resp.data["register"]["designsource_vendor"] is None
    # Served adopt vocabulary: humanized "Type (Phase)", full lifecycle minus implementation.
    types = resp.data["adopt_types"]
    assert {"value", "label", "phase", "phase_label"} <= set(types[0].keys())
    assert any(t["label"] == "Wireframe (UX Design)" for t in types)
    assert all(t["value"] != "code" for t in types)


def test_onboarding_hub_names_the_vendor_once_one_is_connected(client, project, member):
    """Before connecting, the step offers a capability; after, it names the real tool.

    Both halves matter. "Connect Jira" before the user chose a vendor was the reported bug, but
    "Import task tracker backlog" after they plainly connected Jira would be its own kind of
    unhelpful. The screen can only tell them apart if the server says which vendor it is, so
    this is the field that lets the label be right on the day a second tracker exists rather
    than hardcoded to the only one that exists today.
    """
    from apps.integrations.models import IntegrationConnection

    IntegrationConnection.objects.create(
        tenant=project.tenant, capability="tasktracker", connector="jira",
        token_ref="vault://x", secret_encrypted="enc",
    )
    _login(client, "dev@acme.com", "dev-pass!")

    register = client.get(_hub_url(project)).data["register"]

    assert register["tasktracker_connected"] is True
    assert register["tasktracker_vendor"] == "Jira"      # the catalog's label, not the slug
    # The other two are untouched — one connection must not make the whole step claim vendors.
    assert register["docstore_vendor"] is None
    assert register["designsource_vendor"] is None


def test_onboarding_hub_does_not_name_a_half_finished_connection(client, project, member):
    """A row with no secret stored is not a connection. `is_configured` already governs the
    `*_connected` flags; the vendor name has to follow the same rule or the step would name a
    tool it cannot actually reach."""
    from apps.integrations.models import IntegrationConnection

    IntegrationConnection.objects.create(
        tenant=project.tenant, capability="tasktracker", connector="jira", token_ref="",
    )
    _login(client, "dev@acme.com", "dev-pass!")

    register = client.get(_hub_url(project)).data["register"]

    assert register["tasktracker_connected"] is False
    assert register["tasktracker_vendor"] is None


def test_onboarding_hub_reflects_uploads_index_and_gap(client, project, repo, tech_lead):
    SourceDocument.objects.create(tenant=project.tenant, project=project, filename="spec.docx",
                                  mime="application/msword",
                                  status=SourceDocument.Status.EXTRACTED)
    SourceDocument.objects.create(tenant=project.tenant, project=project, filename="nfrs.xlsx",
                                  mime="application/vnd.ms-excel",
                                  status=SourceDocument.Status.ADOPTED)
    _login(client, "lead@acme.com", "lead-pass!")

    _index_code(project, repo)
    client.post(_gap_url(project))

    resp = client.get(_hub_url(project))
    assert len(resp.data["upload"]) == 2
    assert len(resp.data["adopt"]) == 1 and resp.data["adopt"][0]["filename"] == "spec.docx"
    assert resp.data["index"]["status"] == "indexed"
    assert resp.data["gap"]["ready"] is True and resp.data["gap"]["resume_phase"] == "ideation"


# ── tenant isolation ─────────────────────────────────────────────────
def test_onboarding_surfaces_are_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    # Brownfield on both sides: this test is about tenant isolation, and a greenfield project
    # is now refused for a different reason (S.No 221), which would mask what it is checking.
    p1 = Project.objects.create(tenant=t1, name="P1", track=Project.Track.BROWNFIELD)
    p2 = Project.objects.create(tenant=t2, name="P2", track=Project.Track.BROWNFIELD)
    User.objects.create_user(
        email="a1@acme.com", name="A1", tenant=t1, password="pw!", is_tenant_admin=True
    )
    User.objects.create_user(
        email="a2@globex.com", name="A2", tenant=t2, password="pw!", is_tenant_admin=True
    )
    _publish(p1, "ideation")

    c = APIClient()
    _login(c, "a1@acme.com", "pw!")
    assert c.get(_hub_url(p1)).status_code == 200
    # cross-tenant project id is invisible under this admin's session (RLS/tenant scoping)
    assert c.get(_hub_url(p2)).status_code == 404


# ── the accessibility step, while an audit is actually running ───────────────
#
# The step counted a `judging` audit as run, and then said "1 audit run — open the report from
# Artifacts" while the audit was still going. There is no report to open until the judging ends:
# the baseline is published when the judge run closes, deliberately, so that it never states a
# position that is still changing. Seen on the live run of 21 August.


def _an_audit(project, status):
    from apps.a11y.models import A11yBaselineAudit, A11yRoute

    A11yRoute.objects.get_or_create(
        tenant=project.tenant, project=project, path="/",
        defaults={"label": "Home", "enabled": True})
    return A11yBaselineAudit.objects.create(
        tenant=project.tenant, project=project, base_url="http://localhost:4180",
        routes=["/"], status=status)


def test_an_audit_still_running_is_not_reported_as_a_finished_one(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    _an_audit(project, "judging")

    a11y = client.get(_hub_url(project)).data["a11y"]

    assert a11y["status"] == "running", "it is going, not done"
    assert a11y["running"] is True
    assert a11y["audits_run"] == 0, "nothing to open from Artifacts yet"


def test_a_finished_audit_makes_the_step_done(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    _an_audit(project, "complete")

    a11y = client.get(_hub_url(project)).data["a11y"]

    assert a11y["status"] == "done"
    assert a11y["audits_run"] == 1
    assert a11y["running"] is False


def test_a_finished_audit_stays_finished_while_the_next_one_runs(client, project, member):
    """Both facts are true at once, so both are carried. The tick does not flicker back off
    because somebody started another audit."""
    _login(client, "dev@acme.com", "dev-pass!")
    _an_audit(project, "complete")
    _an_audit(project, "capturing")

    a11y = client.get(_hub_url(project)).data["a11y"]

    assert a11y["status"] == "done" and a11y["audits_run"] == 1
    assert a11y["running"] is True


def test_an_audit_that_could_not_run_leaves_the_step_where_it_was(client, project, member):
    """A failed audit is not a finished one and is not a running one. With pages registered the
    step is simply ready again, which is the true thing to say."""
    _login(client, "dev@acme.com", "dev-pass!")
    _an_audit(project, "failed")

    a11y = client.get(_hub_url(project)).data["a11y"]

    assert a11y["status"] == "ready"
    assert a11y["audits_run"] == 0 and a11y["running"] is False


# ── S.No 221: onboarding is brownfield-only, at the endpoint as well as in the nav ──
def test_hub_refuses_a_greenfield_project(client, tenant, member):
    """Hiding the sidebar item is not the same as closing the door — `/onboarding` is still a
    URL that can be typed or bookmarked from another project, and this endpoint would have
    happily reported on a codebase that does not exist. A greenfield project is the ONLY
    thing that changes here; the same member, on the same workspace, is still let through
    to a brownfield project below, so this cannot pass by refusing everyone."""
    greenfield = Project.objects.create(tenant=tenant, name="New Service")
    Membership.objects.create(tenant=tenant, user=member, project=greenfield, role="engineer")
    _login(client, "dev@acme.com", "dev-pass!")

    resp = client.get(_hub_url(greenfield))

    assert resp.status_code == 403
    # The refusal has to say WHY, or it reads as a permissions problem the person could fix.
    assert "brownfield" in str(resp.data["detail"]).lower()


def test_hub_still_serves_a_brownfield_project(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    assert client.get(_hub_url(project)).status_code == 200
