"""Downloading an artifact as a file — `GET /api/artifacts/{id}/download/`.

Separate from `test_artifact_preview_rest.py` because the two endpoints answer different questions
and one of the differences is the reason this exists at all: **Export is not Download.** The
registry's Export control pushes the document INTO Confluence or Jira, a gated write to a system of
record, and people were clicking it to get a copy. `test_downloading_writes_nothing` is the test
that keeps those two apart.

The other load-bearing cases:

- `test_an_sbom_downloads_as_the_stored_json` — the preview layer renders an SBOM into a readable
  table. A file called `SBOM-v1.json` must contain the SBOM, not a picture of it.
- `test_a_body_that_cannot_be_read_is_refused` — `_s3_body` degrades a missing or non-UTF-8 object
  to an empty string by design, which is right for a screen that can say "Preview unavailable" and
  wrong for a download, which would otherwise save a 0-byte file named after the document.
- `test_a_hostile_title_cannot_break_the_header` — `Artifact.title` is free text written by a phase
  agent and it ends up inside an HTTP header.
"""
import json

import pytest
from rest_framework.test import APIClient

from apps.ledger.models import Event
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def store(object_store):
    """The suite-wide in-memory store from `conftest.py`, under this file's older name.

    This file used to patch the store itself, because it was the first to notice that staging a body
    writes a real object into the team's live AWS bucket. That guard now covers every test in the
    suite (`conftest.object_store`), so there is nothing local left to do but name it.
    """
    return object_store


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


def _login(client, email="dev@acme.com", password="dev-pass!"):
    assert client.post(
        "/api/auth/login/", {"email": email, "password": password}, format="json"
    ).status_code == 200


def _url(artifact_id):
    return f"/api/artifacts/{artifact_id}/download/"


def _artifact(tenant, project, **over):
    fields = dict(tenant=tenant, project=project, phase="prd", type="prd",
                  title="PRD — Spend Export", status="approved", sor="internal", version=2)
    fields.update(over)
    return Artifact.objects.create(**fields)


def _staged(store, tenant, project, body: bytes, **over):
    key = f"t/{tenant.id}/draft-{over.get('type', 'prd')}.md"
    store.put(key, body)
    return _artifact(tenant, project, s3_key=key, **over)


# ── the file is the document ────────────────────────────────────────
def test_an_internal_artifact_downloads_its_body(client, tenant, project, member, store):
    body = b"# Spend Export PRD\n\nThe product must let a user export their spend."
    art = _staged(store, tenant, project, body)
    _login(client)

    resp = client.get(_url(art.id))

    assert resp.status_code == 200
    assert resp.content == body, "byte-for-byte, not a rendering of it"
    assert "attachment" in resp["Content-Disposition"], "saved, not shown in the page"
    assert "text/markdown" in resp["Content-Type"]


def test_the_filename_names_the_document_not_its_id(client, tenant, project, member, store):
    art = _staged(store, tenant, project, b"# PRD")
    _login(client)

    said = client.get(_url(art.id))["Content-Disposition"]

    assert "PRD-Spend-Export-v2.md" in said
    # Standing rule: no ids on a client's screen. A file called `3dab76d0-....md` in somebody's
    # Downloads folder is that failure made permanent.
    assert str(art.id) not in said


def test_a_blank_title_falls_back_to_words(client, tenant, project, member, store):
    """Blank titles are legal — the display layer humanises the type. A download may not fall back
    to the id just because the agent left the title empty."""
    art = _staged(store, tenant, project, b"# Doc", title="",
                  type="architecture", phase="architecture")
    _login(client)

    said = client.get(_url(art.id))["Content-Disposition"]

    assert "Architecture" in said and str(art.id) not in said


def test_an_sbom_downloads_as_the_stored_json(client, tenant, project, member, store):
    """The preview layer renders an SBOM into a markdown table. The FILE must be the SBOM."""
    sbom = json.dumps({"bomFormat": "CycloneDX", "components": [{"name": "django"}]}).encode()
    art = _staged(store, tenant, project, sbom, type="sbom", title="SBOM", version=1,
                  external_ref={"format": "json"})
    _login(client)

    resp = client.get(_url(art.id))

    assert resp.status_code == 200
    assert json.loads(resp.content)["bomFormat"] == "CycloneDX"
    assert b"|" not in resp.content, "a rendered table reached the file"
    assert "SBOM-v1.json" in resp["Content-Disposition"]


def test_an_inline_draft_body_downloads(client, tenant, project, member, store):
    """Some drafts are registered with the body inline and no S3 key yet."""
    art = _artifact(tenant, project, external_ref={"body": "# Draft PRD", "format": "markdown"})
    _login(client)

    resp = client.get(_url(art.id))

    assert resp.status_code == 200 and resp.content == b"# Draft PRD"


def test_a_wireframe_with_bodies_only_per_state_downloads(client, tenant, project, member, store):
    """A wireframe registers one row with a body per SCREEN STATE in `external_ref.states` and no
    `s3_key` of its own. The predicate reads that branch, so the row offers Download — and the file
    must then be a real body, not the empty string the bodyless case is refused for."""
    key = f"t/{tenant.id}/wire-default.md"
    store.put(key, "# Login — default state\n\nEmail, password, Sign in.".encode())
    art = _artifact(
        tenant, project, type="wireframe", phase="ux_design", title="Wireframe — Login",
        version=1, s3_key="",
        external_ref={"states": [{"name": "default", "s3_key": key},
                                 {"name": "error", "s3_key": f"t/{tenant.id}/wire-error.md"}]},
    )
    _login(client)

    rows = {r["id"]: r for r in client.get("/api/artifacts/").data}
    assert rows[str(art.id)]["downloadable"] is True, "the per-state branch was not read"

    resp = client.get(_url(art.id))

    assert resp.status_code == 200
    assert b"Email, password" in resp.content, "the state's body did not reach the file"
    assert "Wireframe-Login-v1" in resp["Content-Disposition"]


# ── what must NOT be downloadable ───────────────────────────────────
@pytest.mark.parametrize("sor", ["jira", "figma", "xray", "git"])
def test_a_pointer_at_someone_elses_system_is_refused(client, tenant, project, member, store, sor):
    """The authoritative copy lives elsewhere and we only point at it. For Jira the 'body' is two
    lines we synthesise (`summary` + `Status: x`) — handed over as `Login-flow.txt` that looks like
    the document and is not."""
    art = _artifact(tenant, project, sor=sor, external_ref={"url": "https://example.test/x",
                                                            "id": "ENG-1"})
    _login(client)

    resp = client.get(_url(art.id))

    assert resp.status_code == 404
    said = resp.data["detail"]
    assert "kept somewhere else" in said and "Preview" in said


def test_a_body_that_cannot_be_read_is_refused(client, tenant, project, member, store):
    """An S3 object that has gone missing degrades to an empty body for the preview screen, which
    can say so. A download has no way to say so — it would save a 0-byte file named after the
    document, which reads as 'this document is empty'."""
    art = _artifact(tenant, project, s3_key="t/missing/gone.md")
    _login(client)

    resp = client.get(_url(art.id))

    assert resp.status_code == 404
    assert "nothing to download" in resp.data["detail"]


def test_downloadable_is_reported_on_the_list(client, tenant, project, member, store):
    """So the button and the endpoint cannot disagree — the `previewable` lesson."""
    ours = _staged(store, tenant, project, b"# PRD")
    theirs = _artifact(tenant, project, sor="figma", type="wireframe",
                       external_ref={"url": "https://figma.test/x"})
    _login(client)

    rows = {r["id"]: r for r in client.get("/api/artifacts/").data}

    assert rows[str(ours.id)]["downloadable"] is True
    assert rows[str(theirs.id)]["downloadable"] is False
    # Still previewable — it has a link to follow. The two flags are deliberately different.
    assert rows[str(theirs.id)]["previewable"] is True


def test_an_inline_body_row_is_previewable_too(client, tenant, project, member, store):
    """`artifact_has_preview` used to test only `s3_key`, while the reader it claims to mirror also
    serves an inline `external_ref.body`. Such a row previewed perfectly and was labelled 'Nothing
    to preview'. Fixed alongside the download predicate, which shares the same helper."""
    art = _artifact(tenant, project, external_ref={"body": "# Draft"})
    _login(client)

    rows = {r["id"]: r for r in client.get("/api/artifacts/").data}

    assert rows[str(art.id)]["previewable"] is True
    assert rows[str(art.id)]["downloadable"] is True


# ── a filename cannot break the response ────────────────────────────
def test_a_hostile_title_cannot_break_the_header(client, tenant, project, member, store):
    """`title` is free text an AGENT writes. It ends up in an HTTP header, which is a line-oriented
    format with quoting rules — so a newline is not a cosmetic problem."""
    art = _staged(
        store, tenant, project, b"# x",
        title='Q3 "final"\r\nX-Injected: yes\r\n\r\n../../etc/passwd',
    )
    _login(client)

    said = client.get(_url(art.id))["Content-Disposition"]

    assert "\r" not in said and "\n" not in said, "a header was split"
    assert "X-Injected" not in client.get(_url(art.id)).headers
    assert "../" not in said and "/" not in said.split("filename=")[1].split(";")[0]
    assert said.startswith("attachment;")


def test_a_non_ascii_title_survives_and_still_degrades(client, tenant, project, member, store):
    """RFC 6266: `filename=` may only carry ASCII, `filename*=` carries the real one. Both are
    written, so a modern browser gets the accents and an old one gets a readable name rather than
    mojibake."""
    art = _staged(store, tenant, project, b"# x", title="Résumé — Café")
    _login(client)

    said = client.get(_url(art.id))["Content-Disposition"]

    assert "filename*=UTF-8''" in said
    # Transliterated, not stripped to nothing.
    assert "Resume" in said and "Cafe" in said


# ── downloading is not publishing ───────────────────────────────────
def test_downloading_writes_nothing(client, tenant, project, member, store):
    """THE test. Export pushes the document into a system of record; this reads a body and streams
    it. The two controls sit a few pixels apart on the registry, and people clicking Export to get
    a copy is the whole reason this endpoint exists."""
    art = _staged(store, tenant, project, b"# PRD")
    before = (art.status, art.published_at, art.version,
              Event.objects.filter(tenant_id=tenant.id).count())
    _login(client)

    assert client.get(_url(art.id)).status_code == 200

    art.refresh_from_db()
    after = (art.status, art.published_at, art.version,
             Event.objects.filter(tenant_id=tenant.id).count())
    assert before == after, "a download changed state"


# ── access ──────────────────────────────────────────────────────────
def test_a_stranger_cannot_download(client, tenant, project, member, store):
    art = _staged(store, tenant, project, b"# secret")

    assert client.get(_url(art.id)).status_code in (401, 403)
