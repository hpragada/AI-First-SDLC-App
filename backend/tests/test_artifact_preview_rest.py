"""P4.7-T10 — artifact preview read-through (J19, DECISION-5): wraps `read_artifact_preview`
behind `GET /api/artifacts/{id}/preview/`, backing S-28 (list, pointers only) / S-29 (preview).

The body is fetched **on demand** — never persisted onto the registry row: internal (draft/
staged, not yet pushed) reads its S3 body; confluence/jira read live through their capability
(`DocStore.get_page`/`TaskTracker.get_issue` — themselves "read-through, not stored"); any
other SoR (or an unavailable connector) still returns the pointer/version + a deep-link, no body.
"""
from types import SimpleNamespace

import pytest
from rest_framework.test import APIClient

from apps.integrations.models import IntegrationConnection
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User
from integrations.registry import _BUILDERS, register_connector
from storage import s3_from_settings


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def tenant(db):
    return Tenant.objects.create(name="Acme")


@pytest.fixture
def project(tenant):
    return Project.objects.create(tenant=tenant, name="Payments")


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


def _preview_url(artifact_id):
    return f"/api/artifacts/{artifact_id}/preview/"


def _list_url():
    return "/api/artifacts/"


# ── internal (S3 read-through) ───────────────────────────────────────
def test_preview_internal_artifact_returns_stored_body(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/prd.md"
    store.put(key, "# PRD\nSome content.")
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# PRD\nSome content."
    assert resp.data["content_type"] == "text/markdown"
    assert resp.data["status"] == "draft"
    assert resp.data["version"] == 1
    assert resp.data["sor_link"] is None


def test_preview_internal_artifact_reads_inline_external_ref_body(client, project, member):
    """Bugs.xlsx row 22: agents register internal drafts with the body inline in
    external_ref.body and no s3_key yet. Preview must read that draft body through instead
    of 404-ing 'artifact has no body to preview'."""
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="ideation", type="assumption",
        sor="internal", status="draft", s3_key="", version=1,
        external_ref={"title": "Assumptions Register", "format": "markdown",
                      "body": "# Assumptions\nSome draft content."},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# Assumptions\nSome draft content."
    assert resp.data["content_type"] == "text/markdown"


def test_preview_multistate_wireframe_returns_states_and_default_body(project, member):
    """A per-screen wireframe carries one HTML document per UI state in external_ref.states.
    The preview surfaces every state (read-through) and defaults the primary body to the
    'default' state so the switcher and the top-level body both render."""
    from integrations.preview import read_artifact_preview
    from storage.object_store import InMemoryObjectStore

    store = InMemoryObjectStore()
    tenant = project.tenant
    dk = f"drafts/{tenant.id}/{project.id}/r/ux/SCR-001-login-state-1-default.html"
    ek = f"drafts/{tenant.id}/{project.id}/r/ux/SCR-001-login-state-4-error.html"
    store.put(dk, "<html>DEFAULT</html>", content_type="text/html")
    store.put(ek, "<html>ERROR</html>", content_type="text/html")
    artifact = Artifact.objects.create(
        tenant=tenant, project=project, phase="ux_design", type="wireframe",
        sor="internal", status="draft", s3_key=dk, version=1,
        external_ref={"screen_id": "SCR-001", "route": "/auth/login", "states": [
            {"name": "state-1-default", "s3_key": dk},
            {"name": "state-4-error", "s3_key": ek},
        ]},
    )
    payload = read_artifact_preview(
        tenant_id=str(tenant.id), artifact_id=str(artifact.id), object_store=store)
    assert payload is not None
    assert [s["name"] for s in payload["states"]] == ["state-1-default", "state-4-error"]
    assert "ERROR" in payload["states"][1]["body"]
    assert payload["states"][1]["content_type"] == "text/html"
    # primary body is the default state
    assert "DEFAULT" in payload["body"]


def test_preview_missing_internal_body_says_so_instead_of_404(client, project, member, caplog):
    """CHANGED for Bugs S.No 218. This used to assert a 404 — the same answer as "no such
    artifact" — and the screen worded that 404 as "doesn't exist, has no body, or you don't have
    access to it": three explanations, one true, none actionable. The artifact exists, so it
    answers normally with an empty body and the screen shows "Preview unavailable". The fault
    behind it is ours, so it goes to the server log rather than to the person."""
    import logging

    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    with caplog.at_level(logging.WARNING, logger="integrations.preview"):
        resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""
    assert resp.data["status"] == "draft"
    assert not resp.data["sor_link"]
    assert str(artifact.id) in caplog.text


def test_a_publish_still_never_sees_an_empty_body_as_a_body(project):
    """`allow_empty` is the preview endpoint's alone. Everything else keeps the old contract, so
    an export can never push an empty page."""
    from integrations.preview import read_artifact_preview

    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="approved", s3_key="", version=1,
    )
    assert read_artifact_preview(
        tenant_id=str(project.tenant_id), artifact_id=str(artifact.id)) is None


def _run_for(project, phase="ideation", outputs=None):
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    wi = WorkItem.objects.create(tenant=project.tenant, project=project,
                                 type=WorkItem.Type.STORY)
    spec = AgentSpec.objects.create(tenant=project.tenant, key=f"01_{phase}",
                                    body_ref="x", phase_label=phase)
    return Run.objects.create(tenant=project.tenant, work_item=wi, agent_spec=spec,
                              status="completed", outputs=outputs or {})


def test_preview_renders_structured_external_ref(client, project, member):
    """Run 7f67d88a incident: agents register sub-artifacts whose CONTENT is structured
    JSON in external_ref (the MCP tool is pointers-only — there is no other body channel).
    Preview must render that content generically, for every artifact type of every phase."""
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="ideation", type="assumption",
        sor="internal", status="draft", s3_key="", version=1,
        external_ref={
            "title": "Assumptions Register — SpendLog Ideation Phase",
            "project": "SpendLog-Test-2.1",          # pointer — must NOT render
            "work_item_id": "8d6f3b7d",              # pointer — must NOT render
            "total_tier3_inferences": 2,
            "zero_inference_count": False,
            "tier3_inferences": [
                {"id": "ASM-001", "statement": "Mint's shutdown created a gap",
                 "risk": "Medium", "used_in": ["ideation", "competitive_analysis"]},
                {"id": "ASM-002", "statement": "5% conversion is reasonable",
                 "risk": "High", "used_in": ["market_sizing"]},
            ],
        },
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    body = resp.data["body"]
    assert resp.data["content_type"] == "text/markdown"
    assert "# Assumptions Register — SpendLog Ideation Phase" in body
    assert "### ASM-001" in body and "### ASM-002" in body
    assert "Mint's shutdown created a gap" in body
    assert "**Used in:** ideation, competitive_analysis" in body
    assert "**Total tier3 inferences:** 2" in body
    assert "SpendLog-Test-2.1" not in body and "8d6f3b7d" not in body


def test_preview_prefers_own_structured_ref_over_run_fallback(client, project, member):
    """A sub-artifact with its own structured content must preview THAT content, not the
    run's whole phase document."""
    run = _run_for(project, outputs={"report": {"body": "# whole phase doc", "status": "ok"}})
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, run=run, phase="ideation",
        type="stakeholder_map", sor="internal", status="draft", s3_key="", version=1,
        external_ref={"stakeholders": [{"name": "PO", "role": "approver"}]},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert "PO" in resp.data["body"]
    assert "whole phase doc" not in resp.data["body"]


def test_preview_pointer_only_external_ref_still_uses_run_fallback(client, project, member):
    """An external_ref holding nothing but pointers renders no structured body — the run
    fallback chain must still apply (regression guard for the row-59 behavior)."""
    run = _run_for(project, outputs={"report": {"body": "# phase doc", "status": "ok"}})
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, run=run, phase="ideation",
        type="market_sizing", sor="internal", status="draft", s3_key="", version=1,
        external_ref={"title": "", "project": "SpendLog", "work_item_id": "8d6f3b7d"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# phase doc"


def test_render_structured_ref_units():
    from integrations.preview import render_structured_ref

    assert render_structured_ref(None) == ""
    assert render_structured_ref({}) == ""
    assert render_structured_ref({"url": "x", "id": "1", "sor": "internal"}) == ""
    out = render_structured_ref({"title": "T", "notes": ["a", "b"],
                                 "summary": {"state": "ok", "count": 3}})
    assert "# T" in out
    assert "## Notes" in out and "- a" in out and "- b" in out
    assert "## Summary" in out and "- **State:** ok" in out and "- **Count:** 3" in out


def test_preview_falls_back_to_run_report_body(client, project, member):
    """Bugs.xlsx row 59: an agent-registered pointer (no s3_key, no inline body) must read
    through to the body of the run it came from instead of 404-ing 'Artifact not found'."""
    run = _run_for(project, outputs={"report": {"body": "# Ideation\nfull phase output",
                                                "status": "ok"}})
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, run=run, phase="ideation",
        type="market_sizing", sor="internal", status="published", s3_key="", version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# Ideation\nfull phase output"
    assert resp.data["content_type"] == "text/markdown"


def test_preview_prefers_runs_staged_draft_over_raw_report(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/staged-ideation.md"
    store.put(key, "# Staged draft")
    run = _run_for(project, outputs={"artifact_s3_key": key,
                                     "report": {"body": "raw report", "status": "ok"}})
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, run=run, phase="ideation",
        type="assumption", sor="internal", status="published", s3_key="", version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == "# Staged draft"


def test_preview_missing_s3_object_degrades_not_500(client, project, member):
    """A pointer at an S3 key that no longer exists must degrade, never crash the endpoint with
    an unhandled boto error (Bugs.xlsx row 59). Degrading now means an empty body rather than a
    404 (S.No 218) — the document exists; it is its body that cannot be read."""
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="test-preview/definitely-missing.md",
        version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""


def test_preview_unknown_artifact_is_404(client, project, member):
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url("00000000-0000-0000-0000-000000000000"))
    assert resp.status_code == 404


# ── external SoR (read-through via capability) ───────────────────────
def test_preview_confluence_artifact_reads_through_docstore(client, project, member):
    page = SimpleNamespace(
        id="123", title="Multi-Currency Requirements", body_html="<p>Live body</p>",
        version=2, url="https://acme.atlassian.net/wiki/123", space_key="SDLC",
    )
    register_connector("docstore", "test_fake", lambda conn: SimpleNamespace(
        get_page=lambda *, page_ref: page
    ))
    try:
        IntegrationConnection.objects.create(
            tenant=project.tenant, capability="docstore", connector="test_fake",
        )
        artifact = Artifact.objects.create(
            tenant=project.tenant, project=project, phase="onboarding", type="document",
            sor="confluence", status="published", version=2,
            external_ref={"sor": "confluence", "id": "123", "url": "https://old-link/123"},
        )
        _login(client, "dev@acme.com", "dev-pass!")
        resp = client.get(_preview_url(artifact.id))
        assert resp.status_code == 200
        assert resp.data["body"] == "<p>Live body</p>"
        assert resp.data["content_type"] == "text/html"
        # the live page's URL wins over the stored external_ref url
        assert resp.data["sor_link"] == "https://acme.atlassian.net/wiki/123"
    finally:
        _BUILDERS.pop(("docstore", "test_fake"), None)


def test_preview_falls_back_to_link_when_capability_unavailable(client, project, member):
    """No docstore connector configured for this tenant → graceful degrade (S-29 'Preview
    unavailable'): the pointer/version/link still return, just without a body."""
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="onboarding", type="document",
        sor="confluence", status="published", version=1,
        external_ref={"sor": "confluence", "id": "999", "url": "https://acme.atlassian.net/999"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""
    assert resp.data["sor_link"] == "https://acme.atlassian.net/999"


def test_preview_other_sor_returns_link_only(client, project, member):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="implementation", type="code",
        sor="git", status="published", version=1,
        external_ref={"sor": "git", "repo": "acme/payments-api", "number": 42,
                      "url": "https://github.com/acme/payments-api/pull/42"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(artifact.id))
    assert resp.status_code == 200
    assert resp.data["body"] == ""
    assert resp.data["sor_link"] == "https://github.com/acme/payments-api/pull/42"


# ── version history (sibling revisions) ──────────────────────────────
def test_preview_versions_lists_sibling_revisions(client, project, member):
    store = s3_from_settings()
    ids = []
    for v in (1, 2, 3):
        key = f"test-preview/{project.tenant_id}/{project.id}/prd-v{v}.md"
        store.put(key, f"v{v} body")
        art = Artifact.objects.create(
            tenant=project.tenant, project=project, phase="prd", type="prd",
            sor="internal", status="draft", s3_key=key, version=v,
        )
        ids.append(str(art.id))
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(ids[-1]))
    assert resp.status_code == 200
    versions = resp.data["versions"]
    assert len(versions) == 3
    assert {v["artifact_id"] for v in versions} == set(ids)
    # newest-first
    assert versions[0]["created_at"] >= versions[-1]["created_at"]


# ── access control ────────────────────────────────────────────────────
def test_preview_unauthenticated_is_403(client, project):
    artifact = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )
    assert client.get(_preview_url(artifact.id)).status_code == 403


def test_artifact_list_payload_carries_no_body(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/list-check.md"
    store.put(key, "body should never leak into the list")
    Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_list_url())
    assert resp.status_code == 200
    for row in resp.data:
        assert "body" not in row
        assert "versions" not in row
        assert "sor_link" not in row


def test_preview_is_tenant_isolated(client, db):
    t1 = Tenant.objects.create(name="Acme")
    t2 = Tenant.objects.create(name="Globex")
    p1 = Project.objects.create(tenant=t1, name="P1")
    p2 = Project.objects.create(tenant=t2, name="P2")
    u2 = User.objects.create_user(email="dev@globex.com", name="Dev2", tenant=t2, password="pw!")
    Membership.objects.create(tenant=t2, user=u2, project=p2, role="engineer")
    artifact = Artifact.objects.create(
        tenant=t1, project=p1, phase="prd", type="prd",
        sor="internal", status="draft", s3_key="", version=1,
    )

    c = APIClient()
    _login(c, "dev@globex.com", "pw!")
    resp = c.get(_preview_url(artifact.id))
    assert resp.status_code == 404  # cross-tenant artifact is invisible under this session


# ── the list must say whether Preview can show anything (Artifacts preview bug) ──────────────
# A row with neither a body nor a link opened a blank page, or — for an internal one — a 404 the
# UI words as "this artifact doesn't exist, has no body, or you don't have access to it", which
# reads like a permissions problem when it is nothing of the kind. `previewable` lets the UI stop
# offering the button, and is computed beside `read_artifact_preview` so the two cannot drift.
def _artifact(project, **over):
    base = dict(tenant=project.tenant, project=project, phase="implementation", type="code",
                sor="internal", status="draft", version=1)
    base.update(over)
    return Artifact.objects.create(**base)


def test_previewable_is_false_only_when_there_is_nothing_to_show(client, project, member):
    from integrations.preview import artifact_has_preview

    # the TASK-019 shape: internal, registered with a hash and no body — unpreviewable
    assert artifact_has_preview(
        _artifact(project, type="code_review", content_hash="d1")) is False
    # ...and the same row once its body is staged
    assert artifact_has_preview(
        _artifact(project, type="code_review", s3_key="drafts/x/review.md")) is True
    # a `code` pointer at a PR carries no body BY DESIGN (#1/#3) — the preview is the link
    assert artifact_has_preview(_artifact(
        project, sor="git", external_ref={"sor": "git", "repo": "a/b", "number": 7,
                                          "url": "https://github.com/a/b/pull/7"})) is True
    # ...but a pre-PR pointer with no link has nothing to open
    assert artifact_has_preview(_artifact(
        project, sor="git", external_ref={"sor": "git", "branch": "feature/x"})) is False
    # a wireframe keeps its bodies per state, with no s3_key of its own — still previewable
    assert artifact_has_preview(_artifact(
        project, type="wireframe",
        external_ref={"states": [{"name": "default", "s3_key": "drafts/x/s1.html"}]})) is True
    # Confluence/Jira read through their connector, so there is always something to show
    assert artifact_has_preview(_artifact(
        project, sor="confluence", external_ref={"page_ref": "123"})) is True


def test_the_artifact_list_carries_previewable(client, project, member):
    _artifact(project, type="code_review", content_hash="d1")
    _artifact(project, type="code_review", s3_key="drafts/x/review.md")
    _login(client, "dev@acme.com", "dev-pass!")

    payload = client.get(_list_url()).json()
    rows = payload["results"] if isinstance(payload, dict) else payload

    flags = sorted(r["previewable"] for r in rows)
    assert flags == [False, True], "the UI cannot hide the button without this"


def test_a_row_the_list_calls_previewable_actually_previews(client, project, member):
    """Guard the guard: the flag has to agree with the endpoint, or we have simply moved the
    confusion from one screen to another."""
    store = s3_from_settings()
    key = f"test-previewable/{project.tenant_id}/{project.id}/review.md"
    store.put(key, "# Review")
    good = _artifact(project, type="code_review", s3_key=key)
    bad = _artifact(project, type="code_review", content_hash="d1")
    _login(client, "dev@acme.com", "dev-pass!")

    assert client.get(_preview_url(good.id)).data["body"] == "# Review"
    # Not previewable, and the endpoint agrees: it exists, and there is nothing to show
    # (S.No 218 — this was a 404 before, the same answer as a document that does not exist).
    resp = client.get(_preview_url(bad.id))
    assert resp.status_code == 200 and resp.data["body"] == ""


# ── S.No 187: the SBOM renders for people, and ONLY for people ──────
_SBOM_JSON = (
    '{"bomFormat":"CycloneDX","specVersion":"1.5",'
    '"metadata":{"timestamp":"2026-09-04T11:22:08Z",'
    '"tools":{"components":[{"name":"syft","version":"1.9.0"}]}},'
    '"components":[{"type":"library","name":"django","version":"5.1.4",'
    '"licenses":[{"license":{"id":"BSD-3-Clause"}}]}]}'
)


@pytest.fixture
def sbom(project):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/sbom.json"
    store.put(key, _SBOM_JSON)
    return Artifact.objects.create(
        tenant=project.tenant, project=project, phase="security", type="sbom",
        sor="internal", status="draft", s3_key=key, version=1, title="SBOM",
    )


def test_sbom_previews_as_a_readable_inventory(client, sbom, member):
    """Bugs S.No 187: the preview announced every internal body as markdown whatever was in
    it, so the CycloneDX JSON went to the prose renderer and came out as one run-on blob."""
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(sbom.id))
    assert resp.status_code == 200
    assert resp.data["rendered"] is True
    assert resp.data["content_type"] == "text/markdown"
    assert "| django | 5.1.4 | BSD-3-Clause | library |" in resp.data["body"]
    assert "bomFormat" not in resp.data["body"]          # not the raw file
    # The headline figures ride alongside, structured, for the labelled-number layout.
    assert resp.data["render_summary"]["components"] == 1
    assert resp.data["render_summary"]["tool"] == "syft 1.9.0"
    assert resp.data["render_summary"]["taken"] == "2026-09-04T11:22:08Z"


def test_raw_returns_the_stored_file_byte_for_byte(client, sbom, member):
    """The raw file is kept — `?raw=1` is how a person can actually see it."""
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(sbom.id) + "?raw=1")
    assert resp.status_code == 200
    assert resp.data["body"] == _SBOM_JSON
    assert resp.data["content_type"] == "application/json"
    assert resp.data["rendered"] is False


def test_agents_and_publish_still_receive_the_raw_bytes(sbom):
    """THE REGRESSION GUARD. Three callers share the internal read and only ONE may see a
    rendered body. Rendering for an agent would hand it a markdown table where it asked for
    parseable JSON; rendering for publish would push a table to Confluence where the SBOM
    belongs. Both must stay byte-identical to what was stored."""
    from integrations.preview import artifact_body_for_agent, internal_draft_body

    assert internal_draft_body(sbom) == _SBOM_JSON
    for_agent = artifact_body_for_agent(sbom)
    assert for_agent["body"] == _SBOM_JSON
    assert for_agent["content_type"] == "application/json"


def test_json_that_is_not_an_sbom_is_shown_as_json_not_guessed_at(client, project, member):
    """The renderer is keyed on the artifact TYPE, so an unrelated JSON body is left as JSON
    rather than pushed through whichever renderer matched first. It is still legible: the
    preview screen renders an unknown content type in a plain block."""
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/other.json"
    store.put(key, '{"some": "config"}')
    art = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="architecture", type="api_spec",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(art.id))
    assert resp.data["content_type"] == "application/json"
    assert resp.data["body"] == '{"some": "config"}'
    assert resp.data["rendered"] is False


def test_a_malformed_sbom_degrades_to_text_rather_than_failing(client, project, member):
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/broken.json"
    store.put(key, '{"bomFormat":"CycloneDX", TRUNCATED')
    art = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="security", type="sbom",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(art.id))
    assert resp.status_code == 200
    assert resp.data["rendered"] is False
    assert resp.data["content_type"] == "text/markdown"     # unparseable, so not claimed as JSON


def test_ordinary_markdown_drafts_are_untouched(client, project, member):
    """The whole change must be invisible to the 99% of bodies that really are prose."""
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/prd2.md"
    store.put(key, "# PRD\n\nName: Ada\nRole: engineer\n")
    art = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="prd", type="prd",
        sor="internal", status="draft", s3_key=key, version=1,
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(art.id))
    assert resp.data["content_type"] == "text/markdown"
    assert resp.data["body"] == "# PRD\n\nName: Ada\nRole: engineer\n"
    assert resp.data["rendered"] is False


def test_a_declared_format_beats_detection(client, project, member):
    """An agent knows what it staged. `register_artifact(format=...)` is how it says so."""
    store = s3_from_settings()
    key = f"test-preview/{project.tenant_id}/{project.id}/data.csv"
    store.put(key, "name,version\ndjango,5.1.4\n")
    art = Artifact.objects.create(
        tenant=project.tenant, project=project, phase="security", type="security_finding",
        sor="internal", status="draft", s3_key=key, version=1,
        external_ref={"format": "csv"},
    )
    _login(client, "dev@acme.com", "dev-pass!")
    resp = client.get(_preview_url(art.id))
    assert resp.data["content_type"] == "text/csv"


def test_a_wireframe_with_no_s3_key_of_its_own_still_reads_a_real_document(project, member):
    """The states-only row: bodies in `external_ref.states`, nothing on the row itself.

    `test_preview_multistate_wireframe_...` above sets `s3_key` on the row too, so it never
    exercised this shape — which is how the following went unnoticed. `render_structured_ref`
    treated `states` as CONTENT and rendered it, producing a body that read:

        ## States
        ### default
        - **S3 key:** t/<tenant>/wire-default.md

    Raw storage paths, where the document belongs. And because that body was non-empty it satisfied
    the `if not body` guard in front of the per-state read, so the real documents were never
    reached — on the preview screen, in a downloaded file, and in whatever publish pushed into the
    client's Confluence.

    Fixed by naming `states` a pointer key (as `page_images` already was) and resolving the default
    state inside `_read_internal`, where all three callers share it.
    """
    from integrations.preview import internal_draft_body, read_artifact_preview
    from storage.object_store import InMemoryObjectStore

    store = InMemoryObjectStore()
    tenant = project.tenant
    dk = f"drafts/{tenant.id}/{project.id}/r/ux/SCR-002-state-1-default.html"
    store.put(dk, "<html>Email, password, Sign in.</html>", content_type="text/html")
    artifact = Artifact.objects.create(
        tenant=tenant, project=project, phase="ux_design", type="wireframe",
        sor="internal", status="draft", s3_key="", version=1,
        external_ref={"screen_id": "SCR-002", "states": [
            {"name": "state-1-default", "s3_key": dk},
            {"name": "state-4-error", "s3_key": f"drafts/{tenant.id}/gone.html"},
        ]},
    )

    payload = read_artifact_preview(
        tenant_id=str(tenant.id), artifact_id=str(artifact.id), object_store=store)

    assert payload is not None
    assert "Email, password" in payload["body"], "the state's document was not read"
    assert "S3 key" not in payload["body"] and dk not in payload["body"], (
        "storage paths reached the screen"
    )

    # The publish path shares `_read_internal`, so it was pushing the same thing to a system of
    # record. Non-negotiable #5 territory: what goes out must be the document.
    published = internal_draft_body(artifact, store)
    assert "Email, password" in published
    assert "S3 key" not in published and dk not in published
