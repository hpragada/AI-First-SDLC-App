"""QA-17 — auditing an app the platform never built.

Against the task's acceptance criteria:

  AC1  an onboarded app with a registered route list and NO accessibility spec produces
       findings for those routes when the baseline audit runs
  AC2  a route that fails to load is reported as an error, never skipped
  AC3  a run against a sample route list including a failing route is covered

**The sharpest thing in this file** is `test_a_finding_on_an_unreachable_route_is_not_resolved`.
`findings.record_run_findings` resolves a finding by ABSENCE across the routes a run covered, so
a route that never opened must not count as covered — otherwise an auth wall or a 404 would
close every accessibility defect on that page as though somebody had fixed it. That is the one
way this task could have quietly destroyed existing data.
"""
from __future__ import annotations

import base64
import io
import json
import re
import shutil
from pathlib import Path

import pytest
from PIL import Image as PILImage

from apps.a11y.baseline import (
    NEVER_REPORTED,
    BaselineError,
    audit_manifest,
    complete_audit,
    finish_baseline_audit,
    ingest_audit_capture,
    reconcile_routes,
    start_baseline_audit,
)
from apps.a11y.capture import fingerprint, parse_capture
from apps.a11y.findings import record_run_findings
from apps.a11y.models import A11yBaselineAudit, A11yFinding, A11yRoute, A11yScreenScan
from apps.a11y.report import merge_run, report_body
from apps.a11y.routes import (
    MAX_ROUTES,
    RouteError,
    normalise_path,
    register_routes,
    route_paths,
)
from apps.a11y.scanner import rule_findings_for
from apps.projects.models import Project
from apps.tenancy.models import Tenant
from storage.object_store import InMemoryObjectStore

_REPO = Path(__file__).resolve().parents[2]

_STYLES = {
    "color": "rgb(20, 20, 20)", "background-color": "rgb(255, 255, 255)",
    "text-decoration-line": "none", "font-size": "16px", "font-weight": "400",
    "border-style": "none",
}


def _png(colour=(200, 40, 40)) -> bytes:
    buf = io.BytesIO()
    PILImage.new("RGB", (40, 30), colour).save(buf, format="PNG")
    return buf.getvalue()


def _element(**over) -> dict:
    base = {
        "selector": "img.hero", "tag": "img", "role": "", "attrs": {"alt": "IMG_1234"},
        "text": "", "accessible_name": "IMG_1234", "interactive": False, "rendered": True,
        "styles": dict(_STYLES), "parent_styles": dict(_STYLES),
        "html": '<img class="hero" alt="IMG_1234">', "context": "Our new range",
        "box": {"x": 10, "y": 20, "width": 120, "height": 80},
    }
    base.update(over)
    return base


def _screen(route="/login", **over) -> dict:
    base = {
        "route": route, "url": f"http://localhost:5173{route}",
        "screenshot_base64": base64.b64encode(_png()).decode("ascii"),
        "elements": [_element()],
    }
    base.update(over)
    return base


@pytest.fixture
def world(db):
    tenant = Tenant.objects.create(name="Acme")
    project = Project.objects.create(tenant=tenant, name="Imported App")
    return {"t": str(tenant.id), "p": str(project.id), "tenant": tenant, "project": project}


@pytest.fixture
def ready_folder(monkeypatch):
    """Given a machine whose project folder has the browser and the scanner installed.

    Requested by every test that drives a pass, because those tests are about the PASS and not
    about what is installed on the machine. Whether a folder can run an audit at all is its own
    question with its own tests (`preflight`, at the end of this file) — and without stating it
    here, every one of them would stop at a temp directory with no `node_modules`, which is
    exactly the honest thing `preflight` was added to do.
    """
    from runner.companion import a11yaudit

    monkeypatch.setattr(a11yaudit, "preflight", lambda **kw: {
        "ok": True, "cwd": "", "browser": {"ok": True, "error": ""},
        "scanner": {"ok": True, "version": "4.13.0", "error": ""},
    })


def _register(world, *paths):
    return register_routes(tenant_id=world["t"], project_id=world["p"],
                           routes=list(paths))


def _audit(world, *paths, base_url="http://localhost:5173"):
    if paths:
        _register(world, *paths)
    return start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                base_url=base_url)


def _post(world, audit, screen):
    return ingest_audit_capture(tenant_id=world["t"], audit_id=str(audit.id),
                                text=json.dumps(screen),
                                object_store=InMemoryObjectStore())


# ══ the route registry — where the screen list comes from ════════════════════════════

def test_a_route_is_a_path_not_a_url():
    assert normalise_path("/checkout") == "/checkout"
    with pytest.raises(RouteError) as err:
        normalise_path("http://localhost:5173/checkout")
    assert "page's path only" in str(err.value)


def test_a_route_must_start_at_the_apps_root():
    with pytest.raises(RouteError) as err:
        normalise_path("checkout")
    assert 'must start with a slash' in str(err.value)


def test_a_blank_route_is_refused_rather_than_guessed():
    with pytest.raises(RouteError):
        normalise_path("   ")


def test_a_route_with_a_line_break_is_refused():
    with pytest.raises(RouteError):
        normalise_path("/check\nout")


def test_an_overlong_route_is_refused():
    with pytest.raises(RouteError):
        normalise_path("/" + "x" * 600)


def test_registering_routes_is_idempotent(world):
    first = _register(world, "/", "/login")
    second = _register(world, "/", "/login")
    assert sorted(first["added"]) == ["/", "/login"]
    assert second["added"] == [] and sorted(second["updated"]) == ["/", "/login"]
    assert route_paths(world["t"], world["p"]) == ["/", "/login"]


def test_a_route_named_twice_is_stored_once(world):
    result = _register(world, "/cart", "/cart")
    assert result["total"] == 1


def test_routes_carry_a_label_and_a_note(world):
    register_routes(tenant_id=world["t"], project_id=world["p"], routes=[
        {"path": "/admin", "label": "Admin console", "notes": "needs a signed-in session"}])
    row = A11yRoute.objects.get(tenant_id=world["t"], path="/admin")
    assert row.label == "Admin console" and "signed-in" in row.notes
    assert row.source == A11yRoute.Source.MANUAL


def test_replacing_the_list_disables_rather_than_deletes(world):
    _register(world, "/", "/legacy")
    result = register_routes(tenant_id=world["t"], project_id=world["p"],
                             routes=["/"], replace=True)
    assert result["disabled"] == ["/legacy"]
    assert route_paths(world["t"], world["p"]) == ["/"]
    assert A11yRoute.objects.filter(tenant_id=world["t"], path="/legacy").exists(), \
        "the row survives — a page that stopped being audited is a fact worth keeping"


def test_onboarding_can_own_the_list_when_it_lands(world):
    """OP-06 writes the same table. Nothing about the audit changes; only `source` does."""
    register_routes(tenant_id=world["t"], project_id=world["p"], routes=["/"],
                    source="onboarding")
    assert A11yRoute.objects.get(tenant_id=world["t"], path="/").source == "onboarding"


def test_an_unknown_source_is_refused(world):
    with pytest.raises(RouteError):
        register_routes(tenant_id=world["t"], project_id=world["p"], routes=["/"],
                        source="magic")


def test_routes_must_be_a_list(world):
    with pytest.raises(RouteError):
        register_routes(tenant_id=world["t"], project_id=world["p"], routes="/")


def test_the_route_list_describes_itself_for_a_console(world):
    from apps.a11y.routes import describe_routes

    assert "No pages are listed" in describe_routes(world["t"], world["p"])
    _register(world, "/", "/legacy")
    assert describe_routes(world["t"], world["p"]) == "2 pages listed"
    register_routes(tenant_id=world["t"], project_id=world["p"], routes=["/"], replace=True)
    assert describe_routes(world["t"], world["p"]) == "1 page listed, 1 excluded"


def test_a_sitemap_dump_is_refused_with_a_reason(world):
    with pytest.raises(RouteError) as err:
        register_routes(tenant_id=world["t"], project_id=world["p"],
                        routes=[f"/p/{n}" for n in range(MAX_ROUTES + 1)])
    assert "Nothing was stored" in str(err.value)


# ══ starting an audit ════════════════════════════════════════════════════════════════

def test_an_audit_freezes_the_route_list_it_was_given(world):
    audit = _audit(world, "/", "/login")
    _register(world, "/cart")                       # added after the audit opened
    assert audit.routes == ["/", "/login"], "a route added mid-pass is not a route that failed"


def test_an_audit_needs_no_accessibility_spec(world):
    """AC1's premise. Nothing in this chain reads an `accessibility` artifact, and the audit
    is the proof: this project has no artifacts at all."""
    from apps.registry.models import Artifact

    audit = _audit(world, "/login")
    assert not Artifact.objects.filter(tenant_id=world["t"]).exists()
    assert audit.status == A11yBaselineAudit.Status.CAPTURING


def test_an_audit_of_a_project_with_no_routes_is_refused(world):
    with pytest.raises(BaselineError) as err:
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert "reads exactly like an application with none" in str(err.value)


def test_an_audit_can_be_given_routes_directly(world):
    # An address is given because since B3 an audit without one is refused: the manifest this
    # used to produce carried `base_url: ""`, which the audit script cannot visit. What this
    # test is about — dedupe and order — is unchanged.
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                 base_url="http://localhost:5173",
                                 routes=["/one", "/two", "/one"])
    assert audit.routes == ["/one", "/two"], "deduped, order preserved"


def test_a_bad_route_stops_the_audit_before_it_starts(world):
    with pytest.raises(BaselineError) as err:
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                             routes=["https://example.com/x"])
    assert "page's path only" in str(err.value)


def test_routes_given_directly_must_be_a_list(world):
    with pytest.raises(BaselineError):
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"], routes="/one")


def test_the_manifest_says_where_to_go_and_what_to_visit(world):
    audit = _audit(world, "/", "/login")
    manifest = audit_manifest(audit)
    assert manifest["base_url"] == "http://localhost:5173"
    assert manifest["routes"] == ["/", "/login"]
    assert manifest["output"].endswith("a11y-candidates.json")
    assert manifest["audit_id"] == str(audit.id)


# == where the address comes from (B3) ================================================
#
# The audit needs one fact: where the running application answers. The platform already holds
# it - `Repository.preview_url` is an APPLICATION address (not a repo URL; that is `name` /
# `code_host_ref`), stored per repo because the served thing is a repo. Until B3 nothing in
# `apps.a11y` read it, so a person typed it again on a command line. The resolution order and
# its reasoning live in `apps.projects.preview_config.resolve_app_base_url`.


def _repo(world, **over):
    from apps.projects.models import Repository

    fields = {"tenant": world["tenant"], "project": world["project"], "name": "acme/web",
              "is_default": True, "preview_url": "http://127.0.0.1:5173"}
    fields.update(over)
    return Repository.objects.create(**fields)


def test_the_address_comes_from_the_default_repository_when_none_is_given(world):
    _repo(world)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert audit.base_url == "http://127.0.0.1:5173"
    assert audit_manifest(audit)["base_url"] == "http://127.0.0.1:5173"


def test_an_address_given_for_this_pass_always_wins(world):
    """Someone deliberately checking a staging site must never be overridden by a stored
    development URL."""
    _repo(world)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                 base_url="https://staging.example.com")
    assert audit.base_url == "https://staging.example.com"


def test_the_only_repository_that_serves_an_app_is_used_when_it_is_not_the_default(world):
    """A `preview_url` is a claim that this repo serves the application. On a multi-repo project
    the default is often the API, which has no UI to check - reading the one repo that does make
    the claim is reading the data, not guessing."""
    _repo(world, name="acme/api", preview_url="", is_default=True)
    _repo(world, name="acme/web", preview_url="http://127.0.0.1:4000", is_default=False)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert audit.base_url == "http://127.0.0.1:4000"


def test_the_default_repositorys_own_address_wins_over_another_repos(world):
    _repo(world, name="acme/web", preview_url="http://127.0.0.1:5173", is_default=True)
    _repo(world, name="acme/admin", preview_url="http://127.0.0.1:5174", is_default=False)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert audit.base_url == "http://127.0.0.1:5173"


def test_two_applications_and_no_default_is_refused_naming_both(world):
    _repo(world, name="acme/web", preview_url="http://127.0.0.1:5173", is_default=False)
    _repo(world, name="acme/admin", preview_url="http://127.0.0.1:5174", is_default=False)
    _register(world, "/login")
    with pytest.raises(BaselineError) as err:
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert "acme/web" in str(err.value) and "acme/admin" in str(err.value)
    assert "only you know which application to check" in str(err.value)


def test_the_port_the_project_builds_with_is_used_when_no_url_is_stored(world):
    """The address the companion itself uses when a build brings the app up - derived from the
    platform's own behaviour, not invented. Nothing is started here: if the app is not up, the
    audit reports pages nothing answered on, which is honest and never a pass."""
    _repo(world, preview_url="", preview_start={"command": "npm run dev", "port": 5173})
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert audit.base_url == "http://127.0.0.1:5173"


def test_an_audit_with_no_address_anywhere_is_refused_and_says_what_to_set(world):
    from apps.a11y.models import A11yBaselineAudit

    _register(world, "/login")
    with pytest.raises(BaselineError) as err:
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert "no application address on record" in str(err.value)
    assert "Preview URL" in str(err.value)
    assert not A11yBaselineAudit.objects.filter(tenant_id=world["t"]).exists(), \
        "refused before anything was written"


def test_a_project_with_no_routes_is_still_told_about_the_routes_first(world):
    """Refusal order: the routes are the earlier thing to go and fix, and every existing refusal
    keeps its own wording."""
    with pytest.raises(BaselineError) as err:
        start_baseline_audit(tenant_id=world["t"], project_id=world["p"])
    assert "reads exactly like an application with none" in str(err.value)


def test_the_resolver_says_where_the_address_came_from(world):
    """A screen pre-filling this field has to be able to say why (B1). Exactly one of `url` /
    `reason` is ever set."""
    from apps.projects.preview_config import resolve_app_base_url

    empty = resolve_app_base_url(tenant_id=world["t"], project_id=world["p"])
    assert empty.url == "" and empty.source == "" and "Preview URL" in empty.reason

    _repo(world)
    found = resolve_app_base_url(tenant_id=world["t"], project_id=world["p"])
    assert found.url == "http://127.0.0.1:5173"
    assert found.source == "the default repository acme/web" and found.reason == ""


def test_the_companion_may_leave_the_address_to_the_platform(tmp_path, monkeypatch, ready_folder):
    """The half that makes B3 visible today: `--base-url` is optional, and the address the
    platform resolved comes back on the manifest, which is what the script visits."""
    from runner.companion import a11yaudit

    seen = {}

    def _fake_script(manifest, **kw):
        seen["manifest"] = manifest
        return {"screens": [_screen("/")], "output": "x", "returncode": 0, "stderr": ""}

    monkeypatch.setattr(a11yaudit, "run_audit_script", _fake_script)

    class _Resolving(_FakeClient):
        def call(self, tool, **kwargs):
            out = super().call(tool, **kwargs)
            if tool == "start_a11y_audit" and not kwargs.get("base_url"):
                out["manifest"]["base_url"] = "http://127.0.0.1:5173"   # what the platform held
            return out

    client = _Resolving()
    a11yaudit.run_baseline_audit(client=client, project_id="p-1", workdir=tmp_path)
    assert client.calls[0]["base_url"] == "", "nothing typed, nothing invented"
    assert seen["manifest"]["base_url"] == "http://127.0.0.1:5173"


def test_an_audit_is_not_a_run(world):
    """The audit's id is the capture key and no `Run` has it — that is the design, not a gap."""
    from apps.runs.models import Run

    audit = _audit(world, "/login")
    assert not Run.objects.filter(id=audit.id).exists()


def test_two_audits_of_one_project_do_not_share_a_bucket(world):
    first = _audit(world, "/login")
    second = _audit(world)
    _post(world, first, _screen())
    _post(world, second, _screen())
    keys = set(A11yScreenScan.objects.filter(tenant_id=world["t"])
               .values_list("run_key", flat=True))
    assert keys == {str(first.id), str(second.id)}


def test_an_audit_capture_stays_out_of_the_project_wide_ci_bucket(world):
    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    assert not A11yScreenScan.objects.filter(tenant_id=world["t"], run_key="").exists()


def test_posting_to_an_audit_that_does_not_exist_says_so(world):
    import uuid

    with pytest.raises(BaselineError):
        ingest_audit_capture(tenant_id=world["t"], audit_id=str(uuid.uuid4()), text="{}")


# ══ AC2 — a route that would not open ════════════════════════════════════════════════

def test_a_route_that_failed_to_load_is_recorded_with_its_reason(world):
    audit = _audit(world, "/admin")
    _post(world, audit, _screen("/admin", load_error="the page returned HTTP 403",
                                elements=[]))
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], route="/admin")
    assert scan.load_error == "the page returned HTTP 403"
    assert scan.scan_error == "", "a page that never opened was not 'seen but unmeasured'"


def test_a_route_that_never_opened_has_no_elements_key_to_give(world):
    """A capture entry for an unreachable route legitimately carries no `elements`."""
    [screen] = parse_capture(json.dumps({"route": "/admin", "load_error": "timed out"}))
    assert screen["elements"] == [] and screen["load_error"] == "timed out"


def test_a_screen_with_no_elements_and_no_reason_is_still_refused():
    """Inside a document, a screen with neither elements nor a reason is a broken capture and
    is refused — the leniency is only for the entry that says why it has nothing."""
    from apps.a11y.capture import CaptureError

    with pytest.raises(CaptureError):
        parse_capture(json.dumps({"version": 1, "screens": [{"route": "/admin"}]}))


def test_a_bare_object_that_is_neither_is_simply_not_a_capture():
    assert parse_capture(json.dumps({"route": "/admin"})) == []


def test_whether_a_route_opened_changes_the_screens_identity():
    """QA-07 carries an unchanged screen forward. A route that failed this time must not
    inherit the run where it worked."""
    ok = parse_capture(json.dumps(_screen()))[0]
    broken = parse_capture(json.dumps(_screen(load_error="timed out", elements=[])))[0]
    assert fingerprint(ok) != fingerprint(broken)


def test_the_reason_is_bounded_like_every_other_captured_string():
    [screen] = parse_capture(json.dumps(_screen(load_error="x" * 5_000, elements=[])))
    assert len(screen["load_error"]) <= 1_000


def test_an_asked_for_route_that_never_reported_is_recorded_too(world):
    """The other half of "never silently skipped": the script died before reaching it, so
    nothing was posted at all — which looks identical to a page that was fine."""
    audit = _audit(world, "/", "/checkout")
    _post(world, audit, _screen("/"))
    recorded = reconcile_routes(tenant_id=world["t"], audit=audit)
    assert [item["route"] for item in recorded] == ["/checkout"]
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], route="/checkout")
    assert scan.load_error == NEVER_REPORTED


def test_reconciling_twice_records_nothing_new(world):
    audit = _audit(world, "/", "/checkout")
    _post(world, audit, _screen("/"))
    reconcile_routes(tenant_id=world["t"], audit=audit)
    assert reconcile_routes(tenant_id=world["t"], audit=audit) == []


def test_a_route_that_reported_its_own_failure_is_not_relabelled(world):
    audit = _audit(world, "/admin")
    _post(world, audit, _screen("/admin", load_error="the page returned HTTP 403",
                                elements=[]))
    assert reconcile_routes(tenant_id=world["t"], audit=audit) == []
    scan = A11yScreenScan.objects.get(tenant_id=world["t"], route="/admin")
    assert scan.load_error == "the page returned HTTP 403", "the app's reason, not ours"


# ══ the silence reaches the scanner and the report ═══════════════════════════════════

def test_the_scan_result_separates_unreachable_from_unscanned(world):
    audit = _audit(world, "/", "/admin")
    _post(world, audit, _screen("/", axe_error="no axe integration"))
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[]))

    scan = rule_findings_for(world["t"], world["p"], str(audit.id))
    assert scan.unreachable == [{"route": "/admin", "reason": "HTTP 403"}]
    assert scan.unscanned == [{"route": "/", "reason": "no axe integration"}]
    assert scan.routes == ["/"], "an unreachable route is not a route we looked at"


def test_the_report_names_the_routes_that_never_opened(world):
    audit = _audit(world, "/admin")
    _post(world, audit, _screen("/admin", load_error="the page returned HTTP 403",
                                elements=[]))
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    body = report_body(report)

    assert "Some screens could not be opened at all" in body
    assert "/admin" in body
    assert "HTTP 403" in body


def test_the_console_line_counts_the_screens_that_never_opened():
    from apps.a11y.capture import summarize

    screens = parse_capture(json.dumps({"version": 1, "screens": [
        _screen("/"), _screen("/admin", load_error="HTTP 403", elements=[])]}))
    line = summarize(screens)
    assert "on 1 screen(s)" in line, "an unreachable route is not a captured screen"
    assert "1 screen(s) could not be opened" in line


def test_the_published_report_counts_the_unreachable_routes(world):
    audit = _audit(world, "/", "/admin")
    _post(world, audit, _screen("/"))
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[]))
    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    assert out["report"]["unreachable"] == 1
    assert "1 screen(s) never opened" in out["report"]["summary"]


def test_a_reachable_run_makes_no_such_claim(world):
    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    assert report.unreachable == []
    assert "Some screens could not be opened at all" not in report_body(report)


def test_a_finding_on_an_unreachable_route_is_not_resolved(world):
    """The data-loss case this task could have caused.

    A run resolves a finding by absence across the routes it covered. If an unreachable route
    counted as covered, an auth wall in front of `/admin` would close every accessibility
    defect on it — reported to a client as a page that had been fixed.
    """
    audit = _audit(world, "/admin")
    finding = A11yFinding.objects.create(
        tenant_id=world["t"], project_id=world["p"], fingerprint="deadbeef",
        route="/admin", selector="button.pay", criterion="4.1.2", criteria=["4.1.2"],
        source=A11yFinding.Source.AI, outcome="failure", severity="critical",
        evidence="no accessible name", status=A11yFinding.Status.OPEN,
    )
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[]))
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    record_run_findings(tenant_id=world["t"], project_id=world["p"],
                        run_id=str(audit.id), report=report)

    finding.refresh_from_db()
    assert finding.status == A11yFinding.Status.OPEN


def test_a_finding_on_a_route_that_opened_and_came_back_clean_does_resolve(world):
    """The other direction, so the test above is not passing because nothing ever resolves."""
    audit = _audit(world, "/login")
    finding = A11yFinding.objects.create(
        tenant_id=world["t"], project_id=world["p"], fingerprint="cafe1234",
        route="/login", selector="button.pay", criterion="4.1.2", criteria=["4.1.2"],
        source=A11yFinding.Source.AI, outcome="failure", severity="critical",
        evidence="no accessible name", status=A11yFinding.Status.OPEN,
    )
    _post(world, audit, _screen("/login"))
    report = merge_run(tenant_id=world["t"], project_id=world["p"], run_id=str(audit.id))
    record_run_findings(tenant_id=world["t"], project_id=world["p"],
                        run_id=str(audit.id), report=report)

    finding.refresh_from_db()
    assert finding.status == A11yFinding.Status.RESOLVED


# ══ finishing an audit — AC1 end to end ══════════════════════════════════════════════

def test_finishing_accounts_for_every_route_asked_for(world):
    audit = _audit(world, "/", "/checkout", "/admin")
    _post(world, audit, _screen("/"))
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[]))

    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    assert out["asked"] == 3
    assert out["opened"] == 1
    assert out["unreachable"] == ["/admin", "/checkout"]
    assert out["never_reported"] == ["/checkout"]


def test_finishing_produces_findings_for_the_registered_routes(world):
    """AC1. The rule scanner's own violations become findings with no AI judge in sight —
    which is the honest floor for an app nobody has judged yet."""
    audit = _audit(world, "/login")
    _post(world, audit, _screen("/login", axe_violations=[{
        "rule": "image-alt", "impact": "critical", "criteria": ["1.1.1"],
        "help": "Images must have alternate text", "nodes": ["img.hero"]}]))

    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    # **Rule-scanner findings only, which is what this test is about.** With no judge to ask,
    # every element an AI check claims is filed as `uncertain` for a person — real behaviour
    # (QA-13), and it means the AI half of this list grows whenever a checker is added. It grew
    # on 27 Aug when `graphics` arrived and started claiming the default screen's element for
    # 1.4.11, and this assertion had been listing every finding regardless of source, so a
    # correct new checker read as a broken audit.
    findings = list(A11yFinding.objects.filter(tenant_id=world["t"], source="rule"))
    assert [f.criterion for f in findings] == ["1.1.1"]
    assert findings[0].route == "/login"


def test_a_finished_audit_registers_its_report_against_no_run(world):
    from apps.registry.models import Artifact

    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))

    artifact = Artifact.objects.get(tenant_id=world["t"], type="a11y_report")
    assert artifact.run_id is None
    assert (artifact.external_ref or {}).get("a11y_capture") == str(audit.id)


def test_re_finishing_an_audit_updates_its_report_rather_than_stacking_one(world):
    from apps.registry.models import Artifact

    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    assert Artifact.objects.filter(tenant_id=world["t"], type="a11y_report").count() == 1


def test_two_audits_keep_two_reports(world):
    """A baseline you cannot compare against the next one is not a baseline."""
    from apps.registry.models import Artifact

    first = _audit(world, "/login")
    _post(world, first, _screen())
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(first.id))

    second = _audit(world)
    _post(world, second, _screen("/login", axe_error="no scanner this time"))
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(second.id))

    keys = {(a.external_ref or {}).get("a11y_capture")
            for a in Artifact.objects.filter(tenant_id=world["t"], type="a11y_report")}
    assert keys == {str(first.id), str(second.id)}


def test_an_audit_where_nothing_opened_fails_loudly(world):
    audit = _audit(world, "/admin")
    _post(world, audit, _screen("/admin", load_error="HTTP 403", elements=[]))
    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))

    assert out["status"] == A11yBaselineAudit.Status.FAILED
    assert "nothing to report on" in out["reason"]
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.FAILED


def test_an_audits_start_and_end_are_in_the_activity_log(world):
    """Recon 2026-10-10, finding 11: the log listed the pages but never that an audit was started
    (by whom, on which address, over which pages) nor how it ended. Each is now one entry, filed
    under the project so the project's own log shows it."""
    from apps.a11y.baseline import abandon_audit
    from apps.ledger.models import Event

    failed = _audit(world, "/admin")
    _post(world, failed, _screen("/admin", load_error="HTTP 403", elements=[]))
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(failed.id))

    walked_off = _audit(world, "/", "/login")
    abandon_audit(tenant_id=world["t"], audit_id=str(walked_off.id))

    def actions(audit):
        return list(Event.objects.filter(target_type="a11y_audit", target_id=audit.id)
                    .order_by("ts").values_list("action", flat=True))

    assert actions(failed) == ["a11y.audit.started", "a11y.audit.failed"]
    assert actions(walked_off) == ["a11y.audit.started", "a11y.audit.abandoned"]
    started = Event.objects.get(target_id=failed.id, action="a11y.audit.started")
    assert started.payload["address"] == "http://localhost:5173"
    assert started.payload["pages"] == ["/admin"]
    assert str(started.project_id) == world["p"]


def test_an_audit_is_named_by_the_day_it_ran_never_by_its_id(world):
    """Recon 2026-10-10, finding 5: "baseline audit b0813885" reached the Artifacts list and the
    conformance statement. Named by the day instead, and still told apart from a second audit
    the same day."""
    from apps.a11y.baseline import _title, audit_label

    first = _audit(world, "/")
    second = _audit(world)
    day = f"{first.created_at.day} {first.created_at:%b %Y}"

    assert audit_label(first) == f"the audit of {day}"
    assert audit_label(second) == f"the audit of {day} (2nd that day)"
    assert _title(first) == f"audit of {day}"
    assert str(first.id)[:8] not in _title(first)


def test_an_audit_nobody_captured_anything_for_also_fails(world):
    audit = _audit(world, "/", "/login")
    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))
    assert out["status"] == A11yBaselineAudit.Status.FAILED
    assert out["never_reported"] == ["/", "/login"]


def test_a_finished_audit_records_what_happened_on_itself(world):
    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id))

    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.COMPLETE
    assert audit.summary["asked"] == 1 and audit.summary["opened"] == 1
    assert "ai_pass" in audit.summary


def test_an_audit_completes_when_its_judgment_run_ends(world):
    """The dispatched path. `finish_ai_pass` closes the audit AFTER publishing the report, so
    an audit is never shown as complete before the document it is complete because of exists."""
    from apps.a11y.aipass import SOURCE_RUN_KEY, finish_ai_pass
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    audit = _audit(world, "/login")
    _post(world, audit, _screen())
    spec = AgentSpec.objects.create(
        tenant=world["tenant"], key="09c_a11y_judge", semver="1.0.0",
        body_ref="agents/09c_a11y_judge/agent.md", phase_label="a11y_judge")
    item = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                   title="Accessibility judging")
    judge_run = Run.objects.create(
        tenant=world["tenant"], work_item=item, agent_spec=spec,
        inputs={SOURCE_RUN_KEY: str(audit.id)})

    out = finish_ai_pass(tenant_id=world["t"], judge_run_id=str(judge_run.id))
    assert out["published"] is True and out["audit_completed"] is True
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.COMPLETE


def _judging_world(world):
    """A tenant that can really dispatch a judge: agent registered, machine connected, and a
    user to own both — `_resolve_enrollment` returns nothing without one."""
    from apps.registry.models import AgentSpec
    from apps.runs.enrollment import enroll_runner
    from apps.tenancy.models import User

    user = User.objects.create_user(email="qa@acme.com", name="QA", tenant=world["tenant"],
                                    password="pw")
    AgentSpec.objects.create(
        tenant=world["tenant"], key="09c_a11y_judge", semver="1.0.0",
        prompt_version="a11y-judge-1", body_ref="agents/09c_a11y_judge/agent.md",
        recommended_engine="claude", recommended_model="claude-opus-5",
        phase_label="a11y_judge")
    enroll_runner(tenant_id=world["t"], project_id=world["p"],
                  developer_id=str(user.id), label="qa-laptop")
    return user


def _guarded_trigger(world):
    """`trigger_phase` with Temporal taken out and NOTHING ELSE.

    The platform's own `_guard_no_active_run` is called for real, so the refusal this test is
    about is the refusal the platform actually raises — not a stand-in exception chosen to
    match. Only the workflow start is skipped, which is `trigger_phase`'s own tested business.
    """
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.tenancy.context import tenant_context
    from orchestration.trigger import _guard_no_active_run

    def trigger(*, tenant_id, project_id, work_item_id, agent_key, **kwargs):
        with tenant_context(tenant_id):
            _guard_no_active_run(tenant_id, work_item_id)
            spec = AgentSpec.objects.get(tenant_id=tenant_id, key=agent_key)
            run = Run.objects.create(
                tenant_id=tenant_id, work_item_id=work_item_id, agent_spec=spec,
                status=Run.Status.RUNNING, engine=spec.recommended_engine,
                model=spec.recommended_model, prompt_version=spec.prompt_version)

        class _Outcome:
            run_id = str(run.id)
            workflow_id = f"agent-run-{run.id}"

        return _Outcome()

    return trigger


def test_closing_one_audit_twice_leaves_the_judging_pass_untouched(world):
    """The 31 August audit, end to end.

    Closing a 94-route audit is minutes of work — reconcile the routes, hash 2,171 elements,
    check each against the cache, file the rest, start the run. The companion's platform client
    gave up after 60 seconds, its daemon read that timeout as the audit having failed, and its
    recovery path closed the SAME audit again while the first close was still going.

    The second close was refused a judge (one was already running), and then: wrote off all
    1,065 captured elements as unjudgeable while 800 of them were being judged, replaced the
    first close's record of the pass with its own empty one, and marked the audit complete with
    the judge still working. Every wrong number the team saw afterwards came from that record.

    A repeat now returns what the first call left and changes nothing.
    """
    user = _judging_world(world)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                 base_url="http://localhost:5173", started_by=user.id)
    _post(world, audit, _screen())
    trigger = _guarded_trigger(world)

    first = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id), trigger=trigger)
    assert first["ai_pass"]["started"] is True, "the first close really did dispatch a judge"
    judge_run_id = first["ai_pass"]["judge_run_id"]
    assert judge_run_id

    audit.refresh_from_db()
    before = dict(audit.summary)
    assert audit.status == A11yBaselineAudit.Status.JUDGING

    second = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id), trigger=trigger)

    assert second["repeat"] is True
    assert "already in progress" in second["reason"]
    audit.refresh_from_db()
    assert audit.summary == before, "the record of the pass that IS running must not be replaced"
    assert audit.status == A11yBaselineAudit.Status.JUDGING, "the audit is not complete yet"
    assert audit.summary["ai_pass"]["judge_run_id"] == judge_run_id
    assert audit.summary["ai_pass"]["filed_unjudged"] == 0, "nothing may be written off"

    # And no second run was started for the judging work item either — the guard is what
    # refused, and this proves the refusal was obeyed rather than worked around.
    from apps.runs.models import Run

    assert Run.objects.filter(tenant_id=world["t"], agent_spec__key="09c_a11y_judge").count() == 1


def test_a_build_runs_judgment_does_not_look_like_an_audit(world):
    """The same wiring runs on every ordinary build. It must answer "not an audit" quietly."""
    from apps.a11y.aipass import SOURCE_RUN_KEY, finish_ai_pass
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    spec = AgentSpec.objects.create(
        tenant=world["tenant"], key="09c_a11y_judge", semver="1.0.0",
        body_ref="agents/09c_a11y_judge/agent.md", phase_label="a11y_judge")
    item = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                   title="Checkout")
    build_run = Run.objects.create(tenant=world["tenant"], work_item=item, agent_spec=spec)
    judge_run = Run.objects.create(
        tenant=world["tenant"], work_item=item, agent_spec=spec,
        inputs={SOURCE_RUN_KEY: str(build_run.id)})

    out = finish_ai_pass(tenant_id=world["t"], judge_run_id=str(judge_run.id))
    assert out["published"] is True and out["audit_completed"] is False


def test_finishing_an_audit_that_does_not_exist_says_so(world):
    import uuid

    with pytest.raises(BaselineError):
        finish_baseline_audit(tenant_id=world["t"], audit_id=str(uuid.uuid4()))


def test_completing_a_capture_key_that_is_not_an_audit_is_not_an_error(world):
    """A build run's key comes through here too — a valid UUID that names no audit."""
    import uuid

    assert complete_audit(world["t"], "") is False
    assert complete_audit(world["t"], "not-a-uuid") is False
    assert complete_audit(world["t"], str(uuid.uuid4())) is False


def test_completing_a_real_audit_marks_it_complete(world):
    audit = _audit(world, "/login")
    assert complete_audit(world["t"], str(audit.id)) is True
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.COMPLETE


def test_a_second_audit_reuses_the_first_ones_capture_where_nothing_changed(world):
    """QA-07 is what keeps a whole-app audit affordable on its second pass. It has to still
    work when the bucket is an audit's rather than a run's."""
    first = _audit(world, "/login")
    _post(world, first, _screen())
    second = _audit(world)
    result = _post(world, second, _screen())
    assert result["screens"][0]["reused"] is True


# ══ the audit script the companion runs ══════════════════════════════════════════════

def _script() -> str:
    return (_REPO / "runner" / "companion" / "assets" / "a11y_audit.mjs").read_text(
        encoding="utf-8")


def _offer_tags() -> set[str]:
    """The bare tag names the capture offers, read out of the script rather than restated."""
    block = _script().split("const OFFER = [", 1)[1].split("].join", 1)[0]
    return set(re.findall(r'"([a-z0-9]+)"', re.sub("//.*", "", block)))


def test_the_audit_script_offers_the_containers_that_structure_lives_on():
    """The other half of a pairing that failed silently for a whole audit.

    A rule that would claim an element never gets the chance if the capture never offers it,
    and nothing anywhere reports the difference. `/loans/current` tints each row of its loans
    table to carry the status; the colour rule claims a tinted row on sight
    (`test_color_selects_a_table_row_tinted_to_carry_a_status`); `tr` was not in this list. So
    the row never arrived, the page produced no colour finding, and the conformance statement
    recorded it as a page where 1.4.1 had been checked.

    The rest of these are offered for a reason worth stating, because most are not claimed by
    any rule yet: structure lives on the container, so a table with no header cells and a set
    of radio buttons with no grouping are invisible while only their children are offered. An
    element that is offered and declined is **counted**, and `rules.explain()` can name the
    rule that declined it. An element never offered is a silence nothing can measure.
    """
    offered = _offer_tags()
    for tag in ("table", "tr", "ul", "ol", "fieldset", "form", "canvas", "iframe"):
        assert tag in offered, tag


def test_the_audit_script_still_offers_what_it_always_did():
    """Added alongside the containers: growing the list must never quietly shrink it."""
    offered = _offer_tags()
    for tag in ("img", "svg", "area", "input", "button", "a", "select", "textarea",
                "h1", "h2", "h3", "h4", "h5", "h6", "label", "summary", "details",
                "p", "li", "td", "th", "span"):
        assert tag in offered, tag


def test_the_audit_script_measures_a_containers_shape():
    """The half of the container checks that lives in the browser.

    A table's markup grows with every row and is bounded; its shape is not. The counting has to
    happen where the live page is, so this pins that the capture does it and sends it under the
    name the platform reads. Verified in a real browser against a 401-row table: 31,985
    characters of markup, 906 of outline, nothing about the shape lost.
    """
    script = _script()
    assert "structure: outlineOf(el)" in script
    for part in ("tableOutline", "listOutline", "fieldsOutline", "repeatedOutline"):
        assert part in script, part
    # Every fact the judge is taught to read has to be one the capture actually sends.
    for field in ("header_cells", "header_scopes", "first_row", "first_column", "columns",
                  "grouped", "group_name", "other_children", "repeated_class"):
        assert field in script, field


def test_the_outline_is_bounded_so_a_long_container_costs_no_more_than_a_short_one():
    """The property that makes this a fix rather than a bigger limit. Raising the markup cap
    would only move the cliff; a bound on width does not have one."""
    script = _script()
    assert "MAX_SAMPLE = 12" in script
    assert "MAX_SAMPLE_CHARS = 40" in script


def test_a_container_the_capture_cannot_describe_is_reported_not_dropped():
    script = _script()
    assert '"unreadable"' in script or "kind: \"unreadable\"" in script


def test_the_audit_script_captures_all_six_style_keys():
    """A missing key does not raise anywhere — it reads as "no" and silently drops the element
    from every check that needed it. Both ends spell the list out for that reason."""
    from apps.a11y.checkers.rules import STYLE_KEYS

    script = _script()
    for key in STYLE_KEYS:
        assert f'"{key}"' in script, key


def test_the_audit_script_writes_every_field_the_platform_reads():
    script = _script()
    for field in ("selector", "tag", "role", "attrs", "text", "accessible_name",
                  "interactive", "rendered", "styles", "parent_styles", "html",
                  "context", "box", "axe_violations", "axe_error", "load_error",
                  "screenshot_base64", "screenshot_error"):
        assert field in script, field


def test_the_audit_script_takes_the_accessible_name_from_the_browser():
    """Never approximated from aria-label or the text: the `label` check exists for the case
    where the computed name and the visible text disagree."""
    script = _script()
    assert "page.accessibility.snapshot" in script
    assert "never from" in script


def test_the_audit_script_records_a_route_that_would_not_open():
    script = _script()
    assert "load_error" in script
    assert "HTTP ${response.status()}" in script


def test_the_audit_script_never_guesses_an_axe_package():
    """QA-11a's rule: a plausible-looking wrong import reads as a scan that ran."""
    script = _script()
    # The message now names BOTH places it looked — the project and the companion's own pinned
    # toolchain — because a missing scanner is no longer only the project's problem to fix.
    assert "axe-core could not be loaded from this project" in script
    assert "companion" in script
    assert "never guesses a package name" in script.lower()


def test_the_audit_script_honours_the_platforms_bounds():
    from apps.a11y.capture import MAX_ELEMENTS_PER_SCREEN, MAX_SCREENS

    script = _script()
    assert f"MAX_SCREENS = {MAX_SCREENS}" in script
    assert f"MAX_ELEMENTS_PER_SCREEN = {MAX_ELEMENTS_PER_SCREEN}" in script


def test_the_audit_script_does_not_judge_anything():
    script = _script()
    assert "It does not judge anything" in script


# ══ the companion side ═══════════════════════════════════════════════════════════════

class _FakeClient:
    def __init__(self, audit_id="a-1"):
        self.calls = []
        self.audit_id = audit_id

    def call(self, tool, **kwargs):
        self.calls.append({"tool": tool, **kwargs})
        if tool == "start_a11y_audit":
            return {"audit_id": self.audit_id, "status": "capturing",
                    "manifest": {"version": 1, "audit_id": self.audit_id,
                                 "base_url": kwargs.get("base_url", ""),
                                 "routes": ["/", "/login"],
                                 "output": "test-results/a11y-candidates.json"}}
        if tool == "finish_a11y_audit":
            return {"audit_id": self.audit_id, "status": "complete"}
        return {}


def test_the_companion_posts_one_screen_per_call():
    from runner.companion.a11yaudit import post_audit_screens

    client = _FakeClient()
    out = post_audit_screens([_screen("/"), _screen("/login")], client=client, audit_id="a-1")
    assert out["posted"] == 2
    assert [c["tool"] for c in client.calls] == ["ingest_a11y_audit_screen"] * 2


def test_a_screen_that_will_not_post_costs_that_screen_and_no_other():
    from runner.companion.a11yaudit import post_audit_screens

    class _Flaky(_FakeClient):
        def call(self, tool, **kwargs):
            if kwargs.get("screen", {}).get("route") == "/login":
                raise RuntimeError("upload rejected")
            return super().call(tool, **kwargs)

    out = post_audit_screens([_screen("/"), _screen("/login")], client=_Flaky(),
                             audit_id="a-1")
    assert out["posted"] == 1 and out["failed"] == ["/login: upload rejected"]


def test_an_absent_capture_file_is_no_capture_not_a_clean_pass(tmp_path):
    from runner.companion.a11yaudit import read_capture

    assert read_capture(tmp_path / "nothing.json") == []


def test_an_unreadable_capture_file_is_reported_not_raised(tmp_path):
    from runner.companion.a11yaudit import read_capture

    path = tmp_path / "a11y-candidates.json"
    path.write_text(json.dumps({"version": 99, "screens": []}), encoding="utf-8")
    assert read_capture(path) == []


def test_a_missing_node_is_reported_rather_than_crashing_the_pass(tmp_path):
    from runner.companion.a11yaudit import run_audit_script

    out = run_audit_script({"routes": ["/"], "output": "test-results/a11y-candidates.json"},
                           workdir=tmp_path, node="definitely-not-node-xyz")
    assert out["returncode"] == 127 and "not on PATH" in out["stderr"]
    assert out["screens"] == []


def test_the_audit_run_posts_what_it_captured_and_closes_the_audit(
        tmp_path, monkeypatch, ready_folder):
    from runner.companion import a11yaudit

    monkeypatch.setattr(a11yaudit, "run_audit_script", lambda manifest, **kw: {
        "screens": [_screen("/"), _screen("/login")], "output": "x",
        "returncode": 0, "stderr": ""})
    client = _FakeClient()
    out = a11yaudit.run_baseline_audit(
        client=client, project_id="p-1", base_url="http://localhost:5173",
        workdir=tmp_path)

    assert out["posted"] == 2 and out["captured"] == 2
    assert [c["tool"] for c in client.calls][0] == "start_a11y_audit"
    assert [c["tool"] for c in client.calls][-1] == "finish_a11y_audit"


# ══ one audit, as many passes as it takes (B5) ══════════════════
#
# `capture.MAX_SCREENS` bounds ONE capture document - a screen carries a full-page screenshot,
# and a file with hundreds of them is refused. It never bounded an application: screens are
# posted one per HTTP call and the audit is reconciled against its stored route list, whatever
# produced the rows. Until B5 the script simply took the first 60 routes and wrote a line about
# the rest to a console nobody was watching.


class _PassRecorder(_FakeClient):
    """A fake platform that hands back the routes it was asked to open, and remembers the
    screens posted to it."""

    def __init__(self, routes, audit_id="a-1"):
        super().__init__(audit_id=audit_id)
        self.routes = list(routes)
        self.posted_routes: list[str] = []

    def call(self, tool, **kwargs):
        out = super().call(tool, **kwargs)
        if tool == "start_a11y_audit":
            out["manifest"]["routes"] = list(self.routes)
            out["manifest"]["base_url"] = "http://127.0.0.1:5173"
        if tool == "ingest_a11y_audit_screen":
            self.posted_routes.append(kwargs["screen"]["route"])
        return out


def _script_stub(behaviour=None):
    """Stand in for the audit script: writes what a real pass would have written, honouring the
    per-pass output path so the isolation between passes is exercised rather than assumed."""
    seen: list[dict] = []

    def _run(manifest, *, workdir, **kw):
        seen.append({"routes": list(manifest["routes"]), "output": manifest["output"]})
        if behaviour is not None:
            result = behaviour(len(seen), manifest)
            if result is not None:
                return result
        path = Path(workdir) / manifest["output"]
        path.parent.mkdir(parents=True, exist_ok=True)
        screens = [_screen(route) for route in manifest["routes"]]
        path.write_text(json.dumps({"version": 1, "screens": screens}), encoding="utf-8")
        from runner.companion.a11yaudit import read_capture
        return {"screens": read_capture(path), "output": str(path),
                "returncode": 0, "stderr": ""}

    _run.seen = seen
    return _run


def test_a_big_audit_runs_in_passes_and_accounts_for_every_page(
        tmp_path, monkeypatch, ready_folder):
    from runner.companion import a11yaudit

    routes = [f"/p{i}" for i in range(130)]
    script = _script_stub()
    monkeypatch.setattr(a11yaudit, "run_audit_script", script)
    client = _PassRecorder(routes)

    out = a11yaudit.run_baseline_audit(client=client, project_id="p-1", workdir=tmp_path)

    assert [p["routes"] for p in out["passes"]] == [60, 60, 10], "three passes, none over 60"
    assert out["captured"] == 130 and out["posted"] == 130
    assert client.posted_routes == routes, "every page, once, in order, to the SAME audit"
    assert [c["tool"] for c in client.calls].count("start_a11y_audit") == 1
    assert [c["tool"] for c in client.calls].count("finish_a11y_audit") == 1


def test_each_pass_writes_its_own_file(tmp_path, monkeypatch, ready_folder):
    from runner.companion import a11yaudit

    script = _script_stub()
    monkeypatch.setattr(a11yaudit, "run_audit_script", script)
    a11yaudit.run_baseline_audit(client=_PassRecorder([f"/p{i}" for i in range(130)]),
                                 project_id="p-1", workdir=tmp_path)
    outputs = [call["output"] for call in script.seen]
    assert len(set(outputs)) == 3, outputs
    assert outputs[1].endswith("a11y-candidates-pass-2.json")


def test_a_pass_that_dies_never_reposts_the_previous_passs_screens(
        tmp_path, monkeypatch, ready_folder):
    """The trap this design exists to avoid. Share one filename and a pass that dies before
    writing leaves the previous pass's file in place — which would be read again and posted a
    second time, reporting pages as seen in a pass that never visited them."""
    from runner.companion import a11yaudit

    def _die_on_second(number, manifest):
        if number == 2:
            return {"screens": [], "output": manifest["output"], "returncode": 1,
                    "stderr": "the audit stopped"}
        return None

    script = _script_stub(_die_on_second)
    monkeypatch.setattr(a11yaudit, "run_audit_script", script)
    routes = [f"/p{i}" for i in range(130)]
    client = _PassRecorder(routes)

    out = a11yaudit.run_baseline_audit(client=client, project_id="p-1", workdir=tmp_path)

    assert client.posted_routes == routes[:60] + routes[120:], \
        "the dead pass's pages are absent — not duplicated from pass 1"
    assert len(client.posted_routes) == len(set(client.posted_routes)), "no page posted twice"
    assert out["passes"][1] == {"pass": 2, "routes": 60, "captured": 0, "posted": 0,
                                "script_returncode": 1}


def test_a_failed_pass_does_not_abandon_the_audit(tmp_path, monkeypatch, ready_folder):
    from runner.companion import a11yaudit

    script = _script_stub(lambda n, m: (
        {"screens": [], "output": m["output"], "returncode": 1, "stderr": "boom"}
        if n == 1 else None))
    monkeypatch.setattr(a11yaudit, "run_audit_script", script)
    client = _PassRecorder([f"/p{i}" for i in range(130)])

    out = a11yaudit.run_baseline_audit(client=client, project_id="p-1", workdir=tmp_path)

    assert len(script.seen) == 3, "the later passes still ran"
    assert [c["tool"] for c in client.calls][-1] == "finish_a11y_audit", "still closed"
    assert out["captured"] == 70
    assert out["script_returncode"] == 1, "one number, and it is not the last pass's"


def test_an_audit_that_fits_in_one_pass_is_unchanged(tmp_path, monkeypatch, ready_folder):
    from runner.companion import a11yaudit

    script = _script_stub()
    monkeypatch.setattr(a11yaudit, "run_audit_script", script)
    out = a11yaudit.run_baseline_audit(client=_PassRecorder(["/", "/login"]),
                                       project_id="p-1", workdir=tmp_path)
    assert len(out["passes"]) == 1
    assert script.seen[0]["output"] == "test-results/a11y-candidates.json", \
        "the plain name — nothing changes for a project that always fitted"


def test_a_page_that_will_not_open_is_reported_in_whichever_pass_it_fell_in(world, tmp_path):
    """The platform half, over two capture documents rather than one: the reconciliation accounts
    for all 70 routes, and a page that would not open in the SECOND pass is recorded as itself
    rather than as one nobody asked about. (The pass loop itself is covered above; this is the
    end it posts into.)"""
    routes = [f"/p{i}" for i in range(70)]
    _register(world, *routes)
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                 base_url="http://127.0.0.1:5173")

    def _run(manifest, *, workdir, **kw):
        screens = []
        for route in manifest["routes"]:
            if route == "/p65":                       # in the SECOND pass
                screens.append({"route": route, "url": route, "elements": [],
                                "load_error": "the page returned HTTP 404"})
            else:
                screens.append(_screen(route))
        from apps.a11y.capture import parse_capture
        return {"screens": parse_capture(json.dumps({"version": 1, "screens": screens})),
                "output": manifest["output"], "returncode": 0, "stderr": ""}

    for pass_routes in (routes[:60], routes[60:]):
        ran = _run({"routes": pass_routes, "output": "x"}, workdir=tmp_path)
        for screen in ran["screens"]:
            ingest_audit_capture(tenant_id=world["t"], audit_id=str(audit.id),
                                 text=json.dumps({"version": 1, "screens": [screen]}),
                                 object_store=InMemoryObjectStore())

    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id),
                                trigger=lambda **kw: None)
    assert out["asked"] == 70
    assert out["unreachable"] == ["/p65"]
    assert out["never_reported"] == []


# ══ the platform-state tools ═════════════════════════════════════════════════════════

def test_the_audit_tools_are_companion_only_never_the_engines():
    """Same rule as `ingest_a11y_candidates`: an agent able to write a capture could describe
    a page instead of one having been visited."""
    from runner.companion.runner import BUILD_STATE_TOOLS

    from api.runner_views import _BUILD_STATE_TOOLS

    for tool in ("start_a11y_audit", "ingest_a11y_audit_screen", "finish_a11y_audit"):
        assert tool in _BUILD_STATE_TOOLS, tool
        assert tool not in BUILD_STATE_TOOLS, tool


def test_the_start_tool_returns_a_manifest(world):
    from mcp_platform_state import tools

    _register(world, "/", "/login")
    out = tools.start_a11y_audit(world["t"], world["p"], base_url="http://localhost:5173")
    assert out["manifest"]["routes"] == ["/", "/login"]
    assert out["status"] == A11yBaselineAudit.Status.CAPTURING


def test_the_ingest_tool_stores_a_screen(world):
    from mcp_platform_state import tools

    audit = _audit(world, "/login")
    out = tools.ingest_a11y_audit_screen(world["t"], str(audit.id), _screen())
    assert out["imported"] is True
    assert A11yScreenScan.objects.filter(tenant_id=world["t"], route="/login").exists()


def test_the_finish_tool_closes_the_audit(world):
    from mcp_platform_state import tools

    audit = _audit(world, "/login")
    tools.ingest_a11y_audit_screen(world["t"], str(audit.id), _screen())
    out = tools.finish_a11y_audit(world["t"], str(audit.id))
    assert out["opened"] == 1


# ══ the REST surface ═════════════════════════════════════════════════════════════════

def test_routes_and_audits_are_reachable_from_the_api():
    """The endpoints exist and are named — the detail of each is covered above."""
    from api.views import ProjectViewSet

    assert hasattr(ProjectViewSet, "a11y_routes")
    assert hasattr(ProjectViewSet, "a11y_audits")
    assert ProjectViewSet.a11y_routes.mapping.keys() >= {"get", "put"}
    assert ProjectViewSet.a11y_audits.mapping.keys() >= {"get", "post"}


# ══ can this machine run an audit at all? (task 8a) ══════════════════════════
#
# The audit script imports the browser and the scanner BY NAME. Node resolves a bare name from
# the importing FILE's directory upward — `runner/companion/assets/` — and the companion ships
# no `node_modules` and no `package.json`, so it found neither tool on any machine, ever.
# Running from the project did not help (`cwd` is not consulted) and neither did `NODE_PATH`
# (ignored for ES modules). Anchoring resolution at the working directory is what fixes it.
#
# Nothing caught this because nothing has ever executed the script: every test above stubs it,
# and the one real invocation points at a missing `node` on purpose. So the tests below run it
# for real. They skip where there is no Node — but they are never faked, because faking is
# precisely what hid this.

_NODE = shutil.which("node")
needs_node = pytest.mark.skipif(_NODE is None, reason="no Node on this machine")


def _project_with(tmp_path, *, browser=True, scanner=True) -> Path:
    """A throwaway project carrying stand-ins for the two tools, installed where a real project
    installs them. Stubs rather than the real packages: what is under test is whether Node can
    SEE the project's `node_modules` from the script, which a two-line module proves as well as
    a 200MB browser and in a fraction of the time."""
    root = tmp_path / "client-project"
    if browser:
        pkg = root / "node_modules" / "playwright"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"name": "playwright", "version": "1.99.0", "main": "index.js"}),
            encoding="utf-8")
        (pkg / "index.js").write_text(
            "module.exports = { chromium: { launch: async () => ({}) } };", encoding="utf-8")
    if scanner:
        pkg = root / "node_modules" / "axe-core"
        pkg.mkdir(parents=True)
        (pkg / "package.json").write_text(
            json.dumps({"name": "axe-core", "version": "4.13.0", "main": "axe.js"}),
            encoding="utf-8")
        (pkg / "axe.js").write_text(
            'module.exports = { source: "window.axe = {};", version: "4.13.0" };',
            encoding="utf-8")
    root.mkdir(parents=True, exist_ok=True)
    return root


@needs_node
def test_the_script_finds_the_tools_in_the_project_being_audited(tmp_path):
    """The fix, proved by running the real script. Before it, this returned not-ok on every
    machine — including one with both tools correctly installed."""
    from runner.companion.a11yaudit import preflight

    out = preflight(workdir=_project_with(tmp_path), node=_NODE)
    assert out["ok"] is True, out
    assert out["browser"]["ok"] is True
    assert out["scanner"]["ok"] is True
    assert out["scanner"]["version"] == "4.13.0", "the project's version, which the report names"


#: Both of the tests below describe the world #9 built: a project with nothing installed is
#: AUDITABLE, because the companion carries its own pinned toolchain. That is only true on a
#: machine where the companion's toolchain has actually been installed, so they are skipped
#: rather than failed where it has not — exactly as `needs_node` skips where there is no Node.
#: The case where BOTH are missing has its own test below, and needs no toolchain to prove.
_COMPANION_MODULES = Path(__file__).resolve().parents[2] / "runner" / "node_modules"
needs_companion_toolchain = pytest.mark.skipif(
    not ((_COMPANION_MODULES / "playwright").exists()
         and (_COMPANION_MODULES / "axe-core").exists()),
    reason="the companion's own toolchain is not installed (npm install in runner/)",
)


@needs_node
@needs_companion_toolchain
def test_a_folder_with_nothing_installed_falls_back_to_the_companion(tmp_path):
    """A project with no `node_modules` of its own is audited, not refused (#9).

    **This test used to assert the opposite** — that an empty folder was refused with a message
    naming it and the npm command. That was true until 20 August, when a missing clone became a
    fallback rather than a refusal: an application written in Django, Rails or .NET has no
    `node_modules` and never will, and requiring one meant the only way to audit it was to add
    npm dev-dependencies to a client's own repository in order to look at it. The refusal is now
    reserved for a machine where the companion has nothing either, which is the test below.
    """
    from runner.companion.a11yaudit import preflight

    bare = tmp_path / "empty"
    bare.mkdir()
    out = preflight(workdir=bare, node=_NODE)
    assert out["ok"] is True, out
    assert out["browser"]["ok"] is True, "the companion's own browser answers for this project"
    assert out["scanner"]["ok"] is True
    assert out["scanner"]["from"] == "companion", (
        "and the report must be able to SAY it was ours, not the application's")


@needs_node
@needs_companion_toolchain
def test_the_scanner_alone_missing_falls_back_without_taking_the_project_browser_with_it(tmp_path):
    """The two tools resolve independently, and the fallback is per tool, not per project.

    A project shipping playwright but no axe is scanned with **its own** browser and **our**
    scanner — so `from` is what the report reads to stamp `(companion)` on the version, and it
    must say `companion` here even though the browser came from the project.

    **This test used to assert `scanner.ok is False`** and the "could not be loaded" message.
    That was the pre-#9 world too: the scanner had no fallback to reach for. The sentence it was
    written to protect — that a missing scanner is a warning and not a refusal — is still true
    and still tested, by the both-missing test below, which is now the only way to be without one.
    """
    from runner.companion.a11yaudit import preflight

    out = preflight(workdir=_project_with(tmp_path, scanner=False), node=_NODE)
    assert out["ok"] is True, "the audit still runs"
    assert out["scanner"]["ok"] is True
    assert out["scanner"]["from"] == "companion"


@needs_node
def test_a_machine_with_no_toolchain_anywhere_names_the_folder_and_the_command(tmp_path,
                                                                               monkeypatch):
    """Both places empty — the one remaining refusal, and it must stay actionable.

    Run from a COPY of the real script placed where nothing resolves above it, which is exactly
    what a machine that has never run `npm install` in `runner/` looks like. That folder cannot
    be faked away with a stub: faking is what let the pre-#9 assertions above sit green for a
    day after the behaviour they described had gone.
    """
    import shutil as _shutil

    from runner.companion import a11yaudit

    stranded = tmp_path / "no-toolchain"
    stranded.mkdir()
    script = stranded / "a11y_audit.mjs"
    _shutil.copy(a11yaudit.AUDIT_SCRIPT, script)
    monkeypatch.setattr(a11yaudit, "AUDIT_SCRIPT", script)

    out = a11yaudit.preflight(workdir=stranded, node=_NODE)
    assert out["ok"] is False
    assert str(stranded) in out["browser"]["error"], "the folder we looked in, by name"
    assert "npm install -D playwright axe-core" in out["browser"]["error"]
    assert "runner/" in out["browser"]["error"], "and the companion-wide fix, which is the real one"
    # The scanner is the warning half, not the refusal half — it says so separately.
    assert out["scanner"]["ok"] is False
    assert "the measurable checks did not run" in out["scanner"]["error"]


def test_a_machine_with_no_node_is_reported_as_a_folder_that_cannot_run(tmp_path):
    from runner.companion.a11yaudit import preflight

    out = preflight(workdir=tmp_path, node="definitely-not-node-xyz")
    assert out["ok"] is False and "not on PATH" in out["browser"]["error"]


def test_an_audit_that_cannot_open_a_browser_visits_nothing_and_says_why(tmp_path, monkeypatch):
    """It still opens and closes an audit — so every route is accounted for and the failure is
    on the record — but it does not pretend to visit anything, and the reason it carries is the
    real one rather than the generic 'the application did not respond'."""
    from runner.companion import a11yaudit

    monkeypatch.setattr(a11yaudit, "preflight", lambda **kw: {
        "ok": False, "cwd": str(tmp_path),
        "browser": {"ok": False, "error": f"Playwright is not installed in {tmp_path}"},
        "scanner": {"ok": False, "version": "", "error": ""}})
    ran = []
    monkeypatch.setattr(a11yaudit, "run_audit_script",
                        lambda *a, **kw: ran.append(1) or {"screens": [], "output": "",
                                                           "returncode": 0, "stderr": ""})
    client = _FakeClient()
    out = a11yaudit.run_baseline_audit(client=client, project_id="p-1",
                                       base_url="http://localhost:5173", workdir=tmp_path)

    assert ran == [], "no pass is attempted when no page can be opened"
    assert out["captured"] == 0 and out["script_returncode"] == 3
    finish = [c for c in client.calls if c["tool"] == "finish_a11y_audit"]
    assert len(finish) == 1
    assert "Playwright is not installed" in finish[0]["reason"]


def test_the_machines_own_reason_replaces_the_generic_one(world):
    """The generic message blames the application and sends someone to check a server nothing
    ever contacted. When the machine knows better, it says so."""
    audit = _audit(world, "/", "/login")
    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id),
                                reason="Playwright is not installed in C:/work/meridian")

    assert out["status"] == A11yBaselineAudit.Status.FAILED
    assert out["reason"] == "Playwright is not installed in C:/work/meridian"
    assert out["asked"] == 2 and out["opened"] == 0, "every route is still accounted for"


def test_a_stated_reason_cannot_overrule_a_real_capture(world):
    """A reason explains an empty audit. It must never be able to mark a working one failed."""
    audit = _audit(world, "/login")
    _post(world, audit, _screen("/login"))
    out = finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id),
                                reason="Playwright is not installed")

    assert out["status"] != A11yBaselineAudit.Status.FAILED
    assert "reason" not in out


# ══ an audit a machine can be handed (task 8a) ═══════════════════════════════
#
# Until now an audit only ever existed because somebody ran a command on the machine that would
# visit it. The screen creates one instead, and a companion picks it up — the same shape code
# intelligence took, for the same reason: mechanical work with no engine and no work item behind
# it, so it rides its own channel rather than the plan/review/build one.


def _enrol(world, label="dev-1"):
    from apps.runs.models import RunnerEnrollment

    return RunnerEnrollment.objects.create(
        tenant=world["tenant"], project=world["project"], label=label,
        enroll_token_hash=f"hash-{label}")


def _claim(world, runner):
    """What the companion's claim does, without the HTTP layer: the view's own body."""
    from django.test import RequestFactory

    from api.runner_views import RunnerA11yAuditClaimView, RunnerStateView

    request = RequestFactory().get("/api/runner/a11y-audits/")
    original = RunnerStateView._resolve_runner
    RunnerStateView._resolve_runner = staticmethod(lambda _r: runner)
    try:
        return RunnerA11yAuditClaimView().get(request)
    finally:
        RunnerStateView._resolve_runner = original


def test_an_audit_opened_from_the_app_waits_for_a_machine(world):
    """The button cannot visit anything itself, so the audit it creates says so rather than
    claiming to be capturing from the moment it is pressed."""
    _repo(world)
    _register(world, "/", "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    assert audit.status == A11yBaselineAudit.Status.PENDING


def test_an_audit_started_at_the_machine_does_not_wait_for_one(world):
    """The command line opens an audit on the machine that is about to visit it. Making that
    one wait for a claim would leave every terminal-run audit sitting forever."""
    audit = _audit(world, "/", "/login")
    assert audit.status == A11yBaselineAudit.Status.CAPTURING


def test_the_first_screen_is_what_makes_an_audit_capturing(world):
    """One rule for both ways in, and it is a fact rather than a declaration: a screen arrived,
    so something is visiting."""
    _repo(world)
    _register(world, "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    _post(world, audit, _screen("/login"))
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.CAPTURING


def test_a_companion_claims_the_waiting_audit_and_is_told_where_to_run_it(world):
    _repo(world)
    _register(world, "/", "/login")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)

    body = _claim(world, _enrol(world)).data
    assert body["audit_id"] == str(audit.id)
    assert body["repo"] == "acme/web", "the folder the browser and scanner come from"
    assert body["manifest"]["routes"] == ["/", "/login"]
    audit.refresh_from_db()
    assert audit.status == A11yBaselineAudit.Status.CLAIMED
    assert audit.claimed_at is not None


def test_two_machines_never_take_the_same_audit(world):
    """A broadcast audit binds to the machine that takes it, so the second one finds nothing."""
    _repo(world)
    _register(world, "/")
    start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)

    first = _claim(world, _enrol(world, "dev-1"))
    second = _claim(world, _enrol(world, "dev-2"))
    assert first.status_code == 200
    assert second.status_code == 204, "there is one audit and one machine already has it"


def test_a_machine_that_restarts_mid_audit_picks_its_own_audit_back_up(world):
    """The common failure: the companion is restarted while an audit is in its hands. Without
    this the audit sits `claimed` and the person waiting sees a machine that never got to it."""
    from datetime import timedelta

    from django.utils import timezone

    _repo(world)
    _register(world, "/")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    machine = _enrol(world, "dev-1")
    _claim(world, machine)

    audit.refresh_from_db()
    audit.claimed_at = timezone.now() - timedelta(hours=2)
    audit.save(update_fields=["claimed_at"])

    again = _claim(world, machine)
    assert again.status_code == 200 and again.data["audit_id"] == str(audit.id)


def test_another_machine_does_not_take_over_an_audit_in_progress(world):
    """Deliberate, and the same rule code intelligence has. An audit belongs to the machine
    that can reach the running application; a colleague's machine may not have it up at all,
    and handing the audit over would produce a report saying every page was unreachable —
    which is far worse than an audit that visibly stalled. A stalled one is on the screen with
    the time it was claimed, and running again opens a fresh one.
    """
    from datetime import timedelta

    from django.utils import timezone

    _repo(world)
    _register(world, "/")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    _claim(world, _enrol(world, "dev-1"))
    audit.refresh_from_db()
    audit.claimed_at = timezone.now() - timedelta(hours=2)
    audit.save(update_fields=["claimed_at"])

    assert _claim(world, _enrol(world, "dev-2")).status_code == 204


def test_a_finished_audit_is_never_claimed(world):
    """`complete`, `failed`, `capturing` — none of them is work waiting for a machine."""
    _repo(world)
    _register(world, "/")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    audit.status = A11yBaselineAudit.Status.COMPLETE
    audit.save(update_fields=["status"])

    assert _claim(world, _enrol(world)).status_code == 204


def test_a_project_with_no_repository_is_handed_the_reason_not_a_guess(world):
    """There is nowhere to run without a project folder, and the person needs to be told what
    to register — an audit that is claimed and silently dropped looks like one nobody picked up.
    """
    _register(world, "/")
    A11yBaselineAudit.objects.create(
        tenant=world["tenant"], project=world["project"], base_url="http://localhost:5173",
        routes=["/"], status=A11yBaselineAudit.Status.PENDING)

    body = _claim(world, _enrol(world)).data
    assert body["repo"] == ""
    assert "no repository registered" in body["repo_reason"]


def test_a_handed_audit_is_run_not_opened_again(tmp_path, monkeypatch, ready_folder):
    """The seam that would have doubled every audit: the screen creates one, the companion is
    handed it, and the pass loop used to open its own as its first act."""
    from runner.companion import a11yaudit

    class _Handed(_FakeClient):
        def call(self, tool, **kwargs):
            out = super().call(tool, **kwargs)
            if tool == "get_a11y_audit":
                return {"audit_id": "handed-1", "status": "claimed",
                        "manifest": {"version": 1, "audit_id": "handed-1",
                                     "base_url": "http://127.0.0.1:5173", "routes": ["/"],
                                     "output": "test-results/a11y-candidates.json"}}
            return out

    monkeypatch.setattr(a11yaudit, "run_audit_script", lambda manifest, **kw: {
        "screens": [_screen("/")], "output": "x", "returncode": 0, "stderr": ""})
    client = _Handed()
    out = a11yaudit.run_baseline_audit(client=client, project_id="p-1", workdir=tmp_path,
                                       audit_id="handed-1")

    tools = [c["tool"] for c in client.calls]
    assert "start_a11y_audit" not in tools, "a handed audit must never open a second one"
    assert tools[0] == "get_a11y_audit"
    assert out["audit_id"] == "handed-1" and out["posted"] == 1


def test_reading_an_audit_back_cannot_widen_what_it_was_asked_to_visit(world):
    """A companion that reconnects asks again. The frozen list is what it gets, even after
    somebody registers more pages in the meantime."""
    from apps.a11y.baseline import audit_snapshot

    _register(world, "/", "/login")
    audit = _audit(world, "/", "/login")
    _register(world, "/", "/login", "/basket")

    snap = audit_snapshot(tenant_id=world["t"], audit_id=str(audit.id))
    assert snap["manifest"]["routes"] == ["/", "/login"]


# ── a route that is a pattern ───────────────────────────────────────────────
#
# `/events/:id` is how a developer writes "any event". No browser can open it, so before this it
# was asked for on every audit and reported as never opened on every audit — honest, and
# permanently useless.


def test_a_pattern_route_is_visited_by_example_and_recorded_as_the_pattern(world):
    audit = _audit(world, "/", "/events/:id")
    A11yRoute.objects.filter(tenant_id=world["t"], path="/events/:id").update(
        example_path="/events/482")

    manifest = audit_manifest(audit)
    assert manifest["routes"] == ["/", "/events/:id"], "the pattern is what the audit asked for"
    assert manifest["visit"] == {"/events/:id": "/events/482"}, "the page actually opened"


def test_a_project_of_real_pages_carries_no_example_map_at_all(world):
    audit = _audit(world, "/", "/login")
    assert audit_manifest(audit)["visit"] == {}


def test_the_example_is_where_the_browser_goes_and_the_pattern_is_what_is_filed(world):
    """The whole point of keeping them apart: findings stay attached to the page of the
    application, not to whichever example happened to be used this time."""
    audit = _audit(world, "/events/:id")
    A11yRoute.objects.filter(tenant_id=world["t"], path="/events/:id").update(
        example_path="/events/482")
    _post(world, audit, _screen("/events/:id", url="http://localhost:5173/events/482"))

    scan = A11yScreenScan.objects.get(tenant_id=world["t"], run_key=str(audit.id))
    assert scan.route == "/events/:id", "one row per page of the application"
    assert scan.url.endswith("/events/482"), "and the evidence says what was really opened"


# ══ registering pages from the app (task 8a) ═════════════════════════════════
#
# A page is identified BY ITS PATH — there is no hidden id, and the database's one rule is one
# row per (project, path). So editing the text of a path does not edit a page, it names a
# different one. Everything below exists because that is invisible from where the user sits.


def _paste(world, text, **kw):
    from apps.a11y.routes import parse_routes_text, register_routes

    return register_routes(tenant_id=world["t"], project_id=world["p"],
                           routes=parse_routes_text(text), **kw)


def test_a_pasted_list_of_paths_is_registered(world):
    out = _paste(world, '["/", "/catalogue"]')
    assert out["added"] == ["/", "/catalogue"] and out["total"] == 2


def test_a_pasted_list_of_entries_keeps_the_names_and_the_scope(world):
    _paste(world, json.dumps([
        {"path": "/", "title": "Home"},
        {"path": "/admin/debug", "title": "Internal debug page", "enabled": False},
    ]))
    rows = {r.path: r for r in A11yRoute.objects.filter(tenant_id=world["t"])}
    assert rows["/"].label == "Home"
    assert rows["/admin/debug"].enabled is False


def test_title_and_label_are_one_field_and_not_two(world):
    """`title` is what an exported list calls the human name and `label` is what this table
    calls it. Accepting both is an alias; storing both would be a second field to keep in step."""
    _paste(world, json.dumps([{"path": "/a", "title": "A"}, {"path": "/b", "label": "B"}]))
    rows = {r.path: r.label for r in A11yRoute.objects.filter(tenant_id=world["t"])}
    assert rows == {"/a": "A", "/b": "B"}


def test_an_entry_with_no_path_names_itself_and_registers_nothing(world):
    """The failure this is really about: an export whose path column is called something else.
    'A route has no path' is unactionable on a list of 69, so the entry and its keys are handed
    back — and because nothing is written, there is no half-registered list to clean up."""
    from apps.a11y.routes import RouteError

    with pytest.raises(RouteError) as exc:
        _paste(world, json.dumps([
            {"path": "/", "title": "Home"},
            {"url": "/catalogue", "name": "Browse", "inScope": True},
        ]))
    message = str(exc.value)
    assert 'Page 2 of 2' in message
    assert "`url`" in message and "`name`" in message and "`inScope`" in message
    assert A11yRoute.objects.filter(tenant_id=world["t"]).count() == 0, "all or nothing"


def test_a_key_we_do_not_recognise_is_named_back_rather_than_dropped(world):
    """The dangerous silence. If an export calls the in-scope flag `inScope`, every page comes
    back in scope and we audit the ones the client excluded — with nothing anywhere saying a
    flag was ignored. Naming it is what turns that into a ten-second fix."""
    out = _paste(world, json.dumps([
        {"path": "/", "inScope": True, "owner": "web"},
        {"path": "/catalogue", "inScope": False},
    ]))
    assert out["ignored_keys"] == [{"key": "inScope", "entries": 2},
                                   {"key": "owner", "entries": 1}]
    assert out["total"] == 2, "the pages are still registered — throwing them away helps nobody"


def test_every_column_is_named_back_and_not_only_the_scope_flag(world):
    out = _paste(world, json.dumps([{"path": "/", "heading": "Home", "weight": 3}]))
    assert [k["key"] for k in out["ignored_keys"]] == ["heading", "weight"]


def test_something_that_is_not_a_list_of_pages_says_so_in_those_words(world):
    """Still refused, and now with a sharper reason.

    `"/, /catalogue"` does not open with `[` or `{`, so it is read as one path per line — and
    the one line it has contains a space, which is the specific thing that cannot be a path.
    Saying that beats "this could not be read as a list of pages", which is what it used to say
    and which left the reader to work out which part was wrong.
    """
    from apps.a11y.routes import RouteError, parse_routes_text

    with pytest.raises(RouteError) as exc:
        parse_routes_text("/, /catalogue")
    assert "contains a space" in str(exc.value)
    # A malformed JSON list still gets the JSON answer — line mode must not swallow it.
    with pytest.raises(RouteError) as exc:
        parse_routes_text('["/", "/catalogue"')
    assert "couldn't be read as a list of pages" in str(exc.value)


# ── One path per line, which is what people actually paste ──────────────────
#
# It used to be refused outright, with a message that explained JSON to somebody who had just
# pasted a perfectly clear list of pages. The first thing anyone does on this screen failed.


def test_one_path_per_line_is_a_list_of_pages(world):
    out = _paste(world, "/\n/catalogue\n/catalogue/:id")
    assert out["added"] == ["/", "/catalogue", "/catalogue/:id"] and out["total"] == 3


def test_blank_lines_and_comments_are_skipped_not_refused(world):
    out = _paste(world, "\n/  \n\n# the members area\n/account\n")
    assert out["added"] == ["/", "/account"]


def test_a_line_with_a_space_is_refused_by_name_and_by_number(world):
    """The hole that killed the earlier line-per-path form, closed rather than reopened.

    `normalise_path` rejects an empty path, a full URL, a path not starting with `/` and a line
    break — but NOT a space. `Home /catalogue` would register a page that cannot exist and be
    reported unreachable on every audit, forever, from a typo nobody can see.
    """
    from apps.a11y.routes import RouteError, parse_routes_text

    with pytest.raises(RouteError) as exc:
        parse_routes_text("/\nHome /catalogue\n/account")
    assert "Line 2" in str(exc.value) and "contains a space" in str(exc.value)


def test_a_half_converted_json_list_still_reads_as_paths(world):
    """Quotes and trailing commas belong to the other format, not to the path."""
    out = _paste(world, '"/",\n"/catalogue",')
    assert out["added"] == ["/", "/catalogue"]


def test_nothing_pasted_is_still_nothing_pasted(world):
    from apps.a11y.routes import RouteError, parse_routes_text

    with pytest.raises(RouteError, match="Nothing was pasted"):
        parse_routes_text("\n  \n# only a comment\n")


# ── `in_scope` is the name most route lists actually use ────────────────────


def test_in_scope_is_the_same_flag_as_enabled(world):
    """Our own reference brownfield app writes `in_scope` for all 69 of its routes.

    Without the alias every one came back as an unrecognised column and every page was
    registered in scope — including the one its author had deliberately excluded. The warning
    that named the column was honest and still fires for anything genuinely unknown; it was the
    alias that was missing.
    """
    from apps.a11y.models import A11yRoute

    out = _paste(world, json.dumps([
        {"path": "/", "title": "Home", "in_scope": True},
        {"path": "/health", "title": "Health", "in_scope": False},
    ]))
    assert out["ignored_keys"] == [], "`in_scope` is recognised, so nothing is named back"
    rows = {r.path: r.enabled for r in A11yRoute.objects.filter(project_id=world["p"])}
    assert rows == {"/": True, "/health": False}


def test_a_genuinely_unknown_scope_flag_is_still_named_back(world):
    """`inScope` (camelCase) is NOT the alias, and must keep being reported."""
    out = _paste(world, json.dumps([{"path": "/", "inScope": False}]))
    assert out["ignored_keys"] == [{"key": "inScope", "entries": 1}]


def test_a_single_entry_without_its_brackets_is_still_a_list_of_one(world):
    from apps.a11y.routes import parse_routes_text

    assert parse_routes_text('{"path": "/checkout"}') == [{"path": "/checkout"}]


def test_an_example_is_checked_like_any_other_path(world):
    """An example that is not a path would send the audit to an address nobody asked for."""
    from apps.a11y.routes import RouteError

    with pytest.raises(RouteError) as exc:
        _paste(world, json.dumps([{"path": "/events/:id", "example": "events/482"}]))
    assert 'must start with a slash' in str(exc.value)


def test_an_example_that_is_the_route_itself_is_not_an_example(world):
    _paste(world, json.dumps([{"path": "/checkout", "example": "/checkout"}]))
    assert A11yRoute.objects.get(tenant_id=world["t"], path="/checkout").example_path == ""


# ── what a paste would do, before it does it ────────────────────────────────
#
# The confirm step. Renaming a path by re-pasting cannot be told from adding a page, because
# from the database's point of view it IS adding a page. The only place that distinction can be
# made is in front of the person who typed it, before anything is written.


def _open_finding(world, route):
    """One open problem recorded against a page, the way a real audit records one."""
    from apps.a11y.report import SOURCE_AI, MergedReport, ReportRow

    record_run_findings(
        tenant_id=world["t"], project_id=world["p"],
        run_id="c0ffee00-0000-4000-8000-000000000009",
        report=MergedReport(rows=[ReportRow(
            source=SOURCE_AI, outcome="failure", criteria=("1.1.1",), route=route,
            selector="img.hero", evidence="alt reads like a filename", confidence=0.9,
            checker="alt", verdict="fail", suggested_fix="describe it", screenshot_ref="",
            content_hash="h-1", engine="claude", model="opus", prompt_version="v3",
        )], routes=[route]))


def _preview(world, text):
    from apps.a11y.routes import parse_routes_text, preview_registration

    return preview_registration(tenant_id=world["t"], project_id=world["p"],
                                routes=parse_routes_text(text))


def test_a_preview_writes_nothing(world):
    _preview(world, '["/", "/catalogue"]')
    assert A11yRoute.objects.filter(tenant_id=world["t"]).count() == 0


def test_a_renamed_path_shows_up_as_one_new_page_and_one_left_behind(world):
    """The team's own scenario. Five pages registered, the third edited, the list pasted again:
    the platform sees five paths of which one is new, and one it already has that nobody
    mentioned. Without this the sixth page stays in scope and is audited forever."""
    _paste(world, json.dumps(["/", "/catalogue", "/catalogue/search", "/account/holds"]))

    out = _preview(world, json.dumps(["/", "/catalogue", "/catalogue/results",
                                      "/account/holds"]))
    assert out["adding"] == ["/catalogue/results"]
    assert [m["path"] for m in out["missing"]] == ["/catalogue/search"]
    assert sorted(out["updating"]) == ["/", "/account/holds", "/catalogue"]


def test_the_pages_left_out_carry_what_would_be_lost_by_excluding_them(world):
    """'Did you mean to remove it?' is a question worth asking only with the facts attached."""
    _paste(world, json.dumps([{"path": "/checkout", "title": "Checkout"}]))
    _open_finding(world, "/checkout")

    out = _preview(world, '["/"]')
    left = next(m for m in out["missing"] if m["path"] == "/checkout")
    assert left["label"] == "Checkout"
    assert left["open_findings"] == 1


def test_a_page_already_out_of_scope_is_not_offered_for_removal_again(world):
    _paste(world, json.dumps([{"path": "/admin/debug", "enabled": False}, {"path": "/"}]))
    out = _preview(world, '["/"]')
    assert out["missing"] == []


def test_the_preview_refuses_exactly_what_the_write_refuses(world):
    """One reader for both, so a confirmation screen can never describe something the write
    would then reject."""
    from apps.a11y.routes import RouteError

    with pytest.raises(RouteError):
        _preview(world, json.dumps([{"url": "/catalogue"}]))


# ── what changed, and when (decision 3) ─────────────────────────────────────
#
# An audit finds 47 problems across 68 pages. Twelve are quietly taken out of scope and it is
# re-run: 9 problems across 56, and the report's Movement section reads as an improvement.
# Every part of that is doing its job. The gap is between them.


def test_changing_the_page_list_is_written_to_the_ledger(world):
    from apps.ledger.models import Event

    _paste(world, '["/", "/catalogue"]', actor="user-7")
    entry = Event.objects.get(tenant_id=world["t"], action="a11y.routes.registered")
    assert entry.actor == "user-7"
    assert entry.payload["added"] == ["/", "/catalogue"]
    assert entry.payload["source"] == "manual"


def test_taking_a_page_out_of_scope_is_recorded_with_the_page_named(world):
    from apps.ledger.models import Event

    _paste(world, '["/", "/catalogue"]')
    _paste(world, '["/"]', replace=True)

    latest = Event.objects.filter(tenant_id=world["t"],
                                  action="a11y.routes.registered").order_by("ts").last()
    assert latest.payload["disabled"] == ["/catalogue"]


def test_pasting_the_same_list_again_is_still_recorded(world):
    """'Somebody pasted the same list again' is a different fact from 'nobody touched it', and
    only one of them explains a report that did not change."""
    from apps.ledger.models import Event

    _paste(world, '["/"]')
    _paste(world, '["/"]')
    assert Event.objects.filter(tenant_id=world["t"],
                                action="a11y.routes.registered").count() == 2


def test_nothing_to_compare_against_says_nothing(world):
    from apps.a11y.routes import scope_change_since

    _paste(world, '["/", "/catalogue"]')
    assert scope_change_since(world["t"], world["p"]) == {}


def test_a_page_list_that_has_not_moved_says_nothing(world):
    from apps.a11y.routes import scope_change_since

    _paste(world, '["/", "/login"]')
    audit = _audit(world, "/", "/login")
    audit.status = A11yBaselineAudit.Status.COMPLETE
    audit.save(update_fields=["status"])
    assert scope_change_since(world["t"], world["p"]) == {}


def test_a_shrunken_scope_is_reported_against_the_audit_it_shrank_from(world):
    """The one that matters: the numbers are about to improve for a reason that has nothing to
    do with accessibility, and this is what says so."""
    from apps.a11y.routes import scope_change_since

    _paste(world, json.dumps(["/", "/login", "/basket"]))
    audit = _audit(world, "/", "/login", "/basket")
    audit.status = A11yBaselineAudit.Status.COMPLETE
    audit.save(update_fields=["status"])

    _paste(world, json.dumps(["/", "/checkout"]), replace=True)
    moved = scope_change_since(world["t"], world["p"])
    assert moved["added"] == ["/checkout"]
    assert moved["removed"] == ["/basket", "/login"]
    assert moved["before"] == 3 and moved["now"] == 2
    assert moved["audit_id"] == str(audit.id)


# ══ editing one page (task 8b) ═══════════════════════════════════════════════
#
# Registering works by path, because a pasted list carries no identities. That is the whole
# reason a corrected path adds a page and leaves the old one in scope, and the whole reason 8a
# needed a confirm step. Editing a NAMED ROW removes the ambiguity instead of warning about it.


def _row(world, path="/catalogue", **over):
    _paste(world, json.dumps([{"path": path, **over}]))
    return A11yRoute.objects.get(tenant_id=world["t"], path=path)


def _edit(world, row, **fields):
    from apps.a11y.routes import update_route

    return update_route(tenant_id=world["t"], project_id=world["p"], route_id=str(row.id),
                        fields=fields, actor="user-7")


def test_editing_a_row_changes_that_page_and_creates_nothing(world):
    """The point of the whole task. Re-pasting a corrected path leaves a ghost; editing the row
    the platform already knows cannot."""
    row = _row(world, "/catalogue/search", title="Search")
    _edit(world, row, path="/catalogue/results")

    paths = sorted(r.path for r in A11yRoute.objects.filter(tenant_id=world["t"]))
    assert paths == ["/catalogue/results"], "one page, renamed — not two"


def test_a_rename_is_checked_like_any_other_path(world):
    from apps.a11y.routes import RouteError

    row = _row(world)
    with pytest.raises(RouteError) as exc:
        _edit(world, row, path="catalogue")
    assert 'must start with a slash' in str(exc.value)
    row.refresh_from_db()
    assert row.path == "/catalogue", "a refused edit changes nothing"


def test_renaming_onto_a_page_that_already_exists_is_refused_not_merged(world):
    """Merging two rows would silently discard whichever page's name and scope lost, and the
    audit would then visit a page under a description nobody wrote for it."""
    from apps.a11y.routes import RouteError

    _paste(world, json.dumps([{"path": "/a", "title": "First"},
                              {"path": "/b", "title": "Second"}]))
    row = A11yRoute.objects.get(tenant_id=world["t"], path="/b")

    with pytest.raises(RouteError) as exc:
        _edit(world, row, path="/a")
    assert "already registered" in str(exc.value) and "First" in str(exc.value)
    assert A11yRoute.objects.filter(tenant_id=world["t"]).count() == 2


def test_a_field_that_is_not_a_page_property_is_refused_by_name(world):
    from apps.a11y.routes import RouteError

    row = _row(world)
    with pytest.raises(RouteError) as exc:
        _edit(world, row, source="onboarding")
    # Who put a page here is a fact about how it arrived, not something a person edits.
    assert "source can't be changed" in str(exc.value)


def test_an_edit_that_changes_nothing_says_so_rather_than_writing(world):
    row = _row(world, "/catalogue", title="Browse")
    assert _edit(world, row, label="Browse", enabled=True) == {}


def test_every_edit_is_recorded_with_what_it_was_before(world):
    """A page's scope decides what every later number is a number ABOUT, so the change has to be
    reconstructable and not merely visible."""
    from apps.ledger.models import Event

    row = _row(world, "/catalogue")
    _edit(world, row, path="/browse", enabled=False)

    entry = Event.objects.filter(tenant_id=world["t"],
                                 action="a11y.routes.registered").order_by("ts").last()
    assert entry.actor == "user-7"
    assert entry.payload["fields"]["path"] == {"from": "/catalogue", "to": "/browse"}
    assert entry.payload["fields"]["enabled"] == {"from": True, "to": False}


def test_what_a_rename_would_leave_behind_is_readable_before_it_happens(world):
    """A finding is keyed on the route it was found at, so a rename cannot take the page's
    problems with it. The screen has to be able to say that while the path field is being typed,
    which means the count travels on the row."""
    from apps.a11y.routes import history_for

    _row(world, "/checkout")
    _open_finding(world, "/checkout")

    assert history_for(world["t"], world["p"])["/checkout"]["open_findings"] == 1


def test_a_rename_does_not_move_the_pages_recorded_problems(world):
    """Team decision: warn and proceed. Rewriting a finding's key would edit records the ledger
    treats as permanent, so the honest outcome is that history stays where it was found."""
    _row(world, "/checkout")
    _open_finding(world, "/checkout")
    row = A11yRoute.objects.get(tenant_id=world["t"], path="/checkout")
    _edit(world, row, path="/pay")

    assert A11yFinding.objects.filter(tenant_id=world["t"], route="/checkout").count() == 1
    assert A11yFinding.objects.filter(tenant_id=world["t"], route="/pay").count() == 0


# ── removing a page ─────────────────────────────────────────────────────────


def _remove(world, row):
    from apps.a11y.routes import delete_route

    return delete_route(tenant_id=world["t"], project_id=world["p"], route_id=str(row.id),
                        actor="user-7")


def test_a_page_typed_by_mistake_can_simply_go(world):
    """The disabled-never-deleted rule protects pages that were REAL. A path that was never
    opened and has nothing recorded against it was never a page, and keeping the row forever is
    noise on a screen people have to read."""
    row = _row(world, "/catalouge")     # a typo, never audited
    out = _remove(world, row)

    assert out["removed"] is True
    assert not A11yRoute.objects.filter(tenant_id=world["t"], path="/catalouge").exists()


def test_a_page_that_has_been_audited_is_excluded_and_kept(world):
    """A page that stopped existing is a fact about the application worth keeping, and its past
    findings would otherwise point at a page nothing explains."""
    _row(world, "/checkout")
    _open_finding(world, "/checkout")
    row = A11yRoute.objects.get(tenant_id=world["t"], path="/checkout")

    out = _remove(world, row)
    assert out["removed"] is False and out["excluded"] is True
    assert "kept and taken out of scope" in out["reason"]
    row.refresh_from_db()
    assert row.enabled is False


def test_a_page_that_was_visited_and_found_clean_is_also_kept(world):
    """Being clean is a result, not an absence — the row is what says the page was looked at."""
    _row(world, "/login")
    audit = _audit(world, "/login")
    _post(world, audit, _screen("/login"))
    row = A11yRoute.objects.get(tenant_id=world["t"], path="/login")

    assert _remove(world, row)["removed"] is False


def test_removing_a_page_is_recorded(world):
    from apps.ledger.models import Event

    _remove(world, _row(world, "/typo"))
    entry = Event.objects.filter(tenant_id=world["t"],
                                 action="a11y.routes.registered").order_by("ts").last()
    assert entry.payload["deleted"] == "/typo"


# ── The audit no longer needs a clone of the application (#9) ───────────────
#
# The folder exists so the browser and the scanner can be resolved out of the audited project's
# own `node_modules` — worth having, because the version stamped on every scan is then the
# version that application actually ships. But it was a REFUSAL, and that made a whole class of
# application unauditable: a Django, Rails or .NET app has no `node_modules`, so the only way to
# audit one was to add npm dev-dependencies to the client's own repository in order to look at
# it. The clone is now preferred, not required.


class _FakeDaemon:
    """Just enough of the daemon to exercise `_run_a11y_audit`'s folder decision."""

    _base = "http://localhost:8000"
    _tenant = "t1"
    _token = "tok"

    def __init__(self, tmp_path, *, has_clone: bool):
        self._worktrees_root = str(tmp_path / "worktrees")
        self._has_clone = has_clone
        self._clone = str(tmp_path / "clone")
        self.ran_from = None

    def _resolve_repo_path(self, repo):
        from runner.companion.daemon import DaemonError

        if not self._has_clone:
            raise DaemonError(f"no local clone of {repo}")
        return self._clone

    # The real one, borrowed unbound — this stub stands in for the daemon's plumbing, never for
    # the behaviour under test.
    def _a11y_scratch(self, project_id):
        from runner.companion.daemon import CompanionDaemon

        return CompanionDaemon._a11y_scratch(self, project_id)


def _audit_with(monkeypatch, daemon, claimed):
    from runner.companion import daemon as daemon_mod

    monkeypatch.setattr(daemon_mod, "RemoteStateClient", lambda **kw: object(), raising=False)

    calls = {}

    def _run(*, client, project_id, workdir, audit_id):
        calls["workdir"] = workdir
        return {"posted": 3}

    import runner.companion.a11yaudit as a11yaudit_mod

    monkeypatch.setattr(a11yaudit_mod, "run_baseline_audit", _run)
    daemon_mod.CompanionDaemon._run_a11y_audit(daemon, claimed)
    return calls


def test_an_audit_runs_from_the_projects_own_clone_when_there_is_one(tmp_path, monkeypatch):
    daemon = _FakeDaemon(tmp_path, has_clone=True)
    calls = _audit_with(monkeypatch, daemon, {
        "audit_id": "a1", "project_id": "p1", "repo": "acme/web", "repo_reason": ""})
    assert calls["workdir"] == daemon._clone, "the application's own axe version still wins"


def test_no_clone_falls_back_to_the_companions_own_folder_instead_of_refusing(tmp_path,
                                                                             monkeypatch):
    daemon = _FakeDaemon(tmp_path, has_clone=False)
    calls = _audit_with(monkeypatch, daemon, {
        "audit_id": "a1", "project_id": "p1", "repo": "acme/web", "repo_reason": ""})
    assert "a11y-audit" in calls["workdir"] and "p1" in calls["workdir"]
    assert Path(calls["workdir"]).is_dir()


def test_a_project_with_no_repository_at_all_can_still_be_audited(tmp_path, monkeypatch):
    """The case that mattered: point the platform at a running application and ask where it
    stands, without registering a repository for it first."""
    daemon = _FakeDaemon(tmp_path, has_clone=False)
    calls = _audit_with(monkeypatch, daemon, {
        "audit_id": "a1", "project_id": "p2", "repo": "",
        "repo_reason": "this project has no repository registered"})
    assert "p2" in calls["workdir"]


def test_two_projects_do_not_share_one_scratch_folder(tmp_path, monkeypatch):
    """Two audits of two applications must not fight over one candidates file."""
    daemon = _FakeDaemon(tmp_path, has_clone=False)
    one = _audit_with(monkeypatch, daemon, {"audit_id": "a", "project_id": "p1", "repo": "",
                                            "repo_reason": "none"})
    two = _audit_with(monkeypatch, daemon, {"audit_id": "b", "project_id": "p2", "repo": "",
                                            "repo_reason": "none"})
    assert one["workdir"] != two["workdir"]


def test_the_capture_says_when_it_used_our_scanner_and_not_the_applications():
    """`(companion)` rides on the version string that already travels everywhere a version is
    shown — per screen, in the report, and onto the signed conformance statement. Without it the
    platform would name a version the client's application does not actually ship."""
    script = _script()
    assert 'axe.from === "companion" ? " (companion)" : ""' in script
    assert 'lastResolvedFrom = "project"' in script and 'lastResolvedFrom = "companion"' in script


def test_the_companion_pins_its_own_browser_and_scanner():
    """The fallback import has been in the audit script from the first version and nothing was
    ever installed for it to find. This is what turns it from dead code into the answer for a
    non-Node stack."""
    manifest = json.loads(
        (Path(__file__).resolve().parents[2] / "runner" / "package.json").read_text("utf-8"))
    deps = manifest["dependencies"]
    assert set(deps) == {"axe-core", "playwright"}
    for name, version in deps.items():
        assert version[0].isdigit(), f"{name} is pinned exactly, not floated: {version}"


# ── The audit path has to stand on its own, and must never take the machine down ──
#
# Both of these come from the team's first live run. The moment an audit could actually be
# claimed — which needed `claimable=True` on the REST caller — the companion claimed one, and
# died on `ModuleNotFoundError: No module named 'apps'`. Neither half had ever been reachable
# before, so neither had ever been exercised.


def test_the_audit_path_puts_backend_on_the_path_itself(monkeypatch, tmp_path):
    """`run_baseline_audit` imports `apps.a11y.capture` lazily, and on this path nobody had put
    `backend/` on `sys.path`. Its three callers are the two `__main__` subcommands and the engine
    driver factory — a companion that only ever runs audits reaches none of them.
    """
    from runner.companion import daemon as daemon_mod

    called = []
    monkeypatch.setattr(daemon_mod, "ensure_backend_importable",
                        lambda: called.append(True))
    monkeypatch.setattr(daemon_mod, "RemoteStateClient", lambda **kw: object(), raising=False)

    import runner.companion.a11yaudit as a11yaudit_mod
    monkeypatch.setattr(a11yaudit_mod, "run_baseline_audit",
                        lambda **kw: {"posted": 0})

    daemon = _FakeDaemon(tmp_path, has_clone=True)
    daemon_mod.CompanionDaemon._run_a11y_audit(daemon, {
        "audit_id": "a-1", "project_id": "p-1", "repo": "acme/web", "manifest": {}})

    assert called, "the audit path never made `apps.*` importable, so it died on the import"


def test_an_audit_that_raises_closes_the_audit_and_says_so_plainly(monkeypatch, tmp_path):
    """A raising audit must close with a reason rather than being dropped.

    Left `claimed`, it is indistinguishable on screen from an audit no machine has reached yet,
    for the whole fifteen minutes its lease takes to age out. And the reason is written for the
    person reading the report: the exception goes to this machine's log, never to the screen.
    """
    from runner.companion import daemon as daemon_mod

    posted = {}

    class _Client:
        def call(self, tool, **kw):
            posted["tool"] = tool
            posted.update(kw)
            return {}

    # Patched where it LIVES, not on the daemon module: `_close_failed_a11y_audit` imports it
    # inside the function, so a name bound on `daemon_mod` is never the one looked up.
    import runner.companion.state_client as state_client_mod
    monkeypatch.setattr(state_client_mod, "RemoteStateClient", lambda **kw: _Client())

    daemon = _FakeDaemon(tmp_path, has_clone=True)
    daemon_mod.CompanionDaemon._close_failed_a11y_audit(
        daemon, {"audit_id": "a-9"}, ModuleNotFoundError("No module named 'apps'"))

    assert posted["tool"] == "finish_a11y_audit"
    assert posted["audit_id"] == "a-9"
    reason = posted["reason"]
    assert "stopped before it could visit any pages" in reason
    assert "Start a new audit" in reason
    # The two things a reader must never be shown, and the one they must be told.
    assert "ModuleNotFound" not in reason and "apps" not in reason
    assert "tells you anything about your application" in reason


def test_a_failure_the_platform_cannot_be_told_about_does_not_raise(monkeypatch, tmp_path):
    """Best-effort: the 15-minute lease is the backstop, and this must not be what kills the
    companion after the thing it exists to survive already went wrong."""
    from runner.companion import daemon as daemon_mod

    class _DeadClient:
        def call(self, tool, **kw):
            raise OSError("the platform is unreachable")

    import runner.companion.state_client as state_client_mod
    monkeypatch.setattr(state_client_mod, "RemoteStateClient", lambda **kw: _DeadClient())

    daemon = _FakeDaemon(tmp_path, has_clone=True)
    daemon_mod.CompanionDaemon._close_failed_a11y_audit(
        daemon, {"audit_id": "a-9"}, RuntimeError("original"))   # must not raise


# ══ live progress — what the screen can say WHILE an audit is running ═════════════════
#
# `summary` is written once, when the audit closes. So for the whole time one is running there
# was no count of anything anywhere and the only thing a screen could show was the status word:
# an audit that had visited six of ten pages and one that had visited none looked identical, and
# an audit whose judge had stopped looked exactly like one still working. These are the numbers
# the S-38 running panel is made of, and every one of them is DERIVED from rows that were being
# written the whole time — nothing new is recorded to be able to say this.

def test_progress_counts_the_pages_that_have_actually_come_back(world):
    from apps.a11y.baseline import audit_progress

    audit = _audit(world, "/", "/login", "/catalogue")
    _post(world, audit, _screen("/"))
    _post(world, audit, _screen("/login"))

    progress = audit_progress(world["t"], [str(audit.id)])[str(audit.id)]
    assert progress["visited"] == 2, "of three asked for — the third has not been visited yet"
    assert progress["unreachable"] == 0


def test_a_page_that_would_not_open_is_counted_as_known_not_as_missing(world):
    """A page the browser could not open is a RESULT. Counting it as progress-not-yet-made would
    leave the panel stuck one short for ever on an audit that had in fact finished looking."""
    from apps.a11y.baseline import audit_progress

    audit = _audit(world, "/", "/admin")
    _post(world, audit, _screen("/"))
    _post(world, audit, _screen("/admin", load_error="the page returned HTTP 403", elements=[]))

    progress = audit_progress(world["t"], [str(audit.id)])[str(audit.id)]
    assert progress["visited"] == 2
    assert progress["unreachable"] == 1


def test_an_audit_nothing_has_reported_on_yet_says_zero_rather_than_nothing(world):
    """Zero is an answer; a missing key is not. The panel has to be able to render the moment a
    machine claims an audit, which is before any page has been posted."""
    from apps.a11y.baseline import audit_progress

    audit = _audit(world, "/")
    assert audit_progress(world["t"], [str(audit.id)])[str(audit.id)] == {
        "visited": 0, "unreachable": 0}


def test_the_judging_half_is_counted_against_what_was_actually_dispatched(world):
    """The number the team could not see yesterday: 81 of 144. The denominator comes off the
    audit's own summary, written when the pass was dispatched, so it is the real one."""
    from apps.a11y.baseline import audit_progress
    from apps.a11y.models import A11yBaselineAudit, A11yJudgmentCache
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    audit = _audit(world, "/")
    seed_agent_specs(world["tenant"])
    judge_run = Run.objects.create(
        tenant=world["tenant"],
        work_item=WorkItem.objects.create(
            tenant=world["tenant"], project=world["project"], title="Accessibility judging"),
        agent_spec=AgentSpec.objects.get(tenant=world["tenant"], key="09c_a11y_judge"),
    )
    audit.status = A11yBaselineAudit.Status.JUDGING
    audit.summary = {"ai_pass": {"judge_run_id": str(judge_run.id), "dispatched": 144}}
    audit.save(update_fields=["status", "summary"])
    for n in range(3):
        A11yJudgmentCache.objects.create(
            tenant=world["tenant"], project=world["project"], checker="alt",
            content_hash=f"{n:064d}", verdict="pass", run=judge_run)

    progress = audit_progress(world["t"], [str(audit.id)])[str(audit.id)]
    assert progress["judged"] == 3
    assert progress["dispatched"] == 144


def test_an_audit_that_has_not_reached_judging_carries_no_judging_keys(world):
    """"None judged yet" and "not that stage" are different facts, and the panel shows a
    different tile for each — so the absence has to be real rather than a zero."""
    from apps.a11y.baseline import audit_progress

    audit = _audit(world, "/")
    assert "judged" not in audit_progress(world["t"], [str(audit.id)])[str(audit.id)]


def test_progress_for_two_audits_at_once_does_not_mix_them_up(world):
    """One grouped query for the whole set — which is the shape most likely to attribute one
    audit's screens to another. Two audits of one project can genuinely overlap."""
    from apps.a11y.baseline import audit_progress

    first = _audit(world, "/", "/login")
    second = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                  base_url="http://localhost:4180")
    _post(world, first, _screen("/"))
    _post(world, second, _screen("/"))
    _post(world, second, _screen("/login"))

    progress = audit_progress(world["t"], [str(first.id), str(second.id)])
    assert progress[str(first.id)]["visited"] == 1
    assert progress[str(second.id)]["visited"] == 2


def test_asking_about_nothing_is_not_a_query(world):
    """The API asks only about the audits still in flight, which is normally none at all."""
    from apps.a11y.baseline import audit_progress

    assert audit_progress(world["t"], []) == {}


def test_the_pass_arithmetic_is_the_platforms_own(world):
    """68 pages is two passes, not one truncated at 60 (D-B5). Shared so the strip, the running
    panel and the capture cannot disagree about how many passes a list takes."""
    from apps.a11y.baseline import passes_for

    assert passes_for(0) == 1, "an empty list still describes one pass, never zero"
    assert passes_for(60) == 1
    assert passes_for(61) == 2
    assert passes_for(68) == 2
    assert passes_for(200) == 4


def _judge_run(world, batches=None):
    """A judging run carrying the batches a dispatch would have attached."""
    from apps.registry.catalog import seed_agent_specs
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    seed_agent_specs(world['tenant'])
    return Run.objects.create(
        tenant=world['tenant'],
        work_item=WorkItem.objects.create(
            tenant=world['tenant'], project=world['project'], title='Accessibility judging'),
        agent_spec=AgentSpec.objects.get(tenant=world['tenant'], key='09c_a11y_judge'),
        inputs={'a11y_batches': batches} if batches is not None else {},
    )


def test_a_complete_pass_never_reads_as_two_thirds_done(world):
    """The defect the first complete live run exposed, and the reason it mattered.

    144 requests over ten pages were 81 distinct elements: the site header, the footer, the nav
    are the same markup on every page, they hash identically, and one verdict answers all ten.
    The judge recorded 81 and was complete. The tile counted verdicts against REQUESTS and read
    `81 of 144` — a screen telling the person who ran it that a third of the checking had not
    happened, on a run where all of it had. That is this capability's own worst failure, told
    about itself.
    """
    from apps.a11y.baseline import audit_progress
    from apps.a11y.models import A11yBaselineAudit, A11yJudgmentCache

    audit = _audit(world, "/")
    judge_run = _judge_run(world)
    audit.status = A11yBaselineAudit.Status.JUDGING
    audit.summary = {"ai_pass": {"judge_run_id": str(judge_run.id),
                                 # what the dispatch handed over…
                                 "dispatched": 144,
                                 # …and what it is actually about
                                 "distinct": 81}}
    audit.save(update_fields=["status", "summary"])
    for n in range(81):
        A11yJudgmentCache.objects.create(
            tenant=world["tenant"], project=world["project"], checker="alt",
            content_hash=f"{n:064d}", verdict="pass", run=judge_run)

    progress = audit_progress(world["t"], [str(audit.id)])[str(audit.id)]
    assert progress["judged"] == 81
    assert progress["dispatched"] == 81, (
        "the denominator counts the same unit as the numerator, or it is not a fraction")


def test_a_pass_dispatched_before_this_was_recorded_still_shows_a_true_number(world):
    """An audit that ran before the distinct count was stored must not go on showing the old
    misleading one. Derived from the run's own batches, where the elements still are."""
    from apps.a11y.baseline import audit_progress
    from apps.a11y.models import A11yBaselineAudit

    audit = _audit(world, "/")
    # Three screens, all carrying the SAME element — a site header, the everyday case.
    shared = {"id": "1-aaaa", "content_hash": "a" * 64, "checker": "semantics",
              "criteria": ["1.3.1"], "html": "<span>Meridian Library</span>",
              "selector": "header span", "context": ""}
    judge_run = _judge_run(world, batches=[
        {"route": f"/p{i}", "elements": [dict(shared), {**shared, "id": f"{i}-bbbb",
                                                        "content_hash": f"{i}" * 64}]}
        for i in range(3)
    ])
    audit.status = A11yBaselineAudit.Status.JUDGING
    # No `distinct` key at all — the pre-fix shape.
    audit.summary = {"ai_pass": {"judge_run_id": str(judge_run.id), "dispatched": 6}}
    audit.save(update_fields=["status", "summary"])

    progress = audit_progress(world["t"], [str(audit.id)])[str(audit.id)]
    assert progress["dispatched"] == 4, "one shared element plus three of its own, not six slots"


def test_what_the_panel_says_after_the_run_counts_problems_and_questions_apart(world):
    """The panel does not disappear when the run ends — it says what happened. A problem the
    platform is sure about and a question it is asking a person are counted separately, because
    folding the second into the first inflates the problem count with undecided things."""
    from apps.a11y.baseline import audit_outcome
    from apps.a11y.models import A11yFinding

    made = [("failure", "critical"), ("failure", "high"), ("failure", "high"),
            ("needs_review", "high")]
    for n, (outcome, severity) in enumerate(made):
        A11yFinding.objects.create(
            tenant=world["tenant"], project=world["project"], fingerprint=f"{n:064d}",
            route="/", selector=f"#e{n}", criterion="1.1.1", source="ai",
            outcome=outcome, severity=severity, status=A11yFinding.Status.OPEN)

    assert audit_outcome(world["t"], world["p"]) == {
        "problems": 3, "critical": 1, "high": 2, "waiting": 1}


def test_the_panels_numbers_do_not_hang_off_a_column_a_baseline_audit_never_fills(world):
    """The bug this replaced, kept as a test because it would have shipped a confident zero.

    `A11yFinding.last_seen_run` is a foreign key to a real `Run`, and a baseline audit
    deliberately manufactures none (QA-17) — so for every brownfield audit that column is NULL.
    Counting on it reported **0 problems on an audit that found three**, which is the exact kind
    of reassuring, wrong number this capability exists to refuse.
    """
    from apps.a11y.baseline import audit_outcome
    from apps.a11y.models import A11yFinding

    finding = A11yFinding.objects.create(
        tenant=world["tenant"], project=world["project"], fingerprint="f" * 64,
        route="/", selector="#a", criterion="1.1.1", source="ai", outcome="failure",
        severity="critical", status=A11yFinding.Status.OPEN)
    assert finding.last_seen_run_id is None, "the column a per-audit count would have used"
    assert audit_outcome(world["t"], world["p"])["problems"] == 1


def test_a_project_with_nothing_found_reports_zeros_rather_than_nothing(world):
    """Zero is an answer and the panel renders it; a missing key is not."""
    from apps.a11y.baseline import audit_outcome

    assert audit_outcome(world["t"], world["p"]) == {
        "problems": 0, "critical": 0, "high": 0, "waiting": 0}


def test_a_resolved_problem_stops_being_counted(world):
    """The tile says where the application stands NOW, so a problem that has gone is gone."""
    from apps.a11y.baseline import audit_outcome
    from apps.a11y.models import A11yFinding

    A11yFinding.objects.create(
        tenant=world["tenant"], project=world["project"], fingerprint="a" * 64,
        route="/", selector="#a", criterion="1.1.1", source="ai", outcome="failure",
        severity="critical", status=A11yFinding.Status.RESOLVED)
    assert audit_outcome(world["t"], world["p"])["problems"] == 0


def test_another_projects_findings_are_never_counted_here(world):
    """Scoped to the project, and that is the widest it ever goes."""
    from apps.a11y.baseline import audit_outcome
    from apps.a11y.models import A11yFinding
    from apps.projects.models import Project

    other = Project.objects.create(tenant=world["tenant"], name="Somewhere else")
    A11yFinding.objects.create(
        tenant=world["tenant"], project=other, fingerprint="b" * 64,
        route="/", selector="#a", criterion="1.1.1", source="ai", outcome="failure",
        severity="critical", status=A11yFinding.Status.OPEN)
    assert audit_outcome(world["t"], world["p"])["problems"] == 0


# ══ an audit whose machine went away ═════════════════════════════════════════════════
#
# The capture half of an audit runs on a machine this server cannot see, so the platform learns
# it is still there only from the fact that it is still talking. The claim lease already
# recovered a dead companion's work — but it only ever looked at `pending` and stale `claimed`
# audits, and an audit moves to `capturing` the instant its first screen lands. Past that line
# there was no lease, no timeout and no way to cancel: a laptop that restarted mid-audit left the
# row saying "Visiting pages" for ever, which is this capability's own worst failure — a
# confident report of work that is not happening. Found on the live run of 21 August.

def test_an_audit_whose_machine_stopped_reporting_is_closed_with_the_reason(world):
    from apps.a11y.baseline import ABANDONED_REASON, abandon_audit

    audit = _audit(world, "/", "/login", "/catalogue")
    _post(world, audit, _screen("/"))

    out = abandon_audit(tenant_id=world["t"], audit_id=str(audit.id))

    assert out["closed"] is True
    assert out["status"] == "failed"
    assert out["reason"] == ABANDONED_REASON
    assert out["abandoned"] is True
    audit.refresh_from_db()
    assert audit.status == "failed"
    assert audit.summary["reason"] == ABANDONED_REASON


def test_what_the_abandoned_audit_did_capture_is_stated_not_thrown_away(world):
    """One page reported, two never asked about. Both facts are on the record — the difference
    is the whole of what somebody re-running needs to know."""
    from apps.a11y.baseline import abandon_audit

    audit = _audit(world, "/", "/login", "/catalogue")
    _post(world, audit, _screen("/"))

    out = abandon_audit(tenant_id=world["t"], audit_id=str(audit.id))

    assert out["asked"] == 3
    assert out["opened"] == 1
    assert out["never_reported"] == ["/catalogue", "/login"]
    assert A11yScreenScan.objects.filter(run_key=str(audit.id)).count() == 1, (
        "what it captured is kept — the audit is failed, not erased"
    )


def test_an_abandoned_audit_is_never_judged_and_publishes_nothing(world, monkeypatch):
    """A report from one of three pages would be a document stating a position about an
    application most of which was never looked at. Failed is the honest end."""
    from apps.a11y import baseline as baseline_mod
    from apps.a11y.baseline import abandon_audit

    audit = _audit(world, "/", "/login", "/catalogue")
    _post(world, audit, _screen("/"))

    def _boom(**kwargs):  # pragma: no cover - the point is that it is never called
        raise AssertionError("a partial capture must never reach the judge")

    monkeypatch.setattr(baseline_mod, "publish_baseline_for", _boom)
    monkeypatch.setattr(baseline_mod, "start_ai_pass", _boom, raising=False)
    abandon_audit(tenant_id=world["t"], audit_id=str(audit.id))


def test_closing_an_audit_that_is_not_being_captured_does_nothing(world):
    """`judging` is a Temporal run and is closed from the other end; a finished audit is
    finished. Only the states a companion actually holds are this function's business."""
    from apps.a11y.baseline import abandon_audit

    audit = _audit(world, "/")
    A11yBaselineAudit.objects.filter(id=audit.id).update(status="judging")

    out = abandon_audit(tenant_id=world["t"], audit_id=str(audit.id))
    assert out["closed"] is False
    audit.refresh_from_db()
    assert audit.status == "judging", "left exactly as it was"


def test_a_machine_that_is_still_posting_screens_is_not_declared_dead(world):
    """Liveness is measured from the WORK as well as the heartbeat. An audit whose claim was
    stamped an hour ago but whose last screen landed a moment ago is plainly alive, and killing
    it would be the S.No 111 mid-flight re-claim all over again."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audit_ids

    audit = _audit(world, "/", "/login")
    _post(world, audit, _screen("/"))
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        claimed_at=timezone.now() - timedelta(hours=1), status="capturing")
    audit.refresh_from_db()

    stale_before = timezone.now() - timedelta(minutes=15)
    assert stalled_audit_ids(world["t"], [audit], stale_before=stale_before) == set()


def test_an_audit_that_has_said_nothing_at_all_for_the_lease_is_stalled(world):
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audit_ids

    audit = _audit(world, "/", "/login")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        claimed_at=timezone.now() - timedelta(hours=1), status="capturing")
    audit.refresh_from_db()

    stale_before = timezone.now() - timedelta(minutes=15)
    assert stalled_audit_ids(world["t"], [audit], stale_before=stale_before) == {str(audit.id)}


def test_reading_which_audits_are_stalled_never_writes_to_them(world):
    """The screen asks this on every poll. A read that closed an audit would mean looking at a
    list changed it — and the answer has to stay available to a person who simply reloads."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audit_ids

    audit = _audit(world, "/")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        claimed_at=timezone.now() - timedelta(hours=1), status="capturing")
    audit.refresh_from_db()

    stalled_audit_ids(world["t"], [audit], stale_before=timezone.now() - timedelta(minutes=15))

    audit.refresh_from_db()
    assert audit.status == "capturing", "derived, never written"
    assert audit.summary == {}


def test_a_pending_audit_nobody_has_claimed_is_not_stalled(world):
    """Nothing has gone wrong with an audit that is simply waiting for a machine to pick it up,
    however long it waits — and the claim lease already offers that one back."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audit_ids

    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"],
                                 base_url="http://localhost:5173",
                                 routes=["/"], claimable=True)
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        created_at=timezone.now() - timedelta(hours=2))
    audit.refresh_from_db()
    assert audit.status == "pending"
    assert stalled_audit_ids(
        world["t"], [audit], stale_before=timezone.now() - timedelta(minutes=15)) == set()


# ── a JUDGING pass whose machine went away (9.26.E1) ────────────────────────
#
# The capture half of this has been covered since 21 August. The judging half was left out on the
# reasoning that a judging pass is "closed from the other end" — true only when the RUN fails.
# When the MACHINE dies the run does not fail: the workflow waits two hours for a report that is
# never coming. On 31 August that left an audit reading "Checking the rest… in progress" for 25
# minutes beside a header badge that said `Companion: Offline`.


def _judging_audit(world, *, claimed_ago, verdict_ago=None, run_status="running"):
    """An audit in `judging`, its judge run claimed `claimed_ago` ago, optionally with its newest
    verdict written `verdict_ago` ago."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.models import A11yJudgmentCache
    from apps.registry.models import AgentSpec
    from apps.runs.models import Run
    from apps.workitems.models import WorkItem

    now = timezone.now()
    spec = AgentSpec.objects.create(
        tenant=world["tenant"], key="09c_a11y_judge", semver="1.0.0",
        prompt_version="a11y-judge-1", body_ref="agents/09c_a11y_judge/agent.md",
        recommended_engine="claude", recommended_model="claude-opus-5",
        phase_label="a11y_judge")
    item = WorkItem.objects.create(tenant=world["tenant"], project=world["project"],
                                   title="judging", type="chore")
    run = Run.objects.create(
        tenant=world["tenant"], work_item=item, agent_spec=spec, status=run_status,
        inputs={"dispatch": {"kind": "plan", "status": "claimed",
                             "claimed_at": (now - claimed_ago).isoformat()}})
    Run.objects.filter(id=run.id).update(started_at=now - claimed_ago - timedelta(minutes=1))

    audit = _audit(world, "/")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        status="judging", summary={"ai_pass": {"judge_run_id": str(run.id)}})
    audit.refresh_from_db()

    if verdict_ago is not None:
        row = A11yJudgmentCache.objects.create(
            tenant=world["tenant"], project=world["project"], checker="alt",
            content_hash="a" * 64, criteria=["1.1.1"], verdict="pass", confidence=0.9,
            run=run, engine="claude")
        # `updated_at` is auto_now, so it can only be set past the ORM.
        A11yJudgmentCache.objects.filter(id=row.id).update(updated_at=now - verdict_ago)
    return audit, run


def test_a_judging_audit_whose_machine_went_quiet_is_stalled_and_says_when(world):
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audits

    quiet_for = timedelta(hours=1)
    audit, _ = _judging_audit(world, claimed_ago=quiet_for, verdict_ago=quiet_for)

    out = stalled_audits(world["t"], [audit],
                         stale_before=timezone.now() - timedelta(minutes=15))
    assert set(out) == {str(audit.id)}, "a judging pass gets the same honesty as a capture"
    # …and WHEN, because a count with no time beside it reads the same after one second and
    # after twenty-five minutes. That is the half of E1 that made the screen dangerous.
    assert (timezone.now() - out[str(audit.id)]) >= quiet_for


def test_a_judge_still_writing_verdicts_is_not_stalled_however_old_its_claim_is(world):
    """**The false alarm this must not raise.** `_renew_claims_for` deliberately STOPS renewing a
    claim once it has been held for MAX_CLAIM_AGE, so a long healthy judging pass has a frozen
    claim by design — on 31 August the first pass's claim froze at 10:38 and the judge went on
    answering until 11:55. Keyed on the claim alone this would have called a working audit dead
    for well over an hour, which is the same false alarm that nearly had a healthy audit killed."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audits

    audit, _ = _judging_audit(world, claimed_ago=timedelta(hours=2),
                              verdict_ago=timedelta(seconds=5))

    assert stalled_audits(world["t"], [audit],
                          stale_before=timezone.now() - timedelta(minutes=15)) == {}


def test_a_judging_audit_whose_run_already_failed_is_not_reported_as_gone_quiet(world):
    """It is being closed through the ordinary path — `close_unfinished_ai_pass` files what was
    never answered and publishes. Calling that "the machine went away" would put a second, wrong
    explanation on a screen that is about to show the right one."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import stalled_audits

    audit, _ = _judging_audit(world, claimed_ago=timedelta(hours=1),
                              verdict_ago=timedelta(hours=1), run_status="failed")

    assert stalled_audits(world["t"], [audit],
                          stale_before=timezone.now() - timedelta(minutes=15)) == {}


def test_a_judging_pass_past_its_deadline_is_reported_as_needing_a_person(world):
    """**The difference between "wait" and "act", which the screen was getting wrong.**

    A quiet judging pass recovers by itself for exactly as long as the report deadline has not
    fired: the claim lease offers the stale claim back and the pass carries on. Parking sets the
    run STALLED, and the re-claim rule requires PENDING or RUNNING — so from that instant it can
    never be re-claimed, permanently. Reconnecting the machine does nothing.

    The screen was still saying "start the machine again and it carries on from where it
    stopped", which was true when it was written and false the moment the deadline fired. A
    wrong instruction is worse than none: it sends a person to restart something that will sit
    there doing nothing, and offers no other route. This is what tells the two apart.
    """
    from datetime import timedelta

    from apps.a11y.baseline import parked_judge_runs

    audit, run = _judging_audit(world, claimed_ago=timedelta(hours=3), run_status="stalled")

    assert parked_judge_runs(world["t"], [audit]) == {str(audit.id): str(run.id)}


def test_a_judging_pass_that_can_still_recover_by_itself_offers_no_button(world):
    """The other side, and the one that keeps the button honest. Offering "finish this audit" on
    a pass that a returning companion would resume is asking somebody to end work that is about
    to continue on its own."""
    from datetime import timedelta

    from apps.a11y.baseline import parked_judge_runs

    audit, _ = _judging_audit(world, claimed_ago=timedelta(hours=3), run_status="running")

    assert parked_judge_runs(world["t"], [audit]) == {}


def test_a_finished_audit_is_never_offered_a_recovery(world):
    """A capture that failed, or an audit already complete, has no judging pass to finish. Its
    route back is "check the rest", which is a different button meaning a different thing."""
    from apps.a11y.baseline import parked_judge_runs

    audit = _audit(world, "/")
    A11yBaselineAudit.objects.filter(id=audit.id).update(status="complete")
    audit.refresh_from_db()

    assert parked_judge_runs(world["t"], [audit]) == {}


def test_the_sweep_closes_the_dead_one_and_leaves_the_live_one_alone(world):
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import abandon_stale_audits

    dead = _audit(world, "/", "/login")
    live = _audit(world)
    A11yBaselineAudit.objects.filter(id=dead.id).update(
        claimed_at=timezone.now() - timedelta(hours=1), status="capturing")
    A11yBaselineAudit.objects.filter(id=live.id).update(
        claimed_at=timezone.now(), status="capturing")

    closed = abandon_stale_audits(tenant_id=world["t"], project_id=world["p"],
                                  stale_before=timezone.now() - timedelta(minutes=15))

    assert closed == [str(dead.id)]
    dead.refresh_from_db()
    live.refresh_from_db()
    assert dead.status == "failed"
    assert live.status == "capturing"


def test_the_sweep_does_not_reach_another_project(world):
    """Scoped to the project the companion is enrolled on. A machine reporting in about one
    application has said nothing whatever about another."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import abandon_stale_audits

    other = Project.objects.create(tenant=world["tenant"], name="Another App")
    register_routes(tenant_id=world["t"], project_id=str(other.id), routes=["/"])
    theirs = start_baseline_audit(tenant_id=world["t"], project_id=str(other.id),
                                  base_url="http://localhost:5173")
    A11yBaselineAudit.objects.filter(id=theirs.id).update(
        claimed_at=timezone.now() - timedelta(hours=1), status="capturing")

    closed = abandon_stale_audits(tenant_id=world["t"], project_id=world["p"],
                                  stale_before=timezone.now() - timedelta(minutes=15))

    assert closed == []
    theirs.refresh_from_db()
    assert theirs.status == "capturing"


# ── and the two places the companion actually tells us it is alive ──────────────────

def _heartbeat(runner):
    """What the companion's heartbeat does, without the HTTP layer: the view's own body."""
    from django.test import RequestFactory

    from api.runner_views import RunnerHeartbeatView, RunnerStateView

    request = RequestFactory().post("/api/runner/heartbeat/")
    original = RunnerStateView._resolve_runner
    RunnerStateView._resolve_runner = staticmethod(lambda _r: runner)
    try:
        return RunnerHeartbeatView().post(request)
    finally:
        RunnerStateView._resolve_runner = original


def test_the_heartbeat_keeps_a_live_machines_audit_from_ageing_out(world):
    """Part A, and it has to come first: until this, NOTHING renewed an audit's claim — it was
    stamped once and never touched — so a capture that legitimately took longer than the lease
    would be declared dead by the very sweep that fixes the stuck audit."""
    from datetime import timedelta

    from django.utils import timezone

    runner = _enrol(world)
    audit = _audit(world, "/", "/login")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        enrollment=runner, status="capturing",
        claimed_at=timezone.now() - timedelta(minutes=40))

    _heartbeat(runner)

    audit.refresh_from_db()
    assert audit.status == "capturing", "still being captured by a machine that is still there"
    assert audit.claimed_at > timezone.now() - timedelta(minutes=1), "lease renewed"


def test_a_live_machine_never_closes_the_audit_it_is_holding(world):
    """The heartbeat renews BEFORE it sweeps. The other order would have a companion close the
    very audit it was in the middle of capturing."""
    from datetime import timedelta

    from django.utils import timezone

    runner = _enrol(world)
    audit = _audit(world, "/", "/login")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        enrollment=runner, status="capturing",
        claimed_at=timezone.now() - timedelta(hours=1))

    response = _heartbeat(runner)

    assert response.data["audits_closed"] == 0
    audit.refresh_from_db()
    assert audit.status == "capturing"


def test_a_restarted_machine_closes_the_audit_its_predecessor_abandoned(world):
    """The live case from 21 August: the laptop restarts mid-capture, the companion comes back,
    and the audit it left behind is closed within seconds of it saying hello."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import ABANDONED_REASON

    dead_machine = _enrol(world, "dev-before-the-reboot")
    audit = _audit(world, "/", "/login")
    _post(world, audit, _screen("/"))
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        enrollment=dead_machine, status="capturing",
        claimed_at=timezone.now() - timedelta(hours=1))
    A11yScreenScan.objects.filter(run_key=str(audit.id)).update(
        created_at=timezone.now() - timedelta(hours=1))

    back = _enrol(world, "dev-after-the-reboot")
    response = _heartbeat(back)

    assert response.data["audits_closed"] == 1
    audit.refresh_from_db()
    assert audit.status == "failed"
    assert audit.summary["reason"] == ABANDONED_REASON
    assert audit.summary["opened"] == 1
    assert audit.summary["never_reported"] == ["/login"]


def test_asking_for_work_also_closes_what_a_dead_machine_left(world):
    """A companion started fresh asks for work before it has heartbeated, and an audit still
    showing as running is the first thing its owner sees on the screen."""
    from datetime import timedelta

    from django.utils import timezone

    _repo(world)
    dead_machine = _enrol(world, "dev-gone")
    stuck = _audit(world, "/", "/login")
    A11yBaselineAudit.objects.filter(id=stuck.id).update(
        enrollment=dead_machine, status="capturing",
        claimed_at=timezone.now() - timedelta(hours=1))

    _claim(world, _enrol(world, "dev-new"))

    stuck.refresh_from_db()
    assert stuck.status == "failed"


def test_the_audit_list_says_which_running_audit_has_gone_quiet(world):
    """Part C. A machine switched off for good never comes back to be swept, so the screen must
    not be the last thing still claiming the audit is running — and reading the list must not
    be what closes it."""
    from datetime import timedelta

    from django.test import RequestFactory
    from django.utils import timezone

    from api.views import ProjectViewSet

    audit = _audit(world, "/", "/login")
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        status="capturing", claimed_at=timezone.now() - timedelta(hours=1))

    view = ProjectViewSet()
    view.request = RequestFactory().get("/")
    view.request.tenant_id = world["t"]
    view.format_kwarg = None
    view.get_object = lambda: world["project"]
    response = view.a11y_audits(view.request, pk=world["p"])

    row = response.data["audits"][0]
    assert row["stalled"] is True
    audit.refresh_from_db()
    assert audit.status == "capturing", "the screen reads; it does not close"


def test_a_stale_claim_is_still_handed_on_and_never_abandoned(world):
    """The near-miss this whole change had to avoid. A `claimed` audit has captured NOTHING, and
    the claim lease already hands a stale one to the next machine that asks — so it simply runs.
    The first version of the sweep closed those too, which would have turned a recovery that
    worked into a failure a person has to go and restart. Abandonment applies to `capturing`
    alone: the one state nothing could get an audit out of."""
    from datetime import timedelta

    from django.utils import timezone

    from apps.a11y.baseline import abandon_stale_audits

    _repo(world)
    _register(world, "/")
    audit = start_baseline_audit(tenant_id=world["t"], project_id=world["p"], claimable=True)
    machine = _enrol(world, "dev-1")
    _claim(world, machine)
    A11yBaselineAudit.objects.filter(id=audit.id).update(
        claimed_at=timezone.now() - timedelta(hours=2))

    closed = abandon_stale_audits(tenant_id=world["t"], project_id=world["p"],
                                  stale_before=timezone.now() - timedelta(minutes=15))

    assert closed == [], "a claim nobody has captured under is recoverable, not abandoned"
    audit.refresh_from_db()
    assert audit.status == "claimed"
    again = _claim(world, machine)
    assert again.status_code == 200, "and it is still there to be picked back up"


# ══ the check that never ran ══════════════════════════════════════════════════════════
#
# The capture asks the browser for every element's computed accessible name. One element failing
# is normal and harmless — `_applies_label` skips it. EVERY element failing is a broken
# toolchain, and it hides completely: the elements all arrive, three checks run perfectly, and
# one of them simply never selects anything. That is what happened. `page.accessibility` was
# removed from Playwright, the capture's per-element `catch` swallowed the failure on all of
# them, and 2.5.3 never selected a single element in the whole life of the feature — found on
# the live audit of 21 August by noticing one checker's count had always been zero.

def test_a_capture_where_nothing_could_be_named_says_so(world):
    from apps.a11y.baseline import _name_coverage
    from apps.a11y.models import A11yCandidateBundle

    audit = _audit(world, "/")
    for index, tag in enumerate(("a", "button", "h1")):
        A11yCandidateBundle.objects.create(
            tenant_id=world["t"], project_id=world["p"], run_key=str(audit.id),
            route="/", position=index, selector=f"#e{index}", checkers=["semantics"],
            element={"tag": tag, "text": "Renew", "accessible_name": ""},
        )

    out = _name_coverage(world["t"], world["p"], str(audit.id))

    assert out["nameable"] == 3 and out["named"] == 0
    assert "2.5.3" in out["reason"] and "Label in Name" in out["reason"]
    assert "not in the application" in out["reason"], (
        "it must point at the machine, not send somebody to fix the app"
    )


def test_one_element_without_a_name_is_not_a_broken_machine(world):
    """The normal case, and it must stay silent. Plenty of real controls have no computed name —
    that is 4.1.2's problem, reported as a finding, not a fault in the audit."""
    from apps.a11y.baseline import _name_coverage
    from apps.a11y.models import A11yCandidateBundle

    audit = _audit(world, "/")
    for index, name in enumerate(("Catalogue", "", "Help")):
        A11yCandidateBundle.objects.create(
            tenant_id=world["t"], project_id=world["p"], run_key=str(audit.id),
            route="/", position=index, selector=f"#e{index}", checkers=["semantics"],
            element={"tag": "a", "text": "x", "accessible_name": name},
        )

    out = _name_coverage(world["t"], world["p"], str(audit.id))

    assert out["named"] == 2 and out["nameable"] == 3
    assert "reason" not in out, "two of three named is a working machine"


def test_a_capture_with_nothing_nameable_in_it_makes_no_claim(world):
    """A page of nothing but paragraphs says nothing about whether names can be read. Silence is
    the honest answer, not an accusation."""
    from apps.a11y.baseline import _name_coverage
    from apps.a11y.models import A11yCandidateBundle

    audit = _audit(world, "/")
    A11yCandidateBundle.objects.create(
        tenant_id=world["t"], project_id=world["p"], run_key=str(audit.id),
        route="/", position=0, selector="#p1", checkers=["color"],
        element={"tag": "p", "text": "words", "accessible_name": ""},
    )

    out = _name_coverage(world["t"], world["p"], str(audit.id))

    assert out == {"named": 0, "nameable": 0}


def test_the_audit_carries_what_it_could_read(world, ready_folder):
    """On the audit itself, so the screen can say it and a reader of an old audit can see which
    of its checks were actually able to run."""
    audit = _audit(world, "/")
    _post(world, audit, _screen("/"))

    finish_baseline_audit(tenant_id=world["t"], audit_id=str(audit.id), trigger=None)

    audit.refresh_from_db()
    assert "names" in audit.summary
    assert set(audit.summary["names"]) >= {"named", "nameable"}


def test_the_audit_script_does_not_use_the_removed_accessibility_api():
    """The regression guard for the worst defect this feature has had. `page.accessibility` was
    removed from Playwright; the call threw on every element, a per-element `catch` swallowed it,
    and 2.5.3 never selected anything for the whole life of the feature. Nothing about that was
    visible: the elements arrived, the others ran, and one was silently absent."""
    script = _script()
    # The CALL, not the word: the comment above `fillAccessibleNames` names the dead API on
    # purpose, so that whoever reads it next knows why this is written the way it is.
    assert "await page.accessibility" not in script, (
        "this API no longer exists; use locator.ariaSnapshot()"
    )
    assert ".accessibility.snapshot(" not in script.replace("`page.accessibility.snapshot()`", "")
    assert "ariaSnapshot(" in script


def test_the_audit_script_bounds_the_wait_for_one_name():
    """`ariaSnapshot` defaults to waiting FOR EVER. A selector that no longer matches — an
    element re-rendered between collection and naming — would stop the audit rather than cost it
    one name."""
    script = _script()
    assert "NAME_TIMEOUT_MS" in script
    assert "timeout: NAME_TIMEOUT_MS" in script


def test_the_audit_script_reads_a_name_out_of_a_real_aria_snapshot(tmp_path):
    """The parser itself, run as JavaScript, against snapshots taken from a real browser.

    Worth a real test rather than a source assertion: a regex is exactly the kind of thing that
    quietly does the wrong thing, and this one decides whether an entire WCAG criterion is
    checked. The cases below are Playwright 1.62 output, copied from what it actually returned
    for Meridian's pages.
    """
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed on this machine")

    script = _script()
    start = script.index("function nameFromAriaSnapshot")
    end = script.index("\n}", start) + 2
    fn = script[start:end]

    cases = [
        # (snapshot, the name it must read)
        ('- button "Extend the loan period on every item": Renew',
         "Extend the loan period on every item"),
        ('- heading "Card services" [level=1]', "Card services"),
        ('- link "Skip to content":\n  - /url: "#main"', "Skip to content"),
        ('- link "What\'s on":\n  - /url: /events/calendar', "What's on"),
        # No name at all — a paragraph is not named, and must not borrow one.
        ('- paragraph: Things you can do with your membership card.', ""),
        # …and MUST NOT take a quoted string out of the element's own text.
        ('- paragraph: He said "hello" to the room', ""),
        ('- text: Meridian Library', ""),
        ("", ""),
    ]
    harness = fn + "\nconst cases = " + json.dumps(cases) + ";\n" + """
    const bad = [];
    for (const [snapshot, expected] of cases) {
      const got = nameFromAriaSnapshot(snapshot);
      if (got !== expected) bad.push({ snapshot, expected, got });
    }
    process.stdout.write(JSON.stringify(bad));
    """
    path = tmp_path / "parse.mjs"
    path.write_text(harness, encoding="utf-8")
    out = subprocess.run([node, str(path)], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout or "[]") == [], out.stdout
