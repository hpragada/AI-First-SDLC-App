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
    assert "path alone" in str(err.value)


def test_a_route_must_start_at_the_apps_root():
    with pytest.raises(RouteError) as err:
        normalise_path("checkout")
    assert "must start with `/`" in str(err.value)


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

    assert "no routes are registered" in describe_routes(world["t"], world["p"])
    _register(world, "/", "/legacy")
    assert describe_routes(world["t"], world["p"]) == "2 route(s) registered for audit"
    register_routes(tenant_id=world["t"], project_id=world["p"], routes=["/"], replace=True)
    assert describe_routes(world["t"], world["p"]) == "1 route(s) registered for audit, 1 disabled"


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
    assert "path alone" in str(err.value)


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


def test_the_companion_may_leave_the_address_to_the_platform(tmp_path, monkeypatch):
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
    findings = list(A11yFinding.objects.filter(tenant_id=world["t"]))
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
    assert "axe-core is not installed" in script
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


def test_the_audit_run_posts_what_it_captured_and_closes_the_audit(tmp_path, monkeypatch):
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
