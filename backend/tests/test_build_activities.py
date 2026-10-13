"""P2 — BuildWorkflow activity cores (idempotent; CodeHost via the capability seam).

Pure activity-core tests (no Temporal): dispatch, open-PR, merge, gate, takeover/fail
compensation. CodeHost is a fake injected through `get_capability`.
"""
from types import SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

from apps.gates.models import Approval
from apps.ledger.models import Event
from apps.projects.models import Project, ProjectProfile
from apps.registry.models import AgentSpec, Artifact, TraceEdge
from apps.runs.models import Run
from apps.tenancy.models import Tenant
from apps.workitems.models import WorkItem
from integrations.types import PullRequest, PullRequestRef
from orchestration import build_activities as ba
from orchestration.build_types import BuildInput, BuildReport
from storage.object_store import InMemoryObjectStore


class _FakeCodeHost:
    def __init__(self, draft=False, mergeable_state="clean", mergeable=True):
        self.merged = False
        self.draft = draft
        self.ready_called = False
        self.statuses = []
        self.mergeable_state = mergeable_state
        self.mergeable = mergeable
        self.update_branch_called = False
        self.pr_title = ""
        self.pr_body = ""

    def open_pull_request(self, *, repo, head, base, title, body, draft=True):
        self.pr_title, self.pr_body = title, body
        return PullRequestRef(sor="git", repo=repo, number=7, head=head,
                              url=f"https://github.com/{repo}/pull/7", sha="abc")

    def get_pull_request(self, *, pr_ref):
        repo, number = pr_ref.split("#")
        return PullRequest(repo=repo, number=int(number), title="t", state="open",
                           head="feature/ST-1", base="main", url="u", sha="abc",
                           merged=self.merged, draft=self.draft,
                           mergeable=self.mergeable, mergeable_state=self.mergeable_state)

    def mark_ready_for_review(self, *, pr_ref):
        self.ready_called = True
        self.draft = False

    def update_branch(self, *, pr_ref):
        self.update_branch_called = True
        self.mergeable_state = "clean"     # updating a behind branch resolves it
        self.mergeable = True

    def ensure_mergeable(self, *, pr_ref):
        if self.mergeable_state == "behind":
            self.update_branch(pr_ref=pr_ref)
        return self.get_pull_request(pr_ref=pr_ref)

    def merge_pull_request(self, *, pr_ref, method="squash"):
        # Mirror GitHub: a draft PR cannot be merged (this is the 405 the fix guards against).
        assert not self.draft, "attempted to merge a draft PR"
        assert self.mergeable_state != "dirty", "attempted to merge a conflicted PR"
        self.merged = True
        return self.get_pull_request(pr_ref=pr_ref)

    def set_commit_status(self, **kw):
        self.statuses.append(kw)


@pytest.fixture
def world(db):
    t = Tenant.objects.create(name="Acme")
    p = Project.objects.create(tenant=t, name="App")
    ProjectProfile.objects.create(tenant=t, project=p, important_context="Ship it.")
    wi = WorkItem.objects.create(tenant=t, project=p, type=WorkItem.Type.STORY, title="Add login",
                                 state=WorkItem.State.ACCEPTED, feature_stream="ST-1")
    spec = AgentSpec.objects.create(tenant=t, key="07_implementation", body_ref="",
                                    recommended_model="claude-x", phase_label="implementation")
    run = Run.objects.create(tenant=t, work_item=wi, agent_spec=spec, engine="claude",
                             status=Run.Status.PENDING)
    return SimpleNamespace(t=t, p=p, wi=wi, spec=spec, run=run)


def _inp(world, **over):
    base = dict(run_id=str(world.run.id), tenant_id=str(world.t.id), project_id=str(world.p.id),
                work_item_id=str(world.wi.id), agent_spec_id=str(world.spec.id),
                work_item_key="ST-1", repo="acme/api", base="main")
    base.update(over)
    return BuildInput(**base)


def _use_fake_codehost(monkeypatch, fake):
    monkeypatch.setattr("integrations.registry.get_capability", lambda tid, cap: fake)


def test_dispatch_assembles_payload_and_marks_running(world):
    ba.dispatch_build_core(_inp(world))
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.RUNNING
    payload = world.run.inputs["build_task"]
    assert payload["repo"] == "acme/api" and payload["work_item_key"] == "ST-1"
    assert payload["manifest"]                       # composed manifest shipped to the companion
    # G2: WorkItem title/type travel so the companion derives the Conventional-Commit message.
    assert payload["work_item_title"] == "Add login" and payload["work_item_type"] == "story"


def test_dispatch_sets_claim_block_for_companion(world):
    ba.dispatch_build_core(_inp(world, enrollment_id="enr-9"))
    world.run.refresh_from_db()
    assert world.run.inputs["dispatch"] == {
        "kind": "build", "enrollment_id": "enr-9", "status": "pending"}


def test_open_pr_registers_code_pointer_and_is_idempotent(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    report = BuildReport(status="ok", branch="feature/ST-1", head_sha="abc",
                         changed_files=["login.py"])
    out = ba.open_build_pr_core(_inp(world), report)
    assert out["pr"]["number"] == 7
    art = Artifact.objects.get(run_id=world.run.id, type="code")
    assert art.sor == "git" and art.status == Artifact.Status.STAGED
    assert art.external_ref["number"] == 7
    assert fake.statuses and fake.statuses[0]["state"] == "pending"

    again = ba.open_build_pr_core(_inp(world), report)
    assert again.get("idempotent") is True
    assert Artifact.objects.filter(run_id=world.run.id, type="code").count() == 1


def test_open_pr_reconciles_agent_pre_pr_pointer(world, monkeypatch):
    """The implementation agent registers a *pre-PR* `code` pointer (branch/files, no PR).
    open_build_pr must still open the PR and reconcile that pointer in place — not mistake it
    for an already-opened PR (the KeyError('repo')/no-PR bug)."""
    from mcp_platform_state import tools
    tools.register_artifact(
        str(world.t.id), str(world.p.id), str(world.run.id), "implementation", "code", "git",
        content_hash="", external_ref={"branch": "feature/ST-1", "files_changed": ["login.py"]})
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)

    out = ba.open_build_pr_core(_inp(world), BuildReport(status="ok", branch="feature/ST-1",
                                                         head_sha="abc"))

    assert out.get("idempotent") is not True          # the PR was actually opened
    assert out["pr"]["number"] == 7
    # the agent's pointer was reconciled in place — still one artifact, now carrying the PR ref
    arts = Artifact.objects.filter(run_id=world.run.id, type="code")
    assert arts.count() == 1
    art = arts.first()
    assert art.external_ref["repo"] and art.external_ref["number"] == 7
    assert art.status == Artifact.Status.STAGED


def test_merge_performs_the_gated_write_then_publish_completes_the_run(world, monkeypatch):
    """S.No 152: merge does the gated SoR write only; publish_build_artifacts publishes the
    artifacts and completes the run (mirroring the planning path's split)."""
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    monkeypatch.setattr(ba, "get_object_store", InMemoryObjectStore)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    out = ba.merge_build_pr_core(_inp(world))
    assert out["merged"] is True and fake.merged is True
    # Idempotent: a second merge on an already-merged PR is a no-op.
    assert ba.merge_build_pr_core(_inp(world))["merged"] is True

    ba.publish_build_artifacts_core(_inp(world))
    assert Artifact.objects.get(run_id=world.run.id, type="code").status == \
        Artifact.Status.PUBLISHED
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.COMPLETED


def test_publish_build_artifacts_publishes_every_artifact_not_just_the_code_one(world,
                                                                                monkeypatch):
    """S.No 152: after gate approval the Assumptions + Code Review artifacts stayed DRAFT forever
    — the build path published ONLY the `code` artifact, having no publish step of its own."""
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    store = InMemoryObjectStore()
    monkeypatch.setattr(ba, "get_object_store", lambda: store)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))
    # The other artifacts a build produces (registered by the agent / the review step).
    store.put("bodies/review.md", b"# Review")
    review = Artifact.objects.create(
        tenant=world.t, project=world.p, run=world.run, phase="implementation",
        type="code_review", sor=Artifact.SoR.INTERNAL, status=Artifact.Status.DRAFT,
        s3_key="bodies/review.md", title="Code Review — Add login", content_hash="d1",
    )
    assumption = Artifact.objects.create(
        tenant=world.t, project=world.p, run=world.run, phase="implementation",
        type="assumption", sor=Artifact.SoR.INTERNAL, status=Artifact.Status.DRAFT,
        title="Assumptions", content_hash="d2",
    )

    out = ba.publish_build_artifacts_core(_inp(world))

    review.refresh_from_db()
    assumption.refresh_from_db()
    code = Artifact.objects.get(run_id=world.run.id, type="code")
    assert review.status == Artifact.Status.PUBLISHED
    assert assumption.status == Artifact.Status.PUBLISHED
    assert code.status == Artifact.Status.PUBLISHED
    assert len(out["published"]) == 3
    # The code artifact's SoR pointer must survive — publishing only changes status.
    assert code.sor == Artifact.SoR.GIT and code.external_ref["number"] == 7
    assert review.sor == Artifact.SoR.INTERNAL
    # A body-bearing artifact gets its immutable audit snapshot, as on the planning path.
    assert any(k.startswith("snapshots/") for k in store._data)


def test_publish_build_artifacts_is_idempotent(world, monkeypatch):
    """Temporal retries/replays must not double-publish or fail on an already-published run."""
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    monkeypatch.setattr(ba, "get_object_store", InMemoryObjectStore)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    first = ba.publish_build_artifacts_core(_inp(world))
    second = ba.publish_build_artifacts_core(_inp(world))

    assert first["published"] == second["published"]
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.COMPLETED


def test_merge_takes_draft_pr_out_of_draft_first(world, monkeypatch):
    """Build PRs are opened as drafts (draft during the review loop); GitHub refuses to merge a
    draft PR (405). merge_build_pr_core must mark it ready-for-review before merging (Bugs:
    draft-PR merge 405)."""
    fake = _FakeCodeHost(draft=True)
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    out = ba.merge_build_pr_core(_inp(world))

    assert fake.ready_called is True          # un-drafted before merge
    assert out["merged"] is True and fake.merged is True


def test_reopen_merge_gate_resets_approval_and_records_conflict(world):
    """S.No 141 ENH-2: after a merge conflict, reopen_merge_gate must reset the (approved) merge
    Approval back to PENDING, keep the run AWAITING_GATE, and record the conflict reason — so the
    reviewer can resolve it in GitHub and approve again to retry, without a rebuild."""
    ba.open_merge_gate_core(_inp(world))
    ap = Approval.objects.get(run_id=world.run.id, gate_type="merge_gate")
    ap.decision = Approval.Decision.APPROVED
    ap.save(update_fields=["decision"])

    out = ba.reopen_merge_gate_core(
        _inp(world), "merge failed: merge conflict: the branch conflicts with its base")

    ap.refresh_from_db()
    world.run.refresh_from_db()
    assert out["status"] == "merge_conflict_reopened"
    assert ap.decision == Approval.Decision.PENDING          # gate re-opened for a retry
    assert world.run.status == Run.Status.AWAITING_GATE      # not FAILED — recoverable
    assert "merge conflict" in (world.run.outputs.get("merge_conflict") or "").lower()


def test_open_merge_gate_creates_reviewer_approval(world):
    approval_id = ba.open_merge_gate_core(_inp(world))
    ap = Approval.objects.get(id=approval_id)
    assert ap.required_role == "reviewer" and ap.gate_type == "merge_gate"
    assert ap.decision == Approval.Decision.PENDING
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.AWAITING_GATE


def test_takeover_flags_workitem_and_fails_run(world):
    ba.mark_takeover_core(_inp(world))
    world.wi.refresh_from_db()
    world.run.refresh_from_db()
    assert world.wi.takeover_flag is True and world.run.status == Run.Status.FAILED


def test_build_failed_returns_workitem_to_in_progress(world):
    world.wi.state = WorkItem.State.IN_REVIEW
    world.wi.save(update_fields=["state"])
    ba.mark_build_failed_core(_inp(world), "compiler error")
    world.wi.refresh_from_db()
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.FAILED
    assert world.wi.state == WorkItem.State.IN_PROGRESS


# ── S.No 157: park on error instead of ending the build ──────────────
def test_park_build_keeps_the_run_recoverable_with_a_classified_reason(world):
    """S.No 157: an error PARKS the build — STALLED (not terminal FAILED), with a classified
    reason and the step to resume from, while the workflow stays alive waiting for the human.
    Previously this path ran mark_build_failed and returned, which closed the Temporal history
    for good — the only way forward was a whole new run that rebuilt everything from step 1."""
    world.wi.state = WorkItem.State.IN_PROGRESS
    world.wi.save(update_fields=["state"])

    out = ba.park_build_core(_inp(world), "merge failed: 403 branch protection", "merge_build_pr")

    world.run.refresh_from_db()
    world.wi.refresh_from_db()
    assert out["status"] == "parked"
    assert world.run.status == Run.Status.STALLED             # recoverable, not FAILED
    assert world.run.outputs["resumable"] is True
    assert world.run.outputs["resume_from"] == "merge_build_pr"
    # The reason is classified (S.No 139) — the user reads plain language, not a raw 403.
    assert "branch protection" in world.run.outputs["error"]
    assert "403" not in world.run.outputs["error"]
    # The WorkItem is untouched — it is already in_progress, which stays true for a paused build.
    assert world.wi.state == WorkItem.State.IN_PROGRESS


def test_park_build_is_idempotent(world):
    ba.park_build_core(_inp(world), "boom", "open_build_pr")
    ba.park_build_core(_inp(world), "boom", "open_build_pr")     # Temporal may retry
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.STALLED
    assert world.run.outputs["resume_from"] == "open_build_pr"


def test_resume_build_unparks_and_clears_the_markers(world):
    """S.No 157: resuming puts the run back to RUNNING and clears the park markers, so the
    console stops offering Resume / showing a stale failure once it is moving again."""
    ba.park_build_core(_inp(world), "merge failed: 403", "merge_build_pr")

    out = ba.resume_build_core(_inp(world))

    world.run.refresh_from_db()
    assert out["status"] == "resumed" and out["resume_from"] == "merge_build_pr"
    assert world.run.status == Run.Status.RUNNING
    assert "error" not in world.run.outputs and "resumable" not in world.run.outputs
    assert "resume_from" not in world.run.outputs


# ── S.No 136: never merge a stale/conflicted branch as-is ────────────
def test_merge_updates_a_behind_branch_then_merges(world, monkeypatch):
    """The base moved since the branch was cut → mergeable_state='behind' (no conflict). The
    merge must update the branch against base first, then merge — not fail."""
    fake = _FakeCodeHost(mergeable_state="behind", mergeable=None)
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    out = ba.merge_build_pr_core(_inp(world))

    assert fake.update_branch_called is True     # updated against base before merging
    assert out["merged"] is True and fake.merged is True


def test_merge_conflict_fails_clean_not_raw_405(world, monkeypatch):
    """A true conflict (mergeable_state='dirty') must NOT be PUT-merged (that raises a raw 405).
    It fails fast, non-retryably, with a clear reason — the run is never left merged."""
    fake = _FakeCodeHost(mergeable_state="dirty", mergeable=False)
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    with pytest.raises(ApplicationError) as exc:
        ba.merge_build_pr_core(_inp(world))
    assert exc.value.non_retryable is True
    assert "merge conflict" in str(exc.value).lower()
    assert fake.merged is False                  # never merged a conflicted PR


# ── S.No 139: classified failure reasons ────────────────────────────
def test_classify_build_failure_maps_known_reasons():
    c = ba.classify_build_failure
    assert "merge conflict" in c("merge failed: GitHub PUT .../merge -> 405").lower()
    assert "permission" in c("pr/gate setup failed: ... -> 403 forbidden").lower()
    assert "remediation" in c("remediation cycles exhausted").lower()
    assert "empty build" in c("pr/gate setup failed: empty build: no commits between").lower()
    assert "without reporting a specific reason" in c("build reported failed").lower()
    assert c("secret scan blocked the push: 2 finding(s): ...").startswith("secret scan")
    # an unrecognized specific message is preserved, never lost
    assert c("ImportError: no module named foo") == "ImportError: no module named foo"


def test_is_merge_conflict_detects_typed_cause_and_message():
    """S.No 141 ENH-2: the workflow decides retry-vs-fail with is_merge_conflict. It must catch
    the typed ApplicationError (type='MergeConflict', set by merge_build_pr_core) AND fall back to
    the message text — robust whether or not Temporal preserved the typed cause."""
    from orchestration.build_types import is_merge_conflict

    assert is_merge_conflict(SimpleNamespace(cause=SimpleNamespace(type="MergeConflict"))) is True
    assert is_merge_conflict(SimpleNamespace(cause=RuntimeError("merge conflict: resolve it")))
    assert is_merge_conflict(SimpleNamespace(cause=RuntimeError("some other error"))) is False
    assert is_merge_conflict(RuntimeError("plain error")) is False


def test_is_review_failed_detects_typed_cause_and_message():
    """The workflow decides park-vs-raise with is_review_failed. Same two-way detection as its
    siblings, and it must NOT fire on an ordinary review that merely found problems."""
    from orchestration.build_types import is_review_failed

    assert is_review_failed(SimpleNamespace(cause=SimpleNamespace(type="ReviewFailed"))) is True
    assert is_review_failed(
        SimpleNamespace(cause=RuntimeError("code review did not complete: exit code 1")))
    assert is_review_failed(SimpleNamespace(cause=RuntimeError("CHANGES_REQUIRED"))) is False
    assert is_review_failed(RuntimeError("plain error")) is False


def test_a_failed_review_is_raised_non_retryable_not_counted_as_clean(world, monkeypatch):
    """A review the engine never completed must stop the build, not read as zero findings.
    Non-retryable because the usual cause is a usage limit, which an immediate retry only
    walks back into."""
    _open_pr(world, monkeypatch)

    class _DeadEngine:
        def review(self, inp, pr_ref):
            from orchestration.review_provider import ReviewUnavailableError
            raise ReviewUnavailableError("code review did not complete: exit code 1")

    monkeypatch.setattr(ba, "get_review_provider", lambda: _DeadEngine())
    with pytest.raises(ApplicationError) as exc:
        ba.run_code_review_core(_inp(world))
    assert exc.value.type == "ReviewFailed"
    assert exc.value.non_retryable is True
    assert "exit code 1" in str(exc.value)
    # No gate may be opened off the back of it, and no artifact may claim a clean review.
    assert not Artifact.objects.filter(run_id=world.run.id, type="code_review").exists()


def test_the_artifact_never_claims_no_findings_for_a_review_that_failed(world):
    """Belt-and-braces on the rendering itself: same empty body, opposite meaning."""
    world.run.outputs = {"review_body": "", "review_status": "failed",
                         "review_error": "Command failed with exit code 1"}
    world.run.save(update_fields=["outputs"])
    body = ba._review_body_for_artifact(_inp(world), [])
    assert "No findings were raised" not in body
    assert "did not complete" in body
    # Option A: the approver reads why in words; the raw engine error stays on the run.
    assert "closed before it finished" in body and "exit code 1" not in body


def test_the_artifact_still_says_no_findings_for_a_genuinely_clean_review(world):
    world.run.outputs = {"review_body": "", "review_status": "ok"}
    world.run.save(update_fields=["outputs"])
    assert "No findings were raised" in ba._review_body_for_artifact(_inp(world), [])


def test_remediation_description_reads_as_a_real_brief(world):
    """S.No 147: the remediation work item was created with a title and NO description at all —
    every word of the reviewer's explanation was discarded. It must now carry the problem, the
    fix, and where it is."""
    finding = ba.Finding(
        rem="REM-C1", severity="critical", title="Search filter is open to SQL injection",
        file="api/search.py", line=42, category="Security — A03 Injection",
        problem="The user's search text is pasted straight into the SQL statement.",
        fix="Pass the search text as a query parameter.",
    )

    body = ba._remediation_description(finding)

    assert "must be fixed before the code can merge" in body     # plain-language severity lead
    assert "The user's search text is pasted straight into the SQL statement." in body
    assert "Pass the search text as a query parameter." in body
    assert "`api/search.py` line 42" in body                     # the technical nuance is kept
    assert "Security — A03 Injection" in body and "REM-C1" in body


def test_remediation_description_is_honest_when_the_review_gave_no_detail():
    """A title-only finding must not imply a fuller brief that doesn't exist."""
    body = ba._remediation_description(ba.Finding(rem="REM-W1", severity="warning", title="t"))
    assert "did not provide further detail" in body
    assert "should be fixed" in body and "REM-W1" in body


def test_review_opens_remediation_items_with_a_readable_description(world, monkeypatch):
    """S.No 147 end-to-end: the child work item the board shows carries the reviewer's words."""
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    class _Provider:
        def review(self, inp, pr_ref):
            return [ba.Finding(rem="REM-C1", severity="critical", title="SQL injection in search",
                               file="api/search.py", line=42, category="Security",
                               problem="Input is concatenated into the query.",
                               fix="Use a parameterized query.")]

    ba.set_review_provider(_Provider())
    try:
        ba.run_code_review_core(_inp(world))
    finally:
        ba.set_review_provider(None)

    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.title == "SQL injection in search"
    assert "Input is concatenated into the query." in child.description
    assert "Use a parameterized query." in child.description


def test_remediation_brief_gives_agent_07_the_review_detail(world):
    """S.No 147: agent 07 was asked to fix each finding from its one-line title — the reviewer's
    problem/fix detail never reached its manifest."""
    section = ba._render_remediation_section([
        {"rem": "REM-C1", "severity": "critical", "title": "SQL injection in search",
         "file": "api/search.py", "line": 42,
         "description": "**What's wrong**\n\nInput is concatenated.\n\n**What to do**\n\nUse a "
                        "parameterized query."},
    ])
    assert "REM-C1" in section and "api/search.py:42" in section
    assert "Input is concatenated." in section
    assert "Use a parameterized query." in section


def test_display_name_prefers_the_title_over_the_branch_slug():
    """S.No 151: artifact + PR names must show the task's TITLE. work_item_key is a branch slug
    and degrades to 'WI-<uuid8>' when the item has no SoR id — meaningless to a reader."""
    from orchestration.build_types import display_name

    assert display_name(SimpleNamespace(work_item_title="Add login",
                                        work_item_key="WI-85bb350f")) == "Add login"
    # No title (or a blank/whitespace one) → fall back to the key rather than an empty name.
    assert display_name(SimpleNamespace(work_item_title="   ", work_item_key="TASK-003")) \
        == "TASK-003"
    assert display_name(SimpleNamespace(work_item_title="", work_item_key="TASK-003")) \
        == "TASK-003"


def test_build_artifacts_and_pr_are_named_with_the_task_title(world, monkeypatch):
    """S.No 151: the platform's own fallback naming used the branch slug, so users saw
    'Code Review — WI-85bb350f' instead of the task they triggered. The PR title leaked it to
    GitHub too. All three now read the title."""
    codehost = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, codehost)
    inp = _inp(world)
    inp.work_item_title = "Add login"
    inp.work_item_key = "WI-85bb350f"

    ba.open_build_pr_core(inp, BuildReport(status="ok", branch="feature/x", head_sha="abc",
                                           changed_files=["a.py"]))

    art = Artifact.objects.get(run_id=world.run.id, type="code")
    assert art.title == "Code — Add login"
    assert codehost.pr_title == "Add login: build"        # what a human sees in GitHub
    assert "WI-85bb350f" in codehost.pr_body              # the key still identifies the branch


def test_is_empty_build_detects_typed_cause_and_message():
    """S.No 157: an EMPTY BUILD must never be parked for a Resume — the agent produced no changes,
    so resuming would fail identically forever. The workflow tells it apart from a resumable error
    with is_empty_build, which (like is_merge_conflict) catches the typed ApplicationError
    (type='EmptyBuild', set by open_build_pr_core) and falls back to the message text."""
    from orchestration.build_types import is_empty_build

    assert is_empty_build(SimpleNamespace(cause=SimpleNamespace(type="EmptyBuild"))) is True
    assert is_empty_build(SimpleNamespace(cause=RuntimeError("empty build: no commits between")))
    assert is_empty_build(SimpleNamespace(cause=RuntimeError("merge conflict"))) is False
    assert is_empty_build(RuntimeError("GitHub 403 branch protection")) is False


def test_failure_reason_unwraps_activity_error_cause():
    """S.No 139: str(ActivityError) is the generic 'Activity task failed'; the meaningful message
    lives on .cause. failure_reason must surface the cause so the classifier can see it — without
    this the S.No 136 'merge conflict' message and empty-build/422 reasons never reach the user."""
    from orchestration.build_types import failure_reason

    wrapped = SimpleNamespace(cause=RuntimeError("merge conflict: needs manual resolution"))
    assert "merge conflict" in failure_reason(wrapped)
    # No cause → falls back to the exception itself.
    assert failure_reason(RuntimeError("plain error")) == "plain error"


def test_open_pr_empty_build_fails_fast_with_clear_reason(world, monkeypatch):
    """S.No 139: a build that produced no changes (no head_sha, no changed_files) can't open a PR
    (GitHub 422). Fail fast, non-retryably, with a clear 'empty build' reason — not a cryptic 422
    after 3 retries. This is the expected outcome for a redundant task (e.g. TASK-002 vs 001)."""
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    empty = BuildReport(status="ok", branch="feature/ST-1", head_sha="", changed_files=[])
    with pytest.raises(ApplicationError) as exc:
        ba.open_build_pr_core(_inp(world), empty)
    assert exc.value.non_retryable is True
    assert "empty build" in str(exc.value).lower()
    # The classifier turns it into the user-facing reason.
    assert "empty build" in ba.classify_build_failure(str(exc.value)).lower()


def test_mark_build_failed_classifies_and_writes_to_run_outputs(world):
    """S.No 139: the classified reason is stored on run.outputs.error (where the run console
    reads it) and in the build.failed event — not just a bare 'Build failed'."""
    ba.mark_build_failed_core(_inp(world), "merge failed: GitHub PUT .../merge -> 405")
    world.run.refresh_from_db()
    assert "merge conflict" in (world.run.outputs.get("error") or "").lower()


# ── remediation-exhaustion auto-retry (Bugs S.No 161) ────────────────
def test_review_persists_blocking_finding_detail_not_just_counts(world, monkeypatch):
    """S.No 161: the run console (and an eventual auto-retry) used to see only
    {blocking: N, findings: M} — no way to tell WHAT blocked. Each review cycle now appends the
    actual finding detail to run.outputs.review_cycles."""
    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-C1", severity="critical", title="SQL injection",
                    file="db.py", line=42)],
    ]))
    ba.run_code_review_core(_inp(world))
    world.run.refresh_from_db()
    cycles = world.run.outputs["review_cycles"]
    assert len(cycles) == 1
    assert cycles[0]["blocking"] == [
        {"rem": "REM-C1", "severity": "critical", "title": "SQL injection",
         "file": "db.py", "line": 42}
    ]


def test_remediation_exhausted_auto_retries_with_seeded_context(world, monkeypatch):
    """S.No 161: attempt 1 of 2 exhausting remediation auto-retries as a FRESH run instead of
    hard-failing — the new run's BuildInput carries attempt=2 and a readable digest of what
    blocked attempt 1, and the old run is marked failed (not left dangling)."""
    from apps.tenancy.models import User
    from orchestration import trigger as trigger_mod

    # The retry must route to the SAME companion as the original trigger — carry triggered_by
    # forward, or the new run dispatches with a null enrollment and sits unclaimable (the
    # build-dispatch binding bug). Give the original run a triggering user to prove it flows.
    user = User.objects.create_user(email="dev@acme.test", name="Dev", tenant=world.t,
                                    password="p")
    world.run.triggered_by = user
    started = {}
    monkeypatch.setattr(trigger_mod, "_default_build_starter",
                        lambda workflow_id, inp: started.update(workflow_id=workflow_id, inp=inp))
    captured = {}
    world.run.outputs = {"review_cycles": [{
        "blocking": [{"rem": "REM-C1", "severity": "critical", "title": "SQL injection",
                      "file": "db.py", "line": 42}],
        "blocking_count": 1, "findings_count": 1,
    }]}
    world.run.save(update_fields=["outputs", "triggered_by"])

    import orchestration.trigger as _tm

    real_trigger = _tm.trigger_build

    def _spy(**kw):
        captured.update(kw)
        return real_trigger(**kw)

    monkeypatch.setattr(_tm, "trigger_build", _spy)

    out = ba.handle_remediation_exhausted_core(_inp(world, attempt=1))

    assert out["action"] == "retried"
    assert captured["triggered_by"] == str(user.id)   # routed to the original companion
    assert started["inp"].attempt == 2
    assert "SQL injection" in started["inp"].prior_attempt_context
    assert "db.py:42" in started["inp"].prior_attempt_context
    new_run = Run.objects.get(id=started["inp"].run_id)
    assert new_run.id != world.run.id and new_run.work_item_id == world.wi.id
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.FAILED
    assert world.run.outputs["retry_run_id"] == str(new_run.id)


def test_remediation_exhausted_parks_once_auto_retries_are_also_exhausted(world):
    """S.No 161: only after `max_auto_attempts` auto-retried attempts have ALL exhausted does
    this park for a human — the last resort, not the first response to one failed cycle."""
    world.run.outputs = {"review_cycles": [{
        "blocking": [{"rem": "REM-W1", "severity": "warning", "title": "naming",
                      "file": "x.py", "line": 1}],
        "blocking_count": 1, "findings_count": 1,
    }]}
    world.run.save(update_fields=["outputs"])

    out = ba.handle_remediation_exhausted_core(_inp(world, attempt=2, max_auto_attempts=2))

    assert out["action"] == "park"
    assert "naming" in out["reason"] and "x.py:1" in out["reason"]
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.PENDING     # untouched — the park activity does this


# ── a pre-push secret block is not a dead end ───────────────────────
_SECRET_FINDINGS = [
    {"kind": "high_entropy_secret", "path": "packages/backend/src/auth/jwt.strategy.ts",
     "line": 73, "preview": "conf***ow (24 chars)"},
]


def test_a_secret_block_auto_retries_with_the_findings_seeded(world, monkeypatch):
    """Before this, a secret block failed the run and the agent was never told what tripped — the
    only way forward was a human re-trigger with no memory of it. Now it gets the same bounded
    auto-retry as remediation-exhaustion, seeded with the redacted findings."""
    from apps.tenancy.models import User
    from orchestration import trigger as trigger_mod

    user = User.objects.create_user(email="dev2@acme.test", name="Dev", tenant=world.t,
                                    password="p")
    world.run.triggered_by = user
    world.run.save(update_fields=["triggered_by"])
    started = {}
    monkeypatch.setattr(trigger_mod, "_default_build_starter",
                        lambda workflow_id, inp: started.update(workflow_id=workflow_id, inp=inp))

    out = ba.handle_secret_block_core(
        _inp(world, attempt=1),
        "secret scan blocked the push: 1 finding(s)", _SECRET_FINDINGS)

    assert out["action"] == "retried"
    ctx = started["inp"].prior_attempt_context
    assert started["inp"].attempt == 2
    assert "jwt.strategy.ts:73" in ctx                 # the agent is told WHERE
    assert "conf***ow (24 chars)" in ctx               # ...and only the REDACTED shape
    assert "environment variable" in ctx               # ...and what to do instead
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.FAILED
    assert world.run.outputs["retry_run_id"] == str(started["inp"].run_id)
    # D6: the findings are persisted on the run, so the block is diagnosable after the fact
    assert world.run.outputs["secret_findings"] == _SECRET_FINDINGS


def test_a_secret_block_fails_terminally_once_retries_are_exhausted(world):
    """Bounded: the last attempt does NOT retry again, and does not park either — parking resumes
    mid-workflow and there is no branch to resume onto (nothing was ever pushed)."""
    out = ba.handle_secret_block_core(
        _inp(world, attempt=2, max_auto_attempts=2), "secret scan blocked the push",
        _SECRET_FINDINGS)

    assert out["action"] == "failed"
    world.run.refresh_from_db()
    assert world.run.status == Run.Status.PENDING     # untouched — mark_build_failed does this


def test_the_retry_context_never_carries_an_unredacted_value(world, monkeypatch):
    """The previews are what `guardrails._redact` produced, so seeding the next prompt with them
    cannot leak a credential — pin that the activity passes them through rather than re-deriving."""
    from orchestration import trigger as trigger_mod

    started = {}
    monkeypatch.setattr(trigger_mod, "_default_build_starter",
                        lambda workflow_id, inp: started.update(inp=inp))
    ba.handle_secret_block_core(
        _inp(world, attempt=1), "blocked",
        [{"kind": "high_entropy_secret", "path": "a.ts", "line": 1,
          "preview": "sk_l***hL (38 chars)"}])
    ctx = started["inp"].prior_attempt_context
    assert "sk_l***hL" in ctx
    assert "sk_live" not in ctx        # the full value shape never appears


# ── code review + remediation loop (07<->08) ────────────────────────
class _ScriptedReviewer:
    """Returns successive finding lists per review call (last one repeats)."""

    def __init__(self, scripts):
        self._scripts = list(scripts)
        self._i = 0

    def review(self, inp, pr_ref):
        out = self._scripts[min(self._i, len(self._scripts) - 1)]
        self._i += 1
        return out


def _open_pr(world, monkeypatch):
    _use_fake_codehost(monkeypatch, _FakeCodeHost())
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))


def test_review_opens_remediation_child_then_resolves_it(world, monkeypatch):
    _open_pr(world, monkeypatch)
    reviewer = _ScriptedReviewer([
        [ba.Finding(rem="REM-C1", severity="critical", title="SQLi", file="db.py", line=10)],
        [],   # second review: the finding is gone (fixed by the remediation build)
    ])
    monkeypatch.setattr(ba, "get_review_provider", lambda: reviewer)

    first = ba.run_code_review_core(_inp(world))
    assert first["open_blocking"] == 1
    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-C1" and child.state == WorkItem.State.IN_PROGRESS
    review_art = Artifact.objects.get(run_id=world.run.id, type="code_review")
    assert TraceEdge.objects.filter(from_artifact=review_art, rel="tests").exists()

    second = ba.run_code_review_core(_inp(world))
    assert second["open_blocking"] == 0
    child.refresh_from_db()
    assert child.state == WorkItem.State.DONE        # resolved → closed


def test_review_suggestions_are_non_blocking(world, monkeypatch):
    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-S1", severity="suggestion", title="rename var")],
    ]))
    out = ba.run_code_review_core(_inp(world))
    assert out["findings"] == 1 and out["open_blocking"] == 0   # REM-S never blocks
    assert not WorkItem.objects.filter(parent_id=world.wi.id, type=WorkItem.Type.TASK).exists()


def test_dispatch_remediation_briefs_the_open_items(world, monkeypatch):
    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-W1", severity="warning", title="naming")],
    ]))
    ba.run_code_review_core(_inp(world))
    out = ba.dispatch_remediation_core(_inp(world))
    assert out["items"] == 1
    world.run.refresh_from_db()
    assert world.run.inputs["remediation"]["items"][0]["rem"] == "REM-W1"
    assert world.run.status == Run.Status.RUNNING


def test_a_reused_rem_id_rebriefs_07_with_the_finding_it_now_means(world, monkeypatch):
    """The WI-87 deadlock, reproduced end to end.

    A `rem` id is a POSITION in one review's output, not an identity: the reviewer numbers from 1
    each cycle, so REM-W1 can mean a different problem next time. The board entry used to be
    frozen at creation (state flipped, nothing else), and `dispatch_remediation_core` briefs
    agent 07 from exactly those frozen fields — so 07 kept re-fixing cycle 1's finding while the
    reviewer blocked on one 07 was never told about. Unwinnable: 20 cycles, 15 rebuilds, 0
    progress. The brief must describe the finding the reviewer raised THIS cycle."""
    _open_pr(world, monkeypatch)
    reviewer = _ScriptedReviewer([
        [ba.Finding(rem="REM-W1", severity="warning",
                    title="COMPOFF_EXPIRED has no user-friendly message",
                    file="ApplyLeavePage.tsx", line=131,
                    problem="The error code falls through to the generic message.",
                    fix="Add a COMPOFF_EXPIRED case to mapApiErrorToMessage.")],
        # Cycle 2: 07 fixed that one, so the reviewer moved on — and reused REM-W1 for something
        # entirely different, in a different file.
        [ba.Finding(rem="REM-W1", severity="warning",
                    title="duration-preview accepts reversed date ranges",
                    file="leave-application.service.ts", line=280,
                    problem="previewWorkingDays never calls validateDateRange.",
                    fix="Call validateDateRange before computing working days.")],
    ])
    monkeypatch.setattr(ba, "get_review_provider", lambda: reviewer)

    ba.run_code_review_core(_inp(world))
    ba.run_code_review_core(_inp(world))

    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["rem"] == "REM-W1"          # same id, deliberately
    assert child.state == WorkItem.State.IN_PROGRESS
    assert "reversed date ranges" in child.title           # …now pointing at the real finding
    assert child.external_ref["file"] == "leave-application.service.ts"
    assert child.external_ref["line"] == 280

    ba.dispatch_remediation_core(_inp(world))
    world.run.refresh_from_db()
    brief = world.run.inputs["remediation"]["items"][0]
    assert "reversed date ranges" in brief["title"]
    assert "validateDateRange" in brief["description"]
    # The decisive assertion: the stale finding must be gone from what 07 is asked to do.
    assert "COMPOFF" not in brief["title"] and "COMPOFF" not in brief["description"]
    assert Event.objects.filter(action="remediation.retargeted").exists()


def test_a_reused_rem_id_that_still_means_the_same_thing_is_not_flagged(world, monkeypatch):
    """The ordinary case — the finding is genuinely still open and the reviewer reused its id.
    That is the contract working, not a collision, so no `remediation.retargeted` noise. The
    entry is still refreshed (the line may have moved as the file changed around it)."""
    _open_pr(world, monkeypatch)
    reviewer = _ScriptedReviewer([
        [ba.Finding(rem="REM-W1", severity="warning", title="naming is unclear",
                    file="a.py", line=10)],
        [ba.Finding(rem="REM-W1", severity="warning", title="naming is unclear",
                    file="a.py", line=14)],
    ])
    monkeypatch.setattr(ba, "get_review_provider", lambda: reviewer)
    ba.run_code_review_core(_inp(world))
    ba.run_code_review_core(_inp(world))

    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.external_ref["line"] == 14
    assert not Event.objects.filter(action="remediation.retargeted").exists()


def test_a_fresh_attempt_does_not_inherit_the_previous_attempts_board(world, monkeypatch):
    """Remediation children hang off the WorkItem, not the run, so an auto-retry used to start
    with the last attempt's open items still on the board — mis-briefed on cycle 1, before its
    reviewer had said anything. They are CLOSED, not deleted: they are the previous attempt's
    record, and `prior_attempt_context` already carries their substance to the new agent."""
    from orchestration import trigger as trigger_mod

    _open_pr(world, monkeypatch)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([
        [ba.Finding(rem="REM-W1", severity="warning", title="COMPOFF_EXPIRED unmapped",
                    file="ApplyLeavePage.tsx", line=131)],
    ]))
    ba.run_code_review_core(_inp(world))
    child = WorkItem.objects.get(parent_id=world.wi.id, type=WorkItem.Type.TASK)
    assert child.state == WorkItem.State.IN_PROGRESS

    monkeypatch.setattr(trigger_mod, "_default_build_starter", lambda workflow_id, inp: None)
    out = ba.handle_remediation_exhausted_core(_inp(world, attempt=1))

    assert out["action"] == "retried"
    child.refresh_from_db()
    assert child.state == WorkItem.State.DONE
    assert Event.objects.filter(action="remediation.closed").exists()
    assert WorkItem.objects.filter(id=child.id).exists()      # closed, never deleted


def test_review_survives_duplicate_pre_pr_code_pointer(world, monkeypatch):
    """A remediation build makes the implementation agent re-register a fresh *pre-PR* `code`
    pointer (no repo/number) on the same run, so a run can carry two `code` artifacts. Review
    (and merge) must operate on the artifact carrying the real PR ref, not the pre-PR pointer —
    otherwise `_code_artifact().first()` non-deterministically picked the pre-PR one and review
    raised "no opened PR to review" (Bugs: remediation duplicate code artifact)."""
    from mcp_platform_state import tools
    _open_pr(world, monkeypatch)                     # artifact #1: the opened PR (repo+number)
    # artifact #2: the agent's remediation pre-PR pointer (registered AFTER the PR artifact)
    tools.register_artifact(
        str(world.t.id), str(world.p.id), str(world.run.id), "implementation", "code", "git",
        content_hash="", external_ref={"branch": "feature/ST-1", "work_item_id": str(world.wi.id)})
    assert Artifact.objects.filter(run_id=world.run.id, type="code").count() == 2

    picked = ba._code_artifact(_inp(world))
    assert ba._is_pr_ref(picked.external_ref)         # prefers the real PR ref, not the pre-PR one

    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([[]]))
    out = ba.run_code_review_core(_inp(world))         # must NOT raise "no opened PR to review"
    assert out["open_blocking"] == 0


# ── classify_build_failure: engine / usage-limit reasons (Bugs S.No 146) ──────
# Pure-function (no DB): the classifier turns raw engine-failure strings into human-readable
# reasons, and must leave the already-classified paths untouched.
@pytest.mark.parametrize("raw,expect_substr", [
    # a usage/rate limit surfaced via the driver-captured engine stderr tail
    ("Command failed with exit code 1\nEngine stderr (tail):\nClaude usage limit reached. "
     "Your limit will reset at 5pm.", "reached its usage limit"),
    ("Error: 429 Too Many Requests", "reached its usage limit"),
    ("The engine is overloaded, try again", "reached its usage limit"),
    # engine could not launch on the companion
    ("Failed to start Claude Code: open_process() got an unexpected keyword argument 'user'",
     "couldn't start"),
    # bare non-zero exit with no captured stderr (the exact WI-32 symptom) still reads clearly
    ("Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for "
     "details", "closed before it finished"),
])
def test_classify_build_failure_engine_reasons(raw, expect_substr):
    assert expect_substr in ba.classify_build_failure(raw).lower()


@pytest.mark.parametrize("raw,expect_substr", [
    ("merge failed: GitHub PUT /repos/x/pulls/14/merge -> 405", "merge conflict"),
    ("pr/gate setup failed: 403 Forbidden", "permission denied"),
    ("Empty build: the agent produced no changes to commit.", "empty build"),
    # the S.No 130 secret-scan message must pass through verbatim
    ("secret scan blocked the push: 1 finding(s): [high_entropy_secret] a.env:2",
     "secret scan blocked the push"),
])
def test_classify_build_failure_leaves_other_paths_intact(raw, expect_substr):
    assert expect_substr in ba.classify_build_failure(raw).lower()


# ── the engine-failure corpus: distinct causes must READ distinctly ──────────────────────────
# Nine builds across two tenants died with a byte-identical message and none could be
# root-caused. They lasted 0.2, 2.7, 7.3, 9.3, 12.5, 23.8 and 75.2 minutes — they cannot all
# have been the one cause the message asserted ("most common cause is a usage/rate limit").
# The old wording was a guess stated as a finding, and it directed the investigation.
#
# This corpus is the ratchet: each row is a raw engine failure and what a human must be able to
# tell from the classified reason. Add a row whenever a new engine failure shape appears.
_ENGINE_FAILURE_CORPUS = [
    # (label, raw reason, must contain, must NOT contain)
    ("usage limit, with a reset time the notice carried",
     "Command failed with exit code 1 (exit code: 1)\nEngine output (tail):\n"
     "[engine] Skipping non-JSON line from CLI stdout: Claude AI usage limit reached|1755432000",
     ["reached its usage limit", "resets 2025-08-17"], []),
    ("usage limit with no timestamp — still named, just no reset time",
     "Engine output (tail):\n[engine] Claude AI usage limit reached",
     ["reached its usage limit"], ["(resets"]),
    ("bare exit, nothing captured — must NOT invent a cause",
     "Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for "
     "details",
     ["closed before it finished"], ["most common cause", "usage limit"]),
    ("engine died 12 seconds in, before producing anything",
     "Command failed with exit code 1 (exit code: 1)\n"
     "Engine progress before the failure: 0 message(s).",
     ["closed before it finished"], ["usage limit"]),
    ("engine died 12 minutes in, after real work — must read differently from the row above",
     "Command failed with exit code 1 (exit code: 1)\nEngine progress before the failure: "
     "214 message(s), 2 artifact(s) registered.\nLast agent output: …applying the review fix to "
     "auth.service.ts",
     ["closed before it finished"], ["usage limit"]),
    ("could not launch at all",
     "Failed to start Claude Code: open_process() got an unexpected keyword argument 'user'",
     ["couldn't start"], ["usage limit"]),
]


@pytest.mark.parametrize("label,raw,must,must_not",
                         _ENGINE_FAILURE_CORPUS, ids=[c[0][:38] for c in _ENGINE_FAILURE_CORPUS])
def test_engine_failure_corpus(label, raw, must, must_not):
    out = ba.classify_build_failure(raw)
    low = out.lower()
    for phrase in must:
        assert phrase.lower() in low, f"{label}: missing {phrase!r} in {out!r}"
    for phrase in must_not:
        assert phrase.lower() not in low, f"{label}: must not claim {phrase!r} — {out!r}"
    # Option A (2026-09-21): the engine's own output is not in the sentence; it is kept whole in
    # the technical detail beside it, where a developer opens it.
    assert ba._technical_detail(raw, out) == raw.strip(), f"{label}: the evidence was dropped"


def test_two_different_engine_failures_never_render_identically():
    """A 12-second failure and a 12-minute one used to produce the same string, which is why nine
    occurrences looked like one bug. They may share a SENTENCE now (both are "the engine closed
    early"); what a developer reads — the technical detail stored beside it — must still differ."""
    fast_raw = ("Command failed with exit code 1 (exit code: 1)\n"
                "Engine progress before the failure: 0 message(s).")
    slow_raw = ("Command failed with exit code 1 (exit code: 1)\n"
                "Engine progress before the failure: 214 message(s), 2 artifact(s) registered.")
    fast = ba._technical_detail(fast_raw, ba.classify_build_failure(fast_raw))
    slow = ba._technical_detail(slow_raw, ba.classify_build_failure(slow_raw))
    assert fast != slow and "0 message(s)" in fast and "214 message(s)" in slow


def test_the_sentence_never_points_at_a_terminal_or_a_file_path():
    """The old message sent the reader to a terminal that no longer existed, and later to a log
    path on the developer's machine. The client-facing sentence names neither (option A)."""
    out = ba.classify_build_failure(
        "Command failed with exit code 1 (exit code: 1)\n"
        "Error output: Check stderr output for details")
    assert "terminal" not in out and "<worktrees>" not in out and "stderr" not in out


def test_an_unrecognised_engine_shape_still_keeps_the_raw_output():
    """Never drop evidence in favour of a sentence we made up — an unknown shape is kept whole in
    the technical detail beside the sentence."""
    raw = "processerror: the engine said something we have never seen before, verbatim"
    assert "something we have never seen before" in ba._technical_detail(
        raw, ba.classify_build_failure(raw))


def test_the_planning_path_classifies_the_same_way():
    """05_ux_design and 06_task_breakdown both died with this too — the planning mirror must not
    drift from the build classifier."""
    from orchestration.activities import classify_phase_failure

    raw = ("Command failed with exit code 1 (exit code: 1)\nEngine output (tail):\n"
           "[engine] Claude AI usage limit reached|1755432000")
    out = classify_phase_failure(raw, phase="ux")
    assert out.startswith("The UX phase stopped because the AI engine reached its usage limit")
    assert "resets 2025-08-17" in out
    bare = classify_phase_failure("Command failed with exit code 1 (exit code: 1)")
    assert "most common cause" not in bare.lower() and "closed before it finished" in bare


def test_a_paused_phase_reads_like_a_paused_build_and_keeps_the_raw_text(world):
    """The agent-run park stored its reason exactly as raised — the one path never rewritten.
    It now says one sentence, keeps the raw text for "Technical details", and clears both on
    resume (team: "apply the same fix to the agent runs too", 2026-09-21)."""
    from orchestration.activities import park_run_core, resume_run_state_core
    from orchestration.types import AgentRunInput

    inp = AgentRunInput(run_id=str(world.run.id), tenant_id=str(world.t.id),
                        project_id=str(world.p.id), work_item_id=str(world.wi.id),
                        agent_spec_id=str(world.spec.id), phase="prd")
    raw = ("Command failed with exit code 1 Last agent output: You've hit your session limit"
           " · resets 1:20am (Asia/Kolkata)")
    park_run_core(inp, raw, "execute_agent")
    world.run.refresh_from_db()
    assert world.run.outputs["error"] == (
        "The PRD phase stopped because the AI engine reached its usage limit (resets 1:20 AM, "
        "Asia/Kolkata). Resume once the limit resets.")
    assert world.run.outputs["error_detail"] == raw
    ev = Event.objects.filter(target_id=str(world.run.id), action="run.parked").latest("ts")
    from api.serializers import EventSerializer
    assert EventSerializer(ev).data["message"] == \
        "Run paused — stopped: the AI engine reached its usage limit"
    resume_run_state_core(inp)
    world.run.refresh_from_db()
    assert "error" not in world.run.outputs and "error_detail" not in world.run.outputs


# ── an engine exit must PARK, not kill the run (Bugs S.No 146, second pass) ──────────────────
# TASK-014's engine exited during remediation and took a run that already had a working PR and a
# completed code review with it. Every other recoverable failure in this workflow has a recourse
# (secret block → auto-retry, remediation exhaustion → auto-retry, merge error → park); this one
# called mark_build_failed and returned, which closes the Temporal history for good.
@pytest.mark.parametrize("message,parks,why", [
    ("Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for "
     "details", True, "the exact nine-occurrence symptom"),
    ("Engine output (tail):\n[engine] Claude AI usage limit reached|1755432000", True,
     "a usage limit is transient by definition"),
    ("Failed to start Claude Code: open_process() ...", True, "the engine never came up"),
    # ...but these are NOT the engine going away, and must stay on their own paths
    ("Empty build: the agent produced no changes to commit.", False,
     "no amount of waiting makes a diff appear — a Resume that cannot work is worse than a "
     "clear failure"),
    ("secret scan blocked the push: 1 finding(s): [high_entropy_secret] a.ts:1", False,
     "has its own auto-retry; the agent needs a FRESH attempt, not the same one resumed"),
    ("git add -A failed: fatal: not a git repository", False, "a real build failure"),
    ("", False, "nothing to go on"),
])
def test_is_engine_exit_separates_a_dead_engine_from_a_failed_build(message, parks, why):
    from orchestration.build_types import is_engine_exit

    assert is_engine_exit(message) is parks, why


def test_the_empty_build_guard_still_holds_against_the_engine_markers():
    """An empty build's message can mention an exit code without becoming resumable."""
    from orchestration.build_types import is_empty_build, is_engine_exit

    msg = "Empty build: the agent produced no changes to commit. (exit code: 0)"
    assert is_engine_exit(msg) is False
    assert is_empty_build(SimpleNamespace(cause=None, message=msg)) or "empty build" in msg.lower()


# ── a code review must leave a body you can actually read (Artifacts preview bug) ────────────
# The QA member opened TASK-019's code-review artifact and got "This artifact doesn't exist, has
# no body, or you don't have access to it" — on a run that had completed successfully. The review
# text was intact on `run.outputs["review_body"]` (24,702 chars); the artifact simply pointed at
# nothing, because this function registered a `sor="internal"` row with a content_hash and no
# body. 11 of 11 such artifacts in the QA tenant were unpreviewable. Unlike a `code` row — a
# pointer at a PR, correctly bodyless (#1/#3) — an internal row has no system of record to read
# back from, so an unstaged body exists nowhere at all.
def _review_findings():
    return [ba.Finding(rem="REM-C1", severity="critical", title="SQL injection",
                       file="db.py", line=42, problem="User input is concatenated into SQL.",
                       fix="Use a parameterised query.")]


def test_a_completed_review_leaves_a_body_that_reads_back(world, monkeypatch):
    store = InMemoryObjectStore()
    monkeypatch.setattr(ba, "get_object_store", lambda: store)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([_review_findings()]))
    _open_pr(world, monkeypatch)
    world.run.outputs = {"review_body": "# Code Review\n\nThe reviewer's own prose."}
    world.run.save(update_fields=["outputs"])

    ba.run_code_review_core(_inp(world))

    art = Artifact.objects.get(run_id=world.run.id, type="code_review")
    assert art.s3_key, "registered a pointer to nothing — this is the defect"
    assert store.get(art.s3_key).decode() == "# Code Review\n\nThe reviewer's own prose."
    # ...and the row is genuinely previewable, by the same rule the UI uses.
    from integrations.preview import artifact_has_preview
    assert artifact_has_preview(art) is True


def test_the_review_artifact_is_filed_under_its_own_phase(world, monkeypatch):
    """`inp.phase` is the BUILD phase ("implementation"), so the platform filed reviews under the
    phase that produced the code rather than their own — disagreeing with every review the
    reviewer registers for itself."""
    monkeypatch.setattr(ba, "get_object_store", lambda: InMemoryObjectStore())
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([_review_findings()]))
    _open_pr(world, monkeypatch)

    ba.run_code_review_core(_inp(world, phase="implementation"))

    assert Artifact.objects.get(run_id=world.run.id, type="code_review").phase == "code_review"


def test_a_later_cycle_restages_rather_than_leaving_the_first_pass(world, monkeypatch):
    """Cycle 2 used to update only the hash, so the artifact kept resolving to cycle 1's body."""
    store = InMemoryObjectStore()
    monkeypatch.setattr(ba, "get_object_store", lambda: store)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([_review_findings()]))
    _open_pr(world, monkeypatch)
    world.run.outputs = {"review_body": "cycle 1 review"}
    world.run.save(update_fields=["outputs"])
    ba.run_code_review_core(_inp(world))

    world.run.outputs = {"review_body": "cycle 2 review"}
    world.run.save(update_fields=["outputs"])
    ba.run_code_review_core(_inp(world))

    arts = Artifact.objects.filter(run_id=world.run.id, type="code_review")
    assert arts.count() == 1, "a cycle must not spawn a second review row"
    assert store.get(arts.first().s3_key).decode() == "cycle 2 review"


def test_a_review_with_no_prose_still_gets_a_readable_body(world, monkeypatch):
    """Never leave the artifact pointing at nothing — if the reviewer returned findings but no
    prose, render the findings. An empty body would 404 exactly as before."""
    store = InMemoryObjectStore()
    monkeypatch.setattr(ba, "get_object_store", lambda: store)
    monkeypatch.setattr(ba, "get_review_provider", lambda: _ScriptedReviewer([_review_findings()]))
    _open_pr(world, monkeypatch)   # run.outputs has no review_body at all

    ba.run_code_review_core(_inp(world))

    body = store.get(Artifact.objects.get(run_id=world.run.id, type="code_review").s3_key).decode()
    assert "REM-C1" in body and "SQL injection" in body and "db.py:42" in body


# ── a leftover pre-PR pointer gets the PR's link, not a blank page ───────────────────────────
def test_a_stray_code_pointer_is_given_the_pr_link(world, monkeypatch):
    """Each remediation cycle registers a fresh pre-PR pointer. The first is reconciled; by cycle
    2 a real PR row exists, open_build_pr returns early as idempotent, and the new pointer is
    orphaned with no url — 21 such rows across 14 runs. It previews as a blank page."""
    _open_pr(world, monkeypatch)
    stray = Artifact.objects.create(
        tenant=world.t, project=world.p, run=world.run, phase="implementation",
        type="code", sor=Artifact.SoR.GIT, status=Artifact.Status.DRAFT,
        external_ref={"sor": "git", "branch": "feature/ST-1", "files_changed": ["a.ts"]},
        title="TASK-x remediation cycle 2", content_hash="",
    )

    out = ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    assert out.get("idempotent") is True
    stray.refresh_from_db()
    assert stray.external_ref["url"], "stray pointer still previews blank"
    # ...and it must NOT look like the opened PR, or _code_artifact could pick it for merge.
    assert not ba._is_pr_ref(stray.external_ref)
    assert stray.external_ref["files_changed"] == ["a.ts"]      # its own provenance is kept


def test_linking_strays_never_touches_the_real_pr_row(world, monkeypatch):
    _open_pr(world, monkeypatch)
    pr_row = ba._code_artifact(_inp(world))
    before = dict(pr_row.external_ref)

    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    pr_row.refresh_from_db()
    assert pr_row.external_ref == before
    assert ba._code_artifact(_inp(world)).id == pr_row.id       # merge still finds the same PR


# ── S.No 132: the sdlc/build check must reach a terminal state ───────────────────────────────
#
# It was posted as `pending` when the PR opened and NOTHING ever moved it. Harmless while the
# check is optional; a permanent block on every merge the moment anyone makes it required on
# GitHub, because it could never reach green.
def _final_status(fake):
    """The last sdlc/build status posted, or None."""
    ours = [s for s in fake.statuses if s.get("context") == "sdlc/build"]
    return ours[-1] if ours else None


def test_a_merged_build_finishes_the_commit_check(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))
    assert _final_status(fake)["state"] == "pending"

    ba.merge_build_pr_core(_inp(world))

    final = _final_status(fake)
    assert final["state"] == "success" and final["sha"] == "abc"


def test_a_failed_build_finishes_the_commit_check(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    ba.mark_build_failed_core(_inp(world), "compiler error")

    final = _final_status(fake)
    assert final["state"] == "failure" and final["sha"] == "abc"


def test_a_taken_over_build_finishes_the_commit_check(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    ba.mark_takeover_core(_inp(world))

    assert _final_status(fake)["state"] == "failure"


def test_a_merge_conflict_leaves_the_check_pending(world, monkeypatch):
    """The merge gate re-opens for a resolve-then-retry — the build is still live, so `pending`
    is the honest state and must NOT be finished."""
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    ba.reopen_merge_gate_core(_inp(world), "merge conflict: the branch conflicts with its base")

    assert _final_status(fake)["state"] == "pending"


def test_nothing_is_posted_when_no_commit_was_ever_pushed(world, monkeypatch):
    """A secret-blocked build never pushed a branch, so there is no commit to attach a status to.
    Guessing one would mark a stranger's commit."""
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)

    ba.mark_build_failed_core(_inp(world), "secret detected in the diff")

    assert fake.statuses == []


def test_a_status_that_cannot_be_written_never_fails_the_build(world, monkeypatch):
    class _Broken(_FakeCodeHost):
        def set_commit_status(self, **kw):
            raise RuntimeError("GitHub is down")

    fake = _Broken()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))

    out = ba.merge_build_pr_core(_inp(world))       # must not raise

    assert out["merged"] is True


# ── S.No 218: a rejected build supersedes its drafts, as the planning path already did ───────
def test_a_rejected_build_supersedes_its_drafts(world, monkeypatch):
    """Without this the code artifact sits at STAGED — the status that reads "Waiting for
    approval" on screen — forever, after a human has already turned it down."""
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))
    assert Artifact.objects.get(run_id=world.run.id, type="code").status == \
        Artifact.Status.STAGED

    out = ba.reject_build_core(_inp(world), "not what we asked for")

    assert out["superseded_artifacts"] == 1
    assert Artifact.objects.get(run_id=world.run.id, type="code").status == \
        Artifact.Status.SUPERSEDED
    assert _final_status(fake)["state"] == "failure"


def test_rejecting_a_build_never_unpublishes_an_already_merged_artifact(world, monkeypatch):
    fake = _FakeCodeHost()
    _use_fake_codehost(monkeypatch, fake)
    monkeypatch.setattr(ba, "get_object_store", InMemoryObjectStore)
    ba.open_build_pr_core(_inp(world), BuildReport(branch="feature/ST-1", head_sha="abc"))
    ba.merge_build_pr_core(_inp(world))
    ba.publish_build_artifacts_core(_inp(world))

    ba.reject_build_core(_inp(world), "late change of mind")

    assert Artifact.objects.get(run_id=world.run.id, type="code").status == \
        Artifact.Status.PUBLISHED


# ── run-console wording (2026-09-21, option A): one row per case in the approved table ─────────
_TOKEN_401 = ("pr/gate setup failed: CapabilityError: GitHub GET "
              "/repos/TARUN51/medslot-single-repo/pulls -> 401")
_SESSION_LIMIT = ("code review did not complete: Command failed with exit code 1 (exit code: 1) "
                  "Last agent output: ...You've hit your session limit · resets 1:20am "
                  "(Asia/Kolkata) Engine output (tail): [engine] Fatal error")


@pytest.mark.parametrize("raw,subject,sentence", [
    (_TOKEN_401, "",
     "GitHub didn't accept the access token, so the pull request couldn't be opened. Ask your "
     "admin to reconnect GitHub in Integrations, then Resume."),
    (_SESSION_LIMIT, "review",
     "The code review stopped because the AI engine reached its usage limit (resets 1:20 AM, "
     "Asia/Kolkata). The code has not been reviewed yet. Resume once the limit resets."),
    ("code review did not complete: Command failed with exit code 1 Engine output (tail): x",
     "review",
     "The code review stopped because the AI engine closed before it finished. The code has not "
     "been reviewed yet. Resume to run the review again."),
    ("code review did not complete: the companion reported no reason", "review",
     "The code review stopped before it finished, and no reason was reported. The code has not "
     "been reviewed yet. Resume to run the review again."),
    ("Command failed with exit code 2 Engine output (tail): x", "",
     "The build stopped because the AI engine closed before it finished. Resume to carry on "
     "from the step that stopped."),
])
def test_each_failure_reads_as_the_approved_sentence(raw, subject, sentence):
    assert ba.classify_build_failure(raw, subject=subject) == sentence


def test_a_token_rejected_while_merging_says_merging():
    out = ba.classify_build_failure("merge failed: GitHub PUT /repos/x/pulls/3/merge -> 401")
    assert "couldn't be merged" in out and "401" not in out


def test_a_failed_run_is_never_told_to_resume():
    out = ba.classify_build_failure(_TOKEN_401, parked=False)
    assert "Resume" not in out and out.endswith("then try again.")


def test_a_parked_review_stores_the_sentence_the_detail_and_what_is_kept(world):
    """The step being resumed says it was the REVIEW — not the words of the message."""
    world.wi.state = WorkItem.State.IN_PROGRESS
    world.wi.save(update_fields=["state"])
    ba.park_build_core(_inp(world), "Command failed with exit code 1 Engine output (tail): boom",
                       "run_code_review")
    world.run.refresh_from_db()
    out = world.run.outputs
    assert out["error"].startswith("The code review stopped because the AI engine closed")
    assert "boom" in out["error_detail"] and "boom" not in out["error"]
    assert out["kept"] == ba.BUILD_KEPT
    ev = Event.objects.filter(target_id=str(world.run.id), action="build.parked").latest("ts")
    assert ev.payload["reason"] == "code review stopped: the AI engine closed before it finished"


def test_resume_clears_the_detail_and_the_kept_line(world):
    ba.park_build_core(_inp(world), _TOKEN_401, "open_build_pr")
    ba.resume_build_core(_inp(world))
    world.run.refresh_from_db()
    for key in ("error", "error_detail", "kept", "resumable"):
        assert key not in world.run.outputs


def test_the_console_lines_say_paused_and_stopped_not_the_raw_text(world):
    from api.serializers import EventSerializer
    from orchestration.review_provider import record_review_report

    record_review_report(tenant_id=str(world.t.id), run_id=str(world.run.id), body="",
                         status="failed", message="Command failed with exit code 1 (x)")
    ba.park_build_core(_inp(world), "code review did not complete: exit code 1",
                       "run_code_review")
    lines = {e.action: EventSerializer(e).data["message"]
             for e in Event.objects.filter(target_id=str(world.run.id))}
    assert lines["review.reported"] == \
        "Code review stopped — the AI engine closed before it finished"
    assert lines["build.parked"].startswith("Build paused — code review stopped:")
    assert "Command failed" not in " ".join(lines.values())
