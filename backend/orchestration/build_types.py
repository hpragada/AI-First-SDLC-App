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


def failure_reason(exc) -> str:
    """The human-meaningful message from a Temporal ActivityError (Bugs S.No 139): its `.cause`
    (the real ApplicationError / exception raised inside the activity — e.g. "merge conflict: …"
    or "GitHub POST …/pulls -> 422") rather than the generic "Activity task failed" wrapper that
    `str(ActivityError)` returns. Without this the classifier and the S.No 136 merge-conflict
    message never reach the user. Django-free so the workflow sandbox can import it."""
    return str(getattr(exc, "cause", None) or exc)
