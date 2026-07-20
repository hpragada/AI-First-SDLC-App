"""P2 — BuildWorkflow activity cores (idempotent; CodeHost via the capability seam).

Pure activity-core tests (no Temporal): dispatch, open-PR, merge, gate, takeover/fail
compensation. CodeHost is a fake injected through `get_capability`.
"""
from types import SimpleNamespace

import pytest
from temporalio.exceptions import ApplicationError

from apps.gates.models import Approval
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
    from orchestration import trigger as trigger_mod

    started = {}
    monkeypatch.setattr(trigger_mod, "_default_build_starter",
                        lambda workflow_id, inp: started.update(workflow_id=workflow_id, inp=inp))
    world.run.outputs = {"review_cycles": [{
        "blocking": [{"rem": "REM-C1", "severity": "critical", "title": "SQL injection",
                      "file": "db.py", "line": 42}],
        "blocking_count": 1, "findings_count": 1,
    }]}
    world.run.save(update_fields=["outputs"])

    out = ba.handle_remediation_exhausted_core(_inp(world, attempt=1))

    assert out["action"] == "retried"
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
     "Your limit will reset at 5pm.", "usage or rate limit"),
    ("Error: 429 Too Many Requests", "usage or rate limit"),
    ("The engine is overloaded, try again", "usage or rate limit"),
    # engine could not launch on the companion
    ("Failed to start Claude Code: open_process() got an unexpected keyword argument 'user'",
     "could not start"),
    # bare non-zero exit with no captured stderr (the exact WI-32 symptom) still reads clearly
    ("Command failed with exit code 1 (exit code: 1)\nError output: Check stderr output for "
     "details", "exited with an error"),
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
