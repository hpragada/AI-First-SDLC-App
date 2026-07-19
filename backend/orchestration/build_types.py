"""BuildWorkflow payloads (Phase-2 §4). Django-free so the workflow sandbox can import
them without the ORM (same rule as `types.py`)."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class BuildInput:
    """One build run = one BuildWorkflow. The companion runs the agent locally and reports
    back; the platform opens the PR and (on the merge gate) merges."""

    run_id: str
    tenant_id: str
    project_id: str
    work_item_id: str
    agent_spec_id: str
    work_item_key: str          # branch name + run prompt
    repo: str                   # "owner/name"
    base: str                   # base branch the worktree forks from
    # The work item's human title, for anything a PERSON reads: artifact titles and the PR title
    # (Bugs S.No 151). Never use work_item_key for display — it is a branch slug, and when the
    # item has no SoR id it falls back to "WI-<uuid8>", which is meaningless to a reader. Passed
    # in on the input (not read from the DB inside an activity) to keep activities deterministic.
    work_item_title: str = ""
    phase: str = "implementation"
    gate_type: str = "merge_gate"
    required_role: str = "reviewer"      # D6: the merge gate is a reviewer's call
    # If the companion (a laptop) never reports within this window, park for takeover.
    report_timeout_seconds: int = 7200
    # How long the review activity waits for the companion's 08 verdict before giving up and
    # falling through to the merge gate with no findings (Bugs S.No 110). Must comfortably
    # exceed a realistic FIRST review on a cold companion (engine cold-start + context
    # compaction can add several minutes) — 480s was too tight and skipped the remediation loop.
    review_timeout_seconds: int = 1800
    # 07<->08 remediation loop: cap re-review cycles before escalating (§5).
    max_remediation_cycles: int = 3
    # Which enrolled companion to dispatch to (the triggering user's), so the build is
    # claimable via /api/runner/work/ like a planning phase (req #1).
    enrollment_id: str | None = None


@dataclass
class BuildReport:
    """What the companion posts back after running the build locally (signal payload)."""

    status: str = "ok"          # "ok" | "failed"
    branch: str = ""
    head_sha: str = ""
    changed_files: list = field(default_factory=list)
    message: str = ""
    # The suite's own JUnit results from the worktree (D4: the companion worktree executes
    # tests; results are imported on report). [{test_ref, status, evidence}] — a summary, never
    # result bodies (#1/#3). The companion reports what it found for EVERY build; the control
    # plane decides which phases actually import them (catalog `imports_test_results`), so the
    # companion stays dumb and the routing rule lives in one place.
    test_results: list = field(default_factory=list)
    test_summary: str = ""      # "12 passed, 1 failed" — for the run console / build message
    # The companion-local preview URL the app was brought up on for a test-automation build (D7 /
    # P3-09bR): the live target 09b's Playwright explored. The platform records it on a `PreviewEnv`
    # and links it on the PR. "" for phases that bring no app up (07/11) or when no preview ran.
    preview_url: str = ""


def failure_reason(exc) -> str:
    """The human-meaningful message from a Temporal ActivityError (Bugs S.No 139): its `.cause`
    (the real ApplicationError / exception raised inside the activity — e.g. "merge conflict: …"
    or "GitHub POST …/pulls -> 422") rather than the generic "Activity task failed" wrapper that
    `str(ActivityError)` returns. Without this the classifier and the S.No 136 merge-conflict
    message never reach the user. Django-free so the workflow sandbox can import it."""
    return str(getattr(exc, "cause", None) or exc)


def display_name(inp) -> str:
    """What a PERSON should see for this work item (Bugs S.No 151): its title, falling back to the
    key only when there is no title. Artifact names and the PR title used work_item_key, which is a
    BRANCH SLUG — and with no SoR id it degrades to "WI-85bb350f", so users saw an opaque uuid
    instead of the task they triggered. (Agent-authored artifacts already read well: the platform
    registers don't-recreate and never overwrites their title — this fixes the platform's own
    fallback naming.) Django-free so the workflow sandbox can import it."""
    return (getattr(inp, "work_item_title", "") or "").strip() or inp.work_item_key


def is_empty_build(exc) -> bool:
    """True when an ActivityError was an EMPTY BUILD — the agent produced no changes, so there is
    nothing to open a PR for (raised by open_build_pr_core). This is NOT resumable (Bugs S.No 157):
    parking it for a retry would fail identically forever, because no amount of waiting makes a
    diff appear. It stays a terminal, clearly-explained failure. Same detection shape as
    is_merge_conflict: prefer the structured ApplicationError `type`, fall back to the message."""
    cause = getattr(exc, "cause", None)
    if getattr(cause, "type", "") == "EmptyBuild":
        return True
    return "empty build" in failure_reason(exc).lower()


def is_merge_conflict(exc) -> bool:
    """True when an ActivityError was a MERGE CONFLICT (Bugs S.No 141 / ENH-2), so the build can
    re-open the merge gate for a resolve-then-retry instead of failing. Prefers the structured
    ApplicationError `type` ("MergeConflict", set by merge_build_pr_core) and falls back to the
    message text — robust whether or not Temporal preserved the typed cause."""
    cause = getattr(exc, "cause", None)
    if getattr(cause, "type", "") == "MergeConflict":
        return True
    return "merge conflict" in failure_reason(exc).lower()
