"""QA-24 — the conformance statement's three endpoints, over HTTP.

`apps.a11y.conformance` is tested directly in `test_a11y_conformance.py`. This file is about the
seam the screen talks to: does the compiled table arrive, does an edit really clear a signature
across a request boundary, and does a refusal come back as a status code the UI can branch on.

**The refusals are the contract.** `403` is "you may never do this" (wrong role); `409` is "you
may, but not in this state" (unsigned, or signed against evidence that has since moved); `400`
is "fix your request". Export is the one that matters most — the platform must never certify
anything on its own, and that rule has to survive the trip through HTTP, not just the unit test.
"""
import pytest
from rest_framework.test import APIClient

from apps.a11y import coverage
from apps.a11y.conformance import PARTIALLY, sign
from apps.a11y.models import WcagCriterion
from apps.projects.models import Project
from apps.registry.models import Artifact
from apps.tenancy.models import Membership, Tenant, User

PASSWORD = "conformance-pass!"


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Payment Gateway v2")
    WcagCriterion.objects.get_or_create(
        version="2.2", number="1.1.1",
        defaults={"handle": "Non-text Content", "level": "A", "slug": "n", "text": "…"})

    aisha = User.objects.create_user(email="aisha@acme.test", name="Aisha Khan", tenant=tenant,
                                     password=PASSWORD)
    dev = User.objects.create_user(email="dev@acme.test", name="Dana Ops", tenant=tenant,
                                   password=PASSWORD)
    Membership.objects.create(tenant=tenant, project=project, user=aisha, role="qa_lead")
    Membership.objects.create(tenant=tenant, project=project, user=dev, role="engineer")

    # Both engines, because both really do look at 1.1.1 and only one of them can settle it.
    # axe's `image-alt` proves an alt attribute exists; whether the alt says anything is the
    # AI's question, and `ownership.json` gives 1.1.1 to `ai`. With only the scanner row here
    # the criterion correctly reads as not evaluated -- which is the conformance guard doing
    # its job, not the statement endpoint failing.
    coverage.record(tenant_id=str(tenant.id), project_id=str(project.id), run_key="k1",
                    route="/checkout", engine="rule",
                    observations=[("1.1.1", "passed", "image-alt")])
    coverage.record(tenant_id=str(tenant.id), project_id=str(project.id), run_key="k1",
                    route="/checkout", engine="AI",
                    observations=[("1.1.1", "passed", "alt judged meaningful")])
    return {"tenant": tenant, "project": project, "aisha": aisha, "dev": dev,
            "base": f"/api/projects/{project.id}/a11y-conformance"}


def _client(email):
    client = APIClient()
    assert client.post("/api/auth/login/", {"email": email, "password": PASSWORD},
                       format="json").status_code == 200
    return client


def test_the_statement_arrives_compiled_with_every_criterion(world):
    body = _client("aisha@acme.test").get(f"{world['base']}/").json()
    assert body["can_sign"] is True and body["signed"] is False
    assert len(body["rows"]) == body["totals"]["total"] == 55
    assert body["totals"]["evaluated"] == 1
    assert body["totals"]["not_evaluated"] == 54
    assert "risk reduction, not certification" in body["disclaimer"]
    assert body["required_role"] == "qa_lead"
    row = next(r for r in body["rows"] if r["criterion"] == "1.1.1")
    # Both engines are named, and the order is the scanner AFTER the judge only because
    # the list is sorted. What matters is that the judge is in it: it is the presence of
    # `AI` that entitles 1.1.1 to read as "supports" at all.
    assert row["suggested"] == "supports" and row["established_by"] == ["AI", "rule"]
    assert "checked on 1 pages with nothing wrong" in row["evidence"].lower()


def test_the_versions_never_reach_the_screen(world):
    """D-A11Y-96, asserted at the seam rather than trusted: recorded on the export, never shown."""
    body = _client("aisha@acme.test").get(f"{world['base']}/").json()
    text = str(body)
    for leak in ("prompt_version", "scanner_version", "axe-core", "model"):
        assert leak not in text


def test_a_reader_without_the_role_sees_it_and_cannot_change_it(world):
    client = _client("dev@acme.test")
    body = client.get(f"{world['base']}/").json()
    assert body["can_sign"] is False
    assert len(body["rows"]) == 55, "read-only, not blind"

    assert client.put(f"{world['base']}/", {"scope": "mine now"}, format="json").status_code == 403
    assert client.post(f"{world['base']}/sign/",
                       {"name": "Dana", "acknowledged": True}, format="json").status_code == 403


def test_an_edit_survives_the_round_trip_and_a_bad_level_is_refused(world):
    client = _client("aisha@acme.test")
    body = client.put(f"{world['base']}/",
                      {"scope": "Checkout and expenses only",
                       "verdicts": {"1.1.1": {"level": PARTIALLY, "note": "desktop only"}}},
                      format="json").json()
    assert body["scope"] == "Checkout and expenses only"
    row = next(r for r in body["rows"] if r["criterion"] == "1.1.1")
    assert row["verdict"] == PARTIALLY and row["effective"] == PARTIALLY

    bad = client.put(f"{world['base']}/", {"verdicts": {"1.1.1": {"level": "great"}}},
                     format="json")
    assert bad.status_code == 400 and "isn't a conformance level" in bad.json()["detail"]


def test_export_is_refused_while_unsigned(world):
    """AC3. The platform never auto-certifies, and the refusal has to survive HTTP."""
    response = _client("aisha@acme.test").post(f"{world['base']}/export/")
    assert response.status_code == 409
    assert "cannot be exported unsigned" in response.json()["detail"]


def test_signing_then_exporting_publishes_the_statement(world):
    client = _client("aisha@acme.test")
    signed = client.post(f"{world['base']}/sign/",
                         {"name": "Aisha Khan", "acknowledged": True}, format="json")
    assert signed.status_code == 200
    assert signed.json()["signed"] is True and signed.json()["can_export"] is True

    artifact = Artifact.objects.get(type="conformance")
    assert artifact.status == Artifact.Status.APPROVED, "the signature IS the gate (B1)"

    out = client.post(f"{world['base']}/export/").json()
    assert out["signed_by"] == "Aisha Khan"
    assert out["artifact_id"] == str(artifact.id) and out["exported_at"]
    artifact.refresh_from_db()
    # Published inside the platform — never routed to test management (recon 2026-10-10).
    assert artifact.status == Artifact.Status.PUBLISHED


def test_the_signing_reply_says_who_may_sign_like_the_page_load_does(world):
    """The screen writes the reply into its cache; without can_sign the Statement and Export
    boxes vanished after signing until a reload (live retest 2026-10-12)."""
    client = _client("aisha@acme.test")
    signed = client.post(f"{world['base']}/sign/",
                         {"name": "Aisha Khan", "acknowledged": True}, format="json")
    assert signed.status_code == 200, signed.content
    assert signed.json()["can_sign"] is True


def test_signing_without_the_acknowledgement_is_refused(world):
    response = _client("aisha@acme.test").post(
        f"{world['base']}/sign/", {"name": "Aisha Khan"}, format="json")
    assert response.status_code == 400
    assert 'Confirm you have read' in response.json()["detail"]


def test_editing_after_signing_clears_the_signature_over_http(world):
    client = _client("aisha@acme.test")
    client.post(f"{world['base']}/sign/", {"name": "Aisha Khan", "acknowledged": True},
                format="json")
    after = client.put(f"{world['base']}/", {"body": "Rewritten."}, format="json").json()
    assert after["signed"] is False
    assert client.post(f"{world['base']}/export/").status_code == 409


def test_new_evidence_makes_the_signed_statement_refuse_to_export(world):
    """C1 at the seam: the words are still theirs, the facts moved, and the door closes."""
    client = _client("aisha@acme.test")
    sign(tenant_id=str(world["tenant"].id), project_id=str(world["project"].id),
         user_id=world["aisha"].id, name="Aisha Khan", acknowledged=True)
    coverage.record(tenant_id=str(world["tenant"].id), project_id=str(world["project"].id),
                    run_key="k2", route="/dashboard", engine="rule",
                    observations=[("1.1.1", "failed", "image-alt")])

    body = client.get(f"{world['base']}/").json()
    assert body["signed"] is True and body["stale"] is True and body["can_export"] is False
    refused = client.post(f"{world['base']}/export/")
    assert refused.status_code == 409 and "evidence has changed" in refused.json()["detail"]


def test_the_endpoints_need_a_session(world):
    anon = APIClient()
    assert anon.get(f"{world['base']}/").status_code in (401, 403)
    assert anon.post(f"{world['base']}/sign/", {"name": "x", "acknowledged": True},
                     format="json").status_code in (401, 403)
