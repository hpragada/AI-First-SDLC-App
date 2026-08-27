"""Review-as-dispatch (req #1): the 08 review runs on the user's companion, not the server.

Covers the dispatch + poll + report-endpoint round trip and the CompanionReviewProvider, and
proves the companion provider still feeds the existing 07<->08 remediation loop unchanged.
"""
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from rest_framework.test import APIClient

from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec
from apps.runs.enrollment import enroll_runner
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import PullRequest, PullRequestRef
from orchestration import build_activities as ba
from orchestration import review_provider as rp
from orchestration.build_types import BuildInput, BuildReport
from orchestration.review_provider import (
    CompanionReviewProvider,
    dispatch_review_task,
    poll_review_body,
    record_review_report,
)

_VERDICT = (
    '```json\n{"status":"CHANGES_REQUIRED","findings":['
    '{"rem":"REM-C1","severity":"critical","title":"SQLi","file":"db.py","line":10},'
    '{"rem":"REM-S1","severity":"suggestion","title":"rename","file":"db.py","line":2}'
    ']}\n```'
)


class _FakeCodeHost:
    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        return PullRequestRef(sor="git", repo=repo, number=7, head=head,
                              url=f"https://github.com/{repo}/pull/7", sha="abc")

    def get_pull_request(self, *, pr_ref):
        repo, number = pr_ref.split("#")
        return PullRequest(repo=repo, number=int(number), title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc")

    def list_pr_files(self, *, pr_ref):
        return ["db.py"]

    def get_file(self, *, repo, path, ref):
        return "def q(): ...  # pretend code"

    def set_commit_status(self, **kw):
        pass


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Add login",
                                 state=WorkItem.State.ACCEPTED, feature_stream="ST-1")
    impl = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    AgentSpec.objects.create(tenant=t, key="08_code_review",
                             body_ref="agents/08_code_review/agent.md",
                             recommended_model="claude-x", phase_label="code_review")
    enrollment, token = enroll_runner(tenant_id=str(t.id), project_id=str(p.id), label="l")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=impl, engine="claude",
                             status=Run.Status.PENDING)
    return SimpleNamespace(t=t, p=p, wi=wi, spec=impl, run=run,
                           enrollment=enrollment, token=token)


def _inp(world, enrollment_id=None):
    return BuildInput(run_id=str(world.run.id), tenant_id=str(world.t.id),
                      project_id=str(world.p.id), work_item_id=str(world.wi.id),
                      agent_spec_id=str(world.spec.id), work_item_key="ST-1", repo="acme/api",
                      base="main", enrollment_id=enrollment_id)


# ── dispatch / poll / report (server side) ──────────────────────────
def test_dispatch_review_task_sets_block_and_clears_prior_body(world):
    world.run.outputs = {"review_body": "stale"}
    world.run.save(update_fields=["outputs"])
    dispatch_review_task(_inp(world, enrollment_id=str(world.enrollment.id)),
                         manifest="# PR diff", agent_body="08 BODY", model="claude-x")
    world.run.refresh_from_db()
    assert world.run.inputs["review_task"]["manifest"] == "# PR diff"
    assert world.run.inputs["review_task"]["kind"] == "review"
    assert world.run.inputs["dispatch"] == {
        "kind": "review", "enrollment_id": str(world.enrollment.id), "status": "pending"}
    assert "review_body" not in world.run.outputs   # prior cycle's body cleared


def test_dispatch_review_task_scrubs_nul(world):
    """A NUL byte in the manifest (a 09b PR can commit binary Playwright report files) must be
    stripped before the review_task lands in the JSON run.inputs — otherwise the write fails with
    "\\u0000 cannot be converted to text" and parks the run. The write must succeed and be clean."""
    dispatch_review_task(_inp(world), manifest="diff\x00with\x00nul", agent_body="08\x00body")
    world.run.refresh_from_db()
    assert world.run.inputs["review_task"]["manifest"] == "diffwithnul"
    assert "\x00" not in world.run.inputs["review_task"]["agent_body"]


def test_render_pr_section_omits_binary_files():
    """The review manifest inlines changed-file contents; a binary file (NUL present) must be
    skipped with a placeholder, never inlined — that is the root cause of the run park."""
    class _BinCodeHost:
        def list_pr_files(self, *, pr_ref):
            return ["src/app.py", "tests/automated/playwright-report/data/shot.png"]

        def get_pull_request(self, *, pr_ref):
            return PullRequest(repo="acme/api", number=7, title="t", state="open",
                               head="feature/ST-1", base="main", url="u", sha="abc")

        def get_file(self, *, repo, path, ref):
            return "print('hi')" if path.endswith(".py") else "PNG\x00\x01\x02binary"

    prov = rp.AgentReviewProvider(get_capability=lambda t, c: _BinCodeHost(),
                                  compose_manifest=lambda inp: "# base manifest")
    inp = BuildInput(run_id="r", tenant_id="t", project_id="p", work_item_id="w",
                     agent_spec_id="s", work_item_key="ST-1", repo="acme/api", base="main")
    manifest = prov._build_review_manifest(inp, "acme/api#7")
    assert "\x00" not in manifest
    assert "print('hi')" in manifest                       # text file still inlined
    assert "(binary file — omitted from review)" in manifest
    assert "binary" not in manifest.split("shot.png")[1]   # png bytes not inlined


class _PlainCodeHost:
    def list_pr_files(self, *, pr_ref):
        return ["src/app.py"]

    def get_pull_request(self, *, pr_ref):
        return PullRequest(repo="acme/api", number=7, title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc")

    def get_file(self, *, repo, path, ref):
        return "print('hi')"


def _provider():
    return rp.AgentReviewProvider(get_capability=lambda t, c: _PlainCodeHost(),
                                  compose_manifest=lambda inp: "# base manifest")


def test_the_reviewer_is_shown_the_rem_ids_it_already_has_open(world):
    """The 08 body is told to reuse a still-open finding's `rem` id on a re-review — but the
    manifest never carried the previous cycle's ids, so the agent had nothing to reuse and
    renumbered from 1 every time. REM-W1 then meant a different problem each cycle while the
    remediation board tracked the label instead of the finding."""
    WorkItem.objects.create(
        tenant=world.t, project=world.p, type=WorkItem.Type.TASK, parent=world.wi,
        title="duration-preview accepts reversed date ranges",
        state=WorkItem.State.IN_PROGRESS,
        external_ref={"rem": "REM-W1", "severity": "warning",
                      "file": "leave-application.service.ts", "line": 280})
    WorkItem.objects.create(
        tenant=world.t, project=world.p, type=WorkItem.Type.TASK, parent=world.wi,
        title="already fixed last cycle", state=WorkItem.State.DONE,
        external_ref={"rem": "REM-W9", "severity": "warning", "file": "old.ts", "line": 1})

    manifest = _provider()._build_review_manifest(_inp(world), "acme/api#7")

    assert "Findings Already Open From Your Previous Review" in manifest
    assert "REM-W1" in manifest
    assert "leave-application.service.ts:280" in manifest
    assert "REM-W9" not in manifest        # closed items are not open findings


def test_no_open_findings_section_on_the_first_review(world):
    """Nothing open yet — the section must not appear at all rather than as an empty heading
    the reviewer has to interpret."""
    manifest = _provider()._build_review_manifest(_inp(world), "acme/api#7")
    assert "Findings Already Open" not in manifest


def test_poll_returns_body_else_none(world):
    inp = _inp(world)
    assert poll_review_body(inp, sleep=lambda _s: None, poll_interval=1, timeout=0) is None
    world.run.outputs = {"review_body": _VERDICT}
    world.run.save(update_fields=["outputs"])
    assert poll_review_body(inp, sleep=lambda _s: None, poll_interval=1, timeout=0) == _VERDICT


def test_record_review_report_stores_body(world):
    record_review_report(tenant_id=str(world.t.id), run_id=str(world.run.id), body=_VERDICT)
    world.run.refresh_from_db()
    assert world.run.outputs["review_body"] == _VERDICT


def test_poll_does_a_final_grace_read_before_timeout(world):
    """S.No 110: the 08 verdict often lands moments after the last poll tick. poll_review_body
    must do one final read on timeout so a just-late report still drives the remediation loop
    instead of being orphaned in run.outputs while the merge gate opens with no findings."""
    inp = _inp(world)
    reads = {"n": 0}
    real_get = Run.objects.get

    def _get_side_effect(**kw):
        reads["n"] += 1
        # No body during the polling window; the companion posts it exactly at the timeout
        # boundary, so only the post-timeout grace read should see it.
        if reads["n"] == 2:
            world.run.outputs = {"review_body": _VERDICT}
            world.run.save(update_fields=["outputs"])
        return real_get(**kw)

    with patch.object(rp.Run.objects, "get", side_effect=_get_side_effect):
        # timeout=0 → one polling read (empty) then the grace read (finds the late body).
        body = poll_review_body(inp, sleep=lambda _s: None, poll_interval=1, timeout=0)
    assert body == _VERDICT


def test_companion_provider_honours_per_run_review_timeout(world):
    """The review wait is per-run configurable via inp.review_timeout_seconds (S.No 110):
    480s was too tight for a first cold-companion review and skipped the remediation loop."""
    seen = {}
    prov = CompanionReviewProvider(
        get_capability=lambda tid, cap: _FakeCodeHost(),
        compose_manifest=lambda inp: "# Project\n",
        dispatch=lambda inp, **kw: None,
        poll=lambda inp, **kw: seen.update(timeout=kw["timeout"]) or _VERDICT,
    )
    inp = _inp(world)
    inp.review_timeout_seconds = 1800
    prov.review(inp, "acme/api#7")
    assert seen["timeout"] == 1800.0


# ── CompanionReviewProvider ─────────────────────────────────────────
def test_companion_provider_dispatches_and_parses(world):
    captured = {}
    prov = CompanionReviewProvider(
        get_capability=lambda tid, cap: _FakeCodeHost(),
        compose_manifest=lambda inp: "# Project\nAcme\n",
        dispatch=lambda inp, **kw: captured.update(kw),
        poll=lambda inp, **kw: _VERDICT,
    )
    findings = prov.review(_inp(world), "acme/api#7")
    assert [f.rem for f in findings] == ["REM-C1", "REM-S1"]
    assert "# Pull Request Under Review" in captured["manifest"]   # PR diff shipped to companion


def test_companion_provider_timeout_returns_empty(world):
    prov = CompanionReviewProvider(
        get_capability=lambda tid, cap: _FakeCodeHost(),
        compose_manifest=lambda inp: "# Project\n",
        dispatch=lambda inp, **kw: None, poll=lambda inp, **kw: None,
    )
    assert prov.review(_inp(world), "acme/api#7") == []


def test_companion_provider_no_08_returns_empty(world):
    AgentSpec.objects.filter(tenant=world.t, key="08_code_review").delete()

    def _no_dispatch(inp, **kw):
        raise AssertionError("must not dispatch when 08 is not seeded")

    prov = CompanionReviewProvider(dispatch=_no_dispatch, poll=lambda inp, **kw: _VERDICT)
    assert prov.review(_inp(world), "acme/api#7") == []


def test_companion_provider_feeds_remediation_loop(world, monkeypatch):
    """The companion verdict → blocking finding → remediation child WorkItem, exactly as the
    server-side provider did — the loop machinery is unchanged, only where 08 runs."""
    fake = _FakeCodeHost()
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    prov = CompanionReviewProvider(
        get_capability=lambda tid, cap: fake, compose_manifest=lambda inp: "# Project\n",
        dispatch=lambda inp, **kw: None, poll=lambda inp, **kw: _VERDICT,
    )
    monkeypatch.setattr(ba, "get_review_provider", lambda: prov)
    out = ba.run_code_review_core(_inp(world))
    assert out["open_blocking"] == 1 and out["findings"] == 2
    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1"


# ── runner endpoints (claim review + post verdict) ──────────────────
def _auth(world):
    return {"HTTP_AUTHORIZATION": f"Runner {world.token}", "HTTP_X_TENANT_ID": str(world.t.id)}


def test_work_claim_returns_review_task(world):
    dispatch_review_task(_inp(world, enrollment_id=str(world.enrollment.id)),
                         manifest="# PR diff", agent_body="08 BODY")
    r = APIClient().get("/api/runner/work/", **_auth(world))
    assert r.status_code == 200
    assert r.json()["kind"] == "review"
    assert r.json()["payload"]["manifest"] == "# PR diff"


def test_review_report_endpoint_stores_verdict(world):
    r = APIClient().post(f"/api/runner/reviews/{world.run.id}/report/",
                         {"status": "ok", "body": _VERDICT}, format="json", **_auth(world))
    assert r.status_code == 200 and r.json()["recorded"] is True
    world.run.refresh_from_db()
    assert world.run.outputs["review_body"] == _VERDICT


# ── robust verdict parse + fail-closed guard (Bugs S.No 114) ─────────
# The 08 reply this bug came from: a prose executive summary that names blocking findings
# (CHANGES_REQUIRED + REM-C/REM-W) but carries NO fenced json verdict block. The old parser
# read 0 findings → 0 blocking → merge gate opened on an unreviewed downgrade.
_PROSE_BLOCKING_NO_JSON = (
    "The review is complete.\n\n## Review Complete — CHANGES_REQUIRED\n\n"
    "| REM-C1 | CRITICAL | PR size ~1,100 lines |\n"
    "| REM-W1 | WARNING | PR targets main not develop |\n"
    "Here is the executive summary — no machine-readable block follows."
)


def test_parse_findings_uses_last_verdict_block_ignoring_illustrative_json():
    """A body may show illustrative json before the real verdict; parse must take the LAST block
    that looks like a verdict, and ignore non-verdict json and trailing prose."""
    text = ("Format example:\n```json\n{\"note\":\"ignore me\"}\n```\n"
            "My verdict:\n" + _VERDICT + "\n\nThanks for reading!")
    assert [f.rem for f in rp.parse_findings(text)] == ["REM-C1", "REM-S1"]


def test_parse_findings_empty_when_no_verdict_block():
    assert rp.parse_findings("just prose, no json at all") == []


def test_parse_and_guard_passes_through_a_clean_verdict(world):
    findings = rp.parse_and_guard(_VERDICT, tenant_id=str(world.t.id), run_id=str(world.run.id))
    assert [f.rem for f in findings] == ["REM-C1", "REM-S1"]


def test_parse_and_guard_returns_empty_on_empty_body(world):
    # Review timeout path (S.No 110): empty body has no blocking signal → [] (gate still applies).
    assert rp.parse_and_guard("", tenant_id=str(world.t.id), run_id=str(world.run.id)) == []
    assert rp.parse_and_guard(None, tenant_id=str(world.t.id), run_id=str(world.run.id)) == []


def test_parse_and_guard_fails_closed_when_blocking_signalled_but_unparsed(world):
    """THE S.No 114 fix: prose says CHANGES_REQUIRED / REM-C / REM-W but no json parses → raise
    (fail closed) and log review.parse_mismatch, so the merge gate is never opened blind."""
    from apps.ledger.models import Event
    with pytest.raises(rp.ReviewContractError):
        rp.parse_and_guard(_PROSE_BLOCKING_NO_JSON,
                           tenant_id=str(world.t.id), run_id=str(world.run.id))
    assert Event.objects.filter(tenant=world.t, action="review.parse_mismatch",
                                target_id=str(world.run.id)).exists()


def test_parse_and_guard_trusts_approved_verdict_mentioning_resolved_rem(world):
    """Bugs S.No 114 false-positive (WI-27): a clean APPROVED verdict (0 blocking, one
    suggestion) whose *narrative* names a RESOLVED REM-W1 must NOT fail closed — the present,
    parseable verdict is authoritative; the prose REM mention is history, not an active blocker."""
    from apps.ledger.models import Event
    body = (
        "## Findings Summary\n\n### REM-W1 — RESOLVED (Cycle 1 → Cycle 2; confirmed closed)\n"
        "The blocking Warning REM-W1 raised in Cycle 1 was resolved and remains resolved.\n\n"
        "## Review Verdict\n\n**APPROVED** — no Criticals, no open Warnings.\n\n"
        '```json\n{"status":"APPROVED","findings":['
        '{"rem":"REM-S1","severity":"suggestion","title":"add note","file":"a.py","line":1}'
        ']}\n```'
    )
    findings = rp.parse_and_guard(body, tenant_id=str(world.t.id), run_id=str(world.run.id))
    assert [f.rem for f in findings] == ["REM-S1"]        # trusted through, not raised
    assert not any(f.severity in rp._BLOCKING for f in findings)   # 0 blocking → merge gate
    assert not Event.objects.filter(tenant=world.t, action="review.parse_mismatch",
                                    target_id=str(world.run.id)).exists()


def test_parse_and_guard_fails_closed_on_in_json_downgrade(world):
    """A parseable verdict whose own status demands changes but whose findings array carries no
    blocking items is a genuine in-JSON downgrade → still fail closed (guard strengthened)."""
    body = ('```json\n{"status":"CHANGES_REQUIRED","findings":['
            '{"rem":"REM-S1","severity":"suggestion","title":"nit","file":"a.py","line":1}'
            ']}\n```')
    with pytest.raises(rp.ReviewContractError):
        rp.parse_and_guard(body, tenant_id=str(world.t.id), run_id=str(world.run.id))


def test_companion_provider_fails_closed_on_contract_mismatch(world):
    """End-to-end through the provider: a blocking-but-unparseable verdict raises rather than
    feeding 0 findings into the loop (which would open the merge gate)."""
    prov = CompanionReviewProvider(
        get_capability=lambda tid, cap: _FakeCodeHost(),
        compose_manifest=lambda inp: "# Project\n",
        dispatch=lambda inp, **kw: None,
        poll=lambda inp, **kw: _PROSE_BLOCKING_NO_JSON,
    )
    with pytest.raises(rp.ReviewContractError):
        prov.review(_inp(world), "acme/api#7")


# ── remediation re-dispatch arms the companion claim (Bugs S.No 115) ─
# Without re-arming inputs['dispatch'] the companion has nothing to claim after remediation,
# so the 07 agent never re-runs, no build_reported ever fires, and the loop hangs → takeover.
def _open_rem_child(world, rem, severity):
    return WorkItem.objects.create(
        tenant=world.t, project=world.p, type=WorkItem.Type.TASK, parent=world.wi,
        title=f"fix {rem}", state=WorkItem.State.IN_PROGRESS,
        external_ref={"rem": rem, "severity": severity, "file": "db.py", "line": 10})


def test_dispatch_remediation_arms_build_claim_and_manifest(world):
    _open_rem_child(world, "REM-C1", "critical")
    _open_rem_child(world, "REM-W1", "warning")
    out = ba.dispatch_remediation_core(_inp(world, enrollment_id=str(world.enrollment.id)))
    assert out["items"] == 2
    world.run.refresh_from_db()
    # The claim block the companion polls for is armed as a pending BUILD, pinned to the enrollment.
    assert world.run.inputs["dispatch"] == {
        "kind": "build", "enrollment_id": str(world.enrollment.id), "status": "pending"}
    bt = world.run.inputs["build_task"]
    assert bt["remediation"] is True
    assert "Remediation Items" in bt["manifest"]
    assert "REM-C1" in bt["manifest"] and "REM-W1" in bt["manifest"]
    assert len(world.run.inputs["remediation"]["items"]) == 2  # brief retained for provenance


def test_dispatch_remediation_ships_preview_for_test_automation(world):
    """A 09b remediation re-runs the test-automation agent, which brings the app up — so it must
    carry the preview target like the initial dispatch. Without it the fix-build fails loud with
    'no preview target for this repo'."""
    from apps.projects.models import Repository

    Repository.objects.create(tenant=world.t, project=world.p, name="acme/api",
                              preview_url="http://127.0.0.1:5175/", is_default=True)
    _open_rem_child(world, "REM-C1", "critical")
    inp = _inp(world, enrollment_id=str(world.enrollment.id))
    inp.phase = "test_automation"
    ba.dispatch_remediation_core(inp)
    world.run.refresh_from_db()
    bt = world.run.inputs["build_task"]
    assert bt["preview_url"] == "http://127.0.0.1:5175/"
    assert "preview_start" in bt


def test_work_claim_returns_the_remediation_build(world):
    """The whole point (S.No 115): after remediation dispatch, /api/runner/work/ actually hands
    the companion a build task carrying the REM brief — previously it returned 204 forever."""
    _open_rem_child(world, "REM-C1", "critical")
    ba.dispatch_remediation_core(_inp(world, enrollment_id=str(world.enrollment.id)))
    r = APIClient().get("/api/runner/work/", **_auth(world))
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "build"
    assert "Remediation Items" in body["payload"]["manifest"]
    assert body["payload"]["remediation"] is True
